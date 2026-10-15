"""PDF ingestion with PyMuPDF: text layer only, no OCR, no JavaScript, no embedded files.

Pages without a usable text layer become 'unreadable' blocks; nothing is invented for them.
"""
from __future__ import annotations

import re
import statistics
from types import SimpleNamespace
from collections import Counter

import fitz  # PyMuPDF

from . import layout_math, tables_text
from .common import (caption_match, clean, garble_score, heading_match, make_block)
from .errors import PaperError
from .formulas import is_formula_line

WHITE = 0xFFFFFF
NOTE = re.compile(r"^(notes?|source|sources|资料来源|注|说明)\s*[:：.]", re.I)
UNITS = re.compile(r"(%|\bbps\b|basis points|in (thousands|millions|billions)|\bUSD\b|\bRMB\b|百万元|亿元|万元|元|个基点)", re.I)


def _lines(page):
    """Visible text lines with style info; hidden spans (white or < 2pt) returned separately.

    Sub/superscripts are written _{..}/^{..} and stacked fractions are rebuilt from the page layout
    (layout_math); fractions that cannot be rebuilt are marked [FORMULA_UNRESOLVED] with their region."""
    d = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    raw, hidden = [], []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            vis = [s for s in ln["spans"] if s["text"].strip() and s["size"] >= 2 and s["color"] != WHITE]
            hid = [s for s in ln["spans"] if s["text"].strip() and (s["size"] < 2 or s["color"] == WHITE)]
            if hid:
                hidden.append({"text": clean("".join(s["text"] for s in hid)), "bbox": ln["bbox"]})
            if vis:
                raw.append({"block": b["number"], "bbox": list(ln["bbox"]), "spans": vis,
                            "dir": tuple(round(v) for v in ln.get("dir", (1, 0)))})
    sizes = Counter()
    for r in raw:
        for s in r["spans"]:
            sizes[round(s["size"], 1)] += len(s["text"].strip())
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    rebuilt, maths = layout_math.reconstruct(raw, layout_math.fraction_rules(page), body)
    out = []
    for r in rebuilt:
        vis = r["spans"]
        out.append({"text": clean(r["text"]), "bbox": tuple(r["bbox"]), "size": max((s["size"] for s in vis), default=body),
                    "block": r["block"], "fonts": tuple(sorted({s["font"] for s in vis})), "spans": vis, "math": r["math"],
                    "also_blocks": r.get("also_blocks", []), "dir": r.get("dir", (1, 0)),
                    "glyph_substitution": r.get("glyph_substitution", False),
                    "bold": bool(vis) and all(s["flags"] & 16 or "Bold" in s["font"] for s in vis)})
    return out, hidden, maths


def _inside(bbox, rect, pad=1.0):
    x0, y0, x1, y1 = bbox
    return x0 >= rect[0] - pad and y0 >= rect[1] - pad and x1 <= rect[2] + pad and y1 <= rect[3] + pad


def ingest_pdf(path, doc_id: str, max_pages: int = 400) -> tuple[list, dict, dict]:
    try:
        pdf = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        raise PaperError("PARSE_FAILED", f"{type(e).__name__}: {e}") from e
    if pdf.needs_pass:
        raise PaperError("ENCRYPTED")
    if pdf.page_count == 0:
        raise PaperError("PARSE_FAILED", "PDF has no pages")
    meta = {k: v for k, v in (pdf.metadata or {}).items() if v}
    report = {"pages_total": pdf.page_count, "pages_parsed": 0, "pages_unreadable": [],
              "pages_low_confidence": [], "hidden_text_spans": 0, "tables_detected": 0,
              "headers_footers_removed": 0, "warnings": [], "parser": f"PyMuPDF {fitz.VersionBind}",
              "ocr_attempted": False, "tables_from_text_layout": 0, "layout_fractions_reconstructed": 0,
              "formula_regions_unresolved": []}
    if pdf.page_count > max_pages:
        report["warnings"].append(f"only the first {max_pages} of {pdf.page_count} pages parsed")

    pages = []
    for pno in range(min(pdf.page_count, max_pages)):
        page = pdf[pno]
        lines, hidden, maths = _lines(page)
        report["layout_fractions_reconstructed"] += sum(m["status"] == "reconstructed" for m in maths)
        report["formula_regions_unresolved"] += [{"page": pno + 1, "bbox": m["bbox"], "method": m["method"]}
                                                 for m in maths if m["status"] == "unresolved"]
        try:
            # extract now: PyMuPDF table objects are only valid while their page is loaded
            tables = []
            for t in page.find_tables().tables:
                try:
                    names = list(t.header.names)
                except Exception:  # noqa: BLE001
                    names = None
                tables.append(SimpleNamespace(bbox=tuple(t.bbox), rows=t.extract(), header_names=names))
        except Exception as e:  # noqa: BLE001
            tables = []
            report["warnings"].append(f"page {pno + 1}: table detection failed ({type(e).__name__})")
        pages.append({"no": pno + 1, "lines": lines, "hidden": hidden, "tables": tables,
                      "height": page.rect.height, "images": len(page.get_images(full=False))})

    # repeated header/footer lines (top/bottom 6% of the page on >= 3 pages, digits normalised)
    def key(ln):
        return re.sub(r"\d+", "#", ln["text"])
    marg = Counter()
    for p in pages:
        for ln in p["lines"]:
            if ln["bbox"][1] < 0.06 * p["height"] or ln["bbox"][3] > 0.94 * p["height"]:
                marg[key(ln)] += 1
    # a repeated running header/footer has words; a bare number pattern ("#.#") near an edge is usually a table cell
    # of a landscape table, not a footer (page numbers are matched explicitly)
    repeated = {k for k, n in marg.items() if (n >= 3 and len(re.findall(r"[^\W\d_]", k)) >= 3)
                or re.fullmatch(r"#|- # -|Page #|第 ?# ?页", k)}
    sizes = [ln["size"] for p in pages for ln in p["lines"] for _ in range(max(1, len(ln["text"]) // 20))]
    body = statistics.median(sizes) if sizes else 10.0

    blocks, n = [], 0
    section = None
    in_refs = False
    title_size = max((ln["size"] for ln in pages[0]["lines"]), default=0) if pages else 0

    def add(kind, text, page, bbox, **kw):
        nonlocal n
        n += 1
        b = make_block(f"p{page}-b{n}", kind, text, page=page, section=section, bbox=bbox, **kw)
        blocks.append(b)
        return b

    for p in pages:
        pno = p["no"]
        text_chars = sum(len(ln["text"]) for ln in p["lines"])
        if text_chars < 20:
            reason = "image-only page, no text layer (scanned?)" if p["images"] else "empty page"
            add("unreadable", "", pno, None, confidence="none", flags=["no_text_layer"], data={"reason": reason})
            report["pages_unreadable"].append(pno)
            continue
        report["pages_parsed"] += 1
        g = garble_score(" ".join(ln["text"] for ln in p["lines"]))
        if g > 0.05:
            report["pages_low_confidence"].append(pno)
        for h in p["hidden"]:
            report["hidden_text_spans"] += 1
            add("hidden_text", h["text"], pno, h["bbox"], confidence="none", flags=["hidden_text", "excluded"])
        table_rects = [t.bbox for t in p["tables"]]
        lines = [ln for ln in p["lines"] if key(ln) not in repeated or
                 not (ln["bbox"][1] < 0.06 * p["height"] or ln["bbox"][3] > 0.94 * p["height"])]
        report["headers_footers_removed"] += len(p["lines"]) - len(lines)

        def add_table(t):
            rows = [[clean(c) if c else "" for c in r] for r in t.rows]
            header = [clean(h) if h else "" for h in t.header_names] if t.header_names else (rows[0] if rows else [])
            body_rows = rows[1:] if rows and rows[0] == header else rows
            prev = blocks[-1] if blocks else None
            cap = ({"text": prev["text"]} if prev and prev["kind"] == "caption" and prev["page"] == pno
                   and prev["data"]["kind"] == "table" and t.bbox[1] - prev["bbox"][3] < 60 else None)
            notes = [ln["text"] for ln in lines if ln["bbox"][1] >= t.bbox[3] - 2 and ln["bbox"][1] - t.bbox[3] < 40
                     and NOTE.match(ln["text"])]
            cm = caption_match(cap["text"]) if cap else None
            flags, issues = [], []
            widths = {len(r) for r in rows}
            empty = sum(1 for r in rows for c in r if not c) / max(1, sum(len(r) for r in rows))
            if len(widths) > 1:
                issues.append("ragged rows")
            if not any(header):
                issues.append("empty header")
            if empty > 0.3:
                issues.append(f"{empty:.0%} empty cells")
            units = sorted({m.group(0) for s in [cap["text"] if cap else ""] + header + notes for m in UNITS.finditer(s)})
            add("table", " | ".join(header), pno, t.bbox, confidence="medium" if issues else "high",
                flags=["suspect"] if issues else [],
                data={"caption": cap["text"] if cap else None, "number": cm[1] if cm else None,
                      "continued_marker": bool(cm and cm[2]), "header": header, "rows": body_rows,
                      "n_cols": max(widths) if widths else 0, "notes": notes, "units": units, "issues": issues,
                      "continuation_of": None, "continued_in": []})
            report["tables_detected"] += 1

        # group remaining lines: headings, formulas, captions, paragraphs
        para, para_bbox, para_math, last_ln, para_glyph = [], None, [], None, False

        def flush():
            nonlocal para, para_bbox, para_math, para_glyph
            if para:
                text = ""
                for s in para:
                    text = text[:-1] + s if text.endswith("-") and s[:1].islower() else (text + " " + s if text else s)
                kind = "reference" if in_refs else "paragraph"
                g2 = garble_score(text)
                add(kind, text, pno, para_bbox, confidence="low" if g2 > 0.05 else "high",
                    flags=(["garbled"] if g2 > 0.05 else []) + (["layout_math"] if para_math else []) +
                    (["glyph_substitution"] if para_glyph else []),
                    data={"layout_math": para_math} if para_math else None)
            para, para_bbox, para_math, para_glyph = [], None, [], False

        # tables without ruled cells: rebuilt from line geometry under a table caption (never over a ruled table)
        text_tables = []
        frames = [(sorted([l for l in lines if l["dir"] == (1, 0)], key=lambda l: (l["bbox"][1], l["bbox"][0])), None)]
        for dr in sorted({l["dir"] for l in lines} - {(1, 0)}):
            rl, back = tables_text.rotate(lines, dr)
            if rl:
                frames.append((rl, back))              # landscape table: same reconstruction in a rotated frame
        for ordered, back in frames:
            col_w = max((l["bbox"][2] - l["bbox"][0] for l in ordered), default=0)
            for ci, cl in enumerate(ordered):
                cmt = caption_match(cl["text"])
                if not cmt or cmt[0] != "table" or (back is None and any(t.bbox[1] > cl["bbox"][1] for t in p["tables"])):
                    continue
                tt = tables_text.reconstruct_table(*tables_text.table_region(ordered, ci, body, col_w))
                if tt:
                    tt["caption_line"] = cl.get("orig_id", id(cl))
                    cap_page = next(l for l in lines if id(l) == tt["caption_line"])["bbox"]
                    # after its caption (and the caption's wrapped title) in the reading order
                    tt["sort_y"] = tt["bbox"][1] if back is None else cap_page[3] + 0.01
                    if back is not None:
                        tt["bbox"] = back(tt["bbox"])
                        for c in tt["cells"]:
                            c["bbox"] = [round(v, 1) for v in back(c["bbox"])]
                        tt["issues"] = sorted(set(tt["issues"]) | {"rotated (landscape) table"})
                    text_tables.append(tt)
        consumed = set().union(*[t["consumed"] for t in text_tables]) if text_tables else set()
        lines = [ln for ln in lines if id(ln) not in consumed]
        caption_of_line = {}

        last_block = None
        para_block = None
        events = [(ln["bbox"][1], ln["bbox"][0], "line", ln) for ln in lines
                  if not any(_inside(ln["bbox"], r) for r in table_rects)]
        events += [(t.bbox[1], t.bbox[0], "table", t) for t in p["tables"]]
        events += [(t["sort_y"], t["bbox"][0], "text_table", t) for t in text_tables]
        for _, _, ev_kind, ln in sorted(events, key=lambda e: (e[0], e[1])):
            if ev_kind == "table":
                flush()
                add_table(ln)
                last_block = None
                continue
            if ev_kind == "text_table":
                flush()
                cap_b = caption_of_line.get(ln["caption_line"])
                cm2 = caption_match(cap_b["text"]) if cap_b else None
                units = sorted({m.group(0) for m in UNITS.finditer(cap_b["text"] if cap_b else "")})
                add("table", " | ".join(ln["header"]), pno, ln["bbox"], confidence="medium", flags=["suspect", "text_layout"],
                    data={"caption": cap_b["text"] if cap_b else None, "number": cm2[1] if cm2 else None,
                          "continued_marker": bool(cm2 and cm2[2]), "header": ln["header"], "rows": ln["rows"],
                          "n_cols": ln["n_cols"], "notes": [], "units": units, "issues": ln["issues"],
                          "method": "text_layout", "cells": ln["cells"], "reliability": ln["reliability"], "caption_context": ln["caption_context"], "caption_block": cap_b["id"] if cap_b else None,
                          "continuation_of": None, "continued_in": []})
                report["tables_detected"] += 1
                report["tables_from_text_layout"] += 1
                last_block = None
                continue
            text = ln["text"]
            hm = heading_match(text)
            is_title = pno == 1 and ln["size"] >= title_size - 0.1 and title_size > body * 1.3
            if is_title:
                flush()
                if blocks and blocks[-1]["kind"] == "title" and blocks[-1]["page"] == 1:
                    blocks[-1]["text"] += " " + text
                else:
                    add("title", text, pno, ln["bbox"])
                continue
            if hm and (ln["size"] > body * 1.1 or ln["bold"]) or (hm and hm[0] is None and len(text) < 30):
                flush()
                num, ttl = hm
                section = f"{num} {ttl}" if num else ttl
                in_refs = bool(re.match(r"(references|bibliography|参考文献)", ttl.strip(), re.I))
                lvl = num.count(".") + 1 if num and num[0].isdigit() else 1
                add("heading", text, pno, ln["bbox"], level=lvl, data={"number": num, "title": ttl})
                continue
            cm = caption_match(text)
            if cm and not in_refs:
                flush()
                last_block = add("caption", text, pno, ln["bbox"], data={"kind": cm[0], "number": cm[1],
                                                                          "continued": cm[2]})
                caption_of_line[id(ln)] = last_block
                continue
            if is_formula_line(text, ln["fonts"]) and not in_refs:
                flush()
                prev = blocks[-1] if blocks else None
                if prev and prev["kind"] == "formula" and prev["page"] == pno and ln["bbox"][1] - prev["bbox"][3] < ln["size"] * 1.2:
                    prev["text"] += " " + text
                    prev["bbox"] = [min(prev["bbox"][0], ln["bbox"][0]), prev["bbox"][1],
                                    max(prev["bbox"][2], ln["bbox"][2]), ln["bbox"][3]]
                    if ln["math"]:
                        prev["data"].setdefault("layout_math", []).extend(ln["math"])
                    if ln["glyph_substitution"] and "glyph_substitution" not in prev["flags"]:
                        prev["flags"].append("glyph_substitution")
                else:
                    add("formula", text, pno, ln["bbox"], data={"fonts": list(ln["fonts"]),
                                                               **({"layout_math": ln["math"]} if ln["math"] else {})},
                        flags=["glyph_substitution"] if ln["glyph_substitution"] else [])
                continue
            if last_block is not None and last_block["kind"] == "caption" and not para and ln["bbox"][1] - last_block["bbox"][3] < ln["size"] * 0.6:
                last_block["text"] += " " + text           # caption wraps onto the next line
                continue
            last_block = None
            gap =ln["bbox"][1] - para_bbox[3] if para_bbox else 0
            same_row = (last_ln is not None and ln["bbox"][0] >= last_ln["bbox"][2] - 2 and
                        abs((ln["bbox"][1] + ln["bbox"][3]) / 2 - (last_ln["bbox"][1] + last_ln["bbox"][3]) / 2) < 0.5 * ln["size"])
            if same_row and para:
                pass                                      # same visual row (e.g. text after an inline formula)
            elif in_refs and para:
                # references: an indented line continues the entry (hanging indent), a flush-left line starts one
                col_left = min(l2["bbox"][0] for l2 in lines if abs(l2["bbox"][0] - ln["bbox"][0]) < 200)
                starts_entry = bool(re.match(r"(\[\d+\]|\d+\.\s|[A-Z][A-Za-z'\-]+,\s|[一-鿿]{2,4}[，,])", text))
                if ln["bbox"][0] <= col_left + 3 and (para[-1].rstrip().endswith(".") or starts_entry):
                    flush()
            elif para and (gap > ln["size"] * 0.9 or (ln["block"] != para_block and ln["block"] not in last_ln.get("also_blocks", []))):
                flush()
            para.append(text)
            para_math.extend(ln["math"])
            para_glyph = para_glyph or ln["glyph_substitution"]
            last_ln = ln
            para_block = ln["block"]
            para_bbox = list(ln["bbox"]) if para_bbox is None else [min(para_bbox[0], ln["bbox"][0]), para_bbox[1],
                                                                    max(para_bbox[2], ln["bbox"][2]), ln["bbox"][3]]
        flush()

    _link_tables(blocks)
    for b in blocks:            # captions announcing a table whose body was not detected
        if b["kind"] == "caption" and b["data"]["kind"] == "table":
            if not any(t["kind"] == "table" and t["data"]["caption"] == b["text"] for t in blocks):
                b["flags"].append("table_body_not_detected")
                b["confidence"] = "low"
    return blocks, meta, report


def _link_tables(blocks):
    """Conservative multi-page linking: next page's first table with the same column count and
    either a 'continued' marker, no caption, or an identical header. Tables are not merged."""
    tables = [b for b in blocks if b["kind"] == "table"]
    for a, b in zip(tables, tables[1:]):
        if b["page"] != a["page"] + 1 or a["data"]["n_cols"] != b["data"]["n_cols"]:
            continue
        first_on_page = next(t for t in tables if t["page"] == b["page"]) is b
        cont = b["data"]["continued_marker"] or b["data"]["caption"] is None or b["data"]["header"] == a["data"]["header"]
        if first_on_page and cont:
            root = a["data"]["continuation_of"] or a["id"]
            b["data"]["continuation_of"] = root
            next(t for t in tables if t["id"] == root)["data"]["continued_in"].append(b["id"])
            b["flags"].append("multi_page")
            a["flags"] = sorted(set(a["flags"] + ["multi_page"]))
