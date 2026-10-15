"""Market data contract: declared units, timestamps, sessions and availability.

Nothing here guesses a vendor's format. Every ambiguous property (timestamp = bar start or bar
end, volume unit, amount unit, how auctions are represented) must be declared; 'unknown' units
are allowed for OHLC work but any VWAP/volume computation refuses them.

Five different times are kept apart:
  data time        the interval a bar describes          bar_start .. bar_end
  available time   when the bar can be used              available_at = bar_end + availability_lag
  signal time      when a daily signal is produced       after the close of T (+ daily lag)
  execution time   when an order may trade               a window on the next session, T+1
  price window     data needed to compute the fill price the execution rule's window
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta

import numpy as np
import pandas as pd

VOLUME_UNITS = {"share": 1.0, "lot100": 100.0, "unknown": np.nan}
AMOUNT_UNITS = {"CNY": 1.0, "thousand_CNY": 1000.0, "unknown": np.nan}
ADJUSTMENTS = ("none", "forward", "backward")


class ContractError(ValueError):
    """Raised when data or a request is incompatible with the declared contract."""


def _td(t: time) -> pd.Timedelta:
    return pd.Timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)


@dataclass(frozen=True)
class SessionConfig:
    """Trading sessions of one exchange day, local time, half-open intervals [start, end).

    Defaults describe the current A-share layout as a configuration, not a historical fact:
    opening call auction 09:15-09:25 (match at 09:25, no trading until 09:30), continuous
    09:30-11:30 and 13:00-14:57, closing call auction 14:57-15:00. Periods without a closing
    auction (e.g. SSE before Aug 2018) need close_auction=None and continuous ending 15:00."""
    timezone: str = "Asia/Shanghai"
    continuous: tuple = ((time(9, 30), time(11, 30)), (time(13, 0), time(14, 57)))
    open_auction: tuple | None = (time(9, 15), time(9, 30))
    close_auction: tuple | None = (time(14, 57), time(15, 0))
    open_match_time: time = time(9, 25)
    bar_minutes: int = 1

    def __post_init__(self):
        prev = pd.Timedelta(0)
        for s, e in self.continuous:
            if not _td(s) < _td(e) or _td(s) < prev:
                raise ContractError("continuous sessions must be increasing, non-overlapping")
            if (_td(e) - _td(s)) % pd.Timedelta(minutes=self.bar_minutes):
                raise ContractError("session length must be a multiple of bar_minutes")
            prev = _td(e)

    def windows(self) -> list[tuple[str, pd.Timedelta, pd.Timedelta]]:
        out = []
        if self.open_auction:
            out.append(("open_auction", _td(self.open_auction[0]), _td(self.open_auction[1])))
        out += [("continuous", _td(s), _td(e)) for s, e in self.continuous]
        if self.close_auction:
            out.append(("close_auction", _td(self.close_auction[0]), _td(self.close_auction[1])))
        return out

    def expected_bar_starts(self) -> list[pd.Timedelta]:
        """Start offsets (from midnight) of every continuous-session bar."""
        step = pd.Timedelta(minutes=self.bar_minutes)
        out = []
        for s, e in self.continuous:
            t = _td(s)
            while t < _td(e):
                out.append(t)
                t += step
        return out

    @property
    def close_offset(self) -> pd.Timedelta:
        return _td(self.close_auction[1]) if self.close_auction else _td(self.continuous[-1][1])

    @property
    def open_offset(self) -> pd.Timedelta:
        return _td(self.continuous[0][0])


@dataclass(frozen=True)
class MinuteBarContract:
    """What a minute-bar source means. All fields without defaults must be declared."""
    timestamp_convention: str          # "start" | "end" of the bar interval
    volume_unit: str                   # "share" | "lot100" | "unknown"
    amount_unit: str                   # "CNY" | "thousand_CNY" | "unknown"
    open_auction: str                  # "separate" (own bar(s) in the auction window) | "merged" | "absent"
    close_auction: str                 # "separate" | "absent"
    adjustment: str = "none"           # "none" | "forward" | "backward"
    timezone: str = "Asia/Shanghai"    # zone of naive timestamps
    price_unit: str = "CNY"
    bar_minutes: int = 1
    availability_lag: timedelta = timedelta(0)
    source: str = "unspecified"

    def __post_init__(self):
        checks = [("timestamp_convention", ("start", "end")), ("volume_unit", tuple(VOLUME_UNITS)),
                  ("amount_unit", tuple(AMOUNT_UNITS)), ("open_auction", ("separate", "merged", "absent")),
                  ("close_auction", ("separate", "absent")), ("adjustment", ADJUSTMENTS)]
        for name, allowed in checks:
            if getattr(self, name) not in allowed:
                raise ContractError(f"{name} must be one of {allowed}")
        if self.price_unit != "CNY":
            raise ContractError("only price_unit='CNY' is supported")

    @property
    def units_known(self) -> bool:
        return self.volume_unit != "unknown" and self.amount_unit != "unknown"


@dataclass(frozen=True)
class DailyBarContract:
    """What a daily-bar source means."""
    volume_unit: str
    amount_unit: str
    adjustment: str = "none"
    availability_lag: timedelta = timedelta(0)   # after the session close
    source: str = "unspecified"

    def __post_init__(self):
        if self.volume_unit not in VOLUME_UNITS or self.amount_unit not in AMOUNT_UNITS:
            raise ContractError("unknown volume_unit/amount_unit value")
        if self.adjustment not in ADJUSTMENTS:
            raise ContractError(f"adjustment must be one of {ADJUSTMENTS}")


def _issue_frame(df: pd.DataFrame, mask, issue: str, detail: str = "") -> pd.DataFrame:
    cols = [c for c in ("code", "timestamp", "trade_date") if c in df]
    return df.loc[mask, cols].assign(issue=issue, detail=detail)


ISSUE_COLUMNS = ["code", "timestamp", "trade_date", "issue", "detail"]


def normalize_minute_bars(raw: pd.DataFrame, contract: MinuteBarContract, session: SessionConfig,
                          trading_days) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Standardise a long minute table and log every data-quality problem.

    raw columns: code, timestamp, open, high, low, close, volume, amount (vendor units).
    Returns (bars, issues). bars: code, trade_date, bar_start, bar_end, available_at, session,
    open, high, low, close, volume_raw, volume (shares), amount (CNY); local naive times.
    Dropped bars (non-trading day, outside session, bad values, conflicting duplicates) appear
    only in issues; kept-but-suspicious bars are flagged there too."""
    if contract.bar_minutes != session.bar_minutes:
        raise ContractError("contract and session bar_minutes differ")
    req = ["code", "timestamp", "open", "high", "low", "close", "volume", "amount"]
    miss = [c for c in req if c not in raw]
    if miss:
        raise ContractError(f"missing columns {miss}")
    days = pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize()
    df = raw[req].copy().reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    ts = pd.to_datetime(df["timestamp"])
    ts = ts.dt.tz_localize(contract.timezone) if ts.dt.tz is None else ts
    ts = ts.dt.tz_convert(session.timezone).dt.tz_localize(None)
    step = pd.Timedelta(minutes=contract.bar_minutes)
    df["bar_start"] = ts if contract.timestamp_convention == "start" else ts - step
    df["bar_end"] = df["bar_start"] + step
    df["trade_date"] = df["bar_start"].dt.normalize()
    issues = []

    back = df.groupby("code", sort=False)["bar_start"].diff() < pd.Timedelta(0)
    if back.any():
        issues.append(_issue_frame(df, back, "out_of_order", "input not sorted; re-sorted"))

    bad_day = ~df["trade_date"].isin(days)
    issues.append(_issue_frame(df, bad_day, "not_trading_day", "dropped"))
    df = df[~bad_day]

    s_off, e_off = df["bar_start"] - df["trade_date"], df["bar_end"] - df["trade_date"]
    df["session"] = None
    for name, ws, we in session.windows():
        df.loc[(s_off >= ws) & (e_off <= we), "session"] = name
    outside = df["session"].isna()
    issues.append(_issue_frame(df, outside, "outside_session", "dropped; check timestamp_convention"))
    df = df[~outside]
    for name, declared in (("open_auction", contract.open_auction), ("close_auction", contract.close_auction)):
        if declared != "separate":
            m = df["session"] == name
            issues.append(_issue_frame(df, m, "undeclared_auction_bar", f"{name} bar but contract says {declared}"))

    vals = df[["open", "high", "low", "close", "volume", "amount"]]
    nonfinite = ~np.isfinite(vals).all(axis=1)
    issues.append(_issue_frame(df, nonfinite, "nan_or_inf", "dropped"))
    df = df[~nonfinite]
    px = df[["open", "high", "low", "close"]]
    nonpos = (px <= 0).any(axis=1)
    issues.append(_issue_frame(df, nonpos, "nonpositive_price", "dropped"))
    df = df[~nonpos]
    incons = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    issues.append(_issue_frame(df, incons, "ohlc_inconsistent", "dropped"))
    df = df[~incons]
    neg = (df["volume"] < 0) | (df["amount"] < 0)
    issues.append(_issue_frame(df, neg, "negative_volume_or_amount", "dropped"))
    df = df[~neg]

    key = ["code", "bar_start"]
    dup = df.duplicated(key, keep=False)
    if dup.any():
        vcols = ["open", "high", "low", "close", "volume", "amount"]
        n_versions = df[dup].groupby(key)[vcols].nunique().max(axis=1)
        conflict_keys = set(n_versions[n_versions > 1].index)
        is_conflict = pd.Series([k in conflict_keys for k in zip(df["code"], df["bar_start"])], index=df.index)
        issues.append(_issue_frame(df, dup & is_conflict, "duplicate_conflict", "all copies dropped"))
        issues.append(_issue_frame(df, dup & ~is_conflict & df.duplicated(key), "duplicate_identical", "extra copy dropped"))
        df = df[~(dup & is_conflict) & ~(dup & ~is_conflict & df.duplicated(key))]

    mism = ((df["volume"] == 0) & (df["amount"] > 0)) | ((df["volume"] > 0) & (df["amount"] == 0))
    issues.append(_issue_frame(df, mism, "volume_amount_mismatch", "kept"))
    df = df.rename(columns={"volume": "volume_raw"})
    df["volume"] = df["volume_raw"] * VOLUME_UNITS[contract.volume_unit]
    df["amount"] = df.pop("amount") * AMOUNT_UNITS[contract.amount_unit]
    if contract.units_known:
        traded = (df["volume"] > 0) & (df["amount"] > 0)
        bv = df["amount"] / df["volume"]
        out = traded & ((bv < df["low"] * (1 - 1e-4)) | (bv > df["high"] * (1 + 1e-4)))
        issues.append(_issue_frame(df, out, "bar_vwap_outside_range", "amount/volume outside [low, high]; check units"))
    df["available_at"] = df["bar_end"] + pd.Timedelta(contract.availability_lag)
    bars = df.sort_values(key, kind="mergesort")[
        ["code", "trade_date", "bar_start", "bar_end", "available_at", "session",
         "open", "high", "low", "close", "volume_raw", "volume", "amount"]].reset_index(drop=True)
    issue_df = pd.concat([i for i in issues if len(i)], ignore_index=True) if any(len(i) for i in issues) \
        else pd.DataFrame(columns=ISSUE_COLUMNS)
    return bars, issue_df.reindex(columns=ISSUE_COLUMNS)


def normalize_daily_bars(raw: pd.DataFrame, contract: DailyBarContract, trading_days,
                         session: SessionConfig = SessionConfig()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Standardise a long daily table: trade_date, code, open, high, low, close, volume, amount.

    Units converted to shares / CNY (NaN when declared unknown); available_at = close + lag."""
    req = ["trade_date", "code", "open", "high", "low", "close", "volume", "amount"]
    miss = [c for c in req if c not in raw]
    if miss:
        raise ContractError(f"missing columns {miss}")
    df = raw[req].copy().reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="mixed").dt.normalize()
    for c in req[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    days = pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize()
    df["timestamp"] = df["trade_date"]
    issues = []
    bad_day = ~df["trade_date"].isin(days)
    issues.append(_issue_frame(df, bad_day, "not_trading_day", "dropped"))
    df = df[~bad_day]
    px = df[["open", "high", "low", "close"]]
    bad = (~np.isfinite(px).all(axis=1)) | (px <= 0).any(axis=1)
    issues.append(_issue_frame(df, bad, "invalid_price", "dropped"))
    df = df[~bad]
    incons = (df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    issues.append(_issue_frame(df, incons, "ohlc_inconsistent", "dropped"))
    df = df[~incons]
    dup = df.duplicated(["trade_date", "code"], keep=False)
    issues.append(_issue_frame(df, dup, "duplicate", "all copies dropped"))
    df = df[~dup]
    df["volume"] = df["volume"] * VOLUME_UNITS[contract.volume_unit]
    df["amount"] = df["amount"] * AMOUNT_UNITS[contract.amount_unit]
    df["available_at"] = df["trade_date"] + session.close_offset + pd.Timedelta(contract.availability_lag)
    issue_df = pd.concat([i for i in issues if len(i)], ignore_index=True) if any(len(i) for i in issues) \
        else pd.DataFrame(columns=ISSUE_COLUMNS)
    return (df.drop(columns="timestamp").sort_values(["trade_date", "code"]).reset_index(drop=True),
            issue_df.reindex(columns=ISSUE_COLUMNS))


def to_panel(long_df: pd.DataFrame, field: str, trading_days=None, codes=None,
             ok_only: bool = True) -> pd.DataFrame:
    """Long (trade_date, code, ...) table -> wide date x code panel.

    With ok_only and a 'status' column, rows whose status is not 'ok' become NaN."""
    df = long_df
    if ok_only and "status" in df:
        df = df[df["status"] == "ok"]
    out = df.pivot(index="trade_date", columns="code", values=field)
    if trading_days is not None:
        out = out.reindex(pd.DatetimeIndex(pd.to_datetime(trading_days)).normalize())
    if codes is not None:
        out = out.reindex(columns=list(codes))
    out.index.name, out.columns.name = None, None
    return out
