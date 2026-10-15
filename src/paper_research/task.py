"""Paper -> research task: an executable research specification built from an evidence-grounded spec.

Every statement in a task carries its basis:
  paper        verbatim evidence from the document (A items, formulas, defined variables)
  inference    derived mathematically from paper content (warmup from formula lags, units); needs review
  host_choice  decided by the host/researcher (symbol mapping, label lag, independent test window); recorded
  missing      not available; listed in `unresolved` with a question
A task is "blocked" while any blocking item is unresolved and otherwise "ready_for_review". It is never
"approved": approval, execution and data access belong to the host.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from qrtk_skills.runtime import validate as validate_schema

from . import dsl as D
from .errors import PaperError
from .extract import EXTRACTOR
from .factor_ir import IR_VERSION, IRError, fields_used, parse_formula, render, walk, warmup

TASK_SCHEMA = "paper_research.task/1.1"
BUILDER = {"name": "paper_research.task_builder", "version": "0.2.0"}
REQUIRED_METRICS = ["IC", "RankIC", "coverage", "stability"]

SEMANTIC = [  # definition text -> semantic input; order matters (first match wins)
    ("amount", r"dollar (trading )?volume|volume in (dollars|yuan|rmb|currency)|(trading|traded|turnover) value|amount|成交额|成交金额"),
    ("market_cap", r"market (cap|value)|市值"),
    ("book_equity", r"book (equity|value)|账面"),
    ("returns", r"\breturns?\b|收益率"),
    ("volume", r"(share |trading )?volume|成交量"),
    # the same-day high/low fields only when the text says so; "highest price during ..." is an aggregate
    ("high", r"\b(daily|intraday) high\b|\bhigh price (of|on) (the )?(day|date)|日内最高价|当日最高价|^最高价$|(?<!过去)(?<!期间)最高价"),
    ("low", r"\b(daily|intraday) low\b|\blow price (of|on) (the )?(day|date)|日内最低价|当日最低价|(?<!过去)(?<!期间)最低价"),
    ("open", r"open(ing)? price|开盘价"),
    ("close", r"(clos\w+ )?price|收盘价|价格"),
]
AGGREGATE = [("max", r"\b(highest|maximum|max|peak)\b|最高(?!价)"), ("min", r"\b(lowest|minimum|min|trough)\b|最低(?!价)"),
             ("mean", r"\b(average|mean)\b|平均|均值"), ("sum", r"\b(sum|total|cumulative)\b|累计|总和"),
             ("std", r"\b(standard deviation|volatility)\b|标准差|波动率")]
_N = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|sixty)"
WINDOW_RX = [re.compile(rf"\b(?:during|over|in|within|for|across|of)\s+(?:the|a)?\s*(?:past|previous|prior|last|preceding|trailing)?\s*"
                        rf"(?P<n>{_N})[- ](?P<trd>trading[- ])?(?P<unit>day|week|month|quarter|year)s?\b", re.I),
             re.compile(rf"\b(?:past|previous|prior|last|preceding|trailing)\s+(?P<n>{_N})[- ]?(?P<trd>trading[- ])?(?P<unit>day|week|month|quarter|year)s?\b", re.I),
             re.compile(r"\b(?P<n>\d+)[- ](?P<unit>day|week|month|year)[- ](?:high|low)s?\b", re.I),
             re.compile(r"(?:过去|最近|前)\s*(?P<n>\d+)\s*(?:个)?(?P<unit>交易日|日|天|周|个月|月|年)")]
UNIT_ZH = {"交易日": "trading_day", "日": "day", "天": "day", "周": "week", "个月": "month", "月": "month", "年": "year"}
WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "sixty": 60}
# approximate trading periods per unit, used only to compare a host derivation with the paper's stated window
PERIODS = {"trading_day": 1, "day": 1, "week": 5, "month": 21, "quarter": 63, "year": 252}
FREQ_UNIT = {"daily": "day", "weekly": "week", "monthly": "month", "quarterly": "quarter", "annual": "year"}
PRICE_FIELDS = {"close", "open", "high", "low"}


def interpret_definition(text: str | None) -> dict:
    """Read a variable's verbal definition: base quantity, aggregation over a window, sampling point, adjustment.

    kind: 'raw'               a field observed at one date (price, volume, ...)
          'window_aggregate'  an aggregate (max/min/mean/sum/std) over a stated window -- a derived input, never a raw field
          'ambiguous'         an aggregate word without a stated window, or nothing recognisable
    """
    if not text:
        return {"kind": "ambiguous", "base": None, "aggregate": None, "window": None, "sampling": None,
                "adjustment": "unstated", "text": text}
    agg = next((name for name, pat in AGGREGATE if re.search(pat, text, re.I)), None)
    raw_hl = next((name for name in ("high", "low") if re.search(dict(SEMANTIC)[name], text, re.I)), None)
    win = None
    for rx in WINDOW_RX:
        m = rx.search(text)
        if m:
            n = m.group("n")
            n = int(n) if n.isdigit() else WORDN.get(n.lower())
            u = m.group("unit")
            unit = UNIT_ZH.get(u, ("trading_day" if (m.groupdict().get("trd") and u.lower().startswith("day")) else u.lower()))
            win = {"n": n, "unit": unit, "text": m.group(0)}
            break
    if win and agg is None and re.search(r"最高价|最低价", text):
        agg, raw_hl = ("max", "high") if "最高价" in text else ("min", "low")
    if raw_hl:
        base = raw_hl                  # the high/low price field itself ("当日最高价", "daily high")
    elif re.search(r"\bclos\w*|收盘", text, re.I):
        base = "close"
    elif re.search(r"\bopen(ing)?\s+price|\bopen\b|开盘", text, re.I) and not re.search(r"\bopen(ed|s)?\s+(a|the)?\s*position", text, re.I):
        base = "open"
    elif re.search(r"\bintraday\b|\bdaily high\b|\bdaily low\b|日内", text, re.I):
        base = "high" if re.search(r"high|最高", text, re.I) else "low"
    elif re.search(r"\bprices?\b|价", text, re.I):
        base = "price_unspecified"
    else:
        base = next((name for name, pat in SEMANTIC if re.search(pat, text, re.I)), None)
    sampling = ("period_end" if re.search(r"\b(at )?the end of (the |each |every )?(month|week|quarter|year)\b|月末|周末|季末|年末", text, re.I)
                else "daily" if re.search(r"\bdaily\b|\bon day\b|日频|每日", text, re.I) else None)
    adjustment = ("none" if re.search(r"\bunadjusted\b|\braw prices?\b|未复权|不复权", text, re.I)
                  else "adjusted" if re.search(r"adjust|复权", text, re.I) else "unstated")
    if agg and win:
        kind = "window_aggregate"
    elif agg and not re.search(r"\b(daily|intraday)\b|日内|当日", text, re.I):
        kind = "ambiguous"
    else:
        kind = "raw"
        if base == "price_unspecified":
            base = "close"           # a single price observation; the closing price is the convention (inference)
        elif base is None:
            base = next((name for name, pat in SEMANTIC if re.search(pat, text, re.I)), None)
        if base is None:
            kind = "ambiguous"
    return {"kind": kind, "base": base, "aggregate": agg, "window": win, "sampling": sampling,
            "adjustment": adjustment, "text": text}


def _window_in_periods(win, freq):
    unit = FREQ_UNIT.get(freq)
    if not win or not unit:
        return None
    return win["n"] * PERIODS[win["unit"]] / PERIODS[unit]


def _derive_window(macro):
    """(aggregate, length in periods) of the outermost window aggregate of a derivation, or (None, None)."""
    for n in walk(macro):
        if n["op"].startswith("ts_"):
            return n["op"][3:], n["end"] - n["start"] + 1
    return None, None


def _cross_time_prices(ir, price_symbols):
    """True when a price input is compared across dates (inside a window, or at two different lags)."""
    lags = {}
    in_window = False

    def visit(node, inside):
        nonlocal in_window
        if node["op"] == "field" and node["symbol"] in price_symbols:
            lags.setdefault(node["symbol"], set()).add((node["lag"]["base"], node["lag"].get("var")))
            in_window = in_window or inside
        for a in node.get("args", []):
            visit(a, inside or node["op"].startswith("ts_") or node["op"] == "ema")
    visit(ir, False)
    # different price fields at the same date (e.g. (C-O)/(H-L)) are not a comparison across dates
    return in_window or len(set().union(*lags.values())) > 1 if lags else in_window


def _common_lag(ir):
    """L when every input is observed at the same constant lag L >= 1 (the paper indexes the formation date as t-L).

    An input inside a window counts by its most recent observation (field lag + window start): P_{t-1} / max_{0<=k<=11}
    P_{t-1-k} dates both inputs at t-1 exactly like P_{t-1} / high_{t-1} (live A/B D09: the window version kept the month
    and ran one month stale). With a window, at least two input occurrences must agree, so a single skipped window such
    as mean_{k=2}^{12} r_{t-k} keeps its skip. Recursive smoothing (ema) is never re-dated."""
    recent = []

    def visit(n, bound):
        if n["op"] == "ema":
            raise ValueError("ema")
        if n["op"] == "field":
            var = n["lag"].get("var")
            recent.append(n["lag"]["base"] + (bound.get(var, 0) if var else 0))
            return
        inner = dict(bound)
        if n["op"].startswith("ts_") and n.get("var"):
            inner[n["var"]] = n.get("start", 0)
        for a in n.get("args", []):
            visit(a, inner)
    try:
        visit(ir, {})
    except ValueError:
        return 0
    lags = set(recent)
    if len(lags) != 1 or next(iter(lags)) < 1:
        return 0
    if any(n["op"].startswith("ts_") for n in walk(ir)) and len(recent) < 2:
        return 0
    return lags.pop()


def _shift(ir, by):
    out = copy.deepcopy(ir)
    for n in walk(out):
        if n["op"] == "field":
            n["lag"] = dict(n["lag"], base=n["lag"]["base"] - by, time_index=None)
    return out


ADMISSION_STATES = ["SEMANTICS_UNRESOLVED", "MISSING_FIELDS", "HOST_DECISION_REQUIRED", "DATA_UNCERTIFIED",
                    "CANDIDATE_ONLY", "READY_FOR_REVIEW_DSL"]
DATA_REQUIREMENTS = {
    "adjusted_prices": "split/dividend-adjusted prices (or a corporate-action table to build them), certified for the period",
    "listing_status": "point-in-time listing/delisting dates (universe membership without survivorship bias)",
    "trading_status": "point-in-time suspension / limit / ST status (tradability of signals and labels)",
}
DSL_FIELD = {"close": "close", "open": "open", "high": "high", "low": "low", "volume": "volume"}
UNITS = {"close": "currency/share", "open": "currency/share", "high": "currency/share", "low": "currency/share",
         "volume": "shares", "amount": "currency", "returns": "dimensionless", "market_cap": "currency",
         "book_equity": "currency"}
FUNDAMENTAL = {"market_cap", "book_equity"}


def _ev(item):
    return item["evidence"][0] if item and item.get("evidence") else None


def _paper(items, key="value"):
    return [{"value": it[key], "evidence": it["evidence"], "basis": "paper",
             **{k: it[k] for k in ("parsed", "splits", "results", "methods") if k in it}} for it in items]


def _select_factor(spec, factor):
    """(factor, selection note). Without an explicit choice: the only formula-linked factor, or the only one named in
    the paper's title (recorded as an inference the host can override); otherwise the host must choose."""
    facs = spec["factors"]
    if factor is None:
        cands = [f for f in facs if f["formula_ids"]]
        if len(cands) == 1:
            return cands[0], None
        title = ((spec["paper"].get("title") or {}).get("value") or "").lower()
        named = [f for f in cands if title and (f["name"].lower() in title or any(a.lower() in title for a in f["aliases"]))]
        if len(named) == 1:
            others = [f["name"] for f in cands if f is not named[0]]
            return named[0], (f"'{named[0]['name']}' was selected because the paper's title names it; other formula-linked "
                              f"candidates: {others}. Pass factor= to choose another.")
        raise PaperError("SCHEMA_INVALID", f"choose a factor explicitly; formula-linked factors: {[f['name'] for f in cands]}")
    for f in facs:
        if factor == f["name"] or factor in f["aliases"]:
            return f, None
    raise PaperError("SCHEMA_INVALID", f"factor {factor!r} not found in spec")


def _substitute(ir, symbol, macro):
    """Replace every occurrence of `symbol` by the macro IR, shifting the macro's lags by the occurrence's lag."""
    if ir["op"] == "field" and ir["symbol"] == symbol:
        out = copy.deepcopy(macro)
        for n in walk(out):
            if n["op"] == "field":
                n["lag"] = {"base": n["lag"]["base"] + ir["lag"]["base"], "var": ir["lag"].get("var") or n["lag"].get("var"),
                            "time_index": None}
        return out
    out = dict(ir)
    if "args" in ir:
        out["args"] = [_substitute(a, symbol, macro) for a in ir["args"]]
    return out


FREQ_WORDS = [("daily", r"\bdaily\b|日频|交易日"), ("weekly", r"\bweekly\b|周频"), ("monthly", r"\bmonthly\b|月频|月末"),
              ("quarterly", r"\bquarterly\b|季频"), ("annual", r"\bannual\b|年频")]


def paper_frequency(spec):
    """The data frequency stated in the paper (first frequency sentence), or None."""
    for it in spec["A_supported"].get("frequency", []):
        for name, pat in FREQ_WORDS:
            if re.search(pat, it["value"], re.I):
                return name, it["evidence"]
    return None, []


def _scale_time(ir, rows):
    """Express lags in rows of a daily panel: every lag and window bound times `rows` (a host deviation)."""
    out = copy.deepcopy(ir)
    for n in walk(out):
        if n["op"] == "field":
            n["lag"] = dict(n["lag"], base=n["lag"]["base"] * rows)
        if n["op"].startswith("ts_"):
            n["start"], n["end"] = n["start"] * rows, (n["end"] + 1) * rows - 1
        if n["op"] == "ema":
            # N paper periods -> N*rows daily rows; alpha and the truncation window are recomputed (a recorded deviation:
            # daily smoothing over the same span is not identical to smoothing period-end values)
            if n["smoothing"] == "ratio":
                raise ValueError("Chinese SMA(N,M) cannot be rescaled to daily rows without changing M/N")
            from .factor_ir import make_ema
            n.update(make_ema(n["smoothing"], n["n"] * rows, n["args"][0], init=n["init"]), args=n["args"])
    return out


def build_research_task(spec: dict, *, factor: str | None = None, symbol_map: dict | None = None,
                        choices: dict | None = None) -> dict:
    """Build a research task for one factor of an extracted spec.

    symbol_map: {symbol: {"field": "close", "adjustment": "backward"|"none"|...}} or
                {symbol: {"derive": "<LaTeX formula in other symbols, in the paper's time units>"}}
                (host choices, recorded as such; "deviates_from_paper": true + "reason" marks a knowing deviation)
    choices:    {"label_lag": int, "horizon": {"n": int, "unit": str}, "splits": {"train": [s, e], "valid": [...],
                 "test": [...]}, "independent_test": [s, e], "time_unit_rows": {...},
                 "data_certification": {"source": str, "level": str, "fields": [...],
                                        "certified": {"adjusted_prices": bool, "listing_status": bool,
                                                      "trading_status": bool}}}       (host choices, recorded as such)
    """
    symbol_map, choices = dict(symbol_map or {}), dict(choices or {})
    A = spec["A_supported"]
    fac, selection = _select_factor(spec, factor)
    unresolved = []

    def need(item, question, blocking=True, source="missing", related=None, gate="semantics"):
        unresolved.append({"item": item, "question": question, "blocking": blocking, "source": source,
                           "related": related or [], "gate": gate})

    if selection:
        need("factor selection", selection, blocking=False, source="inference", gate="semantics")
    # ---------------- formula -> IR
    formulas = {f["id"]: f for f in spec["formulas"]}
    flist = [formulas[i] for i in fac["formula_ids"] if i in formulas]
    formula, ir, ir_error, output_symbol = None, None, None, None
    timing = {"common_lag_removed": 0}
    if not flist:
        need("factor formula", f"No formula is linked to '{fac['name']}'; write its definition before implementation.",
             gate="formula")
    else:
        formula = flist[0]
        if formula["status"] == "unresolved":
            need("factor formula", f"FORMULA_UNRESOLVED: formula {formula['id']} could not be read from the source; read page "
                 f"{formula['page']}" + (f" region {formula['layout']['regions']}" if formula.get("layout") else "") + ".",
                 related=[formula["id"]], gate="formula")
        else:
            try:
                parsed = parse_formula(formula["latex"] or formula["readable"])
                ir, output_symbol = parsed["ir"], parsed["output"]
            except IRError as e:
                ir_error = {"code": e.code, "detail": e.detail}
                need("factor formula structure", f"Formula {formula['id']} could not be parsed into the factor IR "
                     f"({e.code}: {e.detail}); a human must restate it.", related=[formula["id"]], gate="formula")
            if formula["status"] == "suspect":
                need("formula check", f"Formula {formula['id']} is flagged suspect ({'; '.join(formula['issues'])}).",
                     related=[formula["id"]], gate="formula")
    freq_name, freq_ev = paper_frequency(spec)
    if ir is not None:
        lag = _common_lag(ir)
        if lag:
            ir = _shift(ir, lag)
            timing = {"common_lag_removed": lag, "unit": FREQ_UNIT.get(freq_name), "basis": "inference",
                      "note": f"every input is observed at t-{lag}: the paper indexes the formation date relative to the "
                              "holding period. The factor is indexed by its observation date; when the position starts "
                              "is recorded in the label (lag), not in the factor."}
    # ---------------- symbols -> inputs (verbal definitions are interpreted, never matched on a single word)
    symbols, derived = [], {}
    if ir is not None:
        defs = formula["defined_variables"] if formula else {}
        for sym, spec_ in symbol_map.items():
            if "derive" in spec_:
                try:
                    macro = parse_formula(spec_["derive"])["ir"]
                except IRError as e:
                    raise PaperError("SCHEMA_INVALID", f"symbol_map[{sym}].derive does not parse: {e}") from e
                derived[sym] = macro
                ir = _substitute(ir, sym, macro)
        for sym in sorted(set(derived) | set(fields_used(ir)), key=lambda s: (s in derived, s)):
            pdef = defs.get(sym)
            text = pdef["definition"] if pdef else ""
            interp = interpret_definition(text) if text and not text.startswith(("left-hand side", "defined by formula")) else \
                interpret_definition(None)
            host = symbol_map.get(sym)
            semantic = interp["base"] if interp["kind"] == "raw" else None
            entry = {"symbol": sym, "paper_definition": pdef, "semantic": semantic, "interpretation": interp,
                     "adjustment_in_paper": interp["adjustment"] == "adjusted" if text else None,
                     "field": None, "dsl_field": None, "unit": None, "basis": "missing", "derived": sym in derived}
            dev = bool(host and host.get("deviates_from_paper") and host.get("reason"))
            if sym in derived:
                agg, length = _derive_window(derived[sym])
                entry.update(basis="host_choice", derivation=host["derive"])
                if interp["kind"] == "window_aggregate":
                    want = _window_in_periods(interp["window"], freq_name)
                    if agg != interp["aggregate"] and not dev:
                        need(f"input {sym}", f"The paper defines {sym} as the {interp['aggregate']} over {interp['window']['text']!r}; "
                             f"the host derivation uses {agg or 'no window aggregate'}. A different aggregate is a different factor.",
                             source="conflict", gate="semantics")
                    elif want is not None and length is not None and abs(length - want) > 0.1 * want and not dev:
                        need(f"input {sym}", f"The paper's window for {sym} is {interp['window']['text']!r} (~{want:g} "
                             f"{freq_name} periods); the host derivation spans {length}. Shortening or lengthening the window "
                             "changes the factor.", source="conflict", gate="semantics")
                    if interp["base"] in ("price_unspecified", None):
                        need(f"price basis of {sym}", f"The paper does not say which price the {interp['aggregate']} is taken "
                             f"over (daily close, intraday {'high' if interp['aggregate'] == 'max' else 'low'}, period-end); "
                             "the host derivation decides it and is recorded as a host choice.", blocking=False,
                             source="host_choice", gate="semantics")
                symbols.append(entry)
                continue
            if host and "field" in host:
                entry.update(field=host["field"], dsl_field=DSL_FIELD.get(host["field"]), unit=UNITS.get(host["field"]),
                             adjustment=host.get("adjustment"), basis="host_choice")
                if interp["kind"] == "window_aggregate" and not dev:
                    need(f"input {sym}", f"The paper defines {sym} as '{text}' ({interp['aggregate']} over "
                         f"{interp['window']['text']!r}); the host maps it to the single-date field '{host['field']}'. "
                         "Derive it from the window instead (symbol_map derive), or mark deviates_from_paper with a reason.",
                         source="conflict", gate="semantics")
                elif semantic and semantic != host["field"] and not host.get("deviates_from_paper"):
                    need(f"input {sym}", f"Host maps {sym} to '{host['field']}' but the paper defines it as '{text}'; "
                         "mark deviates_from_paper with a reason or correct the mapping.", source="conflict", gate="semantics")
            elif interp["kind"] == "window_aggregate":
                options = _derivation_options(sym, interp, fields_used(ir), defs)
                entry.update(basis="derived_in_paper", options=options)
                need(f"input {sym}", f"The paper defines {sym} as '{text}': a {interp['aggregate']} over "
                     f"{interp['window']['text']!r}, not a single-date field. Choose how to derive it "
                     f"(options: {', '.join(o['id'] for o in options)}) and give symbol_map['{sym}'].derive.",
                     related=[formula["id"]] if formula else [], gate="semantics")
            elif semantic:
                entry.update(field=semantic, dsl_field=DSL_FIELD.get(semantic), unit=UNITS.get(semantic), basis="inference")
            else:
                need(f"input {sym}", f"What is '{sym}'? The paper's definition ('{text or 'none'}') cannot be mapped to a "
                     "data field without guessing.", related=[formula["id"]] if formula else [], gate="semantics")
            symbols.append(entry)
        # prices compared across dates need a declared adjustment
        price_syms = {s["symbol"] for s in symbols if s["field"] in PRICE_FIELDS}
        # a price aggregated over a window (even one not yet derived) also compares prices across dates
        windowed_price = any(s["interpretation"]["kind"] == "window_aggregate" and
                             s["interpretation"]["base"] in PRICE_FIELDS | {"price_unspecified"} for s in symbols)
        if price_syms and (_cross_time_prices(ir, price_syms) or windowed_price):
            for s in symbols:
                if s["symbol"] not in price_syms:
                    continue
                host = symbol_map.get(s["symbol"]) or {}
                adj = host.get("adjustment")
                deviation = bool(host.get("deviates_from_paper") and host.get("reason"))
                if s["adjustment_in_paper"] and adj not in ("backward", "total_return") and not deviation:
                    need(f"price adjustment for {s['symbol']}", f"The paper uses adjusted prices for {s['symbol']}; confirm the "
                         "data source supplies backward-adjusted prices (the main Agent's daily65 close is unadjusted).",
                         gate="host_choices")
                elif not s["adjustment_in_paper"] and adj in (None, "none") and not (host.get("deviates_from_paper") and host.get("reason")):
                    need(f"price adjustment for {s['symbol']}", f"{s['symbol']} is compared across dates; the paper does not "
                         "state its adjustment. Unadjusted prices turn splits and dividends into spurious moves: choose "
                         "'backward' (or justify 'none' with deviates_from_paper and a reason).", gate="host_choices")
    # ---------------- DSL mapping (the DSL works on daily rows; other frequencies are never converted silently)
    ir_exec, time_basis = ir, {"paper_frequency": freq_name, "rows_per_period": 1 if freq_name in (None, "daily") else None,
                              "basis": "paper" if freq_name else "missing"}
    conv = choices.get("time_unit_rows")
    if ir is not None and freq_name not in (None, "daily"):
        if conv:
            ir_exec = _scale_time(ir, int(conv["rows"]))
            time_basis.update(rows_per_period=int(conv["rows"]), basis="host_choice", deviates_from_paper=True,
                              reason=conv.get("reason"))
            if not conv.get("deviates_from_paper"):
                need("frequency conversion", "Converting the paper's periods into daily rows changes the definition; "
                     "set deviates_from_paper with a reason.", source="conflict", gate="host_choices")
    if ir is not None:
        fmap = {s["symbol"]: s["dsl_field"] for s in symbols}
        if freq_name not in (None, "daily") and not conv:
            dsl_res = {"status": "contract_limit_exceeded", "expression": None, "reasons": [
                {"code": "FREQUENCY_MISMATCH", "detail": f"formula lags are in {freq_name} periods; the DSL operates on daily rows. "
                 "A conversion would change the definition and must be an explicit host decision."}]}
        else:
            dsl_res = D.compile_ir(ir_exec, fmap)
        if dsl_res["status"] != "expressible":
            need("implementation route", "The factor cannot run in the 19-operator DSL as written "
                 f"({dsl_res['status']}: {', '.join(r['code'] for r in dsl_res['reasons'])}); a reviewed new "
                 "implementation is required. The definition is not changed to fit the DSL.",
                 blocking=False, source="dsl", gate="implementation")
        wu = warmup(ir)
        if wu["uses_future"]:
            need("future reference", f"The formula references t+{-wu['min_lag']}; it cannot be a signal as written.",
                 source="pit", gate="formula")
    else:
        dsl_res = {"status": "not_assessed", "reasons": [{"code": "NO_IR", "detail": "no parsed factor definition"}],
                   "expression": None}
        wu = None
    # ---------------- lookback consistency (inference)
    paper_lb = [i["parsed"] for i in A.get("lookback", []) if "parsed" in i]
    lookback = {"paper": _paper(A.get("lookback", [])), "formula_warmup": wu, "basis": "inference",
                "note": "formula warmup = max lag + 1 observations at the paper's data frequency"}
    if not paper_lb:
        need("lookback window", "The paper states no lookback in prose; the formula warmup is an inference only.",
             blocking=False)
    # ---------------- horizon & label
    hz_paper = [i["parsed"] for i in A.get("holding_horizon", []) if "parsed" in i]
    horizon = choices.get("horizon")
    horizon_basis = "host_choice" if horizon else ("paper" if len({json.dumps(h, sort_keys=True) for h in hz_paper}) == 1 else "missing")
    if horizon is None and horizon_basis == "paper":
        horizon = hz_paper[0]
    if horizon is None:
        need("prediction horizon", "No single prediction horizon is stated; choose it explicitly.", gate="host_choices")
    label_lag = choices.get("label_lag")
    if label_lag is None:
        need("label timing", "When does the position start after the signal (lag)? The builder does not assume one.",
             gate="host_choices")
    label = {"horizon": horizon, "horizon_basis": horizon_basis, "horizon_paper": _paper(A.get("holding_horizon", [])),
             "lag": label_lag, "lag_basis": "host_choice" if label_lag is not None else "missing",
             "definition": "forward return from t+lag to t+lag+horizon at the paper's frequency (proposal; confirm the price field)",
             "definition_basis": "inference",
             "maturity_rule": "label(t) is known only at t+lag+horizon; training/validation/test windows are purged by lag+horizon"}
    if timing["common_lag_removed"]:
        label["paper_timing_hint"] = timing
    # ---------------- splits
    paper_splits, seen = [], set()
    for it in A.get("evaluation_design", []) + A.get("sample_periods", []):   # one sentence can match both fields
        for sp in it.get("splits", []):
            key = (sp["role"], sp["start_year"], sp["end_year"], it["evidence"][0]["location"]["block_id"])
            if key not in seen:
                seen.add(key)
                paper_splits.append(dict(sp, evidence=it["evidence"]))
    splits = {"paper": paper_splits, "chosen": choices.get("splits"), "chosen_basis": "host_choice" if choices.get("splits") else "missing",
              "independent_test": choices.get("independent_test"),
              "policy": "the paper's own out-of-sample period is reported, not reused as our independent test; the host "
                        "assigns an untouched test window and the builder never reads it"}
    if not choices.get("splits"):
        need("train/validation/test windows", "Assign train, validation and test windows for this replication "
             "(the paper's periods may not overlap the available data).", gate="host_choices")
    # ---------------- data schema & PIT
    freq = _paper(A.get("frequency", []))
    universe = _paper(A.get("universe", []))
    if not freq:
        need("data frequency", "At what frequency are the inputs observed?")
    if not universe and choices.get("universe"):
        universe = [{"value": choices["universe"], "basis": "host_choice", "evidence": []}]
    if not universe:
        need("universe", "Which securities form the universe?", gate="host_choices")
    pit = [{"rule": "the factor value at row t may use only rows <= t (no negative lags)", "basis": "inference"},
           {"rule": "prices must be backward-adjusted or unadjusted as defined; forward-adjusted (qfq) series embed later corporate actions",
            "basis": "inference"},
           {"rule": "universe membership must be point-in-time (delisted securities kept while listed)", "basis": "inference"}]
    if any(s["field"] in FUNDAMENTAL for s in symbols):
        pit.append({"rule": "fundamental inputs become available only after their announcement date", "basis": "inference"})
        lag_risk = next(r for r in spec["integrity_risks"] if r["risk"] == "fundamental_reporting_lag")
        if lag_risk["status"] == "not_mentioned":
            need("fundamental availability lag", "Fundamental inputs are used; at what lag do they become known?",
                 gate="host_choices")
    data_schema = {"panel": "dates x securities, float64", "frequency": freq, "universe": universe,
                   "fields": [{k: s[k] for k in ("symbol", "field", "unit", "basis")} for s in symbols],
                   "sample_selection": _paper(A.get("sample_selection", [])),
                   "preprocessing": _paper(A.get("preprocessing", []))}
    # ---------------- data certification (what the data must prove before anything is computed)
    needs_adjusted = any(u["item"].startswith("price adjustment for") for u in unresolved) or any(
        (symbol_map.get(s["symbol"]) or {}).get("adjustment") in ("backward", "total_return") for s in symbols)
    required = (["adjusted_prices"] if needs_adjusted else []) + ["listing_status", "trading_status"]
    dc = choices.get("data_certification")
    data = {"required": [{"property": r, "why": DATA_REQUIREMENTS[r]} for r in required], "declared": dc}
    if dc is None:
        data["status"] = "not_assessed"
        need("data certification", "No data certification was declared; the task cannot state that the inputs support the "
             "factor (adjusted prices, listing and trading status).", blocking=False, source="host_choice", gate="data")
    else:
        missing_cert = [r for r in required if not (dc.get("certified") or {}).get(r)]
        for r in missing_cert:
            need(f"data: {r} not certified", f"{DATA_REQUIREMENTS[r]} is required but the declared source "
                 f"({dc.get('source')}, level {dc.get('level')}) does not certify it.", source="data", gate="data")
        published = set(dc.get("fields") or [])
        for s in symbols:
            if s["field"] and published and s["field"] not in published:
                need(f"field {s['field']} not published", f"Input {s['symbol']} needs '{s['field']}', which the declared source "
                     f"does not publish ({sorted(published)}).", source="data", gate="fields")
        data["status"] = "fail" if missing_cert else "pass"
    io = {"input": {"type": "mapping field -> DataFrame[dates x securities]", "fields": sorted({s["field"] for s in symbols if s["field"]})},
          "output": {"name": output_symbol or (fac["aliases"][0] if fac["aliases"] else fac["name"]),
                     "type": "DataFrame[dates x securities] float64", "alignment": "value at row t uses rows <= t",
                     "missing": "NaN where inputs are missing or the window is incomplete; never filled with 0"}}
    evaluation = {"required_metrics": REQUIRED_METRICS, "paper_metrics": _paper(A.get("evaluation_metrics", [])),
                  "paper_reported_results": _paper(A.get("reported_results", [])),
                  "note": "paper results are quoted for comparison only; they are not targets and do not tune the replication"}
    fids = set(fac["formula_ids"])
    for c in spec["C_missing"]:
        if c.get("optional") or c["item"] in {u["item"] for u in unresolved}:
            continue
        if c.get("related") and not fids & set(c["related"]):
            continue                                   # about another formula of the paper, not this factor
        if c.get("code") == "FORMULA_UNRESOLVED":
            mine = bool(fids & set(c.get("related") or []))
            need(c["item"], c["question"], blocking=mine, source="spec.C_missing", related=c.get("related"), gate="formula")
        else:
            need(c["item"], c["question"], blocking=c["item"] in ("factor_definition",), source="spec.C_missing",
                 related=c.get("related"))
    for a in spec["ambiguities"]:
        # several horizons / split sets in the paper: the host's explicit choice resolves it (recorded, not blocking)
        resolved = (a["topic"] == "holding_horizon" and choices.get("horizon")) or (a["topic"] == "evaluation_design" and choices.get("splits"))
        hostish = a["topic"] in ("holding_horizon", "evaluation_design")
        need(f"ambiguity: {a['topic']}", a["question"] + " " + a["detail"] + (" Resolved by the host's explicit choice." if resolved else ""),
             blocking=hostish and not resolved, source="host_choice" if resolved else "spec.ambiguity",
             gate="host_choices" if hostish else "semantics")
    status = "blocked" if any(u["blocking"] for u in unresolved) else "ready_for_review"
    task = {
        "schema": TASK_SCHEMA,
        "builder": BUILDER,
        "source": {"spec_id": spec["spec_id"], "doc_id": spec["generated_from"]["doc_id"],
                   "filename": spec["generated_from"]["filename"], "sha256": spec["generated_from"]["sha256"],
                   "extractor": spec["extractor"]["version"]},
        "hypothesis": {"objective": _paper(A.get("research_objective", [])), "economic_intuition": _paper(A.get("economic_intuition", []))},
        "time_basis": time_basis,
        "factor": {"name": fac["name"], "aliases": fac["aliases"], "status_in_spec": fac["status"],
                   "selection": "explicit" if factor is not None else ("title_match" if selection else "single_candidate"),
                   "definition_evidence": fac["definition_evidence"],
                   "formula": {k: formula[k] for k in ("id", "readable", "latex", "status", "page", "block_id")} if formula else None,
                   "ir": ir, "ir_rendered": render(ir) if ir else None, "ir_error": ir_error, "ir_version": IR_VERSION,
                   "ir_execution": ir_exec if ir_exec is not ir else None, "timing": timing,
                   "symbols": symbols},
        "data_schema": data_schema, "data_requirements": data, "pit_constraints": pit, "io": io, "lookback": lookback,
        "label": label, "splits": splits, "evaluation": evaluation,
        "dsl": {"catalog": D.DSL_CATALOG["reference"], "catalog_sha256": D.CATALOG_SHA256, **dsl_res},
        "limitations": {"paper": _paper(A.get("limitations", [])), "integrity_risks": spec["integrity_risks"],
                        "extraction_quality": spec["extraction_quality"]},
        "unresolved": unresolved,
        "status": status,
        "admission": _admission(unresolved, ir, dsl_res, data),
        "host_choices": {"symbol_map": symbol_map, "choices": choices},
        "reproducibility": {"spec_id": spec["spec_id"], "document_sha256": spec["generated_from"]["sha256"],
                            "extractor_version": EXTRACTOR["version"], "builder_version": BUILDER["version"],
                            "ir_version": IR_VERSION, "dsl_catalog_sha256": D.CATALOG_SHA256},
    }
    task["task_id"] = _task_hash(task)
    return task


def _derivation_options(sym, interp, used, defs):
    """Ways to derive a windowed input, as proposals for the host (never applied automatically)."""
    agg = interp["aggregate"]
    n = interp["window"]["n"]
    price = next((s for s in used if s != sym and defs.get(s) and interpret_definition(defs[s]["definition"])["kind"] == "raw"
                  and interpret_definition(defs[s]["definition"])["base"] in PRICE_FIELDS), "P")
    win = f"\\{agg}_{{0 \\le k \\le {n - 1}}}" if agg in ("max", "min") else f"\\operatorname{{{agg}}}_{{k=0}}^{{{n - 1}}}"
    opts = [{"id": f"{agg}_of_daily_close", "derive": f"{win} {price}_{{i,t-k}}",
             "requires": f"{price} mapped to the daily close and the paper periods converted to daily rows (time_unit_rows), "
                         "so the window covers every trading day", "basis": "inference"},
            {"id": f"{agg}_of_period_end_price", "derive": f"{win} {price}_{{i,t-k}}",
             "requires": "evaluation on period-end rows only (no daily conversion): uses one price per period", "basis": "inference"}]
    if agg in ("max", "min"):
        fld = "high" if agg == "max" else "low"
        opts.append({"id": f"{agg}_of_intraday_{fld}", "derive": f"{win} H_{{i,t-k}}",
                     "requires": f"a new symbol H mapped to the daily {fld} field and daily rows", "basis": "inference"})
    return opts


def _admission(unresolved, ir, dsl_res, data):
    """Admission gates: what the task may be used for. Generating a task never means it can be computed or backtested."""
    def fails(gate):
        return [u["item"] for u in unresolved if u["blocking"] and u["gate"] == gate]
    gates = {"formula": fails("formula"), "semantics": fails("semantics"), "fields": fails("fields"),
             "host_choices": fails("host_choices"), "data": fails("data")}
    states = []
    if gates["formula"] or gates["semantics"] or ir is None:
        states.append("SEMANTICS_UNRESOLVED")
    if gates["fields"]:
        states.append("MISSING_FIELDS")
    if gates["host_choices"]:
        states.append("HOST_DECISION_REQUIRED")
    if data["status"] != "pass":
        states.append("DATA_UNCERTIFIED")
    impl = "dsl" if dsl_res["status"] == "expressible" else ("candidate_only" if ir is not None else "none")
    understood = not (gates["formula"] or gates["semantics"]) and ir is not None
    if impl == "candidate_only" and understood:
        states.append("CANDIDATE_ONLY")
    if not states:
        states.append("READY_FOR_REVIEW_DSL")
    return {"state": states[0], "states": states,
            "gates": {k: {"status": "fail" if v else "pass", "blocking_items": v} for k, v in gates.items()} |
                     {"data": {"status": data["status"] if not gates["data"] else "fail", "blocking_items": gates["data"]}},
            "implementation": impl,
            "permissions": {"may_generate_candidate": understood and impl == "candidate_only",
                            "may_execute_candidate": False,
                            "may_compute_after_human_approval": states == ["READY_FOR_REVIEW_DSL"],
                            "may_backtest": False},
            "note": "states are listed in priority order; only READY_FOR_REVIEW_DSL with certified data may be computed, and "
                    "only after human approval. Candidate code is never executed here; backtesting is a separate host decision."}


def _task_hash(task):
    body = {k: v for k, v in task.items() if k != "task_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ validation

TASK_JSON_SCHEMA = {"type": "object", "required": ["schema", "task_id", "builder", "source", "hypothesis", "factor",
                                                   "data_schema", "pit_constraints", "io", "lookback", "label", "splits",
                                                   "evaluation", "dsl", "limitations", "unresolved", "status",
                                                   "admission", "data_requirements", "host_choices", "reproducibility"],
                    "properties": {"schema": {"type": "string", "enum": [TASK_SCHEMA]},
                                   "status": {"type": "string", "enum": ["blocked", "ready_for_review"]},
                                   "admission": {"type": "object", "required": ["state", "states", "gates", "permissions"]},
                                   "unresolved": {"type": "array", "items": {"type": "object", "required":
                                                  ["item", "question", "blocking", "source"]}}}}


def _evidence(obj):
    if isinstance(obj, dict):
        if "location" in obj and "quote" in obj:
            yield obj
        for v in obj.values():
            yield from _evidence(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _evidence(v)


def _years(pair):
    return int(str(pair[0])[:4]), int(str(pair[1])[:4])


def validate_research_task(task: dict, spec: dict | None = None) -> dict:
    """Structure, provenance against the spec, recomputed IR/DSL/warmup, split order, label purge and status."""
    if not isinstance(task, dict) or task.get("schema") != TASK_SCHEMA:
        return {"valid": False, "errors": [{"code": "VERSION_UNSUPPORTED", "detail": str(task.get("schema") if isinstance(task, dict) else task)}]}
    errors = [{"code": "SCHEMA_INVALID", "detail": e} for e in validate_schema(task, TASK_JSON_SCHEMA)]
    if errors:
        return {"valid": False, "errors": errors}
    if spec is not None:
        if spec["spec_id"] != task["source"]["spec_id"]:
            errors.append({"code": "SOURCE_MISMATCH", "detail": "task was built from a different spec"})
        known = {json.dumps(e, sort_keys=True) for e in _evidence(spec)}
        for e in _evidence(task):
            if json.dumps(e, sort_keys=True) not in known:
                errors.append({"code": "PROVENANCE_MISMATCH", "detail": f"evidence not present in spec: {e['quote'][:60]!r}"})
        f = task["factor"]["formula"]
        if f is not None:
            sf = next((x for x in spec["formulas"] if x["id"] == f["id"]), None)
            if sf is None or sf["readable"] != f["readable"]:
                errors.append({"code": "PROVENANCE_MISMATCH", "detail": f"formula {f['id']} differs from the spec"})
        # deterministic rebuild from the spec and the recorded host choices: any edited section shows up here
        try:
            rebuilt = build_research_task(spec, factor=task["factor"]["name"] if task["factor"].get("selection", "explicit") == "explicit" else None,
                                          symbol_map=task["host_choices"]["symbol_map"],
                                          choices=task["host_choices"]["choices"])
        except PaperError as e:
            errors.append({"code": "REBUILD_FAILED", "detail": str(e)})
        else:
            if rebuilt["factor"]["ir"] != task["factor"]["ir"] or rebuilt["factor"].get("ir_execution") != task["factor"].get("ir_execution"):
                errors.append({"code": "IR_MISMATCH", "detail": "stored IR differs from the IR parsed from the source formula"})
            diff = sorted(k for k in rebuilt if k != "task_id" and rebuilt[k] != task.get(k))
            if diff or rebuilt["task_id"] != task["task_id"]:
                errors.append({"code": "REBUILD_MISMATCH", "detail": f"sections differ from a rebuild: {diff}"})
    if _task_hash(task) != task["task_id"]:
        errors.append({"code": "TASK_ID_MISMATCH", "detail": "content changed after the task was built"})
    ir = task["factor"]["ir"]
    if ir is not None:
        fmap = {s["symbol"]: s["dsl_field"] for s in task["factor"]["symbols"]}
        tb = task.get("time_basis", {})
        if tb.get("paper_frequency") not in (None, "daily") and tb.get("basis") != "host_choice":
            re_dsl = {"status": "contract_limit_exceeded", "expression": None}
        else:
            re_dsl = D.compile_ir(task["factor"].get("ir_execution") or ir, fmap)
        if re_dsl["status"] != task["dsl"]["status"] or re_dsl.get("expression") != task["dsl"].get("expression"):
            errors.append({"code": "DSL_MISMATCH", "detail": f"recorded {task['dsl']['status']}, recomputed {re_dsl['status']}"})
        if warmup(ir) != task["lookback"]["formula_warmup"]:
            errors.append({"code": "WARMUP_MISMATCH", "detail": "recorded warmup differs from the IR"})
        if warmup(ir)["uses_future"] and not any(u["item"] == "future reference" and u["blocking"] for u in task["unresolved"]):
            errors.append({"code": "FUTURE_REFERENCE_IN_SIGNAL", "detail": "future reference not blocked"})
    ch = task["splits"]["chosen"]
    if ch:
        try:
            seq = [_years(ch[k]) for k in ("train", "valid", "test")]
        except (KeyError, TypeError, ValueError):
            errors.append({"code": "SPLIT_INVALID", "detail": "splits need train, valid and test [start, end]"})
            seq = []
        for a, b in zip(seq, seq[1:]):
            if not (a[0] <= a[1] < b[0] <= b[1]):
                errors.append({"code": "SPLIT_ORDER", "detail": f"{a} must end before {b} starts"})
        for k in ("train", "valid", "test"):
            if k in ch and str(ch[k][1]) > str(ch[k][0]) and task["label"]["horizon"] is None:
                errors.append({"code": "LABEL_PURGE_MISSING", "detail": "splits without a horizon cannot be purged"})
                break
    if task["status"] == "ready_for_review" and any(u["blocking"] for u in task["unresolved"]):
        errors.append({"code": "STATUS_INCONSISTENT", "detail": "ready_for_review with blocking items"})
    if task["status"] == "blocked" and not any(u["blocking"] for u in task["unresolved"]):
        errors.append({"code": "STATUS_INCONSISTENT", "detail": "blocked without blocking items"})
    adm = task.get("admission", {})
    if adm.get("permissions", {}).get("may_execute_candidate") or adm.get("permissions", {}).get("may_backtest"):
        errors.append({"code": "ADMISSION_INVALID", "detail": "a task never grants candidate execution or backtesting"})
    if adm.get("permissions", {}).get("may_compute_after_human_approval") and (task["status"] != "ready_for_review" or
                                                                            task["dsl"]["status"] != "expressible"):
        errors.append({"code": "ADMISSION_INVALID", "detail": "computation admitted for a blocked or non-DSL task"})
    return {"valid": not errors, "errors": errors}


def to_qrtk_research_spec(task: dict):
    """Freeze a reviewed task into qrtk.ResearchSpec; refused while anything blocks or a choice is missing."""
    from qrtk import ResearchSpec
    if task["status"] != "ready_for_review":
        raise PaperError("SCHEMA_INVALID", "task is blocked: " + "; ".join(u["item"] for u in task["unresolved"] if u["blocking"]))
    if task["admission"]["state"] in ("SEMANTICS_UNRESOLVED", "MISSING_FIELDS", "HOST_DECISION_REQUIRED"):
        raise PaperError("SCHEMA_INVALID", f"task admission is {task['admission']['state']}")
    ch, hz = task["splits"]["chosen"], task["label"]["horizon"]
    if hz.get("unit") not in ("day", "trading_day"):
        raise PaperError("SCHEMA_INVALID", f"qrtk evaluates daily panels; horizon unit {hz.get('unit')!r} needs conversion by the host")
    return ResearchSpec(factor_name=task["io"]["output"]["name"], direction="train", horizon=int(hz["n"]),
                        train=tuple(ch["train"]), valid=tuple(ch["valid"]), test=tuple(ch["test"]),
                        lag=int(task["label"]["lag"]))


# ------------------------------------------------------------------ export

def _at(loc):
    return (f"p.{loc['page']}" if loc.get("page") else f"line {loc.get('line')}") + f"，`{loc['block_id']}`"


def task_markdown(task: dict) -> str:
    f = task["factor"]
    L = [f"# 研究任务：{f['name']}", "",
         f"- 状态：**{task['status']}**（不是批准；执行与数据访问由宿主决定）",
         f"- task_id `{task['task_id']}`；spec_id `{task['source']['spec_id']}`；来源 `{task['source']['filename']}`",
         f"- DSL 兼容性：**{task['dsl']['status']}**（{task['dsl']['catalog']}）",
         f"- 准入状态：**{task['admission']['state']}**（全部：{', '.join(task['admission']['states'])}）；"
         f"可生成候选：{task['admission']['permissions']['may_generate_candidate']}；执行候选：否；回测：否", ""]
    L += ["## 假设（原文）", ""]
    for it in task["hypothesis"]["objective"] + task["hypothesis"]["economic_intuition"]:
        loc = it["evidence"][0]["location"]
        L.append(f"- {it['value']}（{_at(loc)}）")
    if not (task["hypothesis"]["objective"] or task["hypothesis"]["economic_intuition"]):
        L.append("- 原文未找到")
    L += ["", "## 因子定义", ""]
    if f["formula"]:
        where = f"p.{f['formula']['page']}" if f["formula"]["page"] else f"`{f['formula']['block_id']}`"
        L += [f"- 原文公式 {f['formula']['id']}（{f['formula']['status']}，{where}）：`{f['formula']['readable']}`"]
    L.append(f"- 解析结果：`{f['ir_rendered']}`" if f["ir_rendered"] else f"- 未能解析：{f['ir_error']}")
    L += ["", "| 符号 | 原文定义 | 字段 | 单位 | 依据 |", "|---|---|---|---|---|"]
    for s in f["symbols"]:
        d = s["paper_definition"]["definition"] if s["paper_definition"] else "—"
        L.append(f"| {s['symbol']} | {d} | {s['field'] or '?'} | {s['unit'] or '?'} | {s['basis']} |")
    wu = task["lookback"]["formula_warmup"]
    L += ["", "## 时间与标签", "",
          f"- 公式所需历史（推断）：{wu['observations_required'] if wu else '未知'} 个观测；用到未来数据：{wu['uses_future'] if wu else '未知'}",
          f"- 原文回看窗口：{[x.get('parsed') for x in task['lookback']['paper']] or '未写明'}",
          f"- 预测期：{task['label']['horizon']}（{task['label']['horizon_basis']}）；信号到建仓的滞后：{task['label']['lag']}（{task['label']['lag_basis']}）",
          f"- 成熟规则：{task['label']['maturity_rule']}"]
    L += ["", "## 样本划分", ""]
    for sp in task["splits"]["paper"]:
        L.append(f"- 原文：{sp['role']} {sp['start_year']}–{sp['end_year']}")
    L.append(f"- 本次选择：{task['splits']['chosen'] or '未指定'}；独立测试窗口：{task['splits']['independent_test'] or '未指定'}")
    L += ["", f"## 评估指标", "", f"- 必需：{', '.join(task['evaluation']['required_metrics'])}"]
    for it in task["evaluation"]["paper_reported_results"]:
        L.append(f"- 原文报告：{it['value']}（{it.get('results')}）")
    L += ["", "## DSL 映射", ""]
    if task["dsl"]["expression"]:
        L += ["```json", json.dumps(task["dsl"]["expression"], ensure_ascii=False), "```"]
    L += [f"- {r['code']}：{r['detail']}" for r in task["dsl"]["reasons"]] or ["- 无问题"]
    L += ["", "## 未解决事项", "", "| 事项 | 阻塞 | 来源 | 问题 |", "|---|---|---|---|"]
    for u in task["unresolved"]:
        L.append(f"| {u['item']} | {'是' if u['blocking'] else '否'} | {u['source']} | {u['question']} |")
    L += ["", "## 时点约束", ""] + [f"- {p['rule']}（{p['basis']}）" for p in task["pit_constraints"]]
    return "\n".join(L) + "\n"


def export_research_task(task: dict, out_dir, basename: str = "research_task") -> dict:
    res = validate_research_task(task)
    if not res["valid"]:
        raise PaperError("SCHEMA_INVALID", "; ".join(e["code"] + ": " + e["detail"] for e in res["errors"][:5]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp, mp = out / f"{basename}.json", out / f"{basename}.md"
    jp.write_text(json.dumps(task, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    mp.write_text(task_markdown(task), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}
