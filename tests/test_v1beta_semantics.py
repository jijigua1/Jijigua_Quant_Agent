"""Paper semantics vs research definition, research object, symbol table (2026-10-14 hardening).

Fixtures are the REAL staging evidence (document blocks, passages) and the REAL DeepSeek replies recorded for the dev
papers (tests/fixtures_v1beta/papers/*.json.gz). The understanding runs through the actual understand() code with a
scripted client that replays those replies; only the semantic-repair replies are written here, from the original reply,
to exercise both a model that insists on its reading and a corrected reading.
"""
import copy
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from paper_agent.evidence import PaperEvidence
from paper_agent.instruments import classify, scan
from paper_agent.ledger import TaskLedger
from paper_agent.model import ScriptedClient
from paper_agent.planner import ASSET_PHRASE, decision_text, plan
from paper_agent.semantics import cues
from paper_agent.trusted_ir import evaluate as trusted
from paper_agent.understanding import understand

FIX = Path(__file__).parent / "fixtures_v1beta" / "papers"
PROFILE = {"fields": ["open", "high", "low", "close", "volume", "amount"], "train_rows_estimate": 960,
           "status": "PROFILED_EXPLORATORY_ONLY", "adjustment": "none (raw unadjusted market prices)",
           "units": {"volume": "lots (100 shares)", "amount": "thousand CNY"},
           "splits": {"train": ["2020-01-02", "2023-12-29"], "valid": ["2024-01-02", "2025-12-31"], "test": ["2026-01-01", "2026-12-31"]},
           "holdout": "2026 evaluated only by the controlled rolling evaluator (aggregates)",
           "certification": {"source": "gpushare", "level": "PROFILED_EXPLORATORY_ONLY", "fields": [],
                             "certified": {"adjusted_prices": False, "listing_status": False, "trading_status": False}}}


def load(name):
    if not Path(FIX / f"{name}.json.gz").is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(FIX / f"{name}.json.gz", "rt", encoding="utf-8"))
    ev = PaperEvidence(d["doc"], d["spec"], d["passages"])
    last = max(i for i, r in enumerate(d["replies"]) if r["purpose"] == "paper_understanding")
    replies = {"paper_understanding": [d["replies"][last]["raw_output"]],
               "formula_repair": [r["raw_output"] for r in d["replies"][last + 1:] if r["purpose"] == "formula_repair"]}
    return ev, replies


def read(name, tmp_path, semantic=(), focus="", independent=None):
    ev, replies = load(name)
    if independent is None:                     # an independent second reading that agrees with the reader's own formula
        f = (semantic[-1]["factor"] if semantic else insisting(name)["factor"])
        independent = [{"formula_latex": f.get("formula_latex"), "parameters": f.get("parameters") or [],
                        "symbols": f.get("symbols") or []}] * 3
    client = ScriptedClient(dict(replies, paper_investigation=[dict(x, action="answer") for x in semantic],
                                 independent_reading=list(independent)))
    ledger = TaskLedger(tmp_path, goal=name, budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                        design_revisions=2, orchestration_turns=0))
    return ev, understand(ev, client, ledger, focus=focus), client


def insisting(name):
    """The model repeats its own reading (after its parse repairs) when asked to re-read."""
    ev, replies = load(name)
    f = json.loads(replies["paper_understanding"][0])["factors"][0]
    from paper_research.factor_ir import parse_formula
    for r in replies["formula_repair"]:
        latex = json.loads(r)["formula_latex"]
        try:
            parse_formula(latex)
            f = dict(f, formula_latex=latex)
        except Exception:  # noqa: BLE001 - only parseable repairs are what the model "insists" on
            pass
    return {"factor": f}


def codes(factor):
    return {c["code"] for c in factor["conflicts"] if c["blocking"]}


# ------------------------------------------------------------------ cues (English and Chinese)

@pytest.mark.parametrize("text,kind,numbers", [
    ("an equal weighted combination of 1month, 3-month and 12-month time series momentum strategies", "lookback", [1]),
    ("the return over the past 12 months, skipping the most recent month", "lookback", [12]),
    ("past 1-, 3- and 12-month returns", "lookback", [1, 3, 12]),
    ("we use the return in month t-12 as the signal", "single_lag", [12]),
    ("skipping the most recent month", "skip", []),
    ("weekly log-returns of the index", "log", []),
    ("the 12-day exponential moving average of the closing price", "exponential", []),
    ("过去20日涨跌幅", "lookback", [20]),
    ("过去1、3、12个月的累计收益", "lookback", [1, 3, 12]),
    ("剔除最近1个月", "skip", [1]),
    ("指数移动平均", "exponential", []),
])
def test_temporal_cues(text, kind, numbers):
    found = [c for c in cues(text) if c["kind"] == kind]
    assert found, (text, cues(text))
    assert set(numbers) <= {n for c in found for n in c["numbers"]}


# ------------------------------------------------------------------ AQR: look-back read as lag, futures

def corrected_aqr(raw_reply):
    f = copy.deepcopy(json.loads(raw_reply)["factors"][0])
    cite = [{"passage": "P0058", "quote": "1month, 3-month and 12-month time series momentum strategies"}]
    f["formula_latex"] = (r"TSMOM_{i,t} = \frac{1}{3} \left( \operatorname{sign}(R1_{i,t}) + \operatorname{sign}(R3_{i,t})"
                          r" + \operatorname{sign}(R12_{i,t}) \right)")
    f["symbols"] = [{"symbol": f"R{n}", "meaning": f"cumulative return over the past {n} month(s)", "kind": "cumulative_return",
                     "data_field": "close", "aggregate": None, "window": {"n": n, "unit": "month"}, "skip": None,
                     "compounding": "simple", "price_basis": "unstated", "adjustment": "unstated", "units": None, "citations": cite}
                    for n in (1, 3, 12)]
    return {"factor": f}


def test_aqr_real_reading_blocks_and_an_insisting_model_stays_blocked(tmp_path):
    same = insisting("aqr")
    ev, u, client = read("aqr", tmp_path, semantic=[same, same])
    f = u["factors"][0]
    assert "LOOKBACK_READ_AS_LAG" in codes(f) and f["status"] == "BLOCKED"
    assert [x["purpose"] for x in client.calls].count("paper_investigation") == 1          # no progress: one attempt, then stop
    assert [r["conflicts_after"] for r in u["semantic_repairs"]] == [["LOOKBACK_READ_AS_LAG"]]
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "BLOCKED" and "LOOKBACK_READ_AS_LAG" in {h["code"] for h in p["hard_stops"]}
    assert p["assets"]["decision"] == "ASSET_CLASS_NOT_AVAILABLE" and "futures" in p["assets"]["studied"]


def test_aqr_corrected_reading_computes_lookback_returns_and_needs_the_asset_phrase(tmp_path):
    ev, replies = load("aqr")
    ev, u, client = read("aqr", tmp_path, semantic=[corrected_aqr(replies["paper_understanding"][0])])
    f = u["factors"][0]
    assert not codes(f), f["conflicts"]
    assert u["semantic_repairs"][0]["conflicts_before"] == ["LOOKBACK_READ_AS_LAG"] and u["semantic_repairs"][0]["conflicts_after"] == []
    p, task, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "AWAITING_USER_DECISION" and p["asset_consent_required"] and p["route"] == "trusted_ir"
    assert ASSET_PHRASE in decision_text(p) and "期货" in decision_text(p)
    assert any(s["kind"] == "asset_substitution" for s in p["substitutions"])
    timeline = " | ".join(p["timeline"])
    for days in (21, 63, 252):
        assert f"回看 {days} 个交易日" in timeline                                  # cumulative windows, not lags
    # numeric check on a constructed price path: the executed IR equals the independent look-back definition
    idx = pd.bdate_range("2021-01-04", periods=300)
    close = pd.DataFrame({"a": 100 * np.exp(0.0007 * np.arange(300) + 0.03 * np.sin(np.arange(300) / 9.0)),
                          "b": 100 * np.exp(-0.0005 * np.arange(300))}, index=idx)
    ir = p["ir_execution_json"]
    syms = {k: v["field"] for k, v in p["symbol_map"].items() if v.get("field")}
    got = trusted(ir, {"close": close}, syms)
    t = 299
    expect = {c: np.mean([np.sign(close[c].iloc[t] / close[c].iloc[t - n] - 1) for n in (21, 63, 252)]) for c in close}
    for c in close:
        assert got[c].iloc[t] == pytest.approx(expect[c])


# ------------------------------------------------------------------ MA: log returns of an index; cond-mat: undefined m

def test_ma_log_return_and_index_research_object(tmp_path):
    same = insisting("ma")
    ev, u, _ = read("ma", tmp_path, semantic=[same, same])
    f = u["factors"][0]
    assert "LOG_RETURN_READ_AS_SIMPLE" in codes(f)
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "BLOCKED" and "equity_index" in p["assets"]["studied"]
    assert p["assets"]["decision"] == "ASSET_CLASS_NOT_AVAILABLE"           # "stock indices exclusively": consent needed
    assert any(s["kind"] == "parameter_choice" for s in p["substitutions"])  # N = 52 is the reader's declared choice, shown to the user


def test_condmat_undefined_symbol_names_the_garbled_formula_block(tmp_path):
    same = insisting("condmat")
    ev, u, _ = read("condmat", tmp_path, semantic=[same, same])
    f = u["factors"][0]
    undefined = [c for c in f["conflicts"] if c["code"] == "SYMBOL_UNDEFINED"]
    assert undefined and undefined[0]["symbol"] == "m"
    assert "P0045" in undefined[0]["detail"] and "视觉解析" in undefined[0]["detail"]
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "BLOCKED" and not p["symbol_map"]                                # m was never mapped to a field


# ------------------------------------------------------------------ papers that must keep working / blocking

def test_macd_real_reply_is_an_ema_on_the_trusted_executor(tmp_path):
    ev, u, client = read("macd", tmp_path)
    f = u["factors"][0]
    assert f["status"] != "BLOCKED" and "paper_investigation" not in [x["purpose"] for x in client.calls]
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["route"] == "trusted_ir" and p["status"] == "AWAITING_USER_DECISION"
    emas = [n for n in __import__("paper_research.factor_ir", fromlist=["walk"]).walk(p["ir_execution_json"]) if n["op"] == "ema"]
    assert sorted(n["n"] for n in emas) == [12, 26] and all(n["seed_weight"] <= 1e-3 for n in emas)
    assert [s["kind"] for s in p["substitutions"]].count("recursion_truncation") == 2


@pytest.mark.parametrize("name", ["gh"])
def test_equity_papers_are_not_newly_blocked(name, tmp_path):
    ev, u, client = read(name, tmp_path)
    f = u["factors"][0]
    assert not codes(f), f["conflicts"]
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "AWAITING_USER_DECISION" and not p["asset_consent_required"] and p["route"] == "trusted_ir"


def test_amihud_nominal_250_day_window_is_blocked_not_substituted(tmp_path):
    # C6R4 (records/TEST_CHANGES_CN.md): the recorded reading replaces D_iy ("days with data in year y") by a fixed 250-day
    # mean; that is a different definition, so the paper is blocked with the calendar-window reason instead of running.
    ev, u, client = read("amihud", tmp_path)
    f = u["factors"][0]
    assert "CALENDAR_WINDOW_UNSUPPORTED" in codes(f), f["conflicts"]
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "BLOCKED" and p["hard_stops"][0]["code"] == "CALENDAR_WINDOW_UNSUPPORTED"
    assert p["hard_stops"][0]["source"] == "unsupported_notation"


def test_heston_options_paper_is_blocked(tmp_path):
    same = insisting("heston")
    ev, u, _ = read("heston", tmp_path, semantic=[same, same])
    p, _, _ = plan(ev, u, PROFILE, factor=u["factors"][0]["name"])
    assert p["status"] == "BLOCKED" and p["assets"]["studied"] == ["options"]


@pytest.mark.parametrize("name,expected", [("aqr", "ASSET_CLASS_NOT_AVAILABLE"), ("heston", "ASSET_CLASS_NOT_AVAILABLE"),
                                           ("gh", "EQUITY_STOCK_COMPATIBLE"), ("amihud", "EQUITY_STOCK_COMPATIBLE"),
                                           ("ti1110", "SYNTHETIC_DATA_PAPER")])
def test_research_object_from_the_whole_document(name, expected):
    ev, _ = load(name)
    assert classify(scan(ev.doc))["decision"] == expected


def _single_item(latex, meaning, verbal):
    q = {"passage": "P0001", "quote": verbal, "page": 1}
    return {"formula": {"latex": latex, "citations": []}, "verbal_definition": {"value": verbal, "citations": [q]},
            "symbols": [{"symbol": "r", "meaning": meaning, "kind": "period_return", "data_field": "returns", "citations": [q],
                         "status": "PAPER"}]}


def test_a_common_formation_lag_is_a_dating_convention_not_a_lookback_error():
    from paper_agent.semantics import check_factor
    ok = check_factor(_single_item("REV_{i,t} = -r_{i,t-1}", "the one-month return", "the past one-month return of stock i"))
    assert not [c for c in ok if c["blocking"]]
    bad = check_factor(_single_item("TS_{i,t} = sign(r_{i,t-1}) + sign(r_{i,t-12})", "past return", "the past 1-month and 12-month returns"))
    assert "LOOKBACK_READ_AS_LAG" in {c["code"] for c in bad}
