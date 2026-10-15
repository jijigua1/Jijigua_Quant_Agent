"""Synthetic minute bars with hand-checkable values (end-of-interval timestamps)."""
from datetime import time

import pandas as pd

from qrtk import MinuteBarContract, SessionConfig

SESSION = SessionConfig()
CONTRACT = MinuteBarContract(timestamp_convention="end", volume_unit="share", amount_unit="CNY",
                             open_auction="separate", close_auction="separate", source="synthetic")
DAYS = pd.DatetimeIndex(["2025-01-06", "2025-01-07", "2025-01-08"])


def hm(s):
    h, m = map(int, s.split(":"))
    return pd.Timedelta(hours=h, minutes=m)


def day_bars(date, code, price=10.2, vol=100, auction=(10.0, 1000), close_auction=(10.5, 2000),
             overrides=None, drop=()):
    """Full A-share day: auction bar [09:24,09:25), 237 continuous bars, close auction
    bars [14:57,14:58) and [14:58,14:59) with zero volume and [14:59,15:00) with the match.
    Flat bars: open=high=low=close=price, amount=price*vol. overrides: {"HH:MM" bar start: dict}."""
    d = pd.Timestamp(date)
    starts = []
    if auction:
        starts.append(("09:24", auction[0], auction[1]))
    for s in SESSION.expected_bar_starts():
        starts.append((f"{s.components.hours:02d}:{s.components.minutes:02d}", price, vol))
    if close_auction:
        starts += [("14:57", price, 0), ("14:58", price, 0), ("14:59", close_auction[0], close_auction[1])]
    rows = []
    for label, p, v in starts:
        if label in drop:
            continue
        r = {"code": code, "timestamp": d + hm(label) + pd.Timedelta(minutes=1),
             "open": p, "high": p, "low": p, "close": p, "volume": v, "amount": p * v}
        if overrides and label in overrides:
            r.update(overrides[label])
        rows.append(r)
    return pd.DataFrame(rows)


def window_case(date, code="A"):
    """09:30-09:35 bars (open, close, vol); amount = vol * (open+close)/2."""
    spec = {"09:30": (10.0, 10.1, 100), "09:31": (10.1, 10.2, 200), "09:32": (10.2, 10.0, 100),
            "09:33": (10.0, 10.3, 300), "09:34": (10.3, 10.4, 100)}
    ov = {k: {"open": o, "close": c, "high": max(o, c), "low": min(o, c), "volume": v,
              "amount": v * (o + c) / 2} for k, (o, c, v) in spec.items()}
    return day_bars(date, code, overrides=ov)
