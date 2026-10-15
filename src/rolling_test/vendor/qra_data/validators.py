"""Deterministic data-contract validators over date x code panels. Pure numpy; no I/O, no execution of data.

A panel is (dates: list[str YYYYMMDD], codes: list[str], fields: dict[name -> 2-D array dates x codes]).
Each check returns a list of Finding; an empty list means the check passed.
"""
from dataclasses import asdict, dataclass, field
import datetime as _dt
import re

import numpy as np

ERROR, WARNING = "error", "warning"
CODE_RE = re.compile(r"^\d{6}(\.(SH|SZ|BJ))?$")


@dataclass
class Finding:
    check: str
    severity: str
    count: int
    detail: str
    sample: list = field(default_factory=list)


@dataclass
class Panel:
    dates: list
    codes: list
    fields: dict

    def __post_init__(self):
        for name, mat in self.fields.items():
            if mat.shape != (len(self.dates), len(self.codes)):
                raise ValueError("field %s shape %s does not match axes" % (name, mat.shape))

    def get(self, name):
        return self.fields.get(name)


def _cells(mask, dates, codes, limit=5):
    idx = np.argwhere(mask)[:limit]
    return [(dates[i], codes[j]) for i, j in idx]


def _finding(check, severity, mask_or_count, detail, dates=None, codes=None):
    if isinstance(mask_or_count, np.ndarray):
        n = int(np.count_nonzero(mask_or_count))
        sample = _cells(mask_or_count, dates, codes) if n and dates is not None else []
    else:
        n, sample = int(mask_or_count), []
    return [Finding(check, severity, n, detail, sample)] if n else []


# ---------------------------------------------------------------- structure

def check_axes(p):
    out = []
    bad = [d for d in p.dates if not (len(d) == 8 and d.isdigit())]
    out += _finding("axes.date_format", ERROR, len(bad), "dates must be YYYYMMDD strings")
    out += _finding("axes.dates_unique", ERROR, len(p.dates) - len(set(p.dates)), "duplicate dates")
    out += _finding("axes.dates_sorted", ERROR, int(p.dates != sorted(p.dates)), "dates not ascending")
    out += _finding("axes.codes_unique", ERROR, len(p.codes) - len(set(p.codes)), "duplicate codes")
    out += _finding("axes.code_format", ERROR, sum(not CODE_RE.match(c) for c in p.codes), "codes must be 6 digits [+ .SH/.SZ/.BJ]")
    return out


def check_long_keys(keys):
    """keys: sequence of (date, code) from a long table; every pair must occur once."""
    seen, dup = set(), 0
    for k in keys:
        dup += k in seen
        seen.add(k)
    return _finding("keys.unique", ERROR, dup, "duplicate (date, code) rows")


# ---------------------------------------------------------------- prices and volumes

def check_ohlc(p):
    o, h, l, c = (p.get(k) for k in ("open", "high", "low", "close"))
    have = np.isfinite(c)
    out = _finding("ohlc.partial", ERROR, have != np.isfinite(o), "open missing/present inconsistently with close", p.dates, p.codes)
    with np.errstate(invalid="ignore"):
        out += _finding("ohlc.low_gt_high", ERROR, l > h + 1e-9, "low above high", p.dates, p.codes)
        out += _finding("ohlc.open_outside", ERROR, (o > h + 1e-9) | (o < l - 1e-9), "open outside [low, high]", p.dates, p.codes)
        out += _finding("ohlc.close_outside", ERROR, (c > h + 1e-9) | (c < l - 1e-9), "close outside [low, high]", p.dates, p.codes)
        out += _finding("ohlc.nonpositive", ERROR, have & (c <= 0), "non-positive close", p.dates, p.codes)
    return out


def check_volume_amount(p, *, price_per_unit=10.0):
    """price_per_unit converts amount/volume to CNY/share (lots & thousand CNY: 1000/100 = 10; shares & CNY: 1)."""
    c, v, a, h, l = (p.get(k) for k in ("close", "volume", "amount", "high", "low"))
    have = np.isfinite(c)
    out = _finding("volume.missing_with_price", ERROR, have & ~np.isfinite(v), "price without volume", p.dates, p.codes)
    with np.errstate(invalid="ignore", divide="ignore"):
        out += _finding("volume.nonpositive_with_price", WARNING, have & (v <= 0), "price with zero volume (filled price?)", p.dates, p.codes)
        out += _finding("amount.nonpositive_with_price", WARNING, have & (a <= 0), "price with zero amount", p.dates, p.codes)
        vwap = a * price_per_unit / v
        ok = have & np.isfinite(vwap) & (v > 0)
        out += _finding("units.vwap_outside_range", ERROR, ok & ((vwap > h * 1.001) | (vwap < l * 0.999)),
                        "amount/volume does not land inside [low, high]: unit mismatch", p.dates, p.codes)
    return out


# ---------------------------------------------------------------- calendar and coverage

def check_calendar(dates, exchange_days):
    span = [d for d in exchange_days if dates[0] <= d <= dates[-1]]
    missing, extra = sorted(set(span) - set(dates)), sorted(set(dates) - set(span))
    weekend = [d for d in dates if _dt.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() >= 5]
    out = []
    out += [Finding("calendar.missing_trading_days", ERROR, len(missing), "exchange days absent from data", missing[:5])] if missing else []
    out += [Finding("calendar.non_trading_dates", ERROR, len(extra), "dates that are not exchange days", extra[:5])] if extra else []
    out += [Finding("calendar.weekend_dates", ERROR, len(weekend), "weekend dates", weekend[:5])] if weekend else []
    return out


def check_coverage(p, field="close", *, max_drop=0.2):
    have = np.isfinite(p.get(field))
    per_day = have.sum(1)
    out = []
    drops = [p.dates[i] for i in range(1, len(per_day)) if per_day[i - 1] and per_day[i] < per_day[i - 1] * (1 - max_drop)]
    if drops:
        out.append(Finding("coverage.sudden_drop", ERROR, len(drops), "cross-section shrinks by more than %.0f%%" % (max_drop * 100), drops[:5]))
    empty = [p.dates[i] for i in np.flatnonzero(per_day == 0)]
    if empty:
        out.append(Finding("coverage.empty_dates", ERROR, len(empty), "dates with no observations", empty[:5]))
    return out


# ---------------------------------------------------------------- universe, listing, suspension, limits

def check_listing_bounds(p, list_dates, delist_dates, field="close"):
    """list_dates/delist_dates: {code: 'YYYYMMDD' or None}. Data outside [list, delist) is an error."""
    have = np.isfinite(p.get(field))
    d = np.array(p.dates)
    before, after, unknown = np.zeros_like(have), np.zeros_like(have), 0
    for j, code in enumerate(p.codes):
        ld, dd = list_dates.get(code), delist_dates.get(code)
        if ld is None:
            unknown += 1
            continue
        before[:, j] = have[:, j] & (d < ld)
        if dd:
            after[:, j] = have[:, j] & (d >= dd)
    out = _finding("listing.data_before_list_date", ERROR, before, "observations before listing", p.dates, p.codes)
    out += _finding("listing.data_after_delist_date", ERROR, after, "observations on/after delisting", p.dates, p.codes)
    out += _finding("listing.unknown_list_date", WARNING, unknown, "codes without a listing date")
    return out


def check_suspension(p, suspended=None):
    """Detect filled prices (close repeated with no volume) and status/price contradictions."""
    c, v = p.get("close"), p.get("volume")
    have = np.isfinite(c)
    out = []
    with np.errstate(invalid="ignore"):
        filled = np.zeros_like(have)
        filled[1:] = have[1:] & (c[1:] == c[:-1]) & ((~np.isfinite(v[1:])) | (v[1:] <= 0))
    out += _finding("suspension.filled_prices", ERROR, filled, "price carried forward on a no-volume day", p.dates, p.codes)
    if suspended is not None:
        with np.errstate(invalid="ignore"):
            out += _finding("suspension.traded_while_suspended", ERROR, suspended.astype(bool) & np.isfinite(v) & (v > 0),
                            "volume on a day flagged suspended", p.dates, p.codes)
    return out


def check_limits(p, limit_up, limit_down, tol=0.0051):
    c = p.get("close")
    ok = np.isfinite(c) & np.isfinite(limit_up) & np.isfinite(limit_down)
    with np.errstate(invalid="ignore"):
        out = _finding("limits.close_above_limit_up", ERROR, ok & (c > limit_up + tol), "close above the stated limit-up price", p.dates, p.codes)
        out += _finding("limits.close_below_limit_down", ERROR, ok & (c < limit_down - tol), "close below the stated limit-down price", p.dates, p.codes)
    return out


def check_survivorship(universe, universe_asof, window_start, ended_codes):
    """A universe snapped after the window start that drops codes which ended inside the window is biased."""
    if universe_asof <= window_start:
        return []
    dropped = sorted(set(ended_codes) - set(universe))
    return [Finding("universe.survivorship", ERROR, len(dropped), "universe as of %s omits codes that ended after %s" % (universe_asof, window_start),
                    dropped[:5])] if dropped else []


def check_frozen_tail(dates, status, min_run=5):
    """Status tables that stop changing (forward-filled) produce identical consecutive rows at the tail."""
    same = np.array([np.array_equal(status[i], status[i - 1]) for i in range(1, len(dates))])
    run = 0
    for flag in same[::-1]:
        if not flag:
            break
        run += 1
    if run >= min_run:
        return [Finding("status.frozen_tail", ERROR, run, "status identical for the last %d dates (forward-filled)" % run,
                        [dates[-run - 1], dates[-1]])]
    return []


# ---------------------------------------------------------------- adjustment and corporate actions

def check_adjustment(p, *, tiny=1e-3, exchange_preclose=None):
    c, f, ca = p.get("close"), p.get("adj_factor"), p.get("close_adj")
    out = []
    with np.errstate(invalid="ignore", divide="ignore"):
        if ca is not None:
            rel = np.abs(ca - c * f) / np.abs(c * f)
            out += _finding("adjust.product_mismatch", ERROR, np.isfinite(rel) & (rel > 1e-9), "close_adj != close*adj_factor", p.dates, p.codes)
        out += _finding("adjust.factor_missing_with_price", ERROR, np.isfinite(c) & ~np.isfinite(f), "price without factor", p.dates, p.codes)
        out += _finding("adjust.factor_nonpositive", ERROR, np.isfinite(f) & (f <= 0), "non-positive factor", p.dates, p.codes)
        ratio = np.full_like(f, np.nan)
        ratio[1:] = f[1:] / f[:-1]
        step = np.isfinite(ratio) & (np.abs(ratio - 1) > 1e-12)
        out += _finding("adjust.factor_decrease", ERROR, step & (ratio < 1 - tiny), "backward factor decreased materially (revision or rebase)", p.dates, p.codes)
        out += _finding("adjust.factor_rounding_noise", WARNING, step & (np.abs(ratio - 1) < tiny), "tiny factor steps (rounding)", p.dates, p.codes)
        # forward-adjust leakage signature: factors normalised so the LAST value is 1 and earlier values exceed it
        last = np.array([f[np.flatnonzero(np.isfinite(f[:, j]))[-1], j] if np.isfinite(f[:, j]).any() else np.nan for j in range(f.shape[1])])
        first = np.array([f[np.flatnonzero(np.isfinite(f[:, j]))[0], j] if np.isfinite(f[:, j]).any() else np.nan for j in range(f.shape[1])])
        # backward (hfq) factors start at 1 and grow; forward (qfq) factors end at 1 and are below 1 earlier
        qfq = np.isfinite(last) & (np.abs(last - 1) < 1e-9) & (first < 1 - 1e-9)
        out += _finding("adjust.forward_adjusted_lookahead", ERROR, int(qfq.sum()),
                        "factors anchored to the latest date (qfq): earlier adjusted prices depend on later events")
        if exchange_preclose is not None:
            prev = np.full_like(c, np.nan)
            prev[1:] = c[:-1]
            differs = np.isfinite(exchange_preclose) & np.isfinite(prev) & (np.abs(exchange_preclose - prev) > 0.0051)
            material = step & (np.abs(ratio - 1) >= tiny)
            out += _finding("corporate_action.event_without_factor_step", ERROR, differs & ~step, "ex-date without factor change", p.dates, p.codes)
            out += _finding("corporate_action.factor_step_without_event", WARNING, material & ~differs & np.isfinite(exchange_preclose),
                            "material factor change on a day the exchange pre-close equals the prior close", p.dates, p.codes)
            with np.errstate(invalid="ignore"):
                implied = prev / ratio
            out += _finding("corporate_action.preclose_mismatch", ERROR, differs & step & (np.abs(implied - exchange_preclose) > 0.011 + 0.002 * exchange_preclose),
                            "factor step does not reproduce the exchange pre-close", p.dates, p.codes)
    return out


def compare_snapshots(dates_old, old, dates_new, new, tol=1e-9):
    """History of an adjusted series must not change between snapshots (except appended dates)."""
    pos = {d: i for i, d in enumerate(dates_new)}
    rows = [(i, pos[d]) for i, d in enumerate(dates_old) if d in pos]
    a = old[[i for i, _ in rows]]
    b = new[[j for _, j in rows]]
    ok = np.isfinite(a) & np.isfinite(b)
    with np.errstate(invalid="ignore", divide="ignore"):
        changed = ok & (np.abs(a - b) > tol * np.abs(b))
    lost = np.isfinite(a) & ~np.isfinite(b)
    out = [Finding("version.history_rewritten", ERROR, int(changed.sum()), "historical values changed between snapshots")] if changed.any() else []
    out += [Finding("version.history_deleted", ERROR, int(lost.sum()), "historical values removed")] if lost.any() else []
    return out


# ---------------------------------------------------------------- time semantics

def check_availability(decision_times, available_times):
    """Every value used at decision time t must have become available at or before t (same length sequences)."""
    late = [(d, a) for d, a in zip(decision_times, available_times) if a is None or a > d]
    return [Finding("time.available_after_decision", ERROR, len(late), "value not yet available at decision time", late[:5])] if late else []


def check_field_semantics(requested, contract_fields, purpose="signal"):
    by_name = {f.name: f for f in contract_fields}
    out = []
    unknown = [r for r in requested if r not in by_name]
    if unknown:
        out.append(Finding("contract.unknown_field", ERROR, len(unknown), "field not in the data contract", unknown))
    if purpose == "signal":
        bad = [r for r in requested if r in by_name and not by_name[r].signal_use]
        if bad:
            out.append(Finding("contract.not_for_signal", ERROR, len(bad), "future or unreliable field requested as a signal input", bad))
    rejected = [r for r in requested if r in by_name and by_name[r].status == "REJECTED"]
    if rejected:
        out.append(Finding("contract.rejected_field", ERROR, len(rejected), "field rejected by certification", rejected))
    return out


def check_label_maturity(dates, labels, horizon, lag, data_end, cutoff=None):
    """A label at T needs exit date T+lag+horizon <= min(data_end, cutoff); immature labels must be missing."""
    end = min(data_end, cutoff) if cutoff else data_end
    pos_end = max(i for i, d in enumerate(dates) if d <= end)
    immature = np.zeros_like(labels, dtype=bool)
    for i in range(len(dates)):
        if i + lag + horizon > pos_end:
            immature[i] = np.isfinite(labels[i])
    return _finding("label.immature", ERROR, immature, "label present before its exit date has occurred", dates, list(range(labels.shape[1])))


def check_cross_source(a, b, *, rel_tol=1e-6, name="close"):
    ok = np.isfinite(a) & np.isfinite(b)
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = ok & (np.abs(a - b) > rel_tol * np.maximum(1, np.abs(b)))
    out = [Finding("cross_source.%s_mismatch" % name, ERROR, int(diff.sum()), "values differ between sources")] if diff.any() else []
    one_sided = np.isfinite(a) != np.isfinite(b)
    out += [Finding("cross_source.%s_presence" % name, WARNING, int(one_sided.sum()), "present in one source only")] if one_sided.any() else []
    return out


def check_budget(n_dates, n_codes, n_fields, *, max_cells, itemsize=8, max_bytes=None):
    cells = n_dates * n_codes * n_fields
    out = _finding("budget.cells", ERROR, int(cells > max_cells), "request of %d cells exceeds %d" % (cells, max_cells))
    if max_bytes is not None:
        out += _finding("budget.bytes", ERROR, int(cells * itemsize > max_bytes), "request exceeds memory budget")
    return out


def summarize(findings):
    errors = [f for f in findings if f.severity == ERROR]
    return {"passed": not errors, "errors": len(errors), "warnings": len(findings) - len(errors),
            "findings": [asdict(f) for f in findings]}
