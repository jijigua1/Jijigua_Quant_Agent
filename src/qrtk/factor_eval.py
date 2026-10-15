"""Daily cross-sectional factor evaluation on wide panels (index = trading dates, columns = codes).

Time semantics (see METHODOLOGY.md):
  * factor[t]        observable after the close of signal date t.
  * universe[t]      membership known at t; applied BEFORE ranking.
  * forward return   price[t+lag+h] / price[t+lag] - 1 on the price panel's own calendar
                     (default lag=1: enter at the next session's price, hold h sessions).
  * direction        fixed a priori (+1 larger is better, -1 smaller is better); never chosen
                     from the evaluated sample. Use `choose_direction` on matured training labels.
All functions are pure: no file I/O, no global state, inputs are never mutated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _check_panel(df: pd.DataFrame, name: str) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{name} must be a DataFrame")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(f"{name}: index must be a DatetimeIndex")
    if df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError(f"{name}: dates must be unique and increasing")
    if df.columns.has_duplicates:
        raise ValueError(f"{name}: duplicate codes")


def forward_returns(price: pd.DataFrame, horizon: int = 1, lag: int = 1) -> pd.DataFrame:
    """Return earned by a signal at row t: enter at row t+lag, exit at row t+lag+horizon.

    Shifts are positional on `price`'s calendar, so `price` must contain every trading date.
    Missing entry/exit prices stay NaN (suspension, delisting, end of sample)."""
    _check_panel(price, "price")
    if horizon < 1 or lag < 0:
        raise ValueError("horizon must be >= 1 and lag >= 0")
    p = price.astype(float)
    if (p <= 0).any().any():
        raise ValueError("price must be positive or NaN")
    return p.shift(-(lag + horizon)) / p.shift(-lag) - 1


def label_exit_dates(calendar: pd.DatetimeIndex, horizon: int = 1, lag: int = 1) -> pd.Series:
    """Date on which the label of each signal date becomes known (its exit price date)."""
    s = pd.Series(calendar, index=calendar)
    return s.shift(-(lag + horizon))


def valid_mask(factor: pd.DataFrame, universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """Stocks that enter the cross-section at t: in the universe at t and with a finite factor."""
    _check_panel(factor, "factor")
    m = np.isfinite(factor.astype(float))
    if universe is not None:
        _check_panel(universe, "universe")
        u = universe.reindex(index=factor.index, columns=factor.columns)
        if not u.isin([True, False, 0, 1]).where(u.notna(), True).all().all():
            raise ValueError("universe must be bool/0/1/NaN")
        m &= u.fillna(False).astype(bool)
    return m


def cross_sectional_corr(x: pd.DataFrame, y: pd.DataFrame, method: str = "pearson",
                         min_obs: int = 10) -> pd.Series:
    """Per-date correlation over stocks where both x and y are finite.

    NaN when fewer than `min_obs` pairs or either side is constant (never reported as 0)."""
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be 'pearson' or 'spearman'")
    y = y.reindex(index=x.index, columns=x.columns)
    both = x.notna() & y.notna()
    a, b = x.where(both).astype(float), y.where(both).astype(float)
    if method == "spearman":
        a, b = a.rank(axis=1), b.rank(axis=1)  # average ranks for ties
    da, db = a.sub(a.mean(axis=1), axis=0), b.sub(b.mean(axis=1), axis=0)
    corr = (da * db).sum(axis=1) / np.sqrt((da ** 2).sum(axis=1) * (db ** 2).sum(axis=1))
    constant = (a.max(axis=1) == a.min(axis=1)) | (b.max(axis=1) == b.min(axis=1))
    corr[(both.sum(axis=1) < min_obs) | constant] = np.nan
    return corr.rename(method)


def ic_summary(ic: pd.Series) -> dict:
    """Mean, sample std, non-annualised ICIR, positive ratio over valid dates."""
    v = ic.dropna()
    std = v.std(ddof=1) if len(v) > 1 else np.nan
    return {
        "mean": float(v.mean()) if len(v) else np.nan,
        "std": float(std),
        "icir": float(v.mean() / std) if len(v) > 1 and std > 0 else np.nan,
        "positive_ratio": float((v > 0).mean()) if len(v) else np.nan,
        "n_dates": int(len(v)),
    }


def assign_groups(factor: pd.DataFrame, valid: pd.DataFrame, n_groups: int = 5,
                  direction: int = 1) -> pd.DataFrame:
    """Group 0 = best after applying `direction`; equal-count groups per date.

    Ties are broken by column order (rank method 'first'), so results are deterministic.
    Dates with fewer valid stocks than `n_groups` get no groups (NaN)."""
    if direction not in (1, -1):
        raise ValueError("direction must be +1 or -1 and fixed before evaluation")
    adj = factor.where(valid).astype(float) * direction
    rank = adj.rank(axis=1, ascending=False, method="first")
    n = adj.notna().sum(axis=1)
    groups = np.floor((rank - 1).mul(n_groups).div(n, axis=0))
    groups[n < n_groups] = np.nan
    return groups


def group_returns(groups: pd.DataFrame, fwd: pd.DataFrame, n_groups: int,
                  weights: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-date group return and label coverage.

    Members with a missing forward return are excluded from that date's average and counted
    in coverage; weights (known at t, >= 0) are renormalised over the remaining members."""
    fwd = fwd.reindex(index=groups.index, columns=groups.columns)
    w = (pd.DataFrame(1.0, index=groups.index, columns=groups.columns) if weights is None
         else weights.reindex(index=groups.index, columns=groups.columns).astype(float))
    if (w < 0).any().any():
        raise ValueError("weights must be non-negative")
    rets, cover = {}, {}
    for g in range(n_groups):
        member = groups == g
        has_ret = member & fwd.notna() & w.notna()
        ww = w.where(has_ret, 0.0)
        rets[g] = (fwd.where(has_ret, 0.0) * ww).sum(axis=1) / ww.sum(axis=1).replace(0, np.nan)
        cover[g] = has_ret.sum(axis=1) / member.sum(axis=1).replace(0, np.nan)
    return pd.DataFrame(rets), pd.DataFrame(cover)


def cumulative_returns(period_returns: pd.DataFrame | pd.Series, horizon: int,
                       phase: int = 0):
    """Compound non-overlapping h-period returns: rows phase, phase+h, ...

    A missing period makes the rest of the path NaN instead of silently skipping it."""
    sub = period_returns.iloc[phase::horizon]
    return (1 + sub).cumprod(skipna=False)


def coverage(factor: pd.DataFrame, fwd: pd.DataFrame,
             universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """factor_coverage = valid / universe; label_coverage = valid with label / valid."""
    univ = (pd.DataFrame(True, index=factor.index, columns=factor.columns) if universe is None
            else universe.reindex(index=factor.index, columns=factor.columns).fillna(False).astype(bool))
    valid = valid_mask(factor, universe)
    labelled = valid & fwd.reindex(index=factor.index, columns=factor.columns).notna()
    return pd.DataFrame({
        "universe_count": univ.sum(axis=1),
        "valid_count": valid.sum(axis=1),
        "factor_coverage": valid.sum(axis=1) / univ.sum(axis=1).replace(0, np.nan),
        "label_coverage": labelled.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan),
    })


def group_turnover(groups: pd.DataFrame, group: int = 0) -> pd.Series:
    """1 - |members(t) ∩ members(t-1)| / |members(t)| between consecutive rows.

    Pass groups.iloc[::h] to measure turnover at an h-day rebalance frequency."""
    m = groups == group
    overlap = (m & m.shift(1, fill_value=False)).sum(axis=1)
    out = 1 - overlap / m.sum(axis=1).replace(0, np.nan)
    out.iloc[0] = np.nan
    return out.rename(f"turnover_g{group}")


def rank_autocorr(factor: pd.DataFrame, valid: pd.DataFrame, lag: int = 1,
                  min_obs: int = 10) -> pd.Series:
    """Spearman correlation of the valid cross-section at t with the one at t-lag."""
    x = factor.where(valid)
    return cross_sectional_corr(x, x.shift(lag), "spearman", min_obs).rename("rank_autocorr")


def choose_direction(ic: pd.Series, exit_dates: pd.Series, train_end) -> int:
    """Sign of mean IC using only labels whose exit date is <= train_end (matured)."""
    exit_dates = exit_dates.reindex(ic.index)
    matured = ic[(exit_dates <= pd.Timestamp(train_end)) & ic.notna()]
    if matured.empty:
        raise ValueError("no matured IC observations before train_end")
    return 1 if matured.mean() >= 0 else -1


def evaluate_factor(factor: pd.DataFrame, price: pd.DataFrame, *, direction: int,
                    horizon: int = 1, lag: int = 1, n_groups: int = 5,
                    universe: pd.DataFrame | None = None, weights: pd.DataFrame | None = None,
                    min_obs: int = 10, as_of=None) -> dict:
    """Full evaluation. `as_of` blanks labels whose exit date is after it (research cutoff)."""
    _check_panel(factor, "factor")
    _check_panel(price, "price")
    if not factor.index.isin(price.index).all():
        raise ValueError("every factor date must be on the price calendar")
    fwd = forward_returns(price, horizon, lag)
    exits = label_exit_dates(price.index, horizon, lag)
    if as_of is not None:
        fwd = fwd.mul(np.where(exits <= pd.Timestamp(as_of), 1.0, np.nan), axis=0)
    fwd = fwd.reindex(index=factor.index, columns=factor.columns)
    exits = exits.reindex(factor.index)
    valid = valid_mask(factor, universe)
    x = factor.where(valid)
    groups = assign_groups(factor, valid, n_groups, direction)
    g_ret, g_cov = group_returns(groups, fwd, n_groups, weights)
    long_short = (g_ret[0] - g_ret[n_groups - 1]).rename("long_short_gross")
    ic = cross_sectional_corr(x, fwd, "pearson", min_obs)
    ric = cross_sectional_corr(x, fwd, "spearman", min_obs)
    return {
        "forward_returns": fwd,
        "label_exit_dates": exits,
        "valid": valid,
        "ic": ic,
        "rank_ic": ric,
        "ic_summary": ic_summary(ic),
        "rank_ic_summary": ic_summary(ric),
        "groups": groups,
        "group_returns": g_ret,
        "group_coverage": g_cov,
        "long_short": long_short,
        "cumulative_group_returns": cumulative_returns(g_ret, horizon),
        "coverage": coverage(factor, fwd, universe),
        "top_group_turnover": group_turnover(groups, 0),
        "rank_autocorr": rank_autocorr(factor, valid, 1, min_obs),
        "meta": {"direction": direction, "horizon": horizon, "lag": lag, "n_groups": n_groups,
                 "min_obs": min_obs, "as_of": None if as_of is None else str(pd.Timestamp(as_of).date()),
                 "label": f"price[t+{lag}+{horizon}]/price[t+{lag}]-1",
                 "returns": "gross, no costs, not a tradable account"},
    }
