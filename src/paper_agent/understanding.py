"""DeepSeek paper understanding with local verification.

The model reads only selected passages and returns one structured JSON object. Locally:
  * every citation quote is re-located verbatim in its passage (else the claim is UNVERIFIED);
  * the factor formula must parse in the closed Factor IR grammar;
  * each symbol's model reading is compared with the deterministic v0.3 reading of the *cited* definition text
    (window aggregate vs single-date field, window length, aggregate) and with any formula v0.3 rebuilt itself;
  * conflicts never resolve in the model's favour: they block or go to review.
Claim labels: PAPER (verified quote), DERIVED (mathematical restatement of quoted prose), REPLICATION_CHOICE (ours),
UNKNOWN (paper silent), UNVERIFIED (quote not found), CONFLICT (model vs deterministic reading).
"""
from __future__ import annotations

import json
import re

from paper_research.factor_ir import IRError, fields_used, parse_formula, render
from paper_research.task import PERIODS, interpret_definition

from .model import ModelFailure, ask_json

CIT = {"type": "array", "items": {"type": "object", "required": ["passage", "quote"]}}
FIELD = {"type": "object", "required": ["value", "citations"]}
SCHEMA = {
    "type": "object",
    "required": ["research_question", "hypothesis", "factors", "results_vs_methods", "unstated_details"],
    "properties": {
        "research_question": FIELD, "hypothesis": FIELD,
        "factors": {"type": "array", "minItems": 0, "items": {"type": "object", "required": [
            "name", "role", "verbal_definition", "formula_latex", "formula_status", "formula_citations", "symbols",
            "direction", "frequency", "signal_timing", "holding_period", "sample", "portfolio_rules"],
            "properties": {"symbols": {"type": "array", "items": {"type": "object", "required": [
                "symbol", "meaning", "kind", "data_field", "citations"]}}}}},
        "results_vs_methods": {"type": "array"}, "unstated_details": {"type": "array"},
        "replication_notes": {"type": "array"}, "research_object": {"type": "object"},
    },
}
VERSION = "paper_agent.understanding/5"          # 2: time-index semantics, symbol kinds, research object, new operators; 3: Chinese retrieval, algorithm guard; 4: named parameters, conflict sources, bounded investigation; 5: independent second reading of unreadable formulas, byte budgets
SEMANTIC_REPAIRABLE = {"LOOKBACK_READ_AS_LAG", "CUMULATIVE_READ_AS_SINGLE_PERIOD", "LAG_READ_AS_LOOKBACK", "LOOKBACK_WINDOW_MISMATCH",
                       "LOG_RETURN_READ_AS_SIMPLE", "EXPONENTIAL_READ_AS_MEAN", "EXPONENTIAL_SMOOTHING_MISSING",
                       "SKIP_PERIOD_MISSING", "CONSTANT_WITHOUT_SOURCE", "SYMBOL_NOT_IN_TABLE", "SYMBOL_DEFINITION_UNVERIFIED",
                       "SYMBOL_UNDEFINED", "FIELD_MAPPING_UNSUPPORTED", "ALGORITHM_STEP_AMBIGUOUS"}
ALGO_VAGUE = re.compile(r"\boptional(?:ly)?\b|\bsome (?:sort|kind) of\b|\bor similar\b|\bapproximately\b|\bsuch as\b|\be\.g\.|"
                        r"\bfor example\b|\bsomehow\b|可选|大致|类似|例如|某种", re.I)
FIELDS = ["open", "high", "low", "close", "volume", "amount", "returns", "market_cap", "other", "unknown"]
CONTEXT_BYTES = 32000          # understanding passages (UTF-8); the request and its repair turn stay under 64 KB
INTRO_BYTES = 14000            # passages handed to an investigation round
MESSAGE_BYTES = 40000          # an investigation request as a whole

SYSTEM = """You are a careful quantitative-finance research reader. You read ONLY the numbered passages given to you
(page-located excerpts of one paper) and return ONE JSON object. Rules:
1. Every factual claim must cite passages as {"passage": "P0123", "quote": "<verbatim substring of that passage, >= 8 chars>"}.
   Copy quotes exactly; never paraphrase inside "quote". If the passages do not state something, put it in
   "unstated_details" instead of guessing.
2. Separate the paper's METHOD from its RESULTS. Numbers the authors report are results, not parameters to reuse.
3. formula_latex: restate the factor at observation date t in this grammar only: \\frac{a}{b}, + - * /, |x|, \\log(x),
   \\sqrt{x}, \\operatorname{sign}(x), element-wise \\max(a, b) and \\min(a, b), window aggregates written
   \\max_{0 \\le k \\le N} X_{i,t-k}, \\min_{0 \\le k \\le N} X_{i,t-k}, \\operatorname{mean}_{k=0}^{N} (X_{i,t-k}),
   \\sum_{k=0}^{N} X_{i,t-k}, \\prod_{k=0}^{N} (X_{i,t-k}), \\operatorname{std}_{k=0}^{N} (X_{i,t-k}),
   \\operatorname{tsrank}_{k=0}^{N}(X_{i,t-k}), \\operatorname{corr}_{k=0}^{N}(X_{i,t-k}, Y_{i,t-k}), \\operatorname{cov}_{k=0}^{N}(X_{i,t-k}, Y_{i,t-k}),
   exponential smoothing \\operatorname{ema}_{N}(x) (alpha = 2/(N+1)), \\operatorname{rma}_{N}(x) (Wilder, alpha = 1/N),
   \\operatorname{sma}_{N,M}(x) (Chinese software SMA, alpha = M/N); cross-sectional \\operatorname{rank}(x).
   TIME INDEX RULE: a subscript X_{i,t-k} is ALWAYS the single value observed k periods (the paper's own period unit)
   before t. Never use a subscript to mean a look-back horizon. A return over a look-back window ("past 12-month return",
   "return over the previous N days", "过去N日涨跌幅") is written explicitly, e.g. \\frac{P_{i,t}}{P_{i,t-12}} - 1, or kept as
   its own symbol of kind "cumulative_return" (see 4). A skipped most-recent period moves the window; it is not a lag of a
   one-period return. Write "NAME_{i,t} = ...". Every number in the formula (windows, lags, parameters) must be stated in
   a cited passage, or listed in replication_notes as your choice.
   If the factor CANNOT be written in this grammar (path-dependent logic such as a running drawdown or a streak count,
   conditional state, sorting or a regression residual inside a window), set formula_status "algorithm", formula_latex ""
   and add "algorithm": {"steps": ["ordered, precise steps naming every window and which past rows are used"],
   "inputs": [symbols], "lookback": {"n": int, "unit": "..."}, "citations": [...]}. Never force such a factor into the
   grammar by changing what it computes.
   Do NOT put portfolio construction into formula_latex: "stocks are ranked/sorted by X" means the factor is X
   (no rank operator); ranking, deciles and weights belong in portfolio_rules.
   Window bounds are integers or a NAMED PARAMETER. When the paper names a count with a symbol (N, N_{fast}, \\tau, X,
   lead) keep that symbol in formula_latex (e.g. \\operatorname{ema}_{N_{fast}}(close_{i,t}), \\sum_{k=0}^{X-1}) and list
   it in the factor's "parameters": {"symbol", "meaning", "value": the number the paper uses for its main results or
   null, "paper_values": [every value the paper reports testing], "status": "stated" (the paper fixes one value) |
   "paper_tested" (several values, none singled out) | "unstated", "citations": [quotes that contain the numbers]}.
   NEVER invent or "standardise" a value (no "conventional 14 days", no "one year = 250"): if the passages do not give
   it, value null and status "unstated"; the program then asks the user. A program binds the value only if the number
   is inside your quote. A count fixed by the calendar or data availability is NOT a parameter, even when the paper
   gives it a symbol (e.g. D_{i,y} = "days with data in year y"): use its nominal length in the paper's period unit
   and record that approximation in replication_notes.
   If a symbol is itself a windowed quantity defined in words (e.g. "highest price over the past 12 months") you may
   keep it as a symbol in the formula and describe it in "symbols" with kind "window_aggregate".
   formula_status: "stated_in_paper" (the paper prints it), "restated_from_prose" (you translated the paper's words),
   or "unknown" (cannot be determined; then formula_latex = "").
4. symbols[]: {"symbol","meaning","kind": "raw_field"|"period_return"|"cumulative_return"|"window_aggregate"|"derived"|"constant",
   "data_field": one of open/high/low/close/volume/amount/returns/market_cap/other/unknown,
   "aggregate": max/min/mean/sum/std or null, "window": {"n": int, "unit": "day"|"trading_day"|"week"|"month"|"year"} or null,
   "price_basis": e.g. "daily close", "month-end price", "intraday high" or "unstated",
   "adjustment": "adjusted"|"unadjusted"|"unstated", "units": text or null, "citations": [...]}.
   IMPORTANT: data_field "high" means ONLY the same-day intraday high price. A maximum over a past window is kind
   "window_aggregate" with aggregate "max" (aggregate "ema" for exponential smoothing) and the underlying data_field.
   kind "period_return": the return of ONE period (the paper's period) observed at the subscripted lag; add
   "compounding": "simple"|"log". kind "cumulative_return": the return accumulated over a look-back window ending at t;
   add "window": {"n","unit"}, "skip": {"n","unit"} or null, "compounding": "simple"|"log", data_field = the price.
   kind "derived": a quantity the paper defines by its own formula; add "derivation_latex" (this grammar, in terms of other
   symbols) and cite the passage that defines it. If a symbol is not defined anywhere in the passages, say so in "meaning"
   and set data_field "unknown" -- never map an undefined symbol onto a market field.
   "amount" means traded value in currency (dollar volume); "volume" means number of shares/lots.
5. direction/frequency/signal_timing/holding_period/sample/portfolio_rules/research_question/hypothesis are objects
   {"value": text, "citations": [...]}; use value "unstated" with empty citations when the paper is silent.
   frequency.value must start with daily/weekly/monthly/quarterly/annual when stated.
6. results_vs_methods: list of {"statement","type":"result"|"method","citations":[...]} for the key items.
7. unstated_details: list of {"item","why_it_matters"} (e.g. price adjustment, close vs intraday high, data vendor).
8. replication_notes: list of {"choice","reason"} -- only implementation choices YOU would have to make; label them as yours.
10. research_object: {"value": "the instruments the paper's data and tests use", "asset_classes": [one or more of
   equity_stock, equity_index, futures, options, bonds_rates, fx, etf_fund, crypto, synthetic_data], "citations": [...]}.
9. Be concise: describe only the factor(s) the user asked about (or the paper's main factor), at most 2 citations per item,
   quotes of 8-160 characters, at most 6 results_vs_methods and 6 unstated_details. The whole JSON must stay well under
   3000 tokens.
Return JSON only, with EXACTLY this top-level structure (no other top-level keys such as "type"):
{"research_question": {"value": "...", "citations": [{"passage": "P0001", "quote": "..."}]},
 "hypothesis": {"value": "...", "citations": []},
 "factors": [{"name": "<factor name as in the paper>", "role": "primary",
   "verbal_definition": {"value": "...", "citations": [...]},
   "formula_latex": "NAME_{i,t} = ...", "formula_status": "stated_in_paper", "formula_citations": [...],
   "parameters": [{"symbol": "N", "meaning": "...", "value": 20, "paper_values": [10, 20], "status": "stated", "citations": [...]}],
   "symbols": [{"symbol": "<bare symbol exactly as used in formula_latex, without subscripts, e.g. P or close>",
                "meaning": "...", "kind": "raw_field", "data_field": "close", "aggregate": null, "window": null,
                "price_basis": "...", "adjustment": "unstated", "units": null, "citations": [...]}],
   "direction": {"value": "...", "citations": []}, "frequency": {"value": "daily", "citations": [...]},
   "signal_timing": {"value": "...", "citations": []}, "holding_period": {"value": "...", "citations": []},
   "sample": {"value": "...", "citations": []}, "portfolio_rules": {"value": "...", "citations": []}}],
 "results_vs_methods": [{"statement": "...", "type": "result", "citations": [...]}],
 "unstated_details": [{"item": "...", "why_it_matters": "..."}],
 "replication_notes": [{"choice": "...", "reason": "..."}],
 "research_object": {"value": "...", "asset_classes": ["equity_stock"], "citations": [...]}}
Constants (e.g. 0.001) are written inside formula_latex, not listed as symbols.
If the passages define no computable factor or signal, return "factors": [] and say why in "unstated_details"."""


FIX_SCHEMA = {"type": "object", "required": ["formula_latex"],          # a missing unit blocks only non-daily plans
              "properties": {"formula_latex": {"type": "string"}, "window_unit": {"enum": ["paper_period", "trading_day"]}}}


def _queries(focus):
    return [f"{focus} definition formula measure ratio ranked based on", f"{focus} where is the price denotes defined",
            "factor is defined as computed as measured", "sample period stocks data CRSP universe exchange",
            "portfolio formed held months winner loser deciles quintiles weighted", "daily monthly frequency data returns volume",
            "adjusted for splits dividends price", "hypothesis explanation investors anchor illiquidity premium",
            "results returns per month t-statistics significant", "skip month signal formation holding period",
            # Chinese reports (bigram tokens): definitions, formulas, parameters, data, signals and holding rules
            f"{focus} 因子 定义 计算 公式 构建 指标", "其中 表示 为 收盘价 成交量 成交额 收益率 涨跌幅",
            "窗口 参数 周期 日 均线 移动平均 指数平滑", "样本 数据 股票池 标的 指数 期货 期权 基金", "信号 买入 卖出 择时 调仓 持有 回测"]


def understand(evidence, client, ledger, *, focus="", budget_chars=24000, max_tokens=4096, user_params=None):
    spec = evidence.spec
    must = [p["id"] for p in evidence.passages if p["has_formula"] and (p["flags"] or "\\frac" in p["text"]
                                                                        or "[FORMULA_UNRESOLVED]" in p["text"])][:12]
    # passages naming the requested factor verbatim (e.g. "Alpha#101") are always included
    key = re.sub(r"\s+", "", (focus or "").lower())
    for name in {key} | {re.sub(r"\s+", "", t.lower()) for t in re.findall(r"[A-Za-z]+#?\d+[A-Za-z]*", focus or "")}:
        if len(name) >= 4:
            must = [p["id"] for p in evidence.passages if name in re.sub(r"\s+", "", p["text"].lower())][:6] + must
    queries = _queries(focus or " ".join(f["name"] for f in spec["factors"][:2]))
    ctx = evidence.context(queries, budget_chars=budget_chars, must=must)
    # the whole request is capped at 64 KB of UTF-8 (and a repair turn adds the reply): a Chinese report's 24000
    # characters are ~72 KB, so the passages are budgeted in bytes (live J3: Huatai failed before any call)
    size = len(evidence.render(ctx).encode("utf-8"))
    while size > CONTEXT_BYTES and budget_chars > 3000:
        budget_chars = int(budget_chars * CONTEXT_BYTES / size * 0.95)
        ctx = evidence.context(queries, budget_chars=budget_chars, must=must)
        size = len(evidence.render(ctx).encode("utf-8"))
    ledger.event("EVIDENCE_CONTEXT", {"passages": [p["id"] for p in ctx], "chars": sum(len(p["text"]) for p in ctx),
                                      "of_total_passages": len(evidence.passages)})
    user = (f"Paper: {evidence.summary()['title']!r}. User focus: {focus or 'the paper main factor(s)'}.\n"
            f"Deterministic parser notes: formulas rebuilt from layout appear as LaTeX inside passages; "
            f"'[FORMULA_UNRESOLVED]' marks a formula the parser could not read; passages flagged glyph_substitution have "
            f"mis-encoded math symbols.\n\nPASSAGES:\n" + evidence.render(ctx))
    raw, rec = ask_json(client, ledger, purpose="paper_understanding", system=SYSTEM, user=user, schema=SCHEMA,
                        max_tokens=max_tokens)
    raw["_user_params"] = dict(user_params or {})
    raw["_second_readings"] = {}                 # this reader checks unreadable formulas with an independent second reading
    initial = [{"name": f.get("name"), "formula_latex": f.get("formula_latex"), "formula_status": f.get("formula_status"),
                "parameters": f.get("parameters"), "algorithm": f.get("algorithm")}
               for f in raw.get("factors") or [] if isinstance(f, dict)]
    verified = verify(raw, evidence, raw["_user_params"])
    repairs = []
    for attempt in range(2):                     # bounded, targeted repair of an unparseable formula
        bad = [(i, f) for i, f in enumerate(verified["factors"]) if any(c["code"] == "FORMULA_UNPARSEABLE" for c in f["conflicts"])]
        if not bad:
            break
        i, f = bad[0]
        err = next(c["detail"] for c in f["conflicts"] if c["code"] == "FORMULA_UNPARSEABLE")
        freq = ((f.get("frequency") or {}).get("value") or "unstated")
        fix, rec2 = ask_json(client, ledger, purpose="formula_repair", system=SYSTEM, schema=FIX_SCHEMA, max_tokens=1500, user=(
            f"Your formula_latex for factor {f['name']!r} does not parse: {err}\nFormula: {f['formula']['latex']}\n"
            f"The paper's data frequency for this factor (your reading): {freq}.\n"
            "Rewrite it so that it parses:\n"
            "- an average over a window is written \\operatorname{mean}_{k=0}^{M}(X_{i,t-k}) (do not write 1/M times a sum);\n"
            "- a count the paper itself names with a symbol (N, \\tau, X, lead) STAYS that symbol: the program binds it from the "
            "parameters you cited, or asks the user. Never replace it with a number the paper does not give;\n"
            "- a count fixed by the calendar or by data availability is NOT a parameter even if the paper gives it a symbol "
            "(e.g. D_{i,y} = 'number of days with data for stock i in year y'): it becomes its nominal length in the "
            "paper's period unit: one year of daily data = 250 trading days (M = 249), one month of daily data = 21 (M = 20), "
            "one year of weekly data = 52 weeks (M = 51), one year of monthly data = 12 (M = 11);\n"
            "- write lags as X_{i,t-k}.\n"
            "State which unit M and every lag count: window_unit = \"paper_period\" if they count the paper's own periods "
            f"({freq} observations), or \"trading_day\" if they count trading days. Use one unit for the whole formula.\n"
            "Return {\"formula_latex\": \"...\", \"window_unit\": \"paper_period|trading_day\", "
            "\"parameters\": [every named count kept as a symbol: {\"symbol\", \"meaning\", \"value\" (a number inside your quote, or null), "
            "\"paper_values\", \"status\": \"stated|paper_tested|unstated\", \"citations\"}], "
            "\"replication_note\": {\"choice\": \"...\", \"reason\": \"...\"}} "
            "where the note states the approximation. Do not change what is computed otherwise."))
        raw["factors"][i]["formula_latex"] = fix["formula_latex"]
        if isinstance(fix.get("parameters"), list) and fix["parameters"]:
            raw["factors"][i]["parameters"] = [x for x in fix["parameters"] if isinstance(x, dict)][:8]
        if fix.get("replication_note"):
            raw.setdefault("replication_notes", []).append(fix["replication_note"])
        repairs.append({"factor": f["name"], "error": err, "repaired": fix["formula_latex"], "note": fix.get("replication_note"),
                        "window_unit": fix.get("window_unit"), "record": rec2["record"], "attempt": attempt})
        verified = verify(raw, evidence, raw["_user_params"])
        repairs[-1]["parses_after_repair"] = not any(c["code"] == "FORMULA_UNPARSEABLE" for c in verified["factors"][i]["conflicts"])
    if repairs:
        verified["formula_repairs"] = repairs
        raw["_repairs"] = [{k: r.get(k) for k in ("repaired", "note")} for r in repairs]
        verified = verify(raw, evidence, raw["_user_params"])
        verified["formula_repairs"] = repairs
    verified, investigations = _investigate(raw, verified, evidence, client, ledger, focus)
    verified = _second_readings(raw, verified, evidence, client, ledger, focus)
    if repairs:
        verified["formula_repairs"] = repairs
    if investigations:
        verified["investigations"] = investigations
        verified["semantic_repairs"] = investigations      # same records under the name the report already reads
    verified["model_record"] = rec
    verified["context_passages"] = [p["id"] for p in ctx]
    verified["focus"] = focus or ""
    # the AI's first reading and its final one (re-verified later with values the user types, e.g. "N=20")
    verified["reading"] = {"initial": initial, "final": raw}
    return verified


def reverify(understanding, evidence, user_params):
    """The same verification on the stored final reading with the user's parameter values; investigations are kept."""
    raw = json.loads(json.dumps((understanding.get("reading") or {}).get("final") or {}))
    if not raw.get("factors"):
        return understanding
    raw["_user_params"] = dict(raw.get("_user_params") or {}, **user_params)
    out = verify(raw, evidence, raw["_user_params"])
    for k in ("formula_repairs", "investigations", "semantic_repairs", "model_record", "context_passages"):
        if k in understanding:
            out[k] = understanding[k]
    out["reading"] = {"initial": (understanding.get("reading") or {}).get("initial"), "final": raw}
    out["user_parameters"] = raw["_user_params"]
    return out


SECOND_SCHEMA = {"type": "object", "required": ["formula_latex"], "properties": {
    "formula_latex": {"type": "string"}, "parameters": {"type": "array"}, "symbols": {"type": "array"}}}


def _second_readings(raw, verified, evidence, client, ledger, focus):
    """One independent reconstruction for a factor whose printed formula the program cannot read (see verify). The reader
    gets the passages of the formula's pages and of the definitions -- never the first reading -- and the program
    compares the two numerically. At most one call per factor; failures are recorded and the factor stays blocked."""
    from .reconcile import unreadable_formula
    changed = False
    for f in verified["factors"]:
        codes = {c["code"] for c in f["conflicts"] if c["blocking"]}
        if codes != {"FORMULA_RECONSTRUCTION_UNVERIFIED"}:
            continue                           # blocked anyway, or nothing to check
        if focus and not (focus.lower() in (f["name"] or "").lower() or (f["name"] or "").lower() in focus.lower()
                          or any(re.sub(r"\W", "", t) and re.sub(r"\W", "", t).lower() in (f["name"] or "").lower()
                                 for t in re.findall(r"[A-Za-z]+#?\d*", focus))):
            continue
        pages = set(unreadable_formula(f, evidence))
        cited = {c["passage"] for k in ("verbal_definition", "formula") for c in f[k]["citations"]} | \
            {c["passage"] for s in f["symbols"] for c in s["citations"]}
        ids, used = [], 0
        for p in evidence.passages:
            if p["page"] in pages or p["id"] in cited:
                b = len(p["text"].encode("utf-8"))
                if used + b <= INTRO_BYTES * 2:
                    ids.append(p)
                    used += b
        user = (f"Factor: {f['name']!r}. Write its formula at observation date t, in the grammar and rules given, from these "
                "passages only. Keep named counts symbolic and list them in parameters (value only if it is inside your quote). "
                "The printed formula may be unreadable in this text layer; use the paper's words and say nothing you cannot cite. "
                "Return {\"formula_latex\": \"...\", \"parameters\": [...], \"symbols\": [{\"symbol\", \"kind\", \"data_field\"}]}.\n\n"
                "PASSAGES:\n" + evidence.render(ids))
        try:
            obj, rec = ask_json(client, ledger, purpose="independent_reading", system=SYSTEM, schema=SECOND_SCHEMA,
                                max_tokens=1500, user=user)
            second = {"formula_latex": obj.get("formula_latex"), "parameters": obj.get("parameters") or [],
                      "symbols": [s for s in obj.get("symbols") or [] if isinstance(s, dict)], "record": rec["record"]}
        except ModelFailure as e:
            second = {"error": e.code}
        raw.setdefault("_second_readings", {})[f["name"]] = second
        ledger.event("INDEPENDENT_READING", {"factor": f["name"], "pages": sorted(pages), "error": second.get("error")})
        changed = True
    return verify(raw, evidence, raw.get("_user_params")) if changed else verified


INVESTIGABLE = SEMANTIC_REPAIRABLE |{"FORMULA_UNPARSEABLE", "FREE_PARAMETER_UNBOUND", "PARAMETER_VALUE_UNVERIFIED",
                                      "MODEL_FORMULA_CONTRADICTS_PAPER", "FORMULA_DEGENERATE_TERMS", "FORMULA_NOT_ESTABLISHED"}
INVESTIGATE_SCHEMA = {"type": "object", "required": ["action"], "properties": {
    "action": {"enum": ["investigate", "answer"]}, "requests": {"type": "array"}, "factor": {"type": "any"},
    "findings": {"type": "array"}, "replication_notes": {"type": "array"}}}
INVESTIGATE_RULES = """You are checking your own reading of one factor against the paper. A separate program compared your
formula, parameters and symbol table with the verbatim passages and the PDF layout, and reports the conflicts below. The
program is not assumed to be right either: its parser may not support a notation, and the PDF text layer may be garbled.
You may investigate before answering, using ONLY these tools on the same paper (at most 4 requests per round):
  {"tool": "search", "query": "keywords, English or Chinese"}   -> the best matching passages
  {"tool": "read", "passage": "P0123"}                          -> that passage with its neighbours
  {"tool": "page", "page": 7}                                    -> every passage of that page as the program rebuilt it, plus
                                                                    the page's raw PDF text layer extracted independently
You cannot see images. If both text layers of a formula are garbled, say so; never reconstruct it by guessing.
Reply {"action": "investigate", "requests": [...]} to read more, or answer with
{"action": "answer", "factor": <the corrected factor, same keys as in "factors", or null if your reading stands>,
 "findings": [{"issue": "<conflict code>", "symbol": "<symbol or null>", "source": "ai_misreading" (your reading was
   wrong) | "extraction_error" (the PDF text of the formula/definition is garbled or incomplete) | "unsupported_notation"
   (the paper is clear but the grammar cannot express it) | "paper_ambiguity" (the paper itself does not define it
   unambiguously) | "data_mismatch" | "free_parameter" (the paper leaves a value open), "explanation": "...",
   "citations": [{"passage": "P0123", "quote": "verbatim"}]}],
 "replication_notes": [...]}.
Rules: every claim cites verbatim quotes; a number used in the formula must be inside a quote or the parameter stays
"unstated" (value null) for the user to choose; keep named counts symbolic and list them in "parameters"; follow the
TIME INDEX RULE. Do not invent a definition to make the factor computable: an honest "unstated" is a correct answer."""


def _investigate(raw, verified, evidence, client, ledger, focus, *, max_attempts=2, max_rounds=3, round_chars=12000):  # round_chars: bytes
    """Bounded investigation after a conflict: the reader may call the existing evidence tools (search / read / page with
    the PDF's raw text layer) for up to `max_rounds - 1` rounds, then answers once; the same deterministic verification
    runs on the answer. Source claims are accepted only when the program can check them. Every request, page, claim
    and model record is kept for the audit record."""
    from .reconcile import accept_claim, run_request, save_page_image
    from .semantics import definition_passages
    history = []
    for attempt in range(max_attempts):
        bad = [(i, f) for i, f in enumerate(verified["factors"])
               if any(c["blocking"] and c["code"] in INVESTIGABLE for c in f["conflicts"])]
        if focus:
            want = [x for x in bad if focus.lower() in (x[1]["name"] or "").lower() or (x[1]["name"] or "").lower() in focus.lower()]
            bad = want or bad[:1]
        if not bad:
            break
        i, f = bad[0]
        issues = [c for c in f["conflicts"] if c["blocking"] and c["code"] in INVESTIGABLE]
        cited = {c["passage"] for k in ("verbal_definition", "formula") for c in f[k]["citations"]} | \
            {c["passage"] for s in f["symbols"] for c in s["citations"]} | \
            {c["passage"] for p in f.get("parameters") or [] for c in p.get("citations") or []}
        ids = set()
        for pid in cited:
            n = int(pid[1:])
            ids.update(f"P{j:04d}" for j in (n - 1, n, n + 1))
        for c in issues:
            for d in definition_passages(evidence, c.get("symbol")):
                ids.add(d["passage"])
        ctx, used_bytes = [], 0
        for x in sorted(ids, key=lambda x: int(x[1:])):
            p = evidence.by_id.get(x)
            b = len(p["text"].encode("utf-8")) if p else 0
            if p and len(ctx) < 12 and used_bytes + b <= INTRO_BYTES:
                ctx.append(p)
                used_bytes += b
        before = sorted({c["code"] for c in issues})
        current = raw["factors"][i]
        intro = (f"Factor {f['name']!r}. Your current reading:\n" + json.dumps(
            {k: current.get(k) for k in ("formula_latex", "formula_status", "parameters", "symbols", "algorithm") if current.get(k)},
            ensure_ascii=False)[:3500] +
            "\n\nThe program found (code, program's view of the source, detail):\n" +
            "\n".join(f"- {c['code']}" + (f" (symbol {c['symbol']})" if c.get("symbol") else "") +
                      f" [{c.get('source_program') or c.get('source')}]: {c['detail']}" for c in issues) +
            "\n\nPASSAGES (cited by you, their neighbours, and definition-like passages the program found):\n" + evidence.render(ctx))
        messages_user = intro
        consulted = {"passages": [p["id"] for p in ctx], "pages": []}
        requests, records, obj = [], [], None
        for rnd in range(max_rounds):
            last = rnd == max_rounds - 1
            obj, rec = ask_json(client, ledger, purpose="paper_investigation", system=SYSTEM + "\n\n" + INVESTIGATE_RULES,
                                schema=INVESTIGATE_SCHEMA, max_tokens=3000,
                                user=messages_user + ("\n\nThis is your last turn: answer now (action \"answer\")." if last else ""))
            records.append(rec["record"])
            if obj.get("action") != "investigate" or last:
                break
            texts, used = [], 0
            reqs = obj.get("requests") if isinstance(obj.get("requests"), list) else []
            for req in reqs[:4]:
                text, info = run_request(evidence, req if isinstance(req, dict) else {})
                b = len(text.encode("utf-8"))
                if used + b > round_chars or len(messages_user.encode("utf-8")) + used + b > MESSAGE_BYTES:
                    break                      # bytes, not characters: Chinese text is 3 bytes per character
                used += b
                texts.append(text)
                info["round"] = rnd
                requests.append(info)
                consulted["passages"] += info.get("passages") or []
                consulted["pages"] += info.get("pages") or []
            ledger.event("PAPER_INVESTIGATION_ROUND", {"factor": f["name"], "attempt": attempt, "round": rnd,
                                                       "requests": [{k: r.get(k) for k in ("tool", "query", "pages")} for r in requests if r["round"] == rnd]})
            messages_user = (messages_user + "\n\nYOUR REQUESTS (round " + str(rnd + 1) + "):\n" +
                             json.dumps(reqs[:4], ensure_ascii=False) + "\n\nRESULTS:\n" + "\n\n".join(texts))
        if obj.get("action") != "answer":
            obj = {"action": "answer", "factor": None, "findings": []}
        findings = []
        for x in (obj.get("findings") if isinstance(obj.get("findings"), list) else [])[:8]:
            if not isinstance(x, dict):
                continue
            ok, why = accept_claim(x, evidence, f, consulted)
            findings.append({"issue": x.get("issue"), "symbol": x.get("symbol"), "source": x.get("source"),
                             "explanation": str(x.get("explanation") or "")[:400], "accepted": ok, "why": why,
                             "citations": [c for c in (evidence.verify_quote(c.get("passage"), c.get("quote"))
                                                       for c in (x.get("citations") if isinstance(x.get("citations"), list) else [])
                                                       if isinstance(c, dict)) if c]})
        raw.setdefault("_claims", {})[f["name"]] = [y for y in findings if y["accepted"]]
        fixed = obj.get("factor") if isinstance(obj.get("factor"), dict) else None
        if fixed:
            fixed["name"] = f["name"]
            raw["factors"][i] = fixed
        if isinstance(obj.get("replication_notes"), list):
            raw.setdefault("replication_notes", []).extend([n for n in obj["replication_notes"] if isinstance(n, dict)][:6])
        verified = verify(raw, evidence, raw.get("_user_params"))
        after = sorted({c["code"] for c in verified["factors"][i]["conflicts"] if c["blocking"]})
        pages = sorted(set(consulted["pages"]))
        images = [img for img in (save_page_image(ledger, evidence, p) for p in pages[:4]) if img]
        history.append({"factor": f["name"], "attempt": attempt, "conflicts_before": before, "conflicts_after": after,
                        "formula_before": f["formula"].get("latex_as_written") or f["formula"]["latex"],
                        "formula_after": verified["factors"][i]["formula"]["latex"], "changed": bool(fixed),
                        "requests": requests, "pages_consulted": pages, "page_images": images, "findings": findings,
                        "records": records, "record": records[-1] if records else None, "rounds": len(records)})
        ledger.event("PAPER_INVESTIGATION", {k: history[-1][k] for k in ("factor", "attempt", "conflicts_before", "conflicts_after",
                                                                         "pages_consulted", "rounds", "changed")})
        if not after or not fixed or after == before:
            # resolved; or the reader stands by its reading; or a corrected reading leaves the same conflicts (live A/B:
            # a second attempt on an unstated RSI window added a call and nothing else): report, do not loop
            break                              # resolved, or the reader stands by its reading: report, do not loop
    return verified, history


# ---------------------------------------------------------------- local verification

def _cites(evidence, cits):
    good, bad = [], []
    for c in cits or []:
        loc = evidence.verify_quote(c.get("passage"), c.get("quote"))
        (good if loc else bad).append(loc or c)
    return good, bad


def _label(evidence, obj):
    if not isinstance(obj, dict):
        return {"value": obj, "status": "UNKNOWN", "citations": []}
    good, bad = _cites(evidence, obj.get("citations"))
    v = obj.get("value")
    status = "PAPER" if good else ("UNKNOWN" if (not obj.get("citations") or str(v).lower().startswith("unstated")) else "UNVERIFIED")
    return {"value": v, "status": status, "citations": good, "rejected_citations": bad}


def _window_periods(win, freq):
    unit = {"daily": "day", "weekly": "week", "monthly": "month", "quarterly": "quarter", "annual": "year"}.get(freq)
    if not win or not unit or win.get("unit") not in PERIODS:
        return None
    return win["n"] * PERIODS[win["unit"]] / PERIODS[unit]


def _strip_lhs(ir):
    return ir


def _normalized(ir):
    """IR with time indices removed and every lag shifted so the smallest constant lag is 0 (common-lag invariant)."""
    import copy
    from paper_research.factor_ir import walk
    out = copy.deepcopy(ir)
    bases = [n["lag"]["base"] for n in walk(out) if n["op"] == "field"]
    lo = min(bases) if bases else 0
    for n in walk(out):
        if n["op"] == "field":
            n["lag"] = {"base": n["lag"]["base"] - lo, "var": n["lag"].get("var")}
    return out


def _degenerate(ir):
    """x - x or x / x inside a formula: what a garbled text layer produces (live round 1, ROOT08)."""
    from paper_research.factor_ir import walk
    for n in walk(ir):
        if n["op"] in ("sub", "div") and len(n.get("args") or []) == 2 and n["args"][0] == n["args"][1]:
            return render(n)
    return None


def verify(raw, evidence, user_params=None):
    from .reconcile import annotate, bind_parameters, field_map, formulas_agree, unreadable_formula
    spec = evidence.spec
    ro = raw.get("research_object") if isinstance(raw.get("research_object"), dict) else {}
    out = {"research_question": _label(evidence, raw.get("research_question")),
           "hypothesis": _label(evidence, raw.get("hypothesis")), "factors": [], "conflicts": [], "version": VERSION,
           "research_object": dict(_label(evidence, ro) if ro else {"value": None, "status": "UNKNOWN", "citations": []},
                                   asset_classes=[c for c in (ro.get("asset_classes") or []) if isinstance(c, str)][:6]),
           "unstated_details": raw.get("unstated_details") or [],
           "replication_notes": [dict(n, status="REPLICATION_CHOICE") for n in raw.get("replication_notes") or []],
           "results_vs_methods": []}
    for r in raw.get("results_vs_methods") or []:
        good, bad = _cites(evidence, r.get("citations"))
        out["results_vs_methods"].append({"statement": r.get("statement"), "type": r.get("type"),
                                          "status": "PAPER" if good else "UNVERIFIED", "citations": good})
    for f in raw.get("factors") or []:
        conf = []
        item = {"name": f.get("name"), "role": f.get("role")}
        for key in ("verbal_definition", "direction", "frequency", "signal_timing", "holding_period", "sample", "portfolio_rules"):
            item[key] = _label(evidence, f.get(key))
        fgood, fbad = _cites(evidence, f.get("formula_citations"))
        written = (f.get("formula_latex") or "").strip()
        st = f.get("formula_status")
        # named parameters: bound only from verified quotes or the user's own values; otherwise the user is asked
        declared = {str(p.get("symbol")) for p in f.get("parameters") or [] if isinstance(p, dict)}
        data_syms = {s.get("symbol") for s in f.get("symbols") or [] if s.get("kind") != "constant" and s.get("symbol") not in declared}
        latex, params, pconf = bind_parameters(written, f.get("parameters"), lambda cits: _cites(evidence, cits)[0],
                                               user_params, data_syms)
        conf += pconf
        unbound = any(c["blocking"] for c in pconf)
        item["parameters"] = params
        item["formula"] = {"latex": latex, "model_status": st, "citations": fgood, "rejected_citations": fbad}
        if latex != written:
            item["formula"]["latex_as_written"] = written
        ir = None
        if latex and not unbound:
            try:
                ir = parse_formula(latex)["ir"]
                item["formula"]["ir_rendered"] = render(ir)
            except IRError as e:
                conf.append({"code": "FORMULA_UNPARSEABLE", "detail": f"{e.code}: {e.detail}", "blocking": True})
            else:
                same = _degenerate(ir)
                if same:
                    conf.append({"code": "FORMULA_DEGENERATE_TERMS", "blocking": True,
                                 "detail": f"公式含有恒为常数的项 {same}（同一项相减或相除），常见于 PDF 公式文本层提取错误；需要核对原页"})
        algo = f.get("algorithm") if isinstance(f.get("algorithm"), dict) else None
        if st == "stated_in_paper":
            item["formula"]["status"] = "PAPER" if fgood else "UNVERIFIED"
        elif st == "restated_from_prose":
            item["formula"]["status"] = "DERIVED" if (fgood or item["verbal_definition"]["status"] == "PAPER") else "UNVERIFIED"
        elif st == "algorithm" and algo and not latex:
            agood, abad = _cites(evidence, algo.get("citations"))
            steps = [str(x)[:400] for x in (algo.get("steps") or []) if str(x).strip()][:12]
            item["formula"]["status"] = "ALGORITHM" if steps and (agood or item["verbal_definition"]["status"] == "PAPER") else "UNVERIFIED"
            item["algorithm"] = {"steps": steps, "inputs": [str(x) for x in (algo.get("inputs") or [])][:8],
                                 "lookback": algo.get("lookback") if isinstance(algo.get("lookback"), dict) else None,
                                 "citations": agood, "rejected_citations": abad}
        else:
            item["formula"]["status"] = "UNKNOWN"
        if (not latex and item["formula"]["status"] != "ALGORITHM") or item["formula"]["status"] in ("UNKNOWN", "UNVERIFIED"):
            conf.append({"code": "FORMULA_NOT_ESTABLISHED", "detail": "no verified formula for this factor", "blocking": True})
        # compare with a formula the deterministic layer rebuilt itself (same symbols must match)
        if ir is not None:
            v03 = [x for x in spec["formulas"] if x["status"] == "extracted" and x.get("latex")]
            for x in v03:
                try:
                    vir = parse_formula(x["latex"])["ir"]
                except IRError:
                    continue
                if set(fields_used(vir)) and set(fields_used(vir)) <= set(fields_used(ir)) | {"P"} and x["source_kind"].startswith("pdf_layout"):
                    item["formula"]["v03_formula"] = {"id": x["id"], "latex": x["latex"], "page": x["page"]}
                    if _normalized(vir) != _normalized(ir):
                        if ir["op"] in ("cs_rank", "cs_zscore") and _normalized(ir["args"][0]) == _normalized(vir):
                            conf.append({"code": "MODEL_ADDED_CROSS_SECTIONAL_TRANSFORM", "blocking": False,
                                         "detail": f"model wrote {render(ir)}; the paper's factor is {render(vir)} (ranking is a portfolio rule); the paper formula is used"})
                        else:
                            conf.append({"code": "MODEL_FORMULA_CONTRADICTS_PAPER", "blocking": True,
                                         "detail": f"paper layout formula {render(vir)} vs model {render(ir)}"})
                    if not set(fields_used(vir)) <= set(fields_used(ir)):
                        conf.append({"code": "FORMULA_SYMBOLS_DIFFER_FROM_LAYOUT", "detail": f"{x['latex']} vs {latex}", "blocking": False})
                    break                                   # the first (defining) occurrence in the paper
        freq = (item["frequency"]["value"] or "").lower().split()[0] if item["frequency"]["value"] else ""
        syms = []
        for s in f.get("symbols") or []:
            good, bad = _cites(evidence, s.get("citations"))
            cited_text = " ".join(c["quote"] for c in good)
            det = interpret_definition(cited_text) if cited_text else None
            sym = dict(s, citations=good, rejected_citations=bad, status="PAPER" if good else ("UNVERIFIED" if bad else "UNKNOWN"),
                       deterministic=det and {k: det[k] for k in ("kind", "aggregate", "window", "base", "sampling", "adjustment")})
            if det:
                if det["kind"] == "window_aggregate" and s.get("kind") != "window_aggregate":
                    conf.append({"code": "WINDOW_AGGREGATE_READ_AS_FIELD", "symbol": s.get("symbol"), "blocking": True,
                                 "detail": f"cited text describes a {det['aggregate']} over {det['window']['text']!r}; model says kind={s.get('kind')}"})
                if det["kind"] == "window_aggregate" and s.get("kind") == "window_aggregate":
                    if det["aggregate"] and s.get("aggregate") and det["aggregate"] != s["aggregate"]:
                        conf.append({"code": "AGGREGATE_MISMATCH", "symbol": s.get("symbol"), "blocking": True,
                                     "detail": f"text: {det['aggregate']}, model: {s.get('aggregate')}"})
                    mw, dw = s.get("window"), det["window"]
                    if mw and dw:
                        a, b = _window_periods(mw, freq or "daily"), _window_periods({"n": dw["n"], "unit": dw["unit"]}, freq or "daily")
                        if a and b and abs(a - b) > 0.1 * b:
                            conf.append({"code": "WINDOW_MISMATCH", "symbol": s.get("symbol"), "blocking": True,
                                         "detail": f"text {dw['text']!r} vs model {mw}"})
                if det["kind"] == "raw" and s.get("kind") == "raw_field" and det["base"] and s.get("data_field") not in (None, "unknown") \
                        and det["base"] not in ("price_unspecified",) and det["base"] != s.get("data_field") \
                        and not (det["base"] == "returns" and s.get("data_field") == "returns"):
                    conf.append({"code": "FIELD_MEANING_DIFFERS", "symbol": s.get("symbol"), "blocking": False,
                                 "detail": f"deterministic reading {det['base']} vs model {s.get('data_field')}"})
            if s.get("kind") == "raw_field" and s.get("data_field") == "high" and re.search(r"high(est)?\b.*\b(past|over|during|week|month|year)",
                                                                                             (s.get("meaning") or ""), re.I):
                conf.append({"code": "HISTORICAL_MAX_MAPPED_TO_INTRADAY_HIGH", "symbol": s.get("symbol"), "blocking": True,
                             "detail": "the model's own meaning describes a historical maximum"})
            if s.get("derivation_latex"):
                # a named count inside a derived symbol (live A/B: RSI's X sits in RS = mean_{k=0}^{X-1}...): same binding rules
                d_bound, d_params, d_conf = bind_parameters(str(s["derivation_latex"]), f.get("parameters"),
                                                            lambda cits: _cites(evidence, cits)[0], user_params, data_syms,
                                                            report_undeclared=False)
                if d_bound != s["derivation_latex"]:
                    sym.update(derivation_latex=d_bound, derivation_as_written=s["derivation_latex"])
                known = {p["symbol"] for p in params}
                params += [p for p in d_params if p["symbol"] not in known]
                conf += [c for c in d_conf if not any(c["code"] == x["code"] and c.get("symbol") == x.get("symbol") for x in conf)]
                unbound = unbound or any(c["blocking"] for c in d_conf)
            syms.append(sym)
        item["symbols"] = syms
        item["replication_notes"] = raw.get("replication_notes") or []
        # cross-section check: the definition is supported by passages from at least two different blocks
        blocks = {c["block_id"] for c in item["verbal_definition"]["citations"] + item["formula"]["citations"]
                  + [c for s in syms for c in s["citations"]]}
        pages = {c["page"] for c in item["verbal_definition"]["citations"] + item["formula"]["citations"]}
        item["cross_check"] = {"distinct_blocks": len(blocks), "pages": sorted(pages), "cross_checked": len(blocks) >= 2}
        # paper semantics vs this definition (time indices, look-back vs lag, constants, symbol table): deterministic rules
        from .semantics import check_factor, check_symbols
        if item.get("algorithm"):
            # every symbol the steps use must be defined (not only the declared inputs), and no step may be vague
            steps_text = " ".join(item["algorithm"]["steps"])
            mentioned = {s["symbol"] for s in syms if s.get("symbol") and re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(s['symbol'])}(?![A-Za-z0-9_])", steps_text)}
            conf += check_symbols(item, evidence, used=set(item["algorithm"]["inputs"]) | mentioned)
            vague = ALGO_VAGUE.findall(steps_text)
            if vague:
                conf.append({"code": "ALGORITHM_STEP_AMBIGUOUS", "blocking": True,
                             "detail": f"算法步骤含有不确定的表述（{'、'.join(dict.fromkeys(vague))}），无法确定唯一的计算方法"})
        elif not any(c["code"] == "FORMULA_UNPARSEABLE" for c in conf) and not unbound:
            user_notes = [{"choice": f"user-specified {p['symbol']} = {p['value']}", "reason": "typed by the user"}
                          for p in params if p["status"] == "USER"]
            conf += check_factor(item, replication_notes=(raw.get("replication_notes") or []) + user_notes, repairs=raw.get("_repairs") or [],
                                 freq=freq) + check_symbols(item, evidence)
        # the printed formula is unreadable for the program: the reader reconstructed it. A second, independent
        # reconstruction (made without seeing the first) must compute the same numbers, else a person checks the page.
        pages = unreadable_formula(item, evidence) if ir is not None else []
        if pages:
            item["formula"]["unreadable_pages"] = pages
            second = (raw.get("_second_readings") or {}).get(item["name"] or "")
            if second is None and "_second_readings" not in raw:
                pass                            # a reading made before this check (cached, or verify() alone): no claim
            elif second is None:
                conf.append({"code": "FORMULA_RECONSTRUCTION_UNVERIFIED", "blocking": True, "pages": pages,
                             "detail": f"原文第{pages}页的公式程序无法读取，本次公式由 AI 依据文字重建，尚未经过独立复核"})
            else:
                s_ir, s_err = None, second.get("error")
                if not s_err:
                    s_latex, _, s_conf = bind_parameters(second.get("formula_latex") or "", second.get("parameters"),
                                                         lambda cits: _cites(evidence, cits)[0], user_params, (),
                                                         report_undeclared=False)
                    try:
                        s_ir = parse_formula(s_latex)["ir"] if not any(c["blocking"] for c in s_conf) else None
                    except IRError as e:
                        s_err = f"{e.code}: {e.detail}"
                cmp = formulas_agree(ir, field_map(syms), s_ir, field_map(second.get("symbols"))) if s_ir is not None else None
                item["formula"]["independent_reading"] = {"latex": second.get("formula_latex"), "record": second.get("record"),
                                                          "comparison": cmp, "error": s_err}
                if not cmp or not cmp.get("agree"):
                    conf.append({"code": "FORMULA_READINGS_DISAGREE", "blocking": True, "pages": pages,
                                 "detail": (f"原文第{pages}页的公式程序无法读取。两次独立重建结果"
                                            + ("不一致" if cmp else "无法比较") + f"：①{latex} ②{second.get('formula_latex') or s_err}"
                                            + (f"（合成数据上最大差 {cmp['max_abs_diff']:.3g}）" if cmp and cmp.get("max_abs_diff") is not None else "")
                                            + "。请对照原文公式页确认正确定义")})
        claims = {(c.get("issue"), c.get("symbol")): c for c in (raw.get("_claims") or {}).get(item["name"] or "", [])}
        item["conflicts"] = conf = annotate(conf, item, evidence, claims)
        item["status"] = ("BLOCKED" if any(c["blocking"] for c in conf) else
                          "NEEDS_REVIEW" if conf or item["verbal_definition"]["status"] != "PAPER" else "VERIFIED")
        out["factors"].append(item)
        out["conflicts"] += [dict(c, factor=item["name"]) for c in conf]
    n_c = sum(len(x.get("citations", [])) for x in [out["research_question"], out["hypothesis"]])
    out["citation_stats"] = {"verified": sum(1 for f in out["factors"] for k in ("verbal_definition",) for _ in f[k]["citations"]) + n_c,
                             "rejected": sum(len(f["formula"]["rejected_citations"]) + sum(len(s["rejected_citations"]) for s in f["symbols"])
                                             for f in out["factors"])}
    return out
