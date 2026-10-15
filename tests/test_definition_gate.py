"""Research-definition consent gate: no substitute study runs before the user explicitly confirms it."""
from dataclasses import replace
from pathlib import Path

import pytest

from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.definition_gate import user_consent
from research_agent.llm import ModelResponse, Role, ToolCall
from research_agent.providers.mock import MockProvider
from test_quant_integration import args, engine, research  # noqa: F401  (fixture)

STUDY_TOOLS = {"qrtk_factor_study", "qrtk_expression_study"}
MOMENTUM = {"nodes": [{"op": "field", "field": "close"}, {"op": "returns", "args": [0], "window": 20},
                      {"op": "delay", "args": [1], "window": 5}], "output": 2}
CHANGE = "标准长周期动量超出65日样本与工具窗口/预测期合同；改为20日动量、跳过5日、预测期5日的探索版本。"


def momentum_call(call_id="short_momentum", **changes):
    return ToolCall(call_id, "qrtk_expression_study", dict(resource_id="synthetic:history", expression=MOMENTUM,
        factor_name="momentum_20d_skip5_exploratory", hypothesis="短窗口探索替代：20日价格动量跳过最近5日。",
        reason="不是用户原始的标准长周期动量。", horizon=5, n_groups=5, standardization="zscore") | changes)


def decision(action="reply", reply="", skill_id="", goal="", change="", consent=""):
    return ModelResponse(canonical(dict(action=action, reply=reply, skill_id=skill_id, research_goal=goal,
        reason="固定测试决策", definition_change=change, consent=consent)))


class GateProvider(MockProvider):
    """Scripted router decisions; the research workflow always proposes the same calculation."""

    def __init__(self, decisions, call=None, plan_change=""):
        super().__init__()
        self.decisions, self.call, self.plan_change, self.requests = iter(decisions), call or momentum_call(), plan_change, []

    def complete(self, request):
        self.requests.append(request)
        if request.output_schema and "research_goal" in request.output_schema["properties"]:
            return next(self.decisions)
        if request.tools:
            if self.call.name not in {t.name for t in request.tools}:  # data-only Skill
                return ModelResponse(tool_calls=(ToolCall("catalog%d" % len(self.requests), "list_research_resources", {}),))
            return ModelResponse(tool_calls=(self.call,))
        done = any(x.role == Role.TOOL for x in request.messages)
        return ModelResponse(canonical(dict(action="complete" if done else "continue", hypothesis="动量可能延续",
            change_reason="记录实际计算", summary="合成数据探索性结果；不是市场有效性结论。",
            definition_change=self.plan_change)))


def chat(research, tmp_path, provider):
    return build_chat(tmp_path / "state", provider=provider, profile="development",
                      resources_manifest=research["manifest"], research_config=research["config"])


def study_events(app):
    """(turn index, event kind) for every executed new-study experiment in the session."""
    found = []
    for i, turn in enumerate(app.store.session_turns(app.session_id)):
        if turn["research_task_id"]:
            for e in app.store.events(turn["research_task_id"]):
                if e["kind"] == "EXPERIMENT_RECORDED" and e["payload"]["tool"] in STUDY_TOOLS:
                    found.append((i, e["payload"]))
    return found


def runs(research):
    return [p for p in (research["workspace"] / "research_runs").rglob("*") if p.is_dir()]


def unconfirmed(research, tmp_path, decisions, **kwargs):
    app = chat(research, tmp_path, GateProvider(decisions, **kwargs))
    first = app.turn("帮我构造一个完整的动量因子。")
    second = app.turn("默认设定，验证目标都需要。")
    return app, first, second


# Scenario A: the workflow tries the substitute without confirmation (the v0.6.5 live failure).
@pytest.mark.parametrize("plan_change", ["", CHANGE])
def test_scenario_a_workflow_substitute_is_held_before_any_calculation(research, tmp_path, plan_change):
    app, _, reply = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义与窗口。"),
        decision("skill", skill_id="factor_research", goal="按默认参数构造并检验完整动量因子")], plan_change=plan_change)
    turn = app.store.session_turns(app.session_id)[1]
    task = app.store.load(turn["research_task_id"])
    assert turn["status"] == "COMPLETED" and task.status == "AWAITING_CONFIRMATION"
    assert not task.experiments and not study_events(app) and not runs(research)
    kinds = [e["kind"] for e in app.store.events(task.id)]
    assert "DEFINITION_CHANGE_HELD" in kinds and "AUTHORIZATION_ALLOWED" not in kinds
    pending = app.store.session(app.session_id)["pending_definition"]
    assert pending["tool"] == "qrtk_expression_study" and "delay(returns(close,20),5)" in pending["description"]
    assert "没有运行替代实验" in reply and "回复“同意”" in reply and "delay(returns(close,20),5)" in reply


def test_scenario_a_router_proposal_is_bound_to_held_arguments_without_running(research, tmp_path):
    app, _, reply = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义。"),
        decision("propose", reply="标准动量无法完成：仅65个观测日。可先做20日探索版本。", skill_id="factor_research",
                 goal="构造20日动量跳过5日、预测期5日的探索因子", change=CHANGE)])
    turn = app.store.session_turns(app.session_id)[1]
    assert turn["research_task_id"] is None and len(turn["research_task_ids"]) == 1
    probe = app.store.load(turn["research_task_ids"][0])
    assert probe.status == "AWAITING_CONFIRMATION" and not probe.experiments
    pending = app.store.session(app.session_id)["pending_definition"]
    assert pending["change"] == CHANGE and pending["definition_sha256"] and pending["arguments"]["horizon"] == 5
    assert "仅65个观测日" in reply and "delay(returns(close,20),5)" in reply and "回复“同意”" in reply
    assert not study_events(app) and not runs(research)


def test_router_skill_with_declared_change_is_converted_to_a_proposal(research, tmp_path):
    app, _, reply = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义。"),
        decision("skill", skill_id="factor_research", goal="20日动量探索版本", change=CHANGE)])
    assert all(t["research_task_id"] is None for t in app.store.session_turns(app.session_id))
    assert app.store.session(app.session_id)["pending_definition"]["change"] == CHANGE
    assert not study_events(app) and not runs(research)


# Scenario B: explicit confirmation runs exactly the held definition and keeps the original-definition note.
def test_scenario_b_confirmation_runs_exact_held_definition_with_full_delivery(research, tmp_path):
    app, _, _ = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认参数构造完整动量因子"),
        decision("skill", skill_id="factor_research", goal="执行已确认方案", consent="accept")])
    assert not study_events(app)
    reply = app.turn("可以，先完成20日探索版本。")
    (index, experiment), = study_events(app)
    assert index == 2 and experiment["parameters"]["factor_name"] == "momentum_20d_skip5_exploratory"
    data = experiment["result"]["data"]
    assert data["delivery_status"] == "VERIFIED" and Path(data["factor_path"]).exists()
    assert Path(data["html_path"]).exists() and data["figure_paths"] and not data["formal_backtest_ready"]
    assert Path(data["artifact_path"], "data", "factor_metrics.csv").exists()
    assert "原研究定义尚未完成" in reply and "因子 PKL（已验证）" in reply
    turn = app.store.session_turns(app.session_id)[2]
    route = [e["kind"] for e in app.store.events(turn["route_task_id"])]
    assert route.index("DEFINITION_CHANGE_CONFIRMED") < route.index("SKILL_SELECTED")
    assert any(e["kind"] == "DEFINITION_CHANGE_AUTHORIZED" for e in app.store.events(turn["research_task_id"]))
    assert app.store.session(app.session_id)["pending_definition"] is None


def test_confirmation_executes_the_saved_arguments_not_a_regenerated_call(research, tmp_path):
    provider = GateProvider([decision(reply="请说明动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认参数构造完整动量因子"),
        decision("skill", skill_id="factor_research", goal="执行已确认方案", consent="accept")])
    app = chat(research, tmp_path, provider)
    app.turn("帮我构造一个完整的动量因子。")
    app.turn("默认设定，验证目标都需要。")
    saved = app.store.session(app.session_id)["pending_definition"]
    provider.call = momentum_call(horizon=3)  # the model would now propose something else
    app.turn("同意")
    (_, experiment), = study_events(app)
    assert experiment["parameters"] == saved["arguments"] and experiment["parameters"]["horizon"] == 5
    from research_agent.contracts import fingerprint
    from research_agent.definition_gate import definitional_arguments
    assert fingerprint(definitional_arguments(experiment["parameters"])) == saved["definition_sha256"]


def test_authorized_task_still_holds_a_different_later_definition(research, tmp_path):
    from research_agent.definition_gate import proposal
    held = momentum_call()
    app = engine(research, tmp_path, GateProvider([], call=momentum_call("other", horizon=3)))
    app.definition_authorization = proposal(source="test", skill_id="factor_research", original_goal="动量", change=CHANGE,
                                            research_goal="动量", tool=held.name, arguments=held.arguments)
    app.definition_authorization.pop("arguments")  # bound by fingerprint only: the model must reproduce it exactly
    task = app.run(app.create("动量").id)
    assert task.status == "AWAITING_CONFIRMATION" and not task.experiments and not runs(research)


# Scenario C: refusal keeps the original definition and never runs the short-window study.
@pytest.mark.parametrize("consent", ["reject", "accept"])
def test_scenario_c_refusal_keeps_original_definition(research, tmp_path, consent):
    app, _, _ = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认参数构造完整动量因子"),
        decision(reply="标准方案需要更长历史与更长预测期的工具合同。", consent=consent)])
    reply = app.turn("不要替代，我要原来的标准方案。")
    turn = app.store.session_turns(app.session_id)[2]
    assert turn["research_task_id"] is None and not study_events(app) and not runs(research)
    assert "已保留原研究定义" in reply and "未运行替代实验" in reply
    assert app.store.session(app.session_id)["pending_definition"] is None
    assert any(e["kind"] == "DEFINITION_CHANGE_REJECTED" for e in app.store.events(turn["route_task_id"]))


def test_model_claimed_consent_without_explicit_user_approval_does_not_run(research, tmp_path):
    app, _, _ = unconfirmed(research, tmp_path, [decision(reply="请说明动量定义。"),
        decision("skill", skill_id="factor_research", goal="按默认参数构造完整动量因子"),
        decision("skill", skill_id="factor_research", goal="执行", consent="accept")])
    reply = app.turn("这个方案的窗口是多少？")
    assert "需要你的明确确认" in reply and not study_events(app) and not runs(research)
    assert app.store.session(app.session_id)["pending_definition"] is not None


@pytest.mark.parametrize("text,expected", [("同意", "accept"), ("可以，先完成20日探索版本。", "accept"),
    ("先完成能做的部分", "accept"), ("OK, go ahead", "accept"), ("不要替代，我要原来的标准方案。", "reject"),
    ("不可以", "reject"), ("no", "reject"), ("这个窗口是多少？", "unclear"), ("now what", "unclear")])
def test_user_consent_reading(text, expected):
    assert user_consent(text) == expected


def test_declared_change_on_fixed_factor_is_also_held(research, tmp_path):
    provider = GateProvider([], call=ToolCall("fixed", "qrtk_factor_study", args(lookback=10)),
                            plan_change="用户要求20日回看，固定入口最多20但样本不足，改为10日。")
    app = engine(research, tmp_path, provider)
    task = app.run(app.create("20日反转").id)
    assert task.status == "AWAITING_CONFIRMATION" and not task.experiments and not runs(research)


def test_gate_does_not_mask_parameter_or_authorization_errors(research, tmp_path):
    bad = engine(research, tmp_path, GateProvider([], call=momentum_call(horizon=20)))
    task = bad.run(bad.create("动量").id)
    assert task.status == "INVALID_PARAMETERS" and task.error["code"] == "INVALID_PARAMETERS"
    other = engine(research, tmp_path, GateProvider([], call=momentum_call()))
    other.policy = replace(other.policy, write_scopes=())  # policy denial must win over the consent gate
    task = other.run(other.create("动量").id)
    assert task.status == "AUTHORIZATION_DENIED" and task.error["code"] == "TOOL_EFFECT_DENIED"
    assert not any(e["kind"] == "DEFINITION_CHANGE_HELD" for e in other.store.events(task.id))


def test_unchanged_definition_still_runs_without_confirmation(research, tmp_path):
    app = engine(research, tmp_path, GateProvider([], call=ToolCall("fixed", "qrtk_factor_study", args())))
    task = app.run(app.create("五日反转").id)
    assert task.status == "COMPLETED" and task.experiments[0]["result"]["data"]["delivery_status"] == "VERIFIED"


def test_data_check_turn_ends_with_bound_proposal_then_confirmation_runs(research, tmp_path):
    provider = GateProvider([decision(reply="请说明动量定义。"),
        decision("skill", skill_id="data_research", goal="核验数据能否支持标准动量"),
        decision("propose", reply="仅65个观测日，标准长周期动量无法完成。", skill_id="factor_research",
                 goal="20日动量跳过5日、预测期5日的探索因子", change=CHANGE),
        decision("skill", skill_id="factor_research", goal="执行", consent="accept")])
    app = chat(research, tmp_path, provider)
    app.turn("帮我构造一个完整的动量因子。")
    reply = app.turn("默认设定，验证目标都需要。")
    turn = app.store.session_turns(app.session_id)[1]
    assert turn["status"] == "COMPLETED" and app.store.load(turn["research_task_id"]).skill_id == "data_research"
    assert "回复“同意”" in reply and "delay(returns(close,20),5)" in reply and not study_events(app)
    app.turn("可以，先完成20日探索版本。")
    (index, experiment), = study_events(app)
    assert index == 2 and experiment["result"]["data"]["delivery_status"] == "VERIFIED"


def test_refusal_before_any_proposal_saves_nothing(research, tmp_path):
    app = chat(research, tmp_path, GateProvider([decision("propose", reply="可改为20日。", skill_id="factor_research",
        goal="20日动量", change=CHANGE)]))
    reply = app.turn("不要替代，我要原来的标准方案。")
    turn = app.store.session_turns(app.session_id)[0]
    assert turn["research_task_ids"] == [] and app.store.session(app.session_id).get("pending_definition") is None
    assert "已保留原研究定义" in reply and not runs(research)


def test_data_skill_declaring_a_change_completes_instead_of_looping(research, tmp_path):
    app = engine(research, tmp_path, GateProvider([], plan_change=CHANGE), skill="data_research")
    task = app.run(app.create("核验数据").id)
    assert task.status == "COMPLETED" and task.counters["iterations"] <= 2
