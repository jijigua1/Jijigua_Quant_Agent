"""Implementation route: DSL first; otherwise a DeepSeek-designed Python candidate, checked and repaired without running it.

The candidate is text. It is analysed with paper_research.candidate.analyze_source (AST only) against the contract
derived from the research task; static failures are fed back to the model for a bounded number of revisions. Every
version is stored with its SHA-256. The final bundle (source, contract, independent tests whose expected values come
from the trusted reference evaluator, static analysis, manifest) is READY_FOR_REVIEW and is never executed here.
"""
from __future__ import annotations

import json
from pathlib import Path

from paper_research.candidate import analyze_source, build_candidate, contract_from_task, write_candidate_bundle
from paper_research.factor_ir import render

from .ledger import sha256_text
from .model import ask_json

SCHEMA = {"type": "object", "required": ["design", "source"],
          "properties": {"design": {"type": "object", "required": ["summary", "missing_dsl_capabilities", "algorithm_steps",
                                                                     "window_semantics", "nan_policy"]},
                         "source": {"type": "string"}}}

SYSTEM = """You are implementing one quantitative factor as a reviewed research algorithm. Return ONE JSON object:
{"design": {"summary", "missing_dsl_capabilities": [...], "algorithm_steps": [...], "window_semantics", "nan_policy",
            "units", "complexity"}, "source": "<complete Python module>"}
Rules for "source" (it will be statically analysed, then reviewed by a human before it may ever run):
- Define exactly `def compute(panels):` where panels maps input field name -> pandas DataFrame (rows = trading dates in
  ascending order, columns = securities). Return ONE DataFrame with the same index and columns.
- Import only numpy and pandas. No file, network, OS, reflection, exec/eval, pickle, threads, globals.
- Strictly causal: value at row t may use rows <= t only. Never shift(-k), center=True, bfill, [::-1], or a statistic
  over the whole time axis (e.g. df.mean() over dates, expanding over the whole sample is fine only if causal).
- Rolling windows must require full history: rolling(w, min_periods=w). Do not shorten or lengthen the window: the
  contract states the exact number of rows of history (warmup) the factor needs.
- Never fill NaN (no fillna/ffill-to-invent data), never dropna; propagate NaN. Replace zero denominators with NaN
  (x / y.replace(0, np.nan)); replace +/-inf with NaN at the end.
- Use vectorised pandas/numpy only (the real panel is ~1455 x 5427); avoid Python loops over rows or columns.
- Read only the declared input fields.
The contract and the formula are authoritative; if something is ambiguous, say so in design.summary rather than guess."""


STRICT_WARNINGS = {"PARTIAL_WINDOW", "NAN_FILLED", "HISTORY_BEYOND_DECLARED", "WINDOW_SHORTER_THAN_DECLARED", "UNDECLARED_INPUT"}


def route(task):
    return "dsl" if task["dsl"]["status"] == "expressible" else "trusted_ir"


def design(task, client, ledger, *, max_revisions=None, out_dir=None):
    """Model-designed candidate with a static-analysis repair loop. Returns (candidate dict, history)."""
    contract = contract_from_task(task)
    max_revisions = max_revisions if max_revisions is not None else ledger.state["budget"]["design_revisions"]
    prompt = ("CONTRACT (authoritative):\n" + json.dumps({k: contract[k] for k in ("entrypoint", "inputs", "output", "time_alignment",
                                                                                      "warmup", "panel_frequency")}, ensure_ascii=False)
              + f"\nFORMULA (Factor IR, rows of the daily panel): {render(contract['ir'])}\n"
              + "IR JSON: " + json.dumps(contract["ir"]) + "\n"
              + "WHY NOT THE 19-OPERATOR DSL: " + json.dumps(task["dsl"]["reasons"], ensure_ascii=False) + "\n"
              + "DSL limits: fields open/high/low/close/volume only, rolling mean/std/rank/corr windows 1..60, history <= 120, no rolling max/min.\n"
              + "Design the algorithm and write the module.")
    history, messages_extra = [], ""
    src = None
    for rev in range(max_revisions + 1):
        obj, rec = ask_json(client, ledger, purpose="algorithm_design", system=SYSTEM, user=prompt + messages_extra,
                            schema=SCHEMA, max_tokens=4096)
        src = obj["source"]
        analysis = analyze_source(src, contract)
        # stricter than v0.3's error-only gate: these warnings change the factor's meaning and must be repaired
        strict = [i for i in analysis["issues"] if i["severity"] == "error" or i["code"] in STRICT_WARNINGS]
        analysis["passed"] = not strict
        sha = sha256_text(src)
        version = {"revision": rev, "source_sha256": sha, "model_record": rec["record"], "design": obj["design"],
                   "static_passed": analysis["passed"], "issues": analysis["issues"]}
        history.append(version)
        ledger.write_artifact(f"../candidates/rev{rev}_{sha[:12]}.py.txt", src, kind="text")
        ledger.event("CANDIDATE_VERSION", {k: version[k] for k in ("revision", "source_sha256", "static_passed")} |
                     {"issue_codes": [i["code"] for i in analysis["issues"]]})
        if analysis["passed"]:
            break
        messages_extra = ("\n\nYOUR PREVIOUS SOURCE FAILED STATIC REVIEW. Issues:\n" +
                          json.dumps([{k: i[k] for k in ("code", "severity", "line", "message", "suggestion")} for i in analysis["issues"]],
                                     ensure_ascii=False) + "\nPrevious source:\n" + src + "\nReturn a corrected JSON object.")
    cand = build_candidate(task, source=src, origin=f"deepseek:{getattr(client, 'model', 'model')}")
    cand["analysis"]["passed"] = history[-1]["static_passed"]
    cand["manifest"]["design_history"] = [{k: v for k, v in h.items() if k != "design"} for h in history]
    cand["design"] = history[-1]["design"]
    cand["status"] = "READY_FOR_REVIEW" if cand["analysis"]["passed"] else "STATIC_REVIEW_FAILED"
    if out_dir:
        write_candidate_bundle(cand, out_dir)
        (Path(out_dir) / "design.json").write_text(json.dumps({"design": cand["design"], "history": history,
                                                              "status": cand["status"]}, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    return cand, history


# ---------------------------------------------------------------- factors outside the trusted grammar: a reviewed pair

REFERENCE_SYSTEM = """You are writing the REFERENCE implementation of one quantitative factor: the most literal, obviously
correct translation of the algorithm steps, used only to check a separate fast implementation. Return ONE JSON object
{"source": "<complete Python module>", "notes": "..."}. Rules for "source":
- Define exactly `def reference(panels):` where panels maps input field name -> pandas DataFrame (rows = trading dates in
  ascending order, columns = securities). Return ONE DataFrame with the same index and columns.
- Import only numpy, pandas and math. No file, network, OS, reflection, exec/eval, pickle, threads, globals.
- Loop explicitly over columns and rows. At row t read ONLY rows <= t (positional index), never a later row.
- A value exists only when the full declared look-back of finite observations is available; otherwise NaN.
- Never fill NaN; propagate it. A zero denominator gives NaN. +/-inf becomes NaN.
- Clarity over speed; follow the steps exactly as written and do not optimise."""

SECURITY_CODES = {"SYNTAX_ERROR", "IMPORT_NOT_ALLOWED", "FORBIDDEN_CALL", "FORBIDDEN_NAME", "DUNDER_ACCESS", "BAD_SIGNATURE",
                  "MISSING_ENTRYPOINT", "NEGATIVE_SHIFT", "CENTERED_WINDOW", "BACKWARD_FILL", "REVERSED_TIME",
                  "FULL_SAMPLE_STATISTIC", "UNDECLARED_INPUT", "NOT_A_FRAME"}
PAIR_HEADER = '"""Reviewed pair for one factor outside the trusted grammar.\n\ncompute(): vectorised implementation (model call 1).\n' \
              'reference(): literal loop implementation written from the same steps by an independent model call that never saw\n' \
              'compute(). Both run only after human approval of this exact file; they must agree cell by cell before any use."""\n'


def _pair_fixture(contract, seed, n_rows, n_codes=4):
    from paper_research.candidate import _fixture, _frame_json
    panels = _fixture(contract, seed, n_rows, n_codes)
    return {k: _frame_json(v) for k, v in panels.items()}


def pair_tests(contract, seed=20261014):
    """Fixtures stored before anything runs; expected values come from the approved reference after approval."""
    n = contract["warmup"]["observations_required"] + 12
    cases = [{"name": f"agreement_seed{s}", "inputs": _pair_fixture(contract, s, n)} for s in (seed, seed + 1, seed + 2)]
    first = contract["inputs"][0]["field"]
    return {"mode": "pair", "rows": n, "warmup_rows": contract["warmup"]["observations_required"] - 1, "cases": cases,
            "perturb_after_row": n - 6, "set_nan": {"field": first, "row": n - 3, "column": 1},
            "set_zero": {"field": first, "row": n - 2, "column": 0}, "executed": False,
            "note": "compute() and reference() must agree on every fixture, on a perturbed future, on a missing input and on a zero"}


def design_pair(contract, client, ledger, *, max_revisions=2, out_dir=None):
    """Two independent model calls; static review (full for compute, security/time for reference); a reviewable bundle."""
    from paper_research.candidate import analyze_source
    steps = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(contract["algorithm"]["steps"]))
    quotes = "\n".join(f"- p{c.get('page')}: \"{c.get('quote')}\"" for c in contract["algorithm"]["citations"])
    brief = ("CONTRACT (authoritative):\n" + json.dumps({k: contract[k] for k in ("entrypoint", "inputs", "output", "time_alignment", "warmup",
                                                                                 "panel_frequency")}, ensure_ascii=False)
             + f"\nALGORITHM STEPS (from the paper; look-back {contract['algorithm']['lookback_rows']} rows):\n{steps}\nPAPER QUOTES:\n{quotes}\n")
    history, src, extra = [], None, ""
    for rev in range(max_revisions + 1):
        obj, rec = ask_json(client, ledger, purpose="algorithm_design", system=SYSTEM, user=brief + "Write compute()." + extra,
                            schema=SCHEMA, max_tokens=4096)
        src = obj["source"]
        analysis = analyze_source(src, contract)
        strict = [i for i in analysis["issues"] if i["severity"] == "error" or i["code"] in STRICT_WARNINGS]
        history.append({"part": "compute", "revision": rev, "source_sha256": sha256_text(src), "model_record": rec["record"],
                        "static_passed": not strict, "issues": [i["code"] for i in analysis["issues"]]})
        if not strict:
            break
        extra = "\n\nYOUR PREVIOUS SOURCE FAILED STATIC REVIEW: " + json.dumps(
            [{k: i[k] for k in ("code", "line", "message", "suggestion")} for i in strict], ensure_ascii=False) + "\nPrevious source:\n" + src
    ref, extra = None, ""
    for rev in range(max_revisions + 1):
        obj, rec = ask_json(client, ledger, purpose="reference_design", system=REFERENCE_SYSTEM, user=brief + "Write reference()." + extra,
                            schema={"type": "object", "required": ["source"]}, max_tokens=4096)
        ref = obj["source"]
        analysis = analyze_source(ref.replace("def reference(", "def compute(", 1), contract)
        bad = [i for i in analysis["issues"] if i["code"] in SECURITY_CODES]
        history.append({"part": "reference", "revision": rev, "source_sha256": sha256_text(ref), "model_record": rec["record"],
                        "static_passed": not bad, "issues": [i["code"] for i in analysis["issues"]]})
        if not bad:
            break
        extra = "\n\nYOUR PREVIOUS SOURCE FAILED THE SECURITY/TIME REVIEW: " + json.dumps(
            [{k: i[k] for k in ("code", "line", "message")} for i in bad], ensure_ascii=False) + "\nPrevious source:\n" + ref
    combined = PAIR_HEADER + "\n" + src.strip() + "\n\n\n" + ref.strip() + "\n"
    passed = all(h["static_passed"] for h in (next(h for h in reversed(history) if h["part"] == "compute"),
                                              next(h for h in reversed(history) if h["part"] == "reference")))
    cand = {"files": {"candidate.py": combined}, "status": "READY_FOR_REVIEW" if passed else "STATIC_REVIEW_FAILED",
            "manifest": {"candidate_id": "pair_" + sha256_text(combined)[:16], "origin": f"deepseek:{getattr(client, 'model', 'model')} (pair)",
                         "design_history": history},
            "tests": pair_tests(contract), "contract": contract,
            "analysis": {"passed": passed, "issues": [{"code": c, "part": h["part"]} for h in (
                next(h for h in reversed(history) if h["part"] == "compute"), next(h for h in reversed(history) if h["part"] == "reference"))
                if not h["static_passed"] for c in h["issues"]]},
            "design": {"summary": "vectorised compute() + independent literal reference()"}}
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "candidate.py.txt").write_text(combined, encoding="utf-8")
        (out / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "tests.json").write_text(json.dumps(cand["tests"], ensure_ascii=False), encoding="utf-8")
        (out / "design.json").write_text(json.dumps({"history": history, "status": cand["status"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return cand, history
