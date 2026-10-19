from research_agent.security import Budget
"""Candidate6 recovery, design C: only a bare confirmation in the user's own words authorizes the shown definition.

The real Conversation holds a program-built pending proposal (exact tool, arguments, plan SHA); the router model WRONGLY
reports consent=accept every turn. A sentinel replaces the workflow engine: it records whether the program handed it an
authorization bound to the held call, and runs the REAL PaperPipeline.research definition gate with that binding, then
stops before any computation. Phrasings: Codex C9 audit conversation probe (14) + C8 / earlier question cases.
"""
import copy
from types import SimpleNamespace

import pytest

from research_agent.definition_gate import authorized, code_consent, proposal, user_consent
from test_definition_gate import GateProvider, chat, decision
from test_recovery_identity import ALGO, gate

APPROVE = ["同意。", "批准当前展示的版本。", "同意", "同意 执行吧", "好的，同意", "确认执行", "I approve", "Yes, go ahead"]
NOT_APPROVE = ["这个方案可以吗？", "请先解释风险。", "同意，不过先别运行。", "我不同意。", "如果没风险就同意。", "你觉得我应该批准吗？",
               "可以解释一下吗？", "同意，但把窗口改成5天。", "先给我看看代码，再决定。", "同意，仅供讨论。",
               "同意是假设，不代表现在授权。", "同意，待我确认后执行。", "可以，但先解释一下风险", "同意吗？", "可以", "继续",
               "我觉得可以", "ok but explain the risk first", "agree?", "go ahead and explain why", "approve after the window is fixed"]


class _Stop(Exception):
    pass


def converse(tmp_path, words):
    from test_quant_integration import research
    fx = research.__wrapped__(tmp_path)
    app = chat(fx, tmp_path, GateProvider([decision("reply", reply="回答问题", consent="accept")]))
    args = {"paper": "a" * 64, "factor": "algorithm", "plan_sha256": "b" * 64}
    pending = proposal(source="paper_program", skill_id="paper_research", original_goal="研究算法", change="算法定义待确认",
                       research_goal="研究算法", tool="qrtk_paper_research", arguments=args)
    session = app.store.session(app.session_id)
    session["pending_definition"] = pending
    app.store.save_session(session)
    seen = {}

    class Sentinel:
        def __init__(self):
            self.skill = SimpleNamespace(id="paper_research", version="test", digest="a" * 64)
            self.policy = SimpleNamespace(budget=Budget(max_model_calls=8))

        def create(self, *a, **k):
            return SimpleNamespace(id="sentinel-task", counters={"model_calls": 0}, usage={"total_tokens": 0, "unknown_reserved_tokens": 0})

        def run(self, *a, **k):
            seen["bound"] = authorized(self.definition_authorization, "qrtk_paper_research", args)
            seen["gate"] = gate(tmp_path / "pipeline", copy.deepcopy(ALGO), ctx={"definition_confirmed": seen["bound"]},
                                plan_sha256=args["plan_sha256"])
            raise _Stop()
    app.workflow_factory = lambda skill: Sentinel()
    try:
        app.turn(words)
    except _Stop:
        pass
    rows = app.store.session_turns(app.session_id)
    kinds = [e["kind"] for e in app.store.events(rows[-1]["route_task_id"])]
    return "DEFINITION_CHANGE_CONFIRMED" in kinds, seen, app.store.session(app.session_id)["pending_definition"]


@pytest.mark.parametrize("words", NOT_APPROVE)
def test_a_question_change_condition_scope_or_deferral_never_confirms(tmp_path, words):
    confirmed, seen, pending = converse(tmp_path, words)
    assert not confirmed and not seen.get("bound") and seen.get("gate") != "PASSED_DEFINITION_GATE", (words, seen)
    assert user_consent(words) != "accept" and code_consent(words) != "accept"


@pytest.mark.parametrize("words", APPROVE)
def test_a_bare_confirmation_runs_exactly_the_shown_plan(tmp_path, words):
    confirmed, seen, pending = converse(tmp_path, words)
    assert confirmed and seen["bound"] and seen["gate"] == "PASSED_DEFINITION_GATE" and pending is None, (words, seen)


def test_code_approval_and_the_asset_phrase_are_stricter():
    from research_agent.definition_gate import phrase_consent
    assert code_consent("同意") == "accept" and code_consent("批准运行这份代码") == "accept"
    assert code_consent("这段代码看起来还行吧") == "unclear" and code_consent("同意，但先改一下窗口") == "unclear"
    phrase = "用A股股票做探索性替代"
    assert phrase_consent(phrase, phrase) and phrase_consent("好的，" + phrase + "。", phrase)
    assert not phrase_consent(phrase + "，不过先解释一下", phrase) and not phrase_consent("如果可以就" + phrase, phrase)
    assert not phrase_consent("同意", phrase)


def test_a_model_claiming_consent_never_replaces_the_users_words():
    for words in NOT_APPROVE:
        assert user_consent(words) != "accept", words
    assert user_consent("不同意") == "reject" and user_consent("No, do not run it") == "reject"
