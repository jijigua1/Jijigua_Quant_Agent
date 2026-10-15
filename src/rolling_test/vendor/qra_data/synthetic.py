"""Small synthetic A-share panel with deliberately planted defects (synthetic only, never market evidence).

Clean baseline: 30 exchange days (weekdays from 2024-01-02), 6 codes, lots/thousand-CNY units, hfq factors.
Planted cases (each returned separately so a test proves the matching validator fires):
  corporate_action  B 10-for-10 bonus on day 10 (raw halves, factor doubles, exchange pre-close halves)
  qfq_leak          forward-adjusted factors anchored to the last day
  suspension        C suspended days 12-15 (missing), plus a 'filled' variant repeating the close with zero volume
  delisting         D delists after day 20; a bad variant keeps quoting after delisting
  listing           E lists on day 8; a bad variant has quotes before listing
  ohlc              one high < low
  unit              one day of amount in CNY instead of thousand CNY
  frozen_status     status identical for the last 8 days while E is actually suspended
  availability      a value published after the decision time
  maturity          a 5-day label filled for the last 3 dates
  calendar          a weekend date and a missing exchange day
  cross_source      a second source with one different close
  survivorship      universe snapped at the end, omitting delisted D
  history_rewrite   a later snapshot that rescales part of the adjusted history
  duplicate_rows    a long table with one repeated (date, code)
"""
import datetime as dt

import numpy as np

from .validators import Panel

CODES = ["000001.SZ", "600000.SH", "300750.SZ", "000005.SZ", "688981.SH", "601318.SH"]
A, B, C, D, E, F = range(6)


def exchange_days(n=30, start=dt.date(2024, 1, 2)):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d += dt.timedelta(days=1)
    return days


def clean(seed=7):
    rng = np.random.default_rng(seed)
    dates = exchange_days()
    n, m = len(dates), len(CODES)
    ret = rng.normal(0, 0.01, (n, m))
    close = 10 * np.exp(np.cumsum(ret, axis=0))
    open_ = close * (1 + rng.normal(0, 0.002, (n, m)))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, (n, m))))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, (n, m))))
    volume = rng.integers(10_000, 50_000, (n, m)).astype(float)            # lots
    vwap = (low + high) / 2
    amount = vwap * volume * 100 / 1000                                      # thousand CNY
    factor = np.ones((n, m))
    for arr in (open_, high, low, close):
        np.round(arr, 2, out=arr)
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])
    amount = np.clip(amount, low * volume * 0.1 * 1.0001, high * volume * 0.1 * 0.9999)
    fields = dict(open=open_, high=high, low=low, close=close, volume=volume, amount=amount, adj_factor=factor)
    fields["close_adj"] = close * factor
    listed = {c: "20000101" for c in CODES}
    delisted = {c: None for c in CODES}
    status = np.ones((n, m), dtype=bool)
    return Panel(dates, list(CODES), fields), dict(list_dates=listed, delist_dates=delisted, status=status,
                                                   exchange_days=dates, preclose=_preclose(close))


def _preclose(close):
    pre = np.full_like(close, np.nan)
    pre[1:] = close[:-1]
    return pre


def _copy(p):
    return Panel(list(p.dates), list(p.codes), {k: v.copy() for k, v in p.fields.items()})


def corporate_action():
    p, meta = clean()
    k = 10
    for name in ("open", "high", "low", "close"):
        p.fields[name][k:, B] = np.round(p.fields[name][k:, B] / 2, 2)
    p.fields["volume"][k:, B] *= 2
    lo, hi, vol = p.fields["low"][k:, B], p.fields["high"][k:, B], p.fields["volume"][k:, B]
    p.fields["amount"][k:, B] = np.clip(p.fields["amount"][k:, B], lo * vol * 0.1 * 1.0001, hi * vol * 0.1 * 0.9999)
    p.fields["adj_factor"][k:, B] = 2.0
    p.fields["close_adj"] = p.fields["close"] * p.fields["adj_factor"]
    pre = _preclose(p.fields["close"])
    pre[k, B] = round(p.fields["close"][k - 1, B] / 2, 2)     # exchange pre-close on the ex-date
    meta["preclose"] = pre
    return p, meta


def qfq_leak():
    p, meta = corporate_action()
    f = p.fields["adj_factor"]
    p.fields["adj_factor"] = f / f[-1]                          # anchored to the latest date: uses the future
    p.fields["close_adj"] = p.fields["close"] * p.fields["adj_factor"]
    return p, meta


def suspension(filled=False):
    p, meta = clean()
    rows = slice(12, 16)
    if filled:
        last = p.fields["close"][11, C]
        for name in ("open", "high", "low", "close"):
            p.fields[name][rows, C] = last
        p.fields["volume"][rows, C] = 0.0
        p.fields["amount"][rows, C] = 0.0
    else:
        for name in p.fields:
            p.fields[name][rows, C] = np.nan
    return p, meta


def delisting(bad=False):
    p, meta = clean()
    meta["delist_dates"][CODES[D]] = p.dates[21]
    if not bad:
        for name in p.fields:
            p.fields[name][21:, D] = np.nan
    return p, meta


def listing(bad=False):
    p, meta = clean()
    meta["list_dates"][CODES[E]] = p.dates[8]
    if not bad:
        for name in p.fields:
            p.fields[name][:8, E] = np.nan
    return p, meta


def ohlc_violation():
    p, meta = clean()
    p.fields["high"][5, A] = p.fields["low"][5, A] - 0.05
    return p, meta


def unit_error():
    p, meta = clean()
    p.fields["amount"][7, :] *= 1000                            # CNY instead of thousand CNY
    return p, meta


def frozen_status():
    p, meta = suspension()
    status = np.ones((len(p.dates), len(p.codes)), dtype=bool)
    status[12:16, C] = False
    status[-8:] = status[-9]                                     # forward-filled tail
    p.fields["volume"][-5:, E] = np.nan                          # E actually stops trading
    for name in ("open", "high", "low", "close", "amount", "adj_factor", "close_adj"):
        p.fields[name][-5:, E] = np.nan
    meta["status"] = status
    return p, meta


def availability():
    decisions = ["2024-01-10T15:00", "2024-01-11T15:00", "2024-01-12T15:00"]
    published = ["2024-01-10T15:30", "2024-01-11T14:00", None]   # first arrives late, third never published
    return decisions, published


def maturity(horizon=5, lag=1):
    p, _ = clean()
    c = p.fields["close"]
    label = np.full_like(c, np.nan)
    n = len(p.dates)
    for i in range(n):
        if i + lag + horizon < n:
            label[i] = c[i + lag + horizon] / c[i + lag] - 1
    label[-3:] = 0.01                                            # filled although the exit day has not happened
    return p, label


def calendar_defects():
    p, meta = clean()
    days = list(meta["exchange_days"])
    dates = list(p.dates)
    dates[3] = "20240106"                                        # a Saturday replaces an exchange day
    return dates, days


def cross_source():
    p, _ = clean()
    other = p.fields["close"].copy()
    other[4, F] += 0.10
    return p.fields["close"], other


def survivorship():
    p, meta = delisting()
    ended = [CODES[D]]
    universe_at_end = [c for c in CODES if c != CODES[D]]
    return universe_at_end, p.dates[-1], p.dates[0], ended


def history_rewrite():
    p, _ = corporate_action()
    old = p.fields["close_adj"].copy()
    new = old.copy()
    new[:5, A] *= 1.02                                           # a later snapshot rescales early history
    return p.dates, old, p.dates, new


def duplicate_rows():
    p, _ = clean()
    keys = [(d, c) for d in p.dates for c in p.codes]
    keys.append(keys[17])
    return keys
