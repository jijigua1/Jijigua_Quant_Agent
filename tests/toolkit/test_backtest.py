"""Numerical acceptance for qrtk.backtest. Expected ledgers are hand-computed. Synthetic data only."""
import numpy as np
import pandas as pd
import pytest

from qrtk import CostModel, MarketRules, run_backtest

D = pd.bdate_range("2025-01-06", periods=4)


def px(rows, cols=("A",)):
    return pd.DataFrame(rows, index=D[: len(rows)], columns=list(cols), dtype=float)


def orders(*rows):
    return pd.DataFrame(rows, columns=["signal_date", "code", "side", "shares", "value"][: len(rows[0])])


OPEN = px([[10], [10], [11], [11]])
CLOSE = px([[10.2], [10.5], [11.2], [11.0]])


def test_hand_ledger_buy_then_sell():
    o = orders((D[0], "A", "buy", 1000), (D[1], "A", "sell", np.nan))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=100_000)
    d = r.daily
    # D0: nothing executes (signal only)
    assert d.loc[D[0], "cash"] == 100_000 and d.loc[D[0], "nav"] == 1.0
    # D1 open: buy 1000 @10 = 10000, commission max(3, 5) = 5 -> cash 89995; close 10.5 -> MV 10500
    assert d.loc[D[1], "cash"] == pytest.approx(89_995)
    assert d.loc[D[1], "market_value"] == pytest.approx(10_500)
    assert d.loc[D[1], "equity"] == pytest.approx(100_495)
    # D2 open: sell 1000 @11 = 11000, commission 5, stamp 5.5 -> +10989.5
    assert d.loc[D[2], "cash"] == pytest.approx(100_984.5)
    assert d.loc[D[2], "market_value"] == 0
    assert d.loc[D[2], "nav"] == pytest.approx(1.009845)
    t = r.trades
    assert t["date"].tolist() == [D[1], D[2]]
    assert t["commission"].tolist() == pytest.approx([5, 5]) and t["stamp_duty"].tolist() == pytest.approx([0, 5.5])
    assert r.rejections.empty


def test_commission_above_minimum_and_slippage():
    o = orders((D[0], "A", "buy", 10_000))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=200_000,
                     costs=CostModel(commission_rate=0.0003, min_commission=5, slippage_rate=0.001))
    t = r.trades.iloc[0]
    assert t["price"] == pytest.approx(10.01)
    assert t["amount"] == pytest.approx(100_100)
    assert t["commission"] == pytest.approx(30.03)
    assert r.daily.loc[D[1], "cash"] == pytest.approx(200_000 - 100_100 - 30.03)


def test_value_order_rounds_down_to_lots():
    o = orders((D[0], "A", "buy", np.nan, 50_000))
    t = run_backtest(o, OPEN, CLOSE, initial_cash=100_000).trades.iloc[0]
    # 50000 / (10 * 1.0003) = 4998.5 -> 4900 shares, 49000 + 14.7 fee <= 50000
    assert t["shares"] == 4900 and t["commission"] == pytest.approx(14.7)


def test_t_plus_one_blocks_same_session_sell():
    o = orders((D[0], "A", "buy", 1000), (D[0], "A", "sell", 1000))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=100_000)
    assert r.rejections["reason"].tolist() == ["t_plus_one"]
    assert r.daily.loc[D[1], "n_positions"] == 1
    r0 = run_backtest(o, OPEN, CLOSE, initial_cash=100_000, rules=MarketRules(t_plus_one=False))
    assert r0.rejections.empty and r0.daily.loc[D[1], "n_positions"] == 0
    # T+0 round trip at the same price loses exactly the fees: 5 + 5 + 5 stamp
    assert r0.daily.loc[D[1], "cash"] == pytest.approx(100_000 - 15)


def test_suspension_blocks_trades_and_keeps_stale_mark():
    susp = px([[0], [0], [1], [0]]).astype(bool)
    close = px([[10.2], [10.5], [np.nan], [11.0]])
    o = orders((D[0], "A", "buy", 1000), (D[1], "A", "sell", np.nan), (D[1], "A", "buy", 100))
    r = run_backtest(o, OPEN, close, initial_cash=100_000, suspended=susp)
    assert r.rejections["reason"].tolist() == ["suspended", "suspended"]
    pos = r.positions.set_index("date")
    assert pos.loc[D[2], "shares"] == 1000 and bool(pos.loc[D[2], "stale"])
    assert pos.loc[D[2], "mark_price"] == pytest.approx(10.5)       # last valid close
    assert r.daily.loc[D[2], "equity"] == pytest.approx(89_995 + 10_500)
    assert r.daily.loc[D[2], "n_stale"] == 1


def test_price_limits_and_unmodelled_flag():
    up = px([[0], [1], [0], [0]]).astype(bool)
    down = px([[0], [0], [1], [0]]).astype(bool)
    o = orders((D[0], "A", "buy", 1000), (D[1], "A", "buy", 1000), (D[2], "A", "sell", np.nan))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=100_000, limit_up=up, limit_down=down)
    # D1 buy blocked (limit up); D2 buy fills; D3 sell fills; nothing hits limit_down on D3
    assert r.rejections["reason"].tolist() == ["limit_up"]
    o2 = orders((D[0], "A", "buy", 1000), (D[1], "A", "sell", np.nan))
    r2 = run_backtest(o2, OPEN, CLOSE, initial_cash=100_000, limit_up=up, limit_down=down)
    assert r2.rejections["reason"].tolist() == ["limit_up", "no_position"]
    r3 = run_backtest(o2, OPEN, CLOSE, initial_cash=100_000)
    assert any("price-limit rules NOT modelled" in a for a in r3.assumptions)


def test_limit_down_blocks_sell():
    down = px([[0], [0], [1], [0]]).astype(bool)
    o = orders((D[0], "A", "buy", 1000), (D[1], "A", "sell", np.nan))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=100_000, limit_down=down)
    assert r.rejections["reason"].tolist() == ["limit_down"]
    assert r.daily.loc[D[3], "n_positions"] == 1                      # still held, not dropped


def test_unfillable_orders_are_recorded():
    o = orders((D[0], "A", "buy", 150), (D[0], "A", "buy", 100_000), (D[0], "A", "sell", 100),
               (D[3], "A", "buy", 100))
    r = run_backtest(o, OPEN, CLOSE, initial_cash=100_000)
    assert r.rejections["reason"].tolist() == ["no_next_session", "invalid_lot", "insufficient_cash", "no_position"]
    assert r.trades.empty and r.daily["cash"].eq(100_000).all()


def test_missing_open_rejects():
    o = orders((D[0], "A", "buy", 100))
    r = run_backtest(o, px([[10], [np.nan], [11], [11]]), CLOSE, initial_cash=10_000)
    assert r.rejections["reason"].tolist() == ["no_price"]


def random_case(seed, n_days=60, codes=("A", "B", "C", "D", "E")):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    close = pd.DataFrame(10 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_days, len(codes))), 0)), idx, list(codes))
    open_ = close.shift(1).fillna(10) * np.exp(rng.normal(0, 0.005, close.shape))
    susp = pd.DataFrame(rng.random(close.shape) < 0.05, idx, list(codes))
    rows = []
    for d in idx:
        for c in codes:
            u = rng.random()
            if u < 0.15:
                rows.append((d, c, "buy", int(rng.integers(1, 30)) * 100, np.nan))
            elif u < 0.25:
                rows.append((d, c, "sell", np.nan, np.nan))
    return pd.DataFrame(rows, columns=["signal_date", "code", "side", "shares", "value"]), open_, close, susp


@pytest.mark.parametrize("seed", range(5))
def test_cash_and_share_conservation(seed):
    o, op, cl, su = random_case(seed)
    r = run_backtest(o, op, cl, initial_cash=200_000, suspended=su)
    assert len(r.trades) > 20 and len(r.rejections) > 0
    # cash rebuilt independently from the trade list
    flow = r.trades.groupby("date")["cash_flow"].sum().reindex(r.daily.index, fill_value=0.0)
    np.testing.assert_allclose(200_000 + flow.cumsum(), r.daily["cash"], rtol=0, atol=1e-6)
    # shares rebuilt from trades
    signed = r.trades.assign(q=np.where(r.trades["side"] == "buy", r.trades["shares"], -r.trades["shares"]))
    held = signed.pivot_table(index="date", columns="code", values="q", aggfunc="sum").reindex(r.daily.index).fillna(0).cumsum()
    pos = r.positions.pivot_table(index="date", columns="code", values="shares", aggfunc="sum").reindex(
        index=r.daily.index, columns=held.columns).fillna(0)
    np.testing.assert_array_equal(held.to_numpy(), pos.to_numpy())
    assert (held.to_numpy() >= 0).all() and (r.daily["cash"] >= 0).all()
    # equity = cash + sum(shares * mark)
    mv = r.positions.groupby("date")["market_value"].sum().reindex(r.daily.index, fill_value=0.0)
    np.testing.assert_allclose(r.daily["cash"] + mv, r.daily["equity"], atol=1e-6)
    # fees reconcile
    fees = (r.trades["commission"] + r.trades["stamp_duty"]).groupby(r.trades["date"]).sum()
    np.testing.assert_allclose(fees.reindex(r.daily.index, fill_value=0), r.daily["fees"], atol=1e-9)


def test_no_future_information_in_ledger():
    o, op, cl, su = random_case(42)
    base = run_backtest(o, op, cl, initial_cash=200_000, suspended=su)
    k = 30
    op2, cl2 = op.copy(), cl.copy()
    op2.iloc[k + 1:] *= 3.0
    cl2.iloc[k + 1:] *= 0.3
    alt = run_backtest(o, op2, cl2, initial_cash=200_000, suspended=su)
    pd.testing.assert_frame_equal(base.daily.iloc[: k + 1], alt.daily.iloc[: k + 1])


def test_reproducible():
    o, op, cl, su = random_case(3)
    a = run_backtest(o, op, cl, initial_cash=150_000, suspended=su)
    b = run_backtest(o.copy(), op.copy(), cl.copy(), initial_cash=150_000, suspended=su.copy())
    pd.testing.assert_frame_equal(a.daily, b.daily)
    pd.testing.assert_frame_equal(a.trades, b.trades)
    pd.testing.assert_frame_equal(a.rejections, b.rejections)
