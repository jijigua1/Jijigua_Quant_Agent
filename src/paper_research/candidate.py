"""Candidate implementations for factors the DSL cannot express: generate, specify, analyse, preserve.

SAFETY BOUNDARY. Candidate source code is an untrusted artifact. This module only writes it as text and
inspects it with ``ast.parse``; it never imports, compiles to bytecode, ``exec``s or ``eval``s a candidate,
and nothing here promotes a candidate into a trusted registry. Expected values in the test specification
come from the trusted, hand-written reference evaluator ``factor_ir.evaluate``, never from the candidate.
A candidate can only be run later inside a separately approved execution environment.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .errors import PaperError
from .factor_ir import IRError, evaluate, walk, warmup

GENERATOR = {"name": "paper_research.candidate_generator", "version": "0.1.0", "method": "deterministic template from factor IR"}
STATUS = "UNTRUSTED_NOT_EXECUTED"
ALLOWED_IMPORTS = {"numpy", "pandas", "math"}
FORBIDDEN_CALLS = {"exec", "eval", "compile", "open", "__import__", "input", "getattr", "setattr", "delattr", "globals",
                   "locals", "vars", "breakpoint", "help", "exit", "quit", "memoryview", "classmethod", "staticmethod",
                   "super", "type", "object"}
FORBIDDEN_NAMES = {"os", "sys", "subprocess", "socket", "pickle", "shutil", "pathlib", "importlib", "builtins", "ctypes",
                   "requests", "urllib", "http", "multiprocessing", "threading", "signal", "resource", "io", "tempfile",
                   "marshal", "shelve", "dill", "joblib"}
SUGGEST = {
    "SYNTAX_ERROR": "Fix the syntax; the candidate cannot be reviewed until it parses.",
    "IMPORT_NOT_ALLOWED": "Use only numpy/pandas/math; remove other imports.",
    "FORBIDDEN_CALL": "Remove dynamic execution, file and reflection calls; factor code needs pure array arithmetic.",
    "FORBIDDEN_NAME": "Remove references to system, network or serialization modules.",
    "DUNDER_ACCESS": "Do not access dunder attributes.",
    "MISSING_ENTRYPOINT": "Define exactly `def compute(panels):` returning a DataFrame.",
    "BAD_SIGNATURE": "The entry point takes one argument: the mapping of input field -> DataFrame.",
    "UNDECLARED_INPUT": "Only read inputs declared in the contract, or update the contract and its evidence.",
    "NEGATIVE_SHIFT": "shift(-k) reads future rows; use non-negative lags only.",
    "CENTERED_WINDOW": "center=True uses future rows; use trailing windows.",
    "BACKWARD_FILL": "bfill/backfill copies future values into the past; leave gaps as NaN.",
    "REVERSED_TIME": "Reversing the time axis ([::-1]) makes trailing operations look ahead.",
    "FULL_SAMPLE_STATISTIC": "A statistic over the whole time axis uses future data; use rolling/expanding windows or cross-sectional (axis=1) operations.",
    "NAN_FILLED": "Filling NaN with a value invents data; propagate NaN and let evaluation exclude it.",
    "ROWS_DROPPED": "dropna changes the panel shape; keep the input index and columns.",
    "PARTIAL_WINDOW": "min_periods below the window computes on incomplete history; require full windows.",
    "HISTORY_BEYOND_DECLARED": "The code reaches further back than the declared warmup; reconcile code and contract.",
    "WINDOW_SHORTER_THAN_DECLARED": "No operation reaches the declared lookback: the window may have been shortened silently.",
    "UNGUARDED_DIVISION": "Guard denominators (replace 0 with NaN) so division cannot yield inf.",
    "UNIT_MISMATCH": "Adding or subtracting inputs with different units is meaningless; convert or ratio them first.",
    "NOT_A_FRAME": "Return a DataFrame aligned to the input (dates x securities), not a numpy array or scalar.",
    "UNBOUNDED_LOOP": "Avoid while-loops; vectorised pandas/numpy operations have bounded cost.",
}


# ------------------------------------------------------------------ code generation (text only)

HELPERS = '''import numpy as np
import pandas as pd


def _safe_div(a, b):
    if isinstance(b, pd.DataFrame):
        return a / b.replace(0, np.nan)
    return a / (np.nan if b == 0 else b)


def _window(term, start, end, how):
    """Aggregate term(k) over lags k = start..end; a value exists only when every lag is observed."""
    frames = [term(k) for k in range(start, end + 1)]
    stack = np.stack([f.to_numpy(dtype=float) for f in frames])
    full = np.isfinite(stack).all(axis=0)
    with np.errstate(invalid="ignore"):
        if how == "sum":
            agg = stack.sum(axis=0)
        elif how == "mean":
            agg = stack.mean(axis=0)
        elif how == "std":
            agg = stack.std(axis=0, ddof=1)
        elif how == "max":
            agg = stack.max(axis=0)
        else:
            agg = stack.min(axis=0)
    return pd.DataFrame(np.where(full, agg, np.nan), index=frames[0].index, columns=frames[0].columns)
'''


PRELUDE_SHA256 = hashlib.sha256(HELPERS.encode("utf-8")).hexdigest()


def _gen(node, field_of, names):
    op = node["op"]
    if op == "field":
        lag = node["lag"]
        parts = ([lag["var"]] if lag.get("var") else []) + ([str(lag["base"])] if lag["base"] or not lag.get("var") else [])
        return f"{names[field_of[node['symbol']]]}.shift({' + '.join(parts)})"
    if op == "const":
        return repr(float(node["value"]))
    if op in ("ema", "maximum", "minimum", "ts_prod", "ts_rank", "ts_corr", "ts_cov"):
        # the deterministic template covers the original grammar only; these run on the trusted IR executor
        raise PaperError("TEMPLATE_UNSUPPORTED_OPERATOR", f"{op} is executed by paper_agent.trusted_ir, not by a template")
    if op.startswith("ts_"):
        body = _gen(node["args"][0], field_of, names)
        return f"_window(lambda {node['var']}: {body}, {node['start']}, {node['end']}, {op[3:]!r})"
    a = [_gen(x, field_of, names) for x in node.get("args", [])]
    return {"add": lambda: f"({a[0]} + {a[1]})", "sub": lambda: f"({a[0]} - {a[1]})", "mul": lambda: f"({a[0]} * {a[1]})",
            "div": lambda: f"_safe_div({a[0]}, {a[1]})", "pow": lambda: f"({a[0]} ** {a[1]})", "neg": lambda: f"(-{a[0]})",
            "abs": lambda: f"{a[0]}.abs()", "log": lambda: f"np.log({a[0]}.where({a[0]} > 0))",
            "exp": lambda: f"np.exp({a[0]})", "sqrt": lambda: f"np.sqrt({a[0]}.where({a[0]} >= 0))",
            "sign": lambda: f"np.sign({a[0]})", "cs_rank": lambda: f"{a[0]}.rank(axis=1, method='average', pct=True)",
            "cs_zscore": lambda: f"{a[0]}.sub({a[0]}.mean(axis=1), axis=0).div({a[0]}.std(axis=1, ddof=1).replace(0, np.nan), axis=0)",
            }[op]()


def contract_from_task(task):
    ir = task["factor"].get("ir_execution") or task["factor"]["ir"]
    syms = [s for s in task["factor"]["symbols"] if not s.get("derived")]   # derived symbols live inside the IR
    adm = task.get("admission")
    if adm is not None and not adm["permissions"]["may_generate_candidate"]:
        raise PaperError("SCHEMA_INVALID", f"admission {adm['state']} does not allow a candidate: "
                         f"{adm['gates']['formula']['blocking_items'] + adm['gates']['semantics']['blocking_items']}")
    if ir is None or any(s["field"] is None for s in syms):
        raise PaperError("SCHEMA_INVALID", "a candidate needs a parsed factor and a field for every symbol")
    wu = warmup(ir)
    if wu["uses_future"]:
        raise PaperError("SCHEMA_INVALID", "the factor references future data; no candidate is generated")
    return {"entrypoint": "compute(panels) -> DataFrame",
            "inputs": [{"field": s["field"], "symbol": s["symbol"], "unit": s["unit"], "dtype": "float64",
                        "shape": "dates x securities", "basis": s["basis"]} for s in syms],
            "output": {"name": task["io"]["output"]["name"], "dtype": "float64", "shape": "same index/columns as inputs",
                       "missing": "NaN until every lag in the window is observed; NaN propagates; inf -> NaN"},
            "time_alignment": "row t uses rows t-max_lag..t only; no negative lags, no centered windows, no backward fill",
            "warmup": wu, "rows_per_period": task.get("time_basis", {}).get("rows_per_period"),
            "panel_frequency": ("daily rows (host conversion of the paper's periods)" if task.get("time_basis", {}).get("basis") == "host_choice"
                                else task.get("time_basis", {}).get("paper_frequency") or "unknown - must be stated before use"),
            "ir": ir}


def generate_source(contract):
    names = {i["field"]: f"x_{i['field']}" for i in contract["inputs"]}
    field_of = {i["symbol"]: i["field"] for i in contract["inputs"]}
    expr = _gen(contract["ir"], field_of, names)
    lines = [f'"""Candidate implementation of {contract["output"]["name"]}: generated from factor IR, UNTRUSTED and NOT EXECUTED.',
             "", "Review against the paper and run only inside an approved execution environment.", '"""', HELPERS, "",
             "def compute(panels):"]
    lines += [f'    {v} = panels["{k}"]' for k, v in sorted(names.items())]
    lines += [f"    out = {expr}", "    return out.replace([np.inf, -np.inf], np.nan)", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ test specification (expected values from trusted code)

def _frame_json(df):
    return {"index": [str(x) for x in df.index], "columns": [str(c) for c in df.columns],
            "values": [[None if not np.isfinite(v) else float(v) for v in row] for row in df.to_numpy(dtype=float)]}


def _fixture(contract, seed, n_rows, n_codes=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-04", periods=n_rows).strftime("%Y-%m-%d")
    cols = [f"S{j:02d}" for j in range(n_codes)]
    panels = {}
    for i, inp in enumerate(contract["inputs"]):
        base = 10.0 + 5 * rng.random(n_codes)
        if inp["unit"] in ("dimensionless",):
            vals = rng.normal(0, 0.02, (n_rows, n_codes))
        elif inp["unit"] in ("shares", "currency"):
            vals = rng.uniform(1e5, 5e5, (n_rows, n_codes)).round(0)
        else:
            vals = base * np.exp(np.cumsum(rng.normal(0, 0.02, (n_rows, n_codes)), axis=0))
        panels[inp["field"]] = pd.DataFrame(np.round(vals, 6), index=idx, columns=cols)
    return panels


def test_specification(contract, seed=20261012):
    """Independent numerical tests for a later, approved run of the candidate. Expected values are computed
    here by the trusted reference evaluator on explicit fixtures stored in the specification."""
    ir, wu = contract["ir"], contract["warmup"]
    n = wu["observations_required"] + 8
    panels = _fixture(contract, seed, n)
    symbols = {i["symbol"]: i["field"] for i in contract["inputs"]}
    ref = evaluate(ir, panels, symbols)
    cases = [{"name": "reference_values", "inputs": {k: _frame_json(v) for k, v in panels.items()},
              "expected": _frame_json(ref), "tolerance": {"abs": 1e-9, "rel": 1e-9},
              "source": "factor_ir.evaluate (trusted reference)"},
             {"name": "warmup_rows_are_nan", "expected_nan_rows": wu["observations_required"] - 1,
              "rule": "the first max_lag rows of every column are NaN"},
             {"name": "shape_and_alignment", "rule": "output index and columns equal the input's"}]
    cut = n - 5
    pert = {k: v.copy() for k, v in panels.items()}
    for v in pert.values():
        v.iloc[cut + 1:] = v.iloc[cut + 1:] * 1.5
    ref_p = evaluate(ir, pert, symbols)
    if not np.allclose(ref_p.iloc[:cut + 1].to_numpy(), ref.iloc[:cut + 1].to_numpy(), equal_nan=True):
        raise PaperError("SCHEMA_INVALID", "reference evaluator is not causal for this IR")   # guard for the reference itself
    cases.append({"name": "no_lookahead_perturbation", "perturb": {"rows_after": ref.index[cut], "multiply": 1.5},
                  "rule": "rows up to and including rows_after must equal reference_values"})
    miss = {k: v.copy() for k, v in panels.items()}
    first = contract["inputs"][0]["field"]
    miss[first].iloc[n - 3, 1] = np.nan
    cases.append({"name": "missing_input_propagates", "set_nan": {"field": first, "row": ref.index[n - 3], "column": "S01"},
                  "expected": _frame_json(evaluate(ir, miss, symbols)), "source": "factor_ir.evaluate (trusted reference)"})
    divs = [nd for nd in walk(ir) if nd["op"] == "div" and nd["args"][1]["op"] == "field"]
    if divs:
        den = symbols[divs[0]["args"][1]["symbol"]]
        zero = {k: v.copy() for k, v in panels.items()}
        zero[den].iloc[n - 2, 0] = 0.0
        cases.append({"name": "zero_denominator_is_nan", "set_zero": {"field": den, "row": ref.index[n - 2], "column": "S00"},
                      "expected": _frame_json(evaluate(ir, zero, symbols)), "source": "factor_ir.evaluate (trusted reference)"})
    return {"seed": seed, "cases": cases, "executed": False,
            "note": "expected values come from trusted toolkit code; the candidate has not been run against them"}


# ------------------------------------------------------------------ static analysis (ast.parse only)

def _issue(code, severity, node, msg):
    return {"code": code, "severity": severity, "line": getattr(node, "lineno", None), "col": getattr(node, "col_offset", None),
            "message": msg, "suggestion": SUGGEST.get(code, "")}


def _int(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, (int, float)):
        return -node.operand.value
    return None


def _assign_counts(tree):
    """How often each local name is bound (assignment, augmented assignment, loop target, with/except/comprehension)."""
    counts = {}
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            targets = [node.optional_vars]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    counts[n.id] = counts.get(n.id, 0) + 1
    return counts


def _loop_ranges(tree, counts):
    """Loop variables with a provable integer range: `for k in range(a, b[, s])`, literal bounds, s > 0, k bound only there.
    Returns {name: (min, max)}; anything else stays unresolved (and so cannot pass the history checks)."""
    out = {}
    if counts.get("range"):                       # a rebound `range` is not the builtin: no range is trusted
        return out
    single = {}                                   # names bound exactly once by `name = range(...)`
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and counts.get(node.targets[0].id) == 1:
            single[node.targets[0].id] = node.value
    for node in ast.walk(tree):
        if not (isinstance(node, ast.For) and isinstance(node.target, ast.Name)):
            continue
        it = single.get(node.iter.id) if isinstance(node.iter, ast.Name) else node.iter
        if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range" and not it.keywords):
            continue
        args = [_int(a) for a in it.args]
        if not 1 <= len(args) <= 3 or any(a is None or not isinstance(a, int) for a in args):
            continue
        lo, hi, step = (0, args[0], 1) if len(args) == 1 else (args[0], args[1], args[2] if len(args) == 3 else 1)
        if step <= 0 or hi <= lo or counts.get(node.target.id) != 1:
            continue
        out[node.target.id] = (lo, lo + ((hi - lo - 1) // step) * step)
    return out


def _span(node, loops):
    """(min, max) integer values an index expression can take, or None when not provable."""
    v = _int(node)
    if isinstance(v, int):
        return v, v
    if isinstance(node, ast.Name):
        return loops.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        s = _span(node.operand, loops)
        return (-s[1], -s[0]) if s else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        a, b = _span(node.left, loops), _span(node.right, loops)
        if a and b:
            return (a[0] + b[0], a[1] + b[1]) if isinstance(node.op, ast.Add) else (a[0] - b[1], a[1] - b[0])
    return None


def _panel_key(node):
    """The declared input a (method-chained) expression is derived from: panels['x'] or a name bound to it."""
    while True:
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "panels" \
                and isinstance(node.slice, ast.Constant):
            return node.slice.value
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Name):
            return ("name", node.id)
        else:
            return None


def _composed_reach(tree, loops=None):
    """History reach composed along the data flow: x.shift(a).rolling(w) and y = x.shift(a); y.rolling(w) both reach a + w - 1.
    Branches (binary operations, call arguments) take the maximum. Lambdas are left to the _window rule. A shift by a
    loop variable of provable range (see _loop_ranges) reaches its largest value."""
    loops = loops or {}
    named = {}

    def reach(node):
        if node is None or isinstance(node, (ast.Lambda, ast.Constant)):
            return 0
        if isinstance(node, ast.Name):
            return named.get(node.id, 0)
        if isinstance(node, ast.Call):
            base = reach(node.func.value) if isinstance(node.func, ast.Attribute) else 0
            kw = {k.arg: k.value for k in node.keywords}
            extra = max([reach(a) for a in node.args] + [reach(v) for v in kw.values()], default=0)
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if attr == "shift":
                arg = node.args[0] if node.args else kw.get("periods")
                s = _span(arg, loops) if arg is not None else (1, 1)
                base += s[1] if s is not None and s[1] > 0 else 0
            elif attr == "rolling":
                w = _int(node.args[0]) if node.args else _int(kw.get("window"))
                base += (w - 1) if w else 0
            return max(base, extra)
        return max([reach(c) for c in ast.iter_child_nodes(node) if isinstance(c, ast.expr)], default=0)

    out = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for st in ast.walk(node):
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                    named[st.targets[0].id] = reach(st.value)
                    out = max(out, named[st.targets[0].id])
                elif isinstance(st, ast.Return):
                    out = max(out, reach(st.value))
    return out


def analyze_source(source: str, contract: dict) -> dict:
    """Static checks of untrusted candidate source against its contract. Never executes the source."""
    issues = []
    try:
        ast.parse(source)
    except SyntaxError as e:
        return {"parsed": False, "issues": [{"code": "SYNTAX_ERROR", "severity": "error", "line": e.lineno, "col": e.offset,
                                             "message": str(e.msg), "suggestion": SUGGEST["SYNTAX_ERROR"]}],
                "passed": False}
    # The generator's helper prelude is reviewed text pinned by hash; only an exact copy is exempted from the
    # checks below. Any edit to it makes the whole file subject to every check.
    prelude = HELPERS in source
    tree = ast.parse(source.replace(HELPERS, "", 1) if prelude else source)
    declared = {i["field"]: i["unit"] for i in contract["inputs"]}
    bound = {}                                   # local name -> input field
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            k = _panel_key(node.value)
            if isinstance(k, str):
                bound[node.targets[0].id] = k

    def unit_of(expr):
        k = _panel_key(expr)
        if isinstance(k, tuple):
            k = bound.get(k[1])
        return declared.get(k) if isinstance(k, str) else None

    counts = _assign_counts(tree)
    loops = _loop_ranges(tree, counts)
    # names bound exactly once to a provably safe denominator: a non-zero number, or a zero-guarded expression
    safe_den = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and counts.get(node.targets[0].id) == 1:
            v, val = _int(node.value), node.value
            number = isinstance(val, ast.Constant) and isinstance(val.value, (int, float)) and not isinstance(val.value, bool)
            if (number and val.value != 0) or (isinstance(v, (int, float)) and v != 0) or (
                    isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute) and val.func.attr in ("replace", "where", "mask")):
                safe_den.add(node.targets[0].id)

    def nonzero_number(n):
        return (isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
                and n.value != 0) or (isinstance(_int(n), (int, float)) and _int(n) != 0)

    entry = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "compute"]
    if not entry:
        issues.append(_issue("MISSING_ENTRYPOINT", "error", tree, "no top-level compute()"))
    elif len(entry[0].args.args) != 1 or entry[0].args.vararg or entry[0].args.kwarg:
        issues.append(_issue("BAD_SIGNATURE", "error", entry[0], "compute must take exactly one argument"))
    lags, windows = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            for m in mods:
                if m not in ALLOWED_IMPORTS:
                    issues.append(_issue("IMPORT_NOT_ALLOWED", "error", node, f"import of {m!r}"))
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            issues.append(_issue("FORBIDDEN_NAME", "error", node, f"reference to {node.id!r}"))
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            issues.append(_issue("DUNDER_ACCESS", "error", node, f"access to {node.attr}"))
        if isinstance(node, ast.While):
            issues.append(_issue("UNBOUNDED_LOOP", "warning", node, "while-loop"))
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "panels":
            key = node.slice.value if isinstance(node.slice, ast.Constant) else None
            if key not in declared:
                issues.append(_issue("UNDECLARED_INPUT", "error", node, f"panels[{key!r}] is not a declared input"))
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) and _int(node.slice.step) == -1:
            issues.append(_issue("REVERSED_TIME", "error", node, "[::-1]"))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            right = node.right
            guarded = (isinstance(right, ast.Call) and isinstance(right.func, ast.Attribute) and right.func.attr in ("replace", "where", "mask")) \
                or nonzero_number(right) or (isinstance(right, ast.Name) and right.id in safe_den)
            if not guarded:
                issues.append(_issue("UNGUARDED_DIVISION", "warning", node, "denominator is not guarded against zero"))
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            ul, ur = unit_of(node.left), unit_of(node.right)
            if ul and ur and ul != ur:
                issues.append(_issue("UNIT_MISMATCH", "error", node, f"{ul} {'+' if isinstance(node.op, ast.Add) else '-'} {ur}"))
        if not isinstance(node, ast.Call):
            continue
        fname = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
        kw = {k.arg: k.value for k in node.keywords}
        if isinstance(node.func, ast.Name) and fname in FORBIDDEN_CALLS:
            issues.append(_issue("FORBIDDEN_CALL", "error", node, f"call to {fname}()"))
        if fname == "shift":
            arg = node.args[0] if node.args else kw.get("periods")
            s = _span(arg, loops) if arg is not None else (1, 1)
            if s is not None and s[0] < 0:
                issues.append(_issue("NEGATIVE_SHIFT", "error", node, f"shift reaches {s[0]} (future rows)"))
            elif s is None and isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                issues.append(_issue("NEGATIVE_SHIFT", "error", node, "shift(-x) of an unproven value"))
            if s is not None:
                lags.append(s[1])
            if isinstance(arg, ast.BinOp):                      # k + c inside a window lambda
                c = _int(arg.right) if isinstance(arg.right, (ast.Constant, ast.UnaryOp)) else None
                if c is not None and c < 0:
                    issues.append(_issue("NEGATIVE_SHIFT", "error", node, "shift(k - c)"))
        if fname == "rolling":
            w = _int(node.args[0]) if node.args else _int(kw.get("window"))
            if w:
                windows.append(w - 1)
            if isinstance(kw.get("center"), ast.Constant) and kw["center"].value is True:
                issues.append(_issue("CENTERED_WINDOW", "error", node, "rolling(center=True)"))
            mp = _int(kw.get("min_periods")) if "min_periods" in kw else None
            if w and (mp is None or mp < w):
                issues.append(_issue("PARTIAL_WINDOW", "warning", node, f"rolling({w}) with min_periods={mp}"))
        if fname in ("bfill", "backfill") or (fname == "fillna" and isinstance(kw.get("method"), ast.Constant)
                                               and kw["method"].value in ("bfill", "backfill")):
            issues.append(_issue("BACKWARD_FILL", "error", node, fname))
        if fname == "fillna" and (node.args or "value" in kw):
            issues.append(_issue("NAN_FILLED", "warning", node, "fillna(value)"))
        if fname == "dropna":
            issues.append(_issue("ROWS_DROPPED", "error", node, "dropna"))
        if fname in ("mean", "std", "var", "max", "min", "sum", "median", "quantile", "rank", "cumsum", "cummax") and \
                isinstance(node.func, ast.Attribute):
            axis = kw.get("axis")
            on_window = isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Attribute) and \
                node.func.value.func.attr in ("rolling", "expanding", "ewm", "groupby")
            cross = isinstance(axis, ast.Constant) and axis.value in (1, "columns")
            target_is_np = isinstance(node.func.value, ast.Name) and node.func.value.id in ("np", "numpy")
            if not on_window and not cross and not target_is_np and fname not in ("cumsum", "cummax"):
                issues.append(_issue("FULL_SAMPLE_STATISTIC", "error", node, f".{fname}() over the time axis"))
        if fname == "_window" and len(node.args) >= 3:
            end = _int(node.args[2])
            lam = node.args[0]
            c = 0
            for sub in ast.walk(lam):
                if isinstance(sub, ast.Call) and getattr(sub.func, "attr", None) == "shift" and sub.args and isinstance(sub.args[0], ast.BinOp):
                    c = max(c, _int(sub.args[0].right) or 0)
            if end is not None:
                windows.append(end + c)
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Attribute) and node.value.attr in ("values",):
            issues.append(_issue("NOT_A_FRAME", "error", node, "returns .values"))
    reach = max(lags + windows + [_composed_reach(tree, loops)], default=0)
    max_lag = contract["warmup"]["max_lag"]
    if reach > max_lag:
        issues.append(_issue("HISTORY_BEYOND_DECLARED", "error", tree, f"code reaches lag {reach} > declared {max_lag}"))
    elif reach < max_lag:
        issues.append(_issue("WINDOW_SHORTER_THAN_DECLARED", "error", tree, f"code reaches lag {reach} < declared {max_lag}"))
    return {"parsed": True, "issues": issues, "estimated_max_lag": reach,
            "reviewed_prelude": {"present": prelude, "sha256": PRELUDE_SHA256} if prelude else {"present": False},
            "passed": not any(i["severity"] == "error" for i in issues)}


# ------------------------------------------------------------------ bundle

def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_candidate(task: dict, *, source: str | None = None, origin: str = "template") -> dict:
    """Assemble an untrusted candidate: source (generated, or supplied by another generator such as an LLM),
    contract, independent tests, assumptions, static analysis and a failure report."""
    adm = task.get("admission")
    if adm is not None and (adm["gates"]["formula"]["status"] == "fail" or adm["gates"]["semantics"]["status"] == "fail"):
        raise PaperError("SCHEMA_INVALID", f"admission {adm['state']}: the paper's definition is not understood well enough for code: "
                         f"{adm['gates']['formula']['blocking_items'] + adm['gates']['semantics']['blocking_items']}")
    if task["dsl"]["status"] == "expressible":
        raise PaperError("SCHEMA_INVALID", "the factor is expressible in the DSL; use the DSL expression, not new code")
    contract = contract_from_task(task)
    src = source if source is not None else generate_source(contract)
    analysis = analyze_source(src, contract)
    tests = test_specification(contract)
    assumptions = ([{"statement": u["question"], "basis": "unresolved", "blocking": u["blocking"]} for u in task["unresolved"]] +
                   [{"statement": p["rule"], "basis": p["basis"]} for p in task["pit_constraints"]] +
                   [{"statement": "windows require every lag to be observed (no partial windows)", "basis": "generator"},
                    {"statement": "standard deviations use ddof=1", "basis": "generator"},
                    {"statement": "division by zero and log/sqrt of invalid inputs give NaN", "basis": "generator"},
                    {"statement": f"symbol mapping: { {s['symbol']: (s['field'], s['basis']) for s in task['factor']['symbols']} }",
                     "basis": "task"}])
    if task.get("time_basis", {}).get("basis") == "host_choice":
        assumptions.append({"statement": f"paper periods converted to {task['time_basis']['rows_per_period']} daily rows "
                            "(host deviation from the paper)", "basis": "host_choice"})
    report = {"failures": [i for i in analysis["issues"] if i["severity"] == "error"],
              "warnings": [i for i in analysis["issues"] if i["severity"] == "warning"],
              "repair_suggestions": sorted({i["suggestion"] for i in analysis["issues"]}),
              "dsl_reasons": task["dsl"]["reasons"]}
    files = {"candidate.py": src, "contract.json": json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False),
             "tests.json": json.dumps(tests, indent=2, sort_keys=True), "assumptions.json": json.dumps(assumptions, indent=2, ensure_ascii=False),
             "static_analysis.json": json.dumps(analysis, indent=2, ensure_ascii=False),
             "failure_report.json": json.dumps(report, indent=2, ensure_ascii=False)}
    manifest = {"status": STATUS, "executed": False, "trusted": False, "promotion": "forbidden until an approved execution environment exists",
                "origin": origin, "generator": GENERATOR, "task_id": task["task_id"], "spec_id": task["source"]["spec_id"],
                "document_sha256": task["source"]["sha256"], "factor": task["factor"]["name"],
                "files": {k: _sha(v) for k, v in files.items()}}
    manifest["candidate_id"] = _sha(json.dumps(manifest, sort_keys=True))[:16]
    return {"manifest": manifest, "files": files, "analysis": analysis, "tests": tests, "contract": contract,
            "assumptions": assumptions, "report": report}


def write_candidate_bundle(candidate: dict, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, text in candidate["files"].items():
        # the source is stored with a .py.txt suffix so no tool imports it by accident
        target = out / (name + ".txt" if name.endswith(".py") else name)
        target.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
        paths[name] = str(target)
    (out / "manifest.json").write_text(json.dumps(candidate["manifest"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["manifest.json"] = str(out / "manifest.json")
    return paths


def verify_candidate_bundle(out_dir) -> dict:
    """Recompute file fingerprints against the manifest (no execution)."""
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    bad = []
    for name, digest in manifest["files"].items():
        p = out / (name + ".txt" if name.endswith(".py") else name)
        text = p.read_text(encoding="utf-8")
        if _sha(text[:-1] if text.endswith("\n") and _sha(text) != digest else text) != digest:
            bad.append(name)
    return {"valid": not bad and manifest["status"] == STATUS and manifest["executed"] is False, "changed": bad}


def promote_candidate(*_args, **_kwargs):
    """Promotion into a trusted registry is not available in this toolkit."""
    raise PaperError("SCHEMA_INVALID", "PROMOTION_FORBIDDEN: candidates stay untrusted until a separately approved "
                                        "execution environment and review exist")
