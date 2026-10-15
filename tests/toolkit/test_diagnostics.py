"""Factor diagnostics and frozen research specs. Hand-computed expectations."""
import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from qrtk import (ResearchSpec, coverage_stability, evaluate_splits, factor_distribution,
                  forward_returns, monotonicity, multi_horizon, period_summary)
from test_factor_eval import random_walk


def test_factor_distribution_hand():
    idx = pd.DatetimeIndex(["2025-01-06"])
    f = pd.DataFrame([[1, 2, 3, 4, 100, np.inf, np.nan, 7]], idx, list("ABCDEFGH"), dtype=float)
    u = pd.DataFrame([[1, 1, 1, 1, 1, 1, 1, 0]], idx, list("ABCDEFGH")).astype(bool)
    t, s = factor_distribution(f, u)
    r = t.iloc[0]
    assert (r["n_universe"], r["n_valid"], r["n_inf"]) == (7, 5, 1)
    assert r["missing_rate"] == pytest.approx(2 / 7)
    assert r["q0.5"] == 3
    # median 3, MAD = median(2,1,0,1,97) = 1 -> scale 1.4826; only 100 has robust z > 5
    assert r["n_outliers"] == 1
    assert s["total_inf"] == 1


def test_coverage_stability_hand():
    cov = pd.DataFrame({"factor_coverage": [1.0, 0.7, 0.6, 0.9, 0.5]})
    s = coverage_stability(cov, 0.8)
    assert (s["days_below"], s["longest_run_below"]) == (3, 2) and s["min"] == 0.5


def test_monotonicity():
    dec = pd.DataFrame([[0.03, 0.02, 0.01], [0.05, 0.0, -0.01]])
    m = monotonicity(dec)
    assert m["daily_mean"] == pytest.approx(1.0) and m["strictly_monotone"] and m["pooled"] == pytest.approx(1.0)
    inc = dec.iloc[:, ::-1].set_axis([0, 1, 2], axis=1)
    m2 = monotonicity(inc)
    assert m2["daily_mean"] == pytest.approx(-1.0) and not m2["strictly_monotone"]


def test_period_summary_hand():
    idx = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-02-03", "2025-02-04", "2025-02-05"])
    ic = pd.Series([0.1, 0.3, -0.2, 0.0, 0.2], idx)
    t = period_summary(ic, "M")
    assert t.loc["2025-01", "mean"] == pytest.approx(0.2) and t.loc["2025-02", "mean"] == pytest.approx(0.0)
    assert t.loc["2025-02", "n_dates"] == 3
    t2 = period_summary(ic, periods={"early": ("2025-01-01", "2025-01-31")})
    assert t2.loc["early", "mean"] == pytest.approx(0.2)


def test_multi_horizon_and_overlap():
    p = random_walk(120, 30, 4)
    leak1 = forward_returns(p, 1, 1)                    # exactly the h=1 label
    t = multi_horizon(leak1, p, (1, 5), direction=1, min_obs=5)
    assert t.loc[1, "rank_ic_mean"] == pytest.approx(1.0)
    assert t.loc[5, "rank_ic_mean"] < 0.9               # information decays with horizon
    assert t.loc[5, "approx_independent"] == pytest.approx(t.loc[5, "n_dates"] / 5)


def spec(**kw):
    base = dict(factor_name="f", direction=1, horizon=5, train=("2020-01-01", "2020-04-30"),
                valid=("2020-05-01", "2020-06-30"), test=("2020-07-01", "2020-08-31"),
                min_obs=5, min_dates_per_split=30)
    base.update(kw)
    return ResearchSpec(**base)


def test_spec_is_frozen_and_fingerprinted():
    s = spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.direction = -1
    assert s.fingerprint() == spec().fingerprint()
    assert s.fingerprint() != spec(direction=-1).fingerprint()
    assert s.fingerprint() != spec(execution_rule="vwap_first_30m").fingerprint()
    with pytest.raises(ValueError):
        spec(valid=("2020-04-15", "2020-06-30"))       # overlaps train
    with pytest.raises(ValueError):
        spec(direction=0)


def test_splits_purge_seal_and_train_direction():
    p = random_walk(175, 30, 6)                          # 2020-01-01 .. ~2020-09
    label = forward_returns(p, 5, 1)
    train_end = pd.Timestamp("2020-04-30")
    f = label.mul(np.where(label.index > train_end, 1.0, -1.0), axis=0)   # negative in train, positive after
    s = spec(direction="train")
    out = evaluate_splits(f, p, s)
    assert out["direction"] == -1 and out["direction_source"] == "train_matured_rank_ic"
    assert out["splits"]["test"] == "sealed"
    tr = out["splits"]["train"]
    assert tr["n_purged"] == 6                           # exit = t+1+5 sessions beyond train end
    assert tr["predictive"]["rank_ic"]["mean"] == pytest.approx(-1.0)
    va = out["splits"]["valid"]
    assert va["predictive"]["rank_ic"]["mean"] == pytest.approx(1.0)
    assert va["theoretical_groups"]["long_short_mean_gross"] < 0   # train-chosen direction fails here
    assert any("labels overlap" in w for w in out["warnings"])
    revealed = evaluate_splits(f, p, s, reveal_test=True)
    assert isinstance(revealed["splits"]["test"], dict)
    assert revealed["spec_fingerprint"] == s.fingerprint()


def test_split_warnings_for_small_samples():
    p = random_walk(175, 30, 8)
    f = p / p.shift(5) - 1
    out = evaluate_splits(f, p, spec(min_dates_per_split=100))
    assert any("valid: only" in w for w in out["warnings"])
