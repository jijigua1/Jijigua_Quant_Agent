"""v0.6.8: a calculating Skill whose requested definition is blocked ends deterministically, never by budget exhaustion.

Reproduces the v0.6.7 live failure (gate-v067-confirm-live-session.json): the plan declared a concrete change,
but tool selection kept returning list_research_resources until the iteration budget was exhausted.
"""
import hashlib

import numpy as np
import pandas as pd
import pytest

from research_agent.app import build, build_chat
from research_agent.contracts import canonical, fingerprint
from research_agent.definition_gate import definitional_arguments
from research_agent.llm import ModelResponse, Role, ToolCall
from research_agent.providers.mock import MockProvider

BLOCKER = ("原定义受阻：仅65个观测日，60日回看加跳过20日加5日预测约需85日。"
           "确切改变：20日回看、跳过5日、预测期5日、横截面z-score，名为 momentum_20d_skip5_exploratory。")


@pytest.fixture
def short(tmp_path):
    """65 observed days, the shape of gpushare:daily65 (synthetic values only)."""
    rng = np.random.default_rng(65)
    days = pd.bdate_range("2026-07-03", periods=65)
    codes = [f"{i:06d}" for i in range(1, 21)]
    close = 10 * np.exp(rng.normal(0, .015, (len(days), len(codes))).cumsum(axis=0))
    rows = [dict(Stkcd=c, Trddt=str(d.date()), Opnprc=close[i, j] * .999, Hiprc=close[i, j] * 1.02, Loprc=close[i, j] * .98,
                 Clsprc=close[i, j], Dnshrtrd=100000 + int(rng.integers(100000)))
            for i, d in enumerate(days) for j, c in enumerate(codes)]
    source = tmp_path / "daily65.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    resource = dict(id="synthetic:history", path=str(source), format="csv", source="fixed seeded synthetic fixture",
        approval_ref="offline test fixture", data_kind="synthetic", frequency="daily", timezone="Asia/Shanghai",
        start_date=str(days[0].date()), end_date=str(days[-1].date()), date_column="Trddt",
        fields={"Stkcd": "string", "Trddt": "date", **{c: "float" for c in ["Opnprc", "Hiprc", "Loprc", "Clsprc", "Dnshrtrd"]}},
        adjustment="none", available_time="synthetic after close", sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    manifest = tmp_path / "resources.json"
    manifest.write_text(canonical({"version": "1", "resources": [resource]}), encoding="utf-8")
    workspace = tmp_path / "workspace"
    (workspace / "research_runs").mkdir(parents=True)
    contract = dict(adjustment="none", volume_unit="shares", calendar="observed_union", available_time="synthetic after close",
                    corporate_actions="not_modelled", universe="synthetic fixed twenty codes", limits=["synthetic only"],
                    research_use="synthetic")
    config = tmp_path / "research.json"
    config.write_text(canonical(dict(version="1", workspace=str(workspace), resources={"synthetic:history": contract})), encoding="utf-8")
    return dict(manifest=manifest, config=config, workspace=workspace)


def expression(window, skip):
    return {"nodes": [{"op": "field", "field": "close"}, {"op": "returns", "args": [0], "window": window},
                      {"op": "delay", "args": [1], "window": skip}], "output": 2}


def study(window=20, skip=5, horizon=5, name="momentum_20d_skip5_exploratory"):
    return dict(resource_id="synthetic:history", expression=expression(window, skip), factor_name=name,
                hypothesis="短窗口探索替代。", reason="不是用户原始的标准定义。", horizon=horizon, n_groups=5, standardization="zscore")


class LiveShape(MockProvider):
    """Replays the v0.6.7 model behaviour: discovery first, then a declared blocker with a catalogue-only selection.

    `alternative` is what the model submits when the program restricts selection to calculation tools
    (None: the model says no legal alternative exists)."""

    def __init__(self, decisions=(), alternative=None, declare=True):
        super().__init__()
        self.decisions, self.alternative, self.declare, self.requests = iter(decisions), alternative, declare, []

    def complete(self, request):
        self.requests.append(request)
        if request.output_schema and "research_goal" in request.output_schema["properties"]:
            return next(self.decisions)
        seen = sum(x.role == Role.TOOL for x in request.messages)
        if request.tools:
            names = {t.name for t in request.tools}
            if "list_research_resources" not in names:  # the program allows only calculation tools now
                if self.alternative is None:
                    return ModelResponse("没有合法替代：所需窗口超出工具合同与样本长度。")
                return ModelResponse(tool_calls=(ToolCall("alternative", "qrtk_expression_study", self.alternative),))
            return ModelResponse(tool_calls=(ToolCall("catalog%d" % len(self.requests), "list_research_resources", {}),))
        done = any(x.role == Role.TOOL and "study_id" in x.content for x in request.messages)
        return ModelResponse(canonical(dict(action="complete" if done else "continue", hypothesis="标准动量可能延续", change_reason="核对数据后判断",
            summary="原定义受阻，需要用户确认替代。", definition_change=BLOCKER if self.declare and seen else "")))


def engine(short, tmp_path, provider):
    return build(tmp_path / "state", provider=provider, profile="development", skill_id="factor_research",
                 resources_manifest=short["manifest"], research_config=short["config"])


def runs(short):
    return [p for p in (short["workspace"] / "research_runs").rglob("*") if p.is_dir()]


def test_v067_loop_now_ends_awaiting_confirmation_with_checked_bound_alternative(short, tmp_path):
    app = engine(short, tmp_path, LiveShape(alternative=study()))
    task = app.run(app.create("按默认设定构造并验证完整动量因子").id)
    assert task.status == "AWAITING_CONFIRMATION" and task.status != "BUDGET_EXHAUSTED"
    assert [e["tool"] for e in task.experiments] == ["list_research_resources"] and not runs(short)
    kinds = [e["kind"] for e in app.store.events(task.id)]
    assert "DEFINITION_RESOLUTION_REQUIRED" in kinds and "DEFINITION_ALTERNATIVE_VALIDATED" in kinds
    held = next(e["payload"]["proposal"] for e in app.store.events(task.id) if e["kind"] == "DEFINITION_CHANGE_HELD")
    assert held["definition_sha256"] == fingerprint(definitional_arguments(study())) and held["arguments"] == study()


def test_no_legal_alternative_ends_blocked_unsupported_without_fabricating(short, tmp_path):
    app = engine(short, tmp_path, LiveShape(alternative=None))
    task = app.run(app.create("按默认设定构造并验证完整动量因子").id)
    assert task.status == "BLOCKED_UNSUPPORTED" and not runs(short)
    blocked = next(e["payload"] for e in app.store.events(task.id) if e["kind"] == "DEFINITION_BLOCKED")
    assert blocked["reason"] == BLOCKER and "没有合法替代" in blocked["model_statement"] and blocked["proposal"] is None
    assert not any(e["kind"] == "DEFINITION_CHANGE_HELD" for e in app.store.events(task.id))


@pytest.mark.parametrize("alternative,cause", [
    (study(window=60, skip=5), "INSUFFICIENT_RESEARCH_SAMPLE"),  # warm-up 65 + horizon 5 exceeds 65 observed days
    (study(horizon=20), "INVALID_PARAMETERS"),                    # horizon above the Tool contract
])
def test_alternative_failing_schema_or_data_check_is_not_proposed(short, tmp_path, alternative, cause):
    app = engine(short, tmp_path, LiveShape(alternative=alternative))
    task = app.run(app.create("按默认设定构造并验证完整动量因子").id)
    assert task.status == "BLOCKED_UNSUPPORTED" and not runs(short)
    blocked = next(e["payload"] for e in app.store.events(task.id) if e["kind"] == "DEFINITION_BLOCKED")
    assert blocked["alternative_rejected"] == cause and blocked["proposal"] is None
    assert not any(e["kind"] == "DEFINITION_CHANGE_HELD" for e in app.store.events(task.id))


def test_repeated_identical_call_without_new_information_stops_and_never_proposes(short, tmp_path):
    app = engine(short, tmp_path, LiveShape(declare=False))
    task = app.run(app.create("按默认设定构造并验证完整动量因子").id)
    assert task.status == "BLOCKED_NO_PROGRESS" and len(task.experiments) == 1
    kinds = [e["kind"] for e in app.store.events(task.id)]
    assert "REPEATED_CALL_STOPPED" in kinds and "DEFINITION_CHANGE_HELD" not in kinds


def decision(action="reply", reply="", skill_id="", goal="", change="", consent=""):
    return ModelResponse(canonical(dict(action=action, reply=reply, skill_id=skill_id, research_goal=goal,
        reason="固定测试决策", definition_change=change, consent=consent)))


def chat(short, tmp_path, provider):
    return build_chat(tmp_path / "state", provider=provider, profile="development",
                      resources_manifest=short["manifest"], research_config=short["config"])


def studies(app):
    found = []
    for i, turn in enumerate(app.store.session_turns(app.session_id)):
        for tid in turn["research_task_ids"]:
            found += [(i, e) for e in app.store.load(tid).experiments if e["tool"] == "qrtk_expression_study"]
    return found


def opening(short, tmp_path, final, alternative=None):
    provider = LiveShape([decision("clarify", reply="请确认动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认设定构造并验证完整动量因子"), final],
        alternative=alternative or study())
    app = chat(short, tmp_path, provider)
    app.turn("帮我构造一个完整的动量因子。")
    reply = app.turn("默认设定，验证目标都需要。")
    return app, provider, reply


def test_live_dialogue_shape_confirm_runs_the_saved_arguments(short, tmp_path):
    app, provider, reply = opening(short, tmp_path,
        decision("skill", skill_id="factor_research", goal="执行", consent="accept"))
    turn = app.store.session_turns(app.session_id)[1]
    assert turn["status"] == "COMPLETED" and app.store.load(turn["research_task_id"]).status == "AWAITING_CONFIRMATION"
    saved = app.store.session(app.session_id)["pending_definition"]
    assert "delay(returns(close,20),5)" in reply and "回复“同意”" in reply and not studies(app)
    provider.alternative = study(horizon=3)  # whatever the model would now say is ignored
    final = app.turn("可以，先完成20日探索版本。")
    (index, experiment), = studies(app)
    assert index == 2 and experiment["parameters"] == saved["arguments"]
    assert fingerprint(definitional_arguments(experiment["parameters"])) == saved["definition_sha256"]
    data = experiment["result"]["data"]
    assert data["delivery_status"] == "VERIFIED" and data["factor_path"] and data["html_path"]
    assert "原研究定义尚未完成" in final and app.store.session(app.session_id)["pending_definition"] is None


def test_live_dialogue_shape_reject_clears_the_proposal(short, tmp_path):
    app, _, _ = opening(short, tmp_path, decision(reply="标准方案需要更长历史。", consent="reject"))
    reply = app.turn("不要替代，我要原来的标准方案。")
    assert "已保留原研究定义" in reply and not studies(app) and not runs(short)
    assert app.store.session(app.session_id)["pending_definition"] is None


def test_live_dialogue_shape_without_legal_alternative_reports_blocked(short, tmp_path):
    provider = LiveShape([decision("clarify", reply="请确认动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认设定构造并验证完整动量因子")], alternative=None)
    app = chat(short, tmp_path, provider)
    app.turn("帮我构造一个完整的动量因子。")
    reply = app.turn("默认设定，验证目标都需要。")
    turn = app.store.session_turns(app.session_id)[1]
    assert turn["status"] == "COMPLETED" and app.store.load(turn["research_task_id"]).status == "BLOCKED_UNSUPPORTED"
    assert "无法执行" in reply and "没有合法替代" in reply and app.store.session(app.session_id).get("pending_definition") is None
