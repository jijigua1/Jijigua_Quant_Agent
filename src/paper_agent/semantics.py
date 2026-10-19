"""Paper semantics vs the research definition: deterministic, independent of the model that wrote the definition.

The model reads the paper and writes a formula plus a symbol table; nothing here asks it to agree with itself. Instead:

1. temporal cues are read from the VERIFIED quotes of the factor (verbal definition, formula citations, symbol citations)
   with fixed English/Chinese patterns: cumulative look-back returns ("past 1-, 3- and 12-month returns", "过去20日涨跌幅"),
   single lagged returns ("return in month t-1"), skipped periods, log returns, exponential smoothing;
2. the formula's actual time usage is read from its IR (a subscript t-k is always a lag; a window is explicit);
3. fixed rules compare the two (look-back read as lag, cumulative read as one period, missing skip, log vs simple,
   exponential read as a simple mean, window length);
4. every number that sets a window or a lag must appear in the factor's quotes (or be a declared replication choice);
5. every formula symbol needs a verified definition, and a mapping onto a market field needs that field's words in the
   cited text; an undefined symbol is reported with the passages that mention it and what is missing.

A conflict is never resolved in the model's favour: it blocks, or the model is asked once more with the exact
conflict (bounded, recorded), and the result is checked again by the same rules.
"""
from __future__ import annotations

import re
import unicodedata

from paper_research.factor_ir import TS_OPS, walk


def plain(text):
    """Text as the rules read it: PDF math italics (𝑐𝑙𝑜𝑠𝑖𝑛𝑔 𝑝𝑟𝑖𝑐𝑒) and full-width forms folded to plain letters (NFKC).
    Live R2: the program missed "closing price" in a math-italic quote and blamed the reader's field mapping."""
    return unicodedata.normalize("NFKC", text or "")

VERSION = "paper_agent.semantics/1.0"

WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60, "fifty-two": 52}
ZHN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十二": 12,
       "二十": 20, "六十": 60}
N = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|sixty|fifty-two)"
NLIST = rf"{N}(?:\s*[-–]?\s*(?:,|and|or|to|through)\s*{N})*"
UNIT = r"(?:trading[- ]days?|days?|weeks?|months?|quarters?|years?)"
ZH_N = r"(?:\d+|[一二两三四五六七八九十]+)"
NUM_TOKEN = (r"\d+|(?<![A-Za-z])(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|sixty|"
             r"fifty-two)(?![A-Za-z])|[一二两三四五六七八九十]+")
ZH_UNIT = r"(?:交易日|个交易日|日|天|周|个月|月|季度|年)"
PERIOD_ROWS = {"trading_day": 1, "day": 1, "week": 5, "month": 21, "quarter": 63, "year": 252}

CUES = [
    ("lookback", re.compile(rf"\b(?:past|previous|prior|last|preceding|trailing)\s+(?P<n>{NLIST})\s*[- ]?(?P<u>{UNIT})\s*"
                            rf"(?:\w+\s+){{0,2}}?(?:cumulative\s+|total\s+|excess\s+|log\s+)?(?:returns?|performance|price changes?)", re.I)),
    ("lookback", re.compile(rf"\b(?P<n>{NLIST})\s*[- ]?(?P<u>{UNIT})\s*(?:\w+\s+){{0,3}}?(?:cumulative\s+|past\s+|total\s+|trailing\s+)?"
                            rf"(?:returns?|momentum|performance)\b", re.I)),
    # "1-month, 3-month and 12-month ... momentum": every number carries its own unit
    ("lookback", re.compile(rf"\b(?P<n>{N}\s*[- ]?{UNIT}(?:\s*(?:,|and|or)\s*(?:and\s+)?{N}\s*[- ]?{UNIT})+)\s+(?:[\w-]+\s+){{0,3}}?"
                            rf"(?:returns?|momentum|performance|signals?|strateg\w+)\b", re.I)),
    ("lookback", re.compile(rf"\breturns?\s+(?:over|during|in)\s+the\s+(?:past|previous|prior|last|preceding)\s+(?P<n>{NLIST})\s*[- ]?(?P<u>{UNIT})", re.I)),
    ("lookback", re.compile(rf"\b(?P<n>{NLIST})\s*[- ]?(?P<u>{UNIT})\s+(?:look-?back|formation|ranking)\s+(?:periods?|horizons?|windows?)", re.I)),
    ("lookback", re.compile(rf"\b(?:look-?back|formation|ranking)\s+(?:periods?|horizons?|windows?)\s+of\s+(?P<n>{NLIST})\s*[- ]?(?P<u>{UNIT})", re.I)),
    ("lookback", re.compile(r"\bover the (?:indicated|given|respective|specified|corresponding) (?:look-?back|formation) (?:horizons?|periods?|windows?)"
                            r"|\bcumulative (?:past )?returns?\b|\bpast returns? over\b", re.I)),
    ("lookback", re.compile(rf"(?:过去|最近|前)\s*(?P<n>{ZH_N}(?:\s*[、,，和及]\s*{ZH_N})*)\s*(?P<u>{ZH_UNIT})\s*(?:的)?\s*(?:累计|累积)?\s*(?:收益率?|涨跌幅|涨幅|回报)")),
    ("lookback", re.compile(rf"(?P<n>{ZH_N})\s*(?P<u>日|周|月|个月)\s*(?:累计)?(?:收益率|涨跌幅|涨幅|动量)")),
    ("lookback", re.compile(r"形成期|回看期|回溯期|累计收益|累积收益")),
    ("single_lag", re.compile(rf"\breturns?\s+(?:in|of|during)\s+(?:month|week|day|year|period)\s+t\s*[-−–]\s*(?P<n>\d+)", re.I)),
    ("single_lag", re.compile(rf"\blagged\s+(?P<n>{N})\s*[- ]?(?P<u>{UNIT})\s+returns?", re.I)),
    ("single_lag", re.compile(r"上(?:一|个)?(?P<u>月|周|日)(?:的)?(?:收益|涨跌幅)|滞后\s*(?P<n>\d+)\s*期")),
    ("skip", re.compile(rf"\bskip(?:ping|s|ped)?\s+(?:the\s+)?(?:most recent|last|latest|first)?\s*(?:(?P<n>{N})\s+)?(?P<u>{UNIT})", re.I)),
    ("skip", re.compile(rf"\bexclud(?:e|ing)\s+the\s+(?:most recent|last|latest)\s+(?:(?P<n>{N})\s+)?(?P<u>{UNIT})", re.I)),
    ("skip", re.compile(rf"(?:跳过|剔除|去掉)\s*(?:最近|最新)\s*(?P<n>{ZH_N})?\s*(?:个)?(?P<u>{ZH_UNIT})")),
    ("log", re.compile(r"\blog(?:arithmic)?[- ]returns?\b|\bcontinuously compounded\b|\blog[- ]price\b|对数收益")),
    ("exponential", re.compile(r"\bexponential(?:ly)?[- ](?:weighted\s+)?moving[- ]averages?\b|\bEMA\b|\bEWMA\b|\bexponential smoothing\b|"
                               r"\bexponentially weighted\b|\bWilder\b|指数移动平均|指数平滑|指数加权", re.I)),
    ("simple_mean", re.compile(r"\bsimple moving average\b|\barithmetic (?:mean|average)\b|简单移动平均|算术平均", re.I)),
]
FIELD_WORDS = {
    "close": r"\bclos\w*|\bprices?\b|\bvalues?\b|\blevels?\b|收盘|价格|股价|点位",
    "open": r"\bopen\w*|开盘",
    "high": r"\bhigh\w*|最高",
    "low": r"\blow\w*|最低",
    "volume": r"\bvolume\b|\bshares traded\b|\bnumber of shares\b|\btrading activity\b|成交量",
    "amount": r"\bdollar volume\b|\bvolume in (?:dollars|yuan|rmb)\b|\bamount\b|\btrading value\b|\bvalue traded\b|成交额|成交金额",
    "returns": r"\breturns?\b|\bprice changes?\b|收益|涨跌",
}
NOT_A_FIELD = re.compile(r"\bturnover (?:rate|ratio)\b|换手率|\bshares outstanding\b|流通股本|总股本|\bmarket cap\w*|市值|"
                         r"\bbook\b|\bearnings\b|市盈率|\bP/?E\b|分析师|\banalyst", re.I)


def _num(tok):
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    if tok in WORDN:
        return WORDN[tok]
    if tok in ZHN:
        return ZHN[tok]
    if re.fullmatch(r"[一二三四五六七八九]?十[一二三四五六七八九]?", tok):
        tens, _, ones = tok.partition("十")
        return (ZHN.get(tens, 1) if tens else 1) * 10 + (ZHN.get(ones, 0) if ones else 0)
    return None


def _unit(u):
    if not u:
        return None
    u = u.lower()
    for key, words in (("trading_day", ("trading", "交易日")), ("week", ("week", "周")), ("month", ("month", "月")),
                       ("quarter", ("quarter", "季")), ("year", ("year", "年")), ("day", ("day", "日", "天"))):
        if any(w in u for w in words):
            return key
    return None


def cues(text):
    """Temporal / smoothing cues in one text: [{kind, numbers, unit, match}]."""
    out = []
    for kind, rx in CUES:
        for m in rx.finditer(text or ""):
            g = m.groupdict()
            nums = [_num(x) for x in re.findall(NUM_TOKEN, g.get("n") or "", re.I)] if g.get("n") else []
            unit = _unit(g.get("u")) or (_unit(re.findall(UNIT, g["n"], re.I)[-1]) if g.get("n") and re.findall(UNIT, g["n"], re.I) else None)
            out.append({"kind": kind, "numbers": [x for x in nums if x], "unit": unit, "match": m.group(0)[:120]})
    return out


def _quotes(item):
    q = [c["quote"] for c in (item.get("verbal_definition") or {}).get("citations", [])]
    q += [c["quote"] for c in (item.get("formula") or {}).get("citations", [])]
    # verified quotes for the factor's named parameters (e.g. "traditional MACD parameter (12,26,9)") support its numbers
    q += [c["quote"] for p in item.get("parameters") or [] if p.get("status") == "PAPER" for c in p.get("citations") or []]
    return [plain(x) for x in q]


def _sym_text(sym):
    return plain(" ".join([c["quote"] for c in sym.get("citations") or []]))


def usage(ir):
    """symbol -> list of {lag, var, in_window, window_ops}; a subscript t-k is ALWAYS the value observed k periods before t."""
    out = {}

    def visit(node, stack):
        if node["op"] == "field":
            out.setdefault(node["symbol"], []).append({"lag": node["lag"]["base"], "var": node["lag"].get("var"),
                                                       "in_window": bool(stack), "window_ops": list(stack)})
        inner = stack + ([node["op"]] if node["op"] in TS_OPS or node["op"] == "ema" else [])
        for a in node.get("args", []):
            visit(a, inner)
    visit(ir, [])
    return out


def _numbers_in(texts):
    found = set()
    for t in texts:
        for tok in re.findall(rf"\b{N}\b|{ZH_N}", t or "", re.I):
            v = _num(tok)
            if v:
                found.add(v)
    return found


def _accepted_constants(texts, freq_unit):
    """Numbers the quotes support, with the usual period conversions (one year = 250/252 trading days = 12 months ...)."""
    base = _numbers_in(texts)
    out = set(base)
    joined = " ".join(texts).lower()
    for n in base:
        out.update({n - 1, n + 1})
    for word, rows in (("year", (250, 252, 12, 52, 1)), ("annual", (250, 252, 12, 52)), ("month", (21, 20, 22, 1)),
                       ("week", (5, 1)), ("quarter", (63, 3)), ("年", (250, 252, 12, 52)), ("月", (21, 20, 22)), ("周", (5,))):
        if word in joined:
            for r in rows:
                for n in base | {1}:
                    out.update({n * r, n * r - 1})
    return out


def check_factor(item, *, replication_notes=(), repairs=(), freq=None):
    """Semantic conflicts between the paper's verified quotes and the factor's formula/symbol table.

    Returns a list of {code, symbol, blocking, detail, evidence}. Uses only verified quotes and the parsed formula.
    """
    from paper_research.factor_ir import IRError, parse_formula
    conf = []
    latex = (item.get("formula") or {}).get("latex") or ""
    try:
        ir = parse_formula(latex)["ir"] if latex else None
    except (IRError, ValueError):
        return conf                                      # unparseable formulas are reported by the grammar check
    if ir is None:
        return conf
    syms = {s["symbol"]: s for s in item.get("symbols") or []}
    use = usage(ir)
    factor_quotes = _quotes(item)
    factor_cues = [c for q in factor_quotes for c in cues(q)]
    # papers that date the formation at t-1 (holding period t) write every input at the same lag L: that common lag is a
    # dating convention (the task builder removes it), not a look-back read as a lag
    all_lags = {u["lag"] for us in usage(ir).values() for u in us if not u["in_window"]}
    common_lag = next(iter(all_lags)) if len(all_lags) == 1 and not any(u["in_window"] for us in usage(ir).values() for u in us) else None
    lookback_nums = sorted({n for c in factor_cues if c["kind"] == "lookback" for n in c["numbers"]})
    for name, uses in use.items():
        s = syms.get(name) or {}
        text = " ".join([_sym_text(s), s.get("meaning") or ""])
        own = cues(_sym_text(s)) + cues(s.get("meaning") or "")
        kinds = {c["kind"] for c in own}
        # a price read as a price (P_t / P_{t-12} - 1 IS the 12-month return) is not a return symbol, even when its quotes
        # talk about returns (A/B: AQR's P was flagged LOOKBACK_READ_AS_LAG)
        price = s.get("kind") == "raw_field" and s.get("data_field") in ("close", "open", "high", "low", "unknown") and \
            re.search(r"\bprices?\b|\blevels?\b|价格|收盘|点位", s.get("meaning") or "", re.I)
        is_return = s.get("data_field") == "returns" or s.get("kind") in ("period_return", "cumulative_return") or \
            (re.search(r"\breturns?\b|收益|涨跌", text, re.I) and not price)
        single = [u for u in uses if not u["in_window"]]
        lags = sorted({u["lag"] for u in single})
        if is_return and s.get("kind") != "cumulative_return":
            symbol_lookback = "lookback" in kinds
            # (a) a look-back return written as a lagged one-period return: r_{t-12} for "past 12-month return"
            if (symbol_lookback or lookback_nums) and any(k > 0 for k in lags) and common_lag is None:
                same = bool(lookback_nums) and set(k for k in lags if k > 0) <= set(lookback_nums)
                if symbol_lookback or same:
                    conf.append({"code": "LOOKBACK_READ_AS_LAG", "symbol": name, "blocking": True,
                                 "detail": f"原文把 {name} 描述为回看期累计收益（{'; '.join(c['match'] for c in own + factor_cues if c['kind'] == 'lookback')[:220]}），"
                                           f"公式却写成单期收益的滞后 {name}_{{t-{', t-'.join(str(k) for k in lags if k > 0)}}}"
                                           "（下标 t-k 只表示 k 期之前观察到的一个值，不是回看长度）",
                                 "evidence": [c["match"] for c in own + factor_cues if c["kind"] == "lookback"][:4]})
            # (b) a multi-period look-back return written as the current one-period return
            elif symbol_lookback and lags == [0] and any(n > 1 for c in own for n in c["numbers"]):
                conf.append({"code": "CUMULATIVE_READ_AS_SINGLE_PERIOD", "symbol": name, "blocking": True,
                             "detail": f"原文 {name} 为多期累计收益（{'; '.join(c['match'] for c in own if c['kind'] == 'lookback')[:160]}），公式只用当期单期收益"})
        if s.get("kind") == "cumulative_return":
            if "single_lag" in kinds and "lookback" not in kinds:
                conf.append({"code": "LAG_READ_AS_LOOKBACK", "symbol": name, "blocking": True,
                             "detail": f"原文描述的是某一期的单期收益（{'; '.join(c['match'] for c in own if c['kind'] == 'single_lag')[:160]}），定义却写成累计收益"})
            win = s.get("window") or {}
            nums = sorted({n for c in own if c["kind"] == "lookback" for n in c["numbers"]})
            if win.get("n") and nums and win["n"] not in nums:
                conf.append({"code": "LOOKBACK_WINDOW_MISMATCH", "symbol": name, "blocking": True,
                             "detail": f"原文回看期 {nums} {own[0].get('unit') or ''}，定义为 {win}"})
        if "log" in kinds and is_return and (s.get("compounding") or "simple") != "log" and "log" not in latex:
            conf.append({"code": "LOG_RETURN_READ_AS_SIMPLE", "symbol": name, "blocking": True,
                         "detail": f"原文 {name} 为对数收益（{next(c['match'] for c in own if c['kind'] == 'log')}），定义按简单收益计算"})
        # exponential smoothing read as a simple mean (EMA silently replaced by SMA)
        exp_cue = "exponential" in kinds or re.search(r"exponential|\bEMA\b|指数移动平均|指数平滑", s.get("meaning") or "", re.I)
        if exp_cue and (s.get("aggregate") in ("mean", "sum") or any("ts_mean" in u["window_ops"] for u in uses)):
            conf.append({"code": "EXPONENTIAL_READ_AS_MEAN", "symbol": name, "blocking": True,
                         "detail": f"{name} 在原文/符号表中是指数平滑（EMA），定义却是简单平均"})
    # skip periods stated for this factor must be in the definition
    skip_cues = [c for c in factor_cues if c["kind"] == "skip"]
    has_skip = any(s.get("skip") for s in syms.values()) or any(
        n["op"] in TS_OPS and n["start"] >= 1 for n in walk(ir)) or any(u["lag"] >= 1 for us in use.values() for u in us if not u["in_window"])
    if skip_cues and not has_skip:
        conf.append({"code": "SKIP_PERIOD_MISSING", "blocking": True,
                     "detail": f"原文要求跳过最近的期（{skip_cues[0]['match']}），定义没有跳过期"})
    # exponential smoothing in the factor's own definition but no recursion in the formula
    if any(c["kind"] == "exponential" for c in factor_cues) and not any(n["op"] == "ema" for n in walk(ir)) and \
            not any(x["code"] == "EXPONENTIAL_READ_AS_MEAN" for x in conf):
        conf.append({"code": "EXPONENTIAL_SMOOTHING_MISSING", "blocking": True,
                     "detail": "原文定义使用指数平滑（EMA），公式中没有指数平滑"})
    # numbers that set windows and lags need a source
    paper_support = factor_quotes + [_sym_text(s) for s in syms.values()]
    choices = [" ".join(str(n.get(k, "")) for k in ("choice", "reason")) for n in replication_notes] + \
        [" ".join(str(r.get(k, "")) for k in ("repaired", "note")) for r in repairs]
    in_paper = _accepted_constants(paper_support, freq)
    accepted = _accepted_constants(paper_support + choices, freq)
    used = set()
    for n in walk(ir):
        if n["op"] in TS_OPS:
            used.update({n["start"], n["end"], n["end"] - n["start"] + 1})
        if n["op"] == "field" and n["lag"]["base"] > 1:
            used.add(n["lag"]["base"])
        if n["op"] == "ema":
            used.add(n["n"])
    unsupported = sorted(c for c in used if c > 1 and c not in accepted)
    if unsupported:
        conf.append({"code": "CONSTANT_WITHOUT_SOURCE", "blocking": True,
                     "detail": f"公式中的窗口/滞后数值 {unsupported} 在原文引文中找不到出处，也没有声明为复现选择"})
    chosen = sorted(c for c in used if c > 1 and c in accepted and c not in in_paper)
    if chosen:
        # the paper does not state these numbers: they are the model's replication choice and go to the user as a decision
        conf.append({"code": "PARAMETER_CHOSEN_NOT_IN_PAPER", "blocking": False, "values": chosen,
                     "detail": f"窗口/参数 {chosen} 不是原文给出的数值，而是复现时的选择（{'；'.join(x[:120] for x in choices if x.strip())[:240]}）"})
    conf += window_length_conflicts(item, ir, factor_quotes, freq)
    return conf


FREQ_ROWS = {"daily": 1, "weekly": 5, "monthly": 21, "quarterly": 63, "annual": 252}
SPAN = re.compile(rf"(?P<n>{N})\s*[- ]?\s*(?P<u>{UNIT})", re.I)


def window_length_conflicts(item, ir, factor_quotes, freq):
    """A window's length (end - start + 1 observations at the paper's frequency) must be a period the factor's verified
    quotes state ("the 12-month period", "52-week high", "past 20 days"), converted to that frequency; one fewer is the
    skip form. Nothing is checked when the quotes state no period or the frequency is unknown (live recheck D09 run 1:
    "12-month period" written as max_{0<=k<=12}, 13 months, from the appendix wording "months t-j-12 to t-j")."""
    rows = FREQ_ROWS.get((freq or "").lower())
    if not rows:
        return []
    texts = list(factor_quotes) + [_sym_text(s) for s in item.get("symbols") or []]
    spans, where = set(), {}
    for t in texts:
        for m in SPAN.finditer(t or ""):
            n, u = _num(m.group("n")), _unit(m.group("u"))
            if n and u in PERIOD_ROWS:
                v = n * PERIOD_ROWS[u] / rows
                spans.add(v)
                where.setdefault(v, m.group(0))
    if not spans:
        return []
    out = []
    for node in walk(ir):
        if node["op"] not in TS_OPS or not node.get("var"):
            continue
        length = node["end"] - node["start"] + 1
        if length <= 1:
            continue
        if any(abs(length - v) <= max(0.5, 0.03 * v) or abs(length - (v - 1)) <= max(0.5, 0.03 * v) for v in spans):
            continue
        stated = "、".join(dict.fromkeys(where[v] for v in sorted(spans)))
        out.append({"code": "WINDOW_LENGTH_CONTRADICTS_PAPER", "blocking": True, "symbol": None,
                    "detail": f"公式窗口 {node['op']}_{{{node['var']}={node['start']}..{node['end']}}} 共 {length} 期（{freq}），"
                              f"但原文引文给出的期间是：{stated}",
                    "evidence": [where[v] for v in sorted(spans)][:4]})
    return out


def check_symbols(item, evidence=None, used=None):
    """Symbol table: verified definitions, field mappings with lexical support, undefined symbols with search results.
    `used`: the inputs of an algorithm factor (no formula); otherwise the formula's own fields."""
    from paper_research.factor_ir import IRError, fields_used, parse_formula
    conf = []
    latex = (item.get("formula") or {}).get("latex") or ""
    if used is None:
        try:
            used = set(fields_used(parse_formula(latex)["ir"])) if latex else set()
        except (IRError, ValueError):
            return conf
    syms = {s["symbol"]: s for s in item.get("symbols") or []}
    for name in sorted(used):
        s = syms.get(name)
        found = definition_passages(evidence, name) if evidence is not None else []
        where = "；".join(f"p{p['page']} {p['passage']}“{p['text'][:80]}”" for p in found[:3]) or "全文未检索到“该符号=…/where…denotes/其中…表示”形式的定义"
        garbled = [p for p in found if p.get("kind") == "formula"]
        if garbled:
            where += (f"。其中 {garbled[0]['passage']}（第{garbled[0]['page']}页）是公式块，文本层提取为“{garbled[0]['text'][:60]}”，"
                      "无法从文字确认完整定义；需要对该公式区域做视觉解析，或由用户提供该符号的定义")
        if s is None:
            conf.append({"code": "SYMBOL_NOT_IN_TABLE", "symbol": name, "blocking": True,
                         "detail": f"公式符号 {name} 没有出现在符号表中；原文检索：{where}", "candidates": found[:3]})
            continue
        if s.get("status") != "PAPER" and s.get("kind") not in ("constant",):
            conf.append({"code": "SYMBOL_DEFINITION_UNVERIFIED", "symbol": name, "blocking": True,
                         "detail": f"符号 {name}（{(s.get('meaning') or '')[:80]}）没有核验通过的原文定义；原文检索：{where}",
                         "candidates": found[:3]})
            continue
        field, kind = s.get("data_field"), s.get("kind")
        text = _sym_text(s)
        # a derived quantity with no definition is never a market field, whatever data_field it carries (live A/B
        # 2026-10-17 D03u: RS "average rises / average drops" with data_field close became RSI = 100 - 100/(1 + close));
        # returns are the exception: the program derives them from prices under its own return checks (AQR r)
        if kind in ("derived",) and not s.get("derivation_latex") and field != "returns":
            conf.append({"code": "SYMBOL_UNDEFINED", "symbol": name, "blocking": True,
                         "detail": f"符号 {name} 的含义为“{(s.get('meaning') or '')[:100]}”，但没有可计算的定义式；"
                                   f"不能把它映射为任何行情字段。原文检索：{where}", "candidates": found[:3]})
            continue
        if NOT_A_FIELD.search(text) and field in FIELD_WORDS and not re.search(FIELD_WORDS[field], re.sub(NOT_A_FIELD, "", text), re.I):
            conf.append({"code": "FIELD_NOT_IN_PANEL", "symbol": name, "blocking": True,
                         "detail": f"符号 {name} 的原文定义（“{text[:100]}”）是 {NOT_A_FIELD.search(text).group(0)}，不是 {field}"})
            continue
        if kind in ("period_return", "cumulative_return"):
            # a return symbol needs return words; "momentum" alone is an interpretation the user has to see and accept
            if not re.search(FIELD_WORDS["returns"], text, re.I):
                if re.search(r"\bmomentum\b|\btrend\b|动量|趋势", text, re.I):
                    conf.append({"code": "RETURN_INTERPRETED_FROM_MOMENTUM_WORDING", "symbol": name, "blocking": False,
                                 "detail": f"原文对 {name} 只写了“{text[:100]}”，没有直接写明是过去收益；本次按"
                                           f"{'累计' if kind == 'cumulative_return' else '单期'}价格收益解释（领域惯例，不是原文定义）"})
                else:
                    conf.append({"code": "FIELD_MAPPING_UNSUPPORTED", "symbol": name, "blocking": True,
                                 "detail": f"符号 {name} 被定义为收益，但它的原文定义“{text[:120]}”中没有收益或动量的表述"})
            continue
        if kind in ("raw_field", "window_aggregate") and field in FIELD_WORDS:
            if not re.search(FIELD_WORDS[field], text, re.I):
                conf.append({"code": "FIELD_MAPPING_UNSUPPORTED", "symbol": name, "blocking": True,
                             "detail": f"符号 {name} 被映射为 {field}，但它的原文定义“{text[:120]}”中没有对应字段的词语"})
    return conf


def definition_passages(evidence, symbol):
    """Passages that look like a definition of `symbol` (English and Chinese patterns), in document order."""
    if evidence is None or not symbol:
        return []
    s = rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9])"
    arg = r"(?:\s*\(\s*[a-z]\s*\)|_\{?[a-z0-9,\s]+\}?)?"
    rx = re.compile(rf"(?:where|in which|here|let)\s+{s}{arg}\s|{s}{arg}\s+(?:is|denotes|represents|stands for|measures|refers to)\b|"
                    rf"{s}{arg}\s*(?:=|:=|≡)|=\s*{s}\s*\(\s*[a-z]\s*\)|\b(?:a|an|the)\s+(?:[\w\-]+\s+){{0,5}}{s}{arg}\s+(?:that|which|is)\b|"
                    rf"其中\s*{s}|{s}{arg}\s*(?:为|表示|代表|是指)")
    out = []
    for p in evidence.passages:
        if p.get("kind") == "table":
            continue
        if rx.search(plain(p["text"])):
            out.append({"passage": p["id"], "page": p["page"], "kind": p.get("kind"), "flags": p.get("flags") or [],
                        "text": p["text"][:400]})
    return out[:6]


# ---------------------------------------------------------------- definition -> execution: independent numeric check

def example_path(rows=420):
    """A deterministic, hand-checkable price path (two securities) for worked examples."""
    import numpy as np
    t = np.arange(rows)
    return {"a": [round(100 * float(np.exp(0.0006 * k + 0.04 * np.sin(k / 11.0))), 6) for k in t],
            "b": [round(50 * float(np.exp(-0.0004 * k + 0.02 * np.cos(k / 7.0))), 6) for k in t]}


def expected_return(prices, t, *, n_rows, skip_rows=0, log=False):
    """The declared return read straight off a price list: from t-skip-n to t-skip (no IR, no pandas)."""
    import math
    a, b = prices[t - skip_rows], prices[t - skip_rows - n_rows]
    return math.log(a / b) if log else a / b - 1.0


def check_return_derivations(fac, symbol_map, rows_per_period, freq):
    """For every return symbol: the declared semantics (window, skip, compounding, unit conversion) computed by hand on a
    constructed path must equal the executed derivation. Returns (conflicts, worked_examples)."""
    import pandas as pd
    from paper_research.factor_ir import parse_formula
    from paper_research.task import _scale_time
    from paper_agent.trusted_ir import evaluate
    path = example_path()
    idx = pd.bdate_range("2020-01-02", periods=len(path["a"]))
    panels = {"close": pd.DataFrame(path, index=idx)}
    for f in ("open", "high", "low"):
        panels[f] = panels["close"]
    conflicts, examples = [], []
    unit_rows = {"daily": 1, "weekly": 5, "monthly": 21, "quarterly": 63, "annual": 252}
    for s in fac.get("symbols") or []:
        kind, name = s.get("kind"), s["symbol"]
        m = (symbol_map or {}).get(name) or {}
        if kind not in ("cumulative_return", "period_return") or not m.get("derive"):
            continue
        rows = rows_per_period or 1
        per = unit_rows.get(freq or "daily", 1)
        def to_rows(win):
            if not win:
                return 0
            return int(round(win["n"] * PERIOD_ROWS.get(win.get("unit") or "day", 1) / per)) * rows
        n_rows = to_rows(s.get("window")) if kind == "cumulative_return" else rows
        skip_rows = to_rows(s.get("skip")) if kind == "cumulative_return" else 0
        log = (s.get("compounding") == "log") or bool(re.search(r"\blog|对数", s.get("meaning") or "", re.I))
        ir = parse_formula(m["derive"])["ir"]
        if rows > 1:
            ir = _scale_time(ir, rows)
        letters = {n["symbol"] for n in walk(ir) if n["op"] == "field"}
        field = {"C": "close", "O": "open", "H": "high", "L": "low"}
        got = evaluate(ir, panels, {x: field.get(x, "close") for x in letters})
        t = len(idx) - 1
        want = expected_return(path["a"], t, n_rows=n_rows, skip_rows=skip_rows, log=log)
        val = float(got["a"].iloc[t])
        ok = abs(val - want) <= 1e-12 * max(1.0, abs(want))
        examples.append({"symbol": name, "date_row": t, "n_rows": n_rows, "skip_rows": skip_rows, "compounding": "log" if log else "simple",
                         "price_t_minus_skip": path["a"][t - skip_rows], "price_window_start": path["a"][t - skip_rows - n_rows],
                         "declared_value": want, "executed_value": val, "match": ok})
        if not ok:
            conflicts.append({"code": "DERIVATION_DIFFERS_FROM_DECLARATION", "symbol": name, "blocking": True,
                              "detail": f"{name}: 按声明（回看{n_rows}行、跳过{skip_rows}行、{'对数' if log else '简单'}）应为 {want:.10f}，"
                                        f"执行公式得到 {val:.10f}"})
    return conflicts, examples


# ---------------------------------------------------------------- time axis (program-written, shown to the user)

def timeline(ir, names=None, rows_per_period=None):
    """Plain-Chinese description of what each part of the executed IR reads on the daily time axis."""
    names = names or {}
    lines = []

    def nm(sym):
        return names.get(sym, sym)

    def ratio(node):
        if node["op"] == "div" and all(a["op"] == "field" for a in node["args"]):
            a, b = node["args"]
            if a["symbol"] == b["symbol"] and not a["lag"].get("var") and not b["lag"].get("var") and a["lag"]["base"] < b["lag"]["base"]:
                return nm(a["symbol"]), a["lag"]["base"], b["lag"]["base"]
        return None

    def visit(node):
        r = ratio(node["args"][0]) if node["op"] == "sub" and node["args"][1] == {"op": "const", "value": 1.0} else None
        if r:
            sym, a, b = r
            lines.append(f"{sym}从 t−{b} 到 t−{a} 的累计简单收益：回看 {b - a} 个交易日" + (f"，跳过最近 {a} 个交易日" if a else "，截至 t"))
            return
        if node["op"] == "log" and ratio(node["args"][0]):
            sym, a, b = ratio(node["args"][0])
            lines.append(f"{sym}从 t−{b} 到 t−{a} 的累计对数收益：回看 {b - a} 个交易日" + (f"，跳过最近 {a} 个交易日" if a else ""))
            return
        if node["op"] in TS_OPS:
            what = {"ts_mean": "均值", "ts_sum": "求和", "ts_std": "标准差", "ts_max": "最大值", "ts_min": "最小值",
                    "ts_prod": "连乘", "ts_rank": "最新值在窗口内的百分位排名", "ts_corr": "相关系数", "ts_cov": "协方差"}[node["op"]]
            inputs = sorted({nm(n["symbol"]) for a in node["args"] for n in walk(a) if n["op"] == "field"})
            lines.append(f"窗口 {what}：对 t−{node['end']} 至 t−{node['start']} 共 {node['end'] - node['start'] + 1} 个交易日的"
                         f"{'、'.join(inputs)} 计算（窗口内每一天都必须有有效值）")
        elif node["op"] == "ema":
            inputs = sorted({nm(n["symbol"]) for n in walk(node) if n["op"] == "field"})
            label = {"span": f"EMA(N={node['n']}, α=2/(N+1))", "wilder": f"Wilder/RMA(N={node['n']}, α=1/N)",
                     "ratio": f"SMA(N={node['n']}, M={node['m']}, α=M/N)"}[node["smoothing"]]
            lines.append(f"指数平滑 {label} 作用于 {'、'.join(inputs)}：α={node['alpha']:.4f}，只用最近 W={node['window']} 个交易日"
                         f"（种子={'窗口首值' if node['init'] == 'first' else '前N日均值'}，截断残余权重 {node['seed_weight']:.2e}）")
        elif node["op"] == "field" and node["lag"]["base"] > 0 and not node["lag"].get("var"):
            lines.append(f"{nm(node['symbol'])} 在 t−{node['lag']['base']} 的单日值（只取这一天，不是回看区间）")
        for a in node.get("args", []):
            if node["op"] not in TS_OPS:
                visit(a)
    visit(ir)
    seen, out = set(), []
    for x in lines:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
