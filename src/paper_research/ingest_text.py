"""HTML, Markdown and DOCX ingestion. Scripts, macros and embedded objects are never executed."""
from __future__ import annotations

import re

from .common import caption_match, clean, heading_match, make_block
from .errors import PaperError

REF_HEAD = re.compile(r"^(references|bibliography|works cited|参考文献)\b", re.I)
NOTE = re.compile(r"^(notes?|source|sources|资料来源|注|说明)\s*[:：.]", re.I)


class _Builder:
    def __init__(self, prefix):
        self.blocks, self.n, self.section, self.in_refs, self.prefix = [], 0, None, False, prefix

    def add(self, kind, text, *, line=None, **kw):
        self.n += 1
        b = make_block(f"{self.prefix}-b{self.n}", kind, text, section=self.section, line=line, **kw)
        self.blocks.append(b)
        return b

    def heading(self, text, level, line=None):
        hm = heading_match(text)
        num = hm[0] if hm else None
        title = hm[1] if hm else text
        self.section = f"{num} {title}" if num else title
        self.in_refs = bool(REF_HEAD.match(title.strip()))
        return self.add("heading", text, line=line, level=level, data={"number": num, "title": title})

    def text(self, text, line=None, **kw):
        cm = caption_match(text)
        if cm and not self.in_refs:
            data = {**kw.pop("data", {}), "kind": cm[0], "number": cm[1], "continued": cm[2]}
            return self.add("caption", text, line=line, data=data, **kw)
        return self.add("reference" if self.in_refs else "paragraph", text, line=line, **kw)

    def table(self, rows, line=None, caption=None, notes=()):
        rows = [[clean(c) for c in r] for r in rows if any(c.strip() for c in r)]
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        widths = {len(r) for r in rows}
        issues = (["ragged rows"] if len(widths) > 1 else []) + ([] if any(header) else ["empty header"])
        cm = caption_match(caption) if caption else None
        return self.add("table", " | ".join(header), line=line, confidence="medium" if issues else "high",
                        flags=["suspect"] if issues else [],
                        data={"caption": caption, "number": cm[1] if cm else None, "continued_marker": bool(cm and cm[2]),
                              "header": header, "rows": body, "n_cols": max(widths) if widths else 0,
                              "notes": list(notes), "units": [], "issues": issues,
                              "continuation_of": None, "continued_in": []})


# ------------------------------ Markdown ------------------------------

def ingest_markdown(text: str) -> tuple[list, dict, dict]:
    b = _Builder("md")
    lines = text.splitlines()
    report = {"code_blocks_not_executed": 0, "images_not_loaded": 0, "warnings": [], "parser": "built-in markdown reader"}
    i, para, para_line = 0, [], None

    def flush():
        nonlocal para, para_line
        if para:
            t = clean(" ".join(para))
            inline = re.findall(r"(?<!\$)\$([^$\n]+)\$(?!\$)", t)
            blk = b.text(t, line=para_line)
            if inline:
                blk["data"]["inline_math"] = inline
            para, para_line = [], None

    while i < len(lines):
        ln, no = lines[i], i + 1
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            flush()
            fence, lang = s[:3], s[3:].strip().lower()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                j += 1
            body = "\n".join(lines[i + 1:j])
            if lang in ("math", "latex", "tex"):
                b.add("formula", body.strip(), line=no, data={"latex": body.strip(), "display": True})
            else:
                b.add("code", body, line=no, flags=["not_executed"], data={"language": lang or None})
                report["code_blocks_not_executed"] += 1
            i = j + 1
            continue
        if s.startswith("$$") or s.startswith("\\["):
            flush()
            close = "$$" if s.startswith("$$") else "\\]"
            buf, j = [s[2:]], i
            while not buf[-1].rstrip().endswith(close) or (j == i and len(s) <= 2):
                j += 1
                if j >= len(lines):
                    break
                buf.append(lines[j].strip())
            latex = " ".join(buf).strip()
            latex = latex[:-2].strip() if latex.endswith(close) else latex
            blk = b.add("formula", latex, line=no, data={"latex": latex, "display": True})
            if j >= len(lines):
                blk["flags"].append("unterminated_math")
                blk["confidence"] = "low"
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            b.heading(clean(m.group(2)), len(m.group(1)), line=no)
            i += 1
            continue
        if s.startswith("|"):
            flush()
            j, rows = i, []
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                j += 1
            cap = None
            if b.blocks and b.blocks[-1]["kind"] == "caption" and b.blocks[-1]["data"]["kind"] == "table":
                cap = b.blocks.pop()["text"]
            notes = []
            k = j
            if k + 1 < len(lines) and not lines[k].strip() and NOTE.match(lines[k + 1].strip()):
                k += 1                                     # one blank line between table and its note
            while k < len(lines) and lines[k].strip() and NOTE.match(lines[k].strip()):
                notes.append(lines[k].strip())
                k += 1
            b.table(rows, line=no, caption=cap, notes=notes)
            i = k
            continue
        img = re.match(r"^!\[([^\]]*)\]\(([^)]*)\)", s)
        if img:
            flush()
            report["images_not_loaded"] += 1
            alt = img.group(1).strip()
            if alt:
                blk = b.text(alt, line=no)
                blk["flags"].append("image_not_loaded")
            i += 1
            continue
        if not s:
            flush()
        elif re.match(r"^([-*+]|\d+\.)\s+", s) and b.in_refs:
            flush()
            b.add("reference", clean(re.sub(r"^([-*+]|\d+\.)\s+", "", s)), line=no)
        else:
            if para_line is None:
                para_line = no
            para.append(s)
        i += 1
    flush()
    meta = {}
    first_h1 = next((x for x in b.blocks if x["kind"] == "heading" and x["level"] == 1), None)
    if first_h1:
        meta["title"] = first_h1["text"]
    return b.blocks, meta, report


# ------------------------------ HTML ------------------------------

HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0(\.0+)?\b", re.I)


def ingest_html(text: str) -> tuple[list, dict, dict]:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag

    soup = BeautifulSoup(text, "html.parser")
    report = {"scripts_removed": 0, "comments_removed": 0, "embedded_objects_removed": 0, "warnings": [],
              "parser": "BeautifulSoup html.parser"}
    b = _Builder("html")
    # TeX inside MathJax script tags is content, not code: keep it as formulas before dropping scripts
    for s in soup.find_all("script"):
        typ = (s.get("type") or "").lower()
        if typ.startswith("math/tex"):
            s.replace_with(soup.new_string(f"\\[{s.get_text()}\\]" if "display" in typ else f"${s.get_text()}$"))
        else:
            s.decompose()
            report["scripts_removed"] += 1
    for t in soup.find_all(["style", "iframe", "object", "embed", "noscript", "form", "link", "meta"]):
        report["embedded_objects_removed"] += t.name in ("iframe", "object", "embed", "form")
        t.decompose()
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
        report["comments_removed"] += 1

    def math_text(tag):
        ann = tag.find("annotation", attrs={"encoding": re.compile("tex", re.I)})
        return ann.get_text().strip() if ann else clean(tag.get_text(" "))

    def hidden(tag):
        return (tag.has_attr("hidden") or tag.get("aria-hidden") == "true"
                or bool(HIDDEN_STYLE.search(tag.get("style", ""))))

    def path(tag):
        parts = []
        while tag is not None and tag.name not in ("[document]", None):
            idx = len([s for s in tag.find_previous_siblings(tag.name)]) + 1
            parts.append(f"{tag.name}[{idx}]")
            tag = tag.parent
        return ">".join(reversed(parts))

    def inline_text(tag):
        for m in tag.find_all("math"):
            m.replace_with(soup.new_string(f" ${math_text(m)}$ "))
        return clean(tag.get_text(" "))

    def walk(node):
        for ch in list(node.children):
            if isinstance(ch, NavigableString):
                t = clean(str(ch))
                if t and node.name in ("body", "div", "section", "article", "main"):
                    dm = re.fullmatch(r"\\\[(.+)\\\]|\$\$(.+)\$\$", t, re.S)
                    if dm:                                   # MathJax display TeX kept from <script type=math/tex>
                        latex = (dm.group(1) or dm.group(2)).strip()
                        b.add("formula", latex, line=getattr(node, "sourceline", None),
                              data={"latex": latex, "display": True, "path": path(node)})
                    else:
                        b.text(t, line=getattr(node, "sourceline", None), data={"path": path(node)})
                continue
            if not isinstance(ch, Tag):
                continue
            line, where = ch.sourceline, path(ch)
            if hidden(ch):
                b.add("hidden_text", clean(ch.get_text(" ")), line=line, confidence="none",
                      flags=["hidden_text", "excluded"], data={"path": where})
                continue
            name = ch.name
            if re.fullmatch(r"h[1-6]", name):
                b.heading(clean(ch.get_text(" ")), int(name[1]), line=line)["data"]["path"] = where
            elif name == "math":
                b.add("formula", math_text(ch), line=line, data={"latex": math_text(ch) if ch.find("annotation") else None,
                                                                 "display": ch.get("display") == "block", "path": where})
            elif name in ("p", "li", "blockquote", "dd", "dt", "figcaption", "caption"):
                t = inline_text(ch)
                if not t:
                    continue
                dm = re.fullmatch(r"\\\[(.+)\\\]|\$\$(.+)\$\$", t, re.S)
                if dm:
                    latex = (dm.group(1) or dm.group(2)).strip()
                    b.add("formula", latex, line=line, data={"latex": latex, "display": True, "path": where})
                    continue
                blk = b.text(t, line=line, data={"path": where})
                inline = re.findall(r"(?<!\$)\$([^$]+)\$(?!\$)", t)
                if inline:
                    blk["data"]["inline_math"] = inline
                if name == "figcaption" and blk["kind"] != "caption":
                    blk["kind"], blk["data"] = "caption", {**blk["data"], "kind": "figure", "number": None, "continued": False}
            elif name == "table":
                cap = ch.find("caption")
                rows = [[clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])] for tr in ch.find_all("tr")]
                notes = [clean(f.get_text(" ")) for f in ch.find_all("tfoot")]
                b.table(rows, line=line, caption=clean(cap.get_text(" ")) if cap else None, notes=notes)["data"]["path"] = where
            elif name in ("pre", "code"):
                b.add("code", ch.get_text(), line=line, flags=["not_executed"], data={"path": where})
            elif name in ("img",):
                if ch.get("alt"):
                    b.text(clean(ch["alt"]), line=line, flags=["image_not_loaded"], data={"path": where})
            else:
                walk(ch)

    root = soup.body or soup
    walk(root)
    meta = {}
    if soup.title and soup.title.get_text(strip=True):
        meta["title"] = clean(soup.title.get_text())
    for m in BeautifulSoup(text, "html.parser").find_all("meta"):
        nm = (m.get("name") or "").lower()
        if nm in ("citation_title", "dc.title") and m.get("content"):
            meta["title"] = clean(m["content"])
        if nm in ("citation_author", "dc.creator") and m.get("content"):
            meta.setdefault("authors", []).append(clean(m["content"]))
        if nm in ("citation_publication_date", "citation_date", "dc.date") and m.get("content"):
            yr = re.search(r"(19|20)\d{2}", m["content"])
            if yr:
                meta["year"] = int(yr.group(0))
    return b.blocks, meta, report


# ------------------------------ DOCX ------------------------------

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def ingest_docx(path) -> tuple[list, dict, dict]:
    try:
        import docx
        d = docx.Document(str(path))
    except Exception as e:  # noqa: BLE001
        raise PaperError("PARSE_FAILED", f"{type(e).__name__}: {e}") from e
    report = {"warnings": ["DOCX has no fixed pages: locations are paragraph/table indices"],
              "parser": "python-docx", "hidden_runs": 0, "omml_equations": 0}
    b = _Builder("docx")
    para_idx = tbl_idx = 0
    pending_caption = None
    for el in d.element.body.iterchildren():
        if el.tag == W + "p":
            para_idx += 1
            loc = f"paragraph {para_idx}"
            for om in el.iter(M + "oMath"):
                if om.getparent().tag == M + "oMathPara" and om is not next(om.getparent().iter(M + "oMath")):
                    continue
                txt = "".join(t.text or "" for t in om.iter(M + "t"))
                if txt.strip():
                    report["omml_equations"] += 1
                    b.add("formula", clean(txt), line=para_idx, confidence="medium", flags=["omml_linearized"],
                          data={"latex": None, "location": loc})
            texts, hid = [], []
            for r in el.iter(W + "r"):
                rpr = r.find(W + "rPr")
                vanish = rpr is not None and rpr.find(W + "vanish") is not None
                t = "".join(x.text or "" for x in r.iter(W + "t"))
                (hid if vanish else texts).append(t)
            if any(h.strip() for h in hid):
                report["hidden_runs"] += 1
                b.add("hidden_text", clean("".join(hid)), line=para_idx, confidence="none",
                      flags=["hidden_text", "excluded"], data={"location": loc})
            text = clean("".join(texts))
            if not text:
                continue
            ps = el.find(W + "pPr")
            style = ""
            if ps is not None and ps.find(W + "pStyle") is not None:
                style = ps.find(W + "pStyle").get(W + "val", "")
            sname = d.styles.get_by_id(style, 1).name if style else ""
            hl = re.search(r"(?:Heading|标题)\s*(\d)", sname or "")
            if sname == "Title" or (sname or "").startswith("Title"):
                b.add("title", text, line=para_idx, data={"location": loc})
            elif hl:
                b.heading(text, int(hl.group(1)), line=para_idx)["data"]["location"] = loc
            else:
                blk = b.text(text, line=para_idx, data={"location": loc})
                if blk["kind"] == "caption" and blk["data"]["kind"] == "table":
                    pending_caption = blk
        elif el.tag == W + "tbl":
            tbl_idx += 1
            rows = []
            for tr in el.iter(W + "tr"):
                rows.append([clean("".join(t.text or "" for t in tc.iter(W + "t"))) for tc in tr.iter(W + "tc")])
            cap = pending_caption["text"] if pending_caption else None
            b.table(rows, line=para_idx, caption=cap)["data"]["location"] = f"table {tbl_idx}"
            pending_caption = None
    cp = d.core_properties
    meta = {}
    if cp.title:
        meta["title"] = cp.title
    title_blk = next((x for x in b.blocks if x["kind"] == "title"), None)
    if title_blk:
        meta["title"] = title_blk["text"]
    if cp.author:
        meta["file_author"] = cp.author        # file creator, not necessarily the paper's authors
    return b.blocks, meta, report
