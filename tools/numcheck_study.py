"""Independent numerical check of one finished study (pre-release QA; read-only on the study and the data release).

Recomputes from the published raw arrays, with its own code (numpy/pandas only, no qrtk / research_agent evaluator):
factor values -> labels (open[t+lag+h] / open[t+lag] - 1 on the release calendar, lag 1) -> daily Pearson IC and Spearman
RankIC (pairs with both finite, >= min_obs, non-constant) -> five equal-weight groups per date (G0 = highest factor values)
-> per-split mean / std / ICIR / win rate (purged: exit date inside the split) -> Newey-West HAC standard error.
Every difference above tolerance is written with the production value, the reference value, the cell and the size.

usage: python numcheck_study.py <trusted study dir> <out json> --formula reversal5|alpha12|cmi21|gh52
Only use this offline operator tool on your own freshly generated, trusted artifacts; never on downloaded pickle files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def rankdata(a):
    return pd.Series(a).rank(method="average").to_numpy()

FORMULAS = {
    "reversal5": lambda d: -(d["close"] / d["close"].shift(5) - 1),
    # sign(V_t - V_{t-1}) * -(C_t - C_{t-1})                         Alpha#12 (Kakushadze 2016)
    "alpha12": lambda d: np.sign(d["volume"] - d["volume"].shift(1)) * -(d["close"] - d["close"].shift(1)),
    # (1/21) * sum_{k=0..20} (y_{t-k} - y_{t-k-21}),  y = close       CMI with tau = 21 (cond-mat/0212641)
    "cmi21": lambda d: sum((d["close"].shift(k) - d["close"].shift(k + 21)) for k in range(21)) / 21.0,
    # P_t / max_{0<=k<=251} P_{t-k}, P = close (full 252-row window)      52-week high (George & Hwang 2004)
    "gh52": lambda d: d["close"] / d["close"].rolling(252, min_periods=252).max(),
}


def load(release_manifest):
    m = json.loads(Path(release_manifest).read_text(encoding="utf-8"))
    base = Path(release_manifest).parent
    idx = pd.to_datetime(m["dates"], format="%Y%m%d")
    return {f: pd.DataFrame(np.load(base / f"{f}.npy"), index=idx, columns=m["codes"])
            for f in ("open", "high", "low", "close", "volume", "amount")}


def corr_rows(x, y, rank, min_obs):
    out = np.full(len(x), np.nan)
    n = np.zeros(len(x))
    for i in range(len(x)):
        a, b = x[i], y[i]
        ok = np.isfinite(a) & np.isfinite(b)
        n[i] = ok.sum()
        if ok.sum() < min_obs:
            continue
        a, b = a[ok], b[ok]
        if rank:
            a, b = rankdata(a), rankdata(b)
        if a.std() == 0 or b.std() == 0:
            continue
        out[i] = np.corrcoef(a, b)[0, 1]
    return out, n


def groups_rows(x, y, k=5, min_obs=10):
    """Equal-weight mean label per factor quantile group, G0 = highest factor values. Groups are formed at the signal
    date from stocks with a finite factor (a label known only later cannot decide membership); a member without a label
    is left out of that date's average. Rank r (1 = highest, ties by column order) goes to group floor((r-1)*k/n)."""
    out = np.full((len(x), k), np.nan)
    for i in range(len(x)):
        ok = np.isfinite(x[i])
        n = ok.sum()
        if n < k:
            continue
        cols = np.flatnonzero(ok)
        order = cols[np.argsort(-x[i][ok], kind="mergesort")]          # descending, stable: ties by column order
        g_of = np.empty(len(order), int)
        g_of[:] = np.floor(np.arange(len(order)) * k / n).astype(int)
        for g in range(k):
            members = order[g_of == g]
            vals = y[i][members]
            vals = vals[np.isfinite(vals)]
            out[i, g] = vals.mean() if vals.size else np.nan
    return out


def newey_west_se(s, lags):
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    n = len(s)
    e = s - s.mean()
    v = (e @ e) / n
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        v += 2 * w * (e[L:] @ e[:-L]) / n
    return float(np.sqrt(v / n))


def main():
    study, out, formula = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[sys.argv.index("--formula") + 1]
    man = json.loads((study / "manifest.json").read_text(encoding="utf-8"))
    spec = json.loads((study / "data/frozen_spec.json").read_text(encoding="utf-8"))["spec"]
    rel = json.loads((study / "code/release_resources.json").read_text(encoding="utf-8"))
    paths = {r["partition"]: r["path"] for r in rel["resources"]}
    parts = [load(paths["train"]), load(paths["validation"])]
    data = {f: pd.concat([p[f] for p in parts]) for f in parts[0]}
    lag, h, min_obs = spec["lag"], spec["horizon"], spec["min_obs"]
    fac = FORMULAS[formula](data)
    op = data["open"].where(data["open"] > 0)
    label = op.shift(-(lag + h)) / op.shift(-lag) - 1
    exit_date = pd.Series(data["open"].index, index=data["open"].index).shift(-(lag + h))
    report = {"study": str(study), "formula": formula, "spec": spec, "checks": [], "differences": []}

    def check(name, prod, ref, tol, where=""):
        prod, ref = np.asarray(prod, float), np.asarray(ref, float)
        nan_mismatch = int((np.isnan(prod) != np.isnan(ref)).sum())
        both = np.isfinite(prod) & np.isfinite(ref)
        diff = np.abs(prod[both] - ref[both])
        bad = int((diff > tol).sum())
        mx = float(diff.max()) if diff.size else 0.0
        report["checks"].append({"name": name, "cells": int(both.sum()), "nan_pattern_mismatch": nan_mismatch,
                                 "over_tolerance": bad, "max_abs_diff": mx, "tolerance": tol, "where": where,
                                 "passed": bad == 0 and nan_mismatch == 0})
        if bad or nan_mismatch:
            pos = np.argwhere(np.abs(np.nan_to_num(prod, nan=1e300) - np.nan_to_num(ref, nan=1e300)) > tol)[:5]
            report["differences"].append({"name": name, "first_positions": pos.tolist(),
                                          "prod": [float(prod[tuple(p)]) for p in pos], "ref": [float(ref[tuple(p)]) for p in pos]})

    # 1. factor values (the delivered PKL)
    pf = pd.read_pickle(study / "data/factor_plain.pkl")
    report["pkl_shape"] = list(pf.shape)
    # export format: YYYYMMDD string dates, codes without the exchange suffix
    pf.index = pd.to_datetime(pf.index.astype(str), format="%Y%m%d")
    bare = [c.split(".")[0] for c in fac.columns]
    report["code_suffix_collisions"] = len(bare) - len(set(bare))
    pf = pf.reindex(index=fac.index, columns=bare)
    check("factor values vs PKL", pf.to_numpy(), fac.to_numpy(), 1e-9 * max(1.0, float(np.nanmax(np.abs(fac.to_numpy())))))
    # 2. daily IC / RankIC
    sysd = pd.read_csv(study / "data/ic_rankic.csv", index_col=0, parse_dates=True)
    x, y = fac.to_numpy(), label.to_numpy()
    ic, n = corr_rows(x, y, False, min_obs)
    ric, _ = corr_rows(x, y, True, min_obs)
    ref = pd.DataFrame({"ic": ic, "rank_ic": ric, "n": n}, index=fac.index).reindex(sysd.index)
    check("daily IC", sysd["ic"], ref["ic"], 1e-9)
    check("daily RankIC", sysd["rank_ic"], ref["rank_ic"], 1e-9)
    # 3. groups
    sg = pd.read_csv(study / "data/group_returns_gross.csv", index_col=0, parse_dates=True)
    rg = pd.DataFrame(groups_rows(x, y, spec["n_groups"], min_obs), index=fac.index).reindex(sg.index)
    check("G0..G4 (G0 = highest)", sg.to_numpy(), rg.to_numpy(), 1e-9)
    check("G0-G4 vs G4..G0 reversed (diagnostic)", sg.to_numpy()[:, ::-1], rg.to_numpy(), 1e-9, "passes only if the files order G4 first")
    # 3b. the same statistics computed by this script from the delivered PKL values: separates a statistics error from
    #     floating-point noise in factor values that should tie (rank and group membership are sensitive to 1e-13)
    xp = pf.to_numpy(dtype=float)
    ricp, _ = corr_rows(xp, y, True, min_obs)
    check("daily RankIC recomputed from the PKL values", sysd["rank_ic"], pd.Series(ricp, index=fac.index).reindex(sysd.index), 1e-9)
    rgp = pd.DataFrame(groups_rows(xp, y, spec["n_groups"], min_obs), index=fac.index).reindex(sg.index)
    check("G0..G4 recomputed from the PKL values", sg.to_numpy(), rgp.to_numpy(), 1e-9)
    near = np.abs(xp - x)
    report["factor_float_noise"] = {"cells_differing": int(np.nansum(near > 0)), "max": float(np.nanmax(near)),
                                    "zero_vs_noise_cells": int(np.nansum((x == 0) & (xp != 0)))}
    # 4. split statistics and HAC
    metrics = pd.read_csv(study / "data/factor_metrics.csv")
    infer = pd.read_csv(study / "data/factor_inference.csv")
    splits = {"train": spec["train"], "validation": spec["valid"]}
    report["splits"] = {}
    for name, (s, e) in splits.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        use = (ref.index >= s) & (ref.index <= e) & (exit_date.reindex(ref.index) <= e).to_numpy()
        key = "train" if name == "train" else "valid"
        for col in ("ic", "rank_ic"):
            ser = ref[col][use].dropna()
            mean, std = ser.mean(), ser.std(ddof=1)
            row = metrics[(metrics["split"].isin([key, name])) & (metrics["metric"] == col)]
            inf = infer[(infer["split"].isin([key, name])) & (infer["metric"] == col)]
            lags = int(inf["lags"].iloc[0]) if len(inf) else 6
            se = newey_west_se(ser, lags)
            report["splits"][f"{name}.{col}"] = {"n": int(len(ser)), "mean": mean, "std": std, "icir": mean / std,
                                                 "win_rate": float((ser > 0).mean()), "hac_se": se, "hac_lags": lags,
                                                 "prod": row.iloc[0].to_dict() if len(row) else None,
                                                 "prod_inference": inf.iloc[0].to_dict() if len(inf) else None}
            if len(row):
                check(f"{name} {col} mean", [row["mean"].iloc[0]], [mean], 1e-10)
                check(f"{name} {col} std", [row["std"].iloc[0]], [std], 1e-10)
                check(f"{name} {col} ICIR", [row["icir"].iloc[0]], [mean / std], 1e-9)
                check(f"{name} {col} win rate", [row["positive_ratio"].iloc[0]], [float((ser > 0).mean())], 1e-12)
                check(f"{name} {col} n_dates", [row["n_dates"].iloc[0]], [len(ser)], 0)
            if len(inf):
                check(f"{name} {col} HAC se (lags {lags})", [inf["se"].iloc[0]], [se], 1e-9)
    report["passed"] = all(c["passed"] for c in report["checks"] if "diagnostic" not in c["name"])
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for c in report["checks"]:
        print(("PASS " if c["passed"] else "FAIL ") + c["name"], c["cells"], c["max_abs_diff"], c["nan_pattern_mismatch"])
    print("ALL PASSED" if report["passed"] else "DIFFERENCES FOUND")


if __name__ == "__main__":
    main()
