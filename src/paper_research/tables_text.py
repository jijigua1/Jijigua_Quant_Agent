"""Tables without ruled cells (typical journal layout) recovered from text-line geometry.

Used only when PyMuPDF's ruled-table detection finds no body under a table caption. Rows are lines sharing a
baseline band; columns are clusters of right edges of numeric cells (numbers are right-aligned in journal tables);
a row made only of parenthesized numbers is read as the statistics row (e.g. t-statistics) of the row above.
Every cell keeps its verbatim token and its page box; the reconstruction is marked "text_layout" and is a
candidate structure for review, not a verified reading of the table.
"""
from __future__ import annotations

import re

from .numbers import parse_number

NUMTOK = re.compile(r"^[\x01-\x08\x0e-\x1f]?[-−–]?\(?[-−–]?\s?\d+(?:\.\d+)?\s?%?\)?[a-z*†‡]{0,3}$")
# value-like cells that are not numbers: bounds ("<−100%") and not-available dashes
VALUELIKE = re.compile(r"^([<>≤≥]\s?[-−–]?\d+(?:\.\d+)?\s?%?|[–—-]|n/?a|NA)$", re.I)
PANEL = re.compile(r"^(Panel\s+[A-Z0-9]+|面板\s*[A-Z0-9一二三四])\b", re.I)


def _cells(line):
    """Split a line into cells: numeric tokens get their own (interpolated) horizontal extent."""
    out = []
    for s in line["spans"]:
        text = s["text"]
        if not text.strip():
            continue
        x0, x1 = s["bbox"][0], s["bbox"][2]
        toks = list(re.finditer(r"\S+", text))
        valued = [bool(NUMTOK.match(t.group(0)) or VALUELIKE.match(t.group(0))) for t in toks]
        if len(toks) > 1 and any(valued):
            # numbers / placeholders get their own cell; runs of words stay one label cell
            w = (x1 - x0) / max(1, len(text))
            run = None
            for t, v in zip(toks, valued):
                cell = {"text": t.group(0), "x0": x0 + t.start() * w, "x1": x0 + t.end() * w,
                        "y0": s["bbox"][1], "y1": s["bbox"][3]}
                if v:
                    if run:
                        out.append(run)
                        run = None
                    out.append(cell)
                elif run:
                    run.update(text=run["text"] + " " + cell["text"], x1=cell["x1"])
                else:
                    run = cell
            if run:
                out.append(run)
        else:
            out.append({"text": text.strip(), "x0": x0, "x1": x1, "y0": s["bbox"][1], "y1": s["bbox"][3]})
    merged = []                                        # adjacent spans of one token (font changes inside "−6.29%")
    for c in out:
        if merged and c["x0"] - merged[-1]["x1"] < 1.2 and not (NUMTOK.match(merged[-1]["text"]) and NUMTOK.match(c["text"])) \
                and not VALUELIKE.match(c["text"]) and not VALUELIKE.match(merged[-1]["text"]):
            m = merged[-1]
            m.update(text=m["text"] + c["text"], x1=c["x1"], y0=min(m["y0"], c["y0"]), y1=max(m["y1"], c["y1"]))
        else:
            merged.append(dict(c))
    return merged


def _numeric(text):
    t = re.sub(r"[a-z*†‡]{1,3}$", "", text.strip())
    return parse_number(t.replace(" ", "")) if NUMTOK.match(text.strip()) else None


def rotate(lines, direction):
    """Copies of lines written in `direction` (PyMuPDF line dir) in a frame where that text reads left to right,
    so landscape tables go through the same reconstruction. `to_page` maps a box back to page coordinates."""
    dx, dy = round(direction[0]), round(direction[1])
    if (dx, dy) == (0, -1):                            # text runs bottom -> top
        fwd = lambda b: [-b[3], b[0], -b[1], b[2]]
        back = lambda b: [b[1], -b[2], b[3], -b[0]]
    elif (dx, dy) == (0, 1):                           # text runs top -> bottom
        fwd = lambda b: [b[1], -b[2], b[3], -b[0]]
        back = lambda b: [-b[3], b[0], -b[1], b[2]]
    else:
        return None, None
    out = []
    for ln in lines:
        if tuple(round(v) for v in ln.get("dir", (1, 0))) != (dx, dy):
            continue
        spans = [dict(s, bbox=fwd(s["bbox"])) for s in ln["spans"]]
        out.append(dict(ln, bbox=fwd(ln["bbox"]), spans=spans, orig_id=id(ln)))
    return sorted(out, key=lambda l: (l["bbox"][1], l["bbox"][0])), back


def table_region(lines, cap_index, body_size, column_width):
    """Lines that belong to the table announced by lines[cap_index] (lines sorted by y)."""
    cap = lines[cap_index]
    size = max(s["size"] for s in cap["spans"]) if cap["spans"] else body_size
    i, last = cap_index + 1, cap["bbox"]
    context = [cap["text"]]
    # caption title / description: contiguous lines directly below the caption
    while i < len(lines) and lines[i]["bbox"][1] - last[3] < 0.6 * size and lines[i]["bbox"][1] >= last[1]:
        last = lines[i]["bbox"]
        context.append(lines[i]["text"])
        i += 1
    region, seen_numeric = [], False
    for ln in lines[i:]:
        size_ln = max((s["size"] for s in ln["spans"]), default=body_size)
        wide = (ln["bbox"][2] - ln["bbox"][0]) > 0.6 * column_width
        long_body = size_ln >= 0.97 * body_size and wide
        footnote = re.match(r"^\^\{\d+\}", ln["text"]) and wide
        gap = ln["bbox"][1] - region[-1]["bbox"][3] if region else 0
        if re.match(r"^(Table|TABLE|Figure|FIGURE|表|图)\s*[A-Z]?[\dIVX]+", ln["text"]):
            break
        if not seen_numeric and (wide or footnote):
            context.append(ln["text"])                 # remaining caption text / displayed equation above the body
            continue
        if seen_numeric and (long_body or footnote or gap > 2.5 * size_ln):
            break
        seen_numeric = seen_numeric or any(NUMTOK.match(t) for t in ln["text"].split())
        region.append(ln)
    return region, " ".join(context)


def reconstruct_table(region, context: str = "") -> dict | None:
    if not region:
        return None
    cells = [dict(c, line=ln) for ln in region for c in _cells(ln)]
    if not cells:
        return None
    # rows: cluster by vertical centre
    cells.sort(key=lambda c: ((c["y0"] + c["y1"]) / 2, c["x0"]))
    rows = []
    for c in cells:
        yc = (c["y0"] + c["y1"]) / 2
        h = c["y1"] - c["y0"]
        if rows and abs(yc - rows[-1]["yc"]) < 0.35 * h:
            rows[-1]["cells"].append(c)
        else:
            rows.append({"yc": yc, "cells": [c]})
    for r in rows:
        r["cells"].sort(key=lambda c: c["x0"])
        r["nums"] = [c for c in r["cells"] if _numeric(c["text"])]
        words = sum(len(c["text"]) for c in r["cells"] if not _numeric(c["text"]))
        if len(r["nums"]) == 1 and words > 40:
            r["nums"] = []                             # a sentence that mentions a number ("the extreme 1% tails")
    data_rows = [r for r in rows if r["nums"]]
    if len(data_rows) < 2:
        return None
    # columns: right edges of numeric (non-parenthesized) cells
    edges = sorted(c["x1"] for r in data_rows for c in r["nums"] if not _numeric(c["text"])["parenthesized"])
    cols = []
    for e in edges:
        if cols and e - cols[-1][-1] < 7:
            cols[-1].append(e)
        else:
            cols.append([e])
    cols = [sum(c) / len(c) for c in cols if len(c) >= 2] or [sum(c) / len(c) for c in cols]
    centers = []
    for k, e in enumerate(cols):
        xs = [(c["x0"] + c["x1"]) / 2 for r in data_rows for c in r["nums"] if abs(c["x1"] - e) < 7]
        centers.append(sum(xs) / len(xs) if xs else e)
    first_num_y = data_rows[0]["yc"]
    header_rows = [r for r in rows if r["yc"] < first_num_y and not PANEL.match(" ".join(c["text"] for c in r["cells"]))]
    header = [""] * len(cols)
    issues = ["structure inferred from text alignment (no ruled cells)"]
    for r in header_rows:
        for c in r["cells"]:
            xc = (c["x0"] + c["x1"]) / 2
            spanned = [j for j, cx in enumerate(centers) if c["x0"] - 3 <= cx <= c["x1"] + 3]
            if len(spanned) > 1:                       # a group header spanning several columns
                for j in spanned:
                    header[j] = (header[j] + " " + c["text"]).strip()
                continue
            k = min(range(len(cols)), key=lambda j: min(abs(cols[j] - c["x1"]), abs(cols[j] - xc)))
            if min(abs(cols[k] - c["x1"]), abs(cols[k] - xc)) < 40:
                header[k] = (header[k] + " " + c["text"]).strip()
    if not all(header):
        issues.append("some columns have no header")
    out_cells, body, panel, prev = [], [], None, None
    label_left = min((c["x0"] for r in data_rows for c in r["cells"] if not _numeric(c["text"]) and not VALUELIKE.match(c["text"])),
                     default=None)
    group = None
    for r in rows:
        text = " ".join(c["text"] for c in r["cells"])
        if r["yc"] < first_num_y and r in header_rows:
            continue
        if PANEL.match(text) and not r["nums"]:
            panel = text
            group = None
            continue
        if not r["nums"]:
            continue
        stats_only = all(_numeric(c["text"]) and _numeric(c["text"])["parenthesized"] for c in r["cells"])
        parts = [c for c in r["cells"] if not _numeric(c["text"]) and not VALUELIKE.match(c["text"])]
        # hierarchical row labels: a row without an entry in the leftmost label column inherits the last group
        if parts and label_left is not None and parts[0]["x0"] > label_left + 10 and group:
            label = group + " / " + " ".join(c["text"] for c in parts)
        else:
            if len(parts) >= 2:
                group = parts[0]["text"]
            label = " / ".join(c["text"] for c in parts) if len(parts) >= 2 else " ".join(c["text"] for c in parts)
        row_cells = [""] * len(cols)
        last_est = None
        for c in r["nums"]:
            p = _numeric(c["text"])
            k = min(range(len(cols)), key=lambda j: abs(cols[j] - c["x1"]))
            if p["parenthesized"] and not stats_only and last_est is not None and 0 <= c["x0"] - last_est[1]["x1"] < 30:
                k = last_est[0]                        # "0.46% (2.15)": statistic printed right after its estimate
            elif abs(cols[k] - c["x1"]) > 15:
                issues.append(f"cell {c['text']!r} not aligned with any column")
                continue
            if not p["parenthesized"]:
                last_est = (k, c)
            rec = {"panel": panel, "row": prev["label"] if stats_only and prev else label, "column": header[k] or f"col{k + 1}",
                   "column_index": k, "text": c["text"], "value": p["value"], "unit": p["unit"],
                   "kind": "statistic_in_parentheses" if p["parenthesized"] else "estimate",
                   "verification": "unverified_layout_parse", "sign_unresolved": bool(p.get("sign_unresolved")),
                   "bbox": [round(c["x0"], 1), round(c["y0"], 1), round(c["x1"], 1), round(c["y1"], 1)]}
            out_cells.append(rec)
            if p["parenthesized"] and not stats_only:
                continue
            row_cells[k] = c["text"]
        for c in r["cells"]:
            if VALUELIKE.match(c["text"]):
                k = min(range(len(cols)), key=lambda j: abs(cols[j] - c["x1"]))
                if abs(cols[k] - c["x1"]) <= 15 and not row_cells[k]:
                    out_cells.append({"panel": panel, "row": label, "column": header[k] or f"col{k + 1}", "column_index": k,
                                      "text": c["text"], "value": None, "unit": None,
                                      "kind": "bound" if c["text"][:1] in "<>≤≥" else "not_available",
                                      "verification": "unverified_layout_parse",
                                      "bbox": [round(c["x0"], 1), round(c["y0"], 1), round(c["x1"], 1), round(c["y1"], 1)]})
                    row_cells[k] = c["text"]
        if stats_only and prev:
            prev["stats"] = row_cells
        else:
            prev = {"label": label, "panel": panel, "cells": row_cells}
            body.append(prev)
    rows_out = [[(r["panel"] + ": " if r["panel"] else "") + r["label"]] + r["cells"] +
                ([f"stats: {' '.join(x for x in r['stats'] if x)}"] if r.get("stats") else []) for r in body]
    x0 = min(c["x0"] for c in cells)
    bbox = [x0, min(c["y0"] for c in cells), max(c["x1"] for c in cells), max(c["y1"] for c in cells)]
    from .layout_math import glyph_substitution
    if any(glyph_substitution(ln["spans"]) for ln in region):
        issues.append("math-font glyphs mis-encoded in the table text")
    reliability = "structured" if all(header) and not any("not aligned" in i or "mis-encoded" in i for i in issues) else "partial"
    return {"header": ["row"] + header, "rows": rows_out, "cells": out_cells, "n_cols": len(cols) + 1,
            "issues": sorted(set(issues)), "bbox": bbox, "reliability": reliability, "caption_context": context,
            "consumed": {ln.get("orig_id", id(ln)) for ln in region}}
