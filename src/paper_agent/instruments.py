"""Which financial instrument a paper actually studies, read deterministically from the whole document.

A paper's research object decides whether the published A-share stock panel can stand in for its data. The model sees
only selected passages, so this module scans every block (references excluded) for instrument cues -- including the
indirect ones (contract months, roll-over, margin, strike, implied volatility, open interest, settlement price) and the
Chinese terms -- and scores them, with more weight on the title, the first pages and data/method sections, and on the
pages where the requested factor is defined. The result names the dominant asset classes with verbatim evidence.

Policy (applied in the planner): the published data are A-share common stocks only. A paper whose studied object is
futures, options, bonds/rates, FX, funds/ETFs, crypto or a stock index is BLOCKED; running it on stocks is an asset
substitution that only an explicit user request can unlock, and it is then reported as a non-faithful exploratory
experiment. Synthetic-data papers are recorded as a data-object substitution (no real asset is replaced).
"""
from __future__ import annotations

import re

VERSION = "paper_agent.instruments/1.0"
AVAILABLE = "equity_stock"

CUES = {
    "futures": r"\bfutures\b|\bfront[- ]month\b|\broll(?:ed|ing)?[- ](?:over|into)\b|\brollover\b|\bcontinuous contracts?\b|"
               r"\bopen interest\b|\bsettlement prices?\b|\bmargin (?:requirements?|calls?|accounts?)\b|\bcontango\b|\bbackwardation\b|"
               r"\bnearest[- ]to[- ]delivery\b|\bdelivery months?\b|期货|主力合约|连续合约|展期|移仓|换月|保证金|持仓量|结算价|升贴水",
    "options": r"\boptions? (?:prices?|returns?|contracts?|markets?|data|portfolios?|strateg\w+|volume|positions?)\b|"
               r"\b(?:call|put) options?\b|\bstraddles?\b|\bstrangles?\b|\bstrike(?: price)?s?\b|\bimplied volatilit\w+\b|"
               r"\bdelta[- ]hedg\w*|\bmoneyness\b|\bOptionMetrics\b|\bIvy ?DB\b|期权|行权价|隐含波动率|认购|认沽",
    "bonds_rates": r"\b(?:government|treasury|corporate|sovereign|municipal) bonds?\b|\bbond (?:futures|yields?|returns?|ind(?:ex|ices)|markets?)\b|"
                   r"\byield curves?\b|\binterest[- ]rate (?:futures|swaps?|products?)\b|\bfixed[- ]income\b|国债|债券|利率债|信用债|收益率曲线|久期",
    "fx": r"\bcurrenc(?:y|ies) (?:futures|forwards?|pairs?|markets?|returns?)\b|\bforeign exchange\b|\bexchange rates?\b|\bforex\b|\bFX\b|"
          r"外汇|汇率",
    "etf_fund": r"\bETFs?\b|\bexchange[- ]traded funds?\b|\bmutual funds?\b|\bindex funds?\b|\bLOFs?\b|基金|指数基金",
    "crypto": r"\bbitcoin\b|\bcrypto(?:currenc(?:y|ies)|[- ]?assets?)\b|\bethereum\b|比特币|加密货币|数字货币",
    "equity_index": r"\bS&P ?500\b|\bstock (?:market )?ind(?:ex|ices)\b|\bindex (?:returns?|levels?|prices?|values?|closes?)\b|"
                    r"\bDow Jones(?: Industrial Average)?\b|"
                    r"\bNasdaq(?: Composite| 100)?\b|\bmarket index\b|沪深300|中证500|中证1000|上证(?:综)?指|深证成指|创业板指|指数",
    "equity_stock": r"\bindividual stocks?\b|\bcommon stocks?\b|\bstock returns?\b|\bstocks\b|\bfirms\b|\bshares\b|\bCRSP\b|\bNYSE\b|"
                    r"\bconstituents?\b|\bequit(?:y|ies)\b|个股|股票|A ?股|上市公司|成分股",
    "synthetic_data": r"\bpseudo[- ]?data\b|\bsynthetic (?:data|series|prices?)\b|\bsimulated (?:data|prices?|series|returns?)\b|"
                      r"\bdata (?:is|was|were|are) (?:created|generated)\b|\bgenerated (?:data|series|pseudodata)\b|模拟数据|合成数据|仿真数据",
}
# the paper says its data are indices and not stocks (live R2: the MA paper, "stock indices exclusively", ran on stocks)
INDEX_ONLY = (r"\bind(?:ex|ices|exes)\b[^.;]{0,30}\b(?:exclusively|only)\b|\b(?:exclusively|only)\b[^.;]{0,20}\b(?:stock )?ind(?:ex|ices|exes)\b|"
              r"\bind(?:ex|ices|exes)\s+(?:and\s+)?not\s+(?:individual\s+)?stock|仅(?:使用|采用|研究)?[^。；]{0,8}指数")
# stocks belonging to an index are individual stocks (live R2: "stocks listed on the Dow-Jones, Nasdaq and S&P 500 indices")
STOCKS_OF_INDEX = r"\bstocks? (?:listed|included|traded|quoted) (?:on|in)\b|\b(?:index|indices) (?:constituents?|components?|members?)\b|成分股"
MULTI = r"\b(?:across|multiple|diverse|several|many) asset classes\b|\b\d{2,3} (?:futures |liquid )?markets\b|多资产|大类资产|跨资产"
LABEL_CN = {"futures": "期货", "options": "期权", "bonds_rates": "债券/利率", "fx": "外汇", "etf_fund": "ETF/基金", "crypto": "加密资产",
            "equity_index": "股票指数", "equity_stock": "个股", "synthetic_data": "合成/模拟数据"}
WEIGHTED_SECTION = re.compile(r"data|sample|method|design|strateg|construct|portfolio|appendix|数据|样本|方法|策略|构建|附录", re.I)
REFERENCES = re.compile(r"^\s*(references|bibliography|参考文献)\b", re.I)
COMPILED = {k: re.compile(v, re.I) for k, v in CUES.items()}
INDEX_ONLY_RX, STOCKS_OF_INDEX_RX = re.compile(INDEX_ONLY, re.I), re.compile(STOCKS_OF_INDEX, re.I)
MULTI_RX = re.compile(MULTI, re.I)


def _sentence(text, start, end):
    a = max(text.rfind(". ", 0, start), text.rfind("。", 0, start), -1) + 1
    b = min([x for x in (text.find(". ", end), text.find("。", end)) if x >= 0] or [len(text)])
    return text[a:b + 1].strip()[:240]


def scan(doc, focus_pages=()):
    """Scores per asset class for the whole document and for the factor's own pages (focus_pages +-1)."""
    focus = {p + d for p in focus_pages for d in (-1, 0, 1)}
    title = ((doc.get("metadata") or {}).get("title") or {}).get("value") or ""
    total = {k: 0.0 for k in CUES}
    local = {k: 0.0 for k in CUES}
    blocks = {k: set() for k in CUES}
    evidence = {k: [] for k in CUES}
    multi, index_only, stocks_of_index = [], [], []
    in_refs = False
    for b in doc.get("blocks", []):
        sec = b.get("section") or ""
        if REFERENCES.match(sec) or b.get("kind") == "reference" or REFERENCES.match(b.get("text", "")[:40]):
            in_refs = True
        if in_refs and b.get("kind") != "heading":
            continue
        text = b.get("text") or ""
        if not text:
            continue
        w = 1.0
        if (b.get("page") or 99) <= 2:
            w += 1.0
        if WEIGHTED_SECTION.search(sec):
            w += 1.0
        for k, rx in COMPILED.items():
            hits = list(rx.finditer(text))
            if not hits:
                continue
            total[k] += w * min(len(hits), 5)
            if b.get("page") in focus:
                local[k] += min(len(hits), 5)
            blocks[k].add(b["id"])
            if len(evidence[k]) < 4:
                h = hits[0]
                evidence[k].append({"block_id": b["id"], "page": b.get("page"), "match": h.group(0),
                                    "quote": _sentence(text, h.start(), h.end())})
        for rx, out in ((INDEX_ONLY_RX, index_only), (STOCKS_OF_INDEX_RX, stocks_of_index)):
            m = rx.search(text)
            if m and len(out) < 3:
                out.append({"block_id": b["id"], "page": b.get("page"), "match": m.group(0), "quote": _sentence(text, m.start(), m.end())})
        m = MULTI_RX.search(text)
        if m and len(multi) < 3:
            multi.append({"block_id": b["id"], "page": b.get("page"), "match": m.group(0), "quote": _sentence(text, m.start(), m.end())})
    for k, rx in COMPILED.items():
        if rx.search(title):
            total[k] += 6.0
            evidence[k].insert(0, {"block_id": "title", "page": 1, "match": rx.search(title).group(0), "quote": title[:200]})
    return {"version": VERSION, "title": title, "score": {k: round(v, 1) for k, v in total.items()},
            "local_score": local, "blocks": {k: len(v) for k, v in blocks.items()}, "evidence": evidence, "multi_asset": multi,
            "index_only": index_only, "stocks_of_index": stocks_of_index,
            "focus_pages": sorted(focus)}


def classify(scan_result, model_object=None):
    """Studied asset classes with evidence, the decision for the A-share stock panel, and the reasons.

    A class is studied when it has evidence in at least two blocks and dominates (or rivals) individual stocks, either over
    the whole paper or on the factor's own pages. A model statement backed by a verified quote adds a class but can never
    remove one the document shows (conflicts do not resolve in the model's favour).
    """
    s, loc, nb = scan_result["score"], scan_result["local_score"], scan_result["blocks"]
    equity = s["equity_stock"]
    studied = []
    for k in ("futures", "options", "bonds_rates", "fx", "etf_fund", "crypto", "equity_index", "synthetic_data"):
        if nb[k] < 2 and s[k] < 6:
            continue
        rel = s[k] / max(equity, 1.0)
        local_rel = loc[k] / max(loc["equity_stock"], 1.0) if loc[k] else 0.0
        threshold = 1.0 if k == "equity_index" else 0.35          # stock papers routinely mention a market index
        if rel >= threshold or local_rel >= max(threshold, 0.5) or (k == "synthetic_data" and s[k] >= 4):
            studied.append(k)
    if scan_result["multi_asset"] and any(k in studied for k in ("futures", "bonds_rates", "fx")):
        studied.append("multi_asset")
    model_classes = []
    if model_object and model_object.get("status") == "PAPER":
        model_classes = [c for c in (model_object.get("asset_classes") or []) if c in LABEL_CN and c != AVAILABLE]
    unconfirmed = []
    strong_stocks = equity >= 30 and nb["equity_stock"] >= 8
    for c in model_classes:
        doc_support = (s.get(c, 0) / max(equity, 1.0) >= 0.15 and nb.get(c, 0) >= 2) or loc.get(c, 0) >= 2
        if c not in studied and not doc_support and strong_stocks:
            # AI and program disagree: the reader names a class the document barely mentions while individual stocks
            # dominate (live A/B: Amihud read as index/bonds). Shown to the user as a reading to confirm, not silently applied.
            unconfirmed.append(c)
        elif c not in studied:
            studied.append(c)
    model_classes = [c for c in model_classes if c not in unconfirmed]
    stock_studied = (equity >= 6 and nb["equity_stock"] >= 3) or bool(scan_result.get("stocks_of_index"))
    index_only = scan_result.get("index_only") or []
    if index_only:
        stock_studied = False                     # the paper itself says its data are indices, not stocks
        if "equity_index" not in studied:
            studied.append("equity_index")
    elif "equity_stock" in model_classes_all(model_object) and not scan_result.get("index_only"):
        stock_studied = stock_studied or equity >= 3   # the reader names stocks too: an index is the universe, not the asset
    elif model_classes and "equity_index" in model_classes:
        stock_studied = False                     # the reader's verified statement: indices only
    blocking = [k for k in studied if k in ("futures", "options", "bonds_rates", "fx", "etf_fund", "crypto")]
    # an index factor inside a stock-heavy document (e.g. a timing model in a monthly report): the factor's own pages decide
    local_index = loc["equity_index"] >= 6 and loc["equity_index"] >= 2 * max(loc["equity_stock"], 1.0)
    if "equity_index" in studied and (not stock_studied or local_index):
        blocking.append("equity_index")
    if blocking:
        decision = "ASSET_CLASS_NOT_AVAILABLE"
    elif "synthetic_data" in studied and (not stock_studied or s["synthetic_data"] >= equity):
        decision = "SYNTHETIC_DATA_PAPER"
    else:
        decision = "EQUITY_STOCK_COMPATIBLE"
    return {"version": VERSION, "studied": studied, "blocking_classes": blocking, "decision": decision,
            "stock_evidence": stock_studied, "model_classes": model_classes,
            "summary_cn": "、".join(LABEL_CN.get(k, k) for k in studied if k != "multi_asset") + ("（多资产）" if "multi_asset" in studied else ""),
            "evidence": dict({k: scan_result["evidence"][k][:3] for k in studied if k in scan_result["evidence"]},
                             **({"equity_index": index_only[:2] + scan_result["evidence"]["equity_index"][:1]} if index_only else {})),
            "multi_asset_evidence": scan_result["multi_asset"][:2], "score": scan_result["score"],
            "index_only_evidence": index_only[:2], "stocks_of_index_evidence": (scan_result.get("stocks_of_index") or [])[:2],
            "model_unconfirmed": unconfirmed,
            "model_unconfirmed_quotes": [c.get("quote", "")[:160] for c in (model_object or {}).get("citations") or []][:2] if unconfirmed else []}


def model_classes_all(model_object):
    """Asset classes in a verified research-object statement, including the available one (equity_stock)."""
    if not model_object or model_object.get("status") != "PAPER":
        return []
    return [c for c in (model_object.get("asset_classes") or []) if isinstance(c, str)]
