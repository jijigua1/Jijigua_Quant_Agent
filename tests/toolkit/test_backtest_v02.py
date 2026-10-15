"""v0.2 ledger: validation, initial positions, order priority, lots, metrics, v0.1 regression."""
import importlib.util
import math
import pathlib
import statistics
import sys

import numpy as np
import pandas as pd
import pytest

from qrtk import (BacktestResult, CostModel, MarketRules, performance_metrics, reconcile,
                  run_backtest)
from test_backtest import CLOSE, D, OPEN, px, random_case

_spec = importlib.util.spec_from_file_location(
    "v01_backtest", pathlib.Path(__file__).parent / "baseline" / "v01_backtest.py")
v01 = importlib.util.module_from_spec(_spec)
sys.modules["v01_backtest"] = v01
_spec.loader.exec_module(v01)


def o(*rows):
    return pd.DataFrame(rows, columns=["signal_date", "code", "side", "shares", "value"][: len(rows[0])])


@pytest.mark.parametrize("seed", range(6))
def test_same_results_as_frozen_v01(seed):
    orders, op, cl, su = random_case(seed)
    new = run_backtest(orders, op, cl, initial_cash=200_000, suspended=su)
    old = v01.run_backtest(orders, op, cl, initial_cash=200_000, suspended=su)
    pd.testing.assert_frame_equal(new.daily[old.daily.columns], old.daily)
    pd.testing.assert_frame_equal(new.trades, old.trades)
    pd.testing.assert_frame_equal(new.rejections.drop(columns="category"), old.rejections)
    pd.testing.assert_frame_equal(new.positions, old.positions)


@pytest.mark.parametrize("bad", [
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN.replace(10.0, np.inf), CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN * -1, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN, CLOSE, initial_cash=float("inf")),
    lambda: run_backtest(o((pd.NaT, "A", "buy", 100)), OPEN, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "hold", 100)), OPEN, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "buy", -100)), OPEN, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "buy", 100, 5000)), OPEN, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "A", "sell", np.nan, 5000)), OPEN, CLOSE, initial_cash=1e5),
    lambda: run_backtest(o((D[0], "", "buy", 100)), OPEN, CLOSE, initial_cash=1e5),
    lambda: CostModel(commission_rate=-0.001),
    lambda: CostModel(stamp_duty_rate=0.5),
    lambda: CostModel(min_commission=float("nan")),
    lambda: MarketRules(lot_size=0),
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN, CLOSE, initial_cash=1e5, price_adjustment="forward"),
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN, CLOSE, initial_cash=1e5, initial_positions={"A": 100}),
    lambda: run_backtest(o((D[0], "A", "buy", 100)), OPEN, CLOSE, initial_cash=1e5, order_priority="random"),
], ids=["inf_price", "negative_price", "inf_cash", "nat_date", "bad_side", "negative_shares",
        "shares_and_value", "sell_value", "empty_code", "neg_commission", "huge_stamp", "nan_min_fee",
        "zero_lot", "adjusted_prices", "position_without_mark", "bad_priority"])
def test_invalid_inputs_raise(bad):
    with pytest.raises((ValueError, TypeError)):
        bad()


def test_initial_positions_and_nav_base():
    # 50,000 cash + 1000 A marked at 10 = 60,000 initial equity; starting shares are sellable on D1
    r = run_backtest(o((D[0], "A", "sell", np.nan)), OPEN, CLOSE, initial_cash=50_000,
                     initial_positions={"A": 1000}, initial_marks={"A": 10.0})
    assert r.initial_equity == 60_000
    d = r.daily
    assert d.loc[D[0], "equity"] == pytest.approx(50_000 + 1000 * 10.2)
    assert d.loc[D[0], "nav"] == pytest.approx(60_200 / 60_000)
    # D1 open sell 1000 @10: +10000 - 5 commission - 5 stamp
    assert d.loc[D[1], "cash"] == pytest.approx(59_990) and d.loc[D[1], "market_value"] == 0
    assert reconcile(r)["ok"]


def test_order_priority_frees_cash():
    op = px([[10, 20]] * 4, ("A", "B"))
    cl = op.copy()
    orders = o((D[0], "B", "buy", 100), (D[0], "A", "sell", np.nan))
    kw = dict(initial_cash=1_000, initial_positions={"A": 1000}, initial_marks={"A": 10.0})
    r_in = run_backtest(orders, op, cl, **kw)
    assert r_in.rejections["reason"].tolist() == ["insufficient_cash"]
    r_sf = run_backtest(orders, op, cl, order_priority="sells_first", **kw)
    assert r_sf.rejections.empty
    # 1000 + (10000 - 5 - 5) - (2000 + 5)
    assert r_sf.daily.loc[D[1], "cash"] == pytest.approx(8_985)


def test_per_code_lot_extension_point():
    op = px([[10, 20]] * 4, ("600000.SH", "688001.SH"))
    rules = MarketRules(lot_size_fn=lambda c: 200 if c.startswith("688") else 100)
    orders = o((D[0], "688001.SH", "buy", 100), (D[0], "688001.SH", "buy", 200), (D[0], "600000.SH", "buy", 100))
    r = run_backtest(orders, op, op, initial_cash=100_000, rules=rules)
    assert r.rejections["reason"].tolist() == ["invalid_lot"]
    assert r.trades["shares"].tolist() == [200, 100]


def test_rejection_categories():
    susp = px([[0], [1], [0], [0]]).astype(bool)
    r = run_backtest(o((D[0], "A", "buy", 100), (D[1], "A", "buy", 100)),
                     px([[10], [10], [np.nan], [11]]), CLOSE, initial_cash=10_000, suspended=susp)
    assert r.rejections[["reason", "category"]].values.tolist() == [
        ["suspended", "not_executable"], ["no_price", "data_unavailable"]]


def test_performance_metrics_hand():
    idx = pd.bdate_range("2025-01-06", periods=4)
    daily = pd.DataFrame({"equity": [100.0, 110.0, 99.0, 108.9], "buy_amount": [50.0, 0, 0, 0],
                          "sell_amount": [0, 0, 22.0, 0], "fees": [0.1, 0, 0.2, 0]}, index=idx)
    res = BacktestResult(daily, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), initial_cash=100.0,
                         initial_equity=100.0)
    m = performance_metrics(res)
    r = [0.0, 0.1, -0.1, 0.1]                              # NAV 1, 1, 1.1, 0.99, 1.089
    assert m["cumulative_return"] == pytest.approx(0.089)
    assert m["annual_return"] == pytest.approx(1.089 ** (252 / 4) - 1)
    assert m["annual_volatility"] == pytest.approx(statistics.stdev(r) * math.sqrt(252))
    assert m["sharpe"] == pytest.approx(statistics.mean(r) / statistics.stdev(r) * math.sqrt(252))
    assert m["max_drawdown"] == pytest.approx(0.99 / 1.1 - 1)
    # turnover: day0 (50/2)/100, day2 (22/2)/110
    assert m["turnover"] == pytest.approx((0.25 + 0 + 0.1 + 0) / 4)
    assert m["total_fees"] == pytest.approx(0.3) and m["fee_ratio"] == pytest.approx(0.003)


def test_metrics_undefined_is_nan():
    idx = pd.bdate_range("2025-01-06", periods=1)
    daily = pd.DataFrame({"equity": [100.0], "buy_amount": [0.0], "sell_amount": [0.0], "fees": [0.0]}, index=idx)
    m = performance_metrics(BacktestResult(daily, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                           initial_cash=100.0, initial_equity=100.0))
    assert math.isnan(m["sharpe"]) and math.isnan(m["annual_volatility"])


def test_reconcile_detects_tampering():
    orders, op, cl, su = random_case(2)
    r = run_backtest(orders, op, cl, initial_cash=200_000, suspended=su)
    assert reconcile(r)["ok"]
    bad = r.trades.copy()
    bad.loc[0, "cash_flow"] += 1.0
    tampered = BacktestResult(r.daily, bad, r.rejections, r.positions, r.assumptions, r.initial_cash,
                              r.initial_positions, r.initial_equity)
    assert not reconcile(tampered)["ok"]
