"""Execution-price rules: a daily signal from the close of T traded on session T+1.

Every rule yields, per (T+1 date, code): a price (NaN unless status == 'ok'), a status, the
time the price becomes known, optional capacity (max shares), and the rule's assumptions.

  next_open           official open (daily panel; under A-share rules the 09:25 auction price)
  first_valid_minute  open of the first continuous-session bar with volume > 0 (>= 09:30). It
                      is a continuous-trading price, generally not equal to the auction open.
  window_vwap         amount/volume over a fixed window, e.g. first 5/15/30 minutes. It is a
                      BENCHMARK / research proxy: known only after the window ends and it
                      assumes the order trades evenly through the window at no impact.
Rules are fixed in advance (see diagnostics.ResearchSpec); comparing them is sensitivity
analysis, never a way to pick the best-looking execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

from .contract import ContractError, MinuteBarContract, SessionConfig, _td
from .minute import _suspended_lookup, window_stats


@dataclass(frozen=True)
class ExecutionRule:
    name: str
    kind: str                                  # "daily_open" | "first_valid_minute" | "window_vwap"
    window: tuple[time, time] | None = None    # for window_vwap
    max_participation: float | None = None     # capacity = participation x window volume

    def __post_init__(self):
        if self.kind not in ("daily_open", "first_valid_minute", "window_vwap"):
            raise ValueError("unknown execution kind")
        if (self.kind == "window_vwap") != (self.window is not None):
            raise ValueError("window is required for (and only for) window_vwap")
        if self.max_participation is not None and not 0 < self.max_participation <= 1:
            raise ValueError("max_participation must be in (0, 1]")


NEXT_OPEN = ExecutionRule("next_open", "daily_open")
FIRST_VALID_MINUTE = ExecutionRule("first_valid_minute", "first_valid_minute")
VWAP_5 = ExecutionRule("vwap_first_5m", "window_vwap", (time(9, 30), time(9, 35)))
VWAP_15 = ExecutionRule("vwap_first_15m", "window_vwap", (time(9, 30), time(9, 45)))
VWAP_30 = ExecutionRule("vwap_first_30m", "window_vwap", (time(9, 30), time(10, 0)))


def window_vwap_rule(start: time, end: time, name: str | None = None,
                     max_participation: float | None = None) -> ExecutionRule:
    """A pre-declared fixed window VWAP rule."""
    return ExecutionRule(name or f"vwap_{start:%H%M}_{end:%H%M}", "window_vwap", (start, end),
                         max_participation)


@dataclass(frozen=True)
class ExecutionPrices:
    rule: ExecutionRule
    price: pd.DataFrame        # date x code, NaN unless status == 'ok'
    status: pd.DataFrame       # date x code strings
    known_at: pd.DataFrame     # date x code timestamps: earliest time the price is known
    exec_start: time           # orders must be decided before this time on the execution day
    capacity: pd.DataFrame | None
    adjustment: str
    assumptions: tuple


def build_execution_prices(rule: ExecutionRule, trading_days, codes, *,
                           session: SessionConfig = SessionConfig(),
                           daily_open: pd.DataFrame | None = None, daily_adjustment: str = "none",
                           bars: pd.DataFrame | None = None, contract: MinuteBarContract | None = None,
                           suspended=None) -> ExecutionPrices:
    days = pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize()
    codes = list(codes)
    status = pd.DataFrame("missing_data", index=days, columns=codes, dtype=object)
    price = pd.DataFrame(np.nan, index=days, columns=codes)
    known = pd.DataFrame(pd.NaT, index=days, columns=codes, dtype="datetime64[ns]")
    capacity = None
    is_susp = _suspended_lookup(suspended)
    notes = [f"execution rule '{rule.name}' ({rule.kind}) fixed before evaluation"]

    if rule.kind == "daily_open":
        if daily_open is None:
            raise ValueError("daily_open panel required")
        op = daily_open.reindex(index=days, columns=codes).astype(float)
        if np.isinf(op).any().any() or (op <= 0).any().any():
            raise ValueError("daily_open must be positive finite or NaN")
        match = session.open_match_time if session.open_auction else session.continuous[0][0]
        for d in days:
            for c in codes:
                if is_susp(d, c):
                    status.at[d, c] = "suspended"
                elif pd.notna(op.at[d, c]):
                    status.at[d, c], price.at[d, c] = "ok", op.at[d, c]
                    known.at[d, c] = d + _td(match)
        adjustment = daily_adjustment
        exec_start = match
        notes.append("fill at the official open price; liquidity at the open assumed unlimited")
    else:
        if bars is None or contract is None:
            raise ValueError("bars and contract required for minute-based rules")
        adjustment = contract.adjustment
        lag = pd.Timedelta(contract.availability_lag)
        if rule.kind == "first_valid_minute":
            exec_start = session.continuous[0][0]
            cont = bars[bars["session"] == "continuous"]
            groups = {k: g for k, g in cont.groupby(["trade_date", "code"], sort=False)}
            if rule.max_participation is not None:
                capacity = pd.DataFrame(np.nan, index=days, columns=codes)
            for d in days:
                for c in codes:
                    g = groups.get((d, c))
                    if is_susp(d, c):
                        status.at[d, c] = "suspended"
                    elif g is None:
                        continue
                    else:
                        t = g[g["volume_raw"] > 0]
                        if t.empty:
                            status.at[d, c] = "no_trades"
                            continue
                        status.at[d, c], price.at[d, c] = "ok", t["open"].iloc[0]
                        known.at[d, c] = t["bar_end"].iloc[0] + lag
                        if capacity is not None:
                            capacity.at[d, c] = np.floor(rule.max_participation * t["volume"].iloc[0])
            notes.append("fill at the open of the first traded continuous bar; differs from the auction open")
        else:
            start, end = rule.window
            exec_start = start
            if _td(end) > session.close_offset:
                raise ContractError("execution window must end before the close valuation")
            w = window_stats(bars, contract, session, days, codes, start, end, suspended=suspended)
            st = w.pivot(index="trade_date", columns="code", values="status").reindex(index=days, columns=codes)
            status = st.replace({"missing": "missing_data", "incomplete": "incomplete_window"}).astype(object)
            price = w.pivot(index="trade_date", columns="code", values="vwap").reindex(index=days, columns=codes).astype(float)
            price = price.where(status == "ok")
            obs = w.pivot(index="trade_date", columns="code", values="observable_at").reindex(index=days, columns=codes)
            known = obs.where(status == "ok")
            if rule.max_participation is not None:
                vol = w.pivot(index="trade_date", columns="code", values="volume").reindex(index=days, columns=codes)
                capacity = np.floor(rule.max_participation * vol.astype(float)).where(status == "ok")
            notes += [f"window VWAP {start:%H:%M}-{end:%H:%M} is a benchmark proxy: the price is known only "
                      f"after {end:%H:%M} (+lag) and assumes even participation with no market impact; "
                      "fills are not guaranteed",
                      "window must be complete (every expected bar present) or the order is rejected"]
    if capacity is not None:
        notes.append(f"capacity = floor({rule.max_participation} x bar/window volume); larger orders rejected")
    else:
        notes.append("order capacity NOT modelled")
    price.index.name = status.index.name = None
    return ExecutionPrices(rule, price, status, known, exec_start, capacity, adjustment, tuple(notes))
