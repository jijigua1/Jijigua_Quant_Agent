"""extract_research_spec: rule-based, evidence-grounded research specification (no LLM).

Output separates
  A  supported      verbatim sentences found in the document, each with a source location
  B  deductions     inferences or implementation proposals, each citing its basis; never facts
  C  missing        required items not found, phrased as questions
plus ambiguities, integrity-risk checks, formulas, tables and security findings.
Nothing absent is filled with a default.
"""
from __future__ import annotations

import hashlib
import json
import re

from .common import sentences
from .numbers import find_numbers

SPEC_SCHEMA = "paper_research.spec/1.0"
EXTRACTOR = {"name": "paper_research.rule_extractor", "version": "0.3.0",
             "method": "keyword and pattern matching over parsed blocks; no language model"}

NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|sixty)"
ZHN = r"(\d+|[一二三四五六七八九十百]+)"
MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)"

FIELDS = {
    "research_objective": [r"\b(we|this (paper|study|article))\s+(propose|investigate|examine|study|show|document|test|explore|introduce|develop|find)\b",
                           r"本文(提出|研究|考察|检验|构建|探讨|发现)"],
    "economic_intuition": [r"\b(intuition|rationale|overreact\w*|underreact\w*|mispricing|risk premium|compensat\w+ for|behavioral|limits to arbitrage|liquidity provision|explanation)\b",
                           r"(直觉|逻辑在于|原因在于|过度反应|反应不足|错误定价|风险溢价|补偿)"],
    "factor_definition": [r"\b(is defined (here )?as|we define|is computed as|is calculated as|is measured as|is constructed as|we construct|we measure|we compute|"
                          r"(are|is) (ranked|sorted) (based )?on|based on the ratio of|ranked (by|according to))\b",
                          r"(定义为|计算方式|计算公式|构造方法|构建方法|计算为|定义如下)"],
    "frequency": [r"\b(daily|weekly|monthly|quarterly|annual|intraday|minute-level|high-frequency)\s+(\w+\s+)?(data|returns?|frequency|rebalanc\w*|observations?|sample|horizon|prices?)\b",
                  r"(日频|周频|月频|季频|年频|分钟级|高频)"],
    "lookback": [rf"\b(past|previous|prior|trailing|preceding|rolling|last)\s+{NUM}[- ]?(trading[- ])?(days?|weeks?|months?|quarters?|years?)\b",
                 rf"\b{NUM}[- ](trading[- ])?(day|week|month|year)s?\s+(window|lookback|look-back|formation|estimation|rolling)\b",
                 rf"(过去|前|滚动|最近)\s*{ZHN}\s*(个)?(交易日|日|天|周|个月|月|季度|年)"],
    "universe": [r"\b(NYSE|AMEX|NASDAQ|CRSP|common stocks?|share codes?|S&P\s?500|Russell\s?\d+|CSI\s?\d{3,4}|A-shares?|Chinese (stock|equity)|all (listed )?stocks|listed (firms|companies|stocks)|stock universe)\b",
                 r"(A股|沪深|全市场|中证\s?\d{3,4}|沪深\s?300|上市公司|股票池|样本股)"],
    "sample_selection": [r"\b(exclud\w+|drop\w*|remov\w+|filter\w*|eliminat\w+)\b.{0,80}\b(stocks?|firms?|financials?|penny|price|ST\b|observations|IPOs?|listed|utilities)\b|"
                         r"\b(admitted|included|eligible)\b.{0,60}\b(if|only if|provided)\b|\bsatisfy the following criteria\b|"
                         r"\bprice is (greater|higher|more) than \$?\d|\b(more|fewer|less) than \d+ (trading )?days\b",
                         r"(剔除|排除|删除|去除|过滤).{0,30}(ST|上市|停牌|金融|次新|价格|样本|涨跌停)"],
    "preprocessing": [r"\b(winsoriz\w+|truncat\w+ at|standardiz\w+|z-scores?|normaliz\w+|neutraliz\w+|cross-sectional(ly)? (rank\w*|demean\w*)|missing values?|outliers?)\b",
                      r"(缩尾|去极值|标准化|中性化|归一化|缺失值|填充|异常值)"],
    "signal_timing": [r"\b(at the end of (each|every) (month|week|day|quarter|year)|end of (each )?month|formation (date|period)|skip(ping)? (the )?(most recent|last|first)|skip(ping)? (a|one) month|known to investors|at the beginning of (each |the )?(year|month|week)|observ\w+ at|available (at|to investors)|known at|before the (open|close)|at the close)\b",
                      r"(月末|周末|收盘后|开盘前|每月(底|初)|调仓日|信号.{0,6}(时点|时间)|跳过)"],
    "holding_horizon": [r"\b(holding period|held for|hold\w* (them |the portfolios? )?for|next (month|week|day|quarter)('s)? returns?|(over|in|during) the next \d+ (trading )?(days?|weeks?|months?)|subsequent (month|week|day)\w*|future returns?|forecast horizon|\d+[- ](day|month)s?[- ]ahead|rebalanc\w+ (monthly|weekly|daily|quarterly))\b",
                        r"(持有期|持有\s*\d+|下(个)?月收益|未来\s*\d*\s*(个)?(交易日|日|周|月)|预测期|调仓频率)"],
    "portfolio_construction": [r"\b(deciles?|quintiles?|terciles?|portfolios? (sorted|formed)|sorted into|long[- ]short|long the|short the|value[- ]weighted|equal(ly)?[- ]weighted|hedge portfolio|zero-cost|top \d+|bottom \d+)\b",
                               r"(分组|十分位|五分位|多空|做多|做空|等权|市值加权|组合构建)"],
    "costs_execution": [r"\b(transaction costs?|trading costs?|bid-ask|slippage|commissions?|basis points|bps|market impact|execution (price|cost))\b",
                        r"(交易成本|手续费|佣金|滑点|冲击成本|印花税|成交价)"],
    "evaluation_metrics": [r"\b(information coefficients?|rank ?IC|ICIR|IC\b|sharpe ratios?|alphas?\b|t-stat\w*|Fama( and |[- –])MacBeth|information ratios?|out-of-sample R|R2\b|R-squared|maximum drawdown|annuali[sz]ed returns?)",
                           r"(信息系数|RankIC|ICIR|夏普|阿尔法|t值|最大回撤|年化收益|信息比率)"],
    "sample_periods": [rf"\b(from|between|over)\s+({MONTHS}\s+)?(19|20)\d{{2}}\s+(to|and|through|until)\s+({MONTHS}\s+)?(19|20)\d{{2}}\b",
                       r"\b(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}\b",
                       r"\b(in-sample|out-of-sample|training (period|sample|set|window)|validation (period|sample|set)|test(ing)? (period|sample|set)|hold-?out)\b",
                       r"((19|20)\d{2}\s*年.{0,12}(至|到|—|-)\s*(19|20)\d{2}\s*年|训练集|验证集|测试集|样本内|样本外)"],
    "evaluation_design": [r"\b(in-sample|out-of-sample|training (period|sample|set|window)|validation (period|sample|set)|"
                          r"test(ing)? (period|sample|set)|hold-?out|rolling (window|estimation)|expanding window|cross-validat\w+|walk-forward)\b",
                          r"(训练集|验证集|测试集|样本内|样本外|滚动窗口|扩展窗口|交叉验证)"],
    "reported_results": [r"\b(average|mean|annuali[sz]ed|monthly|daily)?\s*(returns?|profits?|spread|RankIC|rank IC|IC|ICIR|Sharpe ratio|alpha|t-stat\w*|R2|R-squared)\b[^.]{0,80}?(-?\d+\.\d+|-?\d+(\.\d+)?\s?%)",
                         r"(平均|年化|月度)?(收益|RankIC|IC|ICIR|夏普|阿尔法|t值)[^。]{0,30}?(-?\d+\.\d+|-?\d+(\.\d+)?\s?%)"],
    "limitations": [r"\b(limitations?|caveats?|we do not (consider|account|model)|does not account|future research|beyond the scope|cannot rule out|interpreted with caution)\b",
                    r"(局限|不足之处|未考虑|有待进一步|未来研究|需谨慎)"],
}
REQUIRED = ["research_objective", "factor_definition", "data_fields", "frequency", "lookback", "universe",
            "signal_timing", "holding_horizon", "evaluation_metrics", "sample_periods"]
OPTIONAL_REPORTED = ["economic_intuition", "sample_selection", "preprocessing", "portfolio_construction",
                     "costs_execution", "limitations", "evaluation_design", "reported_results"]
QUESTIONS = {
    "research_objective": "What question does the paper answer?",
    "factor_definition": "How exactly is the factor computed (formula and inputs)?",
    "data_fields": "Which raw data fields are required?",
    "frequency": "At what data frequency is the factor computed and rebalanced?",
    "lookback": "What lookback/formation window is used?",
    "universe": "Which securities form the universe?",
    "signal_timing": "When is the signal observable relative to the trade (e.g. end of month t, skip a month)?",
    "holding_horizon": "What is the prediction or holding horizon?",
    "evaluation_metrics": "How is performance evaluated (IC, portfolio returns, Sharpe, t-stats)?",
    "sample_periods": "What are the sample period and any training/validation/test splits?",
    "economic_intuition": "Why should the factor predict returns?",
    "sample_selection": "Which stocks or observations are excluded?",
    "preprocessing": "How are outliers, missing values and scaling handled?",
    "portfolio_construction": "How are portfolios formed and weighted?",
    "costs_execution": "Are transaction costs and execution prices specified?",
    "limitations": "What limitations do the authors report?",
    "evaluation_design": "How are training, validation and out-of-sample periods separated?",
    "reported_results": "Which numerical results does the paper report for the factor?",
}

PREPROCESS_TAGS = {
    "winsorize": r"winsoriz|truncat\w* at|缩尾|去极值",
    "standardize_zscore": r"standardiz|z-score|标准化",
    "cross_sectional_rank": r"cross-sectional(ly)? rank|rank-transform|percentile rank|排序|分位数",
    "neutralize_industry": r"industry[- ]neutral|neutraliz\w+[^.]{0,40}industr|行业中性",
    "neutralize_size": r"size[- ]neutral|neutraliz\w+[^.]{0,40}(size|market cap)|市值中性",
    "missing_values": r"missing values?|缺失值|填充",
    "outliers": r"outliers?|异常值",
}
SPLIT_ROLES = [("validation", r"validat\w*|验证"), ("out_of_sample", r"out-of-sample|\btest\w*|hold-?out|样本外|测试"),
               ("in_sample", r"in-sample|\btrain\w*|estimation (period|sample|window)|训练|样本内")]
YEARS = re.compile(r"((?:19|20)\d{2})\s*(?:[-–—]|to|through|until|至|到)\s*((?:19|20)\d{2})")
# metric words must stand alone ("which" is not IC); acronyms are case-sensitive
METRIC = re.compile(r"(?<![A-Za-z])(?:(?-i:RankIC|ICIR|IC|R2)|rank IC|Sharpe ratios?|information ratios?|alphas?|t-stat\w*|"
                    r"R-squared|returns?|profits?|spreads?|premi(?:um|a)|夏普|阿尔法|t值|收益率?|超额收益)(?![A-Za-z])", re.I)
METRIC_NORM = [("rank_ic", r"rank ?ic"), ("icir", r"^icir$"), ("ic", r"^ic$"), ("sharpe", r"sharpe|夏普"),
               ("t_stat", r"t-stat|t值"), ("alpha", r"alpha|阿尔法"), ("r2", r"^r2$|r-squared"),
               ("information_ratio", r"information ratio"), ("return", r"return|profit|spread|premi|收益")]
PORTFOLIO_BEFORE = re.compile(r"(top|bottom|highest|lowest|first|last)\s*$", re.I)
PORTFOLIO_AFTER = re.compile(r"^\s*(of (the )?(stocks|firms|shares|sample|observations|market|universe|top|bottom|highest|lowest)\b|percentile|quantile|"
                             r"(is|are|was|were) (assigned|set|used|imposed|applied|included|substituted))", re.I)


CITATION = re.compile(r"\([A-Z][A-Za-z’'\-]+(?: et al\.?| and [A-Z][A-Za-z’'\-]+)?,? (?:19|20)\d{2}[a-z]?[;)]|\bsee [A-Z][a-z]+|"
                      r"[A-Z][a-z]+(?: et al\.| and [A-Z][a-z]+)? \((?:19|20)\d{2}\)")


def _metric_norm(word, before=""):
    w = word.lower()
    if w.startswith("spread") and re.search(r"(bid[-–]ask|quoted|effective|买卖)\s*$", before.lower()):
        return "bid_ask_spread"                        # a trading-cost measure, not a return spread
    return next((k for k, pat in METRIC_NORM if re.search(pat, w)), "unknown")


def _parse_splits(text):
    """Role -> (start_year, end_year) for each year range attached to a split keyword in one sentence."""
    out = []
    for m in YEARS.finditer(text):
        before, after = text[max(0, m.start() - 60):m.start()], text[m.end():m.end() + 40]
        # the role keyword closest before the range wins; only if none precedes it, look just after it.
        # neighbouring year ranges cut the search window so a keyword is not reused across ranges
        before = re.split(r"(?:19|20)\d{2}", before)[-1]
        after = re.split(r"(?:19|20)\d{2}", after)[0]
        hits = [(len(before) - mm.end(), r) for r, pat in SPLIT_ROLES for mm in re.finditer(pat, before, re.I)]
        if not hits:                                   # "keep 2016-2020 as the test period"
            hits = [(mm.start(), r) for r, pat in SPLIT_ROLES for mm in re.finditer(pat, after, re.I)]
        role = min(hits)[1] if hits else None
        out.append({"role": role or "unlabelled", "start_year": int(m.group(1)), "end_year": int(m.group(2)),
                    "text": m.group(0)})
    return out


def _parse_results(text):
    """One record per reported number: verbatim token (checked by the validator), signed value, unit, the metric word
    nearest before it in the sentence, the t-statistic printed after it in parentheses, and a review flag. A number
    whose metric cannot be tied to it is kept but marked needs_review; portfolio parameters ("top 30%") are skipped."""
    out = []
    cited = bool(CITATION.search(text))                # numbers attributed to other studies are not the paper's results
    nums = list(find_numbers(text, decimals_only=True))
    for idx, (s, e, p) in enumerate(nums):
        if p["parenthesized"] and p["unit"] is None:
            if out and 0 <= s - out[-1]["_end"] <= 4:
                out[-1]["t_stat"] = p["text"]              # "0.46% (2.15)"
            continue
        if PORTFOLIO_BEFORE.search(text[max(0, s - 12):s]) or PORTFOLIO_AFTER.search(text[e:e + 30]):
            continue
        before = list(METRIC.finditer(text[:s]))
        m = before[-1] if before else None
        dist = s - m.end() if m else None
        inherited = False
        if (m is None or dist > 80) and out and s - out[-1]["_end"] <= 100 and out[-1]["metric"] and out[-1]["review"] == "auto_parsed" and \
                re.search(r"\b(than|versus|vs\.?|and|compared (with|to)|or)\b", text[out[-1]["_end"]:s]):
            m, dist, inherited = out[-1]["_m"], 0, True     # "0.65% ..., which is much greater than 0.38% for JT"
        unit, inferred = p["unit"], False
        if unit is None and idx + 1 < len(nums) and nums[idx + 1][2]["unit"] == "%" and \
                re.fullmatch(r"\s*(to|and|-|–|—|versus|vs\.?)\s*", text[e:nums[idx + 1][0]]):
            unit, inferred = "%", True                     # "from 0.48 to 1.07%"
        subject = re.match(r"\s*(?:per (?:month|year|annum)\s*)?(?:for|of|to)\s+([A-Z][\w’'\-]*(?:\s[\w’'\-]+){0,3}?)(?=[\s,.;)]|$)", text[e:])
        if p.get("sign_unresolved"):
            out.append({"metric": m.group(0) if m else None, "metric_normalized": _metric_norm(m.group(0)) if m else "unknown",
                        "value": p["text"], "number": None, "unit": p["unit"], "sign_unresolved": True, "_end": e, "_m": m,
                        "review": "needs_review", "review_reason": "sign glyph not decoded by the PDF text layer",
                        "verification": "unverified"})
            continue
        rec = {"metric": m.group(0) if m else None,
               "metric_normalized": _metric_norm(m.group(0), text[max(0, m.start() - 12):m.start()]) if m else "unknown",
               "value": p["text"], "number": p["value"], "unit": unit, "unit_inferred": inferred,
               "negative": p["negative"], "subject_hint": subject.group(1) if subject else None, "_end": e, "_m": m,
               "metric_basis": "inherited_from_previous_number" if inherited else ("nearest_preceding_word" if m else None),
               "review": "auto_parsed" if m is not None and dist <= 80 else "needs_review",
               "verification": "unverified"}
        if rec["review"] == "needs_review":
            rec["review_reason"] = "no metric word within 80 characters before the number"
        if cited:
            rec.update(attribution="cited_literature", review="needs_review",
                       review_reason="the sentence cites another study; the number may not be this paper's result")
        out.append(rec)
    for r in out:
        r.pop("_end", None)
        r.pop("_m", None)
    return out


TABLE_METRIC = [("regression_coefficient", r"regress|coefficient|intercept|fama[–-]macbeth"),
                ("return", r"returns?|profits?|premi"), ("ic", r"information coefficient|\bIC\b"), ("sharpe", r"sharpe")]


def _table_results(doc):
    """Cells of text-layout tables with the metric semantics the caption states; never marked verified."""
    out = []
    for b in doc["blocks"]:
        if b["kind"] != "table" or not b["data"].get("cells"):
            continue
        cap = (b["data"].get("caption") or "") + " " + (b["data"].get("caption_context") or "")
        metric = next((k for k, pat in TABLE_METRIC if re.search(pat, cap, re.I)), "unknown")
        paren = "t_stat" if re.search(r"t-?statistics?\s*\(?(are )?(reported )?in parentheses|parentheses.{0,30}t-?stat", cap, re.I) else "unknown"
        for c in b["data"]["cells"]:
            kind = c["kind"]
            sem = paren if kind == "statistic_in_parentheses" else metric
            ok = (b["data"].get("reliability") == "structured" and sem != "unknown" and not c["column"].startswith("col")
                  and c["value"] is not None and not c.get("sign_unresolved"))
            out.append({"table_block": b["id"], "table_number": b["data"].get("number"), "page": b["page"],
                        "panel": c["panel"], "row": c["row"], "column": c["column"], "value": c["text"],
                        "number": c["value"], "unit": c["unit"], "kind": kind, "metric_normalized": sem,
                        "bbox": c["bbox"], "verification": "unverified_layout_parse",
                        "review": "auto_parsed" if ok else "needs_review"})
    return out

DATA_FIELDS = {
    "price": r"\b(prices?|closing price|close price|open price)\b|收盘价|开盘价|价格",
    "returns": r"\b(returns?)\b|收益率",
    "volume": r"\b(trading volume|volume)\b|成交量",
    "turnover": r"\bturnover\b|换手率",
    "market_capitalization": r"\b(market cap\w*|market value of equity|size|ME)\b|市值",
    "shares_outstanding": r"\bshares outstanding\b|流通股|总股本",
    "book_equity": r"\b(book equity|book value|book-to-market|B/M)\b|账面价值|净资产|市净率",
    "earnings": r"\b(earnings|net income|EPS)\b|净利润|每股收益",
    "sales": r"\b(sales|revenue)\b|营业收入|营收",
    "total_assets": r"\btotal assets\b|总资产",
    "dividends": r"\bdividends?\b|分红|股息",
    "analyst_forecasts": r"\b(analyst forecasts?|IBES|consensus)\b|分析师预测",
    "risk_free_rate": r"\b(risk-free rate|T-bill)\b|无风险利率",
    "bid_ask": r"\b(bid-ask|quotes?)\b|买卖价差",
    "industry": r"\b(industry classification|SIC|GICS)\b|行业分类",
    "macro_predictors": r"\b(dividend yield|term spread|default spread|inflation|macroeconomic)\b|宏观",
}
FUNDAMENTAL = {"book_equity", "earnings", "sales", "total_assets", "dividends", "analyst_forecasts"}

RISKS = {
    "future_information_leakage": (r"\b(look-ahead|lookahead|future information|point-in-time|ex ante|real[- ]time|out-of-sample)\b|未来信息|前视|样本外",
                                   "Is every input known at the signal time (no look-ahead)?"),
    "survivorship_bias": (r"\b(survivorship|delist\w*|dead stocks|inactive firms)\b|幸存者|退市",
                          "Does the sample include delisted securities and delisting returns?"),
    "corporate_actions": (r"\b(adjusted for (splits|dividends)|split-adjusted|corporate actions?|dividend-adjusted|total returns?)\b|复权|除权|除息",
                          "Are prices adjusted for splits/dividends, and which adjustment is used?"),
    "fundamental_reporting_lag": (r"\b(reporting lag|announcement date|fiscal year[- ]end|publicly available|six[- ]month lag|lagged by \w+ months)\b|公告日|披露日|财报发布",
                                  "With what lag do fundamental data become available?"),
    "label_alignment": (r"\b(next month('s)? return|subsequent (month|period)|skip(ping)? (a|one|the most recent) month|t\s*\+\s*1|one-month gap)\b|下(个)?月收益|次日|跳过",
                        "How is the prediction target aligned with the signal date?"),
    "parameter_selection": (r"\b(grid search|tun(ed|ing)|cross-validat\w+|chosen to maximi[sz]e|optimal (window|parameter)|data[- ]snooping|data[- ]mining|hyperparameters?)\b|参数优化|网格搜索|调参|数据挖掘",
                            "Were parameters chosen on the evaluation sample (selection bias)?"),
}


def _excluded(block) -> bool:
    return (block["kind"] not in ("paragraph", "caption") or "injection_suspect" in block["flags"]
            or "hidden_text" in block["flags"] or block["confidence"] in ("none",))


def _loc(doc, block, s, e):
    return {"doc_id": doc["doc_id"], "block_id": block["id"], "page": block["page"], "section": block["section"],
            "line": block["line"], "char_start": s, "char_end": e}


def _sentence_index(doc):
    out = []
    for b in doc["blocks"]:
        if _excluded(b):
            continue
        for s, e, text in sentences(b["text"]):
            out.append((b, s, e, text))
    return out


def _item(doc, field, b, s, e, text, matched, **extra):
    quote = text if len(text) <= 400 else text[:400]
    return {"field": field, "status": "supported", "value": quote, "matched": matched,
            "evidence": [{"location": _loc(doc, b, s, s + len(quote)), "quote": quote}],
            "confidence": "medium" if b["confidence"] == "high" else "low", **extra}


WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "sixty": 60}
ZHNUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num(tok):
    if tok.isdigit():
        return int(tok)
    if tok in WORDNUM:
        return WORDNUM[tok]
    if all(c in ZHNUM or c == "十" for c in tok):
        if tok == "十":
            return 10
        if "十" in tok:
            a, _, b = tok.partition("十")
            return (ZHNUM.get(a, 1)) * 10 + (ZHNUM.get(b, 0))
        return ZHNUM.get(tok)
    return None


def _parse_window(m: re.Match):
    txt = m.group(0).lower()
    n = next((v for v in (_num(t) for t in re.findall(r"\d+|[a-z]+|[一二三四五六七八九十百]+", txt)) if v), None)
    unit = next((u for k, u in (("trading day", "trading_day"), ("交易日", "trading_day"), ("day", "day"), ("日", "day"),
                                ("天", "day"), ("week", "week"), ("周", "week"), ("month", "month"), ("月", "month"),
                                ("quarter", "quarter"), ("季度", "quarter"), ("year", "year"), ("年", "year")) if k in txt), None)
    return {"n": n, "unit": unit} if n and unit else None


def extract_research_spec(doc: dict, max_items_per_field: int = 40) -> dict:
    """Build the A/B/C research specification from an ingested document."""
    idx = _sentence_index(doc)
    A, B, C, amb = {}, [], [], []
    for field, pats in FIELDS.items():
        rx = [re.compile(p, re.I) for p in pats]
        items = []
        for b, s, e, text in idx:
            m = next((r.search(text) for r in rx if r.search(text)), None)
            if not m:
                continue
            text = text[:400]                          # parse only what the quote (<= 400 chars) contains
            extra = {}
            if field in ("lookback",):
                w = _parse_window(m)
                if w:
                    extra["parsed"] = w
            if field == "holding_horizon":
                # a period that names a price level ("52-week high") is not a horizon
                w = next((x for x in re.finditer(rf"{NUM}[- ]?(trading[- ])?(days?|weeks?|months?)|(next|subsequent)\s+(day|week|month)|"
                                                 rf"未来\s*{ZHN}\s*(个)?(交易日|日|天|周|个月|月)", text, re.I)
                          if not re.match(r"[- ]?(high|low)s?\b|[- ]?最(高|低)", text[x.end():], re.I)), None)
                if w:
                    pw = _parse_window(w) or ({"n": 1, "unit": w.group(0).split()[-1].rstrip("s").lower()} if w.group(0).lower().startswith(("next", "subsequent")) else None)
                    if pw:
                        extra["parsed"] = pw
            if field == "preprocessing":
                extra["methods"] = [k for k, pat in PREPROCESS_TAGS.items() if re.search(pat, text, re.I)]
            if field in ("evaluation_design", "sample_periods"):
                sp = _parse_splits(text)
                if sp:
                    extra["splits"] = sp
            if field == "reported_results":
                rs = _parse_results(text)
                if not rs:
                    continue
                extra["results"] = rs
            items.append(_item(doc, field, b, s, e, text, m.group(0), **extra))
            if len(items) >= max_items_per_field:
                break
        if items:
            A[field] = items
    # data fields: dictionary of named inputs, each with its first supporting sentence
    found = []
    for name, pat in DATA_FIELDS.items():
        r = re.compile(pat, re.I)
        # "adjusted for splits and dividends" describes price adjustment, not a dividend input
        hit = next(((b, s, e, t, r.search(t)) for b, s, e, t in idx if r.search(t)
                    and not (name == "dividends" and re.search(r"adjust|复权", t, re.I))), None)
        if hit:
            b, s, e, t, m = hit
            found.append(_item(doc, "data_fields", b, s, e, t, m.group(0), data_field=name))
    if found:
        A["data_fields"] = found

    # ambiguity: several different lookback windows mentioned
    wins = {(i["parsed"]["n"], i["parsed"]["unit"]) for i in A.get("lookback", []) if "parsed" in i}
    if len(wins) > 1:
        amb.append({"topic": "lookback", "detail": f"several windows mentioned: {sorted(wins, key=str)}",
                    "evidence": [ev for i in A["lookback"] for ev in i["evidence"]],
                    "question": "Which window defines the main factor, and which are robustness variants?"})

    hz = {(i["parsed"]["n"], i["parsed"]["unit"]) for i in A.get("holding_horizon", []) if "parsed" in i}
    if len(hz) > 1:
        amb.append({"topic": "holding_horizon", "detail": f"several horizons mentioned: {sorted(hz, key=str)}",
                    "evidence": [ev for i in A["holding_horizon"] for ev in i["evidence"]],
                    "question": "Which horizon defines the prediction target?"})
    roles = {}
    for i in A.get("evaluation_design", []) + A.get("sample_periods", []):
        for sp in i.get("splits", []):
            roles.setdefault(sp["role"], set()).add((sp["start_year"], sp["end_year"]))
    if any(len(v) > 1 for k, v in roles.items() if k != "unlabelled"):
        amb.append({"topic": "evaluation_design", "detail": f"conflicting split years: { {k: sorted(v) for k, v in roles.items()} }",
                    "evidence": [ev for i in A.get("evaluation_design", []) for ev in i["evidence"]],
                    "question": "Which period boundaries define training, validation and test?"})

    formulas = doc["formulas"]
    for f in formulas:
        for lag in sorted({int(x) for x in re.findall(r"t\s*[-−]\s*(\d+)", f["readable"])}):
            B.append({"type": "deduction", "statement": f"formula {f['id']} references period t-{lag}: the computation "
                      f"needs at least {lag} past periods of data", "basis": [{"formula_id": f["id"], "block_id": f["block_id"],
                      "page": f["page"]}], "requires_confirmation": True})
        if f["undefined_variables"] and f["status"] != "unresolved":
            C.append({"item": f"definition of {', '.join(f['undefined_variables'])} in {f['id']}",
                      "question": f"What do {', '.join(f['undefined_variables'])} denote in formula {f['id']} "
                                  f"(page {f['page']})?", "related": [f["id"]]})
        if f["status"] == "unresolved":
            region = f.get("layout", {}).get("regions")
            C.append({"item": f"formula {f['id']} unreadable", "code": "FORMULA_UNRESOLVED", "page": f["page"], "region": region,
                      "question": f"Read formula {f['id']} on page {f['page']}" + (f" (region {region})" if region else "") +
                      " of the original document; the extracted text is not reliable.", "related": [f["id"]]})
    # safety net: a definition cue that ends a block with no formula after it (a formula lost by the text layer)
    blocks = doc["blocks"]
    for i, b in enumerate(blocks[:-1]):
        if b["kind"] == "paragraph" and re.search(r"\b((are|is) (ranked|sorted) (based )?on|defined as|computed as|calculated as|given by|as follows)\s*:?\s*$", b["text"], re.I):
            nxt = blocks[i + 1]
            if nxt["kind"] != "formula" and not b["data"].get("layout_math"):
                C.append({"item": f"formula after block {b['id']}", "code": "FORMULA_UNRESOLVED", "page": b["page"], "region": b["bbox"],
                          "question": f"Block {b['id']} (page {b['page']}) ends with a definition cue but no formula follows; "
                                      "the formula was probably lost by the PDF text layer. Read the page.", "related": []})

    for field in REQUIRED:
        if field not in A:
            C.append({"item": field, "question": QUESTIONS[field], "related": []})
    for field in OPTIONAL_REPORTED:
        if field not in A:
            C.append({"item": field, "question": QUESTIONS[field] + " (not found in the document)", "related": [], "optional": True})

    risks = []
    for risk, (pat, q) in RISKS.items():
        r = re.compile(pat, re.I)
        ev = [_item(doc, risk, b, s, e, t, r.search(t).group(0))["evidence"][0] for b, s, e, t in idx if r.search(t)][:3]
        risks.append({"risk": risk, "status": "mentioned_in_source" if ev else "not_mentioned", "evidence": ev,
                      "question": q, "note": "a mention is not proof that the issue is handled"})
    fundamentals = [i["data_field"] for i in A.get("data_fields", []) if i["data_field"] in FUNDAMENTAL]
    lag_risk = next(r for r in risks if r["risk"] == "fundamental_reporting_lag")
    if fundamentals and lag_risk["status"] == "not_mentioned":
        C.append({"item": "fundamental data reporting lag", "related": [],
                  "question": f"Fundamental inputs ({', '.join(fundamentals)}) are used but no availability lag is stated: "
                              "when does each become known?"})
        B.append({"type": "proposal", "statement": "Use point-in-time fundamentals keyed by announcement date; the lag "
                  "itself must be chosen and documented by the researcher (no value is assumed here).",
                  "basis": [{"risk": "fundamental_reporting_lag"}], "requires_confirmation": True})
    if "signal_timing" not in A:
        B.append({"type": "proposal", "statement": "If the paper is silent on timing, a conservative implementation computes "
                  "the signal after the close of t and trades at the next session (qrtk NEXT_OPEN); this is a proposal, "
                  "not the paper's method.", "basis": [{"missing": "signal_timing"}], "requires_confirmation": True})

    # factor candidates: acronyms introduced in parentheses next to a factor cue or used as a
    # formula's left-hand side, Chinese "X因子" names, and formula outputs without a textual name
    cue = re.compile(r"(factor|signal|anomaly|measure|volatility|momentum|reversal|ratio|liquidity|size|value|"
                     r"beta|return|turnover|skewness|因子)", re.I)
    acr = re.compile(r"((?:[A-Za-z0-9][\w'-]*[\s-]+){0,4}?)\(([A-Z][A-Z0-9_]{1,10})\)")
    outs = {f["output_symbol"] for f in formulas if f["output_symbol"]}
    cands = {}
    for b, s, e, t in idx:
        for m in acr.finditer(t):
            ab, pre = m.group(2), m.group(1).strip()
            if ab in outs or cue.search(pre):
                name = re.sub(r"^(the|a|an|our|this|that|we|and)\s+", "", pre, flags=re.I).strip() or ab
                cands.setdefault(ab, {"name": name, "aliases": [ab], "first": (b, s, e, t)})
        for m in re.finditer(r"(?:^|[，。、；：\s（(“\"])([一-鿿]{2,6})因子", t):
            nm = m.group(1)
            if not re.search(r"[按每对将把用以的该本这所单]", nm):
                cands.setdefault(nm, {"name": nm + "因子", "aliases": [], "first": (b, s, e, t)})
    # a formula without a left-hand side inside a ranking/definition sentence names the factor of that sentence
    ctx_cue = re.compile(r"\b(ranked|sorted|ranks?|defined as|computed as|measured (as|by)|calculated as|given by|based on)\b", re.I)
    ctx_name = [re.compile(r"\b(?:for|in|of) (?:the|our|a) (?P<name>[\w\-’' ]{2,40}?) (?:strategy|strategies|portfolios?|factor|measure|signal|anomaly)\b", re.I),
                re.compile(r"(?P<name>[A-Za-z][\w\-’' ]{2,40}?) (?:is|are) (?:defined|computed|measured|calculated) as", re.I)]
    for f in formulas:
        if f["output_symbol"] or f["source_kind"] not in ("pdf_layout_fraction", "inline_latex") or f["status"] == "unresolved":
            continue
        hit = next(((b, s, e, t) for b, s, e, t in idx if b["id"] == f["block_id"] and f["raw"] in t), None)
        if hit is None:
            continue
        head = hit[3][:hit[3].find(f["raw"])]
        if not ctx_cue.search(head):
            continue
        names = [m.group("name").strip() for rx in ctx_name for m in rx.finditer(head)]
        if not names:
            continue
        nm = re.sub(r"^(the|a|an|our)\s+", "", names[-1], flags=re.I)
        if nm not in cands and not any(f["readable"] == next((g["readable"] for g in formulas if g["id"] == c.get("context_formula")), None)
                                       for c in cands.values()):
            cands[nm] = {"name": nm, "aliases": [], "first": hit, "context_formula": f["id"]}
    for sym in sorted(o for o in outs - set(cands) if len(o) >= 2 and sum(ch.isupper() for ch in o) >= 2):
        f0 = next(f for f in formulas if f["output_symbol"] == sym)
        cands[sym] = {"name": sym, "aliases": [sym], "first": None, "formula_only": f0}
    factors = []
    for key, d in cands.items():
        terms = [d["name"]] + d["aliases"]
        mentions = sum(len(re.findall(rf"(?<![A-Za-z]){re.escape(tm)}(?![A-Za-z])", t)) for _, _, _, t in idx for tm in set(terms))
        defs = [i for i in A.get("factor_definition", []) if any(tm.lower() in i["value"].lower() for tm in terms)]
        fids = [f["id"] for f in formulas if f["output_symbol"] in d["aliases"] or (not d["aliases"] and d["name"] in f["readable"])]
        if d.get("context_formula"):
            fids = [d["context_formula"]]
            defs = defs or [_item(doc, "factor_definition", *d["first"], d["name"])]
        if d["first"] is not None:
            b, s, e, t = d["first"]
            first = _item(doc, "factor", b, s, e, t, d["name"])["evidence"][0]
        else:
            first = None
        factors.append({"name": d["name"], "aliases": d["aliases"], "mentions": mentions, "first_mention": first,
                        "definition_evidence": [i["evidence"][0] for i in defs], "formula_ids": fids,
                        "status": ("formula_unresolved" if fids and not defs and all(
                            f["status"] == "unresolved" for f in formulas if f["id"] in fids)
                            else "defined_in_source" if defs or fids else "named_only")})
        if not defs and not fids:
            C.append({"item": f"definition of factor '{d['name']}'", "related": [],
                      "question": f"'{d['name']}' is named but no definition sentence or formula was linked to it."})

    tables = []
    for b in doc["blocks"]:
        if b["kind"] == "table":
            tables.append({"block_id": b["id"], "page": b["page"], "caption": b["data"]["caption"], "header": b["data"]["header"],
                           "n_rows": len(b["data"]["rows"]), "units": b["data"]["units"], "notes": b["data"]["notes"],
                           "method": b["data"].get("method", "ruled"), "reliability": b["data"].get("reliability"),
                           "issues": b["data"]["issues"], "continuation_of": b["data"]["continuation_of"],
                           "continued_in": b["data"]["continued_in"]})
    rep = doc["extraction_report"]
    quality = {"pages_unreadable": rep.get("pages_unreadable", []), "pages_low_confidence": rep.get("pages_low_confidence", []),
               "formulas_unresolved": [f["id"] for f in formulas if f["status"] == "unresolved"],
               "formulas_suspect": [f["id"] for f in formulas if f["status"] == "suspect"],
               "tables_suspect": [t["block_id"] for t in tables if t["issues"]],
               "table_captions_without_body": [b["id"] for b in doc["blocks"] if "table_body_not_detected" in b["flags"]],
               "formula_regions_unresolved": rep.get("formula_regions_unresolved", []),
               "layout_fractions_reconstructed": rep.get("layout_fractions_reconstructed", 0),
               "warnings": rep.get("warnings", [])}
    md = doc["metadata"]
    spec = {
        "schema": SPEC_SCHEMA,
        "generated_from": {"doc_id": doc["doc_id"], **doc["source"]},
        "extractor": EXTRACTOR,
        "paper": {"title": md.get("title"), "authors": md.get("authors"), "year": md.get("year"), "language": doc["language"]},
        "A_supported": A, "factors": factors, "formulas": formulas, "tables": tables, "table_results": _table_results(doc),
        "B_deductions": B, "C_missing": C, "ambiguities": amb, "integrity_risks": risks,
        "security": {"injection_findings": doc["security"]["injection_findings"],
                     "hidden_text_blocks": doc["security"]["hidden_text_blocks"],
                     "excluded_from_extraction": [b["id"] for b in doc["blocks"] if "injection_suspect" in b["flags"]
                                                  or "hidden_text" in b["flags"]]},
        "extraction_quality": quality,
        "reproduction_status": "not_reproduced",
        "disclaimer": ("Extracted by pattern matching. Supported items are verbatim quotes, not interpretations; "
                       "formulas are not executable until a human confirms them; nothing here shows the paper was reproduced."),
    }
    spec["spec_id"] = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    return spec
