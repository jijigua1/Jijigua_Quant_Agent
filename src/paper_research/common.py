"""Shared text utilities: blocks, sentences, language, structure cues, injection scanning."""
from __future__ import annotations

import re
import unicodedata

DOC_SCHEMA = "paper_research.document/1.0"

CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
PUA = re.compile(r"[-]")
CID = re.compile(r"\(cid:\d+\)")


def make_block(bid, kind, text, *, page=None, section=None, bbox=None, line=None, level=None,
               confidence="high", flags=None, data=None):
    return {"id": bid, "kind": kind, "text": text, "page": page, "section": section,
            "bbox": [round(float(v), 1) for v in bbox] if bbox else None, "line": line,
            "level": level, "confidence": confidence, "flags": list(flags or []), "data": dict(data or {})}


LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})


def clean(s: str) -> str:
    # typographic ligatures ("deﬁned") would hide words from every keyword pattern
    s = unicodedata.normalize("NFC", s.replace("­", "")).translate(LIGATURES)
    return re.sub(r"[ \t]+", " ", s).strip()


def language(text: str) -> str:
    """'zh', 'en', 'mixed' or 'unknown' from character composition (no external model)."""
    cjk = len(CJK.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk + latin < 20:
        return "unknown"
    share = cjk / (cjk + latin / 4)          # ~4 latin letters per word vs 1 CJK char per word
    return "zh" if share > 0.7 else "en" if share < 0.2 else "mixed"


def garble_score(text: str) -> float:
    """Share of characters that indicate failed extraction (PUA glyphs, (cid:n), U+FFFD)."""
    if not text:
        return 0.0
    bad = (len(PUA.findall(text)) + text.count("�") + 6 * len(CID.findall(text))
           + len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text)))
    return min(1.0, bad / max(1, len(text)))


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])|(?<=[。！？；])")


def sentences(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) with offsets into text; English and Chinese punctuation."""
    out, pos = [], 0
    for m in _SENT.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            s = pos + len(seg) - len(seg.lstrip())
            out.append((s, m.start(), text[s:m.start()].rstrip()))
        pos = m.end()
    seg = text[pos:]
    if seg.strip():
        s = pos + len(seg) - len(seg.lstrip())
        out.append((s, len(text.rstrip()), text[s:].rstrip()))
    return out


HEADING_NUM = re.compile(r"^(?P<num>(?:\d+(?:\.\d+){0,3})|[IVX]+|[A-H](?:\.\d+)?)[.)]?\s+(?P<title>\S.{0,90})$")
HEADING_ZH = re.compile(r"^(?P<num>[一二三四五六七八九十]+[、.]|第[一二三四五六七八九十\d]+[章节]|（[一二三四五六七八九十]+）)\s*(?P<title>\S.{0,40})$")
NAMED_SECTIONS = re.compile(r"^(abstract|introduction|data|methodology|methods?|conclusions?|references|bibliography|"
                            r"appendix|related literature|literature review|empirical results|robustness|"
                            r"摘要|引言|数据|方法|研究方法|结论|参考文献|附录|实证结果|稳健性检验)\b", re.I)
CAPTION = re.compile(r"^(?P<kind>Table|TABLE|Figure|FIGURE|Fig\.|FIG\.|Exhibit|EXHIBIT|表|图|续表)\s*(?P<num>[A-Z]?\d+(?:\.\d+)?|[IVXL]{1,6}\b)?\s*[:.：．]?\s*")
EQ_NUMBER = re.compile(r"[(（]\s*(\d+(?:\.\d+)?[a-z]?)\s*[)）]\s*$")


def heading_match(text: str):
    t = text.strip()
    if len(t) > 100 or t.endswith((".", "。", ",", "，")) and not NAMED_SECTIONS.match(t):
        return None
    for rx in (HEADING_NUM, HEADING_ZH):
        m = rx.match(t)
        if m and not re.search(r"[=<>]", t) and not re.fullmatch(r"[\d.\s%,-]+", t):
            return m.group("num").rstrip("、."), m.group("title")
    if NAMED_SECTIONS.match(t) and len(t) < 40:
        return None, t
    return None


def caption_match(text: str):
    m = CAPTION.match(text.strip())
    if not m or not m.group("num") and m.group("kind") not in ("续表",):
        return None
    rest = text.strip()[m.end():]
    if re.match(r"[a-z]", rest) or re.match(r"(显示|报告|列出|给出|展示|表明|中)", rest):
        return None                                   # "Table 2 reports ..." is prose, not a caption
    k = m.group("kind").lower()
    kind = "table" if k in ("table", "表", "续表", "exhibit") else "figure"
    continued = k == "续表" or bool(re.search(r"\(cont(inued|\.)?\)|续", text, re.I))
    return kind, m.group("num"), continued


INJECTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instructions?|prompts?|rules)\b",
    r"\bdisregard\b.{0,40}\b(instructions?|above|previous)\b",
    r"\b(you are|act as)\b.{0,30}\b(ai|assistant|chatgpt|claude|agent|language model)\b",
    r"\bsystem prompt\b",
    r"\b(as an?|dear)\s+(ai|llm|language model|agent|assistant)\b",
    r"\b(execute|run)\b.{0,30}\b(command|code|script|shell|following)\b",
    r"\b(download|fetch|visit|open)\b.{0,40}\b(https?://|url|link)\b",
    r"\b(send|upload|email|post)\b.{0,40}\b(data|files?|keys?|credentials?|results?)\b",
    r"\b(api[_ ]?key|password|credential)s?\b",
    r"(rm -rf|/etc/passwd|curl\s+http|wget\s+http|powershell\s|os\.system|subprocess)",
    r"忽略.{0,15}(指令|提示|规则|要求)", r"你(现在)?是.{0,10}(助手|AI|模型|智能体)",
    r"(请|立即)(执行|运行|下载|访问|发送|上传)", r"(系统提示|提示词|密钥|密码)",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def injection_hits(text: str) -> list[str]:
    """Patterns of instructions aimed at an AI/agent. Content is data: it is only reported."""
    return [p.pattern for p in _INJ if p.search(text)]
