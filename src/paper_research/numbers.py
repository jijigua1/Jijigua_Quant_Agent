"""Signed numbers as typeset in papers: ASCII hyphen, Unicode minus (U+2212) and en-dash (U+2013) used as minus,
percentages, and t-statistics in parentheses. The verbatim token is always kept next to the parsed value."""
from __future__ import annotations

import re

MINUS = "-−–"                         # hyphen-minus, U+2212 minus, U+2013 en-dash (journals typeset minus as en-dash)
# a sign counts only when it is attached to the digits (or separated by one thin space) and not part of a range "6–12"
# an unmapped glyph (C0 control character) right before a number is usually a minus from an un-decoded math font:
# the number is kept with sign_unresolved=True and value None -- the sign is never guessed
NUMBER = re.compile(r"(?<![\w.])(?P<ctl>[\x01-\x08\x0e-\x1f](?=[(\d]))?(?P<sign0>[-−–](?=\())?(?P<paren>\()?(?P<sign>[-−–]\s?)?(?P<num>\d+(?:\.\d+)?)(?P<pct>\s?%)?(?(paren)\))")


def parse_number(token: str) -> dict | None:
    """'–0.15%' -> {'value': -0.15, 'unit': '%', 'negative': True, 'parenthesized': False, 'text': '–0.15%'}."""
    m = NUMBER.fullmatch(token.strip())
    if not m:
        return None
    v = float(m.group("num"))
    neg = bool(m.group("sign")) != bool(m.group("sign0"))      # "−(15.22)": sign printed outside the parentheses
    if m.group("ctl"):
        return {"value": None, "magnitude": v, "unit": "%" if m.group("pct") else None, "negative": None,
                "sign_unresolved": True, "parenthesized": bool(m.group("paren")), "text": token.strip()}
    return {"value": -v if neg else v, "unit": "%" if m.group("pct") else None, "negative": neg,
            "parenthesized": bool(m.group("paren")), "text": token.strip()}


def find_numbers(text: str, *, decimals_only: bool = False):
    """Yield (start, end, parsed) for every number in text. A minus sign directly preceded by a digit or letter is a
    range or hyphen ('1963–2001', 't–1'), not a sign: the number is then reported unsigned and flagged."""
    for m in NUMBER.finditer(text):
        tok = m.group(0)
        if decimals_only and "." not in m.group("num") and not m.group("pct"):
            continue
        s = m.start()
        sign = m.group("sign")
        if sign and s > 0 and re.match(r"[\w)]", text[s - 1]):
            s += len(sign) + (1 if m.group("paren") else 0)
            tok = text[s:m.end()]
            p = parse_number(tok.lstrip("("))
            if p:
                p["range_or_hyphen_before"] = True
                yield s, m.end(), p
            continue
        p = parse_number(tok)
        if p:
            yield m.start(), m.end(), p
