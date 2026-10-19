"""Canonical research definition (2026-10-16): the deterministic mathematical contract of one planned factor study.

The model writes names, symbols and prose differently on every run; the definition identity must not. A canonical
definition keeps only what changes the numbers or the research contract -- the executed IR with every symbol replaced by
its market field (window variables renamed, commutative arguments ordered, time_index labels dropped), windows, inputs
and their adjustment, the time contract (paper frequency, rows per period, the dating convention, signal and label), the
parameter values with their source type, the asset contract, the registered system conventions, the executor semantics
version and the KINDS of disclosed substitutions -- and hashes it with a stable serialization.

Display names, the factor key, symbol names, the kinds of disclosure lines, natural-language summaries, model suggestions
and timestamps are recorded next to it but never hashed (offline replay of 38 real readings, 10-16: the same executed
formula had 4 SHAs while the model's factor name or its formula_status wording were hashed). Two definitions with different SHAs can still compute the same numbers (an equivalent expression): that is
decided by evaluating both on one synthetic panel with the reference evaluator (`equivalent`), never by text similarity.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

VERSION = "paper_agent.canonical/1"

# Level-3 system conventions: used where a paper does not decide a mathematical detail. Registered, versioned, disclosed;
# never presented as the author's own choice. A change to any of them is a new convention version (a new definition SHA).
CONVENTIONS_VERSION = "canonical-conventions/1"
SYSTEM_CONVENTIONS = {
    "C1_window_price_basis": "a high/low window uses the formula's own price series unless the symbol's verified quote says intraday/daily high",
    "C2_zero_denominator": "a zero or missing denominator gives a missing value (no 0, no +/-inf, no RSI=100 convention)",
    "C3_ema": "EMA alpha = 2/(N+1), seeded with the first value of a truncated window W (residual weight < 1e-3)",
    "C4_ties": "cross-sectional ranks use average ranks; groups break ties by column order",
    "C5_dating": "a formula is dated by the observation of its most recent input (a common formation lag is removed)",
    "C6_frequency": "a paper period is converted to daily rows (month = 21, week = 5, quarter = 63, year = 252)",
    "C7_label": "signal at the close of t, position from the open of t+1, label open[t+1+H]/open[t+1]-1",
}


def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return float(repr(x)) if isinstance(x, float) else x


def _dumps(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj):
    return hashlib.sha256(_dumps(obj).encode("utf-8")).hexdigest()


COMMUTATIVE = {"add", "mul", "maximum", "minimum"}


def canonical_ir(ir, fields):
    """The executed IR as a field-level expression: symbols -> market fields, window variables -> k0, k1..., no
    time_index labels, numbers normalized, commutative arguments in a canonical order."""
    def visit(node, depth, rename):
        n = {k: v for k, v in node.items() if k not in ("args",)}
        if n.get("op") == "field":
            sym = n.pop("symbol", None)
            n["field"] = fields.get(sym, sym if sym is not None else n.get("field"))
            lag = dict(n.get("lag") or {})
            lag.pop("time_index", None)
            if lag.get("var") is not None:
                lag["var"] = rename.get(lag["var"], lag["var"])
            n["lag"] = {k: _num(v) for k, v in sorted(lag.items())}
        inner = dict(rename)
        if n.get("op", "").startswith("ts_") and n.get("var"):
            inner[n["var"]] = f"k{depth}"
            n["var"] = f"k{depth}"
        for k, v in list(n.items()):
            if isinstance(v, (int, float)):
                n[k] = _num(v)
        args = [visit(a, depth + (1 if n.get("op", "").startswith("ts_") else 0), inner) for a in node.get("args", [])]
        if n.get("op") in COMMUTATIVE:
            args = sorted(args, key=_dumps)
        if args:
            n["args"] = args
        return n
    return visit(copy.deepcopy(ir), 0, {})


def windows(ir):
    out = []

    def visit(n):
        if n.get("op", "").startswith("ts_"):
            out.append({"op": n["op"], "start": _num(n["start"]), "end": _num(n["end"]), "length": _num(n["end"] - n["start"] + 1)})
        if n.get("op") == "ema":
            out.append({"op": "ema", "n": _num(n.get("n")), "window": _num(n.get("window")), "init": n.get("init")})
        for a in n.get("args", []):
            visit(a)
    visit(ir)
    return out


NUMBERED = re.compile(r"(alpha|α)\s*#?\s*0*(\d+)", re.I)


def factor_key(name, requested=""):
    """Numbered factors keep their number (Alpha#12 is never Alpha#1); otherwise a normalized short name (display only:
    the key selects candidates in the registry, the math decides identity)."""
    for text in (requested or "", name or ""):
        m = NUMBERED.search(text)
        if m:
            return f"alpha#{int(m.group(2))}"
    text = requested or name or ""                 # what the user asked for decides; the model's name only as a fallback
    acronym = re.search(r"\(([A-Z][A-Z0-9+\-]{1,12})\)", text)
    if acronym:
        return acronym.group(1).lower()
    return re.sub(r"[^a-z0-9#]+", "-", text.lower()).strip("-")[:60]


def field_map(task, plan):
    out = {}
    for s in (task or {}).get("factor", {}).get("symbols", []) or []:
        if s.get("field"):
            out[s["symbol"]] = s["field"]
    for sym, spec in (plan.get("symbol_map") or {}).items():
        if isinstance(spec, dict) and spec.get("field"):
            out.setdefault(sym, spec["field"])
    return out


def adjustments(task, plan):
    out = {}
    for s in (task or {}).get("factor", {}).get("symbols", []) or []:
        if s.get("field"):
            out[s["field"]] = s.get("adjustment") or "none"
    for spec in (plan.get("symbol_map") or {}).values():
        if isinstance(spec, dict) and spec.get("field"):
            out.setdefault(spec["field"], spec.get("adjustment") or "none")
    return dict(sorted(out.items()))


ALGORITHM_CONTRACT = "algorithm-contract/recovery-1"


def definition(plan, task, understanding, *, paper, requested_factor="", session_id=None, semantics=None, program=None):
    """(canonical definition dict, sha). `paper` = library entry (sha256, name, version)."""
    from paper_research.factor_ir import IR_SEMANTICS
    fac = next((f for f in (understanding or {}).get("factors", []) if f.get("name") == plan.get("factor")), {})
    fields = field_map(task, plan)
    ir = plan.get("ir_execution_json")
    canon = canonical_ir(ir, fields) if ir else None
    # paper-sourced numbers are inside the IR (written as named parameters or as literals -- live MACD did both); only a
    # value the USER chose changes the contract beyond the IR, so only USER values are hashed (their session is recorded)
    params = sorted(({"value": _num(p.get("value")), "source": "USER"} for p in fac.get("parameters") or []
                     if p.get("status") == "USER" and p.get("value") is not None), key=_dumps)
    timing = ((task or {}).get("factor") or {}).get("timing") or {}
    choices = plan.get("choices") or {}
    math = {
        "schema": VERSION,
        "paper_sha256": paper["sha256"],
        "formula_ir": canon,
        "formula_text": None if canon is None else None,      # readable text is recorded outside the hash
        "windows": windows(canon) if canon else [],
        "inputs": {f: a for f, a in adjustments(task, plan).items() if canon is None or f in _fields(canon)},
        "time": {"rows_per_period": (choices.get("time_unit_rows") or {}).get("rows"),     # the effective conversion
                 "common_lag_removed": _num(timing.get("common_lag_removed") or 0),
                 "label_lag": _num(choices.get("label_lag", 1)),
                 "horizon": _num((choices.get("horizon") or {}).get("n"))},
        "parameters": params,
        "asset": {"decision": (plan.get("assets") or {}).get("decision"), "consent_required": bool(plan.get("asset_consent_required"))},
        "conventions": CONVENTIONS_VERSION,
        "semantics": {"ir": semantics or IR_SEMANTICS, "route": plan.get("route")},
    }
    if "n_groups" in choices:
        math["evaluation_groups"] = choices["n_groups"]
    math.pop("formula_text")
    contract = (plan.get("algorithm_contract") or {}).get("algorithm")
    if canon is None and contract:
        # A non-IR algorithm (C6 audit F02: every algorithm hashed as formula None / windows [] and shared one SHA and
        # one approval). Its identity is the steps EXACTLY as shown (no rewording, no renumbering, no symbol rewriting:
        # each such "normalisation" produced a collision in C7-C9 -- 1.5 vs 5, swapped P/Q bindings, names inside quotes),
        # the symbol -> field bindings, the look-back and the inputs. Wording differences give different SHAs; that is the
        # safe direction, and algorithm definitions are never reused. Only algorithm records get this key.
        symbol_map = plan.get("symbol_map") or {}
        math["algorithm"] = {
            "contract": ALGORITHM_CONTRACT,
            "steps": [str(x).strip() for x in contract.get("steps") or []],
            "bindings": {str(k): {"field": (v or {}).get("field"), "adjustment": (v or {}).get("adjustment")}
                         for k, v in sorted(symbol_map.items())},
            "lookback_rows": _num(contract.get("lookback_rows")),
            "inputs": sorted({str((v or {}).get("field")) for v in symbol_map.values()}),
        }
    if plan.get('route') == 'autonomous_python':
        math['autonomous_contract'] = copy.deepcopy(plan['autonomous_contract'])
    digest = sha(math)
    record = {
        "definition_sha256": digest,
        "math": math,
        # selects candidates in the registry (from the user's request first; numbered factors keep their number) but is
        # NOT hashed: the model's display name changes between runs (live D09: "...ratio of current price..." / "...nearness...")
        "factor_key": factor_key(plan.get("factor"), requested_factor),
        "requested_factor_key": factor_key("", requested_factor) if requested_factor else "",
        # which disclosure lines appear depends on the model's phrasing; their mathematical content is hashed above
        "substitution_kinds": sorted({s.get("kind") for s in plan.get("substitutions") or [] if s.get("kind")}),
        "display": {"factor": plan.get("factor"), "paper_name": paper.get("name"), "paper_version": paper.get("version"),
                    "paper_frequency": plan.get("paper_frequency"),
                    "executed": plan.get("ir_execution"), "requested_factor": requested_factor},
        "parameters_detail": [{"symbol": p.get("symbol"), "value": p.get("value"), "source": p.get("status"),
                               "session_id": session_id if p.get("status") == "USER" else None,
                               "citations": p.get("citations")} for p in fac.get("parameters") or []],
        "evidence": [{"page": (c.get("location") or {}).get("page"), "block_id": (c.get("location") or {}).get("block_id"),
                      "quote": c.get("quote")} for c in ((task or {}).get("factor") or {}).get("definition_evidence") or []],
        "substitutions": plan.get("substitutions"),
        "numeric_check": ((fac.get("formula") or {}).get("independent_reading") or {}).get("comparison"),
        "conventions": SYSTEM_CONVENTIONS,
        "plan_status": plan.get("status"),
        "hard_stops": sorted({h.get("code") for h in plan.get("hard_stops") or []}),
        "plan_sha256": plan.get("definition_sha256"),
        "program_sha256": program,
    }
    return record, digest


def _fields(ir):
    out = set()

    def visit(n):
        if n.get("op") == "field":
            out.add(n.get("field"))
        for a in n.get("args", []):
            visit(a)
    visit(ir)
    return out


def _evaluable(ir):
    """A canonical (field-level) IR back in evaluator form: each field becomes a symbol of the same name."""
    def visit(n):
        m = {k: v for k, v in n.items() if k != "args"}
        if m.get("op") == "field":
            m["symbol"] = m.pop("field")
            m["lag"] = dict(m.get("lag") or {}, time_index=None)
        if n.get("args"):
            m["args"] = [visit(a) for a in n["args"]]
        return m
    return visit(ir)


def equivalent(ir_a, ir_b):
    """Do two canonical (field-level) IRs compute the same numbers? Reference evaluator, one synthetic panel.
    Returns {"agree": bool, ...} or None when either cannot be evaluated."""
    from .reconcile import formulas_agree
    fa, fb = _fields(ir_a), _fields(ir_b)
    return formulas_agree(_evaluable(ir_a), {f: f for f in fa}, _evaluable(ir_b), {f: f for f in fb})


def classify(a, b):
    """Difference class of two canonical definitions (dicts as returned by `definition`):
    SAME (identical SHA), A_EQUIVALENT (same numbers), C_SEMANTIC (different numbers or contract), D_ENGINEERING (one is
    missing). Registered convention differences are part of the SHA and therefore C unless they evaluate identically."""
    if a is None or b is None:
        return "D_ENGINEERING"
    if a["definition_sha256"] == b["definition_sha256"]:
        return "SAME"
    ma, mb = a["math"], b["math"]
    rest = lambda m: {k: v for k, v in m.items() if k not in ("formula_ir", "windows")}   # every other contract field must match
    if rest(ma) != rest(mb) or ma["formula_ir"] is None or mb["formula_ir"] is None:
        return "C_SEMANTIC"
    cmp = equivalent(ma["formula_ir"], mb["formula_ir"])
    return "A_EQUIVALENT" if cmp and cmp.get("agree") else "C_SEMANTIC"
