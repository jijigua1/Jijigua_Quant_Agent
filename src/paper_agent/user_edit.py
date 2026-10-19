"""User edits of a proposed paper factor definition (2026-10-17).

The user's natural-language change ("12/26 改成 8/17，预测期 5 天") becomes a small patch: the full new formula in the
program grammar (published fields by name, numbers inline) and/or a horizon. Versions are kept per session over the
paper's own definition (v1): edit appends, undo pops, restore clears. The paper reading is never changed; the planner
re-checks the user version (fields, windows, look-ahead, trusted IR, assets) and it always needs the user's confirmation.
"""
import copy
import hashlib
import json
import re

from .model import ask_json

SCHEMA = {"type": "object", "required": ["intent"], "properties": {
    "intent": {"enum": ["edit", "undo", "restore", "none", "unsupported"]}, "formula_latex": {}, "horizon_days": {},
    "changes_cn": {}}}                               # optional, may be null: checked where they are used

SYSTEM = """You update ONE quantitative factor definition after a user's message. Return JSON only:
{"intent": "edit"|"undo"|"restore"|"none", "formula_latex": "...", "horizon_days": N, "changes_cn": "..."}
- edit: the user changes the formula, a parameter, a data field, a smoothing/initialisation, the prediction horizon, gives a
  missing definition, or asks you for an alternative construction. Write the COMPLETE new formula in formula_latex, starting
  from the CURRENT formula and changing ONLY what the user asked; keep every other field, window, number and operator.
  Leave formula_latex "" when only the horizon changes; set horizon_days only when the user changes it.
- undo: the user takes back the last change. restore: the user wants the paper's original definition again.
- unsupported: the user asks for something this grammar or the daily stock panel cannot express (another data frequency
  such as weekly/monthly/intraday bars, a field that is not listed, future data); say what in changes_cn. Never rewrite it
  silently in daily rows.
- none: anything else (a question, agreement, discussion, a new topic). Never treat a change as agreement. Also none when
  the message only gives values for parameters the paper formula names (e.g. "X=14"): the program binds those itself.
changes_cn: one short Chinese sentence listing exactly what changed.
Formula grammar (only these): fields open, high, low, close, volume, amount written close_{t}, lags close_{t-1};
window over k: \\operatorname{mean}_{k=0}^{13}(...), \\sum_{k=0}^{20}(...), \\max_{k=0}^{251} high_{t-k}, \\min_{k=0}^{n}...,
\\operatorname{std}_{k=0}^{n}(...), inside use close_{t-k}; element-wise \\max(a, b), \\min(a, b); \\operatorname{ema}_{N}(x)
(alpha=2/(N+1), seed = first value), \\operatorname{ema}_{N,sma}(x) (seed = mean of first N), \\operatorname{rma}_{N}(x)
(Wilder, alpha=1/N), \\operatorname{rank}(x) (cross-section), \\operatorname{sign}, \\log, \\sqrt, |x|, \\frac{a}{b}, +, -, \\cdot.
No future values (t+1), no other variables, numbers written out. ONE expression: substitute any auxiliary quantity inline."""


def inline(latex):
    """'A = f(B), \\quad B = g' -> 'A = f((g))': auxiliary definitions written after the main formula are substituted."""
    parts = [x.strip() for x in re.split(r",?\s*\\quad\s*|;\s*", latex or "") if x.strip()]
    main = parts[0] if parts else latex
    for d in parts[1:]:
        lhs, eq, rhs = d.partition("=")
        name = re.match(r"\s*([A-Za-z]+)", lhs)
        if not eq or not name:
            return latex                          # not a definition: left to the parser to refuse
        main = re.sub(r"(?<![A-Za-z\\])" + name.group(1) + r"(?![A-Za-z])(_\{[^}]*\})?", lambda m: "(" + rhs.strip() + ")", main)
    return main


def interpret(client, ledger, *, factor, paper_formula, paper_meanings, blockers, current_formula, current_horizon, text):
    obj, _ = ask_json(client, ledger, purpose="definition_edit", system=SYSTEM, schema=SCHEMA, max_tokens=900, user=json.dumps(
        {"factor": factor, "paper_formula": paper_formula, "paper_symbols": paper_meanings, "why_blocked": blockers,
         "current_formula": current_formula, "current_horizon_days": current_horizon, "user_message": text},
        ensure_ascii=False))
    return obj


def version_id(version):
    return hashlib.sha256(json.dumps({k: version.get(k) for k in ("formula_latex", "horizon_days")},
                                     sort_keys=True).encode()).hexdigest()[:16]


def apply(understanding, factor_name, version, number):
    """A copy of the reading in which `factor_name` computes the user's version; the paper's own entry is kept beside it."""
    u = copy.deepcopy(understanding)
    for f in u["factors"]:
        if f["name"] != factor_name:
            continue
        f["user_version"] = {"n": number, "id": version_id(version), "changes_cn": version.get("changes_cn") or "",
                             "horizon_days": version.get("horizon_days"), "paper_formula": f["formula"].get("latex")}
        if version.get("formula_latex"):
            version = dict(version, formula_latex=inline(version["formula_latex"]))
            # the user's formula names published fields directly: the paper's symbols, parameters and reading conflicts
            # describe the paper's formula, not this one (the planner checks this one afresh)
            f["formula"] = {"latex": version["formula_latex"], "status": "USER", "citations": [], "rejected_citations": []}
            f["parameters"], f["conflicts"], f["status"] = [], [], "USER"
            u["user_parameters"] = {}             # the user's complete formula carries its own numbers
            f["frequency"] = {"value": "daily (user formula in trading-day rows)", "status": "USER", "citations": []}
            try:
                from paper_research.factor_ir import fields_used, parse_formula
                names = fields_used(parse_formula(version["formula_latex"])["ir"])
            except Exception:                    # noqa: BLE001 -- the planner reports the unparseable formula
                names = []
            # every variable of a user formula is a field by name; a name that is not published is refused by the planner
            f["symbols"] = [{"symbol": n, "meaning": f"{n} (user formula)", "kind": "raw_field", "data_field": n, "aggregate": None,
                             "window": None, "price_basis": "user", "adjustment": "unstated", "units": None, "citations": []}
                            for n in names]
    return u
