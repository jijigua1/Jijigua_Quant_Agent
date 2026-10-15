"""Inline mathematics recovered from PDF page layout (PyMuPDF spans and vector drawings).

The PDF text layer loses two-dimensional notation: a stacked fraction becomes two loose lines, subscripts become
plain letters ("Pi,t−1"). This module restores what the layout states unambiguously and flags what it cannot:

  * sub/superscripts: a span that is smaller than the line's body size and whose baseline is lower (higher) than the
    body baseline is written ``_{...}`` (``^{...}``);
  * stacked fractions: a short horizontal rule with text directly above and below inside its horizontal extent is
    rewritten ``\\frac{numerator}{denominator}`` at the position of the rule in the reading order;
  * stacked fragments that cannot be reconstructed (a rule with an empty side, or small stacked fragments inline in a
    sentence without any rule) become the token ``[FORMULA_UNRESOLVED]`` plus a record with the page region.

Nothing is guessed from the paper's topic; only geometry and font sizes are used.
"""
from __future__ import annotations

import re
from collections import Counter

UNRESOLVED = "[FORMULA_UNRESOLVED]"
MATH_FONT = re.compile(r"Mth|Math|MT(SY|MI|EX)|CMSY|CMMI|CMEX|MSAM|MSBM|Symbol|Euclid|Mathematical", re.I)
# characters a math/symbol font should not decode to: Latin-1 letters and vulgar fractions ("¼" for "=", "ð"/"Þ" for
# parentheses, "þ" for "+") and C0 control characters ("\x05" for minus) -- the font's encoding is not mapped
SUBSTITUTED = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f¼½¾ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]")


def glyph_substitution(spans) -> bool:
    """True when a span in a math/symbol font decodes to characters that font cannot mean (unmapped encoding)."""
    return any(SUBSTITUTED.search(s["text"]) and (MATH_FONT.search(s.get("font", "")) or re.search(r"[\x00-\x1f]", s["text"]))
               for s in spans)
RULE_MAX_HEIGHT = 1.2          # pt: a fraction rule is a thin horizontal line ...
RULE_MAX_WIDTH = 180.0         # ... narrower than a table rule spanning the text column


def _origin_y(span):
    o = span.get("origin")
    return o[1] if o else span["bbox"][3]


def _base(spans, mode="chars"):
    """(size, baseline) of the line body. mode 'chars': the size carrying most characters (robust to drop caps in
    running text); mode 'max': the largest size (short math fragments, where scripts can outnumber the base)."""
    if mode == "max" or sum(len(s["text"].strip()) for s in spans) <= 12:
        size = max(round(s["size"], 1) for s in spans)
    else:
        sizes = Counter()
        for s in spans:
            sizes[round(s["size"], 1)] += len(s["text"].strip())
        size = sizes.most_common(1)[0][0] if sizes else 0
    first = next((s for s in spans if round(s["size"], 1) == size), spans[0])
    return size, _origin_y(first)


def script_text(spans, *, threshold=0.9, mode="chars") -> str:
    """Join spans, writing smaller raised/lowered spans as ^{..}/_{..}."""
    if not spans:
        return ""
    size, base_y = _base(spans, mode)
    out, role, buf = [], None, []
    # a script is judged against the nearest preceding body-size span (lines can mix baselines, e.g. display math)
    local = []
    cur = next((_origin_y(s) for s in spans if s["size"] >= threshold * size and s["text"].strip()), base_y)
    for s in spans:
        if s["size"] >= threshold * size and s["text"].strip():
            cur = _origin_y(s)
        local.append(cur)

    def close():
        if buf:
            inner = "".join(buf).strip()
            if role in ("_", "^") and inner:
                out.append(f"{role}{{{inner.replace(' ', '')}}}")
            else:
                out.append("".join(buf))

    for s, ly in zip(spans, local):
        r = None
        if s["size"] < threshold * size:
            dy = _origin_y(s) - ly
            r = "_" if dy > 0.12 * size else "^" if dy < -0.12 * size else None
        if r != role:
            close()
            role, buf = r, []
        buf.append(s["text"])
    close()
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


def _latex_side(spans) -> str:
    t = script_text(spans, threshold=0.95, mode="max")
    return t.replace("−", "-").replace("–", "-").strip()


def fraction_rules(page) -> list[tuple]:
    rules = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return rules
    for d in drawings:
        r = d.get("rect")
        if r is None:
            continue
        if r.height <= RULE_MAX_HEIGHT and 4.0 <= r.width <= RULE_MAX_WIDTH:
            rules.append((r.x0, (r.y0 + r.y1) / 2, r.x1))
    return rules


def _nonspace(spans):
    return sum(len(s["text"].replace(" ", "")) for s in spans)


def reconstruct(raw_lines: list[dict], rules: list[tuple], body_size: float) -> tuple[list[dict], list[dict]]:
    """raw_lines: [{"block", "bbox", "spans"}]. Returns (lines, math_records); lines carry 'text' and 'math'."""
    lines = [dict(ln, spans=list(ln["spans"]), extra=[], math=[]) for ln in raw_lines]
    records = []
    for x0, ry, x1 in rules:
        num, den, used = [], [], []
        for li, ln in enumerate(lines):
            inside = [s for s in ln["spans"] if s["bbox"][0] >= x0 - 2.5 and s["bbox"][2] <= x1 + 2.5 and s["text"].strip()]
            if not inside:
                continue
            # a line mostly inside the rule's extent, or script-size spans inside a body-text line (the text layer
            # sometimes files a denominator into the following text line)
            line_size, _ = _base(ln["spans"])
            if _nonspace(inside) < 0.4 * max(1, _nonspace(ln["spans"])) and max(s["size"] for s in inside) >= 0.9 * line_size:
                continue
            size, base_y = _base(inside, "max")
            if base_y < ry and ry - base_y <= 1.3 * size:
                num += inside
                used.append((li, inside))
            elif base_y > ry and base_y - ry <= 1.9 * size:
                den += inside
                used.append((li, inside))
        if not num and not den:
            continue                                    # a rule with nothing stacked on it (underline, table rule)
        first_den = sorted(den, key=lambda s: s["bbox"][0])[0] if den else None
        if first_den is not None and re.fullmatch(r"\d{1,3}", first_den["text"].strip()):
            host_line = next(lines[li] for li, ins in used if any(s is first_den for s in ins))
            if not num or host_line["bbox"][2] > x1 + 20:
                continue                                # footnote separator: a short rule above a footnote marker + text
        status = "reconstructed" if num and den else "unresolved"
        n_txt, d_txt = _latex_side(sorted(num, key=lambda s: s["bbox"][0])), _latex_side(sorted(den, key=lambda s: s["bbox"][0]))
        latex = f"\\frac{{{n_txt}}}{{{d_txt}}}" if status == "reconstructed" else UNRESOLVED
        boxes = [s["bbox"] for s in num + den] + [(x0, ry, x1, ry)]
        bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        rec = {"latex": latex if status == "reconstructed" else None, "status": status, "method": "fraction_rule",
               "numerator_text": n_txt, "denominator_text": d_txt, "bbox": [round(v, 1) for v in bbox]}
        records.append(rec)
        for li, inside in used:
            ids = {id(s) for s in inside}
            lines[li]["spans"] = [s for s in lines[li]["spans"] if id(s) not in ids]
        _attach(lines, rec, latex, x0, ry, x1, [li for li, _ in used])
    records += _stacked_fragments(lines, body_size)
    out = []
    for ln in lines:
        if not ln["spans"] and not ln["extra"]:
            continue
        text = script_text(ln["spans"])
        if ln["extra"]:
            pieces = [(ln["bbox"][0], text)] if ln["spans"] else []
            pieces += ln["extra"]
            text = " ".join(t for _, t in sorted(pieces, key=lambda p: p[0]) if t)
        out.append(dict(ln, text=text, glyph_substitution=glyph_substitution(ln["spans"])))
    return out, records


def _row_contains(bbox, y):
    return bbox[1] - 0.5 <= y <= bbox[3] + 0.5


def _attach(lines, rec, latex, x0, ry, x1, used_idx):
    """Place the fraction in the reading order: appended to the text line on the same row to its left (the host);
    leftovers of the fraction's own lines on that row (', where', an equation number) follow it."""
    hosts = [i for i, ln in enumerate(lines) if ln["spans"] and _row_contains(ln["bbox"], ry)
             and max(s["bbox"][2] for s in ln["spans"]) <= x0 + 3]
    right = [(i, [s for s in ln["spans"] if s["bbox"][0] >= x1 - 3 and _row_contains(s["bbox"], ry)])
             for i, ln in enumerate(lines) if i in used_idx or _row_contains(ln["bbox"], ry)]
    right = [(i, ss) for i, ss in right if ss and i not in hosts]
    if hosts:
        h = max(hosts, key=lambda i: max(s["bbox"][2] for s in lines[i]["spans"]))
    else:                                               # display fraction: the first line of the fraction holds it
        h = used_idx[0] if used_idx else None
        if h is None:
            return
    host = lines[h]
    host["extra"].append((x0, latex))
    host["math"].append(rec)
    for i, ss in right:
        ids = {id(s) for s in ss}
        lines[i]["spans"] = [s for s in lines[i]["spans"] if id(s) not in ids]
        host["extra"].append((min(s["bbox"][0] for s in ss), script_text(ss)))
        host.setdefault("also_blocks", []).append(lines[i]["block"])   # the sentence continues in that block
    host["bbox"] = [min(host["bbox"][0], x0), min(host["bbox"][1], rec["bbox"][1]),
                    max(host["bbox"][2], rec["bbox"][2]), max(host["bbox"][3], rec["bbox"][3])]


def _stacked_fragments(lines, body_size):
    """Small short fragments stacked inline in a sentence without a fraction rule: cannot be reconstructed safely."""
    recs = []
    small = [i for i, ln in enumerate(lines) if ln["spans"] and not ln["math"]
             and max(s["size"] for s in ln["spans"]) < 0.85 * body_size and _nonspace(ln["spans"]) <= 25]
    taken = set()
    for a in small:
        for b in small:
            if a >= b or a in taken or b in taken:
                continue
            A, B = lines[a]["bbox"], lines[b]["bbox"]
            overlap = min(A[2], B[2]) - max(A[0], B[0])
            gap = B[1] - A[3] if B[1] >= A[1] else A[1] - B[3]
            size = max(s["size"] for s in lines[a]["spans"])
            if overlap < 0.5 * min(A[2] - A[0], B[2] - B[0]) or gap > 0.6 * size:
                continue
            top, bot = (a, b) if A[1] <= B[1] else (b, a)
            yc = (lines[top]["bbox"][3] + lines[bot]["bbox"][1]) / 2
            hosts = [i for i, ln in enumerate(lines) if i not in (a, b) and ln["spans"] and _row_contains(ln["bbox"], yc)
                     and max(s["size"] for s in ln["spans"]) >= 0.95 * body_size and ln["bbox"][2] <= min(A[0], B[0]) + 3]
            if not hosts:
                continue                                # stacked small text not inside a sentence (table cells etc.)
            bbox = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])]
            rec = {"latex": None, "status": "unresolved", "method": "stacked_fragments_without_rule",
                   "numerator_text": script_text(lines[top]["spans"]), "denominator_text": script_text(lines[bot]["spans"]),
                   "bbox": [round(v, 1) for v in bbox]}
            recs.append(rec)
            h = max(hosts, key=lambda i: lines[i]["bbox"][2])
            lines[h]["extra"].append((bbox[0], UNRESOLVED))
            lines[h]["math"].append(rec)
            lines[a]["spans"], lines[b]["spans"] = [], []
            taken |= {a, b}
    return recs
