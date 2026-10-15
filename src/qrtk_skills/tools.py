"""Tool implementations behind the five skills. All computation is delegated to qrtk.

Every tool takes (ctx, **args) and returns a JSON-safe dict. Full results are stored as
immutable artifacts (art:<id>); reports read artifacts, never numbers typed by a model.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

import qrtk
from qrtk.diagnostics import ResearchSpec

from .runtime import SkillError, ToolContext, ToolRegistry


def j(x):
    """JSON-safe copy: numpy scalars -> python, NaN/inf -> None, timestamps -> ISO date."""
    if isinstance(x, dict):
        return {str(k): j(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [j(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(x) else str(pd.Timestamp(x).date())
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _panel(ctx: ToolContext, ref: str) -> pd.DataFrame:
    obj = ctx.catalog.get(ref)
    if not isinstance(obj, pd.DataFrame) or not isinstance(obj.index, pd.DatetimeIndex):
        raise SkillError("SCHEMA_INVALID", f"{ref} is not a date x code panel")
    return obj


def _spec(d: dict) -> ResearchSpec:
    try:
        return ResearchSpec(**{k: tuple(v) if isinstance(v, list) else v for k, v in d.items()})
    except (TypeError, ValueError) as e:
        raise SkillError("SCHEMA_INVALID", f"invalid research spec: {e}") from e


# ============================ data_research ============================

def data_profile_panel(ctx, panel: str, kind: str, observed_at: str, calendar: str | None = None):
    """Structure, coverage and quality of one panel, plus its declared observation time."""
    p = _panel(ctx, panel)
    meta = ctx.catalog.meta(panel)
    v = p.to_numpy(dtype=float) if kind != "mask" else p.astype(float).to_numpy()
    issues = []
    dup = int(p.index.duplicated().sum())
    mono = bool(p.index.is_monotonic_increasing)
    n_inf = int(np.isinf(v).sum())
    nonpos = int((v[np.isfinite(v)] <= 0).sum()) if kind == "price" else 0
    if dup:
        issues.append(f"{dup} duplicate dates")
    if not mono:
        issues.append("dates not increasing")
    if n_inf:
        issues.append(f"{n_inf} infinite values")
    if nonpos:
        issues.append(f"{nonpos} non-positive prices")
    cal_missing, cal_extra = [], []
    if calendar:
        cal = pd.DatetimeIndex(ctx.catalog.get(calendar))
        cal_missing = [d for d in cal[(cal >= p.index.min()) & (cal <= p.index.max())] if d not in p.index]
        cal_extra = [d for d in p.index if d not in cal]
        if cal_missing:
            issues.append(f"{len(cal_missing)} calendar dates missing")
        if cal_extra:
            issues.append(f"{len(cal_extra)} dates not on the calendar")
    miss = np.isnan(v)
    col_miss = miss.mean(axis=0)
    status = "fail" if (dup or not mono or n_inf or nonpos or cal_extra) else ("warn" if issues or miss.mean() > 0.2 else "ok")
    out = {
        "panel": panel, "kind": kind, "rows": int(p.shape[0]), "cols": int(p.shape[1]),
        "start": j(p.index.min()), "end": j(p.index.max()), "dtype": str(p.dtypes.iloc[0]) if p.shape[1] else None,
        "missing_rate": j(miss.mean()), "max_column_missing_rate": j(col_miss.max() if len(col_miss) else np.nan),
        "all_missing_columns": int((col_miss == 1).sum()), "inf_count": n_inf, "nonpositive_count": nonpos,
        "duplicate_dates": dup, "monotonic": mono,
        "calendar_missing": len(cal_missing), "calendar_missing_sample": j(cal_missing[:5]),
        "calendar_extra": len(cal_extra),
        "timing": {"observed_at": observed_at,
                   "usable_for_signal": "after observation time of the same date",
                   "tradable_at": "next trading session (signal at T, execution at T+1)"},
        "source": meta.get("source", "unspecified"), "synthetic": bool(meta.get("synthetic", False)),
        "sha256": meta["sha256"], "issues": issues, "status": status,
    }
    out["ref"] = ctx.put(out, "data_profile")
    return out


def data_minute_quality(ctx, raw: str, contract: dict, trading_days: str, codes: list,
                        min_coverage: float = 0.95, suspended: str | None = None):
    """Minute contract normalisation + daily aggregation quality summary (no prices returned)."""
    try:
        c = qrtk.MinuteBarContract(**contract)
    except (TypeError, ValueError) as e:
        raise SkillError("CONTRACT_INCOMPLETE", f"minute contract not fully declared: {e}") from e
    days = pd.DatetimeIndex(ctx.catalog.get(trading_days))
    session = qrtk.SessionConfig()
    bars, issues = qrtk.normalize_minute_bars(ctx.catalog.get(raw), c, session, days)
    susp = ctx.catalog.get(suspended) if suspended else None
    daily = qrtk.aggregate_daily(bars, c, session, days, codes, min_coverage=min_coverage, suspended=susp)
    out = {"issue_counts": {k: int(v) for k, v in issues["issue"].value_counts().items()},
           "status_counts": {k: int(v) for k, v in daily["status"].value_counts().items()},
           "usable_share": j((daily["status"] == "ok").mean()),
           "contract": {k: str(v) for k, v in contract.items()}}
    out["daily_ref"] = ctx.put(daily, "minute_daily")
    out["ref"] = ctx.put(out, "minute_quality")
    return out


# ============================ factor_research ============================

def _evaluate_full(ctx, factor, price, spec, universe):
    f, p = _panel(ctx, factor), _panel(ctx, price)
    u = _panel(ctx, universe) if universe else None
    return f, p, u


def factor_evaluate(ctx, factor: str, price: str, spec: dict, universe: str | None = None,
                    reveal_test: bool = False):
    """Train/valid(/test) evaluation under a frozen spec via qrtk.evaluate_splits."""
    s = _spec(spec)
    f, p, u = _evaluate_full(ctx, factor, price, spec, universe)
    rep = qrtk.evaluate_splits(f, p, s, universe=u, reveal_test=reveal_test)
    full = qrtk.evaluate_factor(f, p, direction=rep["direction"], horizon=s.horizon, lag=s.lag,
                                n_groups=s.n_groups, universe=u, min_obs=s.min_obs)
    visible_end = pd.Timestamp(s.test[1] if reveal_test else s.valid[1])
    exits = full["label_exit_dates"]
    keep = (full["rank_ic"].index <= visible_end) & (exits <= visible_end).to_numpy()
    series = {"rank_ic": full["rank_ic"][keep], "ic": full["ic"][keep],
              "group_returns": full["group_returns"][keep], "long_short": full["long_short"][keep],
              "coverage": full["coverage"][keep], "horizon": s.horizon,
              "splits": {"train": s.train, "valid": s.valid, "test": s.test}, "test_revealed": reveal_test}
    out = j({k: rep[k] for k in ("spec_fingerprint", "direction", "direction_source", "splits", "warnings", "note")})
    out["spec"] = j(rep["spec"])
    out["series_ref"] = ctx.put(series, "factor_series")
    out["ref"] = ctx.put(out, "factor_evaluation")
    return out


def factor_decay(ctx, factor: str, price: str, spec: dict, horizons: list, direction: int,
                 universe: str | None = None):
    """RankIC by holding period on data up to the validation end (test never touched)."""
    s = _spec(spec)
    f, p, u = _evaluate_full(ctx, factor, price, spec, universe)
    end = pd.Timestamp(s.valid[1])
    t = qrtk.multi_horizon(f.loc[:end], p, horizons, direction=direction, lag=s.lag, n_groups=s.n_groups,
                           universe=u, min_obs=s.min_obs, as_of=end)
    rows = [{"horizon": int(h), **j(r.to_dict())} for h, r in t.iterrows()]
    out = {"cutoff": str(end.date()), "rows": rows, "note": "decay on train+valid only; descriptive"}
    out["ref"] = ctx.put(out, "factor_decay")
    return out


def factor_profile(ctx, factor: str, end: str, universe: str | None = None, min_coverage: float = 0.8):
    """Missing values, outliers, quantiles and coverage stability up to `end`."""
    f = _panel(ctx, factor).loc[:pd.Timestamp(end)]
    u = _panel(ctx, universe) if universe else None
    per_date, summary = qrtk.factor_distribution(f, u)
    cov = pd.DataFrame({"factor_coverage": 1 - per_date["missing_rate"]})
    out = {"distribution": j(summary), "coverage": j(qrtk.coverage_stability(cov, min_coverage)),
           "median_quantiles": j(per_date.filter(like="q").median().to_dict()), "end": end}
    out["ref"] = ctx.put(out, "factor_profile")
    return out


# ============================ strategy_backtest ============================

def strategy_signal_to_orders(ctx, score: str, direction: int, top_n: int, holding_days: int,
                              start: str, end: str, value_per_name: float, universe: str | None = None):
    """Non-overlapping Top-N rebalance: every `holding_days` sessions in [start, end].

    Signal date T uses scores observable at the close of T; the ledger executes on T+1.
    Names leaving the set get a sell-all order, entering names a buy of value_per_name.
    Intended holdings are tracked from orders, not fills: a rejected buy later shows up as a
    'no_position' rejection instead of being hidden."""
    sc = _panel(ctx, score)
    u = _panel(ctx, universe).reindex_like(sc).fillna(False).astype(bool) if universe else None
    # signals strictly before `end`, so every order has a next session inside the window
    dates = sc.index[(sc.index >= pd.Timestamp(start)) & (sc.index < pd.Timestamp(end))][::holding_days]
    held, rows = set(), []
    for d in dates:
        x = sc.loc[d] * direction
        if u is not None:
            x = x[u.loc[d]]
        x = x[np.isfinite(x)]
        new = set(x.sort_values(ascending=False, kind="mergesort").index[:top_n]) if len(x) >= top_n else set()
        for c in sorted(held - new):
            rows.append({"signal_date": d, "code": c, "side": "sell", "shares": np.nan, "value": np.nan})
        for c in sorted(new - held):
            rows.append({"signal_date": d, "code": c, "side": "buy", "shares": np.nan, "value": float(value_per_name)})
        held = new
    if not rows:
        raise SkillError("INSUFFICIENT_EVIDENCE", "no orders generated in the window")
    orders = pd.DataFrame(rows)
    out = {"n_rebalances": len(dates), "n_orders": len(orders), "first_signal": j(dates[0]),
           "last_signal": j(dates[-1]), "timing": "signal at close T -> execution on session T+1",
           "rule": f"top {top_n}, direction {direction}, hold {holding_days} sessions, non-overlapping"}
    out["orders_ref"] = ctx.put(orders, "orders")
    out["ref"] = ctx.put(out, "order_plan")
    return out


def _qrtk_reference_engine(orders, open_px, close_px, initial_cash, costs, suspended, order_priority):
    return qrtk.run_backtest(orders, open_px, close_px, initial_cash=initial_cash,
                             costs=qrtk.CostModel(**costs), suspended=suspended, order_priority=order_priority)


ENGINES: dict[str, Callable] = {"qrtk_reference": _qrtk_reference_engine}


def register_engine(name: str, fn: Callable):
    """Hook for a host to add its own engine (same call signature, returns a qrtk-like result)."""
    ENGINES[name] = fn


def strategy_backtest(ctx, orders: str, open: str, close: str, initial_cash: float,
                      engine: str = "qrtk_reference", costs: dict | None = None,
                      suspended: str | None = None, order_priority: str = "sells_first",
                      end: str | None = None):
    """Run orders through a named engine; the local engine is a reference, not the only one.

    The account window is [first signal date, end or last price date]: annualised figures
    then describe the traded period, not idle history before the first order."""
    if engine not in ENGINES:
        raise SkillError("ENGINE_UNAVAILABLE", f"engine {engine} not registered; available {sorted(ENGINES)}")
    o = ctx.artifacts.get(orders, "orders")
    op, cl = _panel(ctx, open), _panel(ctx, close)
    su = _panel(ctx, suspended) if suspended else None
    lo, hi = pd.Timestamp(o["signal_date"].min()), pd.Timestamp(end) if end else op.index[-1]
    op, cl = op.loc[lo:hi], cl.loc[lo:hi]
    su = su.loc[lo:hi] if su is not None else None
    res = ENGINES[engine](o, op, cl, initial_cash, costs or {}, su, order_priority)
    rec = qrtk.reconcile(res)
    if not rec["ok"]:
        raise SkillError("RECONCILE_FAILED", f"ledger does not reconcile: {rec}")
    if res.trades.empty:
        raise SkillError("INSUFFICIENT_EVIDENCE", "no fills: no tradable result can be reported")
    rj = res.rejections
    out = {"engine": engine, "metrics": j(qrtk.performance_metrics(res)), "reconcile_ok": True,
           "n_trades": int(len(res.trades)), "n_rejections": int(len(rj)),
           "rejections_by_category": {k: int(v) for k, v in rj["category"].value_counts().items()},
           "rejections_by_reason": {k: int(v) for k, v in rj["reason"].value_counts().items()},
           "assumptions": list(res.assumptions), "start": j(res.daily.index[0]), "end": j(res.daily.index[-1]),
           "initial_equity": j(res.initial_equity), "final_nav": j(res.daily["nav"].iloc[-1]),
           "kind": "simulated account under listed assumptions (tradable-return estimate)"}
    out["daily_ref"] = ctx.put(res.daily, "ledger_daily")
    out["ref"] = ctx.put(out, "backtest_summary")
    return out


# ============================ research_diagnostics ============================

def diag_lookahead_check(ctx, price: str, builder: str, cutoffs: list):
    """Rebuild the factor on data truncated at each cutoff; rows up to the cutoff must not change."""
    p = _panel(ctx, price)
    fn = ctx.catalog.get(builder)
    if not callable(fn):
        raise SkillError("SCHEMA_INVALID", f"{builder} is not a factor builder")
    full = fn(p)
    rows = []
    for c in cutoffs:
        c = pd.Timestamp(c)
        trunc = fn(p.loc[:c])
        a, b = full.loc[:c].to_numpy(dtype=float), trunc.reindex_like(full.loc[:c]).to_numpy(dtype=float)
        same = np.isclose(a, b, equal_nan=True, rtol=0, atol=1e-12)
        rows.append({"cutoff": str(c.date()), "changed_cells": int((~same).sum())})
    passed = all(r["changed_cells"] == 0 for r in rows)
    out = {"passed": passed, "checks": rows,
           "meaning": "factor values up to each cutoff do not depend on later data" if passed
           else "factor values change when later data is removed: look-ahead"}
    out["ref"] = ctx.put(out, "lookahead_check")
    return out


def diag_sensitivity(ctx, factor: str, price: str, spec: dict, horizons: list, n_groups: list,
                     universe: str | None = None):
    """RankIC / gross long-short across a grid, on train+valid only. Reporting, not selection."""
    s = _spec(spec)
    f, p, u = _evaluate_full(ctx, factor, price, spec, universe)
    if s.direction not in (1, -1):
        raise SkillError("SCHEMA_INVALID", "sensitivity needs the resolved direction (+1/-1) in spec")
    end = pd.Timestamp(s.valid[1])
    rows = []
    for h in horizons:
        for g in n_groups:
            r = qrtk.evaluate_factor(f.loc[:end], p, direction=s.direction, horizon=h, lag=s.lag,
                                     n_groups=g, universe=u, min_obs=s.min_obs, as_of=end)
            rows.append({"horizon": int(h), "n_groups": int(g), "rank_ic_mean": j(r["rank_ic_summary"]["mean"]),
                         "long_short_mean_gross": j(r["long_short"].mean()),
                         "is_frozen_choice": bool(h == s.horizon and g == s.n_groups)})
    out = {"cutoff": str(end.date()), "rows": rows,
           "policy": "sensitivity only: the frozen spec is not replaced by the best grid point"}
    out["ref"] = ctx.put(out, "sensitivity")
    return out


def diag_evidence_review(ctx, evaluation: str, backtest: str | None = None, lookahead: str | None = None,
                         min_dates: int = 60, suspicious_rank_ic: float = 0.3):
    """Decide whether results support a conclusion. Verdict: sufficient / insufficient / suspicious."""
    ev = ctx.artifacts.get(evaluation, "factor_evaluation")
    reasons, suspicious = [], []
    tr, va = ev["splits"].get("train"), ev["splits"].get("valid")
    for name, sp in (("train", tr), ("valid", va)):
        if not isinstance(sp, dict):
            reasons.append(f"{name} split unavailable")
            continue
        r = sp["predictive"]["rank_ic"]
        if (r["n_dates"] or 0) < min_dates:
            reasons.append(f"{name}: {r['n_dates']} RankIC dates < {min_dates}")
        if r["mean"] is not None and abs(r["mean"]) > suspicious_rank_ic:
            suspicious.append(f"{name}: |RankIC| {abs(r['mean']):.3f} > {suspicious_rank_ic} (check for leakage)")
    if isinstance(tr, dict) and isinstance(va, dict):
        a, b = tr["predictive"]["rank_ic"]["mean"], va["predictive"]["rank_ic"]["mean"]
        if a is not None and b is not None and a * b < 0:
            reasons.append("RankIC sign flips between train and valid")
    if lookahead is not None and not ctx.artifacts.get(lookahead, "lookahead_check")["passed"]:
        suspicious.append("look-ahead check failed")
    if backtest is None:
        reasons.append("no backtest result: no tradable-return conclusion")
    else:
        ctx.artifacts.get(backtest, "backtest_summary")
    verdict = "suspicious" if suspicious else ("insufficient" if reasons else "sufficient")
    out = {"verdict": verdict, "reasons": reasons, "suspicious": suspicious,
           "spec_fingerprint": ev["spec_fingerprint"]}
    out["ref"] = ctx.put(out, "evidence_review")
    return out


# ============================ registry ============================

def build_registry() -> ToolRegistry:
    from .report import report_render
    r = ToolRegistry()
    read = ("read:catalog", "compute")
    r.register("data.profile_panel", data_profile_panel, read)
    r.register("data.minute_quality", data_minute_quality, read)
    r.register("factor.evaluate", factor_evaluate, read)
    r.register("factor.decay", factor_decay, read)
    r.register("factor.profile", factor_profile, read)
    r.register("strategy.signal_to_orders", strategy_signal_to_orders, read)
    r.register("strategy.backtest", strategy_backtest, read)
    r.register("diag.lookahead_check", diag_lookahead_check, read)
    r.register("diag.sensitivity", diag_sensitivity, read)
    r.register("diag.evidence_review", diag_evidence_review, ("compute",))
    r.register("report.render", report_render, ("compute", "write:artifacts"))
    return r
