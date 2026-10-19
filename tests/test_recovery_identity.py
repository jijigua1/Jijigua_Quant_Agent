"""Candidate6 recovery, design B: a non-IR algorithm's identity is exactly what was shown, and its approval never travels.

Recorded collisions of earlier candidates, through the REAL planner._algorithm_plan and canonical.definition:
  C6 audit F02  '5-day mean' and '20-day std' shared one SHA (no algorithm key at all)
  C7 re-audit   '1.5 * close' and '5 * close' (a decimal read as a step number)
  C8 audit      P/Q with swapped field bindings (P=close,Q=open vs P=open,Q=close): 2 vs 0.5 at close=10, open=5
  C9 audit      names inside string constants rewritten: "P if 'P' == 'P' else 0" vs "P if 'P' == 'Q' else 0": 10 vs 0
and the C7 re-audit F03 bypass: an approval from another session ran a new algorithm without this session's confirmation.
"""
import pytest

from paper_agent.canonical import definition
from paper_agent.definitions import DefinitionRegistry


def algo(steps, bindings, rows=5, horizon=1):
    from paper_agent.planner import _algorithm_plan
    from test_v1beta_semantics import PROFILE
    fac = {"name": "algo", "holding_period": {}, "symbols": [{"symbol": s, "data_field": f, "kind": "raw_field"} for s, f in bindings],
           "algorithm": {"steps": list(steps), "inputs": [s for s, _ in bindings], "lookback": {"n": rows, "unit": "day"}, "citations": []}}
    p, _, _ = _algorithm_plan({}, fac, PROFILE, "daily", [], [], [], {"decision": "EQUITY_STOCK_COMPATIBLE"}, horizon)
    rec, digest = definition(p, None, {"factors": [{"name": "algo", "parameters": []}]},
                             paper={"sha256": "a" * 64, "name": "synthetic paper", "version": 1})
    return p, rec, digest


PAIRS = [   # (case, A, B) each (steps, bindings, rows, horizon): mathematically different -> different identity
    ("c6_f02_mean_vs_std", (["average last 5 close prices"], [("P", "close")], 5, 1),
     (["standard deviation of last 20 close prices"], [("P", "close")], 20, 1)),
    ("c7_decimal_vs_integer", (["Return 1.5 * P"], [("P", "close")], 5, 1), (["Return 5 * P"], [("P", "close")], 5, 1)),
    ("c8_swapped_bindings", (["Compute P / Q"], [("P", "close"), ("Q", "open")], 5, 1),
     (["Compute P / Q"], [("P", "open"), ("Q", "close")], 5, 1)),
    ("c9_names_inside_quotes", (["Compute P if 'P' == 'P' else 0"], [("P", "close"), ("Q", "close")], 5, 1),
     (["Compute P if 'P' == 'Q' else 0"], [("P", "close"), ("Q", "close")], 5, 1)),
    ("operator", (["Compute P - Q"], [("P", "close"), ("Q", "open")], 5, 1), (["Compute P + Q"], [("P", "close"), ("Q", "open")], 5, 1)),
    ("input_field", (["Compute P"], [("P", "close")], 5, 1), (["Compute P"], [("P", "high")], 5, 1)),
    ("window", (["mean of P"], [("P", "close")], 5, 1), (["mean of P"], [("P", "close")], 20, 1)),
    ("horizon", (["mean of P"], [("P", "close")], 5, 1), (["mean of P"], [("P", "close")], 5, 5)),
    ("step_order", (["A then B", "B"], [("P", "close")], 5, 1), (["B", "A then B"], [("P", "close")], 5, 1)),
    ("negative_sign", (["Return -1 * P"], [("P", "close")], 5, 1), (["Return 1 * P"], [("P", "close")], 5, 1)),
    ("scientific", (["Return 1e-3 * P"], [("P", "close")], 5, 1), (["Return 1e+3 * P"], [("P", "close")], 5, 1)),
]


@pytest.mark.parametrize("case,a,b", PAIRS, ids=[x[0] for x in PAIRS])
def test_different_algorithms_never_share_an_identity(case, a, b):
    pa, ra, sa = algo(*a)
    pb, rb, sb = algo(*b)
    assert sa != sb, case
    part = "time" if case == "horizon" else "algorithm"                  # the horizon is part of every definition's time
    assert ra["math"][part] != rb["math"][part], case
    assert pa["definition_sha256"] != pb["definition_sha256"]


def test_hand_values_of_the_recorded_collisions():
    close, open_ = 10.0, 5.0
    assert close / open_ == 2.0 and open_ / close == 0.5                  # C8: swapped bindings
    assert (close if "P" == "P" else 0) == 10.0 and (close if "P" == "Q" else 0) == 0    # C9: names inside quotes
    assert 1.5 * close == 15.0 and 5 * close == 50.0                      # C7: decimal vs integer


def test_the_same_algorithm_is_one_definition_and_the_identity_is_versioned():
    a = algo(["Compute P / Q"], [("P", "close"), ("Q", "open")])
    b = algo(["Compute P / Q"], [("Q", "open"), ("P", "close")])          # binding order of the model's list: irrelevant
    assert a[2] == b[2]
    assert a[1]["math"]["algorithm"]["contract"] == "algorithm-contract/recovery-1"
    assert a[1]["math"]["algorithm"]["steps"] == ["Compute P / Q"]          # exactly as shown, never rewritten
    assert a[1]["math"]["algorithm"]["bindings"] == {"P": {"field": "close", "adjustment": None}, "Q": {"field": "open", "adjustment": None}}


def test_an_approval_belongs_to_one_algorithm_and_algorithms_are_never_reused(tmp_path):
    _, a, sa = algo(["Compute P / Q"], [("P", "close"), ("Q", "open")])
    _, b, sb = algo(["Compute P / Q"], [("P", "open"), ("Q", "close")])
    reg = DefinitionRegistry(tmp_path)
    for rec in (a, b):
        reg.propose(rec, plan_status="AWAITING_USER_DECISION", user_params={}, session_id="s1")
    reg.approve(sa, session_id="s1", task_id="t1", substitutions=[], asset_phrase=False)
    reg.freeze(sa, needs_approval=True)
    assert reg.approved(sa) and not reg.approved(sb)
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="", user_params={}) is None


# ---------------------------------------------------------------- the real PaperPipeline.research gate (C7 audit F03)
class _Sentinel(Exception):
    """Anything past the definition gate (rationale, code approval, computation) stops here."""


def gate(tmp_path, plan, *, approvals=(), ctx=None, plan_sha256=""):
    import copy
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import patch
    from paper_agent.evidence import PaperEvidence
    from paper_agent.ledger import TaskLedger
    from paper_agent.understanding import VERSION
    from research_agent.definition_gate import DefinitionDecisionRequired
    from research_agent.paper_tools import PIPELINE, PaperPipeline, program_sha256
    from research_agent.security import Denied
    entry = {"sha256": "a" * 64, "name": "synthetic paper", "version": 1}
    u = {"version": VERSION, "program_sha256": program_sha256(),
         "factors": [{"name": plan["factor"], "parameters": [], "frequency": {"value": "daily"},
                      "verbal_definition": {"value": "synthetic factor"}, "formula": {"latex": None}}]}
    lib = SimpleNamespace(root=tmp_path, resolve=lambda p: {"status": "FOUND", "paper": entry}, touch=lambda sha: None,
                          path=lambda e: tmp_path / "unused.pdf")
    pipe = PaperPipeline(SimpleNamespace(papers=lib, approved_registry=object(), validation_pairs={"s:train": "s:valid"}))
    pipe._plan = lambda *a: copy.deepcopy(plan)
    pipe._decision = lambda *a: {"arguments": {"plan_sha256": plan["definition_sha256"]}, "tool": "qrtk_paper_research"}

    def stop(*a, **k):
        raise _Sentinel()
    pipe._rationale = stop
    key = hashlib.sha256((entry["sha256"] + "|" + PIPELINE).encode()).hexdigest()[:32]
    ledger = TaskLedger(tmp_path, key, goal="synthetic")
    ledger.write_artifact("understanding.json", u)
    rec, sha_ = definition(plan, None, u, paper=entry)
    reg = DefinitionRegistry(ledger.dir)
    reg.propose(rec, plan_status=plan["status"], user_params={}, session_id="old_session")
    for session in approvals:
        reg.approve(sha_, session_id=session, task_id="old_task", substitutions=[], asset_phrase=False)
    context = dict({"task_id": "new_task", "session_id": "new_session", "user_text": "研究这个因子", "emit": lambda *a: None}, **(ctx or {}))
    with patch.object(PaperEvidence, "build", return_value=SimpleNamespace(spec={}, doc={"blocks": []})):
        try:
            pipe.research("synthetic", plan["factor"], context, plan_sha256=plan_sha256)
            return "RETURNED"
        except DefinitionDecisionRequired:
            return "CONFIRMATION_REQUIRED"
        except _Sentinel:
            return "PASSED_DEFINITION_GATE"
        except Denied as e:
            return "DENIED:" + str(e)


ALGO = {"factor": "algorithm", "status": "AWAITING_USER_DECISION", "route": "algorithm", "ir_execution_json": None,
        "ir_execution": "average last 5 close prices", "warmup_rows": 5, "symbol_map": {"P": {"field": "close"}},
        "choices": {"label_lag": 1, "horizon": {"n": 1}}, "assets": {"decision": "EQUITY_STOCK_COMPATIBLE"},
        "asset_consent_required": False, "substitutions": [], "task_id": None, "mode": "EXPLORATORY_REPLICATION",
        "algorithm_contract": {"algorithm": {"steps": ["average last 5 close prices"], "lookback_rows": 5}},
        "definition_sha256": "b" * 64, "hard_stops": []}


@pytest.mark.parametrize("approvals,ctx,plan_sha,expected", [
    ((), {}, "", "CONFIRMATION_REQUIRED"),
    (("new_session",), {}, "", "CONFIRMATION_REQUIRED"),
    (("old_session",), {}, "", "CONFIRMATION_REQUIRED"),                                   # C7-F03: a historical approval
    (("old_session",), {"definition_confirmed": True}, "", "DENIED:PAPER_CONFIRMATION_WITHOUT_DEFINITION"),
    (("old_session",), {"definition_confirmed": True}, "c" * 64, "DENIED:PAPER_PLAN_CHANGED_SINCE_CONFIRMATION"),
    (("old_session",), {}, "b" * 64, "CONFIRMATION_REQUIRED"),                             # a SHA without a confirmation
    ((), {"definition_confirmed": True}, "b" * 64, "PASSED_DEFINITION_GATE"),              # this conversation, exact plan
])
def test_an_algorithm_runs_only_on_this_conversations_confirmation_of_the_shown_plan(tmp_path, approvals, ctx, plan_sha, expected):
    assert gate(tmp_path, ALGO, approvals=approvals, ctx=ctx, plan_sha256=plan_sha) == expected
