"""AI reading x deterministic program analysis: free parameters, conflict sources and the reader's bounded investigation.

The model (DeepSeek, text only) and the program read the same paper but neither is assumed right:

* parameters -- a window or smoothing count the paper names with a symbol (N_fast, tau, X, lead) stays symbolic in the
  model's formula and is listed with the value and the quotes that give it. The program binds a value only when the
  number is in a verified quote of the paper (or the user typed it, e.g. "N=20"); otherwise the factor waits for the user
  (FREE_PARAMETER_UNBOUND) and nothing is invented. A formula the parser cannot read is "程序解析未完成", not "论文没有定义".
* sources -- every conflict carries the program's classification of where it comes from (AI misreading, PDF/formula
  extraction, notation the parser does not support yet, genuine paper ambiguity, data mismatch, free parameter). The
  reader may claim another source after investigating; the claim is accepted only when the program can check it
  (garbled text layers for an extraction error, a verified quote for an ambiguity or a parameter).
* investigation -- the reader may call the existing evidence tools (search, read a passage, read a whole page together
  with the PDF's raw text layer of that page) within fixed call, character and round budgets, then answers once; the
  same deterministic verification runs again on the answer. DeepSeek cannot see images: page images are saved only for
  a human reviewer.
"""
from __future__ import annotations

import re

from paper_research.factor_ir import IRError, parse_formula

from .semantics import _numbers_in, plain

VERSION = "paper_agent.reconcile/1.0"

SOURCES = ("ai_misreading", "extraction_error", "unsupported_notation", "paper_ambiguity", "data_mismatch", "free_parameter")
SOURCE_CN = {"ai_misreading": "模型理解错误（读数与原文矛盾）", "extraction_error": "原文无法解析（PDF 文字层或公式无法读取）",
             "unsupported_notation": "算子不支持（原文写法超出程序可信公式的表达范围，不是读错）",
             "paper_ambiguity": "数学语义不确定（原文未写明、有歧义或两次读数不一致）", "data_mismatch": "研究对象与现有数据不匹配",
             "free_parameter": "需要用户选择的自由参数"}
# what each source means for the user, shown once under the blocked reasons
SOURCE_HINT = {"extraction_error": "论文 PDF 中这部分文字或公式无法被程序读出，程序没法核对模型的读数；可以对照原文页给出公式，或提供可机读的版本。",
               "unsupported_notation": "原文的数学写法（例如条件分支、按日历期间计数的窗口、行业中性化）超出程序能安全计算的算子集合，"
                                       "这不是模型读错；可改走新算法代码审批路线，或给出可信公式能表达的定义。",
               "paper_ambiguity": "原文没有写明，或存在多种合理理解（包括两次独立读数不一致），需要你明确定义后再研究。",
               "ai_misreading": "模型的读数与原文矛盾，已拒绝；可以让我重新读取。",
               "data_mismatch": "论文研究对象或所需数据不在已发布数据中。", "free_parameter": "论文没有给出该参数的取值，需要你指定。"}
CODE_SOURCE = {
    "FORMULA_UNPARSEABLE": "unsupported_notation", "DERIVATION_UNPARSEABLE": "unsupported_notation",
    "FREE_PARAMETER_UNBOUND": "free_parameter", "PARAMETER_SELECTED_FROM_PAPER_VALUES": "free_parameter",
    "PARAMETER_CHOSEN_NOT_IN_PAPER": "free_parameter", "PARAMETER_VALUE_UNVERIFIED": "ai_misreading",
    "FORMULA_NOT_ESTABLISHED": "paper_ambiguity", "RETURN_INTERPRETED_FROM_MOMENTUM_WORDING": "paper_ambiguity",
    "ALGORITHM_STEP_AMBIGUOUS": "paper_ambiguity", "SYMBOL_UNDEFINED": "paper_ambiguity",
    "FIELD_NOT_IN_PANEL": "data_mismatch", "ASSET_CLASS_NOT_AVAILABLE": "data_mismatch",
    "FORMULA_DEGENERATE_TERMS": "extraction_error",
    "CALENDAR_WINDOW_UNSUPPORTED": "unsupported_notation", "CONDITIONAL_NOT_REPRESENTABLE": "unsupported_notation",
    "FORMULA_READINGS_DISAGREE": "paper_ambiguity",
}
GREEK = ("alpha|beta|gamma|delta|epsilon|zeta|eta|theta|kappa|lambda|mu|nu|xi|rho|sigma|tau|phi|chi|psi|omega|"
         "Gamma|Delta|Theta|Lambda|Sigma|Phi|Psi|Omega")
GREEK_UNI = {"α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta", "θ": "\\theta", "κ": "\\kappa", "λ": "\\lambda",
             "μ": "\\mu", "ν": "\\nu", "ρ": "\\rho", "σ": "\\sigma", "τ": "\\tau", "φ": "\\phi", "ω": "\\omega"}
INDEX_LETTERS = {"i", "t", "k", "j", "s", "l", "m", "d"}
CALENDAR_COUNT = re.compile(r"\b(?:number|count) of (?:trading |valid |observed )?days\b[^.;]{0,60}\b(?:data|available|availability|in (?:the )?(?:year|month|week|quarter))"
                            r"|\bdata availability\b|\bdays? with (?:available )?data\b|有数据的(?:交易)?日|当(?:年|月|季|周)(?:的)?(?:实际|有效)?(?:有数据的)?交易日(?:数|天数)"
                            r"|(?:年|月|季|周)内(?:的)?(?:实际|有效)(?:交易)?(?:日数|天数)", re.I)
_BOUND = re.compile(r"(?:\^|_)\{((?:[^{}]|\{[^{}]*\})*)\}")
_TOKEN = re.compile(rf"\\(?:{GREEK})(?![A-Za-z])(?:_\{{?[A-Za-z0-9]+\}}?)?|(?<![\\A-Za-z])[A-Za-z][A-Za-z]*(?:_\{{?(?:\\text\{{)?[A-Za-z0-9]+\}}?\}}?)?")


def _canon(sym):
    """'N_{\\text{fast}}', 'N_{fast}', 'N_fast' -> 'N_fast'; '\\tau' stays."""
    s = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]*)\}", r"\1", str(sym or "").strip())
    s = s.replace("{", "").replace("}", "").replace(" ", "")
    return "".join(GREEK_UNI.get(ch, ch) for ch in s)          # "τ" and "\tau" are the same parameter


def _pattern(sym):
    c = _canon(sym)
    if not c:
        return None
    base, _, sub = c.partition("_")
    b = re.escape(base)
    if sub:
        e = re.escape(sub)
        return re.compile(rf"(?<![A-Za-z\\]){b}_(?:\{{\s*(?:\\(?:text|mathrm)\{{\s*{e}\s*\}}|{e})\s*\}}|{e}(?![A-Za-z0-9]))")
    return re.compile(rf"(?<![A-Za-z\\]){b}(?![A-Za-z])(?!\s*_\s*\{{?\s*[A-Za-z])" if not base.startswith("\\")
                      else rf"{b}(?![A-Za-z])(?!\s*_\s*\{{?\s*[A-Za-z])")


def _fold(latex):
    """{14-1} -> {13}: integer arithmetic inside a bound after binding (only braces holding nothing but the arithmetic)."""
    prev = None
    while prev != latex:
        prev = latex
        latex = re.sub(r"\{\s*(\d+)\s*([-+])\s*(\d+)\s*\}", lambda m: "{%d}" % (int(m[1]) + int(m[3]) if m[2] == "+" else int(m[1]) - int(m[3])), latex)
        latex = re.sub(r"\{\s*(\d+)\s*\}", r"{\1}", latex)
    return latex


def substitute(latex, sym, value):
    rx = _pattern(sym)
    return _fold(rx.sub(str(int(value)), latex)) if rx else latex


def symbolic_counts(latex, data_symbols=()):
    """Symbols used as counts (window bounds, smoothing spans, lags) that the grammar cannot read. Each is tested by
    binding every candidate to a dummy integer: if the formula then parses, the only gap is unbound parameters."""
    found = []
    depth, rhs = 0, latex or ""
    for i, ch in enumerate(rhs):                 # the left-hand side (e.g. R^{\Sigma}_{\tau,t}) names the factor only
        depth += (ch == "{") - (ch == "}")
        if ch == "=" and depth == 0:
            rhs = rhs[i + 1:]
            break
    for m in _BOUND.finditer(rhs):
        for t in _TOKEN.findall(m.group(1)):
            c = _canon(t)
            if c in INDEX_LETTERS or c.startswith(("\\le", "\\ge", "\\text", "\\operatorname")) or c in data_symbols:
                continue
            if c not in found:
                found.append(c)
    if not found:
        return []
    trial = latex
    for c in found:
        trial = substitute(trial, c, 7)
    try:
        parse_formula(trial)
    except (IRError, ValueError):
        return []
    return found


def calendar_window_conflict(text, symbol=None):
    """A window whose length is the number of days with data in a calendar period (Amihud 2002: ILLIQ_iy is the average of
    |R|/VOLD over the D_iy days with data of stock i in year y). The trusted IR has only fixed-length row windows that need
    every row present: no calendar grouping, no 'days with data' average. A fixed number of days (e.g. 250) would change
    the definition (period alignment, missing-day handling), so the factor is not run as trusted IR."""
    return {"code": "CALENDAR_WINDOW_UNSUPPORTED", "symbol": symbol, "blocking": True, "evidence": str(text)[:200],
            "detail": "原文按日历期间计算：窗口长度是该股票在当年（或当月）实际有数据的交易日数（依据：“" + str(text)[:120] + "”），"
                      "随股票和期间变化。可信公式只支持固定行数、窗口内每天都有数据的滚动窗口，没有“按日历期间、只计有数据交易日”"
                      "的算子；用固定天数（如250天）代替会改变定义（期间对齐和缺失日处理都不同），因此不作为可信公式执行。"
                      "如需研究，可改走新算法代码审批路线（按日历期间分组的实现须经你审核和已知真值测试，且不进入2026评价）。"}


def bind_parameters(latex, params, evidence_quotes, user_params=None, data_symbols=(), report_undeclared=True):
    """Bind the formula's symbolic counts. Returns (bound latex, parameter records, conflicts).

    A value is used only when it is in a verified quote of the paper (status PAPER) or the user typed it (USER); a value
    the reader gives without such a quote is UNVERIFIED and not used; no value at all is UNSTATED. The reader's list of
    values the paper tested (paper_values) is kept only for numbers found in its verified quotes."""
    user = {_canon(k): v for k, v in (user_params or {}).items()}
    records, conf, out = [], [], latex
    declared = {}
    for p in params or []:
        # a "parameter" whose symbol is a number (live J2: "21") is a constant in the formula, checked by the constant rules
        if isinstance(p, dict) and p.get("symbol") and not re.fullmatch(r"[\d.]+", _canon(p["symbol"])):
            declared[_canon(p["symbol"])] = p
    # a count fixed by data availability or the calendar (Amihud's D_{i,y} = days with data for stock i in year y) is not a
    # free parameter, and no fixed number of days may stand in for it (C6R4): the window is not computable as trusted IR
    calendar = [s for s, p in declared.items() if CALENDAR_COUNT.search(f"{p.get('meaning') or ''} {p.get('status') or ''}")]
    for s in calendar:
        conf.append(calendar_window_conflict(declared.pop(s).get("meaning") or s, symbol=s))
    in_formula = [s for s in declared if _pattern(s) and _pattern(s).search(latex or "")]
    counts = symbolic_counts(latex, data_symbols)
    # a symbolic count the reader did not declare (e.g. Amihud's D = days with data in year y, a calendar window) is not
    # a free parameter by itself: the formula repair asks the reader to declare it (never a nominal length, C6R4)
    undeclared = [c for c in counts if c not in declared and c not in user and c not in calendar]
    if undeclared and report_undeclared:
        conf.append({"code": "FORMULA_UNPARSEABLE", "blocking": True, "symbols": undeclared,
                     "detail": f"UNDECLARED_SYMBOLIC_COUNT: {', '.join(undeclared)}（公式中的计数符号没有在参数表中声明）"})
    for sym in dict.fromkeys(in_formula + [c for c in counts if c in user]):
        p = declared.get(sym, {})
        quotes = evidence_quotes(p.get("citations") or [])
        in_quotes = _numbers_in([plain(q["quote"]) for q in quotes])
        paper_values = sorted({int(v) for v in (p.get("paper_values") or []) if isinstance(v, (int, float)) and int(v) in in_quotes})
        value = p.get("value") if isinstance(p.get("value"), (int, float)) and not isinstance(p.get("value"), bool) else None
        if value is not None and (value != int(value) or value < 1):
            value = None                       # counts only: a smoothing weight such as alpha is written as ema_N, not bound here
        rec = {"symbol": sym, "meaning": (p.get("meaning") or "")[:160], "paper_values": paper_values, "citations": quotes,
               "model_value": value, "model_status": p.get("status")}
        if sym in user:
            rec.update(value=int(user[sym]), status="USER")
        elif value is not None and int(value) in in_quotes:
            rec.update(value=int(value), status="PAPER")
            if len(set(paper_values) | {int(value)}) > 1 and p.get("status") != "stated":
                conf.append({"code": "PARAMETER_SELECTED_FROM_PAPER_VALUES", "symbol": sym, "blocking": False,
                             "values": sorted(set(paper_values) | {int(value)}),
                             "detail": f"参数 {sym} 原文测试过多个取值 {sorted(set(paper_values) | {int(value)})}，本次采用 {int(value)}"
                                       f"（依据：p{quotes[0]['page']}“{quotes[0]['quote'][:100]}”）；其他取值需另行研究"})
        else:
            rec.update(value=None, status="UNVERIFIED" if value is not None else "UNSTATED")
        records.append(rec)
        if rec["value"] is not None:
            out = substitute(out, sym, rec["value"])
        else:
            cands = f"；原文出现过的取值：{paper_values}" if paper_values else ""
            why = (f"模型给出的取值 {value} 在其引用的原文中找不到" if value is not None else "论文中没有找到该参数的取值")
            conf.append({"code": "FREE_PARAMETER_UNBOUND" if value is None else "PARAMETER_VALUE_UNVERIFIED", "symbol": sym,
                         "blocking": True, "candidates": paper_values,
                         "detail": f"公式中的参数 {sym}（{rec['meaning'] or '窗口/平滑长度'}）没有确定的数值：{why}{cands}。"
                                   f"不会自行选择；可在请求中指定，例如“{sym}=20”"})
    return out, records, conf


def unreadable_formula(item, evidence):
    """Pages where the factor's printed formula cannot be read by the program (unresolved formula regions, or cited
    formula blocks that are garbled), when the program did not rebuild the same formula from the layout itself.
    Then the formula is the reader's reconstruction from prose and must be checked by a person against the page
    (live A/B: cond-mat GMI was read once as blocked and once as price change / mean volume -- the paper says volume
    enters as a multiplicative factor)."""
    f = item.get("formula") or {}
    if f.get("v03_formula") or not f.get("latex"):
        return []
    cits = f.get("citations") or (item.get("verbal_definition") or {}).get("citations") or []
    pages = sorted({c.get("page") for c in cits if isinstance(c.get("page"), int)})
    cited = {c.get("passage") for c in cits}
    regions = {r.get("page") for r in (evidence.doc.get("extraction_report") or {}).get("formula_regions_unresolved") or []
               if isinstance(r.get("page"), int)}
    garbled = {p["page"] for p in evidence.passages if p["id"] in cited and p.get("kind") == "formula" and isinstance(p.get("page"), int) and
               ("[FORMULA_UNRESOLVED]" in p["text"] or {"glyph_substitution"} & set(p.get("flags") or []) or
                re.search(r"=\s*[a-z]\s*=|= t =|\(\d+\)\s*$", p["text"]))}
    return sorted({p for p in pages if p in regions} | garbled)


PANEL_FIELDS = ("open", "high", "low", "close", "volume", "amount", "returns")


def field_map(symbols):
    """symbol -> panel field for a reading's symbol table; None when a symbol is not a plain market field."""
    out = {}
    for s in symbols or []:
        f = s.get("data_field")
        if s.get("symbol") and f in PANEL_FIELDS and s.get("kind") in (None, "raw_field", "period_return"):
            out[s["symbol"]] = f
    return out


def _panels(rows=320, cols=12, seed=11):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    idx, codes = pd.RangeIndex(rows), [f"S{i}" for i in range(cols)]
    close = pd.DataFrame(20 * np.exp(np.cumsum(rng.normal(0, 0.02, (rows, cols)), axis=0)), idx, codes)
    high = close * (1 + rng.uniform(0, 0.03, (rows, cols)))
    low = close * (1 - rng.uniform(0, 0.03, (rows, cols)))
    open_ = low + (high - low) * rng.uniform(0, 1, (rows, cols))
    volume = pd.DataFrame(rng.uniform(1e5, 1e6, (rows, cols)), idx, codes)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "amount": volume * close,
            "returns": close.pct_change()}


def numerical_matches(a, b):
    """Check levels AND observable signals, without a constant-offset tolerance.

    Keep the independent evaluators' relative rounding allowance. In addition,
    compare changes from the first finite observation along each panel axis,
    relative to that axis's variation, and require identical order/ties. A
    small signal on a large constant must not be erased, reversed or rescaled.
    Unresolved floating-point variation is not evidence of equivalence. This
    remains a bounded numerical check, not a symbolic proof of arbitrary code.
    """
    import numpy as np
    if a.shape!=b.shape or not np.array_equal(np.isfinite(a),np.isfinite(b)):
        return None
    both=np.isfinite(a)&np.isfinite(b)
    left,right=a[both],b[both]
    scale=np.maximum(np.abs(left),np.abs(right))
    # Independent rolling Pearson implementations differ by about 2e-10
    # relatively on the recorded baseline. 1e-9 allows that numerical error;
    # exact zero/nonzero and sign agreement are mandatory at every scale.
    matches=(np.abs(left-right)<=1e-9*scale)&((left==0)==(right==0))&((left>0)==(right>0))
    if not np.all(matches) or not left.size:
        return matches
    # Subnormals have already lost relative precision; equality after rounding
    # cannot certify the mathematical signal (nor can an overflowing change).
    tiny=np.finfo(float).tiny
    if np.any((scale!=0)&(scale<tiny)):
        return None
    for axis in range(a.ndim):
        first=np.expand_dims(np.argmax(both,axis=axis),axis)
        with np.errstate(over='ignore',invalid='ignore',under='ignore'):
            da=a-np.take_along_axis(a,first,axis=axis)
            db=b-np.take_along_axis(b,first,axis=axis)
            span=np.maximum(np.max(np.where(both,np.abs(da),0),axis=axis,keepdims=True),
                            np.max(np.where(both,np.abs(db),0),axis=axis,keepdims=True))
            resolution=np.max(np.where(both,np.maximum(np.abs(np.spacing(a)),np.abs(np.spacing(b))),0),
                              axis=axis,keepdims=True)
            # A varying slice spanning only a few representable values cannot
            # establish a reliable signal, even if both evaluators round alike.
            unresolved=(span>0)&(span<=8*resolution)
            signal_ok=np.isfinite(da)&np.isfinite(db)&(np.abs(da-db)<=1e-9*span)
        if np.any((both&~signal_ok)|(both&unresolved)):
            return np.zeros_like(matches)
        # Adjacent sorted pairs suffice to compare all orders and ties. Check
        # raw values, so centring/rescaling cannot hide a one-ULP rank change.
        order=np.argsort(np.where(both,a,np.inf),axis=axis,kind='stable')
        sa=np.take_along_axis(a,order,axis=axis)
        sb=np.take_along_axis(b,order,axis=axis)
        valid=np.isfinite(sa)
        lo=[slice(None)]*a.ndim;hi=lo.copy()
        lo[axis]=slice(None,-1);hi[axis]=slice(1,None)
        lo,hi=tuple(lo),tuple(hi)
        pairs=valid[lo]&valid[hi]
        if np.any(pairs&(((sa[lo]==sa[hi])!=(sb[lo]==sb[hi]))|
                         ((sa[lo]<sa[hi])!=(sb[lo]<sb[hi])))):
            return np.zeros_like(matches)
    return matches


def formulas_agree(ir_a, map_a, ir_b, map_b):
    """Do two readings compute the same numbers? Both are evaluated by the reference evaluator on one synthetic panel
    (symbols mapped to their market fields); cells where both are finite are compared. None when not comparable."""
    import numpy as np
    from paper_research.factor_ir import evaluate, fields_used, warmup
    if not (set(fields_used(ir_a)) <= set(map_a) and set(fields_used(ir_b)) <= set(map_b)):
        return None
    try:
        need = max(warmup(ir_a)["observations_required"], warmup(ir_b)["observations_required"])
    except Exception:  # noqa: BLE001
        need = 300
    panels = _panels(rows=int(need) + 200)            # enough rows after the longer warm-up
    try:
        a = evaluate(ir_a, panels, map_a).to_numpy(dtype=float)
        b = evaluate(ir_b, panels, map_b).to_numpy(dtype=float)
    except Exception:  # noqa: BLE001 -- an unevaluable reading is reported as not comparable
        return None
    both = np.isfinite(a) & np.isfinite(b)
    if both.sum() < 0.3 * a.size:
        return {"agree": False, "compared": int(both.sum()), "max_abs_diff": None, "note": "warm-up or NaN pattern differs"}
    diff = np.abs(a[both] - b[both])
    matches=numerical_matches(a,b)
    return {"agree": matches is not None and bool(np.all(matches)), "compared": int(both.sum()), "max_abs_diff": float(diff.max())}


def classify(conflict, item=None, evidence=None):
    """The program's view of where a conflict comes from (before any claim by the reader)."""
    code = conflict.get("code")
    src = CODE_SOURCE.get(code)
    if src:
        if code in ("SYMBOL_UNDEFINED",) and any(c.get("kind") == "formula" for c in conflict.get("candidates") or []):
            src = "extraction_error"
        return src
    if code in ("SYMBOL_DEFINITION_UNVERIFIED", "SYMBOL_NOT_IN_TABLE"):
        return "extraction_error" if any(c.get("kind") == "formula" for c in conflict.get("candidates") or []) else "ai_misreading"
    detail = str(conflict.get("detail") or "")
    if code == "FORMULA_RECONSTRUCTION_UNVERIFIED":
        # the page cannot be read; a second reading the program cannot compute means the notation, not the reader
        return "unsupported_notation" if "UNSUPPORTED_" in detail else "extraction_error"
    if code == "PRINTED_FORMULA_NOT_CHECKED":
        return "unsupported_notation" if re.search(r"function |data '|exactly comparable|conditional|constant", detail) else "extraction_error"
    if code == "DEFINITION_SCOPE_UNCERTAIN":
        return "extraction_error" if conflict.get("reason") in ("PRINTED_EXPRESSION_UNBALANCED", "QUOTE_POSITION_UNRESOLVED") \
            else "paper_ambiguity"
    if code == "MODEL_FORMULA_CONTRADICTS_PAPER" and item is not None and evidence is not None:
        pages = {(item.get("formula") or {}).get("v03_formula", {}).get("page")}
        if any(p["page"] in pages and ({"glyph_substitution"} & set(p.get("flags") or []) or "[FORMULA_UNRESOLVED]" in p["text"])
               for p in evidence.passages):
            return "extraction_error"
    return "ai_misreading"


def annotate(conflicts, item=None, evidence=None, claims=None):
    """Attach source / source_cn / source_basis; a reader's claim replaces the program's view only when accepted."""
    claims = claims or {}
    for c in conflicts:
        key = (c.get("code"), c.get("symbol"))
        claim = claims.get(key) or claims.get((c.get("code"), None))
        c["source_program"] = classify(c, item, evidence)
        if claim and claim.get("accepted"):
            c["source"], c["source_basis"] = claim["source"], "reader_claim_verified"
        else:
            c["source"], c["source_basis"] = c["source_program"], "program"
        c["source_cn"] = SOURCE_CN.get(c["source"], c["source"])
        if c.get("code") == "FORMULA_UNPARSEABLE":
            c["parse_status"] = "PROGRAM_PARSE_INCOMPLETE"
    return conflicts


# ---------------------------------------------------------------- the reader's investigation tools (existing evidence)

def _page_text(evidence, page, clip_unresolved=True, limit=2600):
    """The PDF's own text layer of one page, read independently of the block/formula reconstruction (PyMuPDF plain
    text), plus the raw text inside formula regions the parser could not rebuild."""
    path = getattr(evidence, "source_path", None)
    if not path:
        return None, []
    try:
        import fitz  # PyMuPDF, already used by the ingestion
        with fitz.open(path) as pdf:
            if not 1 <= page <= pdf.page_count:
                return None, []
            pg = pdf[page - 1]
            text = pg.get_text("text")
            regions = []
            if clip_unresolved:
                for r in (evidence.doc.get("extraction_report") or {}).get("formula_regions_unresolved") or []:
                    if r.get("page") == page and r.get("bbox"):
                        regions.append({"bbox": [round(x, 1) for x in r["bbox"]],
                                        "text": pg.get_text("text", clip=fitz.Rect(*r["bbox"])).strip()[:400]})
            return plain(text)[:limit], regions[:4]
    except Exception:  # noqa: BLE001 -- a missing or unreadable page layer is reported as unavailable
        return None, []


def save_page_image(ledger, evidence, page, zoom=1.6):
    """PNG of one page for a human reviewer (the model never sees it)."""
    path = getattr(evidence, "source_path", None)
    if not path or ledger is None:
        return None
    try:
        import hashlib
        import fitz
        with fitz.open(path) as pdf:
            if not 1 <= page <= pdf.page_count:
                return None
            png = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
        out = ledger.dir / "artifacts" / "pages" / f"p{page:03d}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        digest = hashlib.sha256(png).hexdigest()
        ledger.event("PAGE_IMAGE_SAVED", {"page": page, "name": f"pages/p{page:03d}.png", "sha256": digest})
        return {"page": page, "name": f"pages/p{page:03d}.png", "sha256": digest}
    except Exception:  # noqa: BLE001
        return None


def run_request(evidence, req, *, per_request_chars=3500):
    """One investigation request -> (text for the reader, record). Only the existing evidence is used."""
    tool = (req or {}).get("tool")
    rec = {"tool": tool, "passages": [], "pages": []}
    parts = []
    if tool == "search":
        q = str(req.get("query") or "")[:200]
        rec["query"] = q
        ps = [evidence.by_id[h] for h in (evidence.search(q, k=5) if q.strip() else []) if h in evidence.by_id]
        parts.append(f"search {q!r}: " + (evidence.render(ps) if ps else "no passage matched"))
        rec["passages"] = [p["id"] for p in ps]
    elif tool == "read":
        pid = str(req.get("passage") or "")
        n = int(pid[1:]) if re.fullmatch(r"P\d{4}", pid) else -1
        ps = [evidence.by_id[f"P{j:04d}"] for j in (n - 1, n, n + 1) if f"P{j:04d}" in evidence.by_id]
        parts.append(f"read {pid}: " + (evidence.render(ps) if ps else "no such passage"))
        rec["passages"] = [p["id"] for p in ps]
    elif tool == "page":
        try:
            page = int(req.get("page"))
        except (TypeError, ValueError):
            page = -1
        ps = [p for p in evidence.passages if p["page"] == page]
        rec["pages"] = [page] if ps else []
        rec["passages"] = [p["id"] for p in ps]
        parts.append(f"page {page} as reconstructed by the program:\n" + (evidence.render(ps) if ps else "no such page"))
        raw, regions = _page_text(evidence, page)
        rec["raw_text_layer"] = raw is not None
        if raw is not None:
            parts.append(f"page {page} raw PDF text layer (independent extraction, reading order may differ):\n{raw}")
        for r in regions:
            parts.append(f"raw text inside an unresolved formula region {r['bbox']}: {r['text'] or '(no text: drawn or image formula)'}")
        if raw is None:
            parts.append("(no independent text layer available for this page)")
    else:
        parts.append(f"unknown tool {tool!r}: use search, read or page")
    text = "\n".join(parts)
    return text[:per_request_chars], rec


def accept_claim(finding, evidence, item, consulted):
    """Is the reader's source claim checkable? extraction_error: a cited/consulted passage is a formula block, flagged
    as garbled or unresolved, or the page has unresolved formula regions; paper_ambiguity / free_parameter: backed by a
    verified quote; ai_misreading: always accepted (the reader corrects itself, the rules re-check the result);
    unsupported_notation / data_mismatch: accepted when the program reached the same view."""
    src = finding.get("source")
    if src not in SOURCES:
        return False, "未知的来源类别"
    cits = finding.get("citations") if isinstance(finding.get("citations"), list) else []
    good = [evidence.verify_quote(c.get("passage"), c.get("quote")) for c in cits if isinstance(c, dict)]
    good = [g for g in good if g]
    if src == "ai_misreading":
        return True, "AI 自我更正，结果由同一套规则复核"
    if src == "extraction_error":
        pids = {g["passage"] for g in good} | set(consulted.get("passages") or [])
        pages = {g["page"] for g in good} | set(consulted.get("pages") or [])
        bad = [p for p in evidence.passages if p["id"] in pids and (p.get("kind") == "formula" or
               {"glyph_substitution"} & set(p.get("flags") or []) or "[FORMULA_UNRESOLVED]" in p["text"])]
        unresolved = [r for r in (evidence.doc.get("extraction_report") or {}).get("formula_regions_unresolved") or [] if r.get("page") in pages]
        if bad or unresolved:
            return True, f"程序确认相关位置是公式块或提取异常（{', '.join(p['id'] for p in bad[:3]) or f'第{sorted(pages)[:3]}页有未解析公式区域'}）"
        return False, "引用的段落与页面没有提取异常的迹象"
    if src in ("paper_ambiguity", "free_parameter"):
        return (True, "有核验通过的原文引文") if good else (False, "没有核验通过的原文引文")
    return False, "程序没有得到相同结论"
