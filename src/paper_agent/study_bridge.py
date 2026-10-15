"""Run a factor through the Research Agent's own study pipeline (patched v0.7.0 copy).

DSL route  -> QuantBackend.expression_study (unchanged v0.7.0 tool path)
new route  -> QuantBackend.approved_study (candidate patch): the approved implementation from TrustedRegistry computes
             the factor; every computation (full panel and the truncated panels of the look-ahead gate) is compared with
             the reviewed trusted IR executor -- a mismatch aborts the study (IMPLEMENTATION_MISMATCH).
Data access, the Train/Validation pair, the 2026 embargo, metrics, PKL export and the HTML report are the Agent's.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from paper_research.factor_ir import walk

from .ledger import sha256_text
from .trusted_ir import evaluate as trusted_evaluate


class ImplementationMismatch(RuntimeError):
    pass


def ir_latex(ir):
    """Matplotlib-mathtext-safe LaTeX for a Factor IR (rows of the daily panel)."""
    names = {"close": "C", "open": "O", "high": "H", "low": "L", "volume": "V", "amount": "A"}

    def r(n):
        op = n["op"]
        if op == "field":
            lag = n["lag"]
            t = "t" + (f"-{lag['var']}" if lag.get("var") else "") + (f"-{lag['base']}" if lag["base"] > 0 else "")
            return f"{names.get(n['symbol'], n['symbol'])}_{{{t},i}}"
        if op == "const":
            v = n["value"]
            return str(int(v)) if v == int(v) else str(v)
        a = [r(x) for x in n.get("args", [])]
        if op == "add":
            return f"\\left({a[0]}+{a[1]}\\right)"
        if op == "sub":
            return f"\\left({a[0]}-{a[1]}\\right)"
        if op == "mul":
            return f"{a[0]}\\cdot {a[1]}"
        if op == "div":
            return f"\\frac{{{a[0]}}}{{{a[1]}}}"
        if op == "abs":
            return f"\\left|{a[0]}\\right|"
        if op == "neg":
            return f"-{a[0]}"
        if op.startswith("ts_"):
            name = {"ts_max": "\\max", "ts_min": "\\min", "ts_mean": "\\mathrm{Mean}", "ts_sum": "\\sum", "ts_std": "\\mathrm{Std}",
                    "ts_prod": "\\prod", "ts_rank": "\\mathrm{RankTS}", "ts_corr": "\\mathrm{Corr}", "ts_cov": "\\mathrm{Cov}"}[op]
            return f"{name}_{{{n['start']}\\leq {n['var']}\\leq {n['end']}}}\\left({','.join(a)}\\right)"
        if op == "ema":
            label = {"span": f"EMA}}_{{{n['n']}", "wilder": f"RMA}}_{{{n['n']}", "ratio": f"SMA}}_{{{n['n']},{n['m']}"}[n["smoothing"]]
            return f"\\mathrm{{{label}}}^{{W={n['window']}}}\\left({a[0]}\\right)"
        if op in ("maximum", "minimum"):
            return f"\\{op[:3]}\\left({a[0]},{a[1]}\\right)"
        return f"\\mathrm{{{op}}}\\left({','.join(a)}\\right)"
    return "f_{t,i}=" + r(ir)


def make_backend(deploy_root, registry, crosscheck_log):
    """QuantBackend from the isolated deployment's configs, with the approved registry and the IR cross-check."""
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    root = Path(deploy_root)
    catalog = ResourceCatalog(root / "config/resources.json")
    backend = QuantBackend(catalog, root / "config/research.json")
    backend.approved_registry = registry

    def crosscheck(definition, inputs, out):
        t0 = time.time()
        symbols = {i["symbol"]: i["field"] for i in registry.load(definition["implementation_id"])[0]["contract"]["inputs"]}
        ref = trusted_evaluate(definition["ir"], inputs, symbols)
        a, b = out.to_numpy(dtype=float), ref.to_numpy(dtype=float)
        nan_mismatch = int((np.isnan(a) != np.isnan(b)).sum())
        both = ~np.isnan(a) & ~np.isnan(b)
        diff = np.abs(a[both] - b[both])
        max_abs = float(diff.max()) if both.any() else 0.0
        scale = float(np.abs(b[both]).max()) if both.any() else 1.0
        # per-cell relative tolerance (values can be ~1e-8, e.g. |return| / traded amount)
        bad = int((diff > 1e-9 * np.abs(b[both]) + 1e-12 * scale).sum()) if both.any() else 0
        rel = float((diff / np.maximum(np.abs(b[both]), 1e-300)).max()) if both.any() else 0.0
        rec = {"rows": int(a.shape[0]), "cols": int(a.shape[1]), "non_nan_cells": int(both.sum()), "nan_pattern_mismatch": nan_mismatch,
               "max_abs_diff": max_abs, "max_rel_diff": rel, "cells_outside_tolerance": bad, "reference_max_abs": scale,
               "seconds": round(time.time() - t0, 3)}
        crosscheck_log.append(rec)
        if nan_mismatch or bad:
            raise ImplementationMismatch(json.dumps(rec))
    backend.approved_crosscheck = crosscheck
    return backend


class _Store:
    def __init__(self, path):
        self.path = path


def task_context(task_id, goal, *, hypothesis, reason, session_id, events, deadline_seconds=1800, resources=(), core_sha="paper_agent"):
    def emit(kind, payload):
        events.append({"kind": kind, "payload": payload, "time": time.time()})
    return {"task_id": task_id, "session_id": session_id, "goal": goal, "store": _Store("paper_agent ledger"), "emit": emit,
            "core_code_sha256": core_sha, "provider": {"provider": "deepseek", "model": "deepseek-flash"},
            "deadline": time.monotonic() + deadline_seconds, "authorized_resources": tuple(resources),
            "hypothesis": hypothesis, "change_reason": reason}


def run_study(backend, plan, *, ledger, implementation=None, factor_name, hypothesis, reason, n_groups=5):
    """Returns the Agent's study result (paths to factor.pkl, HTML report, metrics). Train resource auto-pairs Validation."""
    train = "gpushare:train2020_2023"
    events = []
    ctx = task_context(ledger.task_id, ledger.state["goal"], hypothesis=hypothesis, reason=reason, session_id=ledger.task_id,
                       events=events, resources=(train, "gpushare:validation2024_2025"))
    horizon = plan["choices"]["horizon"]["n"]
    t0 = time.time()
    if plan["route"] == "dsl":
        if horizon > 10:
            horizon = 10
        result = backend.expression_study(train, plan["dsl"]["expression"], hypothesis, reason, horizon, n_groups, "raw", ctx,
                                          factor_name=factor_name)
    else:
        result = backend.approved_study(train, implementation["implementation_id"], hypothesis, reason, horizon, n_groups, "raw", ctx,
                                        factor_name=factor_name, latex=ir_latex(plan["ir_execution_json"]))
    seconds = time.time() - t0
    ledger.state["usage"]["compute_seconds"] = round(ledger.state["usage"]["compute_seconds"] + seconds, 3)
    ledger.save()
    ledger.event("STUDY_COMPLETED", {"study_id": result.get("study_id"), "artifact_path": result.get("artifact_path"),
                                     "seconds": round(seconds, 1), "stages": [e["payload"].get("stage") for e in events if e["kind"] == "RESEARCH_STAGE"]})
    return result, events, seconds


def attach_provenance(backend, result, files):
    """Add paper/plan/approval files to the study's code/ folder and refresh the manifest inventory."""
    run = Path(result["artifact_path"])
    for name, text in files.items():
        (run / "code" / name).write_text(text, encoding="utf-8")
    backend.artifacts.update_manifest(run, {"files": backend.artifacts.inventory(run),
                                           "paper_agent_files": {n: sha256_text(t) for n, t in files.items()}})
