"""Formula detection, readable representation, variable definitions and suspicion checks.

A readable formula is never marked executable: `executable` is always False and every formula
needs human confirmation before an implementation uses it.
"""
from __future__ import annotations

import re

from .common import EQ_NUMBER, PUA, garble_score

MATH_FONTS = re.compile(r"CMMI|CMSY|CMEX|CMR\d|Math|Symbol|STIX|MSAM|MSBM|Euclid|MT Extra|Cambria Math", re.I)
MATH_CHARS = set("=∑Σ∏√∫≤≥≠≈±×÷∂∆∇αβγδεζηθλμνξπρστφχψωΓΔΘΛΞΠΦΨΩ^_∈∉⊂∀∃∞")
INDEX_SYMBOLS = {"i", "j", "k", "t", "n", "m", "d", "s", "T", "N", "K"}
FUNCTION_WORDS = {"log", "ln", "exp", "max", "min", "sum", "mean", "std", "var", "cov", "corr", "rank",
                  "sign", "abs", "sqrt", "frac", "left", "right", "cdot", "times", "mathrm", "text",
                  "operatorname", "bar", "hat", "tilde", "sigma", "mu", "beta", "alpha", "sum_", "prod",
                  "where", "and", "if", "for", "otherwise"}
GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "nu", "xi", "pi", "rho",
         "sigma", "tau", "phi", "chi", "psi", "omega"}


def math_ratio(text: str) -> float:
    t = text.replace(" ", "")
    return sum(c in MATH_CHARS for c in t) / max(1, len(t))


def is_formula_line(text: str, fonts=()) -> bool:
    """A short line that looks like a displayed equation (not a sentence that mentions '=')."""
    t = text.strip()
    if not t or len(t) > 220:
        return False
    words = re.findall(r"[A-Za-z]{4,}", t)
    has_eq = bool(re.search(r"(?<![<>!])=|≡|≈|:=", t))
    mathfont = any(MATH_FONTS.search(f or "") for f in fonts)
    if mathfont and ((has_eq and len(words) <= 2) or math_ratio(t) > 0.15 and len(words) <= 1):
        return True
    if has_eq and len(words) <= 4 and (math_ratio(t) > 0.04 or EQ_NUMBER.search(t)):
        return True
    return bool(EQ_NUMBER.search(t)) and has_eq and len(words) <= 6


def readable(text: str) -> str:
    return re.sub(r"\s+", " ", EQ_NUMBER.sub("", text)).strip()


def symbols(expr: str) -> list[str]:
    """Candidate variable symbols (base names), in order of appearance, without indices."""
    e = re.sub(r"\(cid:\d+\)", " ", expr)
    e = re.sub(r"\\(mathrm|text|operatorname)\{([^}]*)\}", r"\2", e)
    indexed = set(re.findall(r"\\?([A-Za-z][A-Za-z0-9]*)(?=[_^])", e))
    e = re.sub(r"[_^]\{[^}]*\}|[_^]\w", " ", e)              # drop sub/superscripts
    toks = re.findall(r"\\?[A-Za-z][A-Za-z0-9]*|[α-ωΑ-Ω]", e)
    out = []
    for tok in toks:
        name = tok.lstrip("\\")
        if name.lower() in FUNCTION_WORDS and name.lower() not in GREEK or name in INDEX_SYMBOLS:
            continue
        if len(name) >= 3 and name.islower() and name not in GREEK and name not in indexed:
            continue                                   # an ordinary word, not a symbol
        if name not in out:
            out.append(name)
    return out


def suspicion(text: str, latex: str | None = None) -> list[str]:
    issues = []
    s = latex or text
    for o, c in ("()", "[]", "{}"):
        if s.count(o) != s.count(c):
            issues.append(f"unbalanced {o}{c}")
    if garble_score(text) > 0 or PUA.search(text):
        issues.append("unmapped glyphs (math font not decoded)")
    if re.search(r"=\s*$|^\s*=", readable(text)):
        issues.append("equation side missing")
    if latex is None and re.search(r"\b[A-Za-z]\s+[a-z,]\s+[a-z]\b", text):
        issues.append("possible flattened subscripts")
    return issues


DEF_EN = re.compile(r"(?P<sym>\\?[A-Za-z][A-Za-z0-9]*(?:_\{[^}]*\}|_\w+)?|[α-ωΑ-Ω](?:_\{[^}]*\})?)\s+"
                    r"(?:is|denotes|represents|refers to|stands for|equals|is defined as|is the)\s+"
                    r"(?P<def>.+?)(?=\s*(?:[,;]|\.(?:\s|$)|$|\band\s+\\?[A-Za-z][A-Za-z0-9_{},+\-−]*\s+"
                    r"(?:is|denotes|represents|refers|stands)\b))")
DEF_ZH = re.compile(r"(?P<sym>[A-Za-zα-ω][A-Za-z0-9_{},]*)\s*(?:表示|代表|为|是|指)\s*(?P<def>[^，,；;。]+)")


def definitions(text: str) -> dict[str, str]:
    """'where X is ..., Y denotes ...' / '其中 X 表示 ...' -> {base symbol: definition}."""
    text = re.sub(r"\$+", "", text)                    # inline-math delimiters around symbols ("where $P_{i,t}$ is")
    m = re.search(r"\b(where|here|in which|with)\b|其中|式中", text)
    if not m:
        return {}
    tail = text[m.end():]
    out = {}
    for rx in (DEF_EN, DEF_ZH):
        for d in rx.finditer(tail):
            base = re.sub(r"[_^].*$", "", d.group("sym")).lstrip("\\")
            out.setdefault(base, d.group("def").strip())
    return out


def build_formula(fid: str, raw: str, *, latex: str | None, source_kind: str, confidence: str) -> dict:
    """Formula record without definitions; definitions are attached by the extractor."""
    eq = EQ_NUMBER.search(raw)
    issues = suspicion(raw, latex)
    status = "unresolved" if any("glyph" in i or "missing" in i for i in issues) else (
        "suspect" if issues or confidence != "high" else "extracted")
    lhs = readable(latex or raw).split("=")[0] if "=" in (latex or raw) else ""
    out_syms = symbols(lhs)
    return {"id": fid, "raw": raw, "latex": latex, "readable": readable(latex or raw),
            "output_symbol": out_syms[0] if len(out_syms) == 1 else None,
            "equation_number": eq.group(1) if eq else None, "source_kind": source_kind,
            "symbols": symbols(latex or raw), "issues": issues, "status": status,
            "executable": False, "requires_human_check": True}
