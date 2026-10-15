"""Quantify how factor floating-point noise changes ranks and group membership (stage 3, 2026-10-15; read-only).

Two numerically valid computations of the same formula differ in the last bits (e.g. the DSL rolling mean versus a direct
sum: CMI, |diff| <= 2.3e-13). Values that are equal in exact arithmetic can then order differently, which moves stocks across
rank positions and group boundaries. This tool measures that effect on one finished study instead of changing the ranking
contract (no global rounding):

  per signal date, over stocks with a finite factor in both computations
    - stocks whose descending position (stable, ties by column order) differs, and dates with any such change
    - stocks whose G0..G{k-1} membership differs (the group rule of tools/numcheck_study.py, G0 = highest)
    - whether every moved stock sits in a near-tie cluster (|gap to a neighbour| <= --tie-tol * scale in the reference)
    - RankIC and group-mean differences, then the effect on the per-split mean / std / IR / HAC SE

usage: python rankflip_study.py <study dir> <out json> --formula cmi21 [--tie-tol 1e-11]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from numcheck_study import FORMULAS, corr_rows, groups_rows, load, newey_west_se  # noqa: E402


def order_desc(v, ok):
    cols = np.flatnonzero(ok)
    return cols[np.argsort(-v[ok], kind="mergesort")]


def main():
    study, out = Path(sys.argv[1]), Path(sys.argv[2])
    formula = sys.argv[sys.argv.index("--formula") + 1]
    tie_tol = float(sys.argv[sys.argv.index("--tie-tol") + 1]) if "--tie-tol" in sys.argv else 1e-11
    spec = json.loads((study / "data/frozen_spec.json").read_text(encoding="utf-8"))["spec"]
    rel = json.loads((study / "code/release_resources.json").read_text(encoding="utf-8"))
    paths = {r["partition"]: r["path"] for r in rel["resources"]}
    parts = [load(paths["train"]), load(paths["validation"])]
    data = {f: pd.concat([p[f] for p in parts]) for f in parts[0]}
    lag, h, k, min_obs = spec["lag"], spec["horizon"], spec["n_groups"], spec["min_obs"]
    ref = FORMULAS[formula](data)
    op = data["open"].where(data["open"] > 0)
    label = (op.shift(-(lag + h)) / op.shift(-lag) - 1).to_numpy()
    pf = pd.read_pickle(study / "data/factor_plain.pkl")
    pf.index = pd.to_datetime(pf.index.astype(str), format="%Y%m%d")
    pf = pf.reindex(index=ref.index, columns=[c.split(".")[0] for c in ref.columns])
    x, xp = ref.to_numpy(dtype=float), pf.to_numpy(dtype=float)
    scale = float(np.nanmax(np.abs(x)))
    moved_pos = moved_grp = dates_pos = dates_grp = cells = outside_tie = 0
    per_date = []
    for i in range(len(x)):
        ok = np.isfinite(x[i]) & np.isfinite(xp[i])
        n = int(ok.sum())
        if n < k:
            continue
        cells += n
        a, b = order_desc(x[i], ok), order_desc(xp[i], ok)
        pos_a = np.empty(x.shape[1], int); pos_a[a] = np.arange(n)
        pos_b = np.empty(x.shape[1], int); pos_b[b] = np.arange(n)
        cols = a
        mp = int((pos_a[cols] != pos_b[cols]).sum())
        g = lambda pos: np.floor(pos * k / n).astype(int)
        mg_mask = g(pos_a[cols]) != g(pos_b[cols])
        mg = int(mg_mask.sum())
        if mp:
            # a moved stock must have a reference neighbour within the tie tolerance (theoretically equal values)
            sv = x[i][a]
            gap = np.minimum(np.r_[np.inf, np.abs(np.diff(sv))], np.r_[np.abs(np.diff(sv)), np.inf])
            moved = pos_a[cols] != pos_b[cols]
            outside_tie += int((moved & (gap > tie_tol * scale)).sum())
        moved_pos += mp; moved_grp += mg; dates_pos += bool(mp); dates_grp += bool(mg)
        if mg:
            per_date.append({"date": str(ref.index[i].date()), "stocks": n, "moved_position": mp, "moved_group": mg})
    ric, _ = corr_rows(x, label, True, min_obs)
    ricp, _ = corr_rows(xp, label, True, min_obs)
    gr, grp = groups_rows(x, label, k, min_obs), groups_rows(xp, label, k, min_obs)
    exit_date = pd.Series(ref.index, index=ref.index).shift(-(lag + h))
    effect = {}
    for name, (s, e) in {"train": spec["train"], "validation": spec["valid"]}.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        use = ((ref.index >= s) & (ref.index <= e) & (exit_date <= e).to_numpy())
        row = {}
        for tag, r0, r1 in (("rank_ic", ric, ricp), *[(f"G{j}", gr[:, j], grp[:, j]) for j in range(k)],
                            ("spread", gr[:, 0] - gr[:, k - 1], grp[:, 0] - grp[:, k - 1])):
            u0, u1 = pd.Series(r0[use]).dropna(), pd.Series(r1[use]).dropna()
            lags = max(h - 1, int(4 * (len(u0) / 100) ** (2 / 9)))
            row[tag] = {"mean_ref": u0.mean(), "mean_pkl": u1.mean(), "mean_diff": u1.mean() - u0.mean(),
                        "std_diff": u1.std(ddof=1) - u0.std(ddof=1),
                        "ir_diff": u1.mean() / u1.std(ddof=1) - u0.mean() / u0.std(ddof=1),
                        "hac_se_diff": newey_west_se(u1, lags) - newey_west_se(u0, lags),
                        "max_daily_abs_diff": float(np.nanmax(np.abs(r1[use] - r0[use]))) if use.any() else None,
                        "days_changed": int(np.nansum(np.abs(r1[use] - r0[use]) > 0))}
        effect[name] = row
    report = {"study": str(study), "formula": formula, "tie_tolerance": tie_tol, "factor_scale": scale,
              "factor_noise_max": float(np.nanmax(np.abs(xp - x))), "cells_compared": cells, "dates": len(x),
              "moved_position_cells": moved_pos, "dates_with_moved_position": dates_pos,
              "moved_group_cells": moved_grp, "dates_with_moved_group": dates_grp,
              "moved_outside_near_tie": outside_tie,
              "verdict": ("all moves are within near-tie clusters (float noise only)" if outside_tie == 0
                          else "some moved stocks are not near-ties: investigate a definitional difference"),
              "statistic_effect": effect, "group_moves_by_date": per_date[:200]}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k2: v for k2, v in report.items() if k2 not in ("statistic_effect", "group_moves_by_date")}, indent=1, default=float))
    for name, row in effect.items():
        for tag in ("rank_ic", "G0", f"G{k - 1}", "spread"):
            r = row[tag]
            print(f"{name:10s} {tag:8s} mean diff {r['mean_diff']:+.3e}  IR diff {r['ir_diff']:+.3e}  HAC SE diff {r['hac_se_diff']:+.3e}"
                  f"  max daily {r['max_daily_abs_diff']:.3e}  days changed {r['days_changed']}")


if __name__ == "__main__":
    main()
