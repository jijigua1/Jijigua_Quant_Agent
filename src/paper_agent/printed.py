"""What the paper itself defines for a factor, read by the program (Candidate6 recovery, 2026-10-18).

The model's citation is only a pointer. Before a reading may become trusted IR, the program looks at the paper's own
definition of the factor:

* NUMBERED LISTS ("Alpha#23: <expression>"). The factor's printed expression starts at its own label and runs, across
  lines and blocks, until its brackets close. Text between two labels that is not part of either expression (notes,
  page breaks, headings, anything) is AMBIGUOUS and belongs to BOTH neighbours. Headings and section changes are not
  boundaries inside a list (only the next label is). After the last label the list ends at a heading, whose own text
  is still read, and a following paragraph that refers back is read too. Expression + ambiguous text are checked for a
  conditional as ONE text (an IF in one block and its ELSE in the next are one rule). The printed expression is parsed
  with the paper's own operators and compared numerically with the model's IR; a printed expression that cannot be
  parsed or computed is reported, never treated as agreement.
* PROSE. The quoted sentence; later sentences (this block and the next four) that refer back to the factor; earlier
  sentences of the block that point forward ("the following ...") or whose subject is the factor; a cited formula
  block read with the formula blocks that continue it. Another variable's sentence is not attributed to the factor
  (George-Hwang: "FHH ... is the winner dummy that takes 1 if ... zero otherwise. The 52-week high measure is ...").

Anything the program cannot establish is UNCERTAIN, and an uncertain definition is never promoted to trusted IR.
"""
import math
import re

CONDITIONAL = re.compile(
    r"\?[^?:]{1,200}:|\bif\b.{1,300}?\b(?:else|otherwise)\b|\botherwise\b|\bunless\b"
    r"|\bcase\s+when\b|\bpiecewise\b|\|\||&&|否则|若.{1,80}?则|当.{1,60}?时.{0,60}?(?:否则|其余|其他)|分段|其余情况|其他情况",
    re.I | re.S)
PARTIAL_CONDITIONAL = re.compile(r"\?\s*$|^\s*\?|\)\s*:\s*[-+\w(.]", re.M)
# In the sentences that define or refer back to a prose factor: a restriction or replacement of its value, which the trusted
# IR cannot express ("set to zero for ...", "only on days ...", "except ...", winsorised / truncated values)
MODIFIER = re.compile(
    r"\b(?:set|reset|replaced|truncated|capped|floored|winsori[sz]ed|trimmed)\s+(?:to|by|with|at)\b|\b(?:is|are|equals?|becomes?)\s+"
    r"(?:set\s+to\s+)?(?:zero|0|missing|nan)\b|\bonly\s+(?:\w+\s+){0,2}?(?:for|when|if|on|in|where|during|applicable)\b|\bexcept\b|\bexcluded?\b"
    r"|\brestricted\s+to\b|\bwhenever\b|\belsewhere\b|\bin\s+(?:all\s+)?other\s+cases\b|\bprovided\s+that\b|\bas\s+long\s+as\b"
    r"|设为|置为|记为0|记为零|仅在|仅对|只在|只对|除了|剔除|缩尾|截尾|其他情况|其余情况", re.I)
SENTENCE_END = re.compile(r"[.;。；!！?？](?=\s)|[。；]|\n\s*\n")
DEICTIC = re.compile(r"\b(?:this|that|the\s+(?:preceding|above|previous|resulting|same|said))\s+(?:value|factor|measure|signal|"
                     r"quantity|alpha|expression|result|score|indicator|ratio|variable)\b|\bit\s+is\s+(?:set|zero|replaced|defined)\b"
                     r"|前述|上述|该值|此值|该因子|此因子|该信号|此信号|上式|前式|该指标|此指标", re.I)
FORWARD = re.compile(r"\b(?:the\s+following|below|as\s+follows|the\s+next)\b|如下|以下|下述|下式", re.I)
SUBJECT_END = re.compile(r"\b(?:is|are|equals?|denotes?|takes?|measures?|represents?)\b|=|为|是|等于|表示", re.I)
MAX_CHARS, MAX_BLOCKS, PROSE_BLOCKS = 6000, 12, 4
_DASH = str.maketrans({"−": "-", "–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"'})
NUMBERED = re.compile(r"([A-Za-z][A-Za-z]{0,20})\s*#\s*(\d+)")


# ------------------------------------------------------------------------------------------------ locating quotes
def locate(text, quote):
    """(start, end) of `quote` in `text` under the evidence normalisation (dashes, quotes, whitespace runs), as RAW
    offsets of `text`; None when it is not there."""
    if not quote or not text:
        return None
    norm, where, space = [], [], False
    for i, ch in enumerate(text.translate(_DASH)):
        if ch.isspace():
            if not space and norm:
                norm.append(" ")
                where.append(i)
            space = True
            continue
        space = False
        norm.append(ch)
        where.append(i)
    q = re.sub(r"\s+", " ", quote.translate(_DASH)).strip()
    k = "".join(norm).find(q)
    if not q or k < 0:
        return None
    return where[k], where[k + len(q) - 1] + 1


def _positions(evidence, cits):
    """[(block index, offset in block, length)] for citations; None when one cannot be placed in its block."""
    blocks = (getattr(evidence, "doc", None) or {}).get("blocks") or []
    index = {b.get("id"): n for n, b in enumerate(blocks)}
    out = []
    for c in cits:
        p = evidence.by_id.get(c.get("passage")) or {}
        n = index.get(p.get("block_id"))
        loc = locate(p.get("text") or "", c.get("quote") or "")
        if n is None or loc is None:
            return None
        out.append((n, (p.get("char_start") or 0) + loc[0], loc[1] - loc[0]))
    return out


def _sentences(text):
    out, start = [], 0
    for m in SENTENCE_END.finditer(text):
        out.append((start, m.end()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


# ------------------------------------------------------------------------------------------------ numbered lists
def _stream(blocks):
    parts, starts, pos = [], [], 0
    for b in blocks:
        starts.append(pos)
        t = b.get("text") or ""
        parts.append(t)
        pos += len(t) + 1
    return "\n".join(parts), starts


def _expression_end(text, start, stop):
    """End offset of the printed expression starting at `start`: brackets balanced, then the end of that line or a ';'
    outside brackets. None when the brackets do not close before `stop` (the next label)."""
    depth, seen = 0, False
    for i in range(start, stop):
        ch = text[i]
        if ch in "([{":
            depth += 1
            seen = True
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return None
        elif not ch.isspace():
            seen = True
        if depth == 0 and seen and (ch == "\n" or ch == ";"):
            return i
    return stop if depth == 0 and seen else None


PAGE_NUMBER = re.compile(r"\s*(?:\d{1,4}|[ivxlcdm]{1,7})\s*", re.I)
SECTION_HEADING = re.compile(r"\s*(?:(?:[A-Z]|\d+)(?:\.\d+)*\.?\s+\S.{0,80}|(?:Appendix|Section|References|Bibliography)\b.{0,80})")


def _uninterpretable(band, end_heading=None):
    """True when a band holds anything but blank lines, page numbers and (after the last label) the numbered section
    heading that ends the list."""
    for line in band.split("\n"):
        if not line.strip() or PAGE_NUMBER.fullmatch(line):
            continue
        if end_heading is not None and line.strip() == end_heading.strip() and SECTION_HEADING.fullmatch(line):
            continue
        if re.search(r"[A-Za-z0-9一-鿿]", line):
            return True
    return False


def numbered_definition(evidence, family, number):
    """None when the paper has no `family#number:` label. Otherwise dict(expressions, ambiguous, zone, uncertain)."""
    blocks = (getattr(evidence, "doc", None) or {}).get("blocks") or []
    text, starts = _stream(blocks)
    peer = re.compile(rf"(?im)^[ \t]*{re.escape(family)}[ \t]*#[ \t]*(\d+)[ \t]*[:=：]")
    labels = [(m.start(), m.end(), int(m.group(1))) for m in peer.finditer(text)]
    own = [i for i, x in enumerate(labels) if x[2] == int(number)]
    if not own:
        return None

    def block_of(offset):
        return max(n for n, s in enumerate(starts) if s <= offset)

    ends = []                                   # expression end of every label (None = brackets never close)
    for i, (s, e, _) in enumerate(labels):
        stop = labels[i + 1][0] if i + 1 < len(labels) else len(text)
        ends.append(_expression_end(text, e, stop))
    expressions, ambiguous, uncertain, zone = [], [], None, []
    for i in own:
        s, e, _ = labels[i]
        if ends[i] is None:
            uncertain = "PRINTED_EXPRESSION_UNBALANCED"
            continue
        expressions.append(text[e:ends[i]].strip())
        if i == 0:                                  # before the first label: the blocks just above it
            lo = starts[max(block_of(s) - 2, 0)]
        else:                                       # an unclosed previous expression already runs up to this label
            lo = ends[i - 1] if ends[i - 1] is not None else s
        lead = text[lo:s]
        if i + 1 < len(labels):
            trail = text[ends[i]:labels[i + 1][0]]
        else:                                       # the last label: the list ends at the next heading
            b = block_of(ends[i])
            trail_parts = [text[ends[i]:starts[b] + len(blocks[b].get("text") or "")]]
            heading = None
            for j in range(b + 1, len(blocks)):
                trail_parts.append(blocks[j].get("text") or "")
                if blocks[j].get("kind") == "heading":
                    heading = j
                    break
                if j - b >= MAX_BLOCKS:
                    break
            if heading is None:
                uncertain = uncertain or "LIST_END_NOT_FOUND"
            else:                                   # a paragraph after the heading that refers back still counts
                for j in range(heading + 1, min(heading + 3, len(blocks))):
                    t = blocks[j].get("text") or ""
                    if DEICTIC.search(t) or re.search(rf"{re.escape(family)}\s*#\s*{number}\b", t):
                        trail_parts.append(t)
            trail = "\n".join(trail_parts)
        for band in (lead, trail):
            if len(band) > MAX_CHARS or band.count("\n") > MAX_BLOCKS:
                uncertain = uncertain or "DEFINITION_SCOPE_UNBOUNDED"
        # Any text beside the printed expression that is not a page number may qualify it in words the program cannot
        # interpret ("used whenever ...; in all other cases 0"): the definition is then uncertain, whatever its wording
        # (hold-out H-M01 on C6R2: keyword spotting cannot be complete). Above the FIRST label a list usually has its
        # introduction, which counts only when it points to a factor or states a condition; after the LAST label a
        # numbered section heading ends the list.
        heading_end = blocks[heading].get("text") if i + 1 == len(labels) and heading is not None else None
        if _uninterpretable(trail, heading_end) or (
                _uninterpretable(lead) if i > 0 else (FORWARD.search(lead) or DEICTIC.search(lead) or CONDITIONAL.search(lead)
                                                       or re.search(rf"{re.escape(family)}\s*#", lead))):
            uncertain = uncertain or "PROSE_AROUND_DEFINITION"
        ambiguous += [lead, trail]
        zone.append((lo if lo is not None else s, ends[i] + len(trail)))
    return dict(expressions=expressions, ambiguous=[a for a in ambiguous if a.strip()], zone=zone,
                stream_starts=starts, uncertain=uncertain)


# ------------------------------------------------------------------------------------------------ prose
def prose_definition(evidence, primary, others, names):
    """The texts that define a factor written in prose; None when a quote cannot be placed."""
    blocks = (getattr(evidence, "doc", None) or {}).get("blocks") or []
    pos_p, pos_o = _positions(evidence, primary), _positions(evidence, others)
    if pos_p is None:
        return None
    refs = [re.escape(x) for x in names if x and len(x) >= 3]
    refer = re.compile("|".join(refs), re.I) if refs else None
    texts = []
    for (n, off, length), is_primary in [(p, True) for p in pos_p] + [(p, False) for p in (pos_o or [])]:
        block = blocks[n]
        text = block.get("text") or ""
        if block.get("kind") == "formula":
            lo, hi = n, n
            while lo > 0 and blocks[lo - 1].get("kind") == "formula" and n - lo < MAX_BLOCKS:
                lo -= 1
            while hi + 1 < len(blocks) and blocks[hi + 1].get("kind") == "formula" and hi - n < MAX_BLOCKS:
                hi += 1
            texts.append("\n".join(blocks[j].get("text") or "" for j in range(lo, hi + 1)))
            continue
        sents = _sentences(text)
        own = next(((a, b) for a, b in sents if a <= off < b), (0, len(text)))
        texts.append(text[own[0]:own[1]])
        if not is_primary:
            continue
        for a, b in sents:                          # earlier sentences: forward pointers, or the factor as subject
            if b <= own[0]:
                s = text[a:b]
                subject = s[:SUBJECT_END.search(s).start()] if SUBJECT_END.search(s) else s
                if FORWARD.search(s) or DEICTIC.search(subject) or (refer and refer.search(subject)):
                    texts.append(s)
        later = [text[a:b] for a, b in sents if a >= own[1]]
        for j in range(n + 1, min(n + 1 + PROSE_BLOCKS, len(blocks))):
            later += [(blocks[j].get("text") or "")[a:b] for a, b in _sentences(blocks[j].get("text") or "")]
        texts += [s for s in later if DEICTIC.search(s) or (refer and refer.search(s))]
    return texts


# ------------------------------------------------------------------------------------------------ printed expressions
_TOKEN = re.compile(r"\s*(?:(?P<num>\d+\.\d*|\.\d+|\d+(?:[eE][-+]?\d+)?)|(?P<name>[A-Za-z_][A-Za-z_0-9.]*)"
                    r"|(?P<op>\|\||&&|==|!=|<=|>=|[-+*/^(),<>?:]))")


class Unsupported(Exception):
    """The printed expression uses something the program cannot parse or compute; never read as agreement."""


def _tokens(src):
    pos, out = 0, []
    src = src.translate(_DASH)
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m or m.end() == pos:
            if src[pos:].strip() == "":
                break
            raise Unsupported(f"unreadable text near {src[pos:pos + 12]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def _literal(text):
    """A printed number as a float only when the float keeps its magnitude: a literal that underflows to 0 or overflows
    to inf would let a different formula compare equal (C11 report D01: 1e-400 * close * 10^300 read as 0)."""
    from decimal import Decimal, InvalidOperation
    try:
        exact = Decimal(text)
    except InvalidOperation:
        raise Unsupported(f"unreadable number {text!r}") from None
    value = float(text)
    if not math.isfinite(value) or (value == 0.0) != (exact == 0) or (exact != 0 and abs(exact) < Decimal("1e-300")) \
            or abs(exact) > Decimal("1e300"):
        raise Unsupported(f"number {text!r} is outside the exactly comparable range")
    return value


def parse_printed(src):
    """AST of a printed formulaic-alpha expression: ('num', v) | ('name', s) | ('call', f, [args]) | ('bin', op, a, b)
    | ('neg', a) | ('cond', c, a, b)."""
    toks, i = _tokens(src), [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else (None, None)

    def take(v=None):
        t = peek()
        if v is not None and t[1] != v:
            raise Unsupported(f"expected {v!r}, found {t[1]!r}")
        i[0] += 1
        return t

    def ternary():
        c = logic()
        if peek()[1] == "?":
            take("?")
            a = ternary()
            take(":")
            return ("cond", c, a, ternary())
        return c

    def logic():
        a = compare()
        while peek()[1] in ("||", "&&"):
            op = take()[1]
            a = ("bin", op, a, compare())
        return a

    def compare():
        a = additive()
        while peek()[1] in ("<", ">", "<=", ">=", "==", "!="):
            op = take()[1]
            a = ("bin", op, a, additive())
        return a

    def additive():
        a = term()
        while peek()[1] in ("+", "-"):
            op = take()[1]
            a = ("bin", op, a, term())
        return a

    def term():
        a = power()
        while peek()[1] in ("*", "/"):
            op = take()[1]
            a = ("bin", op, a, power())
        return a

    def power():
        a = unary()
        if peek()[1] == "^":
            take("^")
            return ("bin", "^", a, unary())
        return a

    def unary():
        if peek()[1] == "-":
            take("-")
            return ("neg", unary())
        if peek()[1] == "+":
            take("+")
            return unary()
        return atom()

    def atom():
        kind, v = take()
        if kind == "num":
            return ("num", _literal(v))
        if kind == "name":
            if peek()[1] == "(":
                take("(")
                args = []
                if peek()[1] != ")":
                    args.append(ternary())
                    while peek()[1] == ",":
                        take(",")
                        args.append(ternary())
                take(")")
                return ("call", v.lower(), args)
            return ("name", v.lower())
        if v == "(":
            a = ternary()
            take(")")
            return a
        raise Unsupported(f"unexpected {v!r}")

    tree = ternary()
    if i[0] != len(toks):
        raise Unsupported(f"text after the expression: {toks[i[0]][1]!r}")
    return tree


def has_conditional(tree):
    if tree[0] == "cond":
        return True
    if tree[0] == "bin" and tree[1] in ("<", ">", "<=", ">=", "==", "!=", "||", "&&"):
        return True
    return any(has_conditional(x) for x in _children(tree))


def _children(t):
    if t[0] == "call":
        return t[2]
    if t[0] == "bin":
        return [t[2], t[3]]
    if t[0] == "neg":
        return [t[1]]
    if t[0] == "cond":
        return [t[1], t[2], t[3]]
    return []


def uses(tree, names):
    return (tree[0] in ("name", "call") and tree[1] in names) or any(uses(x, names) for x in _children(tree))


FIELDS = ("open", "high", "low", "close", "volume")


def evaluate_printed(tree, panels):
    """The paper's own operators (Appendix A.2 of 101 Formulaic Alphas) with the trusted evaluator's conventions: full
    windows only, ddof = 1, average-tie percentile ranks, Pearson correlation; a non-integer window is floored."""
    import numpy as np
    import pandas as pd

    def win(x):
        if x[0] != "num" or x[1] < 1:
            raise Unsupported("window is not a positive number")
        return int(math.floor(x[1]))

    def roll(frame, d, fn):
        return frame.rolling(d, min_periods=d).apply(fn, raw=True) if callable(fn) else getattr(frame.rolling(d, min_periods=d), fn)()

    def arithmetic(op,a,b,result):
        # Check intermediate precision, not just literal conversion. Otherwise
        # (1e-200*close)*1e-200*1e100 is certified as zero after underflow,
        # or (1e100+close)-1e100 loses the entire market-dependent term.
        x,y,z=np.asarray(a,dtype=float),np.asarray(b,dtype=float),np.asarray(result,dtype=float)
        finite=np.isfinite(x)&np.isfinite(y)
        bad=finite&(~np.isfinite(z))&(y!=0 if op=='/' else True)
        if op in ('*','/','^'):
            bad|=finite&(x!=0)&(y!=0)&(z==0)
        if op=='+':bad|=finite&(((z==x)&(y!=0))|((z==y)&(x!=0)))
        if op=='-':bad|=finite&(((z==x)&(y!=0))|((z==-y)&(x!=0)))
        if np.any(bad):raise Unsupported('intermediate arithmetic loses precision; not checkable')
        return result

    def ev(t):
        kind = t[0]
        if kind == "num":
            return t[1]
        if kind == "name":
            if t[1] in FIELDS:
                return panels[t[1]]
            if t[1] == "returns":
                return panels["close"] / panels["close"].shift(1) - 1
            if t[1] == "vwap":                         # A.3: daily volume-weighted average price = amount / volume
                return panels["amount"] / panels["volume"].replace(0, np.nan)
            m = re.fullmatch(r"adv(\d+)", t[1])        # A.3: average daily dollar volume over the past d days
            if m and int(m.group(1)) >= 1:
                return panels["amount"].rolling(int(m.group(1)), min_periods=int(m.group(1))).mean()
            raise Unsupported(f"data {t[1]!r} is not a published field")
        if kind == "neg":
            return -ev(t[1])
        if kind == "cond":
            raise Unsupported("conditional")
        if kind == "bin":
            a, b = ev(t[2]), ev(t[3])
            with np.errstate(divide="ignore", invalid="ignore"):
                if t[1] == "+":
                    return arithmetic('+',a,b,a+b)
                if t[1] == "-":
                    return arithmetic('-',a,b,a-b)
                if t[1] == "*":
                    return arithmetic('*',a,b,a*b)
                if t[1] == "/":
                    den = b.replace(0, np.nan) if isinstance(b, pd.DataFrame) else (np.nan if b == 0 else b)
                    return arithmetic('/',a,den,a/den)
                if t[1] == "^":
                    return arithmetic('^',a,b,a**b)
            raise Unsupported(f"operator {t[1]}")
        f, args = t[1], t[2]
        if f in ("abs", "log", "sign", "rank") and len(args) == 1:
            x = ev(args[0])
            if f == "abs":
                return x.abs()
            if f == "log":
                return np.log(x.where(x > 0))
            if f == "sign":
                return np.sign(x)
            return x.rank(axis=1, method="average", pct=True)
        if f in ("delay", "delta") and len(args) == 2:
            x, d = ev(args[0]), win(args[1])
            return x.shift(d) if f == "delay" else x - x.shift(d)
        if f in ("sum", "ts_sum", "stddev", "ts_min", "ts_max", "min", "max", "product") and len(args) == 2 and args[1][0] == "num":
            x, d = ev(args[0]), win(args[1])
            if f in ("sum", "ts_sum"):
                return roll(x, d, "sum")
            if f == "stddev":
                return x.rolling(d, min_periods=d).std(ddof=1)
            if f in ("ts_min", "min"):
                return roll(x, d, "min")
            if f in ("ts_max", "max"):
                return roll(x, d, "max")
            return roll(x, d, lambda v: float(np.prod(v)))
        if f in ("min", "max") and len(args) == 2:      # two expressions: element-wise, NaN propagates (as the trusted IR)
            x, y = ev(args[0]), ev(args[1])
            fn = np.minimum if f == "min" else np.maximum
            if not isinstance(x, pd.DataFrame):
                x, y = y, x
            if not isinstance(x, pd.DataFrame):
                raise Unsupported("constant min/max")
            return pd.DataFrame(fn(x.to_numpy(dtype=float), y.to_numpy(dtype=float) if isinstance(y, pd.DataFrame) else float(y)),
                                index=x.index, columns=x.columns)
        if f in ("correlation", "covariance") and len(args) == 3:
            x, y, d = ev(args[0]), ev(args[1]), win(args[2])
            out = {}
            for c in x.columns:
                r = x[c].rolling(d, min_periods=d)
                out[c] = r.corr(y[c]) if f == "correlation" else r.cov(y[c], ddof=1)
            return pd.DataFrame(out, index=x.index)
        if f == "ts_rank" and len(args) == 2:
            x, d = ev(args[0]), win(args[1])
            return roll(x, d, lambda v: ((v < v[-1]).sum() + ((v == v[-1]).sum() + 1) / 2.0) / len(v))
        if f == "decay_linear" and len(args) == 2:
            x, d = ev(args[0]), win(args[1])
            w = np.arange(1, d + 1, dtype=float)               # oldest weight 1 ... today weight d, rescaled to sum 1
            return roll(x, d, lambda v: float(np.dot(v, w) / w.sum()))
        if f == "signedpower" and len(args) == 2:
            x, a = ev(args[0]), ev(args[1])
            return np.sign(x) * x.abs() ** a
        raise Unsupported(f"function {f}({len(args)} arguments)")

    out = ev(tree)
    if not isinstance(out, pd.DataFrame):
        raise Unsupported("constant expression")
    return out.replace([np.inf, -np.inf], np.nan)


def compare_printed(tree, ir, symbol_fields):
    """dict(agree, compared, mismatch_share) of the printed expression and the model's IR on one synthetic panel;
    raises Unsupported when either side cannot be computed."""
    import numpy as np
    from paper_research.factor_ir import evaluate, fields_used
    from .reconcile import _panels
    if not set(fields_used(ir)) <= set(symbol_fields):
        raise Unsupported("the reading uses a symbol that is not a market field")
    panels = _panels(rows=520)
    try:
        a = evaluate_printed(tree, panels).to_numpy(dtype=float)
        b = evaluate(ir, panels, symbol_fields).to_numpy(dtype=float)
    except Unsupported:
        raise
    except Exception as e:  # noqa: BLE001 -- an evaluation error is "cannot compare", never agreement
        raise Unsupported(f"{type(e).__name__}: {e}"[:120])
    both = np.isfinite(a) & np.isfinite(b)
    if both.sum() < 0.3 * max(np.isfinite(a).sum(), 1):
        return {"agree": False, "compared": int(both.sum()), "mismatch_share": None}
    from .reconcile import numerical_matches
    close = numerical_matches(a,b)
    if close is None:
        return {"agree":False,"compared":int(both.sum()),"mismatch_share":None}
    share = float(1 - close.mean())
    return {"agree": bool(np.all(close)), "compared": int(both.sum()), "mismatch_share": share}


def check(evidence, name, formula_cits, verbal_cits, other_cits, aliases, ir, symbol_fields):
    """Program findings for one factor reading that has an IR: list of conflict dicts and the conditional text (if any).
    (A check that the source mentions 'sign' whenever the reading uses sign() was tried and removed: it blocked the AQR
    time-series momentum reading, whose sign is standard and not written in the paper; for printed formulas an added
    sign term is caught by the numeric comparison, and a conditional by the scope check.)"""
    conf, found = [], None
    num = NUMBERED.search(name or "")
    printed = numbered_definition(evidence, num.group(1), num.group(2)) if num else None
    texts = []
    if num and printed is None:
        stream = _stream((getattr(evidence, "doc", None) or {}).get("blocks") or [])[0]
        if re.search(rf"(?im)^[ \t]*{re.escape(num.group(1))}[ \t]*#[ \t]*\d+[ \t]*[:=：]", stream):
            # the paper numbers its factors but prints no label for this one: where it is defined is unknown
            conf.append({"code": "DEFINITION_SCOPE_UNCERTAIN", "blocking": True, "reason": "FACTOR_LABEL_NOT_FOUND",
                         "detail": f"论文按编号列出因子，但没有 {num.group(0)} 的标签，无法确定其定义范围，不作为可信公式执行"})
    if printed is not None:
        texts = printed["expressions"] + printed["ambiguous"]
        joined = "\n".join(texts)
        if printed["uncertain"]:
            conf.append({"code": "DEFINITION_SCOPE_UNCERTAIN", "blocking": True, "reason": printed["uncertain"],
                         "detail": "程序无法确定论文中该因子定义的完整范围（" + printed["uncertain"] + "），不作为可信公式执行"})
        cited = _positions(evidence, list(formula_cits))
        if cited is not None and printed["zone"]:
            starts = printed["stream_starts"]
            inside = [lo <= starts[n] + off < hi for n, off, _ in cited for lo, hi in printed["zone"]]
            if cited and not any(inside):
                conf.append({"code": "DEFINITION_SCOPE_UNCERTAIN", "blocking": True, "reason": "QUOTE_OUTSIDE_FACTOR",
                             "detail": "公式引文不在论文中该因子标签所定义的范围内"})
        if len({re.sub(r"\s+", "", e) for e in printed["expressions"]}) > 1:
            conf.append({"code": "DEFINITION_SCOPE_UNCERTAIN", "blocking": True, "reason": "LABEL_REPEATED_WITH_DIFFERENT_TEXT",
                         "detail": "论文中该因子的标签出现多次且内容不同，无法确定哪一个是定义，不作为可信公式执行"})
        trees = []
        for expr in printed["expressions"]:
            try:
                trees.append(parse_printed(expr))
            except Unsupported as e:
                trees.append(e)
        if CONDITIONAL.search(joined) or PARTIAL_CONDITIONAL.search(joined) or any(
                not isinstance(t, Exception) and has_conditional(t) for t in trees):
            found = next((t for t in texts if CONDITIONAL.search(t) or PARTIAL_CONDITIONAL.search(t)), printed["expressions"][0]
                         if printed["expressions"] else joined)
        elif trees:
            t = trees[0]
            try:
                if isinstance(t, Exception):
                    raise t
                cmp = compare_printed(t, ir, symbol_fields)
            except Unsupported as e:
                conf.append({"code": "PRINTED_FORMULA_NOT_CHECKED", "blocking": True, "detail":
                             f"论文为该因子印出了公式 {printed['expressions'][0][:120]}，但程序无法读取或计算它（{str(e)[:80]}），"
                             "不能确认模型的读数与原文一致，不作为可信公式执行；可改走新算法代码审批"})
            else:
                if not cmp["agree"]:
                    conf.append({"code": "MODEL_FORMULA_CONTRADICTS_PAPER", "blocking": True, "detail":
                                 f"论文印出的公式 {printed['expressions'][0][:120]} 与模型读数在合成数据上不一致"
                                 f"（不一致比例 {cmp['mismatch_share']}）"})
    else:
        verbal = list(verbal_cits)
        texts = prose_definition(evidence, list(formula_cits) + verbal, list(other_cits), aliases)
        if texts is None:
            conf.append({"code": "DEFINITION_SCOPE_UNCERTAIN", "blocking": True, "reason": "QUOTE_POSITION_UNRESOLVED",
                         "detail": "引文无法在原文块中定位，不作为可信公式执行"})
            texts = []
        found = next((t for t in texts if CONDITIONAL.search(t) or MODIFIER.search(t)), None)
        formula_texts = [t for t in texts if "\n" in t or t.count("(") >= 2]
        if not found:
            found = next((t for t in formula_texts if PARTIAL_CONDITIONAL.search(t)), None)
    return conf, found
