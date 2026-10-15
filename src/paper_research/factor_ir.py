"""Factor intermediate representation (IR): a restricted, deterministic parser for factor formulas written
in common LaTeX, plus a trusted reference evaluator used to produce expected values.

The parser accepts a closed grammar only. Anything else raises IRError with the offending token, so an
unusual formula stays a human-review item instead of being guessed. Time indices are read from subscripts:
``P_{i,t-2}`` is symbol P lagged 2 periods; ``t+1`` is a future reference and is recorded, never evaluated.

IR node (plain dicts, JSON-serialisable):
  {"op": "field", "symbol": "P", "lag": 2}                       lag in periods (may contain the window variable)
  {"op": "const", "value": 1.0}
  {"op": "add"|"sub"|"mul"|"div"|"pow", "args": [a, b]}
  {"op": "neg"|"abs"|"log"|"exp"|"sqrt"|"sign", "args": [a]}
  {"op": "ts_sum"|"ts_mean"|"ts_std"|"ts_max"|"ts_min"|"ts_prod"|"ts_rank", "var": "k", "start": a, "end": b, "args": [body]}
  {"op": "ts_corr"|"ts_cov", "var": "k", "start": a, "end": b, "args": [body_x, body_y]}
  {"op": "maximum"|"minimum", "args": [a, b]}                      element-wise (NOT a window extremum)
  {"op": "ema", "smoothing": "span"|"wilder"|"ratio", "n": N, "m": M, "alpha": a, "init": "first"|"sma",
   "window": W, "args": [x]}                                       recursive exponential smoothing, truncated to W rows
  {"op": "cs_rank"|"cs_zscore", "args": [a]}
Field lags inside a window body are {"base": c, "var": "k"} meaning lag = k + c.

Recursive smoothing (EMA family) is defined on a FINITE window so that a value depends only on the last W observations:
the seed is x[t-W+1] (init "first", as pandas adjust=False / Chinese trading software) or the mean of the first N
observations of the window (init "sma", as TA-Lib), then y <- alpha*x + (1-alpha)*y runs to t. Every observation in the
window must be finite. W is the smallest window whose seed weight is <= SEED_WEIGHT (stated in every plan), which makes the
study and the 2026 evaluator compute identical values from the same W rows of history. alpha = 2/(N+1) ("span", EMA),
1/N ("wilder", RMA/SMMA/Wilder), M/N ("ratio", Chinese SMA(X,N,M)).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

IR_VERSION = "paper_research.factor_ir/1.0"


class IRError(ValueError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# ------------------------------------------------------------------ tokenizer

TOKEN = re.compile(r"""\s*(?:
    (?P<num>\d+(?:\.\d+)?)|
    (?P<cmd>\\[A-Za-z]+)|
    (?P<id>[A-Za-z][A-Za-z0-9]*)|
    (?P<op>[-+*/^_(){}|=,<>]|\\le|\\ge|\\leq|\\geq|≤|≥|−|·|×)
)""", re.X)
SKIP_CMDS = {r"\left", r"\right", r"\,", r"\;", r"\!", r"\cdot", r"\times", r"\mathrm", r"\text", r"\operatorname",
             r"\displaystyle", r"\limits"}
UNARY = {r"\log": "log", r"\ln": "log", r"\exp": "exp", r"\sqrt": "sqrt", r"\sign": "sign", "sign": "sign",
         "log": "log", "ln": "log", "exp": "exp", "sqrt": "sqrt", "abs": "abs"}
WINDOW = {r"\sum": "ts_sum", r"\max": "ts_max", r"\min": "ts_min", r"\prod": "ts_prod", "mean": "ts_mean", "avg": "ts_mean",
          "std": "ts_std", "sd": "ts_std", "max": "ts_max", "min": "ts_min", "sum": "ts_sum", "prod": "ts_prod",
          "tsrank": "ts_rank", "ts_rank": "ts_rank", "rankts": "ts_rank", "corr": "ts_corr", "cov": "ts_cov"}
PAIR_WINDOWS = {"ts_corr", "ts_cov"}
TS_OPS = ("ts_sum", "ts_mean", "ts_std", "ts_max", "ts_min", "ts_prod", "ts_rank", "ts_corr", "ts_cov")
CROSS = {"rank": "cs_rank", "zscore": "cs_zscore", "z": "cs_zscore"}
RECURSIVE = {"ema": "span", "rma": "wilder", "wilder": "wilder", "smma": "wilder", "sma": "ratio"}
SEED_WEIGHT = 1e-3          # residual weight of the truncated seed (finite-window recursion), stated in every plan


def tokenize(text):
    text = re.sub(r"\\(cdot|times)(?![A-Za-z])", "*", text)
    text = text.replace("−", "-").replace("·", "*").replace("×", "*").replace("≤", r"\le ").replace("≥", r"\ge ")
    pos, out = 0, []
    while pos < len(text):
        if text[pos:pos + 2] in (r"\,", r"\;", r"\!"):
            pos += 2
            continue
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos].isspace():
                pos += 1
                continue
            raise IRError("UNSUPPORTED_TOKEN", repr(text[pos:pos + 12]))
        pos = m.end()
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "cmd" and val in (r"\le", r"\leq"):
            kind, val = "op", "<="
        elif kind == "cmd" and val in (r"\ge", r"\geq"):
            kind, val = "op", ">="
        out.append((kind, val))
    return out


# ------------------------------------------------------------------ parser

class Parser:
    def __init__(self, tokens):
        self.t, self.i = [x for x in tokens if not (x[0] == "cmd" and x[1] in (r"\left", r"\right", r"\displaystyle", r"\limits"))], 0
        self.window_vars = []
        self.abs_depth = 0          # inside |...| a '|' closes the group, it never starts a product

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise IRError("PARSE_ERROR", f"expected {value!r}, found {tok[1]!r} at token {self.i}")
        self.i += 1
        return tok

    def group(self):
        """{...} or a single atom used as a command argument."""
        if self.peek()[1] == "{":
            self.take("{")
            e = self.expr()
            self.take("}")
            return e
        return self.atom()

    def raw_group(self):
        """Tokens inside {...} as text (for subscripts / operator names)."""
        if self.peek()[1] != "{":
            return self.take()[1]
        self.take("{")
        depth, parts = 1, []
        while True:
            k, v = self.take()
            if v == "{":
                depth += 1
            elif v == "}":
                depth -= 1
                if depth == 0:
                    break
            parts.append(v)
        return " ".join(parts)

    # precedence: + -  <  * /  <  unary -  <  ^
    def expr(self):
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = {"op": "add" if op == "+" else "sub", "args": [node, self.term()]}
        return node

    def term(self):
        node = self.unary()
        while True:
            k, v = self.peek()
            if v in ("*", "/"):
                self.take()
                node = {"op": "mul" if v == "*" else "div", "args": [node, self.unary()]}
            elif k in ("id", "num", "cmd") or v in ("(", "{") or (v == "|" and self.abs_depth == 0):
                if k == "cmd" and v not in SKIP_CMDS and v not in UNARY and v not in WINDOW and v not in (r"\frac", r"\operatorname", r"\mathrm", r"\text") and not v.startswith(r"\\"):
                    break
                node = {"op": "mul", "args": [node, self.unary()]}     # implicit multiplication
            else:
                return node

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return {"op": "neg", "args": [self.unary()]}
        if self.peek()[1] == "+":
            self.take()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek()[1] == "^":
            self.take()
            exp = self.group()
            return {"op": "pow", "args": [base, exp]}
        return base

    def atom(self):
        k, v = self.peek()
        if k is None:
            raise IRError("PARSE_ERROR", "unexpected end of formula")
        if k == "num":
            self.take()
            return {"op": "const", "value": float(v)}
        if v == "(":
            self.take("(")
            e = self.expr()
            self.take(")")
            return e
        if v == "{":
            return self.group()
        if v == "|":
            self.take("|")
            self.abs_depth += 1
            e = self.expr()
            self.abs_depth -= 1
            self.take("|")
            return {"op": "abs", "args": [e]}
        if k == "cmd":
            return self.command()
        if k == "id":
            if v.lower() in ("max", "min") and self.peek(1)[1] == "(":
                self.take()
                return self.elementwise(v.lower())
            if v.lower() in RECURSIVE and self.peek(1)[1] == "_":
                self.take()
                return self.recursive(v.lower())
            if v.lower() in WINDOW and self.peek(1)[1] == "_":
                return self.window(WINDOW[v.lower()])
            if v.lower() in CROSS and self.peek(1)[1] in ("(", "_"):
                self.take()
                if self.peek()[1] == "_":
                    self.take("_")
                    self.raw_group()
                return {"op": CROSS[v.lower()], "args": [self.paren_arg()]}
            if v in UNARY and self.peek(1)[1] in ("(", "{"):
                self.take()
                return {"op": UNARY[v], "args": [self.paren_arg()]}
            return self.symbol()
        raise IRError("PARSE_ERROR", f"unexpected {v!r}")

    def paren_arg(self):
        if self.peek()[1] == "(":
            self.take("(")
            e = self.expr()
            self.take(")")
            return e
        return self.group()

    def command(self):
        k, v = self.take()
        if v == r"\frac":
            num = self.group()
            den = self.group()
            return {"op": "div", "args": [num, den]}
        if v in (r"\operatorname", r"\mathrm", r"\text"):
            name = self.raw_group().replace(" ", "").lower()
            if name in ("max", "min") and self.peek()[1] == "(":
                return self.elementwise(name)
            if name in RECURSIVE and self.peek()[1] == "_":
                return self.recursive(name)
            if name in WINDOW and self.peek()[1] == "_":
                return self.window(WINDOW[name])
            if name in CROSS:
                if self.peek()[1] == "_":
                    self.take("_")
                    self.raw_group()
                return {"op": CROSS[name], "args": [self.paren_arg()]}
            if name in UNARY:
                return {"op": UNARY[name], "args": [self.paren_arg()]}
            raise IRError("UNSUPPORTED_FUNCTION", name)
        if v in (r"\max", r"\min") and self.peek()[1] == "(":
            return self.elementwise(v[1:])                  # \max(a, b): element-wise, not a window extremum
        if v in (r"\sum", r"\max", r"\min", r"\prod"):
            return self.window(WINDOW[v])
        if v in UNARY:
            if v == r"\sqrt":
                return {"op": "sqrt", "args": [self.group()]}
            return {"op": UNARY[v], "args": [self.paren_arg()]}
        raise IRError("UNSUPPORTED_COMMAND", v)

    def window(self, op):
        """\\sum_{k=a}^{b} body,  \\max_{0 <= k <= b} body,  mean_{k=a}^{b}(body)."""
        if self.peek()[0] == "id" and self.peek()[1].lower() in WINDOW:
            self.take()
        self.take("_")
        sub = self.raw_group()
        sup = None
        if self.peek()[1] == "^":
            self.take("^")
            sup = self.raw_group()
        var, start, end = parse_bounds(sub, sup)
        self.window_vars.append(var)
        if op in PAIR_WINDOWS:                      # corr_{k=a}^{b}(X_{i,t-k}, Y_{i,t-k})
            self.take("(")
            x = self.expr()
            self.take(",")
            y = self.expr()
            self.take(")")
            self.window_vars.pop()
            if end - start + 1 < 2:
                raise IRError("UNSUPPORTED_WINDOW_BOUNDS", f"{op} needs at least 2 observations")
            return {"op": op, "var": var, "start": start, "end": end, "args": [x, y]}
        body = self.unary() if self.peek()[1] != "(" else self.paren_arg()
        self.window_vars.pop()
        return {"op": op, "var": var, "start": start, "end": end, "args": [body]}

    def elementwise(self, name):
        """max(a, b) / min(a, b): element-wise of two operands."""
        self.take("(")
        a = self.expr()
        self.take(",")
        b = self.expr()
        self.take(")")
        return {"op": "maximum" if name == "max" else "minimum", "args": [a, b]}

    def recursive(self, name):
        """ema_{N}(x), rma_{N}(x) (Wilder), sma_{N,M}(x) (Chinese SMA, alpha = M/N); sma_{N}(x) is a simple mean."""
        self.take("_")
        sub = self.raw_group().replace(" ", "")
        parts = sub.split(",")
        if not all(re.fullmatch(r"\d+", p) for p in parts) or len(parts) > 2:
            raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"{name}_{{{sub}}}")
        n = int(parts[0])
        if name == "sma" and len(parts) == 1:   # English "SMA(N)" is the simple moving average, not a recursion
            if n < 1:
                raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"{name}_{{{sub}}}")
            body = self._var_body(n)
            return body
        if (name == "sma") != (len(parts) == 2):
            raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"{name}_{{{sub}}}: only sma takes two parameters (N,M)")
        m = int(parts[1]) if len(parts) == 2 else None
        x = self.paren_arg()
        return make_ema(RECURSIVE[name], n, x, m=m)

    def _var_body(self, n):
        """sma_{N}(X_{i,t}) -> mean_{k=0}^{N-1} X_{i,t-k}: the argument's lags are shifted by the window variable."""
        x = self.paren_arg()
        var = "k" if "k" not in self.window_vars else "j"
        body = _bind_window_var(x, var)
        return {"op": "ts_mean", "var": var, "start": 0, "end": n - 1, "args": [body]}

    def symbol(self):
        k, name = self.take()
        lag = {"base": 0, "var": None}
        if self.peek()[1] == "_":
            self.take("_")
            sub = self.raw_group()
            lag = parse_time_index(sub, self.window_vars)
        return {"op": "field", "symbol": name, "lag": lag}


def parse_bounds(sub, sup):
    s = sub.replace(" ", "")
    m = re.fullmatch(r"([a-z])=(\d+)", s)
    if m and sup is not None and re.fullmatch(r"\d+", sup.replace(" ", "")):
        return m.group(1), int(m.group(2)), int(sup.replace(" ", ""))
    m = re.fullmatch(r"(\d+)(<=|<)([a-z])(<=|<)(\d+)", s)
    if m:
        lo = int(m.group(1)) + (1 if m.group(2) == "<" else 0)
        hi = int(m.group(5)) - (1 if m.group(4) == "<" else 0)
        return m.group(3), lo, hi
    raise IRError("UNSUPPORTED_WINDOW_BOUNDS", f"_{{{sub}}}^{{{sup}}}")


def parse_time_index(sub, window_vars):
    """'i,t-2' -> lag 2; 'i,t' -> 0; 'i,t-k' (k a window var) -> k; 't+1' -> -1 (future)."""
    parts = [p.strip() for p in sub.replace(" ", "").split(",")]
    tpart = next((p for p in parts if re.match(r"^[td]([-+]|$)", p)), None)
    if tpart is None:
        return {"base": 0, "var": None, "time_index": None}
    m = re.fullmatch(r"[td](?:([-+])(\d+))?(?:([-+])([a-z]))?(?:([-+])(\d+))?", tpart)
    if not m:
        raise IRError("UNSUPPORTED_TIME_INDEX", tpart)
    base, var = 0, None
    if m.group(2):
        base += int(m.group(2)) * (1 if m.group(1) == "-" else -1)
    if m.group(4):
        if m.group(4) not in window_vars or m.group(3) != "-":
            raise IRError("UNSUPPORTED_TIME_INDEX", tpart)
        var = m.group(4)
    if m.group(6):
        base += int(m.group(6)) * (1 if m.group(5) == "-" else -1)
    return {"base": base, "var": var, "time_index": tpart}


def ema_alpha(smoothing, n, m=None):
    if smoothing == "span":
        return 2.0 / (n + 1)
    if smoothing == "wilder":
        return 1.0 / n
    if smoothing == "ratio":
        if not (m and 0 < m <= n):
            raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"SMA(N={n}, M={m}) needs 0 < M <= N")
        return m / n
    raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", smoothing)


def ema_window(alpha, init="first", n=1, seed_weight=SEED_WEIGHT):
    """Smallest W whose truncated seed keeps a residual weight <= seed_weight (W rows of history, W >= 2)."""
    import math
    if alpha >= 1:
        return 1 if init == "first" else n
    steps = math.ceil(math.log(seed_weight) / math.log(1 - alpha) - 1e-12)
    return max(2, steps + (1 if init == "first" else n))


def make_ema(smoothing, n, x, *, m=None, init="first", window=None):
    if n < 1:
        raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"N={n}")
    alpha = ema_alpha(smoothing, n, m)
    w = window or ema_window(alpha, init, n)
    if init == "sma" and w <= n:
        raise IRError("UNSUPPORTED_RECURSION_PARAMETERS", f"window {w} must exceed the SMA seed length {n}")
    return {"op": "ema", "smoothing": smoothing, "n": n, "m": m, "alpha": alpha, "init": init, "window": int(w),
            "seed_weight": ((1 - alpha) ** (w - (1 if init == "first" else n))), "args": [x]}


def ema_weights(node):
    """Closed-form weights w[k] on x[t-k], k = 0..W-1, of the finite-window recursion (trusted executor side)."""
    a, w, init, n = node["alpha"], node["window"], node["init"], node["n"]
    out = np.zeros(w)
    if init == "first":
        out[:w - 1] = a * (1 - a) ** np.arange(w - 1)
        out[w - 1] = (1 - a) ** (w - 1)
    else:
        steps = w - n
        out[:steps] = a * (1 - a) ** np.arange(steps)
        out[steps:] = (1 - a) ** steps / n
    return out


def _bind_window_var(x, var):
    import copy
    out = copy.deepcopy(x)
    for node in walk(out):
        if node["op"] in TS_OPS or node["op"] == "ema":
            raise IRError("UNSUPPORTED_WINDOW_BODY", "a simple moving average of a windowed expression")
        if node["op"] == "field":
            if node["lag"].get("var"):
                raise IRError("UNSUPPORTED_TIME_INDEX", "nested window variable")
            node["lag"] = dict(node["lag"], var=var)
    return out


def parse_formula(text):
    """Parse 'LHS = RHS' (or a bare RHS). Returns {"output": symbol|None, "ir": node}."""
    clean = re.sub(r"\(\s*\d+\s*\)\s*$", "", text).strip()            # trailing equation number
    clean = re.sub(r"\\tag\{[^}]*\}", "", clean)
    # the definition '=' is the first one outside braces ("\sum_{k=0}^{20} x" has no left-hand side)
    depth, cut = 0, None
    for i, ch in enumerate(clean):
        depth += (ch == "{") - (ch == "}")
        if ch == "=" and depth == 0:
            cut = i
            break
    lhs, rhs = (clean[:cut], clean[cut + 1:]) if cut is not None else (None, clean)
    p = Parser(tokenize(rhs))
    ir = p.expr()
    if p.i != len(p.t):
        raise IRError("TRAILING_TOKENS", " ".join(v for _, v in p.t[p.i:p.i + 6]))
    out = None
    if lhs:
        m = re.match(r"\s*\\?([A-Za-z][A-Za-z0-9]*)", lhs)
        out = m.group(1) if m else None
    return {"output": out, "ir": ir}


# ------------------------------------------------------------------ analysis

def walk(node):
    yield node
    for a in node.get("args", []):
        yield from walk(a)


def fields_used(ir):
    return sorted({n["symbol"] for n in walk(ir) if n["op"] == "field"})


def history(ir, bind=None):
    """Maximum past lag (periods) the value at t depends on; negative minimum lag means future data."""
    bind = bind or {}
    op = ir["op"]
    if op == "field":
        base = ir["lag"]["base"]
        var = ir["lag"].get("var")
        if var:
            lo, hi = bind[var]
            return (base + lo, base + hi)
        return (base, base)
    if op == "const":
        return (0, 0)
    if op in TS_OPS:
        b2 = dict(bind)
        b2[ir["var"]] = (ir["start"], ir["end"])
        spans = [history(a, b2) for a in ir["args"]]
        return (min(s[0] for s in spans), max(s[1] for s in spans))
    if op == "ema":
        lo, hi = history(ir["args"][0], bind)
        return (lo, hi + ir["window"] - 1)
    spans = [history(a, bind) for a in ir["args"]]
    return (min(s[0] for s in spans), max(s[1] for s in spans))


def warmup(ir):
    """Periods of history needed before the first valid value (max lag + 1 observations)."""
    lo, hi = history(ir)
    return {"min_lag": lo, "max_lag": hi, "observations_required": hi + 1, "uses_future": lo < 0}


def render(ir):
    op = ir["op"]
    if op == "field":
        lag = ir["lag"]
        t = "t" + (f"-{lag['var']}" if lag.get("var") else "") + (f"-{lag['base']}" if lag["base"] > 0 else f"+{-lag['base']}" if lag["base"] < 0 else "")
        return f"{ir['symbol']}[{t}]"
    if op == "const":
        v = ir["value"]
        return str(int(v)) if v == int(v) else str(v)
    a = [render(x) for x in ir.get("args", [])]
    infix = {"add": "+", "sub": "-", "mul": "*", "div": "/", "pow": "^"}
    if op in infix:
        return f"({a[0]} {infix[op]} {a[1]})"
    if op.startswith("ts_"):
        return f"{op}_{{{ir['var']}={ir['start']}..{ir['end']}}}({', '.join(a)})"
    if op == "ema":
        par = {"span": f"N={ir['n']}", "wilder": f"Wilder N={ir['n']}", "ratio": f"SMA N={ir['n']},M={ir['m']}"}[ir["smoothing"]]
        return f"ema[{par}, alpha={ir['alpha']:.6g}, init={ir['init']}, W={ir['window']}]({a[0]})"
    return f"{op}({', '.join(a)})"


# ------------------------------------------------------------------ trusted reference evaluator

SIGN_ZERO = 1e-12
# Numerical semantics of the trusted IR. A definition records the version it was frozen under and is always recomputed
# under that version (a study is never silently re-evaluated with new semantics; production audit P2).
#   trusted-ir-semantics/1  original: sign(x) = numpy sign
#   trusted-ir-semantics/2  sign(a - b) is 0 when |a - b| <= 1e-12 (|a| + |b|)  (2026-10-15, live J4: MA20 = MA30)
IR_SEMANTICS = "trusted-ir-semantics/2"
SUPPORTED_SEMANTICS = ("trusted-ir-semantics/1", "trusted-ir-semantics/2")
LEGACY_SEMANTICS = "trusted-ir-semantics/1"


def semantics_of(definition):
    """The version a frozen definition was made under; a definition from before versioning is version 1."""
    v = (definition or {}).get("ir_semantics") or LEGACY_SEMANTICS
    if v not in SUPPORTED_SEMANTICS:
        raise IRError("UNSUPPORTED_IR_SEMANTICS", v)
    return v


def tolerant_sign(x, scale):
    """sign(x) with a numerical zero: |x| <= SIGN_ZERO * scale counts as 0, where scale is |a| + |b| for x = a - b.
    Two equal moving averages (a suspended stock) differ by ~1e-16 depending on the summation order; without this the
    executor and the reference evaluator gave sign 0 and 1 for the same cell (live J4). NaN stays NaN."""
    if isinstance(x, (pd.DataFrame, pd.Series)):
        return np.sign(x).where(x.abs() > SIGN_ZERO * scale, 0.0).where(x.notna())
    return 0.0 if abs(x) <= SIGN_ZERO * abs(scale) else float(np.sign(x))


def sign_scale(node, ev, *ctx):
    """|a| + |b| for sign(a - b) or sign(a + b); otherwise |x| (relative zero only for differences and sums)."""
    child = node["args"][0]
    if child["op"] in ("sub", "add"):
        left, right = ev(child["args"][0], *ctx), ev(child["args"][1], *ctx)
        return abs(left) + abs(right)
    return 0.0


def evaluate(ir, panels, symbols, *, ddof=1, semantics=IR_SEMANTICS):
    """Evaluate IR on date x code DataFrames. symbols maps formula symbols to panel keys.

    Trusted, hand-written toolkit code used to produce expected values for tests. Windows require full
    observations (no partial windows); a future reference raises IRError instead of being computed.
    """
    if warmup(ir)["uses_future"]:
        raise IRError("FUTURE_REFERENCE", "formula references t+k; refusing to evaluate")

    def ev(node, bind):
        op = node["op"]
        if op == "field":
            frame = panels[symbols[node["symbol"]]]
            lag = node["lag"]["base"] + (bind[node["lag"]["var"]] if node["lag"].get("var") else 0)
            return frame.shift(lag)
        if op == "const":
            return node["value"]
        if op in TS_OPS:
            ks = range(node["start"], node["end"] + 1)
            stacks = []
            for arg in node["args"]:
                parts = [ev(arg, {**bind, node["var"]: k}) for k in ks]
                stacks.append(np.stack([p.to_numpy(dtype=float) for p in parts]))
                ref = parts[0]
            stack = stacks[0]
            with np.errstate(invalid="ignore", divide="ignore"):
                full = np.isfinite(stacks[0]).all(axis=0) & np.isfinite(stacks[-1]).all(axis=0)
                if op == "ts_rank":
                    # percentile rank (average ties) of the window's most recent element (k = start) among the window
                    cur = stack[0]
                    less = (stack < cur).sum(0)
                    equal = (stack == cur).sum(0)
                    agg = (less + (equal + 1) / 2.0) / stack.shape[0]
                elif op in PAIR_WINDOWS:
                    x, y = stacks
                    dx, dy = x - x.mean(0), y - y.mean(0)
                    cov = (dx * dy).sum(0) / (x.shape[0] - 1)
                    if op == "ts_cov":
                        agg = cov
                    else:
                        sx, sy = np.sqrt((dx * dx).sum(0) / (x.shape[0] - 1)), np.sqrt((dy * dy).sum(0) / (x.shape[0] - 1))
                        agg = np.where((sx > 0) & (sy > 0), cov / (sx * sy), np.nan)
                else:
                    agg = {"ts_sum": lambda s: s.sum(0), "ts_mean": lambda s: s.mean(0), "ts_prod": lambda s: s.prod(0),
                           "ts_std": lambda s: s.std(0, ddof=ddof), "ts_max": lambda s: s.max(0), "ts_min": lambda s: s.min(0)}[op](stack)
            return pd.DataFrame(np.where(full, agg, np.nan), index=ref.index, columns=ref.columns)
        if op == "ema":
            # literal recursion over the last W rows: seed, then y <- alpha*x + (1-alpha)*y (independent of the weights form)
            x = ev(node["args"][0], bind)
            w, alpha, n = node["window"], node["alpha"], node["n"]
            parts = np.stack([x.shift(j).to_numpy(dtype=float) for j in range(w - 1, -1, -1)])     # oldest first
            full = np.isfinite(parts).all(axis=0)
            if node["init"] == "first":
                y, rest = parts[0].copy(), parts[1:]
            else:
                y, rest = parts[:n].mean(0), parts[n:]
            for row in rest:
                y = alpha * row + (1 - alpha) * y
            return pd.DataFrame(np.where(full, y, np.nan), index=x.index, columns=x.columns)
        a = [ev(x, bind) for x in node["args"]]
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
            if op == "sign":
                if semantics == LEGACY_SEMANTICS:
                    return np.sign(a[0])
                return tolerant_sign(a[0], sign_scale(node, ev, bind))
            if op == "cs_rank":
                return a[0].rank(axis=1, method="average", pct=True)
            if op == "cs_zscore":
                return a[0].sub(a[0].mean(axis=1), axis=0).div(a[0].std(axis=1, ddof=1).replace(0, np.nan), axis=0)
            if op in ("maximum", "minimum"):
                # NaN in either operand stays NaN (no silent fill); a constant operand broadcasts
                x, y = a
                f = np.maximum if op == "maximum" else np.minimum
                if not isinstance(x, pd.DataFrame) and not isinstance(y, pd.DataFrame):
                    return float(f(x, y))
                if not isinstance(x, pd.DataFrame):
                    x, y = y, x
                return pd.DataFrame(f(x.to_numpy(dtype=float), y.to_numpy(dtype=float) if isinstance(y, pd.DataFrame) else float(y)),
                                    index=x.index, columns=x.columns)
        raise IRError("UNKNOWN_OP", op)

    out = ev(ir, {})
    if not isinstance(out, pd.DataFrame):
        raise IRError("CONSTANT_FACTOR", "formula does not depend on data")
    return out.replace([np.inf, -np.inf], np.nan)
