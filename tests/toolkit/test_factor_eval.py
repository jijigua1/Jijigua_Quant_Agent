"""Numerical acceptance for qrtk.factor_eval. Expected values are hand-computed, not re-derived
from the implementation. All data are synthetic."""
import math

import numpy as np
import pandas as pd
import pytest

from qrtk import (assign_groups, choose_direction, cross_sectional_corr, cumulative_returns,
                  evaluate_factor, forward_returns, group_returns, group_turnover, ic_summary,
                  label_exit_dates, rank_autocorr, valid_mask)

D = pd.bdate_range("2025-01-06", periods=5)


def panel(rows, cols, index=None):
    return pd.DataFrame(rows, index=index if index is not None else D[: len(rows)], columns=cols, dtype=float)


# ---------- forward returns / timing ----------

def test_forward_return_hand_values_and_entry_lag():
    p = panel([[10], [20], [15], [30], [30]], ["A"])
    f1 = forward_returns(p, horizon=1, lag=1)["A"].tolist()
    # signal at t enters at t+1: t0 -> 15/20-1, t1 -> 30/15-1, t2 -> 30/30-1, tail unknown
    assert f1[:3] == pytest.approx([-0.25, 1.0, 0.0])
    assert all(math.isnan(v) for v in f1[3:])
    f2 = forward_returns(p, horizon=2, lag=1)["A"].tolist()
    assert f2[:2] == pytest.approx([0.5, 1.0]) and math.isnan(f2[2])
    # the t0 -> t1 move (10 -> 20) is never credited to the t0 signal
    assert f1[0] != pytest.approx(1.0)


def test_label_exit_dates():
    ex = label_exit_dates(D, horizon=2, lag=1)
    assert ex.iloc[0] == D[3] and ex.iloc[1] == D[4] and pd.isna(ex.iloc[2])


def test_nonpositive_price_rejected():
    with pytest.raises(ValueError):
        forward_returns(panel([[10], [0]], ["A"]))


# ---------- IC ----------

def test_ic_perfect_positive_and_negative():
    f = panel([[1, 2, 3, 4, 5]], list("ABCDE"))
    up = panel([[3, 5, 7, 9, 11]], list("ABCDE"))
    down = panel([[0.5, 0.4, 0.3, 0.2, 0.1]], list("ABCDE"))
    for m in ("pearson", "spearman"):
        assert cross_sectional_corr(f, up, m, min_obs=3).iloc[0] == pytest.approx(1.0)
        assert cross_sectional_corr(f, down, m, min_obs=3).iloc[0] == pytest.approx(-1.0)


def test_pearson_vs_spearman_hand():
    f = panel([[1, 2, 3, 4]], list("ABCD"))
    r = panel([[1, 2, 3, 10]], list("ABCD"))
    # deviations f: -1.5,-.5,.5,1.5 ; r: -3,-2,-1,6 ; cov=14, ssf=5, ssr=50
    assert cross_sectional_corr(f, r, "pearson", 3).iloc[0] == pytest.approx(14 / math.sqrt(250))
    assert cross_sectional_corr(f, r, "spearman", 3).iloc[0] == pytest.approx(1.0)
    r2 = panel([[0.1, 0.3, 0.2, 0.4]], list("ABCD"))
    # 1 - 6*sum(d^2)/(n(n^2-1)) = 1 - 6*2/60
    assert cross_sectional_corr(f, r2, "spearman", 3).iloc[0] == pytest.approx(0.8)


def test_ic_nan_not_zero_for_constant_or_small_sample():
    f = panel([[1, 1, 1, 1], [1, 2, np.nan, np.nan]], list("ABCD"))
    r = panel([[1, 2, 3, 4], [1, 2, 3, 4]], list("ABCD"))
    ic = cross_sectional_corr(f, r, "pearson", min_obs=3)
    assert ic.isna().all()


def test_ic_summary_hand():
    s = ic_summary(pd.Series([0.1, 0.3, -0.1, 0.5, np.nan]))
    assert s["mean"] == pytest.approx(0.2)
    assert s["std"] == pytest.approx(math.sqrt(0.2 / 3))
    assert s["icir"] == pytest.approx(0.2 / math.sqrt(0.2 / 3))
    assert s["positive_ratio"] == pytest.approx(0.75) and s["n_dates"] == 4


# ---------- missing values, universe changes ----------

def test_missing_factor_and_daily_universe_change():
    cols = list("ABCDE")
    f = panel([[1, 2, np.nan, 4, 1000], [5, 1, 2, 3, 4]], cols)
    r = panel([[0.01, 0.02, 0.5, 0.04, -50], [0.0, 0.01, 0.02, 0.03, 0.04]], cols)
    u = panel([[1, 1, 1, 1, 0], [0, 1, 1, 1, 1]], cols).astype(bool)
    valid = valid_mask(f, u)
    assert valid.iloc[0].tolist() == [True, True, False, True, False]
    assert valid.iloc[1].tolist() == [False, True, True, True, True]
    ic = cross_sectional_corr(f.where(valid), r, "pearson", 3)
    # day0 uses A,B,D only: f=1,2,4 r=.01,.02,.04 -> perfectly linear; E's outlier excluded
    assert ic.iloc[0] == pytest.approx(1.0)
    # day1 uses B..E: f=1,2,3,4 r=.01..04 -> 1 ; A (f=5) is out of the universe
    assert ic.iloc[1] == pytest.approx(1.0)


def test_coverage_counts():
    cols = list("ABCDE")
    price = panel([[10] * 5, [10, 11, np.nan, 10, 10], [11, 12, 10, 10, 10], [11] * 5, [11] * 5], cols, D)
    f = panel([[1, 2, np.nan, 4, 5]] * 5, cols, D)
    u = panel([[1, 1, 1, 1, 0]] * 5, cols, D).astype(bool)
    res = evaluate_factor(f, price, direction=1, n_groups=2, universe=u, min_obs=2)
    cov = res["coverage"].iloc[0]
    assert cov["universe_count"] == 4 and cov["valid_count"] == 3
    assert cov["factor_coverage"] == pytest.approx(0.75)
    assert cov["label_coverage"] == pytest.approx(1.0)
    # day0 label for any stock needs price on D1 and D2: all present except C (excluded anyway)
    assert res["coverage"].iloc[3]["label_coverage"] == pytest.approx(0.0)


# ---------- groups ----------

COLS10 = [f"S{i:02d}" for i in range(1, 11)]


def test_groups_and_returns_hand():
    f = panel([list(range(1, 11))], COLS10)
    r = panel([[i / 100 for i in range(1, 11)]], COLS10)
    valid = f.notna()
    g = assign_groups(f, valid, 5, direction=1)
    assert g.iloc[0][["S10", "S09"]].tolist() == [0, 0]
    assert g.iloc[0][["S01", "S02"]].tolist() == [4, 4]
    ret, cov = group_returns(g, r, 5)
    assert ret.iloc[0, 0] == pytest.approx(0.095)
    assert ret.iloc[0, 4] == pytest.approx(0.015)
    assert ret.iloc[0, 0] - ret.iloc[0, 4] == pytest.approx(0.08)
    g_neg = assign_groups(f, valid, 5, direction=-1)
    assert group_returns(g_neg, r, 5)[0].iloc[0, 0] == pytest.approx(0.015)


def test_group_weights_and_missing_return():
    f = panel([list(range(1, 11))], COLS10)
    r = panel([[i / 100 for i in range(1, 11)]], COLS10)
    g = assign_groups(f, f.notna(), 5, 1)
    w = panel([[1] * 8 + [1, 3]], COLS10)
    assert group_returns(g, r, 5, w)[0].iloc[0, 0] == pytest.approx((0.10 * 3 + 0.09) / 4)
    r_missing = r.copy()
    r_missing.loc[:, "S10"] = np.nan
    ret, cov = group_returns(g, r_missing, 5)
    assert ret.iloc[0, 0] == pytest.approx(0.09) and cov.iloc[0, 0] == pytest.approx(0.5)


def test_too_few_stocks_gives_no_groups():
    f = panel([[1, 2, 3]], list("ABC"))
    assert assign_groups(f, f.notna(), 5, 1).isna().all().all()


def test_direction_must_be_fixed():
    f = panel([[1, 2, 3]], list("ABC"))
    with pytest.raises(ValueError):
        assign_groups(f, f.notna(), 2, direction=0)


def test_cumulative_non_overlapping():
    s = pd.Series([0.1, 0.5, -0.2, 0.5, 0.1], index=D)
    assert cumulative_returns(s, horizon=2).tolist() == pytest.approx([1.1, 0.88, 0.968])
    s2 = s.copy()
    s2.iloc[2] = np.nan
    out = cumulative_returns(s2, horizon=2)
    assert out.iloc[0] == pytest.approx(1.1) and out.iloc[1:].isna().all()


def test_turnover_and_rank_autocorr():
    g = panel([[0, 0, 1, 1], [1, 0, 0, 1]], list("ABCD"))
    t = group_turnover(g, 0)
    assert math.isnan(t.iloc[0]) and t.iloc[1] == pytest.approx(0.5)
    f_same = panel([[1, 2, 3, 4], [10, 20, 30, 40]], list("ABCD"))
    f_flip = panel([[1, 2, 3, 4], [4, 3, 2, 1]], list("ABCD"))
    assert rank_autocorr(f_same, f_same.notna(), 1, 3).iloc[1] == pytest.approx(1.0)
    assert rank_autocorr(f_flip, f_flip.notna(), 1, 3).iloc[1] == pytest.approx(-1.0)


# ---------- leakage and look-ahead ----------

def random_walk(n_dates=200, n_stocks=50, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_dates)
    cols = [f"X{i:03d}" for i in range(n_stocks)]
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_dates, n_stocks)), 0)), idx, cols)


def test_date_misalignment_is_detected():
    p = random_walk()
    known_at_t = p / p.shift(1) - 1           # realised by close t: legitimate
    realised_next = p.shift(-1) / p - 1       # realised only at t+1: leaky if lag=0
    ok = evaluate_factor(known_at_t, p, direction=1, lag=1)["rank_ic_summary"]["mean"]
    assert abs(ok) < 0.05
    leak = evaluate_factor(realised_next, p, direction=1, lag=0)["rank_ic_summary"]["mean"]
    assert leak == pytest.approx(1.0)
    # same factor with the correct entry lag carries no information on a random walk
    fixed = evaluate_factor(realised_next, p, direction=1, lag=1)["rank_ic_summary"]["mean"]
    assert abs(fixed) < 0.05


def test_ex_post_best_group_is_biased_and_train_direction_is_not():
    in_sample, out_sample = [], []
    for seed in range(60):
        p = random_walk(160, 50, seed)
        noise = pd.DataFrame(np.random.default_rng(1000 + seed).normal(size=p.shape), p.index, p.columns)
        res = evaluate_factor(noise, p, direction=1, n_groups=5)
        g = res["group_returns"]
        in_sample.append(g.mean().max() - g.mean().mean())      # best group picked after the fact
        train_end = p.index[79]
        d = choose_direction(res["rank_ic"], res["label_exit_dates"], train_end)
        test = res["long_short"][res["long_short"].index > train_end] * d
        out_sample.append(test.mean())
    in_sample, out_sample = np.array(in_sample), np.array(out_sample)
    assert (in_sample > 0).all()                               # always positive by construction
    se = out_sample.std(ddof=1) / math.sqrt(len(out_sample))
    assert abs(out_sample.mean()) < 3 * se                     # no edge out of sample
    assert in_sample.mean() > 3 * abs(out_sample.mean())


def test_choose_direction_uses_only_matured_labels():
    idx = pd.bdate_range("2025-01-01", periods=6)
    ic = pd.Series([-0.1, -0.2, 0.9, 0.9, 0.9, 0.9], idx)
    exits = label_exit_dates(idx, horizon=1, lag=1)            # exit of row i is row i+2
    assert choose_direction(ic, exits, idx[3]) == -1           # only rows 0,1 have matured
    with pytest.raises(ValueError):
        choose_direction(ic, exits, idx[1])


def test_as_of_blanks_immature_labels():
    p = random_walk(30, 20, 3)
    f = p / p.shift(5) - 1
    res = evaluate_factor(f, p, direction=1, horizon=3, as_of=p.index[19], min_obs=5)
    fwd = res["forward_returns"]
    # exit row = t+4 <= 19 -> t <= 15
    assert fwd.iloc[15].notna().all() and fwd.iloc[16:].isna().all().all()


def test_no_future_information():
    p = random_walk(60, 30, 7)
    f = p / p.shift(5) - 1
    base = evaluate_factor(f, p, direction=1, horizon=2, min_obs=5)
    p2 = p.copy()
    p2.iloc[40:] *= np.random.default_rng(9).uniform(0.5, 1.5, p2.iloc[40:].shape)
    f2 = p2 / p2.shift(5) - 1
    alt = evaluate_factor(f2, p2, direction=1, horizon=2, min_obs=5)
    # labels of t <= 36 exit at t+3 <= 39: untouched by the change from row 40 on
    pd.testing.assert_series_equal(base["rank_ic"].iloc[:37], alt["rank_ic"].iloc[:37])
    pd.testing.assert_frame_equal(base["group_returns"].iloc[:37], alt["group_returns"].iloc[:37])


def test_reproducible():
    p = random_walk(50, 20, 11)
    f = p / p.shift(3) - 1
    a = evaluate_factor(f, p, direction=-1, min_obs=5)
    b = evaluate_factor(f.copy(), p.copy(), direction=-1, min_obs=5)
    for k in ("ic", "rank_ic", "long_short"):
        pd.testing.assert_series_equal(a[k], b[k])
    pd.testing.assert_frame_equal(a["group_returns"], b["group_returns"])
    assert a["ic_summary"] == b["ic_summary"] or all(
        (x == y) or (math.isnan(x) and math.isnan(y)) for x, y in zip(a["ic_summary"].values(), b["ic_summary"].values()))


def test_inputs_not_mutated():
    p = random_walk(30, 10, 5)
    f = p / p.shift(2) - 1
    p0, f0 = p.copy(), f.copy()
    evaluate_factor(f, p, direction=1, min_obs=3)
    pd.testing.assert_frame_equal(p, p0)
    pd.testing.assert_frame_equal(f, f0)
