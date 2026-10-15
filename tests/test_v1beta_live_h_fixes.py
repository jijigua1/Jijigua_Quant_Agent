"""Defects found by the first real-DeepSeek hardening run (H1-H4, 2026-10-14), each pinned by a test.

H2 greatwall: Chinese reports yielded no retrieval tokens (248 characters of context) and an honest "no factor" reply
crashed the turn; H1 AQR: a typed identifier was overruled by a shared topic word; H1/H4 MACD: the factor the user named
was asked again; H1 cond-mat: an algorithm with an undefined m(t) and an "optional" step reached code design; H2 hans: an
over-long structured output failed instead of being retried; H3 CORE04: a damaged PDF gave only a generic failure.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_v1beta_semantics import PROFILE, load  # noqa: E402


def test_chinese_reports_are_retrievable():
    from paper_agent.evidence import PaperEvidence, _tokens
    from paper_agent.understanding import _queries
    assert "收盘" in _tokens("其中C为收盘价") and "价格" not in _tokens("abc")
    ev, _ = load("huatai")
    rebuilt = PaperEvidence(ev.doc, ev.spec, [dict(p, tokens=_tokens(p["text"])) for p in ev.passages])
    ctx = rebuilt.context(_queries("A_n"), budget_chars=24000)
    assert sum(len(p["text"]) for p in ctx) > 8000                                       # was 633 characters


def test_an_identifier_decides_the_paper_and_a_named_factor_is_chosen():
    from research_agent.paper_library import PaperLibrary
    from research_agent.paper_tools import named_factor
    rows = [{"name": "AQR Trend following in rising rates 2023.pdf", "title": "AQR Capital Management, LLC", "heading": "", "uploaded_at": "1",
             "sha256": "a" * 64},
            {"name": "xiangcai_etf_trend_20220929.pdf", "title": "湘财证券-基金研究：趋势跟踪在行业ETF择时中的应用", "heading": "", "uploaded_at": "2",
             "sha256": "b" * 64}]
    lib = PaperLibrary.__new__(PaperLibrary)
    lib._complete_metadata = lambda: rows
    found = lib.resolve("AQR那篇趋势跟踪论文")
    assert found["status"] == "FOUND" and found["paper"]["name"].startswith("AQR")
    names = ["MACD (Moving Average Convergence Divergence)", "VPVMA (Volume Price Volume Moving Average) modified MACD"]
    assert named_factor(names, "MACD那篇") == names[0] and named_factor(names, "VPVMA") == names[1]
    assert named_factor(["Exponential Moving Average (EMA)", "Relative Strength Index (RSI)"], "1110.3383那篇技术指标论文") == ""


def test_an_algorithm_with_an_undefined_symbol_or_a_vague_step_is_stopped_before_code():
    from paper_agent.understanding import verify
    ev, replies = load("condmat")
    raw = json.loads(replies["paper_understanding"][0])
    f = raw["factors"][0]
    f.update(formula_latex="", formula_status="algorithm",
             algorithm={"steps": ["take the daily closing price y(t) and the volume V(t)",
                                  "multiply the momentum by the mass-like factor m(t) built from the volume history",
                                  "optionally rescale the volume before use"],
                        "inputs": ["y", "V"], "lookback": {"n": 21, "unit": "trading_day"},
                        "citations": f["verbal_definition"]["citations"][:1]})
    v = verify(raw, ev)
    codes = {c["code"] for c in v["factors"][0]["conflicts"] if c["blocking"]}
    assert "ALGORITHM_STEP_AMBIGUOUS" in codes
    assert any(c["code"] in ("SYMBOL_UNDEFINED", "SYMBOL_DEFINITION_UNVERIFIED") and c.get("symbol") == "m"
               for c in v["factors"][0]["conflicts"])


def test_an_honest_no_factor_reading_is_reported_not_crashed():
    from paper_agent.planner import PlanError, plan
    from paper_agent.understanding import verify
    ev, replies = load("huatai")
    raw = json.loads(replies["paper_understanding"][0])
    raw["factors"] = []
    v = verify(raw, ev)
    with pytest.raises(PlanError) as e:
        plan(ev, v, PROFILE)
    assert e.value.code == "NO_FACTOR_UNDERSTOOD"


def test_over_long_structured_output_is_retryable_and_failures_name_their_reason():
    from research_agent.contracts import canonical
    from research_agent.llm import ModelError, ModelRequest, ModelResponse, Message, Role, Usage, check_response
    from research_agent.paper_tools import tool_failure_text
    req = ModelRequest((Message(Role.USER, "x"),), output_schema={"type": "object", "properties": {"a": {"type": "string", "maxLength": 3}},
                                                                  "required": ["a"], "additionalProperties": False})
    with pytest.raises(ModelError) as e:
        check_response(ModelResponse(canonical({"a": "toolong"}), usage=Usage()), req)
    assert e.value.code == "INVALID_STRUCTURED_OUTPUT" and e.value.retryable
    text = tool_failure_text("PARSE_FAILED", "PARSE_FAILED: syntax error in content stream")
    assert "PDF 文件内部损坏" in text and "syntax error" in text
    assert "静态审核" in tool_failure_text("CANDIDATE_FAILED_STATIC_REVIEW", "CANDIDATE_FAILED_STATIC_REVIEW: WINDOW_SHORTER_THAN_DECLARED")


def test_a_paper_about_options_is_reported_as_such_before_any_factor_choice():
    from paper_agent.planner import plan
    from paper_agent.understanding import verify
    ev, replies = load("heston")
    raw = json.loads(replies["paper_understanding"][0])
    second = json.loads(json.dumps(raw["factors"][0]))
    second["name"] = "Second straddle signal"
    second["role"] = "secondary"
    first = raw["factors"][0]
    first["role"] = "secondary"
    raw["factors"] = [first, second]
    p, _, _ = plan(ev, verify(raw, ev), PROFILE)                       # no FACTOR_CHOICE_REQUIRED for an options paper
    assert p["status"] == "BLOCKED" and "options" in p["assets"]["studied"]
