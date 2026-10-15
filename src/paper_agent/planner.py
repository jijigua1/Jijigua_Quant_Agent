"""Paper -> research plan.

Builds a v0.3 research task from the verified understanding plus automatically proposed host choices, then decides:

  mode        PAPER_ORIGINAL                 every input/window/frequency as in the paper and certified data
              EXPLORATORY_REPLICATION         the published PROFILED data (and any recorded substitution) is used;
                                              statistics may be computed, never called a faithful replication
              APPROVED_RESEARCH_IMPLEMENTATION is added when the factor runs through a human-approved implementation
  decisions   substitutions that change the paper's method (frequency conversion, price basis, unadjusted prices across
              dates, window approximations, derived inputs) -> one user decision before anything runs
  hard stops  unknown/unparseable formula, semantic conflict, future reference, missing field without a derivation,
              wrong time direction -> BLOCKED, no consent can override them

The plan's definition fingerprint is frozen when the user accepts; later changes are refused (DEFINITION_FROZEN).
"""
from __future__ import annotations

import copy
import re

from paper_research import build_research_task
from paper_research.factor_ir import IRError, fields_used, parse_formula, render, walk, warmup
from paper_research.formulas import build_formula
from paper_research.task import FREQ_WORDS, PERIODS, interpret_definition

DAYS_WORDS = r"\b(?:\d+|[A-Z])\s+(?:trading\s+)?days\b|\bdaily\b|日线|日频|交易日|每日|\d+\s*日"

from .ledger import sha256_obj

ROWS_PER = {"weekly": 5, "monthly": 21, "quarterly": 63, "annual": 252}
UNIT_ROWS = {"trading_day": 1, "day": 1, "week": 5, "month": 21, "quarter": 63, "year": 252}
PRICE = {"open", "high", "low", "close"}
SEVERE_GATES = ("formula", "semantics", "fields", "host_choices")
NON_EQUITY = re.compile(r"\b(options?|straddles?|strangles?|implied volatilit\w*|futures?|swaps?|bonds?|treasur\w*|cds|credit default|"
                        r"currenc\w*|exchange rates?|fx|commodit\w*|warrants?|mutual funds?|crypto\w*)\b", re.I)


class PlanError(RuntimeError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _freq(understood_factor, spec):
    v = (understood_factor["frequency"]["value"] or "").lower()
    for name in ("daily", "weekly", "monthly", "quarterly", "annual"):
        if v.startswith(name):
            return name
    from paper_research.task import paper_frequency
    return paper_frequency(spec)[0]


def _augment_spec(spec, fac, evidence):
    """Add the model's verified (or prose-derived) formula as a formula record with cited symbol definitions."""
    s = copy.deepcopy(spec)
    latex = fac["formula"]["latex"]
    first = (fac["formula"]["citations"] or fac["verbal_definition"]["citations"] or [None])[0]
    blk = first["block_id"] if first else s["formulas"][0]["block_id"] if s["formulas"] else None
    page = first["page"] if first else None
    f = build_formula("mf1", latex, latex=latex, source_kind="model_restated", confidence="high")
    defined = {}
    words = {"open": r"\bopen", "high": r"\bhigh", "low": r"\blow", "close": r"\bclos", "volume": r"\bvolume", "amount": r"amount|dollar|value"}
    for sym in fac["symbols"]:
        if sym["citations"]:
            quote = " ".join(c["quote"] for c in sym["citations"])
            text = quote
            det = interpret_definition(quote)
            field = sym.get("data_field")
            # a quote listing several fields ("open, close, high, low ...") is ambiguous for keyword reading: when it
            # does contain the model's field, use the model's meaning (the verified quote stays as evidence)
            if sym.get("kind") == "raw_field" and det["kind"] == "raw" and det["base"] not in (None, "price_unspecified") \
                    and det["base"] != field and field in words and re.search(words[field], quote, re.I) and sym.get("meaning"):
                text = sym["meaning"]
            defined[sym["symbol"]] = {"definition": text, "block_id": sym["citations"][0]["block_id"], "quote": quote}
    out_sym = parse_formula(latex)["output"]
    if out_sym:
        defined.setdefault(out_sym, {"definition": "left-hand side (quantity defined by this formula)", "block_id": blk})
    # inputs are the parsed IR's fields: operator names (ema, rma, sma, max ...) are not variables
    inputs = fields_used(parse_formula(latex)["ir"])
    f.update(defined_variables=defined, undefined_variables=[x for x in inputs if x not in defined], block_id=blk,
             page=page, section=first["section"] if first else None, line=None,
             provenance={"origin": "deepseek", "formula_status": fac["formula"]["status"],
                         "citations": fac["formula"]["citations"] or fac["verbal_definition"]["citations"]})
    if f["undefined_variables"]:
        f["status"] = "suspect"
    s["formulas"].append(f)
    # the model's verified verbal definition is a paper (A) item: it satisfies the required factor_definition field
    vd = fac["verbal_definition"]
    if vd["status"] == "PAPER" and not s["A_supported"].get("factor_definition"):
        items = []
        for c in vd["citations"]:
            b = next(x for x in evidence.doc["blocks"] if x["id"] == c["block_id"])
            k = b["text"].find(c["quote"])
            if k >= 0:
                items.append({"field": "factor_definition", "status": "supported", "value": c["quote"], "matched": "deepseek_verified_quote",
                              "evidence": [{"location": {"doc_id": evidence.doc["doc_id"], "block_id": b["id"], "page": b["page"],
                                                         "section": b["section"], "line": b["line"], "char_start": k,
                                                         "char_end": k + len(c["quote"])}, "quote": c["quote"]}],
                              "confidence": "medium"})
        if items:
            s["A_supported"]["factor_definition"] = items
            s["C_missing"] = [x for x in s["C_missing"] if x["item"] != "factor_definition"]
    name = fac["name"]
    ev = (fac["verbal_definition"]["citations"] or fac["formula"]["citations"])
    loc = []
    for c in ev:
        b = next(x for x in evidence.doc["blocks"] if x["id"] == c["block_id"])
        k = b["text"].find(c["quote"])
        if k >= 0:
            loc.append({"location": {"doc_id": evidence.doc["doc_id"], "block_id": b["id"], "page": b["page"], "section": b["section"],
                                     "line": b["line"], "char_start": k, "char_end": k + len(c["quote"])}, "quote": c["quote"]})
    s["factors"] = [x for x in s["factors"] if x["name"] != name] + [
        {"name": name, "aliases": [out_sym] if out_sym and out_sym != name else [], "mentions": 0, "first_mention": loc[0] if loc else None,
         "definition_evidence": loc, "formula_ids": ["mf1"], "status": "defined_in_source"}]
    # The program's own extraction found no frequency sentence, but the reader cites one that the program verified
    # verbatim and that itself names the frequency (live J1: RSI "X days" -> daily). The quote is the evidence; nothing
    # is admitted without it (A/B D03u was blocked on "data frequency" although the user had given X).
    freq = fac.get("frequency") or {}
    if not s["A_supported"].get("frequency") and freq.get("status") == "PAPER":
        value = (freq.get("value") or "").lower()
        for c in freq.get("citations") or []:
            daily = value.startswith("daily") and re.search(DAYS_WORDS, c["quote"])
            named = any(value.startswith(n) and re.search(p, c["quote"], re.I) for n, p in FREQ_WORDS)
            b = next((x for x in evidence.doc["blocks"] if x["id"] == c.get("block_id")), None)
            k = b["text"].find(c["quote"]) if b else -1
            if (daily or named) and k >= 0:
                s["A_supported"]["frequency"] = [{
                    "field": "frequency", "status": "supported", "confidence": "low",
                    "value": f"{value.split()[0]} (reader's quote verified by the program: {c['quote'][:120]})",
                    "evidence": [{"location": {"doc_id": evidence.doc["doc_id"], "block_id": b["id"], "page": b["page"],
                                               "section": b["section"], "line": b["line"], "char_start": k,
                                               "char_end": k + len(c["quote"])}, "quote": c["quote"]}]}]
                break
    # The reader may leave frequency "unstated" on another run although the factor's OWN definition says it (A/B 14:03
    # D03u run 2, J1: "the average of X days price rises" -> blocked on "data frequency"). The program then reads the
    # factor's definition and parameter quotes itself: each must be found verbatim in the paper and name the unit.
    if not s["A_supported"].get("frequency"):
        own = list((fac.get("verbal_definition") or {}).get("citations") or []) + list((fac.get("formula") or {}).get("citations") or [])
        for p in fac.get("parameters") or []:
            own += list(p.get("citations") or [])
        for c in own:
            b = next((x for x in evidence.doc["blocks"] if x["id"] == c.get("block_id")), None)
            k = b["text"].find(c.get("quote") or "") if b and c.get("quote") else -1
            if k < 0:
                continue
            value = "daily" if re.search(DAYS_WORDS, c["quote"]) else next(
                (n for n, p in FREQ_WORDS if re.search(p, c["quote"], re.I)), None)
            if value:
                s["A_supported"]["frequency"] = [{
                    "field": "frequency", "status": "supported", "confidence": "low",
                    "value": f"{value} (the factor's own definition, verified verbatim by the program: {c['quote'][:120]})",
                    "evidence": [{"location": {"doc_id": evidence.doc["doc_id"], "block_id": b["id"], "page": b["page"],
                                               "section": b["section"], "line": b["line"], "char_start": k,
                                               "char_end": k + len(c["quote"])}, "quote": c["quote"]}]}]
                break
    return s


def _derive_window(sym, price_symbol, freq):
    agg, win = sym.get("aggregate"), sym.get("window") or {}
    unit = {"daily": "day", "weekly": "week", "monthly": "month", "quarterly": "quarter", "annual": "year"}.get(freq, "day")
    if not win.get("n") or win.get("unit") not in PERIODS:
        return None, "window length unknown"
    n = win["n"] * PERIODS[win["unit"]] / PERIODS[unit]
    if abs(n - round(n)) > 0.05:
        return None, f"window {win} is not a whole number of {unit}s"
    n = int(round(n))
    if agg == "ema":
        return rf"\operatorname{{ema}}_{{{n}}}({price_symbol}_{{i,t}})", None
    if agg in ("max", "min"):
        return rf"\{agg}_{{0 \le k \le {n - 1}}} {price_symbol}_{{i,t-k}}", None
    if agg in ("mean", "std"):
        return rf"\operatorname{{{agg}}}_{{k=0}}^{{{n - 1}}} ({price_symbol}_{{i,t-k}})", None
    if agg == "sum":
        return rf"\sum_{{k=0}}^{{{n - 1}}} {price_symbol}_{{i,t-k}}", None
    return None, f"aggregate {agg!r} not supported"


FIELD_LETTER = {"close": "C", "open": "O", "high": "H", "low": "L"}
ASSET_PHRASE = "用A股股票做探索性替代"


def _rhs(latex):
    """Right-hand side of 'NAME = expr': the first '=' outside braces ('_{k=0}' inside a bound is not a definition)."""
    depth = 0
    for i, ch in enumerate(latex):
        depth += (ch == "{") - (ch == "}")
        if ch == "=" and depth == 0:
            return latex[i + 1:].strip()
    return latex


def _periods(win, freq):
    """A window {n, unit} in the paper's own periods (whole numbers only), or None."""
    unit = {"daily": "day", "weekly": "week", "monthly": "month", "quarterly": "quarter", "annual": "year"}.get(freq, "day")
    if not win or not win.get("n") or win.get("unit") not in PERIODS:
        return None
    n = win["n"] * PERIODS[win["unit"]] / PERIODS[unit]
    return int(round(n)) if abs(n - round(n)) <= 0.05 else None


def _return_derivation(s, freq):
    """LaTeX for a return symbol from its declared semantics (price field, window, skip, compounding), or (None, why)."""
    field = s.get("data_field") if s.get("data_field") in PRICE else "close"
    p = FIELD_LETTER[field]
    log = (s.get("compounding") == "log") or bool(re.search(r"\blog|对数", s.get("meaning") or "", re.I))
    if s.get("kind") == "cumulative_return":
        n = _periods(s.get("window"), freq)
        if not n:
            return None, None, "look-back window of the cumulative return is not stated in whole paper periods"
        skip = _periods(s.get("skip"), freq) if s.get("skip") else 0
        if s.get("skip") and skip is None:
            return None, None, "skipped period is not stated in whole paper periods"
        a, b = (f"{p}_{{i,t-{skip}}}" if skip else f"{p}_{{i,t}}"), f"{p}_{{i,t-{skip + n}}}"
    else:
        a, b = f"{p}_{{i,t}}", f"{p}_{{i,t-1}}"
    latex = rf"\log(\frac{{{a}}}{{{b}}})" if log else rf"\frac{{{a}}}{{{b}}} - 1"
    return latex, (p, field), ("log" if log else "simple")


def _assets(evidence, understanding, fac):
    from .instruments import COMPILED, LABEL_CN, classify, scan
    pages = sorted({c["page"] for k in ("verbal_definition", "formula") for c in fac[k]["citations"] if c.get("page")} |
                   {c["page"] for s in fac["symbols"] for c in s["citations"] if c.get("page")})
    out = classify(scan(evidence.doc, pages), understanding.get("research_object"))
    # the factor's own inputs: a verified symbol quote that names another instrument decides for this factor
    own = {}
    for s in fac["symbols"]:
        text = " ".join(c["quote"] for c in s["citations"])
        for k, rx in COMPILED.items():
            if k not in ("equity_stock", "synthetic_data") and rx.search(text):
                own.setdefault(k, []).append({"symbol": s["symbol"], "quote": text[:200], "page": s["citations"][0].get("page")})
    if own:
        extra = [k for k in own if k not in out["blocking_classes"]]
        out["blocking_classes"] = out["blocking_classes"] + extra
        out["studied"] = list(dict.fromkeys(out["studied"] + list(own)))
        out["factor_inputs"] = own
        out["decision"] = "ASSET_CLASS_NOT_AVAILABLE"
        out["summary_cn"] = "、".join(LABEL_CN.get(k, k) for k in out["studied"] if k != "multi_asset")
    return out


def _algorithm_plan(spec, fac, data_profile, freq, hard, substitutions, notes, assets, horizon_days):
    """A factor the trusted grammar cannot express: a reviewed pair of model-written implementations (vectorised + an
    independently prompted literal reference) on published raw fields; the 2026 evaluator cannot recompute it."""
    algo = fac["algorithm"]
    syms = {s["symbol"]: s for s in fac["symbols"]}
    published = set(data_profile["fields"])
    inputs, symbol_map = [], {}
    for name in algo["inputs"]:
        s = syms.get(name) or {}
        field = s.get("data_field")
        if field == "returns" or s.get("kind") in ("period_return", "cumulative_return"):
            field = s.get("data_field") if s.get("data_field") in PRICE else "close"
            substitutions.append({"item": f"{name}: 收益", "kind": "derived_input", "paper": s.get("meaning") or "returns",
                                  "ours": "算法步骤由未复权收盘价自行计算收益（不含分红与复权调整）"})
        if field not in published:
            hard.append({"code": "FIELD_NOT_AVAILABLE", "symbol": name, "detail": f"needs {field!r}; published fields {sorted(published)}"})
            continue
        symbol_map[name] = {"field": field}
        inputs.append({"field": field, "symbol": name, "unit": {"volume": "shares", "amount": "currency"}.get(field, "currency/share"),
                       "dtype": "float64", "shape": "dates x securities", "basis": "published unadjusted daily panel"})
    lb = algo.get("lookback") or {}
    rows = None
    if lb.get("n") and lb.get("unit") in PERIODS:
        rows = int(round(lb["n"] * PERIODS[lb["unit"]]))
    if not rows:
        hard.append({"code": "ALGORITHM_LOOKBACK_UNSTATED", "detail": "the algorithm does not state how many past observations it reads"})
    if not inputs and not hard:
        hard.append({"code": "ALGORITHM_WITHOUT_INPUTS", "detail": "no published input field"})
    period_rows = ROWS_PER.get(freq)
    h = min(horizon_days or (period_rows or 1), 10)
    choices = {"label_lag": 1, "splits": data_profile["splits"], "independent_test": None, "data_certification": data_profile["certification"],
               "horizon": {"n": h, "unit": "trading_day"}}
    substitutions += [
        {"item": "实现方式", "kind": "algorithm_route", "paper": "论文用文字/步骤定义的算法（无法用可信算子语法表达）",
         "ours": "按原文步骤由模型编写两份独立实现（向量化实现 + 逐行参考实现），经你审核两份代码后，先在合成数据上要求两者逐格一致，再运行"},
        {"item": "2026 Test", "kind": "test_not_evaluable", "paper": "—",
         "ours": "受控评价器只运行可信代码、不运行模型代码：本研究的 2026 Test 将如实标为不可评价"},
        {"item": "price adjustment", "kind": "unadjusted_prices", "paper": "unstated", "ours": "raw unadjusted published prices"},
        {"item": "evaluation horizon", "kind": "evaluation_method", "paper": (fac.get("holding_period") or {}).get("value") or "unstated",
         "ours": f"{h}-trading-day forward open-to-open return"}]
    if freq and freq != "daily":
        substitutions.append({"item": "frequency", "kind": "frequency_conversion", "paper": freq, "ours": "daily rows, factor evaluated every day"})
    contract = {"entrypoint": "compute(panels) -> DataFrame", "inputs": inputs,
                "output": {"name": re.sub(r"[^a-z0-9_]", "_", (fac["name"] or "factor").lower())[:40], "dtype": "float64",
                           "shape": "same index/columns as inputs", "missing": "NaN until the declared look-back is observed; NaN propagates; inf -> NaN"},
                "time_alignment": "row t uses rows t-max_lag..t only; no negative lags, no centered windows, no backward fill",
                "warmup": {"min_lag": 0, "max_lag": (rows or 1) - 1, "observations_required": rows or 1, "uses_future": False},
                "rows_per_period": None, "panel_frequency": "daily rows", "ir": None,
                "algorithm": {"steps": algo["steps"], "lookback_rows": rows, "citations": algo["citations"][:4]}}
    status = "BLOCKED" if hard else "AWAITING_USER_DECISION"
    plan = {"schema": "paper_agent.plan/1.0", "factor": fac["name"], "status": status, "mode": "EXPLORATORY_REPLICATION",
            "route": None if hard else "algorithm", "model_suggestions_not_applied": [], "paper_frequency": freq, "hard_stops": hard,
            "substitutions": substitutions, "notes": notes, "data": {k: data_profile[k] for k in ("status", "adjustment", "units", "splits", "holdout")},
            "task_id": None, "admission": None, "dsl": None, "ir_paper": None,
            "ir_execution": "算法步骤：" + " → ".join(f"{i + 1}) {x}" for i, x in enumerate(algo["steps"])), "ir_execution_json": None,
            "warmup_rows": rows, "inputs": sorted({i["field"] for i in inputs}), "symbol_map": symbol_map, "choices": choices, "label": None,
            "assets": assets, "asset_consent_required": bool(assets and assets["decision"] == "ASSET_CLASS_NOT_AVAILABLE"),
            "timeline": [f"算法读取最近 {rows} 个交易日的 {'、'.join(sorted({i['field'] for i in inputs}))}（只用 t 及之前的行）"] if rows else [],
            "worked_examples": [], "algorithm_contract": contract}
    plan["definition_sha256"] = sha256_obj({k: plan[k] for k in ("factor", "mode", "route", "ir_execution", "symbol_map", "choices")}
                                           | {"contract": contract})
    return plan, None, spec


def plan(evidence, understanding, data_profile, *, factor=None, horizon_days=None):
    spec = evidence.spec
    facs = [f for f in understanding["factors"] if f["role"] in ("primary", "main", None) or True]
    mapped = None
    if factor:
        # a numbered factor (Alpha#12, #101) is that number only: "Alpha#1" is a substring of "Alpha#12" and a single
        # factor read from the paper must never stand in for another one (A/B N01: Alpha#12 was studied as Alpha#1)
        wanted = re.findall(r"#\s*(\d+)", factor)
        if wanted:
            facs = [f for f in facs if set(wanted) <= set(re.findall(r"#\s*(\d+)", f["name"] or ""))]
            if not facs:
                raise PlanError("FACTOR_NOT_UNDERSTOOD", f"{factor!r}: the paper's factors read do not include #{', #'.join(wanted)}: "
                                f"{[f['name'] for f in understanding['factors']]}")
        match = [f for f in facs if (f["name"] or "").lower() == factor.lower() or factor.lower() in (f["name"] or "").lower()
                 or (f["name"] or "").lower() in factor.lower()]
        if not match:                            # e.g. a Chinese name for an English factor: digits / Latin words, or the only factor
            toks = re.findall(r"[a-z]{3,}|\d+", factor.lower())
            score = [sum(t in (f["name"] or "").lower() for t in toks) for f in facs]
            best = max(score, default=0)
            match = [f for f, s in zip(facs, score) if best and s == best]
            if len(match) != 1:
                match = facs if len(facs) == 1 else []
            if match:
                mapped = f"requested factor {factor!r} mapped to the paper's factor {match[0]['name']!r}"
        if not match:
            raise PlanError("FACTOR_NOT_UNDERSTOOD", f"{factor!r} is not among the factors read from the paper: {[f['name'] for f in facs]}")
        facs = match
    if not facs:
        raise PlanError("NO_FACTOR_UNDERSTOOD", "the model did not identify a factor")
    if not factor and len(facs) > 1:
        # several factors and no instruction: one marked primary is the paper's main factor; otherwise ask, never pick blindly.
        # A paper about options/futures/bonds/FX/funds/crypto is reported as such first: choosing among its factors is moot.
        from .instruments import classify, scan
        doc_assets = classify(scan(evidence.doc), understanding.get("research_object"))
        moot = set(doc_assets["blocking_classes"]) & {"futures", "options", "bonds_rates", "fx", "etf_fund", "crypto"}
        # the reader's "primary" label is not stable across readings (A/B E01: two readings chose MA+BOLL and MA+MACD),
        # so the user chooses; only a paper whose assets rule it out anyway is reported without a choice
        primaries = (([f for f in facs if (f.get("role") or "").lower() in ("primary", "main")] or facs)[:1]) if moot else []
        if len(primaries) != 1:
            raise PlanError("FACTOR_CHOICE_REQUIRED", f"the paper defines several factors: {[f['name'] for f in facs]}")
        facs = primaries
    fac = facs[0]
    hard, substitutions, notes = [], [], [mapped] if mapped else []
    if fac["status"] == "BLOCKED":
        hard += [{"code": c["code"], "detail": c.get("detail"), "symbol": c.get("symbol"), "source": c.get("source"),
                  "source_cn": c.get("source_cn")} for c in fac["conflicts"] if c["blocking"]]
    # ---------------- the paper's research object (whole document, the factor's pages, its own input quotes)
    assets = _assets(evidence, understanding, fac)
    if assets["decision"] == "ASSET_CLASS_NOT_AVAILABLE":
        ev = next((e for k in assets["blocking_classes"] for e in (assets.get("factor_inputs", {}).get(k) or assets["evidence"].get(k) or [])), {})
        substitutions.append({"item": "研究资产（非忠实复现）", "kind": "asset_substitution",
                              "paper": f"{assets['summary_cn']}；证据：p{ev.get('page')}“{(ev.get('quote') or '')[:160]}”",
                              "ours": "A股个股日频数据。资产不同，这不是论文复现，原论文的结论不能沿用到本次结果"})
    elif assets["decision"] == "SYNTHETIC_DATA_PAPER":
        ev = (assets["evidence"].get("synthetic_data") or [{}])[0]
        substitutions.append({"item": "研究数据对象", "kind": "data_object",
                              "paper": f"原文实证使用合成/模拟数据（p{ev.get('page')}“{(ev.get('quote') or '')[:140]}”）",
                              "ours": "A股个股真实日频数据：指标在真实市场上的探索性应用，不是论文实证的复现"})
    if assets.get("model_unconfirmed"):
        from .instruments import LABEL_CN
        sc = assets.get("score") or {}
        names = "、".join(LABEL_CN.get(k, k) for k in assets["model_unconfirmed"])
        substitutions.append({"item": "研究资产（AI 与程序判断不一致）", "kind": "interpretation",
                              "paper": f"AI 读取的研究对象还包括{names}（引文：“{'；'.join(assets.get('model_unconfirmed_quotes') or [])[:160]}”）",
                              "ours": f"程序全文统计以个股为主（个股 {sc.get('equity_stock')}，"
                                      + "、".join(f"{LABEL_CN.get(k, k)} {sc.get(k)}" for k in assets["model_unconfirmed"])
                                      + "），按A股个股研究；若该因子实际针对上述资产，请回复“拒绝”"})
    for c in fac["conflicts"]:
        if c["code"] == "PARAMETER_CHOSEN_NOT_IN_PAPER":
            user = [p for p in fac.get("parameters") or [] if p.get("status") == "USER"]
            substitutions.append({"item": "参数选择", "kind": "parameter_choice",
                                  "paper": "原文没有给出该数值" + ("（论文把它留作自由参数）" if user else ""),
                                  "ours": ("用户指定：" + "、".join(f"{p['symbol']}={p['value']}" for p in user)) if user else c["detail"]})
        if c["code"] == "PARAMETER_SELECTED_FROM_PAPER_VALUES":
            substitutions.append({"item": f"参数 {c['symbol']} 取值", "kind": "parameter_choice",
                                  "paper": f"原文测试过多个取值 {c.get('values')}", "ours": c["detail"]})
        if c["code"] == "RETURN_INTERPRETED_FROM_MOMENTUM_WORDING":
            substitutions.append({"item": f"{c['symbol']}: 含义解释", "kind": "interpretation",
                                  "paper": "原文未给出收益的明确定义", "ours": c["detail"]})
    # every value the user typed is shown as the user's choice, wherever it is used (formula or a derived symbol)
    user = [p for p in fac.get("parameters") or [] if p.get("status") == "USER"]
    if user and not any(s["kind"] == "parameter_choice" and s["ours"].startswith("用户指定") for s in substitutions):
        substitutions.append({"item": "参数选择", "kind": "parameter_choice", "paper": "原文没有给出该数值（论文把它留作自由参数）",
                              "ours": "用户指定：" + "、".join(f"{p['symbol']}={p['value']}" for p in user)})
    freq = _freq(fac, spec)
    # ---------------- choose the formula source: the layout-rebuilt v0.3 formula if it matches, else the model's
    spec_used, factor_name = spec, None
    v03 = fac["formula"].get("v03_formula")
    if v03:
        vf = next((f for f in spec["factors"] if v03["id"] in f["formula_ids"]), None)
        if vf:
            factor_name = vf["name"]
            notes.append(f"formula from the PDF layout ({v03['id']}, p{v03['page']}); the model's reading agrees on its symbols")
    if fac["formula"].get("status") == "ALGORITHM" and fac.get("algorithm"):
        return _algorithm_plan(spec, fac, data_profile, freq, hard, substitutions, notes, assets, horizon_days)
    if factor_name is None and not hard:
        try:
            parse_formula(fac["formula"]["latex"])
        except (IRError, ValueError):
            hard.append({"code": "FORMULA_UNPARSEABLE", "detail": fac["formula"]["latex"]})
        else:
            spec_used = _augment_spec(spec, fac, evidence)
            factor_name = fac["name"]
            if fac["formula"]["status"] == "DERIVED":
                substitutions.append({"item": "formula", "paper": "formula printed in the paper is not machine-readable",
                                      "ours": f"restated from the cited prose: {fac['formula']['latex']}",
                                      "kind": "formula_restatement"})
    if hard:
        return _result(spec, fac, None, None, None, hard, substitutions, notes, data_profile, freq, assets=assets)
    # ---------------- automatic host choices (all recorded as host_choice; nothing changes the paper silently)
    ir0 = parse_formula(next(f for f in spec_used["formulas"] if f["id"] in next(
        x for x in spec_used["factors"] if x["name"] == factor_name)["formula_ids"])["latex"] or "")["ir"]
    syms = {s["symbol"]: s for s in fac["symbols"]}
    # symbols the model named differently: fall back to the deterministic reading of the paper's own definition
    fdef = next(f for f in spec_used["formulas"] if f["id"] in next(x for x in spec_used["factors"] if x["name"] == factor_name)["formula_ids"])
    for name in fields_used(ir0):
        if name not in syms and (fdef.get("defined_variables") or {}).get(name):
            det = interpret_definition(fdef["defined_variables"][name]["definition"])
            base = "close" if det["base"] in (None, "price_unspecified") else det["base"]
            syms[name] = {"symbol": name, "kind": "window_aggregate" if det["kind"] == "window_aggregate" else "raw_field",
                          "data_field": base, "aggregate": det["aggregate"],
                          "window": {"n": det["window"]["n"], "unit": det["window"]["unit"]} if det["window"] else None,
                          "price_basis": "unstated", "source": "deterministic_v03"}
    published = set(data_profile["fields"])
    symbol_map, extra = {}, {}
    price_symbol = None
    for name in fields_used(ir0):
        s = syms.get(name)
        if s is None:
            continue
        if s.get("kind") in ("raw_field", "derived") and s.get("data_field") in PRICE:
            price_symbol = price_symbol or name
    for name in fields_used(ir0):
        s = syms.get(name) or {}
        kind, field = s.get("kind"), s.get("data_field")
        if NON_EQUITY.search(s.get("meaning") or ""):
            # a different instrument is not a substitution: stock prices cannot stand in for option/bond/FX data
            hard.append({"code": "INSTRUMENT_NOT_AVAILABLE", "symbol": name,
                         "detail": f"{name} = {(s.get('meaning') or '')[:140]!r}; the published data hold A-share stock prices only"})
            continue
        if kind in ("cumulative_return", "period_return") or (field == "returns" and "returns" not in published):
            # returns are computed from the declared semantics: one period or a look-back window (with skip), simple or log
            latex, letter, comp = _return_derivation(s, freq)
            if latex is None:
                hard.append({"code": "RETURN_NOT_DERIVABLE", "symbol": name, "detail": comp})
                continue
            symbol_map[name] = {"derive": latex}
            extra[letter[0]] = letter[1]
            cum = kind == "cumulative_return"
            substitutions.append({"item": f"{name}: {'累计' if cum else '单期'}收益", "paper": s.get("meaning") or "returns",
                                  "ours": f"由未复权{ {'close': '收盘价', 'open': '开盘价', 'high': '最高价', 'low': '最低价'}[letter[1]] }计算的"
                                          f"{'对数' if comp == 'log' else '简单'}{'累计' if cum else '单期'}收益（{latex}；不含分红与复权调整）",
                                  "kind": "derived_input"})
            continue
        if kind == "derived" and s.get("derivation_latex"):
            # a quantity the paper defines by its own formula: substituted, with every inner symbol mapped to a field
            try:
                inner = fields_used(parse_formula(s["derivation_latex"])["ir"])
            except (IRError, ValueError) as exc:
                hard.append({"code": "DERIVATION_UNPARSEABLE", "symbol": name, "detail": f"{s['derivation_latex']}: {exc}"})
                continue
            missing = [x for x in inner if (syms.get(x) or {}).get("data_field") not in published]
            if missing:
                hard.append({"code": "SYMBOL_UNDEFINED", "symbol": name,
                             "detail": f"{name} = {s['derivation_latex']} 需要 {missing}，它们没有映射到已发布字段"})
                continue
            symbol_map[name] = {"derive": _rhs(s["derivation_latex"])}
            for x in inner:
                extra[x] = syms[x]["data_field"]
            continue
        if kind == "window_aggregate":
            base = price_symbol or "P"
            if field in ("high", "low"):                      # maximum of daily highs / minimum of daily lows
                base = {"high": "H", "low": "L"}[field]
                extra[base] = field
            derive, why = _derive_window(s, base, freq)
            if derive is None:
                hard.append({"code": "WINDOW_NOT_DERIVABLE", "symbol": name, "detail": why})
                continue
            symbol_map[name] = {"derive": derive}
            if base not in syms and base not in symbol_map and base not in extra:
                extra[base] = "close"
            basis = (s.get("price_basis") or "unstated")
            substitutions.append({"item": f"{name}: price basis of the {s.get('aggregate')}", "paper": basis,
                                  "ours": {"high": "daily intraday high prices inside the window",
                                           "low": "daily intraday low prices inside the window"}.get(field, "daily closing prices inside the window"),
                                  "kind": "price_basis"})
        elif field == "returns" and "returns" not in published:
            symbol_map[name] = {"derive": r"\frac{C_{i,t}}{C_{i,t-1}} - 1"}
            extra["C"] = "close"
            substitutions.append({"item": f"{name}: returns", "paper": s.get("meaning") or "returns",
                                  "ours": "close-to-close price change of the published unadjusted close (no dividends, no corporate-action adjustment)",
                                  "kind": "derived_input"})
        elif field in published:
            symbol_map[name] = {"field": field}
            if field == "amount":
                notes.append(f"{name} = published amount, unit {data_profile['units'].get('amount')}; a constant scale does not change ranks/IC")
            if field == "volume":
                notes.append(f"{name} = published volume, unit {data_profile['units'].get('volume')}")
        elif field in (None, "unknown", "other", "market_cap") or field not in published:
            hard.append({"code": "FIELD_NOT_AVAILABLE", "symbol": name, "detail": f"needs {field!r}; published fields {sorted(published)}"})
    for sym, fld in extra.items():
        symbol_map[sym] = {"field": fld}
    # price inputs compared across dates on unadjusted data: an explicit, recorded deviation
    probe = build_research_task(spec_used, factor=factor_name, symbol_map=symbol_map) if not hard else None
    if probe is not None:
        for u in probe["unresolved"]:
            if u["item"].startswith("price adjustment for "):
                sym = u["item"].rsplit(" ", 1)[1]
                symbol_map[sym] = dict(symbol_map.get(sym, {"field": "close"}), adjustment="none", deviates_from_paper=True,
                                       reason=f"published data are unadjusted ({data_profile['adjustment']}); exploratory only")
                stated = "uses adjusted prices" in (u.get("question") or "")
                substitutions.append({"item": f"{sym}: 价格复权口径", "kind": "unadjusted_prices",
                                      "paper": "论文明确使用复权价格" if stated else "论文比较不同日期的价格，未写明复权方式",
                                      "ours": "已发布数据只有未复权价格：拆股、分红会造成虚假跳变，结果只能作探索性参考"
                                              + ("（与论文口径不同，需你确认）" if stated else "")})
    reps = [r for r in understanding.get("formula_repairs") or [] if r["factor"] == fac["name"]]
    used = None
    if reps:                                     # one entry: the paper's restated window vs the repair that actually parsed
        used = next((r for r in reversed(reps) if r.get("parses_after_repair", True)), reps[-1])
        substitutions.append({"item": "formula window (repaired restatement)", "kind": "window_approximation",
                              "paper": reps[0]["error"][:160] + " | model's first restatement (not parseable)",
                              "ours": f"{used['repaired']} -- {(used.get('note') or {}).get('choice', 'nominal fixed-length window')}"
                                      f" (repair attempts: {len(reps)}; window unit: {used.get('window_unit') or 'unstated'})"})
    suggestions = [f"{n.get('choice')} ({n.get('reason')})" for n in fac.get("replication_notes") or []]
    # a model suggestion that contradicts the price basis this plan uses is surfaced, never silently ignored
    for name, sm in symbol_map.items():
        if sm.get("derive") and any(k in sm["derive"] for k in ("H_{", "L_{")) and any(re.search(r"clos", x, re.I) for x in suggestions):
            substitutions.append({"item": f"price basis conflict ({name})", "kind": "price_basis",
                                  "paper": "unstated (the model's replication note suggests closing prices)",
                                  "ours": "daily intraday highs/lows inside the window, as the model's symbol reading and the approved implementation use"})
    rows = ROWS_PER.get(freq)
    if rows and used is not None:
        # A repaired window counts either the paper's periods or trading days; converting a trading-day count again by
        # rows-per-period would silently multiply every lag and window (e.g. 250 trading days -> 1250).
        if used.get("window_unit") == "trading_day":
            rows = None
            substitutions.append({"item": "frequency", "paper": freq,
                                  "ours": "formula restated in trading days by the window repair: lags and windows count daily rows, "
                                          "inputs are daily changes, factor evaluated every day", "kind": "frequency_conversion"})
        elif used.get("window_unit") != "paper_period":
            hard.append({"code": "WINDOW_UNIT_AMBIGUOUS",
                         "detail": f"the repaired window does not state whether it counts trading days or {freq} periods"})
    choices = {"label_lag": 1, "splits": data_profile["splits"], "independent_test": None,
               "data_certification": data_profile["certification"]}
    if not spec_used["A_supported"].get("universe"):
        choices["universe"] = data_profile.get("universe", "published A-share code axis of the GPUShare release")
        notes.append("universe: the paper states none; host choice = " + choices["universe"])
    if rows:
        choices["time_unit_rows"] = {"rows": rows, "deviates_from_paper": True,
                                     "reason": f"daily A-share panel; {rows} trading days per {freq[:-2] if freq != 'daily' else 'day'} period"}
        substitutions.append({"item": "frequency", "paper": freq, "ours": f"daily rows ({rows} trading days per period), factor evaluated every day",
                              "kind": "frequency_conversion"})
    hold = fac["holding_period"]["value"] or ""
    # the Agent's evaluation (research_metrics) accepts label horizons of 1..10 observation days; a non-daily paper keeps
    # one paper period as the label (weekly -> 5, monthly and longer -> capped at 10)
    period_rows = ROWS_PER.get(freq)
    h = min(horizon_days or (period_rows or 1), 10)
    choices["horizon"] = {"n": h, "unit": "trading_day"}
    notes.append(f"evaluation label: next-open to open return over {h} trading days (paper holding period: {hold or 'unstated'})")
    m = re.match(r"\s*(\d+|one)\s*(trading\s*)?days?\b", hold, re.I)
    same = bool(m) and (1 if m.group(1).lower() == "one" else int(m.group(1))) == h
    # stated and different -> confirmable substitution; unstated -> host choice kept in notes (shown at decisions)
    if period_rows or (hold and not hold.lower().startswith("unstated") and not same):
        substitutions.append({"item": "evaluation horizon", "paper": hold or "unstated",
                              "ours": f"{h}-trading-day forward open-to-open return (the Agent's evaluator supports 1-10 days)",
                              "kind": "evaluation_method"})
    if fac["portfolio_rules"]["value"] and not str(fac["portfolio_rules"]["value"]).lower().startswith("unstated"):
        substitutions.append({"item": "portfolio rules", "paper": fac["portfolio_rules"]["value"],
                              "ours": "cross-sectional IC/RankIC and gross quantile groups; the paper's portfolio construction is not replicated",
                              "kind": "evaluation_method"})
    if hard:
        return _result(spec_used, fac, None, symbol_map, choices, hard, substitutions, notes, data_profile, freq, assets=assets)
    task = build_research_task(spec_used, factor=factor_name, symbol_map=symbol_map, choices=choices)
    if rows and (task.get("time_basis") or {}).get("rows_per_period") != rows:
        # the PDF's own frequency statement reads daily, so the task runs the formula unscaled: the plan must say so
        choices.pop("time_unit_rows")
        substitutions = [s for s in substitutions if s["kind"] != "frequency_conversion"] + [
            {"item": "frequency", "paper": freq, "kind": "frequency_conversion",
             "ours": "the paper's data statement reads daily: lags and windows run on daily rows unchanged, factor evaluated every day"}]
        task = build_research_task(spec_used, factor=factor_name, symbol_map=symbol_map, choices=choices)
    # definition -> execution: each return symbol's declared semantics, computed by hand, must equal its executed derivation
    from .semantics import check_return_derivations
    dconf, examples = check_return_derivations(fac, symbol_map, ((choices or {}).get("time_unit_rows") or {}).get("rows"), freq)
    hard += [{"code": c["code"], "symbol": c["symbol"], "detail": c["detail"]} for c in dconf]
    return _result(spec_used, fac, task, symbol_map, choices, hard, substitutions, notes, data_profile, freq, assets=assets,
                   examples=examples)


def _result(spec_used, fac, task, symbol_map, choices, hard, substitutions, notes, data_profile, freq, assets=None, examples=None):
    adm = task["admission"] if task else None
    exec_ir0 = (task["factor"]["ir_execution"] or task["factor"]["ir"]) if task else None
    for n in (walk(exec_ir0) if exec_ir0 else []):
        if n["op"] == "ema":
            # textbook EMA recursions start at the first observation; ours uses the last W rows (stated, user-confirmed)
            item = f"指数平滑递归截断（N={n['n']}）"
            if not any(x["item"] == item for x in substitutions):
                substitutions.append({"item": item, "kind": "recursion_truncation",
                                      "paper": "递归从序列起点开始（软件实现通常如此）",
                                      "ours": f"每个值只用最近 W={n['window']} 个交易日递归，种子={'窗口首值' if n['init'] == 'first' else '前N日均值'}，"
                                              f"截断残余权重 {n['seed_weight']:.1e}；保证 Train 与 2026 Test 由相同长度历史得到相同数值"})
    if task:
        for gate in SEVERE_GATES:
            for item in adm["gates"][gate]["blocking_items"]:
                hard.append({"code": f"ADMISSION_{gate.upper()}", "detail": item})
        if task["lookback"]["formula_warmup"] and task["lookback"]["formula_warmup"]["uses_future"]:
            hard.append({"code": "FUTURE_REFERENCE", "detail": "formula uses future data"})
        # the executing Agent refuses a study whose history need exceeds the Train panel; say so before any decision or code
        lookback = warmup(task["factor"]["ir_execution"] or task["factor"]["ir"])["observations_required"]
        est, h = data_profile.get("train_rows_estimate"), (choices or {}).get("horizon", {}).get("n", 1)
        if est and lookback + h + 10 > est:
            hard.append({"code": "LOOKBACK_EXCEEDS_SAMPLE",
                         "detail": f"needs {lookback} trading days of history plus a {h}-day label; the published Train sample has about {est}"})
    route = None
    if task and not hard:
        # DSL first; otherwise the reviewed Factor-IR executor computes the frozen IR (no model code). A model-written
        # implementation is only needed for algorithms the IR cannot express (they never reach this point as an IR).
        route = "dsl" if task["dsl"]["status"] == "expressible" else "trusted_ir"
    data_only = task is not None and not hard and adm["state"] in ("DATA_UNCERTIFIED", "CANDIDATE_ONLY", "READY_FOR_REVIEW_DSL")
    definition_changes = [s for s in substitutions if s["kind"] != "evaluation_method"]
    mode = "PAPER_ORIGINAL" if (data_only and not definition_changes and adm["state"] == "READY_FOR_REVIEW_DSL") else "EXPLORATORY_REPLICATION"
    status = "BLOCKED" if hard else ("AWAITING_USER_DECISION" if definition_changes else "READY")
    exec_ir = (task["factor"]["ir_execution"] or task["factor"]["ir"]) if task else None
    plan = {"schema": "paper_agent.plan/1.0", "factor": fac["name"], "status": status, "mode": mode, "route": route,
            "model_suggestions_not_applied": [f"{n.get('choice')} ({n.get('reason')})" for n in fac.get("replication_notes") or []],
            "paper_frequency": freq, "hard_stops": hard, "substitutions": substitutions, "notes": notes,
            "data": {k: data_profile[k] for k in ("status", "adjustment", "units", "splits", "holdout")},
            "task_id": task["task_id"] if task else None, "admission": adm,
            "dsl": {"status": task["dsl"]["status"], "reasons": task["dsl"]["reasons"], "expression": task["dsl"].get("expression")} if task else None,
            "ir_paper": task["factor"]["ir_rendered"] if task else None,
            "ir_execution": render(exec_ir) if exec_ir else None, "ir_execution_json": exec_ir,
            "warmup_rows": warmup(exec_ir)["observations_required"] if exec_ir else None,
            "inputs": sorted({s["field"] for s in task["factor"]["symbols"] if s.get("field")}) if task else [],
            "symbol_map": symbol_map, "choices": choices, "label": task["label"] if task else None,
            "assets": assets, "asset_consent_required": bool(assets and assets["decision"] == "ASSET_CLASS_NOT_AVAILABLE"),
            "timeline": _timeline(exec_ir, symbol_map) if exec_ir else [], "worked_examples": examples or []}
    plan["definition_sha256"] = sha256_obj({k: plan[k] for k in ("factor", "mode", "route", "ir_execution", "symbol_map", "choices")})
    return plan, task, spec_used


def _timeline(ir, symbol_map):
    from .semantics import timeline
    cn = {"close": "收盘价", "open": "开盘价", "high": "最高价", "low": "最低价", "volume": "成交量", "amount": "成交额"}
    names = {k: cn.get(v.get("field"), k) for k, v in (symbol_map or {}).items() if v.get("field")}
    return timeline(ir, names)


FREQ_CN = {"weekly": "周频", "monthly": "月频", "quarterly": "季频", "annual": "年频"}


def decision_question(plan):
    """One short question naming what the user is asked to accept; details follow it."""
    kinds = {s["kind"] for s in plan["substitutions"]}
    if plan.get("asset_consent_required"):
        return (f"论文的研究对象是{(plan.get('assets') or {}).get('summary_cn') or '非A股个股资产'}，当前只有A股个股数据，无法忠实复现。"
                f"如仍要用A股个股做非忠实的探索性替代（结果不能代表原论文），请回复“{ASSET_PHRASE}”；回复其他内容都不会运行。")
    parts = []
    if plan.get("warmup_rows"):
        parts.append(f"约{plan['warmup_rows']}个交易日的回看窗口")
    if "unadjusted_prices" in kinds:
        parts.append("未复权价格")
    if "frequency_conversion" in kinds and plan.get("paper_frequency") in FREQ_CN:
        parts.append(f"日频数据（论文为{FREQ_CN[plan['paper_frequency']]}）")
    if "formula_restatement" in kinds:
        parts.append("按原文文字重述的公式")
    h = ((plan.get("choices") or {}).get("horizon") or {}).get("n")
    if h:
        parts.append(f"{h}日预测期")
    return f"该论文需要使用{'、'.join(parts) or '以下替代口径'}进行探索性研究，是否继续？"


def decision_text(plan):
    """Concise question, then the exact computation, then each substitution; long model suggestions come last."""
    lines = [decision_question(plan),
             f"实际执行（按交易日行计）：{plan['ir_execution']}；需要 {plan['warmup_rows']} 个交易日历史"
             f"（约 {plan['warmup_rows'] / 250:.1f} 年）。",
             f"论文因子「{plan['factor']}」无法在当前数据上忠实复现；确认后作为【探索性替代实验】运行，不称为论文复现，也不作为可交易结论。替代项："]
    if plan.get("timeline"):
        lines[2:2] = ["时间轴说明（程序根据执行公式生成）："] + [f"  · {x}" for x in plan["timeline"][:8]]
    for e in (plan.get("worked_examples") or [])[:4]:
        lines.insert(2, f"  · 数值核对 {e['symbol']}：构造价格路径上 {e['price_window_start']:.4f} → {e['price_t_minus_skip']:.4f}"
                        f"（回看{e['n_rows']}行、跳过{e['skip_rows']}行，{'对数' if e['compounding'] == 'log' else '简单'}收益）"
                        f"= {e['declared_value']:.6f}；执行公式 = {e['executed_value']:.6f}，{'一致' if e['match'] else '不一致'}")
    for s in plan["substitutions"]:
        lines.append(f"- {s['item']}：论文 = {str(s['paper'])[:220]}；本次 = {str(s['ours'])[:260]}")
    if plan.get("notes"):
        lines.append("论文未规定、由本系统选定的研究设置（同样随本次确认生效）：")
        lines += [f"  · {x}" for x in plan["notes"][:8]]
    lines.append(f"- 数据：{plan['data']['status']}，价格{plan['data']['adjustment']}；Train {plan['data']['splits']['train']}，"
                 f"Validation {plan['data']['splits']['valid']}；2026 Holdout 不可读")
    if plan.get("model_suggestions_not_applied"):
        lines.append("模型提出的复现建议（仅供参考，本计划没有自动采用）：")
        lines += [f"  · {x[:200]}" for x in plan["model_suggestions_not_applied"][:4]]
    return "\n".join(lines)
