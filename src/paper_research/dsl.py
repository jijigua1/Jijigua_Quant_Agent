"""Mapping factor IR onto the main Agent's controlled 19-operator expression DSL (no Python execution).

The operator catalog below is a pinned description of research_agent.factor_expression 1.0.0 (the main
Agent's DSL); this module does not import that package. compile_ir() either produces DSL nodes that
satisfy the DSL contract, or returns the exact reasons why the research definition cannot be expressed.
It never shortens a window, swaps an input field or drops an operation to make a formula fit.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from .factor_ir import walk

DSL_CATALOG = {
    "reference": "research_agent.factor_expression VERSION 1.0.0 (main Agent, 19 operators)",
    "fields": ["open", "high", "low", "close", "volume", "amount"],
    "leaf": ["field", "constant"],
    "unary": ["neg", "abs", "cs_rank", "cs_zscore"],
    "window": ["delay", "diff", "returns", "rolling_mean", "rolling_std", "rolling_rank"],
    "binary": ["add", "sub", "mul", "div", "min", "max", "rolling_corr"],
    "limits": {"window_min": 1, "window_max": None, "history_max": None, "nodes_max": 40, "depth_max": 8,
               "std_corr_window_min": 2},
    "semantics": {"rolling": "full window required (min_periods = window)", "cs_zscore": "ddof=1",
                  "rolling_std": "ddof=1", "div": "zero denominator -> NaN", "min/max": "element-wise, NOT rolling extrema",
                  "cs_rank": "average ties, percentile"},
}
CATALOG_SHA256 = hashlib.sha256(json.dumps(DSL_CATALOG, sort_keys=True).encode()).hexdigest()
OPERATORS = DSL_CATALOG["leaf"] + DSL_CATALOG["unary"] + DSL_CATALOG["window"] + DSL_CATALOG["binary"]
assert len(OPERATORS) == 19

UNSUPPORTED_OPS = {
    "log": "logarithm is not a DSL operator",
    "exp": "exponential is not a DSL operator",
    "sqrt": "square root is not a DSL operator",
    "sign": "sign is not a DSL operator",
    "pow": "general powers are not DSL operators (only x^2 via mul is expressible)",
    "ts_max": "rolling maximum over a window is not available (DSL min/max are element-wise)",
    "ts_min": "rolling minimum over a window is not available (DSL min/max are element-wise)",
    "ema": "recursive exponential smoothing is not a DSL operator (trusted IR executor)",
    "ts_prod": "window product is not a DSL operator (trusted IR executor)",
    "ts_rank": "rolling rank of an IR window body is not mapped onto the DSL (trusted IR executor)",
    "ts_corr": "rolling correlation of IR window bodies is not mapped onto the DSL (trusted IR executor)",
    "ts_cov": "rolling covariance is not a DSL operator (trusted IR executor)",
}


class _Builder:
    def __init__(self):
        self.nodes, self.memo, self.depth = [], {}, []

    def add(self, node, depth):
        key = json.dumps(node, sort_keys=True)
        if key in self.memo:
            return self.memo[key]
        self.nodes.append(node)
        self.depth.append(depth)
        self.memo[key] = len(self.nodes) - 1
        return self.memo[key]


def compile_ir(ir, field_map):
    """field_map: formula symbol -> DSL field name (or None when the input is not a DSL field).

    Returns {"status", "reasons", "expression" (DSL JSON or None), "history", "nodes"}. Status values:
      expressible                 compiles within every DSL limit
      contract_limit_exceeded     operations exist, but a window/history/size limit is exceeded
      requires_new_implementation an operation or input field has no DSL counterpart
    """
    reasons, limit_reasons = [], []
    for n in walk(ir):
        if n["op"] in UNSUPPORTED_OPS and not (n["op"] == "pow" and n["args"][1] == {"op": "const", "value": 2.0}):
            reasons.append({"code": "UNSUPPORTED_OPERATOR", "op": n["op"], "detail": UNSUPPORTED_OPS[n["op"]]})
        if n["op"] == "field":
            fld = field_map.get(n["symbol"])
            if fld not in DSL_CATALOG["fields"]:
                reasons.append({"code": "FIELD_NOT_IN_DSL", "symbol": n["symbol"], "detail":
                                f"input '{n['symbol']}' maps to {fld!r}, not one of {DSL_CATALOG['fields']}"})
            if n["lag"]["base"] < 0:
                reasons.append({"code": "FUTURE_REFERENCE", "symbol": n["symbol"], "detail": "t+k reference cannot be a signal input"})
    if reasons:
        return {"status": "requires_new_implementation", "reasons": _dedupe(reasons), "expression": None}
    b = _Builder()
    lim = DSL_CATALOG["limits"]

    def emit(node, bind_shift, depth):
        """Returns (index, history, unit). bind_shift: extra lag applied to every field (window offset)."""
        op = node["op"]
        if op == "field":
            lag = node["lag"]["base"] + bind_shift
            unit = (0, 1) if field_map[node["symbol"]] == "volume" else (1, 1) if field_map[node["symbol"]] == "amount" else (1, 0)
            idx = b.add({"op": "field", "field": field_map[node["symbol"]]}, 1)
            if lag:
                if lim["window_max"] is not None and lag > lim["window_max"]:
                    limit_reasons.append({"code": "WINDOW_ABOVE_LIMIT", "detail": f"lag {lag} > {lim['window_max']}"})
                idx = b.add({"op": "delay", "args": [idx], "window": lag}, 2)
            return idx, lag, unit
        if op == "const":
            return b.add({"op": "constant", "value": node["value"]}, 1), 0, (0, 0)
        if op in ("ts_mean", "ts_sum", "ts_std"):
            body = node["args"][0]
            if any(n["op"] == "field" and n["lag"].get("var") != node["var"] for n in walk(body)) or \
                    any(n["op"].startswith("ts_") for n in walk(body)):
                limit_reasons.append({"code": "WINDOW_BODY_NOT_UNIFORM", "detail": "every field in a window body must be indexed by the window variable"})
            w = node["end"] - node["start"] + 1
            inner, h, unit = emit(body, bind_shift + node["start"], 2)
            if w < lim["window_min"] or lim["window_max"] is not None and w > lim["window_max"]:
                limit_reasons.append({"code": "WINDOW_ABOVE_LIMIT", "detail": f"window {w} outside {lim['window_min']}..{lim['window_max']}"})
            if op == "ts_std" and w < lim["std_corr_window_min"]:
                limit_reasons.append({"code": "WINDOW_ABOVE_LIMIT", "detail": "std window must be >= 2"})
            roll = b.add({"op": "rolling_std" if op == "ts_std" else "rolling_mean", "args": [inner], "window": w}, 3)
            hist = h + w - 1
            if op == "ts_sum":
                c = b.add({"op": "constant", "value": float(w)}, 1)
                roll = b.add({"op": "mul", "args": [roll, c]}, 4)
            return roll, hist, unit
        if op in ("neg", "abs", "cs_rank", "cs_zscore"):
            a, h, unit = emit(node["args"][0], bind_shift, depth + 1)
            unit = (0, 0) if op in ("cs_rank", "cs_zscore") else unit
            return b.add({"op": op, "args": [a]}, depth), h, unit
        if op == "pow":                                   # only x^2, as mul(x, x)
            a, h, unit = emit(node["args"][0], bind_shift, depth + 1)
            return b.add({"op": "mul", "args": [a, a]}, depth), h, tuple(2 * u for u in unit)
        if op in ("maximum", "minimum"):                  # DSL min/max are element-wise (same semantics)
            a, ha, ua = emit(node["args"][0], bind_shift, depth + 1)
            c, hc, uc = emit(node["args"][1], bind_shift, depth + 1)
            if ua != uc and (0, 0) not in (ua, uc):
                limit_reasons.append({"code": "UNIT_MISMATCH", "detail": f"{op} of units {ua} and {uc}"})
            return b.add({"op": "max" if op == "maximum" else "min", "args": [a, c]}, depth), max(ha, hc), ua if ua != (0, 0) else uc
        if op in ("add", "sub", "mul", "div"):
            a, ha, ua = emit(node["args"][0], bind_shift, depth + 1)
            c, hc, uc = emit(node["args"][1], bind_shift, depth + 1)
            if op in ("add", "sub") and ua != uc and (0, 0) not in (ua, uc):
                limit_reasons.append({"code": "UNIT_MISMATCH", "detail": f"{op} of units {ua} and {uc}"})
            unit = ua if op in ("add", "sub") else tuple(x + (1 if op == "mul" else -1) * y for x, y in zip(ua, uc))
            if op in ("add", "sub") and (ua == (0, 0)) and uc != (0, 0):
                unit = uc
            return b.add({"op": op, "args": [a, c]}, depth), max(ha, hc), unit
        raise ValueError(op)

    out, hist, _unit = emit(ir, 0, 1)
    # the DSL requires the output to be the last node and every node to be used: re-order by reachability
    nodes = _prune(b.nodes, out)
    if lim["history_max"] is not None and hist > lim["history_max"]:
        limit_reasons.append({"code": "HISTORY_ABOVE_LIMIT", "detail": f"history {hist} > {lim['history_max']}"})
    if len(nodes) > lim["nodes_max"]:
        limit_reasons.append({"code": "TOO_MANY_NODES", "detail": f"{len(nodes)} > {lim['nodes_max']}"})
    expression = {"nodes": nodes, "output": len(nodes) - 1}
    if _depth(nodes) > lim["depth_max"]:
        limit_reasons.append({"code": "TOO_DEEP", "detail": f"depth {_depth(nodes)} > {lim['depth_max']}"})
    if limit_reasons:
        return {"status": "contract_limit_exceeded", "reasons": _dedupe(limit_reasons), "expression": expression,
                "history": hist, "note": "the definition is kept as written; it is not shortened to fit the DSL"}
    return {"status": "expressible", "reasons": [], "expression": expression, "history": hist}


def _dedupe(items):
    seen, out = set(), []
    for x in items:
        k = json.dumps(x, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _prune(nodes, out):
    keep = {out}
    for i in range(out, -1, -1):
        if i in keep:
            keep.update(nodes[i].get("args", []))
    order = sorted(keep)
    remap = {old: new for new, old in enumerate(order)}
    pruned = []
    for old in order:
        n = dict(nodes[old])
        if "args" in n:
            n["args"] = [remap[a] for a in n["args"]]
        pruned.append(n)
    return pruned


def _depth(nodes):
    d = []
    for n in nodes:
        d.append(1 + max((d[a] for a in n.get("args", [])), default=0))
    return d[-1] if d else 0


def interpret(expression, panels):
    """Reference interpreter of the DSL semantics above (trusted toolkit code, for equivalence tests)."""
    anchor = panels["close"]
    res = []
    for node in expression["nodes"]:
        op, w = node["op"], node.get("window")
        if op == "field":
            v = panels[node["field"]]
        elif op == "constant":
            v = anchor * 0 + node["value"]
        else:
            a = res[node["args"][0]]
            b = res[node["args"][1]] if len(node.get("args", [])) > 1 else None
            v = {"neg": lambda: -a, "abs": lambda: a.abs(), "delay": lambda: a.shift(w), "diff": lambda: a - a.shift(w),
                 "returns": lambda: a / a.shift(w).replace(0, np.nan) - 1,
                 "cs_rank": lambda: a.rank(axis=1, method="average", pct=True),
                 "cs_zscore": lambda: a.sub(a.mean(axis=1), axis=0).div(a.std(axis=1, ddof=1).replace(0, np.nan), axis=0),
                 "rolling_mean": lambda: a.rolling(w, min_periods=w).mean(),
                 "rolling_std": lambda: a.rolling(w, min_periods=w).std(ddof=1),
                 "add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b,
                 "div": lambda: a / b.replace(0, np.nan), "min": lambda: np.minimum(a, b), "max": lambda: np.maximum(a, b),
                 "rolling_corr": lambda: a.rolling(w, min_periods=w).corr(b)}[op]()
        res.append(v.replace([np.inf, -np.inf], np.nan))
    return res[expression["output"]]
