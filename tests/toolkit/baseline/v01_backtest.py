"""Small, transparent daily cash-equity reference ledger (for cross-checking real engines).

Semantics (see METHODOLOGY.md):
  * An order carries a `signal_date`; it executes at the OPEN of the next calendar session.
  * Orders of one session are processed in input order (put sells first to free cash).
  * Fill price = open * (1 + slippage) for buys, open * (1 - slippage) for sells; unlimited depth.
  * Valuation at the CLOSE; a suspended stock or missing close keeps the last mark (stale).
  * Shares are real share counts on unadjusted prices; corporate actions are NOT modelled.
Every unfilled order is recorded with a reason; nothing is silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

EPS = 1e-9


@dataclass(frozen=True)
class CostModel:
    commission_rate: float = 0.0003   # both sides
    min_commission: float = 5.0       # per fill
    stamp_duty_rate: float = 0.0005   # sells only; a parameter, not a historical schedule
    slippage_rate: float = 0.0

    def commission(self, amount: float) -> float:
        return max(amount * self.commission_rate, self.min_commission)


@dataclass(frozen=True)
class MarketRules:
    lot_size: int = 100        # buys must be whole lots; sells may be any held quantity
    t_plus_one: bool = True    # shares bought in a session cannot be sold in the same session


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    trades: pd.DataFrame
    rejections: pd.DataFrame
    positions: pd.DataFrame
    assumptions: tuple = field(default_factory=tuple)


def _flag(panel: pd.DataFrame | None, date, code) -> bool:
    if panel is None or code not in panel.columns or date not in panel.index:
        return False
    v = panel.at[date, code]
    return bool(v) if pd.notna(v) else False


def run_backtest(orders: pd.DataFrame, open_px: pd.DataFrame, close_px: pd.DataFrame, *,
                 initial_cash: float, costs: CostModel = CostModel(),
                 rules: MarketRules = MarketRules(), suspended: pd.DataFrame | None = None,
                 limit_up: pd.DataFrame | None = None,
                 limit_down: pd.DataFrame | None = None) -> BacktestResult:
    """Run the ledger.

    orders columns: signal_date, code, side ('buy'|'sell'), and optionally
      shares  - buys: positive multiple of lot_size; sells: positive int, NaN = sell all available
      value   - buys only, used when shares is NaN: max cash to spend including fees
    open_px / close_px: date x code unadjusted prices on the same calendar (the session list).
    suspended / limit_up / limit_down: optional bool panels on the execution date. limit_up
      blocks buys, limit_down blocks sells. Panels not supplied mean the rule is NOT modelled.
    """
    if not open_px.index.equals(close_px.index):
        raise ValueError("open_px and close_px must share one calendar")
    cal = open_px.index
    if cal.has_duplicates or not cal.is_monotonic_increasing:
        raise ValueError("calendar must be unique and increasing")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    orders = orders.copy().reset_index(drop=True)
    for col in ("shares", "value"):
        if col not in orders:
            orders[col] = np.nan
    if not orders["side"].isin(["buy", "sell"]).all():
        raise ValueError("side must be 'buy' or 'sell'")
    sig = pd.to_datetime(orders["signal_date"])
    pos_idx = cal.searchsorted(sig, side="right")
    orders["exec_date"] = [cal[i] if i < len(cal) else pd.NaT for i in pos_idx]

    cash = float(initial_cash)
    held: dict[str, int] = {}
    mark: dict[str, float] = {}
    trades, rejects, pos_rows, daily = [], [], [], []

    def reject(o, reason, date):
        rejects.append({"signal_date": o.signal_date, "exec_date": date, "code": o.code,
                        "side": o.side, "shares": o.shares, "value": o.value, "reason": reason})

    for o in orders[orders["exec_date"].isna()].itertuples():
        reject(o, "no_next_session", pd.NaT)

    for d in cal:
        sellable = dict(held) if rules.t_plus_one else None   # start-of-session holdings
        cash_start = cash
        buy_out = sell_in = fees = 0.0
        for o in orders[orders["exec_date"] == d].itertuples():
            code = o.code
            px_open = open_px.at[d, code] if code in open_px.columns else np.nan
            if _flag(suspended, d, code):
                reject(o, "suspended", d); continue
            if pd.isna(px_open):
                reject(o, "no_price", d); continue
            if o.side == "buy":
                if _flag(limit_up, d, code):
                    reject(o, "limit_up", d); continue
                px = float(px_open) * (1 + costs.slippage_rate)
                if pd.notna(o.shares):
                    n = int(o.shares)
                    if n <= 0 or n != o.shares or n % rules.lot_size:
                        reject(o, "invalid_lot", d); continue
                    if n * px + costs.commission(n * px) > cash + EPS:
                        reject(o, "insufficient_cash", d); continue
                elif pd.notna(o.value):
                    budget = min(float(o.value), cash)
                    n = math.floor(budget / (px * (1 + costs.commission_rate)) / rules.lot_size) * rules.lot_size
                    while n > 0 and n * px + costs.commission(n * px) > budget + EPS:
                        n -= rules.lot_size
                    if n <= 0:
                        reject(o, "budget_below_one_lot", d); continue
                else:
                    raise ValueError("buy order needs shares or value")
                amount = n * px
                comm = costs.commission(amount)
                cash_before, cash = cash, cash - amount - comm
                held[code] = held.get(code, 0) + n
                mark.setdefault(code, px)
                buy_out += amount + comm
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
                    if o.shares != int(o.shares) or o.shares <= 0 or o.shares > have:
                        reject(o, "invalid_or_excess_shares", d); continue
                    if o.shares > avail:
                        reject(o, "t_plus_one", d); continue
                    n = int(o.shares)
                px = float(px_open) * (1 - costs.slippage_rate)
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
                      "nav": equity / initial_cash, "buy_cash_out": buy_out,
                      "sell_cash_in": sell_in, "fees": fees, "n_positions": len(held),
                      "n_stale": n_stale})

    assumptions = [
        "fills at open +/- slippage with unlimited liquidity; no order book or volume cap",
        "unadjusted prices and real share counts; dividends, splits and other corporate actions NOT modelled",
        "delisting liquidation NOT modelled: a position without prices keeps its last mark (stale)",
        f"buys in lots of {rules.lot_size}; board-specific lot rules (e.g. STAR 200-share minimum) NOT modelled",
        "fees are configuration parameters, not historical fee schedules",
        "T+1 enforced" if rules.t_plus_one else "T+1 NOT enforced (T+0 semantics)",
    ]
    if suspended is None:
        assumptions.append("no suspension panel: only a missing open blocks trading")
    if limit_up is None or limit_down is None:
        assumptions.append("price-limit rules NOT modelled for the side(s) without a limit panel")

    cols_t = ["date", "signal_date", "code", "side", "shares", "price", "amount", "commission",
              "stamp_duty", "cash_flow", "cash_before", "cash_after"]
    cols_r = ["signal_date", "exec_date", "code", "side", "shares", "value", "reason"]
    cols_p = ["date", "code", "shares", "mark_price", "market_value", "stale"]
    return BacktestResult(
        daily=pd.DataFrame(daily).set_index("date"),
        trades=pd.DataFrame(trades, columns=cols_t),
        rejections=pd.DataFrame(rejects, columns=cols_r),
        positions=pd.DataFrame(pos_rows, columns=cols_p),
        assumptions=tuple(assumptions),
    )
