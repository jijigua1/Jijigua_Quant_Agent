"""Minute bars -> daily bars and fixed intraday-window features.

Input is the output of contract.normalize_minute_bars (standard units, local naive times).

Conventions:
  * Only bars with volume_raw > 0 carry trade prices; zero-volume bars count for coverage
    but never set open/high/low/close (vendors often fill them with a stale price).
  * VWAP = sum(amount CNY) / sum(volume shares). Undeclared units -> ContractError; a VWAP
    outside [low, high] -> NaN with vwap_status='unit_inconsistent'. No price averages.
  * Coverage counts continuous-session bars present / expected; auctions are not counted.
  * Status (one per trade_date x code), in priority order:
      suspended        flagged by the caller's suspension input (minute data alone cannot tell)
      missing          no bars at all and not flagged suspended
      no_trades        bars exist but every included bar has zero volume
      truncated_as_of  as_of is before the day's close availability
      truncated_feed   coverage below min_coverage and every missing bar is after the last bar
      incomplete       coverage below min_coverage otherwise
      ok
    Values are still reported for truncated/incomplete rows; to_panel(ok_only=True) drops them.
"""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

from .contract import ContractError, MinuteBarContract, SessionConfig, _td

DAILY_COLUMNS = ["trade_date", "code", "open", "high", "low", "close", "volume", "amount", "vwap",
                 "vwap_status", "n_expected", "n_present", "n_zero_volume", "coverage",
                 "open_source", "close_source", "status", "available_at"]


def _suspended_lookup(suspended):
    if suspended is None:
        return lambda d, c: False
    if isinstance(suspended, pd.DataFrame):
        return lambda d, c: bool(suspended.at[d, c]) if (d in suspended.index and c in suspended.columns
                                                         and pd.notna(suspended.at[d, c])) else False
    s = set((pd.Timestamp(d).normalize(), c) for d, c in suspended)
    return lambda d, c: (d, c) in s


def _trade_summary(g: pd.DataFrame, units_known: bool) -> dict:
    t = g[g["volume_raw"] > 0]
    if t.empty:
        return {}
    out = {"open": t["open"].iloc[0], "high": t["high"].max(), "low": t["low"].min(),
           "close": t["close"].iloc[-1], "first_session": t["session"].iloc[0],
           "last_session": t["session"].iloc[-1]}
    if units_known:
        vol, amt = t["volume"].sum(), t["amount"].sum()
        vwap = amt / vol if vol > 0 else np.nan
        ok = np.isfinite(vwap) and out["low"] * (1 - 1e-6) <= vwap <= out["high"] * (1 + 1e-6)
        out.update(volume=vol, amount=amt, vwap=vwap if ok else np.nan,
                   vwap_status="ok" if ok else "unit_inconsistent")
    else:
        out.update(volume=np.nan, amount=np.nan, vwap=np.nan, vwap_status="units_unknown")
    return out


def _require_units(contract: MinuteBarContract, allow_unknown: bool):
    if not contract.units_known and not allow_unknown:
        raise ContractError("volume/amount units undeclared: refuse VWAP/volume; "
                            "declare units or pass allow_unknown_units=True for OHLC only")


def aggregate_daily(bars: pd.DataFrame, contract: MinuteBarContract, session: SessionConfig,
                    trading_days, codes, *, include_open_auction: bool = True,
                    include_close_auction: bool = True, min_coverage: float = 0.95,
                    suspended=None, as_of=None, allow_unknown_units: bool = False) -> pd.DataFrame:
    """One row per trading day x code (rows exist even with no data, carrying a status)."""
    _require_units(contract, allow_unknown_units)
    if not 0 < min_coverage <= 1:
        raise ValueError("min_coverage must be in (0, 1]")
    days = pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize()
    if as_of is not None:
        as_of = pd.Timestamp(as_of)
        bars = bars[bars["available_at"] <= as_of]
    keep = {"continuous"}
    if include_open_auction:
        keep.add("open_auction")
    if include_close_auction:
        keep.add("close_auction")
    bars = bars[bars["session"].isin(keep)]
    groups = {k: g for k, g in bars.groupby(["trade_date", "code"], sort=False)}
    expected = session.expected_bar_starts()
    is_susp = _suspended_lookup(suspended)
    lag = pd.Timedelta(contract.availability_lag)
    rows = []
    for d in days:
        close_at = d + session.close_offset + lag
        for c in codes:
            g = groups.get((d, c))
            row = {"trade_date": d, "code": c, "n_expected": len(expected), "available_at": close_at}
            cont = g[g["session"] == "continuous"] if g is not None else None
            n_present = 0 if cont is None else cont["bar_start"].nunique()
            row.update(n_present=n_present, coverage=n_present / len(expected),
                       n_zero_volume=0 if g is None else int((g["volume_raw"] == 0).sum()))
            summ = {} if g is None else _trade_summary(g, contract.units_known)
            if is_susp(d, c):
                row["status"] = "suspended"
                summ = {}
            elif g is None:
                row["status"] = "missing"
            elif not summ:
                row["status"] = "no_trades"
            elif as_of is not None and as_of < close_at:
                row["status"] = "truncated_as_of"
            elif row["coverage"] < min_coverage:
                present = set(cont["bar_start"] - d)
                missing = [e for e in expected if e not in present]
                last = max(present) if present else pd.Timedelta(0)
                row["status"] = "truncated_feed" if all(m > last for m in missing) else "incomplete"
            else:
                row["status"] = "ok"
            if summ:
                fs, ls = summ.pop("first_session"), summ.pop("last_session")
                row["open_source"] = ("open_auction" if fs == "open_auction" else
                                      "merged_first_bar" if contract.open_auction == "merged" else
                                      "first_continuous_trade")
                row["close_source"] = "close_auction" if ls == "close_auction" else "last_continuous_trade"
                row.update(summ)
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=DAILY_COLUMNS)


WINDOW_COLUMNS = ["trade_date", "code", "first_open", "last_close", "vwap", "volume", "amount",
                  "ret", "vol_1min", "n_expected", "n_present", "status", "window_start",
                  "window_end", "observable_at"]


def window_bars(session: SessionConfig, start: time, end: time) -> list[pd.Timedelta]:
    """Expected continuous bar starts whose whole interval lies in [start, end)."""
    if not _td(start) < _td(end):
        raise ValueError("window start must be before end")
    step = pd.Timedelta(minutes=session.bar_minutes)
    out = [s for s in session.expected_bar_starts() if _td(start) <= s and s + step <= _td(end)]
    if not out:
        raise ValueError("window contains no continuous-session bar")
    return out


def window_stats(bars: pd.DataFrame, contract: MinuteBarContract, session: SessionConfig,
                 trading_days, codes, start: time, end: time, *, require_complete: bool = True,
                 min_coverage: float = 1.0, suspended=None) -> pd.DataFrame:
    """Features of the fixed local window [start, end) on each day (continuous bars only).

    vwap = amount/volume; ret = last traded close / first traded open - 1; vol_1min = sample std
    of 1-minute log returns (first term log(close/open) of the first traded bar), not annualised.
    observable_at = window end + availability lag: no value is usable before that."""
    _require_units(contract, False)
    expected = window_bars(session, start, end)
    days = pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize()
    lo, hi = _td(start), _td(end)
    b = bars[bars["session"] == "continuous"]
    off = b["bar_start"] - b["trade_date"]
    b = b[(off >= lo) & (off + pd.Timedelta(minutes=session.bar_minutes) <= hi)]
    groups = {k: g for k, g in b.groupby(["trade_date", "code"], sort=False)}
    is_susp = _suspended_lookup(suspended)
    need = 1.0 if require_complete else min_coverage
    rows = []
    for d in days:
        for c in codes:
            g = groups.get((d, c))
            row = {"trade_date": d, "code": c, "n_expected": len(expected),
                   "n_present": 0 if g is None else g["bar_start"].nunique(),
                   "window_start": d + lo, "window_end": d + hi,
                   "observable_at": d + hi + pd.Timedelta(contract.availability_lag)}
            t = None if g is None else g[g["volume_raw"] > 0]
            if is_susp(d, c):
                row["status"] = "suspended"
            elif g is None:
                row["status"] = "missing"
            elif t.empty:
                row["status"] = "no_trades"
            elif row["n_present"] / len(expected) < need:
                row["status"] = "incomplete"
            else:
                vol, amt = t["volume"].sum(), t["amount"].sum()
                vwap = amt / vol
                if not t["low"].min() * (1 - 1e-6) <= vwap <= t["high"].max() * (1 + 1e-6):
                    row["status"] = "unit_inconsistent"
                else:
                    lr = np.log(np.r_[t["close"].iloc[0] / t["open"].iloc[0],
                                      t["close"].to_numpy()[1:] / t["close"].to_numpy()[:-1]])
                    row.update(status="ok", first_open=t["open"].iloc[0], last_close=t["close"].iloc[-1],
                               vwap=vwap, volume=vol, amount=amt,
                               ret=t["close"].iloc[-1] / t["open"].iloc[0] - 1,
                               vol_1min=float(np.std(lr, ddof=1)) if len(lr) > 1 else np.nan)
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=WINDOW_COLUMNS)
