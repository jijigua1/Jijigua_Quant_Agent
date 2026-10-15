"""Factor research diagnostics on top of factor_eval, with frozen research specifications.

Three things are kept apart in every output:
  predictive          IC / RankIC: does the factor rank future returns?
  theoretical_groups  gross equal-weight group returns, no costs, no fills: a description
  tradable            only a ledger run (backtest.run_backtest*) produces account returns
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from .factor_eval import (_check_panel, choose_direction, evaluate_factor, ic_summary, valid_mask)

DEFAULT_QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


def factor_distribution(factor: pd.DataFrame, universe: pd.DataFrame | None = None,
                        quantiles=DEFAULT_QUANTILES, outlier_z: float = 5.0) -> tuple[pd.DataFrame, dict]:
    """Per-date missing rate, non-finite count, moments, quantiles and robust outliers.

    missing_rate = 1 - valid / universe members (inf counts as missing).
    outlier: |x - median| / (1.4826 * MAD) > outlier_z on the valid cross-section."""
    _check_panel(factor, "factor")
    univ = (pd.DataFrame(True, index=factor.index, columns=factor.columns) if universe is None else
            universe.reindex(index=factor.index, columns=factor.columns).fillna(False).astype(bool))
    raw = factor.where(univ).astype(float)
    n_inf = np.isinf(raw).sum(axis=1)
    x = raw.where(np.isfinite(raw))
    med = x.median(axis=1)
    mad = x.sub(med, axis=0).abs().median(axis=1) * 1.4826
    z = x.sub(med, axis=0).abs().div(mad.replace(0, np.nan), axis=0)
    out = pd.DataFrame({
        "n_universe": univ.sum(axis=1), "n_valid": x.notna().sum(axis=1), "n_inf": n_inf,
        "missing_rate": 1 - x.notna().sum(axis=1) / univ.sum(axis=1).replace(0, np.nan),
        "mean": x.mean(axis=1), "std": x.std(axis=1, ddof=1),
        "n_outliers": (z > outlier_z).sum(axis=1),
    })
    for q in quantiles:
        out[f"q{q:g}"] = x.quantile(q, axis=1)
    summary = {"mean_missing_rate": float(out["missing_rate"].mean()),
               "max_missing_rate": float(out["missing_rate"].max()),
               "total_inf": int(n_inf.sum()), "total_outliers": int(out["n_outliers"].sum()),
               "outlier_rule": f"robust z > {outlier_z}"}
    return out, summary


def coverage_stability(coverage: pd.DataFrame, min_coverage: float = 0.8) -> dict:
    """Level and stability of factor coverage over time (coverage from evaluate_factor)."""
    c = coverage["factor_coverage"].dropna()
    below = (c < min_coverage).astype(int)
    runs = below.groupby((below != below.shift()).cumsum()).sum()
    return {"mean": float(c.mean()), "min": float(c.min()), "std": float(c.std(ddof=1)) if len(c) > 1 else np.nan,
            "days_below": int(below.sum()), "longest_run_below": int(runs.max()) if len(runs) else 0,
            "threshold": min_coverage}


def monotonicity(group_returns: pd.DataFrame) -> dict:
    """+1 = returns fall strictly from group 0 (best) to the last group.

    daily_mean: mean over dates of -Spearman(group index, group return);
    pooled: -Spearman on the time-averaged group returns; strictly_monotone on those means."""
    g = group_returns.dropna(how="any")
    idx_rank = pd.Series(np.arange(g.shape[1]), dtype=float).rank().to_numpy()

    def neg_spearman(row):
        r = pd.Series(row).rank().to_numpy()
        return -np.corrcoef(idx_rank, r)[0, 1] if np.ptp(r) > 0 else np.nan

    daily = g.apply(lambda row: neg_spearman(row.to_numpy()), axis=1) if len(g) else pd.Series(dtype=float)
    means = group_returns.mean()
    return {"daily_mean": float(daily.mean()) if len(daily) else np.nan,
            "share_positive": float((daily > 0).mean()) if len(daily) else np.nan,
            "pooled": float(neg_spearman(means.to_numpy())) if means.notna().all() else np.nan,
            "strictly_monotone": bool(means.notna().all() and (np.diff(means.to_numpy()) < 0).all()),
            "n_dates": int(len(daily))}


def period_summary(ic: pd.Series, freq: str | None = "M", periods: dict | None = None) -> pd.DataFrame:
    """IC summary per calendar period ('M', 'Q', 'Y') or per named (start, end) periods.

    Periods are assigned by signal date; an h-day label may end in the next period."""
    if periods is not None:
        rows = {name: ic_summary(ic.loc[pd.Timestamp(s):pd.Timestamp(e)]) for name, (s, e) in periods.items()}
    else:
        f = {"M": "M", "Q": "Q", "Y": "Y"}[freq]
        rows = {str(p): ic_summary(v) for p, v in ic.groupby(ic.index.to_period(f))}
    return pd.DataFrame(rows).T


def multi_horizon(factor: pd.DataFrame, price: pd.DataFrame, horizons=(1, 5, 10, 20), *,
                  direction: int, **kwargs) -> pd.DataFrame:
    """RankIC / IC summary and gross long-short mean per holding period (factor decay).

    approx_independent = n_dates / h: overlapping labels share returns, so the effective
    sample is far smaller than n_dates for h > 1."""
    rows = {}
    for h in horizons:
        r = evaluate_factor(factor, price, direction=direction, horizon=h, **kwargs)
        s, si = r["rank_ic_summary"], r["ic_summary"]
        rows[h] = {"rank_ic_mean": s["mean"], "rank_icir": s["icir"], "ic_mean": si["mean"],
                   "icir": si["icir"], "n_dates": s["n_dates"], "approx_independent": s["n_dates"] / h,
                   "long_short_mean_gross": float(r["long_short"].mean())}
    return pd.DataFrame(rows).T.rename_axis("horizon")


@dataclass(frozen=True)
class ResearchSpec:
    """Everything that must be fixed before looking at validation or test results."""
    factor_name: str
    direction: int | str                  # +1, -1 or "train" (sign of matured train RankIC)
    horizon: int
    train: tuple[str, str]
    valid: tuple[str, str]
    test: tuple[str, str]
    lag: int = 1
    n_groups: int = 5
    min_obs: int = 10
    universe_name: str = "unspecified"
    execution_rule: str = "next_open"
    min_dates_per_split: int = 60

    def __post_init__(self):
        if self.direction not in (1, -1, "train"):
            raise ValueError("direction must be +1, -1 or 'train'")
        s = [pd.Timestamp(x) for pair in (self.train, self.valid, self.test) for x in pair]
        if any(s[i] > s[i + 1] for i in range(5)) or s[1] >= s[2] or s[3] >= s[4]:
            raise ValueError("train < valid < test, each (start <= end), no overlap")

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()


def evaluate_splits(factor: pd.DataFrame, price: pd.DataFrame, spec: ResearchSpec, *,
                    universe: pd.DataFrame | None = None, reveal_test: bool = False) -> dict:
    """Train / validation / test evaluation under one frozen spec.

    A split uses signal dates in [start, end] whose label exit date is <= end (purged), so no
    label reaches into the next split. Direction 'train' is decided on matured train labels
    only. Test results stay sealed unless reveal_test=True."""
    kw = dict(horizon=spec.horizon, lag=spec.lag, n_groups=spec.n_groups, universe=universe,
              min_obs=spec.min_obs)
    if spec.direction == "train":
        probe = evaluate_factor(factor, price, direction=1, **kw)
        exits = probe["label_exit_dates"]
        t0, t1 = map(pd.Timestamp, spec.train)
        ic_train = probe["rank_ic"][(probe["rank_ic"].index >= t0)]
        direction, source = choose_direction(ic_train, exits, t1), "train_matured_rank_ic"
    else:
        direction, source = spec.direction, "fixed"
    res = evaluate_factor(factor, price, direction=direction, **kw)
    exits = res["label_exit_dates"]
    out = {"spec": asdict(spec), "spec_fingerprint": spec.fingerprint(), "direction": direction,
           "direction_source": source, "splits": {}, "warnings": [],
           "note": "predictive = IC; theoretical_groups = gross, costless; tradable returns only from the ledger"}
    if spec.horizon > 1:
        out["warnings"].append(f"labels overlap (h={spec.horizon}): ICIR not annualised; "
                               f"effective independent dates ~ n/{spec.horizon}")
    for name in ("train", "valid", "test"):
        if name == "test" and not reveal_test:
            out["splits"]["test"] = "sealed"
            continue
        s, e = map(pd.Timestamp, getattr(spec, name))
        in_rng = (res["ic"].index >= s) & (res["ic"].index <= e)
        use = in_rng & (exits.reindex(res["ic"].index) <= e).to_numpy()
        ric, ic = res["rank_ic"][use], res["ic"][use]
        gr = res["group_returns"][use]
        cov = res["coverage"][use]
        split = {
            "n_signal_dates": int(in_rng.sum()), "n_purged": int(in_rng.sum() - use.sum()),
            "predictive": {"rank_ic": ic_summary(ric), "ic": ic_summary(ic)},
            "theoretical_groups": {"mean_group_return_gross": gr.mean().to_dict(),
                                   "long_short_mean_gross": float(res["long_short"][use].mean()),
                                   "monotonicity": monotonicity(gr)},
            "mean_factor_coverage": float(cov["factor_coverage"].mean()),
            "mean_label_coverage": float(cov["label_coverage"].mean()),
        }
        n = split["predictive"]["rank_ic"]["n_dates"]
        if n < spec.min_dates_per_split:
            out["warnings"].append(f"{name}: only {n} valid RankIC dates (< {spec.min_dates_per_split})")
        if split["mean_factor_coverage"] < 0.8:
            out["warnings"].append(f"{name}: mean factor coverage {split['mean_factor_coverage']:.2f} < 0.80")
        if split["mean_label_coverage"] < 0.8:
            out["warnings"].append(f"{name}: mean label coverage {split['mean_label_coverage']:.2f} < 0.80")
        out["splits"][name] = split
    return out
