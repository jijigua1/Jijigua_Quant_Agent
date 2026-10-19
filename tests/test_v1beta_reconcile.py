"""AI reading x deterministic program analysis (2026-10-14, after live round 2).

Live round 2 lost papers to: symbolic counts the grammar cannot read (MACD ema_{N_fast}, RSI X-1, cond-mat tau / M-1)
reported as "the paper's formula is unparseable"; values the reader invented for them ("conventional 14 days", "one
year = 250"); a JSON bracket mismatch repeated verbatim after a character-offset hint (AQR, xiangcai); a session token
budget reported as a model error (Huatai); a math-italic quote the program could not read (MACD "𝑐𝑙𝑜𝑠𝑖𝑛𝑔 𝑝𝑟𝑖𝑐𝑒").
Real staging evidence (tests/fixtures_v1beta/papers) is used; the reader's replies are written here.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_v1beta_semantics import PROFILE, load  # noqa: E402

from paper_agent.ledger import TaskLedger  # noqa: E402
from paper_agent.model import ModelFailure, ScriptedClient, _syntax_hint, ask_json  # noqa: E402
from paper_agent.planner import plan  # noqa: E402
from paper_agent.reconcile import accept_claim, bind_parameters, run_request, substitute, symbolic_counts  # noqa: E402
from paper_agent.understanding import _investigate, reverify, verify  # noqa: E402


def ledger(tmp_path):
    return TaskLedger(tmp_path, goal="t", budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                     design_revisions=2, orchestration_turns=0))


def cite(ev, pid, quote):
    assert ev.verify_quote(pid, quote), (pid, quote)
    return {"passage": pid, "quote": quote}


def label(value, cits=()):
    return {"value": value, "citations": list(cits)}


def factor(ev, name, latex, symbols, parameters=None, status="restated_from_prose", cits=()):
    return {"name": name, "role": "primary", "verbal_definition": label(name, cits), "formula_latex": latex,
            "formula_status": status, "formula_citations": list(cits), "symbols": symbols, "parameters": parameters or [],
            "direction": label("unstated"), "frequency": label("daily"), "signal_timing": label("unstated"),
            "holding_period": label("unstated"), "sample": label("unstated"), "portfolio_rules": label("unstated")}


def reading(*factors):
    return {"research_question": label("unstated"), "hypothesis": label("unstated"), "factors": list(factors),
            "results_vs_methods": [], "unstated_details": [], "replication_notes": []}


def codes(f, blocking=True):
    return {c["code"] for c in f["conflicts"] if c["blocking"] or not blocking}


# ------------------------------------------------------------------ named parameters

def test_symbolic_counts_are_parameters_not_parse_failures():
    assert symbolic_counts(r"MACD_{i,t} = \operatorname{ema}_{N_{fast}}(close_{i,t}) - \operatorname{ema}_{N_{slow}}(close_{i,t})") == ["N_fast", "N_slow"]
    assert symbolic_counts(r"RS_{i,t} = \operatorname{mean}_{k=0}^{X-1}(close_{i,t-k})") == ["X"]
    assert symbolic_counts(r"R^{\Sigma}_{\tau,t} = \operatorname{mean}_{k=0}^{\tau-1}(y_{i,t-k} - y_{i,t-k-\tau})") == [r"\tau"]
    assert symbolic_counts(r"M_{i,t} = \operatorname{mean}_{k=0}^{20}(close_{i,t-k})") == []
    assert substitute(r"\operatorname{mean}_{k=0}^{X-1}(P_{i,t-k})", "X", 14) == r"\operatorname{mean}_{k=0}^{13}(P_{i,t-k})"
    assert substitute(r"y_{i,t-k-\tau}", "τ", 21) == r"y_{i,t-k-21}"


def test_macd_parameters_bound_from_the_papers_own_quote():
    ev, _ = load("macd")
    q = cite(ev, "P0392", "traditional MACD parameter (12,26,9)")
    params = [{"symbol": "N_{fast}", "meaning": "fast EMA span", "value": 12, "paper_values": [12], "status": "stated", "citations": [q]},
              {"symbol": "N_{slow}", "meaning": "slow EMA span", "value": 26, "paper_values": [26], "status": "stated", "citations": [q]}]
    latex = r"MACD_{i,t} = \operatorname{ema}_{N_{fast}}(close_{i,t}) - \operatorname{ema}_{N_{slow}}(close_{i,t})"
    out, recs, conf = bind_parameters(latex, params, lambda c: [ev.verify_quote(x["passage"], x["quote"]) for x in c])
    assert out == r"MACD_{i,t} = \operatorname{ema}_{12}(close_{i,t}) - \operatorname{ema}_{26}(close_{i,t})"
    assert [r["status"] for r in recs] == ["PAPER", "PAPER"] and not conf


def test_an_unstated_count_waits_for_the_user_and_a_typed_value_is_recorded(tmp_path):
    ev, _ = load("ti1110")
    d = cite(ev, "P0095", "Where RS is the average of X days price rises / X days price drops")
    sym = [{"symbol": "P", "meaning": "share price", "kind": "raw_field", "data_field": "close", "citations": [d]}]
    f = factor(ev, "Relative Strength Index (RSI)",
               r"RS_{i,t} = \frac{\operatorname{mean}_{k=0}^{X-1}(\max(P_{i,t-k} - P_{i,t-k-1}, 0))}{\operatorname{mean}_{k=0}^{X-1}(\max(P_{i,t-k-1} - P_{i,t-k}, 0))}",
               sym, [{"symbol": "X", "meaning": "RSI window in days", "value": None, "paper_values": [], "status": "unstated", "citations": [d]}],
               cits=[d])
    v = verify(reading(f), ev)
    g = v["factors"][0]
    unbound = [c for c in g["conflicts"] if c["code"] == "FREE_PARAMETER_UNBOUND"]
    assert unbound and unbound[0]["source"] == "free_parameter" and "X=20" in unbound[0]["detail"]
    assert "FORMULA_UNPARSEABLE" not in codes(g)                     # not "the paper's formula is unparseable"
    # an invented value (the live reply's "conventional 14 days") is not bound
    f2 = json.loads(json.dumps(f))
    f2["parameters"][0].update(value=14, status="stated")
    g2 = verify(reading(f2), ev)["factors"][0]
    assert "PARAMETER_VALUE_UNVERIFIED" in codes(g2) and g2["parameters"][0]["status"] == "UNVERIFIED"
    # the user's own value: bound, recorded as USER, shown as a parameter choice, never as the paper's
    u = reverify(dict(v, reading={"initial": [], "final": reading(f)}), ev, {"X": 14})
    g3 = u["factors"][0]
    assert g3["parameters"][0]["status"] == "USER" and "^{13}" in g3["formula"]["latex"]
    assert g3["formula"]["latex_as_written"].count("X-1") == 2
    assert not codes(g3) and "PARAMETER_CHOSEN_NOT_IN_PAPER" in codes(g3, blocking=False)
    p, _, _ = plan(ev, u, PROFILE, factor=g3["name"])
    assert any(s["kind"] == "parameter_choice" for s in p["substitutions"])


def test_an_undeclared_count_goes_to_formula_repair_not_to_the_user():
    """Amihud's D (days with data in year y) is a calendar window, not a free parameter: the repair uses its nominal length."""
    ev, _ = load("amihud")
    f = factor(ev, "ILLIQ", r"ILLIQ_{i,t} = \operatorname{mean}_{k=0}^{D-1}(close_{i,t-k})", [])
    c = next(c for c in verify(reading(f), ev)["factors"][0]["conflicts"] if c["blocking"])
    assert c["code"] == "FORMULA_UNPARSEABLE" and "UNDECLARED_SYMBOLIC_COUNT: D" in c["detail"]


def test_unsupported_notation_is_program_parse_incomplete():
    ev, _ = load("macd")
    f = factor(ev, "X", r"X_{i,t} = \operatorname{weird}(close_{i,t})", [])
    c = next(c for c in verify(reading(f), ev)["factors"][0]["conflicts"] if c["code"] == "FORMULA_UNPARSEABLE")
    assert c["parse_status"] == "PROGRAM_PARSE_INCOMPLETE" and c["source"] == "unsupported_notation"


def test_math_italic_quotes_are_read_by_the_program():
    from paper_agent.semantics import FIELD_WORDS, plain
    import re
    assert re.search(FIELD_WORDS["close"], plain("𝐸𝑀𝐴_{𝑡}= 𝛼∗𝑐𝑙𝑜𝑠𝑖𝑛𝑔 𝑝𝑟𝑖𝑐𝑒_{𝑡}"), re.I)


def test_degenerate_terms_point_to_the_page():
    ev, _ = load("macd")
    f = factor(ev, "X", r"X_{i,t} = close_{i,t} - close_{i,t}", [])
    g = verify(reading(f), ev)["factors"][0]
    c = next(c for c in g["conflicts"] if c["code"] == "FORMULA_DEGENERATE_TERMS")
    assert c["blocking"] and c["source"] == "extraction_error"


# ------------------------------------------------------------------ the reader's bounded investigation

def _condmat_reading(ev, with_param):
    y = cite(ev, "P0019", "the average of y over the last")
    price = cite(ev, "P0005", "not only the price of a stock")
    sym = [{"symbol": "y", "meaning": "daily closing price", "kind": "raw_field", "data_field": "close", "citations": [price]}]
    params = [{"symbol": "τ", "meaning": "momentum period", "value": 21, "paper_values": [21], "status": "stated",
               "citations": [cite(ev, "P0028", "for time interval, τ = 21")]}] if with_param else \
        [{"symbol": "τ", "meaning": "momentum period", "value": None, "paper_values": [], "status": "unstated", "citations": []}]
    return reading(factor(ev, "Classical momentum indicator (CMI)",
                          r"CMI_{i,t} = \operatorname{mean}_{k=0}^{\tau-1}(y_{i,t-k} - y_{i,t-k-\tau})", sym, params, cits=[y]))


def test_investigation_reads_the_page_and_binds_the_cited_value(tmp_path):
    ev, _ = load("condmat")
    raw = _condmat_reading(ev, with_param=False)
    v = verify(raw, ev)
    assert "FREE_PARAMETER_UNBOUND" in codes(v["factors"][0])
    fixed = _condmat_reading(ev, with_param=True)["factors"][0]
    client = ScriptedClient({"paper_investigation": [
        {"action": "investigate", "requests": [{"tool": "page", "page": 3}, {"tool": "search", "query": "τ = 21 days"}]},
        {"action": "answer", "factor": fixed, "findings": [
            {"issue": "FREE_PARAMETER_UNBOUND", "symbol": "\\tau", "source": "free_parameter",
             "explanation": "the figures use tau = 21 days", "citations": [{"passage": "P0028", "quote": "for time interval, τ = 21"}]}]}]})
    out, hist = _investigate(raw, v, ev, client, ledger(tmp_path), "")
    g = out["factors"][0]
    assert not codes(g) and "{20}" in g["formula"]["latex"] and g["parameters"][0]["status"] == "PAPER"
    h = hist[0]
    assert h["rounds"] == 2 and h["conflicts_before"] == ["FREE_PARAMETER_UNBOUND"] and h["conflicts_after"] == []
    assert h["pages_consulted"] == [3] and {r["tool"] for r in h["requests"]} == {"page", "search"}
    assert h["findings"][0]["accepted"]
    # the page tool gave the reader the program's reconstruction of page 3 (the fixture has no PDF for a raw layer)
    page_text = client.calls[1]["messages"][1]["content"]
    assert "page 3 as reconstructed by the program" in page_text and "P0028" in page_text


def test_investigation_is_bounded_and_an_unchanged_reading_stays_blocked(tmp_path):
    ev, _ = load("condmat")
    raw = _condmat_reading(ev, with_param=False)
    v = verify(raw, ev)
    keep = {"action": "investigate", "requests": [{"tool": "search", "query": "momentum"}] * 6}
    client = ScriptedClient({"paper_investigation": [keep, keep, {"action": "answer", "factor": None, "findings": []}]})
    out, hist = _investigate(raw, v, ev, client, ledger(tmp_path), "")
    assert len(client.calls) == 3 and len(hist) == 1                     # 2 tool rounds + 1 forced answer, no second attempt
    assert len([r for r in hist[0]["requests"] if r["round"] == 0]) == 4   # at most 4 requests per round
    assert "FREE_PARAMETER_UNBOUND" in codes(out["factors"][0])            # nothing invented: still waits for the user
    assert "last turn" in client.calls[2]["messages"][1]["content"]


def test_source_claims_are_accepted_only_when_the_program_can_check_them():
    ev, _ = load("condmat")
    formula_block = next(p for p in ev.passages if p["kind"] == "formula" and len(p["text"]) >= 24)
    para = next(p for p in ev.passages if p["kind"] == "paragraph" and len(p["text"]) > 40 and "[FORMULA_UNRESOLVED]" not in p["text"]
                and p["page"] not in {r["page"] for r in ev.doc["extraction_report"].get("formula_regions_unresolved") or []})
    ok, _ = accept_claim({"source": "extraction_error", "citations": [{"passage": formula_block["id"], "quote": formula_block["text"][:20]}]},
                         ev, {}, {"passages": [], "pages": []})
    bad, why = accept_claim({"source": "extraction_error", "citations": [{"passage": para["id"], "quote": para["text"][:30]}]},
                            ev, {}, {"passages": [], "pages": []})
    assert ok and not bad and "没有提取异常" in why
    assert not accept_claim({"source": "paper_ambiguity", "citations": [{"passage": para["id"], "quote": "not in the passage at all"}]},
                            ev, {}, {"passages": [], "pages": []})[0]
    text, rec = run_request(ev, {"tool": "read", "passage": "P0028"})
    assert rec["passages"] == ["P0027", "P0028", "P0029"] and "τ = 21" in text


# ------------------------------------------------------------------ model access

def test_json_syntax_hint_names_the_mismatched_bracket(tmp_path):
    bad = '{"factors": [{"name": "a", "citations": [{"passage": "P1", "quote": "x"}]}], "rv": [{"s": 1}]}]}'
    try:
        json.loads(bad)
    except json.JSONDecodeError as e:
        hint = _syntax_hint(e)
    assert "<<HERE>>" in hint
    # a reply with a misplaced bracket gets one correction call naming the bracket, then succeeds
    # a structural fix that still fails the contract (no "b") goes back to the model with the bracket named
    good = {"a": 1, "b": 2}
    client = ScriptedClient({"p": ['{"a": [1}', good]})
    obj, _ = ask_json(client, ledger(tmp_path), purpose="p", system="s", user="u",
                      schema={"type": "object", "required": ["a", "b"]})
    assert obj == good and "does not match the innermost open bracket" in client.calls[1]["messages"][-1]["content"]


def test_session_budget_is_not_reported_as_a_model_error(tmp_path):
    from research_agent.security import BudgetExhausted

    class Spent:
        def raw(self, *a, **k):
            raise BudgetExhausted("model_tokens")
    with pytest.raises(BudgetExhausted):
        ask_json(Spent(), ledger(tmp_path), purpose="p", system="s", user="u", schema={"type": "object"})
    from research_agent.conversation import FAILURE_TEXT
    assert "Token 预算" in FAILURE_TEXT["model_tokens"]


def test_paper_calls_use_provider_json_mode():
    from research_agent.llm import Message, ModelRequest, ProviderConfig, Role
    from research_agent.providers.deepseek import DeepSeekAdapter
    from test_provider_contract import FixtureSecrets, FixtureTransport
    a = DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", credential_ref="env:QRA_TEST_KEY"), FixtureSecrets(), FixtureTransport([]))
    req = ModelRequest((Message(Role.USER, "reply in JSON"),), json_object=True)
    assert a._payload(req)["response_format"] == {"type": "json_object"}
    assert "response_format" not in a._payload(ModelRequest((Message(Role.USER, "hi"),)))


def test_a_model_reading_of_index_constituents_is_a_stock_study():
    from paper_agent.instruments import classify, scan
    ev, _ = load("macd")
    obj = {"status": "PAPER", "asset_classes": ["equity_stock", "equity_index"]}
    assert classify(scan(ev.doc), obj)["decision"] == "EQUITY_STOCK_COMPATIBLE"
    ev, _ = load("ma")
    c = classify(scan(ev.doc), None)
    assert c["decision"] == "ASSET_CLASS_NOT_AVAILABLE" and c["index_only_evidence"]


def test_the_audit_record_and_its_report_section(tmp_path):
    from research_agent.paper_tools import reconciliation_record
    from research_agent.report_explain import reconciliation_html
    ev, _ = load("condmat")
    raw = _condmat_reading(ev, with_param=False)
    v = verify(raw, ev)
    fixed = _condmat_reading(ev, with_param=True)["factors"][0]
    client = ScriptedClient({"paper_investigation": [
        {"action": "investigate", "requests": [{"tool": "page", "page": 3}]},
        {"action": "answer", "factor": fixed, "findings": [{"issue": "FREE_PARAMETER_UNBOUND", "symbol": "\tau", "source": "free_parameter",
                                                            "explanation": "tau = 21", "citations": [{"passage": "P0028", "quote": "for time interval, τ = 21"}]}]}]})
    out, hist = _investigate(raw, v, ev, client, ledger(tmp_path), "")
    out["investigations"] = hist
    out["reading"] = {"initial": [{"name": fixed["name"], "formula_latex": raw["factors"][0]["formula_latex"], "formula_status": "restated_from_prose"}]}
    rec = reconciliation_record(out, out["factors"][0], fixed["name"], "mean(...)")
    assert rec["program_parse"]["status"] == "PARSED" and rec["parameters"][0]["status"] == "PAPER"
    assert rec["investigations"][0]["pages_consulted"] == [3] and rec["investigations"][0]["findings"][0]["accepted"]
    json.dumps(rec, ensure_ascii=False)
    html, md = reconciliation_html(rec, lambda key, title, head, rows, kinds: (f"<table id={key}>{len(rows)}</table>", f"{title}:{len(rows)}"))
    for text in ("AI 解读与程序核对", "读整页", "程序采纳", "纯文本模型"):
        assert text in html, text


def test_a_count_inside_a_derived_symbol_is_bound_from_the_users_value(tmp_path):
    """Live A/B D03u: RSI = 100 - 100/(1+RS) with RS = mean_{k=0}^{X-1}(...)/...; the user's X=14 must reach RS."""
    ev, _ = load("ti1110")
    d = cite(ev, "P0095", "Where RS is the average of X days price rises / X days price drops")
    rs = r"\frac{\operatorname{mean}_{k=0}^{X-1}(\max(P_{i,t-k} - P_{i,t-k-1}, 0))}{\operatorname{mean}_{k=0}^{X-1}(\max(P_{i,t-k-1} - P_{i,t-k}, 0))}"
    sym = [{"symbol": "P", "meaning": "share price", "kind": "raw_field", "data_field": "close", "citations": [d]},
           {"symbol": "RS", "meaning": "relative strength", "kind": "derived", "data_field": "other", "derivation_latex": rs, "citations": [d]}]
    f = factor(ev, "Relative Strength Index (RSI)", r"RSI_{i,t} = 100 - \frac{100}{1 + RS_{i,t}}", sym,
               [{"symbol": "X", "meaning": "RSI window in days", "value": None, "paper_values": [], "status": "unstated", "citations": [d]}], cits=[d])
    f["frequency"] = label("daily", [d])                                # "X days": daily data
    v = verify(reading(f), ev)
    g = v["factors"][0]
    assert "FREE_PARAMETER_UNBOUND" in codes(g)
    u = reverify(dict(v, reading={"initial": [], "final": reading(f)}), ev, {"X": 14})
    g2 = u["factors"][0]
    rs2 = next(s for s in g2["symbols"] if s["symbol"] == "RS")
    assert "^{13}" in rs2["derivation_latex"] and "X-1" in rs2["derivation_as_written"]
    assert g2["parameters"][0]["status"] == "USER" and not codes(g2)
    p, _, _ = plan(ev, u, PROFILE, factor=g2["name"])
    # the derivation parses, and the frequency comes from the reader's quote "X days" that the program verified (live J1)
    assert p["status"] == "AWAITING_USER_DECISION", p.get("hard_stops")
    assert any(s["kind"] == "parameter_choice" for s in p["substitutions"])


# ------------------------------------------------------------------ first real A/B run (2026-10-14 21:30)

def test_a_missing_closing_bracket_is_repaired_without_changing_any_text(tmp_path):
    """A/B D04: DeepSeek wrote '"}]}]' for '"}]}}]' and repeated it verbatim when asked to correct it."""
    good = {"factors": [{"name": "CMI", "portfolio_rules": {"value": "x", "citations": [{"passage": "P1", "quote": "a } ] text"}]}}],
            "results_vs_methods": [{"statement": "s"}]}
    text = json.dumps(good, ensure_ascii=False)
    broken = text.replace('"}]}}], "results_vs_methods"', '"}]}], "results_vs_methods"')
    assert broken != text
    client = ScriptedClient({"p": [broken]})
    led = ledger(tmp_path)
    obj, _ = ask_json(client, led, purpose="p", system="s", user="u", schema={"type": "object"})
    assert obj == good and len(client.calls) == 1
    assert any(e["kind"] == "JSON_BRACKETS_REPAIRED" for e in led.events())


def test_a_truncated_reply_is_asked_once_for_a_shorter_one(tmp_path):
    from research_agent.llm import ModelError

    class Long:
        calls = 0

        def raw(self, messages, **k):
            Long.calls += 1
            if Long.calls == 1:
                raise ModelError("OUTPUT_TRUNCATED")
            assert "cut off" in messages[-1]["content"]
            return {"content": '{"a": 1}', "usage": {"total_tokens": 10}, "model": "m"}
    obj, _ = ask_json(Long(), ledger(tmp_path), purpose="p", system="s", user="u", schema={"type": "object"})
    assert obj == {"a": 1} and Long.calls == 2


def test_a_calendar_count_declared_as_a_parameter_is_not_asked_from_the_user():
    """A/B D10: Amihud's D_{i,y} ('days with data in year y') was declared unstated and blocked the study."""
    ev, _ = load("amihud")
    f = factor(ev, "ILLIQ", r"ILLIQ_{i,t} = \operatorname{mean}_{k=0}^{D-1}(close_{i,t-k})", [],
               [{"symbol": "D", "meaning": "number of days for which data are available for stock i in year y", "value": None,
                 "paper_values": [], "status": "unstated", "citations": []}])
    g = verify(reading(f), ev)["factors"][0]
    # C6R4 (records/TEST_CHANGES_CN.md): no longer FORMULA_UNPARSEABLE -> repair to a nominal length; a calendar window
    # the trusted IR cannot express is blocked with its own reason
    assert "FREE_PARAMETER_UNBOUND" not in codes(g) and "FORMULA_UNPARSEABLE" not in codes(g)
    assert "CALENDAR_WINDOW_UNSUPPORTED" in codes(g)


def test_an_asset_class_only_the_reader_claims_is_shown_not_silently_applied():
    """A/B D10: the reader's research object said index/bonds for Amihud; the document is overwhelmingly about stocks."""
    from paper_agent.instruments import classify, scan
    ev, _ = load("amihud")
    c = classify(scan(ev.doc), {"status": "PAPER", "asset_classes": ["equity_index", "bonds_rates"], "citations": [{"quote": "excess return on the market"}]})
    assert c["decision"] == "EQUITY_STOCK_COMPATIBLE" and set(c["model_unconfirmed"]) == {"equity_index", "bonds_rates"}
    ev, _ = load("aqr")                                  # a genuine futures paper stays blocked
    assert classify(scan(ev.doc), {"status": "PAPER", "asset_classes": ["futures"]})["decision"] == "ASSET_CLASS_NOT_AVAILABLE"


def test_numbered_factors_are_never_substituted_and_acronyms_name_factors():
    from paper_agent.planner import PlanError
    from research_agent.paper_tools import named_factor
    ev, _ = load("gh")
    u = {"factors": [{"name": "Alpha#1", "role": "primary", "status": "VERIFIED", "conflicts": []}]}
    with pytest.raises(PlanError) as e:
        plan(ev, u, PROFILE, factor="Alpha#12")
    assert e.value.code == "FACTOR_NOT_UNDERSTOOD"
    names = ["Classical momentum indicator (CMI)", "Generalized momentum indicator (GMI)"]
    assert named_factor(names, "研究0212641那篇论文里的广义动量指标GMI") == names[1]


def test_a_price_ratio_is_a_lookback_return_not_a_lagged_return():
    """A/B D01: P_t / P_{t-12} - 1 with P = price was flagged LOOKBACK_READ_AS_LAG because P's quotes mention returns."""
    ev, _ = load("aqr")
    q = cite(ev, "P0058", "time series momentum strategies")
    sym = [{"symbol": "P", "meaning": "price of market i", "kind": "raw_field", "data_field": "close", "citations": [q]}]
    f = factor(ev, "TSMOM", r"TSMOM_{i,t} = \operatorname{sign}(\frac{P_{i,t}}{P_{i,t-12}} - 1)", sym, cits=[q])
    assert "LOOKBACK_READ_AS_LAG" not in codes(verify(reading(f), ev)["factors"][0])


def test_a_chinese_sentence_locates_its_paper():
    from research_agent.paper_library import PaperLibrary
    rows = [{"name": n, "title": t, "heading": h, "uploaded_at": str(i), "sha256": str(i) * 64}
            for i, (n, t, h) in enumerate([("华泰量化月报 2020-09.pdf", "研究报告", "金工研究/量化投资月报"),
                                           ("greatwall_technical_overlap_20160824.pdf", "http://www.cgws.com", "量化择时之技术分析指标叠加择时初探 移动平均"),
                                           ("ferreira_silva_yen_2019_ma_rule.pdf", "Moving average rule", "moving average of past returns"),
                                           ("xiangcai_etf_trend_20220929.pdf", "湘财证券-基金研究：趋势跟踪在行业ETF择时中的应用", "")])]
    lib = PaperLibrary.__new__(PaperLibrary)
    lib._complete_metadata = lambda: rows
    for q, want in (("研究华泰那份量化月报里的因子", "华泰"), ("研究长城证券技术指标叠加那篇论文的因子", "greatwall"),
                    ("研究moving average（移动平均）那篇论文的因子", "ferreira"), ("研究湘财ETF趋势跟踪那篇论文的因子", "xiangcai")):
        r = lib.resolve(q)
        assert r["status"] == "FOUND" and r["paper"]["name"].startswith(want), (q, r["status"])


@pytest.mark.parametrize("broken", [
    '{"factors": [{"name": "a", "r": {"v": "x", "c": [{"q": "y"}]}], "next": 1}',      # missing } before ]
    '{"factors": [{"name": "a", "r": {"v": "x", "c": [{"q": "y"}]}}]}, "next": 1}',    # one } too many: root closed early
])
def test_bracket_repair_handles_both_live_shapes(broken):
    from paper_agent.model import _bracket_repair
    obj, fixes = _bracket_repair(broken)
    assert obj == {"factors": [{"name": "a", "r": {"v": "x", "c": [{"q": "y"}]}}], "next": 1} and fixes


def test_bracket_repair_never_touches_strings_or_invents_values():
    from paper_agent.model import _bracket_repair
    assert _bracket_repair('{"a": "x", "b": }') is None                     # a missing value is not a bracket defect
    obj, _ = _bracket_repair('{"a": "keep } ] , as is", "b": [1, 2}')
    assert obj == {"a": "keep } ] , as is", "b": [1, 2]}


# ------------------------------------------------------------------ unreadable printed formulas: independent second reading

def _cmi_with_second(ev, second):
    raw = _condmat_reading(ev, with_param=True)
    raw["_second_readings"] = {} if second is None else {raw["factors"][0]["name"]: second}
    return raw


def test_an_agreeing_second_reading_is_recorded_and_does_not_block():
    ev, _ = load("condmat")
    raw = _condmat_reading(ev, with_param=True)
    f0 = raw["factors"][0]
    same = {"formula_latex": r"CMI_{i,t} = \frac{1}{\tau} \sum_{k=0}^{\tau-1}(y_{i,t-k} - y_{i,t-k-\tau})",   # written differently
            "parameters": f0["parameters"], "symbols": f0["symbols"]}
    g = verify(_cmi_with_second(ev, same), ev)["factors"][0]
    assert g["formula"]["unreadable_pages"] and g["formula"]["independent_reading"]["comparison"]["agree"]
    assert not codes(g)


def test_a_disagreeing_second_reading_blocks_with_both_formulas():
    """The live GMI misreading (price change / mean volume) against the paper's moving average of momentum."""
    ev, _ = load("condmat")
    f0 = _condmat_reading(ev, with_param=True)["factors"][0]
    other = {"formula_latex": r"GMI_{i,t} = \frac{y_{i,t} - y_{i,t-21}}{\operatorname{mean}_{k=0}^{20}(V_{i,t-k})}", "parameters": [],
             "symbols": f0["symbols"] + [{"symbol": "V", "kind": "raw_field", "data_field": "volume"}]}
    g = verify(_cmi_with_second(ev, other), ev)["factors"][0]
    c = next(c for c in g["conflicts"] if c["code"] == "FORMULA_READINGS_DISAGREE")
    assert c["blocking"] and "①" in c["detail"] and "②" in c["detail"]


def test_a_missing_second_reading_blocks_in_the_new_reader_only():
    ev, _ = load("condmat")
    g = verify(_cmi_with_second(ev, None), ev)["factors"][0]
    assert "FORMULA_RECONSTRUCTION_UNVERIFIED" in codes(g)
    assert "FORMULA_RECONSTRUCTION_UNVERIFIED" not in codes(verify(_condmat_reading(ev, with_param=True), ev)["factors"][0])


def test_a_long_chinese_context_stays_under_the_request_limit(tmp_path):
    """Live J3: the Huatai report's 24000 characters were ~72 KB and failed before any model call."""
    from paper_agent.understanding import CONTEXT_BYTES, understand
    ev, replies = load("huatai")
    from paper_agent.evidence import PaperEvidence, _tokens
    ev = PaperEvidence(ev.doc, ev.spec, [dict(p, tokens=_tokens(p["text"])) for p in ev.passages])
    client = ScriptedClient({"paper_understanding": replies["paper_understanding"], "formula_repair": replies["formula_repair"],
                             "paper_investigation": [{"action": "answer", "factor": None, "findings": []}] * 4,
                             "independent_reading": [{"formula_latex": ""}] * 2})
    try:
        understand(ev, client, ledger(tmp_path))
    except Exception:  # noqa: BLE001 -- only the request size matters here
        pass
    first = client.calls[0]["messages"][1]["content"]
    assert len(first.encode("utf-8")) <= CONTEXT_BYTES + 2000


def test_sign_of_two_equal_averages_is_zero_in_both_evaluators():
    """Live J4 (hans): a suspended stock's MA20 and MA30 are equal; the reference gave 8.9e-16 -> sign 1, the executor 0."""
    import numpy as np
    import pandas as pd
    from paper_agent import trusted_ir
    from paper_research.factor_ir import evaluate, parse_formula
    rng = np.random.default_rng(3)
    close = pd.DataFrame(10 * np.exp(np.cumsum(rng.normal(0, 0.02, (200, 4)), axis=0)), columns=list("ABCD"))
    close.iloc[60:100, 1] = 7.13
    close.iloc[80:130, 0] = close.iloc[79, 0]
    close.iloc[150, 2] = np.nan
    ir = parse_formula(r"F_{i,t} = \operatorname{sign}(\operatorname{mean}_{k=0}^{19}(close_{i,t-k}) - "
                       r"\operatorname{mean}_{k=0}^{29}(close_{i,t-k}))")["ir"]
    ref = evaluate(ir, {"close": close}, {"close": "close"})
    ex = trusted_ir.evaluate(ir, {"close": close}, {"close": "close"})
    assert ref.isna().equals(ex.isna()) and (ref.fillna(9) == ex.fillna(9)).all().all()
    assert (ref.iloc[89:100, 1] == 0).all() and ref.iloc[150:180, 2].isna().all()


def test_a_paper_study_cannot_complete_on_a_listing_or_an_earlier_turn():
    """Live J1/J6: the planner claimed 'already blocked' from an earlier turn about another paper and completed after paper_list."""
    from research_agent.acceptance import EvidenceRequired, _quant_research
    listing = [{"tool": "paper_list", "result": {"data": {"mode": "catalog", "analysis_scope": "paper_library"}}}]
    plan = {"summary": "s"}
    with pytest.raises(EvidenceRequired) as e:
        _quant_research(plan, listing, skill_id="paper_research", goal="研究101 Formulaic Alphas那篇论文里的Alpha#101")
    assert str(e.value) == "PAPER_STUDY_NOT_CALLED"
    assert _quant_research(plan, listing, skill_id="paper_research", goal="列出我上传的论文。")["mode"] == "catalog"
