"""Versioned schemas, validation (structure + provenance), JSON/Markdown export and reload."""
from __future__ import annotations

import json
from pathlib import Path

from qrtk_skills.runtime import validate as validate_schema   # shared small JSON-Schema validator

from .common import DOC_SCHEMA
from .errors import PaperError
from .extract import SPEC_SCHEMA

S, A, O, AN = {"type": "string"}, {"type": "array"}, {"type": "object"}, {"type": "any"}
LOC = {"type": "object", "required": ["doc_id", "block_id", "page", "section", "line", "char_start", "char_end"],
       "properties": {"doc_id": S, "block_id": S, "char_start": {"type": "integer", "minimum": 0},
                      "char_end": {"type": "integer", "minimum": 0}}}
EVID = {"type": "object", "required": ["location", "quote"], "properties": {"location": LOC, "quote": S}}
ITEM = {"type": "object", "required": ["field", "status", "value", "evidence", "confidence"],
        "properties": {"status": {"type": "string", "enum": ["supported"]}, "value": S,
                       "evidence": {"type": "array", "items": EVID, "minItems": 1},
                       "confidence": {"type": "string", "enum": ["medium", "low"]}}}
FORMULA = {"type": "object", "required": ["id", "raw", "readable", "status", "executable", "requires_human_check",
                                          "symbols", "defined_variables", "undefined_variables", "block_id", "page"],
           "properties": {"status": {"type": "string", "enum": ["extracted", "suspect", "unresolved"]},
                          "executable": {"type": "boolean", "enum": [False]}, "requires_human_check": {"type": "boolean"}}}
SPEC_JSON_SCHEMA = {
    "type": "object",
    "required": ["schema", "spec_id", "generated_from", "extractor", "paper", "A_supported", "factors", "formulas",
                 "tables", "B_deductions", "C_missing", "ambiguities", "integrity_risks", "security",
                 "extraction_quality", "reproduction_status", "disclaimer"],
    "properties": {
        "schema": {"type": "string", "enum": [SPEC_SCHEMA]}, "spec_id": S,
        "generated_from": {"type": "object", "required": ["doc_id", "filename", "format", "sha256"]},
        "paper": {"type": "object", "required": ["title", "authors", "year", "language"]},
        "A_supported": O, "factors": A, "formulas": {"type": "array", "items": FORMULA}, "tables": A,
        "B_deductions": {"type": "array", "items": {"type": "object", "required": ["type", "statement", "basis",
                         "requires_confirmation"], "properties": {"type": {"type": "string", "enum": ["deduction", "proposal"]},
                         "requires_confirmation": {"type": "boolean", "enum": [True]}}}},
        "C_missing": {"type": "array", "items": {"type": "object", "required": ["item", "question"]}},
        "ambiguities": A, "integrity_risks": {"type": "array", "items": {"type": "object", "required": ["risk", "status", "question"],
                          "properties": {"status": {"type": "string", "enum": ["mentioned_in_source", "not_mentioned"]}}}},
        "security": {"type": "object", "required": ["injection_findings", "hidden_text_blocks", "excluded_from_extraction"]},
        "extraction_quality": O,
        "reproduction_status": {"type": "string", "enum": ["not_reproduced"]}, "disclaimer": S,
    },
}
DOC_JSON_SCHEMA = {"type": "object", "required": ["schema", "doc_id", "source", "metadata", "language", "blocks",
                                                  "sections", "formulas", "tables", "figures", "references", "security",
                                                  "extraction_report"],
                   "properties": {"schema": {"type": "string", "enum": [DOC_SCHEMA]},
                                  "blocks": {"type": "array", "items": {"type": "object", "required":
                                             ["id", "kind", "text", "page", "section", "line", "confidence", "flags", "data"],
                                             "properties": {"kind": {"type": "string", "enum": [
                                                 "title", "heading", "paragraph", "formula", "table", "caption", "reference",
                                                 "code", "hidden_text", "unreadable"]}}}}}}


def _evidence(spec):
    for items in spec["A_supported"].values():
        for it in items:
            yield from it["evidence"]
    for f in spec["factors"]:
        if f["first_mention"]:
            yield f["first_mention"]
        yield from f["definition_evidence"]
    for r in spec["integrity_risks"]:
        yield from r["evidence"]
    for a in spec["ambiguities"]:
        yield from a["evidence"]


def validate_research_spec(spec: dict, document: dict | None = None, *, strict: bool = False) -> dict:
    """Structure against the versioned schema; with the document, also every quote is checked to
    occur exactly at its cited block and character offsets, and every formula's block exists."""
    if not isinstance(spec, dict) or spec.get("schema") != SPEC_SCHEMA:
        err = PaperError("VERSION_UNSUPPORTED", f"expected {SPEC_SCHEMA}, got {spec.get('schema') if isinstance(spec, dict) else type(spec).__name__}")
        if strict:
            raise err
        return {"valid": False, "errors": [str(err)], "warnings": []}
    errors = validate_schema(spec, SPEC_JSON_SCHEMA)
    for field, items in spec.get("A_supported", {}).items():
        for i, it in enumerate(items):
            errors += [f"A_supported.{field}[{i}]: {e}" for e in validate_schema(it, ITEM)]
            # parsed numbers and year ranges must be verbatim substrings of the quoted sentence
            for r in it.get("results", []):
                if r.get("value") not in it.get("value", ""):
                    errors.append(f"A_supported.{field}[{i}]: result value {r.get('value')!r} not in quote")
            for sp_ in it.get("splits", []):
                if sp_.get("text") not in it.get("value", ""):
                    errors.append(f"A_supported.{field}[{i}]: split {sp_.get('text')!r} not in quote")
    warnings = []
    if document is not None:
        if document.get("doc_id") != spec["generated_from"]["doc_id"]:
            errors.append("spec was generated from a different document")
        blocks = {b["id"]: b for b in document["blocks"]}
        for ev in _evidence(spec):
            loc = ev["location"]
            b = blocks.get(loc["block_id"])
            if b is None:
                errors.append(f"evidence cites unknown block {loc['block_id']}")
            elif b["text"][loc["char_start"]:loc["char_end"]] != ev["quote"]:
                errors.append(f"quote does not match block {loc['block_id']} at {loc['char_start']}:{loc['char_end']}")
            elif b["page"] != loc["page"]:
                errors.append(f"page mismatch for block {loc['block_id']}")
            elif "injection_suspect" in b["flags"] or "hidden_text" in b["flags"]:
                errors.append(f"evidence drawn from an excluded block {loc['block_id']}")
        for f in spec["formulas"]:
            if f["block_id"] not in blocks:
                errors.append(f"formula {f['id']} cites unknown block {f['block_id']}")
    if spec.get("extraction_quality", {}).get("pages_unreadable"):
        warnings.append(f"unreadable pages: {spec['extraction_quality']['pages_unreadable']}")
    if strict and errors:
        raise PaperError("PROVENANCE_INVALID" if any("quote" in e or "block" in e for e in errors) else "SCHEMA_INVALID",
                         "; ".join(errors[:5]))
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def validate_document(doc: dict) -> list[str]:
    return validate_schema(doc, DOC_JSON_SCHEMA)


def _where(loc):
    parts = []
    if loc.get("page"):
        parts.append(f"p.{loc['page']}")
    if loc.get("line"):
        parts.append(f"line {loc['line']}")
    if loc.get("section"):
        parts.append(f"§ {loc['section']}")
    parts.append(f"`{loc['block_id']}`")
    return ", ".join(parts)


def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def spec_markdown(spec: dict) -> str:
    p = spec["paper"]
    val = lambda x: x["value"] if isinstance(x, dict) else "未识别"
    L = [f"# 研究规格：{_md_cell(val(p['title']))}", "",
         f"> {spec['disclaimer']}", "",
         f"- 来源文件：`{spec['generated_from']['filename']}`（{spec['generated_from']['format']}，SHA-256 `{spec['generated_from']['sha256'][:16]}…`）",
         f"- 作者：{_md_cell(val(p['authors']))}；年份：{val(p['year'])}；语言：{p['language']}",
         f"- 抽取器：{spec['extractor']['name']} {spec['extractor']['version']}（{spec['extractor']['method']}）",
         f"- 复现状态：**{spec['reproduction_status']}**；spec_id `{spec['spec_id']}`", ""]
    L += ["## A. 原文支持的陈述（逐字引用）", ""]
    for field, items in spec["A_supported"].items():
        L += [f"### {field}", "", "| 引文 | 位置 |", "|---|---|"]
        for it in items:
            tag = f" [{it['data_field']}]" if "data_field" in it else ""
            tag += f" {{n={it['parsed']['n']}, unit={it['parsed']['unit']}}}" if "parsed" in it else ""
            L.append(f"| {_md_cell(it['value'])}{tag} | {_where(it['evidence'][0]['location'])} |")
        L.append("")
    L += ["## 因子", ""]
    for f in spec["factors"] or []:
        fm = _where(f["first_mention"]["location"]) if f["first_mention"] else "仅出现在公式中"
        L.append(f"- **{f['name']}** {('(' + ', '.join(f['aliases']) + ')') if f['aliases'] else ''}：{f['status']}；"
                 f"出现 {f['mentions']} 次；首次 {fm}；关联公式 {', '.join(f['formula_ids']) or '无'}")
    if not spec["factors"]:
        L.append("- 未识别出命名因子。")
    L += ["", "## 公式（可读 ≠ 可执行）", ""]
    for f in spec["formulas"]:
        L += [f"### {f['id']}（{f['status']}，{f['source_kind']}，p.{f['page']}，`{f['block_id']}`）", "",
              "```text", f["readable"], "```", ""]
        if f["defined_variables"]:
            L += [f"- `{s}`：{_md_cell(d['definition'])}（`{d['block_id']}`）" for s, d in f["defined_variables"].items()]
        if f["undefined_variables"]:
            L.append(f"- 未找到定义：{', '.join(f['undefined_variables'])}")
        if f["issues"]:
            L.append(f"- 疑点：{'; '.join(f['issues'])}")
        L.append("")
    if spec["tables"]:
        L += ["## 表格", "", "| 块 | 页 | 标题 | 列 | 行数 | 单位 | 问题 | 跨页 |", "|---|---|---|---|---|---|---|---|"]
        for t in spec["tables"]:
            cont = (f"续自 {t['continuation_of']}" if t["continuation_of"] else "") + (f"续于 {', '.join(t['continued_in'])}" if t["continued_in"] else "")
            L.append(f"| `{t['block_id']}` | {t['page']} | {_md_cell(t['caption'] or '（无标题）')} | {_md_cell(' / '.join(t['header']))} | "
                     f"{t['n_rows']} | {', '.join(t['units']) or ''} | {'; '.join(t['issues'])} | {cont} |")
        L.append("")
    L += ["## B. 推断与实现建议（不是原文事实，均需确认）", ""]
    L += [f"- [{d['type']}] {_md_cell(d['statement'])}" for d in spec["B_deductions"]] or ["- 无"]
    L += ["", "## C. 缺失信息（需要澄清）", ""]
    L += [f"- {'（可选）' if c.get('optional') else ''}**{c['item']}**：{c['question']}" for c in spec["C_missing"]] or ["- 无"]
    L += ["", "## 歧义", ""]
    L += [f"- **{a['topic']}**：{a['detail']}。{a['question']}" for a in spec["ambiguities"]] or ["- 无"]
    L += ["", "## 研究诚信风险检查", "", "| 风险 | 原文 | 问题 | 依据 |", "|---|---|---|---|"]
    for r in spec["integrity_risks"]:
        L.append(f"| {r['risk']} | {r['status']} | {r['question']} | {', '.join(_where(e['location']) for e in r['evidence']) or '—'} |")
    L += ["", "提及不等于已经正确处理。", "", "## 安全", ""]
    sec = spec["security"]
    L.append(f"- 疑似提示注入 {len(sec['injection_findings'])} 处，隐藏文本 {sec['hidden_text_blocks']} 处；这些块已从抽取中排除，内容未被执行。")
    for fnd in sec["injection_findings"]:
        L.append(f"  - `{fnd['block_id']}`（p.{fnd['page']}）：{_md_cell(fnd['excerpt'][:100])}")
    q = spec["extraction_quality"]
    L += ["", "## 抽取质量", "",
          f"- 无法读取的页：{q['pages_unreadable'] or '无'}；低置信页：{q['pages_low_confidence'] or '无'}",
          f"- 未解析公式：{q['formulas_unresolved'] or '无'}；可疑公式：{q['formulas_suspect'] or '无'}",
          f"- 可疑表格：{q['tables_suspect'] or '无'}；有标题但未检测到表体：{q['table_captions_without_body'] or '无'}"]
    L += [f"- 警告：{w}" for w in q["warnings"]]
    return "\n".join(L) + "\n"


def export_research_spec(spec: dict, out_dir, basename: str = "research_spec") -> dict:
    """Write <basename>.json (canonical) and <basename>.md (human summary)."""
    res = validate_research_spec(spec)
    if not res["valid"]:
        raise PaperError("SCHEMA_INVALID", "; ".join(res["errors"][:5]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp, mp = out / f"{basename}.json", out / f"{basename}.md"
    jp.write_text(json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    mp.write_text(spec_markdown(spec), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}


def load_research_spec(path) -> dict:
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PaperError("PARSE_FAILED", f"{type(e).__name__}: {e}") from e
    validate_research_spec(spec, strict=True)
    return spec
