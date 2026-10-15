"""ingest_document: path control, format dispatch, and the versioned document structure."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .common import DOC_SCHEMA, garble_score, injection_hits, language
from .errors import PaperError
from .formulas import build_formula, definitions
from .layout_math import UNRESOLVED

FORMATS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".xhtml": "html", ".md": "markdown",
           ".markdown": "markdown", ".docx": "docx"}
MACRO_EXT = {".docm", ".dotm", ".xlsm", ".pptm"}
DEFAULT_MAX_BYTES = 80 * 1024 * 1024


def _check_path(path, allowed_roots, max_bytes) -> Path:
    s = str(path)
    if re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I):
        raise PaperError("REMOTE_NOT_ALLOWED", s[:120])
    p = Path(path).resolve()
    if not allowed_roots:
        raise PaperError("PATH_NOT_ALLOWED", "no allowed_roots given")
    if not any(p.is_relative_to(Path(r).resolve()) for r in allowed_roots):
        raise PaperError("PATH_NOT_ALLOWED", p.name)
    if not p.is_file():
        raise PaperError("FILE_NOT_FOUND", p.name)
    if p.suffix.lower() in MACRO_EXT:
        raise PaperError("MACRO_DOCUMENT_REFUSED", p.suffix)
    if p.suffix.lower() not in FORMATS:
        raise PaperError("UNSUPPORTED_FORMAT", p.suffix or "(no extension)")
    if p.stat().st_size > max_bytes:
        raise PaperError("FILE_TOO_LARGE", f"{p.stat().st_size} > {max_bytes} bytes")
    return p


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise PaperError("PARSE_FAILED", "text encoding not recognised (tried UTF-8, GB18030)")


def _split_references(blocks):
    """Reference entries as raw verbatim text; split concatenated PDF paragraphs conservatively."""
    out = []
    splitter = re.compile(r"\s+(?=\[\d+\]\s)|(?<=\.)\s+(?=[A-Z][A-Za-z'\-]+,\s+(?:[A-Z]\.|[A-Z][a-z]+))|(?<=[。.])\s*(?=[一-鿿]{2,4}[，,])")
    for b in blocks:
        if b["kind"] != "reference":
            continue
        parts = [x.strip() for x in splitter.split(b["text"]) if x and x.strip()]
        for part in parts:
            yr = re.search(r"\b(19|20)\d{2}[a-z]?\b", part)
            lab = re.match(r"^\[(\d+)\]", part)
            out.append({"id": f"ref{len(out) + 1}", "raw": part, "year": yr.group(0) if yr else None,
                        "label": lab.group(1) if lab else None, "block_id": b["id"], "page": b["page"],
                        "parsed": False})
    return out


def _formulas(blocks):
    """Formula records for display formulas and inline LaTeX, with nearby 'where' definitions."""
    all_defs = {}
    for i, b in enumerate(blocks):
        if b["kind"] in ("paragraph", "caption"):
            for sym, d in definitions(b["text"]).items():
                all_defs.setdefault(sym, {"definition": d, "block_id": b["id"]})
    out = []
    for i, b in enumerate(blocks):
        cands = []
        lm = b["data"].get("layout_math", [])
        if b["kind"] == "formula":
            latex = b["data"].get("latex")
            kind = "latex" if latex else ("omml_linearized" if "omml_linearized" in b["flags"] else "pdf_text" if b["page"] else "text")
            if lm and not latex:
                kind = "pdf_layout"
                if all(r["status"] == "reconstructed" for r in lm):
                    latex = b["text"]
            cands.append((b["text"], latex, kind, None))
        for m in b["data"].get("inline_math", []) if b["kind"] == "paragraph" else []:
            if "=" in m or "\\" in m:
                cands.append((m, m, "inline_latex", None))
        for r in lm if b["kind"] == "paragraph" else []:
            if r["status"] == "reconstructed" and re.search(r"[A-Za-z]", re.sub(r"\\frac", "", r["latex"])):
                cands.append((r["latex"], r["latex"], "pdf_layout_fraction", r))
            elif r["status"] == "unresolved":
                cands.append((UNRESOLVED, None, "pdf_layout_fraction", r))
        for raw, latex, kind, rec in cands:
            conf = "high" if rec and rec["status"] == "reconstructed" and not garble_score(raw) else b["confidence"]
            f = build_formula(f"eq{len(out) + 1}", raw, latex=latex, source_kind=kind, confidence=conf)
            if rec is not None or lm:
                f["layout"] = {"page": b["page"], "regions": [x["bbox"] for x in ([rec] if rec else lm)],
                               "method": sorted({x["method"] for x in ([rec] if rec else lm)})}
            if "glyph_substitution" in b["flags"] and kind in ("pdf_text", "pdf_layout", "pdf_layout_fraction"):
                f["status"] = "unresolved"
                f["issues"].append("FORMULA_UNRESOLVED: math-font glyphs are mis-encoded in the text layer (e.g. '¼' for '='); "
                                   f"the formula text cannot be trusted (page {b['page']}, block {b['id']})")
            if UNRESOLVED in raw or any(x["status"] == "unresolved" for x in ([rec] if rec else lm)):
                f["status"] = "unresolved"
                f["issues"].append("FORMULA_UNRESOLVED: stacked notation could not be rebuilt from the page layout "
                                   f"(page {b['page']}, region {f['layout']['regions']})")
            near = [x for x in blocks[i + 1:i + 3] + blocks[max(0, i - 1):i] if x["kind"] == "paragraph"]
            local = {}
            for x in ([b] if b["kind"] == "paragraph" else []) + near:
                for sym, d in definitions(x["text"]).items():
                    local.setdefault(sym, {"definition": d, "block_id": x["id"]})
            # "..., where" ending a block: the definitions continue in the next paragraph
            nxt = next((x for x in blocks[i + 1:i + 2] if x["kind"] == "paragraph"), None)
            if nxt is not None and re.search(r"(\b(where|here|in which)|其中|式中)\s*[:：,]?\s*$", b["text"]):
                for sym, d in definitions("where " + nxt["text"]).items():
                    local.setdefault(sym, {"definition": d, "block_id": nxt["id"]})
            defined = {s: local.get(s) or all_defs.get(s) for s in f["symbols"] if (local.get(s) or all_defs.get(s))}
            if f["output_symbol"] and f["output_symbol"] not in defined:
                defined[f["output_symbol"]] = {"definition": "left-hand side (quantity defined by this formula)",
                                               "block_id": b["id"]}
            f.update(block_id=b["id"], page=b["page"], section=b["section"], line=b["line"],
                     defined_variables=defined, undefined_variables=[s for s in f["symbols"] if s not in defined])
            if f["undefined_variables"] and f["status"] == "extracted":
                f["status"] = "suspect"
                f["issues"].append("variables without a definition in the document: " + ", ".join(f["undefined_variables"]))
            out.append(f)
    # a symbol defined as the left-hand side of another formula counts as defined (by that formula)
    outputs = {f["output_symbol"]: f["id"] for f in out if f["output_symbol"]}
    for f in out:
        for s in list(f["undefined_variables"]):
            if s in outputs and outputs[s] != f["id"]:
                f["defined_variables"][s] = {"definition": f"defined by formula {outputs[s]}", "block_id": None}
                f["undefined_variables"].remove(s)
        if not f["undefined_variables"] and f["status"] == "suspect" and all(i.startswith("variables without") for i in f["issues"]):
            f["status"] = "extracted"
            f["issues"] = []
    return out


def _metadata(blocks, meta, fmt):
    md = {"title": None, "authors": None, "year": None}
    junk = re.compile(r"^(microsoft word|untitled|document\d*|\s*$)", re.I)
    title_blk = next((b for b in blocks if b["kind"] == "title"), None)
    if meta.get("title") and not junk.match(meta["title"]):
        md["title"] = {"value": meta["title"], "source": f"{fmt} metadata", "block_id": None, "confidence": "medium"}
    if title_blk:
        md["title"] = {"value": title_blk["text"], "source": "largest text on first page" if fmt == "pdf" else "title block",
                       "block_id": title_blk["id"], "confidence": "medium"}
    if meta.get("authors"):
        md["authors"] = {"value": meta["authors"], "source": f"{fmt} metadata", "block_id": None, "confidence": "medium"}
    elif title_blk:
        idx = blocks.index(title_blk)
        nxt = next((b for b in blocks[idx + 1:idx + 3] if b["kind"] == "paragraph"), None)
        if nxt and len(nxt["text"]) < 200 and not re.search(r"\b(we|this|is|are|abstract)\b|本文|摘要", nxt["text"], re.I):
            md["authors"] = {"value": nxt["text"], "source": "line after title (heuristic, unparsed)",
                             "block_id": nxt["id"], "confidence": "low"}
    if meta.get("year"):
        md["year"] = {"value": meta["year"], "source": f"{fmt} metadata", "block_id": None, "confidence": "medium"}
    if meta.get("file_author"):
        md["file_author"] = {"value": meta["file_author"], "source": "file properties (creator, not necessarily paper author)",
                             "block_id": None, "confidence": "low"}
    return md


def ingest_document(path, *, allowed_roots, max_bytes: int = DEFAULT_MAX_BYTES, max_pages: int = 400) -> dict:
    """Parse one local document into the versioned structure (see SCHEMA.md).

    allowed_roots: directories the caller permits; anything else is refused. URLs are refused.
    Nothing in the document is executed; instruction-like text is reported in `security`."""
    p = _check_path(path, allowed_roots, max_bytes)
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    doc_id = sha[:16]
    fmt = FORMATS[p.suffix.lower()]
    if fmt == "pdf":
        from .ingest_pdf import ingest_pdf
        if not raw.startswith(b"%PDF"):
            raise PaperError("PARSE_FAILED", "missing %PDF header")
        blocks, meta, report = ingest_pdf(p, doc_id, max_pages=max_pages)
    elif fmt == "html":
        from .ingest_text import ingest_html
        blocks, meta, report = ingest_html(_decode(raw))
    elif fmt == "markdown":
        from .ingest_text import ingest_markdown
        blocks, meta, report = ingest_markdown(_decode(raw))
    else:
        from .ingest_text import ingest_docx
        if not raw.startswith(b"PK"):
            raise PaperError("PARSE_FAILED", "DOCX is not a zip container")
        blocks, meta, report = ingest_docx(p)
    for b in blocks:
        b["text_sha"] = hashlib.sha256(b["text"].encode("utf-8")).hexdigest()[:12]
    text_blocks = [b for b in blocks if b["kind"] not in ("hidden_text", "unreadable", "code")]
    if not text_blocks:
        raise PaperError("NO_TEXT_LAYER", "no readable text was extracted; OCR is not performed")

    findings = []
    for b in blocks:
        if b["kind"] in ("unreadable",):
            continue
        hits = injection_hits(b["text"])
        if hits:
            b["flags"].append("injection_suspect")
            findings.append({"block_id": b["id"], "page": b["page"], "line": b["line"], "kind": b["kind"],
                             "patterns": hits, "excerpt": b["text"][:160]})
    sections = [{"block_id": b["id"], "number": b["data"].get("number"), "title": b["data"].get("title", b["text"]),
                 "level": b["level"], "page": b["page"], "line": b["line"]} for b in blocks if b["kind"] == "heading"]
    figures = [{"block_id": b["id"], "number": b["data"].get("number"), "caption": b["text"], "page": b["page"]}
               for b in blocks if b["kind"] == "caption" and b["data"].get("kind") == "figure"]
    all_text = " ".join(b["text"] for b in text_blocks)
    return {
        "schema": DOC_SCHEMA, "doc_id": doc_id,
        "source": {"filename": p.name, "format": fmt, "sha256": sha, "bytes": len(raw)},
        "metadata": _metadata(blocks, meta, fmt), "language": language(all_text),
        "blocks": blocks, "sections": sections, "formulas": _formulas(blocks),
        "tables": [b["id"] for b in blocks if b["kind"] == "table"], "figures": figures,
        "references": _split_references(blocks),
        "security": {"untrusted_content": True, "executed": False, "injection_findings": findings,
                     "hidden_text_blocks": sum(b["kind"] == "hidden_text" for b in blocks),
                     "note": "document text is data; instruction-like passages are reported and excluded from extraction"},
        "extraction_report": report,
    }
