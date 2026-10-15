"""Trusted operator extension (2026-10-14): EMA family, element-wise max/min, rolling rank/corr/cov/prod.

Every operator is checked three ways: hand-computed known values, the literal-recursion / stacked reference evaluator
(paper_research.factor_ir.evaluate) against the vectorised trusted executor (paper_agent.trusted_ir.evaluate) on panels
with NaN, zeros and negative values, and a no-lookahead perturbation. MACD/RSI are also compared with independent
full-history pandas recursions within the stated truncation bound.
"""
import numpy as np
import pandas as pd
import pytest

from paper_agent.trusted_ir import evaluate as fast
from paper_research.factor_ir import IRError, SEED_WEIGHT, evaluate as ref, make_ema, parse_formula, render, warmup

SYM = {"C": "close", "V": "volume", "H": "high", "L": "low"}
MACD = (r"2 * ( \operatorname{ema}_{12}(C_{i,t}) - \operatorname{ema}_{26}(C_{i,t})"
        r" - \operatorname{ema}_{9}( \operatorname{ema}_{12}(C_{i,t}) - \operatorname{ema}_{26}(C_{i,t}) ) )")
RSI = (r"100 - \frac{100}{1 + \frac{\operatorname{rma}_{14}(\max(C_{i,t} - C_{i,t-1}, 0))}"
       r"{\operatorname{rma}_{14}(\max(C_{i,t-1} - C_{i,t}, 0))}}")
FORMULAS = [
    MACD, RSI,
    r"\operatorname{ema}_{5}(C_{i,t})", r"\operatorname{rma}_{6}(V_{i,t})", r"\operatorname{sma}_{9,2}(C_{i,t})",
    r"\operatorname{sma}_{4}(C_{i,t})",
    r"\max(H_{i,t} - L_{i,t}, |C_{i,t} - C_{i,t-1}|)", r"\min(C_{i,t}, 1)",
    r"\operatorname{tsrank}_{k=0}^{9}(V_{i,t-k})", r"\operatorname{corr}_{k=0}^{9}(C_{i,t-k}, V_{i,t-k})",
    r"\operatorname{cov}_{k=1}^{8}(C_{i,t-k}, V_{i,t-k})", r"\prod_{k=0}^{4} \frac{C_{i,t-k}}{C_{i,t-k-1}}",
    r"\prod_{k=0}^{3} (C_{i,t-k} - 10)",
]


def panel(seed=7, rows=260, cols=9):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-04", periods=rows)
    close = pd.DataFrame(10 + rng.normal(0, 1, (rows, cols)).cumsum(0), index=idx, columns=[f"c{j}" for j in range(cols)])
    high = close + rng.uniform(0, 1, close.shape)
    low = close - rng.uniform(0, 1, close.shape)
    volume = pd.DataFrame(rng.integers(0, 5, close.shape).astype(float), index=idx, columns=close.columns)   # zeros and ties
    close.iloc[30:33, 2] = np.nan                          # missing observations propagate
    close.iloc[100, 4] = 10.0                              # exact constant used by the product formula
    volume.iloc[50:70, 5] = 3.0                            # zero variance window for corr
    return {"close": close, "high": high, "low": low, "volume": volume}


def run(latex, fn, p):
    return fn(parse_formula(latex)["ir"], p, SYM)


@pytest.mark.parametrize("latex", FORMULAS)
def test_trusted_executor_equals_reference_evaluator(latex):
    p = panel()
    a, b = run(latex, ref, p), run(latex, fast, p)
    assert a.shape == b.shape and a.index.equals(b.index) and list(a.columns) == list(b.columns)
    assert (a.isna() == b.isna()).all().all(), latex                        # same NaN pattern (warmup, gaps, zero variance)
    both = a.notna() & b.notna()
    assert both.to_numpy().sum() > 0
    diff = (a - b).abs()[both].stack()
    tol = 1e-9 * a.abs()[both].stack() + 1e-12 * max(1.0, float(a.abs().max().max()))
    assert (diff <= tol).all(), (latex, float(diff.max()))


def test_known_values_by_hand():
    idx = pd.bdate_range("2024-01-01", periods=5)
    x = {"close": pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=idx)}
    # span N=3 -> alpha = 0.5; window W=3, seed = first value of the window
    ir = make_ema("span", 3, {"op": "field", "symbol": "C", "lag": {"base": 0, "var": None}}, window=3)
    for fn in (ref, fast):
        out = fn(ir, x, SYM)["a"].tolist()
        assert np.isnan(out[0]) and np.isnan(out[1])
        assert out[2:] == pytest.approx([2.25, 3.25, 4.25])               # 1 -> 1.5 -> 2.25 ; 2 -> 2.5 -> 3.25 ; ...
    # TA-Lib style seed: mean of the first N=2 values, alpha = 2/3, W = 4
    ir = make_ema("span", 2, {"op": "field", "symbol": "C", "lag": {"base": 0, "var": None}}, init="sma", window=4)
    for fn in (ref, fast):
        assert fn(ir, x, SYM)["a"].tolist()[3] == pytest.approx(3.5)        # seed 1.5 -> 2.5 -> 3.5
    # Chinese SMA(X, N=3, M=1): alpha = 1/3
    assert parse_formula(r"\operatorname{sma}_{3,1}(C_{i,t})")["ir"]["alpha"] == pytest.approx(1 / 3)
    # element-wise max with 0 and rolling rank of the latest value (average ties, percentile)
    y = {"close": pd.DataFrame({"a": [3.0, -1.0, 2.0, 2.0, 5.0]}, index=idx)}
    assert run(r"\max(C_{i,t}, 0)", fast, y)["a"].tolist() == [3.0, 0.0, 2.0, 2.0, 5.0]
    rk = run(r"\operatorname{tsrank}_{k=0}^{2}(C_{i,t-k})", fast, y)["a"].tolist()
    assert rk[2:] == pytest.approx([2 / 3, 2.5 / 3, 1.0])                  # [3,-1,2]: 2 is 2nd; [-1,2,2]: tie 2.5; [2,2,5]: top
    assert run(r"\prod_{k=0}^{1} C_{i,t-k}", fast, y)["a"].tolist()[1:] == pytest.approx([-3.0, -2.0, 4.0, 10.0])


def test_parsing_distinguishes_window_extremum_and_elementwise():
    assert parse_formula(r"\max(C_{i,t}, C_{i,t-1})")["ir"]["op"] == "maximum"
    assert parse_formula(r"\max_{0 \le k \le 4} C_{i,t-k}")["ir"]["op"] == "ts_max"
    assert parse_formula(r"\operatorname{sma}_{5}(C_{i,t})")["ir"]["op"] == "ts_mean"        # English SMA = simple mean
    assert parse_formula(r"\operatorname{sma}_{5,1}(C_{i,t})")["ir"]["op"] == "ema"         # Chinese SMA(N, M) recursion
    for bad in (r"\operatorname{ema}_{n}(C_{i,t})", r"\operatorname{ema}_{3,1}(C_{i,t})", r"\operatorname{sma}_{3,4}(C_{i,t})"):
        with pytest.raises(IRError):
            parse_formula(bad)


def test_truncation_bound_against_full_history_recursions():
    """Our finite-window EMA differs from a full-history recursion only through the stated seed weight."""
    p = panel(seed=11, rows=400, cols=6)
    c = p["close"].drop(columns=["c2"])                                   # no gaps: the full recursion is defined
    q = {"close": c}
    ours = run(MACD, fast, q)
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    dif = e12 - e26
    full = 2 * (dif - dif.ewm(span=9, adjust=False).mean())
    tail = ours.index[200:]                                                # well past the first W rows of both
    gap = (ours.loc[tail] - full.loc[tail]).abs().max().max()
    scale = (c.max().max() - c.min().min())
    assert gap <= 6 * SEED_WEIGHT * scale, gap                            # seed weights (<= 1e-3 each) times the price range
    ir = parse_formula(MACD)["ir"]
    w = warmup(ir)
    assert w["max_lag"] == 90 + 31 and not w["uses_future"]                # EMA26 W=91 (90 lags) nested in EMA9 W=32 (31 lags)
    assert "W=91" in render(ir) and "W=32" in render(ir)


def test_no_lookahead_for_every_new_operator():
    p = panel(seed=3)
    for latex in FORMULAS:
        base = run(latex, fast, p)
        q = {k: v.copy() for k, v in p.items()}
        for v in q.values():
            v.iloc[150:] = v.iloc[150:] * 1.7 + 3.0                       # change the future only
        after = run(latex, fast, q)
        pd.testing.assert_frame_equal(base.iloc[:150], after.iloc[:150], check_freq=False)


def test_long_window_and_recursion_performance_on_a_wide_panel():
    import time
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2020-01-02", periods=1455)
    c = pd.DataFrame(10 + rng.normal(0, 1, (1455, 800)).cumsum(0), index=idx)
    t0 = time.perf_counter()
    out = fast(parse_formula(MACD)["ir"], {"close": c}, SYM)
    assert time.perf_counter() - t0 < 20 and out.iloc[200:].notna().all().all()
