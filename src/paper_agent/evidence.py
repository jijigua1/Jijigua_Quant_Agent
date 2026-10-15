"""Bounded evidence index over an ingested paper (paper_research document + v0.3 spec).

Passages are verbatim slices of document blocks (paragraphs, captions, formula blocks, table headers/rows), each with
page, block id and character offsets. Retrieval is a small BM25 ranking; the model sees only the selected passages,
never the whole paper. Any quote the model returns is re-located here; a quote that is not a verbatim substring of the
cited passage (after whitespace normalisation) is rejected.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from paper_research import extract_research_spec, ingest_document, validate_research_spec
from paper_research.common import sentences

from .ledger import sha256_text

STOP = set("the a an of and or to in on for by with is are be as at that this from we our it its which their into than "
           "these those was were has have had not but also each over under per all any can may such".split())
FORMULA_HINT = re.compile(r"\\frac|\\max|\\sum|=|\[FORMULA_UNRESOLVED\]")


CJK = re.compile(r"[一-鿿]+")


def _tokens(text):
    """Latin words and numbers, plus Chinese character bigrams (Chinese has no spaces: without them a Chinese report
    yields no tokens and retrieval returns almost nothing)."""
    low = text.lower()
    out = [t for t in re.findall(r"[a-z][a-z0-9\-]*|\d+(?:\.\d+)?", low) if t not in STOP]
    for run in CJK.findall(low):
        out += [run[i:i + 2] for i in range(len(run) - 1)] if len(run) > 1 else [run]
    return out


def _norm(s):
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


class PaperEvidence:
    VERSION = "paper_evidence/1.1"          # 1.1: Chinese bigram tokens

    def __init__(self, doc, spec, passages):
        self.doc, self.spec, self.passages = doc, spec, passages
        self.source_path = None
        self.by_id = {p["id"]: p for p in passages}
        self._df = Counter(t for p in passages for t in set(p["tokens"]))
        self._avg = sum(len(p["tokens"]) for p in passages) / max(1, len(passages))

    # ---------------------------------------------------------------- build / cache
    @classmethod
    def build(cls, pdf_path, *, cache_dir=None, allowed_roots=None):
        pdf_path = Path(pdf_path)
        doc = ingest_document(pdf_path, allowed_roots=allowed_roots or [pdf_path.parent])
        cache = Path(cache_dir) / f"{doc['source']['sha256'][:16]}.json" if cache_dir else None
        if cache and cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("version") == cls.VERSION and data.get("doc_sha256") == doc["source"]["sha256"]:
                ev = cls(doc, data["spec"], data["passages"])
                ev.source_path = str(pdf_path)        # the reader's page tool re-reads the PDF's own text layer
                return ev
        spec = extract_research_spec(doc)
        val = validate_research_spec(spec, doc)
        if not val["valid"]:
            raise ValueError("SPEC_PROVENANCE_INVALID: " + "; ".join(val["errors"][:3]))
        passages = []
        for b in doc["blocks"]:
            if b["kind"] not in ("paragraph", "caption", "formula", "table") or "injection_suspect" in b["flags"] \
                    or "hidden_text" in b["flags"]:
                continue
            text = b["text"]
            if b["kind"] == "table":
                rows = b["data"].get("rows") or []
                text = (b["data"].get("caption") or "") + " | header: " + " | ".join(b["data"].get("header") or []) + \
                    " | rows: " + " || ".join(" | ".join(r) for r in rows[:30])
                passages.append(cls._passage(len(passages), b, text, 0, len(b["text"]), table=True))
                continue
            # split long paragraphs on sentence boundaries into <= ~900-character windows
            start, buf_s, buf_e = 0, None, None
            for s, e, _ in sentences(text) or [(0, len(text), text)]:
                if buf_s is None:
                    buf_s, buf_e = s, e
                elif e - buf_s > 900:
                    passages.append(cls._passage(len(passages), b, text[buf_s:buf_e], buf_s, buf_e))
                    buf_s, buf_e = s, e
                else:
                    buf_e = e
            if buf_s is not None:
                passages.append(cls._passage(len(passages), b, text[buf_s:buf_e], buf_s, buf_e))
        ev = cls(doc, spec, passages)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"version": cls.VERSION, "doc_sha256": doc["source"]["sha256"], "spec": spec,
                                         "passages": passages}, ensure_ascii=False), encoding="utf-8")
        ev.source_path = str(pdf_path)
        return ev

    @staticmethod
    def _passage(i, b, text, s, e, table=False):
        return {"id": f"P{i:04d}", "block_id": b["id"], "page": b["page"], "section": b["section"], "kind": "table" if table else b["kind"],
                "char_start": s, "char_end": e, "text": text, "tokens": _tokens(text),
                "has_formula": bool(FORMULA_HINT.search(text)) or b["kind"] == "formula",
                "flags": [f for f in b["flags"] if f in ("layout_math", "glyph_substitution", "text_layout", "suspect")]}

    # ---------------------------------------------------------------- retrieval
    def search(self, query, k=8):
        q = _tokens(query)
        n = len(self.passages)
        scores = []
        for p in self.passages:
            tf = Counter(p["tokens"])
            dl = len(p["tokens"]) or 1
            s = 0.0
            for t in q:
                if t in tf:
                    idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                    s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * dl / self._avg))
            if s > 0:
                scores.append((s + (0.5 if p["has_formula"] else 0), p["id"]))
        return [pid for _, pid in sorted(scores, reverse=True)[:k]]

    def context(self, queries, *, budget_chars=24000, must=()):
        """Union of top passages for several queries (plus `must` ids), in document order, within a character budget."""
        chosen = list(dict.fromkeys(list(must) + [pid for q in queries for pid in self.search(q, 6)]))
        # short passages (typical of Chinese reports and slide-like PDFs): add the neighbours of every hit, nearest first,
        # so the model reads definitions in their context instead of isolated fragments
        if sum(len(self.by_id[p]["text"]) for p in chosen) < budget_chars * 0.3:
            order = [p["id"] for p in self.passages]
            pos = {pid: i for i, pid in enumerate(order)}
            for d in (1, 2, 3):
                for pid in list(chosen):
                    for j in (pos[pid] - d, pos[pid] + d):
                        if 0 <= j < len(order) and order[j] not in chosen:
                            chosen.append(order[j])
                if sum(len(self.by_id[p]["text"]) for p in chosen) >= budget_chars * 0.6:
                    break
        out, used = [], 0
        for pid in sorted(chosen, key=lambda x: int(x[1:])):
            p = self.by_id[pid]
            if used + len(p["text"]) > budget_chars:
                continue
            out.append(p)
            used += len(p["text"])
        return out

    @staticmethod
    def render(passages):
        return "\n".join(f"[{p['id']}] (page {p['page']}, {p['section'] or '-'}, {p['kind']}"
                         f"{', ' + ','.join(p['flags']) if p['flags'] else ''}) {p['text']}" for p in passages)

    # ---------------------------------------------------------------- verification
    def verify_quote(self, pid, quote):
        """Location of a verbatim quote inside passage `pid` (whitespace/dash-normalised), or None."""
        p = self.by_id.get(pid)
        if not p or not quote or len(quote.strip()) < 8:
            return None
        nq, nt = _norm(quote), _norm(p["text"])
        k = nt.find(nq)
        if k < 0:
            return None
        return {"passage": pid, "block_id": p["block_id"], "page": p["page"], "section": p["section"], "quote": quote}

    def locate_anywhere(self, quote):
        for pid in self.by_id:
            loc = self.verify_quote(pid, quote)
            if loc:
                return loc
        return None

    def fingerprint(self):
        return sha256_text(self.doc["source"]["sha256"] + self.VERSION + str(len(self.passages)))

    def summary(self):
        md = self.doc["metadata"]
        q = self.spec["extraction_quality"]
        return {"title": (md.get("title") or {}).get("value"), "authors": (md.get("authors") or {}).get("value"),
                "pages": self.doc["extraction_report"].get("pages_total"), "sha256": self.doc["source"]["sha256"],
                "passages": len(self.passages), "formulas": len(self.spec["formulas"]),
                "formulas_unresolved": q.get("formulas_unresolved"), "tables": len(self.spec["tables"]),
                "factors_v03": [{"name": f["name"], "formula_ids": f["formula_ids"], "status": f["status"]} for f in self.spec["factors"]]}
