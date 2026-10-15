"""Minute contract + minute-to-daily aggregation. Expected values are hand-computed."""
from datetime import time, timedelta
import math
import statistics

import numpy as np
import pandas as pd
import pytest

from qrtk import (ContractError, DailyBarContract, MinuteBarContract, aggregate_daily,
                  normalize_daily_bars, normalize_minute_bars, to_panel, window_bars, window_stats)
from synth import CONTRACT, DAYS, SESSION, day_bars, hm, window_case

D0 = DAYS[0]
EXTREMES = {"10:00": {"high": 10.8}, "14:00": {"low": 9.9}}


def norm(raw, contract=CONTRACT, days=DAYS):
    return normalize_minute_bars(raw, contract, SESSION, days)


def agg(bars, codes=("A",), contract=CONTRACT, **kw):
    return aggregate_daily(bars, contract, SESSION, DAYS[:1], list(codes), **kw).set_index("code")


def test_contract_requires_explicit_declarations():
    with pytest.raises(TypeError):
        MinuteBarContract(volume_unit="share", amount_unit="CNY", open_auction="separate", close_auction="separate")
    with pytest.raises(ContractError):
        MinuteBarContract("middle", "share", "CNY", "separate", "separate")
    with pytest.raises(ContractError):
        MinuteBarContract("end", "share", "CNY", "separate", "separate", price_unit="cent")


def test_session_layout_with_lunch_break():
    starts = SESSION.expected_bar_starts()
    assert len(starts) == 120 + 117                  # 09:30-11:30 and 13:00-14:57
    assert hm("11:29") in starts and hm("11:30") not in starts and hm("12:30") not in starts
    assert starts[120] == hm("13:00")
    assert len(window_bars(SESSION, time(11, 25), time(13, 5))) == 10   # 5 before + 5 after lunch


def test_normal_day_aggregation_hand_values():
    bars, issues = norm(day_bars(D0, "A", overrides=EXTREMES))
    assert issues.empty
    r = agg(bars).loc["A"]
    # open = 09:25 auction 10.0; close = closing auction 10.5; zero-volume auction bars ignored
    assert (r["open"], r["high"], r["low"], r["close"]) == (10.0, 10.8, 9.9, 10.5)
    assert r["volume"] == 1000 + 237 * 100 + 2000
    assert r["amount"] == pytest.approx(10_000 + 237 * 1020 + 21_000)
    assert r["vwap"] == pytest.approx(272_740 / 26_700)
    assert (r["n_present"], r["n_expected"], r["coverage"]) == (237, 237, 1.0)
    assert (r["open_source"], r["close_source"], r["status"]) == ("open_auction", "close_auction", "ok")
    assert r["available_at"] == D0 + hm("15:00")


def test_auction_inclusion_switches():
    bars, _ = norm(day_bars(D0, "A", overrides=EXTREMES))
    r = agg(bars, include_open_auction=False, include_close_auction=False).loc["A"]
    assert (r["open"], r["close"], r["volume"]) == (10.2, 10.2, 23_700)
    assert r["vwap"] == pytest.approx(10.2)
    assert (r["open_source"], r["close_source"]) == ("first_continuous_trade", "last_continuous_trade")


def test_lunch_bar_is_not_a_valid_minute():
    raw = pd.concat([day_bars(D0, "A"),
                     pd.DataFrame([{"code": "A", "timestamp": D0 + hm("12:00"), "open": 10.2, "high": 10.2,
                                    "low": 10.2, "close": 10.2, "volume": 50, "amount": 510}])]).sort_values("timestamp")
    bars, issues = norm(raw)
    assert issues["issue"].tolist() == ["outside_session"]
    assert agg(bars).loc["A", "volume"] == 26_700          # the lunch bar did not count


def test_missing_duplicate_and_out_of_order_minutes():
    raw = day_bars(D0, "A", drop={"10:00", "10:01", "10:02", "10:03", "10:04"})
    dup_same = raw.iloc[[50]]
    dup_conf = raw.iloc[[60]].assign(close=10.3, high=10.3)
    mixed = pd.concat([raw, dup_same, dup_conf]).sample(frac=1, random_state=1)
    bars, issues = norm(mixed)
    kinds = set(issues["issue"])
    assert {"out_of_order", "duplicate_identical", "duplicate_conflict"} <= kinds
    r = agg(bars, min_coverage=0.99).loc["A"]
    # 237 - 5 dropped - 1 conflicting duplicate removed entirely
    assert r["n_present"] == 231 and r["status"] == "incomplete"
    assert r["volume"] == 26_700 - 6 * 100                 # identical duplicate counted once
    assert bars["bar_start"].is_monotonic_increasing


def test_suspended_no_trades_and_missing_are_distinct():
    zero = day_bars(D0, "C", vol=0, auction=(10.0, 0), close_auction=(10.0, 0))
    bars, _ = norm(pd.concat([day_bars(D0, "A"), zero]))
    r = agg(bars, codes=("A", "B", "C", "D"), suspended={(D0, "B")})
    assert r["status"].to_dict() == {"A": "ok", "B": "suspended", "C": "no_trades", "D": "missing"}
    assert r.loc[["B", "C", "D"], ["open", "close", "vwap"]].isna().all().all()


def test_zero_volume_window_has_no_vwap():
    zero = {f"09:3{i}": {"volume": 0, "amount": 0} for i in range(5)}
    bars, _ = norm(day_bars(D0, "A", overrides=zero))
    w = window_stats(bars, CONTRACT, SESSION, DAYS[:1], ["A"], time(9, 30), time(9, 35)).iloc[0]
    assert w["status"] == "no_trades" and math.isnan(w["vwap"])


def test_amount_unit_error_is_detected():
    raw = day_bars(D0, "A")
    raw["amount"] = raw["amount"] / 1000            # vendor sends thousands, contract says CNY
    bars, issues = norm(raw)
    assert (issues["issue"] == "bar_vwap_outside_range").sum() > 200
    r = agg(bars).loc["A"]
    assert r["vwap_status"] == "unit_inconsistent" and math.isnan(r["vwap"])
    lot = MinuteBarContract("end", "lot100", "CNY", "separate", "separate")
    raw2 = day_bars(D0, "A")
    raw2["volume"] = raw2["volume"] / 100           # declared lots: converted back to shares
    r2 = agg(norm(raw2, lot)[0], contract=lot).loc["A"]
    assert r2["volume"] == 26_700 and r2["vwap"] == pytest.approx(272_740 / 26_700)


def test_unknown_units_refuse_vwap():
    unk = MinuteBarContract("end", "unknown", "unknown", "separate", "separate")
    bars, _ = norm(day_bars(D0, "A"), unk)
    with pytest.raises(ContractError):
        agg(bars, contract=unk)
    with pytest.raises(ContractError):
        window_stats(bars, unk, SESSION, DAYS[:1], ["A"], time(9, 30), time(9, 35))
    r = agg(bars, contract=unk, allow_unknown_units=True).loc["A"]
    assert r["close"] == 10.5 and math.isnan(r["vwap"]) and r["vwap_status"] == "units_unknown"


def test_wrong_timestamp_convention_is_visible():
    start_conv = MinuteBarContract("start", "share", "CNY", "separate", "separate")
    bars, issues = norm(day_bars(D0, "A"), start_conv)
    out = issues[issues["issue"] == "outside_session"]["timestamp"]
    assert sorted(out.dt.strftime("%H:%M")) == ["11:30", "15:00"]
    assert agg(bars, contract=start_conv).loc["A", "coverage"] < 1


def test_timezone_and_trading_day_attribution():
    bar = {"code": "A", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "amount": 10}
    utc = pd.DataFrame([{**bar, "timestamp": pd.Timestamp("2025-01-06 01:31", tz="UTC")}])
    b, issues = norm(utc)                       # 01:31 UTC = 09:31 Shanghai, end-labelled
    assert issues.empty
    assert b.loc[0, "bar_start"] == pd.Timestamp("2025-01-06 09:30") and b.loc[0, "trade_date"] == D0
    naive = pd.DataFrame([{**bar, "timestamp": pd.Timestamp("2025-01-07 00:01")},     # midnight
                          {**bar, "timestamp": pd.Timestamp("2025-01-11 09:31")}])    # Saturday
    b2, issues2 = norm(naive)
    assert b2.empty and sorted(issues2["issue"]) == ["not_trading_day", "outside_session"]


def test_truncated_feed_and_as_of():
    late = [f"{h:02d}:{m:02d}" for h in range(11, 15) for m in range(60) if hm(f"{h:02d}:{m:02d}") >= hm("11:00")]
    bars, _ = norm(day_bars(D0, "A", close_auction=None, drop=set(late)))
    assert agg(bars).loc["A", "status"] == "truncated_feed"
    full, _ = norm(day_bars(D0, "A"))
    r = agg(full, as_of=D0 + hm("11:00")).loc["A"]
    assert r["status"] == "truncated_as_of" and r["n_present"] == 90   # 09:30-11:00 bars


def test_window_stats_hand_values():
    bars, _ = norm(window_case(D0))
    w = window_stats(bars, CONTRACT, SESSION, DAYS[:1], ["A"], time(9, 30), time(9, 35)).iloc[0]
    assert w["status"] == "ok"
    assert w["vwap"] == pytest.approx(8125 / 800)                  # 10.15625
    assert w["ret"] == pytest.approx(10.4 / 10.0 - 1)
    lr = [math.log(10.1 / 10.0), math.log(10.2 / 10.1), math.log(10.0 / 10.2),
          math.log(10.3 / 10.0), math.log(10.4 / 10.3)]
    assert w["vol_1min"] == pytest.approx(statistics.stdev(lr))
    assert w["observable_at"] == D0 + hm("09:35")


def test_incomplete_window_is_not_a_price():
    bars, _ = norm(window_case(D0).loc[lambda df: df["timestamp"] != D0 + hm("09:33")])
    w = window_stats(bars, CONTRACT, SESSION, DAYS[:1], ["A"], time(9, 30), time(9, 35)).iloc[0]
    assert w["status"] == "incomplete" and math.isnan(w["vwap"]) and w["n_present"] == 4


def test_future_minutes_do_not_change_past_days():
    raw = pd.concat([day_bars(d, "A", price=10 + i) for i, d in enumerate(DAYS)])
    b1, _ = norm(raw)
    raw2 = raw.copy()
    later = pd.to_datetime(raw2["timestamp"]) >= DAYS[2]
    raw2.loc[later, ["open", "high", "low", "close"]] *= 1.5
    raw2.loc[later, "amount"] *= 1.5
    b2, _ = norm(raw2)
    a1 = aggregate_daily(b1, CONTRACT, SESSION, DAYS, ["A"])
    a2 = aggregate_daily(b2, CONTRACT, SESSION, DAYS, ["A"])
    pd.testing.assert_frame_equal(a1.iloc[:2], a2.iloc[:2])
    assert a1.iloc[2]["close"] != a2.iloc[2]["close"]
    w1 = window_stats(b1, CONTRACT, SESSION, DAYS, ["A"], time(9, 30), time(10, 0))
    w2 = window_stats(b2, CONTRACT, SESSION, DAYS, ["A"], time(9, 30), time(10, 0))
    pd.testing.assert_frame_equal(w1.iloc[:2], w2.iloc[:2])


def test_to_panel_keeps_only_ok_rows():
    bars, _ = norm(day_bars(D0, "A"))
    daily = aggregate_daily(bars, CONTRACT, SESSION, DAYS[:1], ["A", "B"])
    p = to_panel(daily, "close", DAYS[:1], ["A", "B"])
    assert p.loc[D0, "A"] == 10.5 and math.isnan(p.loc[D0, "B"])


def test_daily_bar_contract_normalisation():
    raw = pd.DataFrame([
        {"trade_date": 20250106, "code": "A", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 10, "amount": 105},
        {"trade_date": 20250106, "code": "B", "open": 10, "high": 9, "low": 9, "close": 10.5, "volume": 10, "amount": 105},
        {"trade_date": 20250111, "code": "A", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 10, "amount": 105},
    ])
    c = DailyBarContract(volume_unit="lot100", amount_unit="thousand_CNY", availability_lag=timedelta(hours=2))
    df, issues = normalize_daily_bars(raw, c, DAYS)
    assert len(df) == 1 and df.loc[0, "volume"] == 1000 and df.loc[0, "amount"] == 105_000
    assert df.loc[0, "available_at"] == D0 + hm("17:00")
    assert sorted(issues["issue"]) == ["not_trading_day", "ohlc_inconsistent"]


def test_reproducible_minute_pipeline():
    raw = pd.concat([day_bars(d, c) for d in DAYS for c in "AB"])
    a = aggregate_daily(norm(raw)[0], CONTRACT, SESSION, DAYS, ["A", "B"])
    b = aggregate_daily(norm(raw.copy())[0], CONTRACT, SESSION, DAYS, ["A", "B"])
    pd.testing.assert_frame_equal(a, b)
