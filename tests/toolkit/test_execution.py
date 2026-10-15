"""Daily signal + minute execution. Expected fills are hand-computed. Synthetic data only."""
from datetime import time

import numpy as np
import pandas as pd
import pytest

from qrtk import (FIRST_VALID_MINUTE, NEXT_OPEN, VWAP_5, VWAP_15, VWAP_30, ExecutionRule,
                  aggregate_daily, build_execution_prices, normalize_minute_bars, reconcile,
                  run_backtest, run_backtest_with_execution, to_panel, window_vwap_rule)
from synth import CONTRACT, DAYS, SESSION, day_bars, hm, window_case

D0, D1, D2 = DAYS


def build(raw, codes):
    bars, _ = normalize_minute_bars(raw, CONTRACT, SESSION, DAYS)
    daily = aggregate_daily(bars, CONTRACT, SESSION, DAYS, codes)
    return bars, to_panel(daily, "open", DAYS, codes), to_panel(daily, "close", DAYS, codes)


def prices(rule, bars, open_px, codes, **kw):
    return build_execution_prices(rule, DAYS, codes, session=SESSION, daily_open=open_px,
                                  bars=bars, contract=CONTRACT, **kw)


@pytest.fixture
def case_a():
    raw = pd.concat([window_case(d) for d in DAYS])
    return build(raw, ["A"])


BUY_A = pd.DataFrame([{"signal_date": D0, "code": "A", "side": "buy", "shares": 1000}])


def test_rule_prices_and_known_times(case_a):
    bars, op, cl = case_a
    nxt = prices(NEXT_OPEN, bars, op, ["A"])
    assert nxt.price.at[D1, "A"] == 10.0 and nxt.known_at.at[D1, "A"] == D1 + hm("09:25")
    v5 = prices(VWAP_5, bars, op, ["A"])
    assert v5.price.at[D1, "A"] == pytest.approx(8125 / 800)
    assert v5.known_at.at[D1, "A"] == D1 + hm("09:35")          # only after the window closes
    assert v5.exec_start == time(9, 30)
    assert any("known only after 09:35" in a for a in v5.assumptions)
    fm = prices(FIRST_VALID_MINUTE, bars, op, ["A"])
    assert fm.price.at[D1, "A"] == 10.0 and fm.known_at.at[D1, "A"] == D1 + hm("09:31")
    v15, v30 = prices(VWAP_15, bars, op, ["A"]), prices(VWAP_30, bars, op, ["A"])
    # 09:30-09:45: the five hand bars (8125 / 800) plus 10 flat bars at 10.2 x 100
    assert v15.price.at[D1, "A"] == pytest.approx((8125 + 10 * 1020) / 1800)
    assert v30.price.at[D1, "A"] == pytest.approx((8125 + 25 * 1020) / 3300)


def test_first_valid_minute_differs_from_auction_open():
    ov = {"09:30": {"volume": 0, "amount": 0}, "09:31": {"open": 10.3, "high": 10.3, "low": 10.3, "close": 10.3, "amount": 1030}}
    raw = pd.concat([day_bars(d, "B", overrides=ov) for d in DAYS])
    bars, op, cl = build(raw, ["B"])
    fm = prices(FIRST_VALID_MINUTE, bars, op, ["B"])
    assert op.at[D1, "B"] == 10.0                       # official open = 09:25 auction
    assert fm.price.at[D1, "B"] == 10.3 and fm.known_at.at[D1, "B"] == D1 + hm("09:32")


def test_t1_open_vs_t1_window_vwap_in_ledger(case_a):
    bars, op, cl = case_a
    r_open = run_backtest_with_execution(BUY_A, prices(NEXT_OPEN, bars, op, ["A"]), cl, initial_cash=100_000)
    r_vwap = run_backtest_with_execution(BUY_A, prices(VWAP_5, bars, op, ["A"]), cl, initial_cash=100_000)
    # open: 1000 x 10 + 5 fee ; VWAP_5: 1000 x 10.15625 + max(3.05, 5) fee
    assert r_open.daily.loc[D1, "cash"] == pytest.approx(89_995)
    assert r_vwap.daily.loc[D1, "cash"] == pytest.approx(89_838.75)
    assert r_open.daily.loc[D1, "cash"] - r_vwap.daily.loc[D1, "cash"] == pytest.approx(156.25)
    # valuation uses the close (10.5 closing auction), not the fill price
    assert r_vwap.daily.loc[D1, "market_value"] == pytest.approx(10_500)
    assert r_vwap.trades["date"].tolist() == [D1]           # never on the signal day


def test_signal_day_data_cannot_move_the_fill(case_a):
    bars, op, cl = case_a
    raw = pd.concat([window_case(d) for d in DAYS])
    on_d0 = pd.to_datetime(raw["timestamp"]).dt.normalize() == D0
    raw.loc[on_d0, ["open", "high", "low", "close"]] *= 2
    raw.loc[on_d0, "amount"] *= 2
    bars2, op2, cl2 = build(raw, ["A"])
    a = run_backtest_with_execution(BUY_A, prices(VWAP_5, bars, op, ["A"]), cl, initial_cash=100_000)
    b = run_backtest_with_execution(BUY_A, prices(VWAP_5, bars2, op2, ["A"]), cl2, initial_cash=100_000)
    pd.testing.assert_frame_equal(a.trades, b.trades)


def test_signal_after_window_start_is_rejected(case_a):
    bars, op, cl = case_a
    late = BUY_A.assign(signal_time=D1 + hm("09:40"))     # decided with intraday info of T+1
    r = run_backtest_with_execution(late, prices(VWAP_5, bars, op, ["A"]), cl, initial_cash=100_000)
    assert r.rejections[["reason", "category"]].values.tolist() == [["signal_after_exec_start", "timing"]]
    ok = BUY_A.assign(signal_time=D0 + hm("15:30"))
    assert run_backtest_with_execution(ok, prices(VWAP_5, bars, op, ["A"]), cl, initial_cash=100_000).rejections.empty


def test_capacity_limit(case_a):
    bars, op, cl = case_a
    rule = window_vwap_rule(time(9, 30), time(9, 35), max_participation=0.1)
    ep = prices(rule, bars, op, ["A"])
    assert ep.capacity.at[D1, "A"] == 80                   # floor(0.1 x 800)
    o = pd.DataFrame([{"signal_date": D0, "code": "A", "side": "buy", "shares": 100}])
    r = run_backtest_with_execution(o, ep, cl, initial_cash=100_000)
    assert r.rejections[["reason", "category"]].values.tolist() == [["capacity_exceeded", "not_executable"]]


def test_unavailable_versus_not_executable():
    raw = pd.concat([window_case(D0, c) for c in "ABE"] + [window_case(D1, "A"),
                    window_case(D1, "E").loc[lambda df: df["timestamp"] != D1 + hm("09:33")]] +
                    [window_case(D2, c) for c in "ABE"])
    codes = ["A", "B", "C", "E"]
    bars, op, cl = build(raw, codes)
    ep = prices(VWAP_5, bars, op, codes, suspended={(D1, "B")})
    assert ep.status.loc[D1].to_dict() == {"A": "ok", "B": "suspended", "C": "missing_data", "E": "incomplete_window"}
    o = pd.DataFrame([{"signal_date": D0, "code": c, "side": "buy", "shares": 100} for c in codes])
    r = run_backtest_with_execution(o, ep, cl, initial_cash=100_000)
    got = dict(zip(r.rejections["code"], zip(r.rejections["reason"], r.rejections["category"])))
    assert got == {"B": ("suspended", "not_executable"), "C": ("missing_data", "data_unavailable"),
                   "E": ("incomplete_window", "data_unavailable")}


def test_adjusted_execution_prices_refused(case_a):
    bars, op, cl = case_a
    ep = build_execution_prices(NEXT_OPEN, DAYS, ["A"], daily_open=op, daily_adjustment="forward")
    with pytest.raises(ValueError):
        run_backtest_with_execution(BUY_A, ep, cl, initial_cash=100_000)


def test_window_rules_validated():
    with pytest.raises(ValueError):
        ExecutionRule("x", "window_vwap")
    with pytest.raises(ValueError):
        ExecutionRule("x", "daily_open", window=(time(9, 30), time(9, 35)))
    with pytest.raises(ValueError):
        window_vwap_rule(time(9, 30), time(9, 35), max_participation=1.5)


def test_next_open_rule_matches_v01_ledger(case_a):
    bars, op, cl = case_a
    o = pd.concat([BUY_A, pd.DataFrame([{"signal_date": D1, "code": "A", "side": "sell", "shares": np.nan}])])
    a = run_backtest(o, op, cl, initial_cash=100_000)
    b = run_backtest_with_execution(o, prices(NEXT_OPEN, bars, op, ["A"]), cl, initial_cash=100_000)
    pd.testing.assert_frame_equal(a.daily, b.daily)
    pd.testing.assert_frame_equal(a.trades, b.trades)


# ---------- random multi-day minute data: conservation in every mode ----------

def random_minutes(seed, days, codes):
    rng = np.random.default_rng(seed)
    frames = []
    for code in codes:
        p = 10.0
        for d in days:
            rows = []
            starts = ["09:24"] + [f"{s.components.hours:02d}:{s.components.minutes:02d}"
                                  for s in SESSION.expected_bar_starts()] + ["14:57", "14:58", "14:59"]
            for lab in starts:
                o = p
                c = p = max(1.0, p * np.exp(rng.normal(0, 0.002)))
                v = int(rng.integers(0, 5)) * 100
                rows.append({"code": code, "timestamp": d + hm(lab) + pd.Timedelta(minutes=1), "open": o,
                             "close": c, "high": max(o, c) * 1.001, "low": min(o, c) * 0.999,
                             "volume": v, "amount": v * (o + c) / 2})
            frames.append(pd.DataFrame(rows))
    return pd.concat(frames, ignore_index=True)


CAL = pd.bdate_range("2025-02-03", periods=6)


def random_orders(seed, codes):
    rng = np.random.default_rng(seed + 100)
    rows = []
    for d in CAL:
        for c in codes:
            u = rng.random()
            if u < 0.4:
                rows.append({"signal_date": d, "code": c, "side": "buy", "shares": int(rng.integers(1, 20)) * 100})
            elif u < 0.6:
                rows.append({"signal_date": d, "code": c, "side": "sell", "shares": np.nan})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("rule", [NEXT_OPEN, FIRST_VALID_MINUTE, VWAP_5, VWAP_15, VWAP_30,
                                  window_vwap_rule(time(10, 30), time(11, 0)),
                                  window_vwap_rule(time(9, 30), time(9, 45), max_participation=0.5)],
                         ids=lambda r: r.name)
def test_conservation_every_mode(rule):
    codes = ["A", "B", "C"]
    raw = random_minutes(1, CAL, codes)
    bars, _ = normalize_minute_bars(raw, CONTRACT, SESSION, CAL)
    daily = aggregate_daily(bars, CONTRACT, SESSION, CAL, codes)
    op, cl = to_panel(daily, "open", CAL, codes), to_panel(daily, "close", CAL, codes)
    ep = build_execution_prices(rule, CAL, codes, session=SESSION, daily_open=op, bars=bars, contract=CONTRACT)
    r = run_backtest_with_execution(random_orders(1, codes), ep, cl, initial_cash=200_000)
    assert len(r.trades) > 5
    check = reconcile(r)
    assert check["ok"], check
    assert (r.trades["date"] > pd.to_datetime(r.trades["signal_date"])).all()


def test_future_minutes_do_not_change_past_ledger():
    codes = ["A", "B"]
    raw = random_minutes(5, CAL, codes)
    raw2 = raw.copy()
    late = pd.to_datetime(raw2["timestamp"]) >= CAL[4]
    raw2.loc[late, ["open", "high", "low", "close"]] *= 1.3
    raw2.loc[late, "amount"] *= 1.3
    out = []
    for r_ in (raw, raw2):
        bars, _ = normalize_minute_bars(r_, CONTRACT, SESSION, CAL)
        daily = aggregate_daily(bars, CONTRACT, SESSION, CAL, codes)
        cl = to_panel(daily, "close", CAL, codes)
        ep = build_execution_prices(VWAP_15, CAL, codes, session=SESSION, bars=bars, contract=CONTRACT)
        out.append(run_backtest_with_execution(random_orders(5, codes), ep, cl, initial_cash=100_000))
    pd.testing.assert_frame_equal(out[0].daily.iloc[:4], out[1].daily.iloc[:4])


def test_reproducible_execution_pipeline():
    codes = ["A", "B"]
    raw = random_minutes(9, CAL, codes)
    res = []
    for _ in range(2):
        bars, _ = normalize_minute_bars(raw.copy(), CONTRACT, SESSION, CAL)
        daily = aggregate_daily(bars, CONTRACT, SESSION, CAL, codes)
        ep = build_execution_prices(VWAP_5, CAL, codes, session=SESSION, bars=bars, contract=CONTRACT)
        res.append(run_backtest_with_execution(random_orders(9, codes), ep, to_panel(daily, "close", CAL, codes),
                                               initial_cash=100_000))
    pd.testing.assert_frame_equal(res[0].daily, res[1].daily)
    pd.testing.assert_frame_equal(res[0].trades, res[1].trades)
