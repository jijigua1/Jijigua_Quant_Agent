"""Small, transparent daily cash-equity reference ledger (for cross-checking real engines).

Semantics (see METHODOLOGY.md):
  * An order carries a `signal_date`; it executes on the NEXT calendar session.
  * The execution price panel defaults to the open; any ExecutionPrices (first valid minute,
    window VWAP, ...) can be supplied instead via run_backtest_with_execution. The fill price
    and the close used for valuation are separate inputs.
  * Orders of one session are processed in input order, or sells first (order_priority).
  * Fill price = exec price * (1 + slippage) for buys, * (1 - slippage) for sells.
  * Valuation at the CLOSE; a suspended stock or missing close keeps the last mark (stale).
  * Shares are real share counts on UNADJUSTED prices; corporate actions are NOT modelled, so
    adjusted prices are refused (price_adjustment must be 'none').
Every unfilled order is recorded with a reason and a category; nothing is silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
import math
from typing import Callable, Mapping

import numpy as np
import pandas as pd

EPS = 1e-9

REJECTION_CATEGORY = {
    "no_next_session": "calendar",
    "signal_after_exec_start": "timing",
    "no_price": "data_unavailable", "missing_data": "data_unavailable",
    "incomplete_window": "data_unavailable", "unit_inconsistent": "data_unavailable",
    "capacity_unknown": "data_unavailable",
    "suspended": "not_executable", "no_trades": "not_executable", "limit_up": "not_executable",
    "limit_down": "not_executable", "capacity_exceeded": "not_executable", "t_plus_one": "not_executable",
    "invalid_lot": "order_or_account", "insufficient_cash": "order_or_account",
    "budget_below_one_lot": "order_or_account", "no_position": "order_or_account",
    "invalid_or_excess_shares": "order_or_account",
}


def _finite_rate(x, name, upper=0.1):
    if not (isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x < upper):
        raise ValueError(f"{name} must be finite and in [0, {upper})")


@dataclass(frozen=True)
class CostModel:
    commission_rate: float = 0.0003   # both sides
    min_commission: float = 5.0       # per fill
    stamp_duty_rate: float = 0.0005   # sells only; a parameter, not a historical schedule
    slippage_rate: float = 0.0

    def __post_init__(self):
        _finite_rate(self.commission_rate, "commission_rate")
        _finite_rate(self.stamp_duty_rate, "stamp_duty_rate")
        _finite_rate(self.slippage_rate, "slippage_rate")
        if not (math.isfinite(self.min_commission) and self.min_commission >= 0):
            raise ValueError("min_commission must be finite and >= 0")

    def commission(self, amount: float) -> float:
        return max(amount * self.commission_rate, self.min_commission)


@dataclass(frozen=True)
class MarketRules:
    lot_size: int = 100        # buys must be whole lots; sells may be any held quantity
    t_plus_one: bool = True    # shares bought in a session cannot be sold in the same session
    lot_size_fn: Callable[[str], int] | None = None   # per-code lot (extension point)

    def __post_init__(self):
        if not (isinstance(self.lot_size, int) and self.lot_size > 0):
            raise ValueError("lot_size must be a positive int")

    def lot(self, code: str) -> int:
        n = self.lot_size_fn(code) if self.lot_size_fn else self.lot_size
        if not (isinstance(n, int) and n > 0):
            raise ValueError(f"lot for {code} must be a positive int")
        return n


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    trades: pd.DataFrame
    rejections: pd.DataFrame
    positions: pd.DataFrame
    assumptions: tuple = field(default_factory=tuple)
    initial_cash: float = float("nan")
    initial_positions: Mapping = field(default_factory=dict)
    initial_equity: float = float("nan")


def _flag(panel: pd.DataFrame | None, date, code) -> bool:
    if panel is None or code not in panel.columns or date not in panel.index:
        return False
    v = panel.at[date, code]
    return bool(v) if pd.notna(v) else False


def _check_price_panel(p: pd.DataFrame, name: str):
    if not isinstance(p, pd.DataFrame) or not isinstance(p.index, pd.DatetimeIndex):
        raise TypeError(f"{name} must be a DataFrame with a DatetimeIndex")
    if p.columns.has_duplicates:
        raise ValueError(f"{name}: duplicate codes")
    v = p.to_numpy(dtype=float)
    if np.isinf(v).any():
        raise ValueError(f"{name} contains inf")
    if (v[~np.isnan(v)] <= 0).any():
        raise ValueError(f"{name} must be positive or NaN")


def _validate_orders(orders: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(orders, pd.DataFrame):
        raise TypeError("orders must be a DataFrame")
    miss = {"signal_date", "code", "side"} - set(orders.columns)
    if miss:
        raise ValueError(f"orders missing columns {sorted(miss)}")
    o = orders.copy().reset_index(drop=True)
    for col in ("shares", "value"):
        o[col] = pd.to_numeric(o[col], errors="raise").astype(float) if col in o else np.nan
    if not o["side"].isin(["buy", "sell"]).all():
        raise ValueError("side must be 'buy' or 'sell'")
    if np.isinf(o[["shares", "value"]].to_numpy()).any():
        raise ValueError("shares/value must not be inf")
    if (o["shares"] <= 0).any() or (o["value"] <= 0).any():
        raise ValueError("shares/value must be positive when given")
    if (o["shares"].notna() & o["value"].notna()).any():
        raise ValueError("give either shares or value, not both")
    if ((o["side"] == "sell") & o["value"].notna()).any():
        raise ValueError("value is only valid for buys")
    if ((o["side"] == "buy") & o["shares"].isna() & o["value"].isna()).any():
        raise ValueError("buy order needs shares or value")
    if not o["code"].map(lambda c: isinstance(c, str) and c != "").all():
        raise ValueError("code must be a non-empty string")
    o["_signal_ts"] = pd.to_datetime(o["signal_date"], errors="raise")
    if o["_signal_ts"].isna().any():
        raise ValueError("signal_date must not be missing")
    if "signal_time" in o:
        o["signal_time"] = pd.to_datetime(o["signal_time"], errors="raise")
    return o


def run_backtest(orders: pd.DataFrame, open_px: pd.DataFrame, close_px: pd.DataFrame, *,
                 initial_cash: float, costs: CostModel = CostModel(),
                 rules: MarketRules = MarketRules(), suspended: pd.DataFrame | None = None,
                 limit_up: pd.DataFrame | None = None, limit_down: pd.DataFrame | None = None,
                 initial_positions: Mapping[str, int] | None = None,
                 initial_marks: Mapping[str, float] | None = None,
                 order_priority: str = "input", price_adjustment: str = "none",
                 exec_status: pd.DataFrame | None = None, exec_capacity: pd.DataFrame | None = None,
                 exec_start_time: time | None = None) -> BacktestResult:
    """Run the ledger.

    orders columns: signal_date, code, side ('buy'|'sell'), optional shares / value / signal_time
      shares      buys: positive multiple of the lot; sells: positive int, NaN = all available
      value       buys only (when shares is NaN): max cash to spend including fees
      signal_time when the decision was made; with exec_start_time it must precede the
                  execution start on the execution day, otherwise 'signal_after_exec_start'
    open_px: execution price panel (default the open); close_px: valuation panel; same calendar.
    suspended / limit_up / limit_down: optional bool panels on the execution date; a panel not
      supplied means the rule is NOT modelled (listed in assumptions).
    initial_positions / initial_marks: starting shares and their reference prices; initial
      equity = initial_cash + sum(shares * mark) is the NAV base. Starting shares are sellable.
    exec_status: date x code; anything other than 'ok' rejects with that status as reason.
    exec_capacity: date x code max fillable shares; NaN -> 'capacity_unknown'.
    """
    if price_adjustment != "none":
        raise ValueError("this ledger holds real shares on unadjusted prices; adjusted prices "
                         "would mis-state cash and share counts (corporate actions not modelled)")
    if order_priority not in ("input", "sells_first"):
        raise ValueError("order_priority must be 'input' or 'sells_first'")
    _check_price_panel(open_px, "open_px")
    _check_price_panel(close_px, "close_px")
    if not open_px.index.equals(close_px.index):
        raise ValueError("open_px and close_px must share one calendar")
    cal = open_px.index
    if cal.has_duplicates or not cal.is_monotonic_increasing:
        raise ValueError("calendar must be unique and increasing")
    if not (isinstance(initial_cash, (int, float)) and math.isfinite(initial_cash) and initial_cash >= 0):
        raise ValueError("initial_cash must be finite and >= 0")
    init_pos = dict(initial_positions or {})
    marks0 = dict(initial_marks or {})
    for c, n in init_pos.items():
        if not (isinstance(n, (int, np.integer)) and n > 0):
            raise ValueError(f"initial position {c} must be a positive int")
        m = marks0.get(c)
        if m is None or not (math.isfinite(m) and m > 0):
            raise ValueError(f"initial_marks must give a positive price for {c}")
    initial_equity = float(initial_cash) + sum(n * marks0[c] for c, n in init_pos.items())
    if initial_equity <= 0:
        raise ValueError("initial equity must be positive")
    for p, name in ((exec_status, "exec_status"), (exec_capacity, "exec_capacity")):
        if p is not None and not p.index.equals(cal):
            raise ValueError(f"{name} must share the price calendar")
    if exec_capacity is not None:
        v = exec_capacity.to_numpy(dtype=float)
        if np.isinf(v).any() or (v[~np.isnan(v)] < 0).any():
            raise ValueError("exec_capacity must be finite and >= 0 or NaN")

    orders = _validate_orders(orders)
    pos_idx = cal.searchsorted(orders["_signal_ts"], side="right")
    orders["exec_date"] = [cal[i] if i < len(cal) else pd.NaT for i in pos_idx]
    if order_priority == "sells_first":
        orders = orders.assign(_k=(orders["side"] == "buy").astype(int)).sort_values(
            ["_k"], kind="mergesort").drop(columns="_k")

    cash = float(initial_cash)
    held: dict[str, int] = {c: int(n) for c, n in init_pos.items()}
    mark: dict[str, float] = {c: float(marks0[c]) for c in init_pos}
    trades, rejects, pos_rows, daily = [], [], [], []

    def reject(o, reason, date):
        rejects.append({"signal_date": o.signal_date, "exec_date": date, "code": o.code,
                        "side": o.side, "shares": o.shares, "value": o.value, "reason": reason,
                        "category": REJECTION_CATEGORY[reason]})

    for o in orders[orders["exec_date"].isna()].itertuples():
        reject(o, "no_next_session", pd.NaT)

    has_signal_time = "signal_time" in orders
    for d in cal:
        sellable = dict(held) if rules.t_plus_one else None   # start-of-session holdings
        cash_start = cash
        buy_out = sell_in = fees = buy_amt = sell_amt = 0.0
        for o in orders[orders["exec_date"] == d].itertuples():
            code = o.code
            if (has_signal_time and exec_start_time is not None and pd.notna(o.signal_time)
                    and o.signal_time >= d + pd.Timedelta(hours=exec_start_time.hour, minutes=exec_start_time.minute)):
                reject(o, "signal_after_exec_start", d); continue
            px_exec = open_px.at[d, code] if code in open_px.columns else np.nan
            if _flag(suspended, d, code):
                reject(o, "suspended", d); continue
            if exec_status is not None:
                st = exec_status.at[d, code] if code in exec_status.columns else "missing_data"
                if st != "ok":
                    reject(o, st if st in REJECTION_CATEGORY else "missing_data", d); continue
            if pd.isna(px_exec):
                reject(o, "no_price", d); continue
            cap = np.inf
            if exec_capacity is not None:
                cap = exec_capacity.at[d, code] if code in exec_capacity.columns else np.nan
                if pd.isna(cap):
                    reject(o, "capacity_unknown", d); continue
            lot = rules.lot(code)
            if o.side == "buy":
                if _flag(limit_up, d, code):
                    reject(o, "limit_up", d); continue
                px = float(px_exec) * (1 + costs.slippage_rate)
                if pd.notna(o.shares):
                    n = int(o.shares)
                    if n != o.shares or n % lot:
                        reject(o, "invalid_lot", d); continue
                    if n * px + costs.commission(n * px) > cash + EPS:
                        reject(o, "insufficient_cash", d); continue
                else:
                    budget = min(float(o.value), cash)
                    n = math.floor(budget / (px * (1 + costs.commission_rate)) / lot) * lot
                    while n > 0 and n * px + costs.commission(n * px) > budget + EPS:
                        n -= lot
                    if n <= 0:
                        reject(o, "budget_below_one_lot", d); continue
                if n > cap:
                    reject(o, "capacity_exceeded", d); continue
                amount = n * px
                comm = costs.commission(amount)
                cash_before, cash = cash, cash - amount - comm
                held[code] = held.get(code, 0) + n
                mark.setdefault(code, px)
                buy_out += amount + comm
                buy_amt += amount
                fees += comm
                trades.append({"date": d, "signal_date": o.signal_date, "code": code, "side": "buy",
                               "shares": n, "price": px, "amount": amount, "commission": comm,
                               "stamp_duty": 0.0, "cash_flow": -(amount + comm),
                               "cash_before": cash_before, "cash_after": cash})
            else:
                have = held.get(code, 0)
                avail = have if sellable is None else min(have, sellable.get(code, 0))
                if have == 0:
                    reject(o, "no_position", d); continue
                if _flag(limit_down, d, code):
                    reject(o, "limit_down", d); continue
                if pd.isna(o.shares):
                    if avail == 0:
                        reject(o, "t_plus_one", d); continue
                    n = avail
                else:
                    if o.shares != int(o.shares) or o.shares > have:
                        reject(o, "invalid_or_excess_shares", d); continue
                    if o.shares > avail:
                        reject(o, "t_plus_one", d); continue
                    n = int(o.shares)
                if n > cap:
                    reject(o, "capacity_exceeded", d); continue
                px = float(px_exec) * (1 - costs.slippage_rate)
                amount = n * px
                comm = costs.commission(amount)
                stamp = amount * costs.stamp_duty_rate
                cash_before, cash = cash, cash + amount - comm - stamp
                held[code] = have - n
                if sellable is not None:
                    sellable[code] = sellable.get(code, 0) - n
                if held[code] == 0:
                    del held[code]
                sell_in += amount - comm - stamp
                sell_amt += amount
                fees += comm + stamp
                trades.append({"date": d, "signal_date": o.signal_date, "code": code, "side": "sell",
                               "shares": n, "price": px, "amount": amount, "commission": comm,
                               "stamp_duty": stamp, "cash_flow": amount - comm - stamp,
                               "cash_before": cash_before, "cash_after": cash})
        # conservation inside the session
        assert abs(cash - (cash_start - buy_out + sell_in)) < 1e-6, "cash not conserved"
        assert cash > -EPS, "negative cash"
        mv, n_stale = 0.0, 0
        for code, n in sorted(held.items()):
            c = close_px.at[d, code] if code in close_px.columns else np.nan
            stale = _flag(suspended, d, code) or pd.isna(c)
            if not stale:
                mark[code] = float(c)
            n_stale += stale
            mv += n * mark[code]
            pos_rows.append({"date": d, "code": code, "shares": n, "mark_price": mark[code],
                             "market_value": n * mark[code], "stale": stale})
        equity = cash + mv
        daily.append({"date": d, "cash": cash, "market_value": mv, "equity": equity,
                      "nav": equity / initial_equity, "buy_cash_out": buy_out,
                      "sell_cash_in": sell_in, "fees": fees, "n_positions": len(held),
                      "n_stale": n_stale, "buy_amount": buy_amt, "sell_amount": sell_amt})

    assumptions = [
        "fills at the execution price +/- slippage with unlimited liquidity unless a capacity panel is given",
        "unadjusted prices and real share counts; dividends, splits and other corporate actions NOT modelled",
        "delisting liquidation NOT modelled: a position without prices keeps its last mark (stale)",
        (f"buys in lots of {rules.lot_size}" if rules.lot_size_fn is None else "buys in per-code lots (lot_size_fn)")
        + "; board-specific rules (e.g. STAR 200-share minimum then 1-share steps) NOT modelled",
        "fees are configuration parameters, not historical fee schedules",
        "T+1 enforced" if rules.t_plus_one else "T+1 NOT enforced (T+0 semantics)",
        f"orders within a session processed in {order_priority} order",
    ]
    if suspended is None:
        assumptions.append("no suspension panel: only a missing open blocks trading")
    if limit_up is None or limit_down is None:
        assumptions.append("price-limit rules NOT modelled for the side(s) without a limit panel")

    cols_t = ["date", "signal_date", "code", "side", "shares", "price", "amount", "commission",
              "stamp_duty", "cash_flow", "cash_before", "cash_after"]
    cols_r = ["signal_date", "exec_date", "code", "side", "shares", "value", "reason", "category"]
    cols_p = ["date", "code", "shares", "mark_price", "market_value", "stale"]
    return BacktestResult(
        daily=pd.DataFrame(daily).set_index("date"),
        trades=pd.DataFrame(trades, columns=cols_t),
        rejections=pd.DataFrame(rejects, columns=cols_r),
        positions=pd.DataFrame(pos_rows, columns=cols_p),
        assumptions=tuple(assumptions),
        initial_cash=float(initial_cash),
        initial_positions={c: int(n) for c, n in init_pos.items()},
        initial_equity=initial_equity,
    )


def run_backtest_with_execution(orders: pd.DataFrame, exec_prices, close_px: pd.DataFrame, *,
                                initial_cash: float, **kwargs) -> BacktestResult:
    """Ledger with an ExecutionPrices rule (next open, first valid minute, window VWAP...).

    The rule's status and capacity are enforced, its exec_start bounds signal_time, and its
    assumptions are appended to the result."""
    if exec_prices.adjustment != "none":
        raise ValueError("execution prices are adjusted; this ledger needs unadjusted prices")
    px = exec_prices.price.reindex(index=close_px.index, columns=close_px.columns)
    st = exec_prices.status.reindex(index=close_px.index, columns=close_px.columns).fillna("missing_data")
    cap = (None if exec_prices.capacity is None else
           exec_prices.capacity.reindex(index=close_px.index, columns=close_px.columns))
    res = run_backtest(orders, px, close_px, initial_cash=initial_cash, exec_status=st,
                       exec_capacity=cap, exec_start_time=exec_prices.exec_start, **kwargs)
    return BacktestResult(res.daily, res.trades, res.rejections, res.positions,
                          res.assumptions + exec_prices.assumptions, res.initial_cash,
                          res.initial_positions, res.initial_equity)
