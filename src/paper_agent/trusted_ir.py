"""Reviewed, vectorised executor for the closed Factor IR grammar (human-written; not model output).

Semantics are those of paper_research.factor_ir.evaluate (the trusted reference evaluator): a window value exists
only when every lag in the window is a finite observation, std uses ddof=1, x/0 -> NaN, log/sqrt outside the domain
-> NaN, cs_rank is the average-method percentile rank, ±inf -> NaN at the end. Windows are computed with pandas
rolling on the shift-equivariant window body (O(T x N) memory instead of stacking L shifted copies), which makes the
full 1455 x 5427 published panel feasible. Equivalence with the reference evaluator is tested on fixtures.

Implementation choices are deliberately different from the reference evaluator, so that each checks the other:
  ema       closed-form weights accumulated over W shifted views (the reference runs the literal recursion)
  ts_prod   sign parity x exp(sum log|x|), zero count (the reference multiplies the stacked window)
  ts_rank   pandas rolling rank (average ties, percentile)
  ts_corr / ts_cov  pandas rolling moments on the full window
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paper_research.factor_ir import (IR_SEMANTICS, LEGACY_SEMANTICS, IRError, PAIR_WINDOWS, TS_OPS, ema_weights, sign_scale,
                                     tolerant_sign, walk, warmup)

TS = {"ts_sum": "sum", "ts_mean": "mean", "ts_std": "std", "ts_max": "max", "ts_min": "min"}


def _depends_on(node, var):
    return any(n["op"] == "field" and n["lag"].get("var") == var for n in walk(node))


def _check_window_body(body, var):
    """The body must reference `var` in every field lag (then body(k) == body(0) shifted by k)."""
    for n in walk(body):
        if n["op"] == "field" and n["lag"].get("var") != var:
            raise IRError("UNSUPPORTED_WINDOW_BODY", f"field {n['symbol']} inside a window without the window lag")


def _full(frame, length):
    """True where the last `length` rows are all finite."""
    return np.isfinite(frame).astype(float).rolling(length, min_periods=length).sum().eq(length)


def _ema(x, node):
    """sum_k w[k] * x[t-k] over the last W rows (closed-form weights of the finite-window recursion)."""
    w = ema_weights(node)
    a = x.to_numpy(dtype=float)
    finite = np.isfinite(a)
    z = np.where(finite, a, 0.0)
    out = np.zeros_like(z)
    for k, wk in enumerate(w):
        if k == 0:
            out += wk * z
        else:
            out[k:] += wk * z[:-k]
    count = pd.DataFrame(finite.astype(float), index=x.index, columns=x.columns).rolling(len(w), min_periods=len(w)).sum()
    out = np.where(count.to_numpy() == len(w), out, np.nan)
    return pd.DataFrame(out, index=x.index, columns=x.columns)


def _prod(b0, length):
    a = b0.to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        logs = pd.DataFrame(np.where(a != 0, np.log(np.abs(a)), 0.0), index=b0.index, columns=b0.columns)
    neg = pd.DataFrame((a < 0).astype(float), index=b0.index, columns=b0.columns)
    zero = pd.DataFrame((a == 0).astype(float), index=b0.index, columns=b0.columns)
    r = lambda f: f.rolling(length, min_periods=length).sum()          # noqa: E731
    sign = np.where(np.mod(r(neg).to_numpy(), 2) == 1, -1.0, 1.0)
    out = np.where(r(zero).to_numpy() > 0, 0.0, sign * np.exp(r(logs).to_numpy()))
    return pd.DataFrame(np.where(_full(b0, length).to_numpy(), out, np.nan), index=b0.index, columns=b0.columns)


def evaluate(ir, panels, symbols, semantics=IR_SEMANTICS):
    if warmup(ir)["uses_future"]:
        raise IRError("FUTURE_REFERENCE", "formula references t+k; refusing to evaluate")

    def ev(node, var=None):
        op = node["op"]
        if op == "field":
            frame = panels[symbols[node["symbol"]]].astype(float)
            # inside a window body the window lag is applied by the window itself (shift-equivariance)
            return frame.shift(node["lag"]["base"])
        if op == "const":
            return node["value"]
        if op in TS_OPS:
            bodies = []
            for body in node["args"]:
                _check_window_body(body, node["var"])
                b = ev(body, node["var"])
                if not isinstance(b, pd.DataFrame):
                    raise IRError("UNSUPPORTED_WINDOW_BODY", "window over a constant")
                bodies.append(b.replace([np.inf, -np.inf], np.nan))
            b0 = bodies[0]
            length = node["end"] - node["start"] + 1
            if op in TS:
                roll = b0.rolling(length, min_periods=length)
                out = getattr(roll, TS[op])() if op != "ts_std" else roll.std(ddof=1)
            elif op == "ts_prod":
                out = _prod(b0, length)
            elif op == "ts_rank":
                out = b0.rolling(length, min_periods=length).rank(method="average", ascending=True, pct=True)
            elif op in PAIR_WINDOWS:
                b1 = bodies[1]
                # both bodies must be finite on every row of the window (pairwise-complete is NOT used)
                both = b0.where(np.isfinite(b1)), b1.where(np.isfinite(b0))
                roll = both[0].rolling(length, min_periods=length)
                out = roll.cov(both[1], ddof=1) if op == "ts_cov" else roll.corr(both[1])
                if op == "ts_corr":
                    sx = both[0].rolling(length, min_periods=length).std(ddof=1)
                    sy = both[1].rolling(length, min_periods=length).std(ddof=1)
                    out = out.where((sx > 0) & (sy > 0))
            else:
                raise IRError("UNKNOWN_OP", op)
            return out.shift(node["start"])
        if op == "ema":
            x = ev(node["args"][0], var)
            if not isinstance(x, pd.DataFrame):
                raise IRError("UNSUPPORTED_WINDOW_BODY", "recursion over a constant")
            return _ema(x.replace([np.inf, -np.inf], np.nan), node)
        a = [ev(x, var) for x in node["args"]]
        with np.errstate(divide="ignore", invalid="ignore"):
            if op == "add":
                return a[0] + a[1]
            if op == "sub":
                return a[0] - a[1]
            if op == "mul":
                return a[0] * a[1]
            if op == "div":
                den = a[1].replace(0, np.nan) if isinstance(a[1], pd.DataFrame) else (np.nan if a[1] == 0 else a[1])
                return a[0] / den
            if op == "pow":
                return a[0] ** a[1]
            if op == "neg":
                return -a[0]
            if op == "abs":
                return a[0].abs()
            if op == "log":
                return np.log(a[0].where(a[0] > 0))
            if op == "exp":
                return np.exp(a[0])
            if op == "sqrt":
                return np.sqrt(a[0].where(a[0] >= 0))
            if op == "sign":                     # shared numerical-zero rule (same as the reference evaluator)
                if semantics == LEGACY_SEMANTICS:
                    return np.sign(a[0])
                return tolerant_sign(a[0], sign_scale(node, ev, var))
            if op == "cs_rank":
                return a[0].rank(axis=1, method="average", pct=True)
            if op == "cs_zscore":
                return a[0].sub(a[0].mean(axis=1), axis=0).div(a[0].std(axis=1, ddof=1).replace(0, np.nan), axis=0)
            if op in ("maximum", "minimum"):
                x, y = a
                if isinstance(x, pd.DataFrame) and isinstance(y, pd.DataFrame):
                    keep = x.ge(y) if op == "maximum" else x.le(y)
                    return x.where(keep, y).where(x.notna() & y.notna())
                frame, c = (x, y) if isinstance(x, pd.DataFrame) else (y, x)
                if not isinstance(frame, pd.DataFrame):
                    return max(x, y) if op == "maximum" else min(x, y)
                return frame.clip(lower=c) if op == "maximum" else frame.clip(upper=c)
        raise IRError("UNKNOWN_OP", op)

    out = ev(ir)
    if not isinstance(out, pd.DataFrame):
        raise IRError("CONSTANT_FACTOR", "the factor does not depend on any input")
    return out.replace([np.inf, -np.inf], np.nan)
