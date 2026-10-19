"""Candidate6 recovery, design A: the paper's own definition decides whether a reading may become trusted IR.

Every layout below is a recorded counterexample of an earlier audit (Codex C6/C7/C8/C9 audits, C10/C11 reports), run
through the REAL understand -> independent reading -> planner.plan entry on the real Alpha#23 evidence of 101 Formulaic
Alphas. Each layout is read twice:
  * "sign"    -- the real recorded model reading (Round C E01): sign(high - mean) * (-delta(high, 2));
  * "dropped" -- two agreeing readings that silently drop the condition: -delta(high, 2) (the "two wrong readings agree"
                 attack); only the program's own reading of the definition can stop it.
Positive controls: the same entry admits a clean printed formula read correctly, and clean neighbours of a conditional.
"""
import copy
import gzip
import json
import re
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures_v1beta" / "papers" / "alpha101.json.gz"
SIMPLE = "Alpha#23: (-1 * delta(high, 2)); threshold = sum(high, 20) / 20"
ORIG = "Alpha#23: (((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)"
Q = "(-1 * delta(high, 2))"
LAYOUTS = [   # (name, blocks replacing the real Alpha#23 block, quote) -- dict blocks carry kind / section overrides
    # C6 audit F01, C7 re-audit, C8 audit (12)
    ("c6_short_quote", [ORIG], "sum(high, 20) / 20"),
    ("c8_original_full", [ORIG], ORIG),
    ("c8_multiline_late", [ORIG.replace("? (", "?\n    (")], Q),
    ("c8_cross_block_forward", [SIMPLE, "Apply this value IF high exceeds the threshold; ELSE return zero."], Q),
    ("c8_cross_block_otherwise", [SIMPLE, "The preceding value applies only above the threshold, otherwise the value is zero."], Q),
    ("c8_cross_block_chinese", [SIMPLE, "若最高价超过阈值则使用前述值，否则为零。"], Q),
    ("c8_unlabelled_next_sentence", [SIMPLE.replace("Alpha#23: ", "") + ". The preceding value is used if high exceeds the threshold, otherwise zero."], Q),
    ("c8_definition_internal_label", ["Alpha#23: IF high exceeds the 20 day mean, then use the following branch, ELSE zero.\nBranch: (-1 * delta(high, 2)); threshold = sum(high, 20) / 20"], Q),
    ("c8_missing_label_same_sentence", ["IF high > sum(high, 20) / 20 use (-1 * delta(high, 2)) ELSE 0"], Q),
    ("c8_decimal_if", ["Alpha#23: IF high > 0.5 * sum(high, 20) / 20 use (-1 * delta(high, 2)) ELSE 0"], Q),
    ("c8_long_block_gap", ["Alpha#23: IF high > mean then value ELSE zero.", "Parameter description continues.", "More parameter description.",
                           "Observation notation.", "Value: (-1 * delta(high, 2)); threshold = sum(high, 20) / 20"], Q),
    ("c8_normalized_quote_wrong_offset", ["Alpha#22: high - low\n" + ORIG + "\nAlpha#24: close - open"], "(-1 *  delta(high, 2))"),
    # Codex C9 audit, C9-R01 (12 new layouts)
    ("c9_if_else_separate_blocks", [SIMPLE, "IF high exceeds the threshold, use this factor.", "ELSE return zero."], Q),
    ("c9_named_threshold_subject", [SIMPLE, "The threshold is used if high exceeds its mean, else this value is zero."], Q),
    ("c9_dependent_rule_subject", [SIMPLE, "The multiplier equals one if high exceeds the threshold, otherwise it equals zero. Multiply the factor by the multiplier."], Q),
    ("c9_heading_continuation", [SIMPLE, {"text": "Parameter and applicability conditions", "kind": "heading"},
                                 "Alpha#23 applies only if high exceeds the mean, otherwise zero."], Q),
    ("c9_section_continuation", [SIMPLE, {"text": "This factor is used if high exceeds the threshold, else zero.", "section": "audit-other-section"}], Q),
    ("c9_label_repeated", [SIMPLE, "Alpha#23: Applicability: if high exceeds the mean use the factor, otherwise zero."], Q),
    ("c9_internal_equation_number", [SIMPLE, "(1) IF high exceeds the threshold, this value is used; ELSE zero."], Q),
    ("c9_cross_sentence_if_else", [SIMPLE + " IF high exceeds the mean, use this value. ELSE use zero."], Q),
    ("c9_prose_conditional_precedes_label", ["If high exceeds the mean use the following factor, else return zero.", SIMPLE], Q),
    ("c9_formula_order_reversed", [SIMPLE, "The factor below is used if high exceeds the threshold, otherwise zero."], Q),
    ("c9_subject_output", [SIMPLE, "The output is zero unless high exceeds the threshold."], Q),
    ("c9_decimal_threshold", [SIMPLE, "For this signal: high > 0.25 ? this value : 0."], Q),
    # C10 report: D01 (condition before the label), D02 (condition in a heading)
    ("c10_d01_condition_before_label", ["If the high exceeds its twenty-day mean use the value; else zero.", SIMPLE], Q),
    ("c10_d02_condition_in_heading", [SIMPLE, {"text": "This factor is zero unless high exceeds threshold.", "kind": "heading"}], Q),
]
SIGN = ("Alpha23_{i,t} = \\operatorname{sign}(high_{i,t} - \\frac{\\sum_{k=0}^{19} high_{i,t-k}}{20}) * (-1) * "
        "(high_{i,t} - high_{i,t-2})")
DROPPED = "Alpha23_{i,t} = -1 * (high_{i,t} - high_{i,t-2})"
STOPS = {"CONDITIONAL_NOT_REPRESENTABLE", "DEFINITION_SCOPE_UNCERTAIN", "MODEL_FORMULA_CONTRADICTS_PAPER", "PRINTED_FORMULA_NOT_CHECKED"}


def run(tmp_path, blocks, quote, reading, *, factor="Alpha#23", replace=("p9-b119",), latex=None):
    """The real entry on the Alpha101 evidence with `replace` blocks swapped for `blocks`; `reading` 'sign' keeps the
    recorded model replies, 'dropped' / 'custom' makes all three readings agree on `latex` (default -delta(high,2))."""
    from paper_agent.evidence import PaperEvidence
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ScriptedClient
    from paper_agent.planner import plan as make_plan
    from paper_agent.understanding import understand
    from test_v1beta_semantics import PROFILE
    if not FIX.is_file():
        pytest.skip("Private paper evidence fixture omitted from public package")
    if not Path(FIX).is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = copy.deepcopy(json.load(gzip.open(FIX, "rt", encoding="utf-8")))
    allb = d["doc"]["blocks"]
    first = next(i for i, b in enumerate(allb) if b["id"] == replace[0])
    last = next(i for i, b in enumerate(allb) if b["id"] == replace[-1])
    new = [dict(allb[first], id="p9-b119" if i == 0 else "rc-block-%d" % i, **(t if isinstance(t, dict) else {"text": t}))
           for i, t in enumerate(blocks)]
    allb[first:last + 1] = new
    texts = [b["text"] for b in new]
    norm = lambda s: re.sub(r"\s+", " ", s)
    qi = next(i for i, t in enumerate(texts) if norm(quote) in norm(t))
    for p in d["passages"]:
        if p["id"] == "P0112":
            p.update(text=texts[qi], block_id=new[qi]["id"], char_start=0, char_end=len(texts[qi]))
    ev = PaperEvidence(d["doc"], d["spec"], d["passages"])
    script = {k: [] for k in ("paper_understanding", "independent_reading")}
    # a blocking, investigable conflict opens the reader's investigation: the reader stands by its reading (no claim)
    script["paper_investigation"] = [json.dumps({"action": "answer", "findings": []})] * 4
    for r in d["replies"]:
        raw = json.loads(r["raw_output"])
        f = raw["factors"][0] if r["purpose"] == "paper_understanding" else raw
        if reading != "sign":
            f["formula_latex"] = latex or DROPPED
            f["parameters"] = [] if latex else [p for p in f["parameters"] if p["symbol"] == "L"]
            proto = next(s for s in f["symbols"] if s["symbol"] == "high")
            used = [x for x in ("open", "high", "low", "close", "volume") if re.search(rf"\b{x}_", latex or DROPPED)]
            f["symbols"] = [dict(proto, symbol=x, data_field=x, meaning=f"daily {x} price") for x in used]
        if r["purpose"] == "paper_understanding":
            f["name"] = factor
            f["formula_citations"] = f["verbal_definition"]["citations"] = [{"passage": "P0112", "quote": quote}]
            for prm in f["parameters"]:
                prm["citations"] = [{"passage": "P0112", "quote": "sum(high, 20) / 20" if prm["symbol"] == "N" else "delta(high, 2)"}]
            if "sum(high, 20) / 20" in texts[qi] and reading == "sign":
                f["symbols"][0]["citations"].append({"passage": "P0112", "quote": "sum(high, 20) / 20"})
        else:
            for prm in f.get("parameters") or []:
                prm["citations"] = [{"passage": "P0112", "quote": "sum(high, 20) / 20" if prm["symbol"] == "N" else "delta(high, 2)"}]
        script[r["purpose"]].append(json.dumps(raw))
    ledger = TaskLedger(tmp_path, goal="recovery", budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                              design_revisions=2, orchestration_turns=0))
    u = understand(ev, ScriptedClient(script), ledger, focus=factor)
    p, _, _ = make_plan(ev, u, PROFILE, factor=factor)
    return p, ev


@pytest.mark.parametrize("reading", ["sign", "dropped"])
@pytest.mark.parametrize("name,blocks,quote", LAYOUTS, ids=[x[0] for x in LAYOUTS])
def test_no_recorded_layout_lets_a_conditional_definition_become_trusted_ir(tmp_path, name, blocks, quote, reading):
    p, ev = run(tmp_path, blocks, quote, reading)
    assert ev.verify_quote("P0112", quote), "the counterexample's quote is real"
    codes = {h["code"] for h in p["hard_stops"]}
    assert p["status"] == "BLOCKED" and p.get("route") not in ("trusted_ir", "dsl"), (name, reading, p["status"], p.get("route"), codes)
    assert codes & STOPS, (name, reading, codes)
    if reading == "dropped":     # no sign to give it away: the program's own reading of the definition must stop it
        assert codes & {"CONDITIONAL_NOT_REPRESENTABLE", "DEFINITION_SCOPE_UNCERTAIN"}, (name, codes)


def test_c10_d03_an_added_sign_term_on_an_unconditional_printed_formula_is_stopped(tmp_path):
    """Source -delta(high,2) (no condition); two agreeing readings add a sign term. Hand values: highs 17x10, 3, 8, 1 ->
    source +2, reading -2."""
    p, _ = run(tmp_path, ["Alpha#23: (-1 * delta(high, 2))"], Q, "custom", latex=SIGN.replace("Alpha23_{i,t} = ", ""))
    codes = {h["code"] for h in p["hard_stops"]}
    assert p["status"] == "BLOCKED" and "MODEL_FORMULA_CONTRADICTS_PAPER" in codes, codes
    import numpy as np
    high = np.array([10.0] * 17 + [3.0, 8.0, 1.0])
    delta2, mean = high[-1] - high[-3], high.mean()
    assert -delta2 == 2.0 and np.sign(high[-1] - mean) * -delta2 == -2.0


@pytest.mark.parametrize("printed", ["Alpha#23: (1e-400 * close * 10^300)", "Alpha#23: (1e-400 * close * 10^300 * 10^100)"])
def test_c11_d01_a_literal_that_underflows_never_makes_a_different_formula_agree(tmp_path, printed):
    """C11 report D01: the source 1e-400 * close * 10^300 (* 10^100) was parsed through float as 0 and a reading
    0 * close was certified (close = 2: source 2e-100, or 2; reading 0). The printed literal is outside the exactly
    comparable range, so the printed formula is reported as not checkable and the reading is not trusted."""
    from paper_agent.printed import Unsupported, parse_printed
    with pytest.raises(Unsupported, match="exactly comparable"):
        parse_printed(printed.split(": ", 1)[1])
    p, _ = run(tmp_path, [printed], printed.split(": ", 1)[1], "custom", latex="0 * close_{i,t}")
    codes = {h["code"] for h in p["hard_stops"]}
    assert p["status"] == "BLOCKED" and "PRINTED_FORMULA_NOT_CHECKED" in codes, codes
    from decimal import Decimal
    assert Decimal("1e-400") * 2 * Decimal(10) ** 300 * Decimal(10) ** 100 == 2      # the source's true value at close = 2


def test_a_clean_printed_formula_read_correctly_is_admitted(tmp_path):
    p, _ = run(tmp_path, ["Alpha#23: (-1 * delta(high, 2))"], Q, "dropped")
    codes = {h["code"] for h in p["hard_stops"]}
    assert not codes & STOPS, codes
    assert p["status"] != "BLOCKED" and p.get("route") in ("trusted_ir", "dsl"), (p["status"], p.get("route"), codes)


@pytest.mark.parametrize("factor,quote,latex", [
    ("Alpha#22", "(-1 * (high - low))", "-1 * (high_{i,t} - low_{i,t})"),
    ("Alpha#24", "(close - open)", "close_{i,t} - open_{i,t}"),
])
def test_clean_neighbours_of_a_conditional_factor_are_admitted(tmp_path, factor, quote, latex):
    blocks = ["Alpha#22: (-1 * (high - low))", ORIG, "Alpha#24: (close - open)"]
    from paper_agent.printed import numbered_definition
    p, ev = run(tmp_path, blocks, quote, "custom", factor=factor, replace=("p9-b118", "p9-b120"), latex=latex)
    codes = {h["code"] for h in p["hard_stops"]}
    assert not codes & STOPS, (factor, codes)
    assert p["status"] != "BLOCKED" and p.get("route") in ("trusted_ir", "dsl"), (factor, p["status"], codes)


def test_every_real_alpha_is_judged_by_its_own_printed_expression():
    """All 101 printed alphas of the real paper: the conditional verdict of each comes only from its own expression
    (no neighbour pollution across page numbers, wrapped formulas, the list end or the operator glossary after it);
    the alphas whose text layer is damaged are uncertain, never silently read."""
    from types import SimpleNamespace as N
    from paper_agent.printed import CONDITIONAL, PARTIAL_CONDITIONAL, Unsupported, has_conditional, numbered_definition, parse_printed
    if not Path(FIX).is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(FIX, "rt", encoding="utf-8"))
    ev = N(doc=d["doc"], by_id={})
    uncertain, conditional = [], []
    for n in range(1, 102):
        r = numbered_definition(ev, "Alpha", n)
        assert r is not None, n
        if r["uncertain"]:
            uncertain.append(n)
            continue
        expr = r["expressions"][0]
        try:
            own = has_conditional(parse_printed(expr))
        except Unsupported:
            own = bool(CONDITIONAL.search(expr) or re.search(r"[<>]|==|\?", expr))
        joined = "\n".join(r["expressions"] + r["ambiguous"])
        assert bool(CONDITIONAL.search(joined) or PARTIAL_CONDITIONAL.search(joined)) <= own, (n, r["ambiguous"])
        conditional += [n] if own else []
    assert uncertain == [1, 7, 8, 18, 19, 32, 84]           # "[FORMULA_UNRESOLVED]" in the text layer: brackets never close
    assert 23 in conditional and 12 not in conditional and 101 not in conditional


def test_what_the_program_can_check_in_the_real_paper():
    """101 printed alphas: 44 are checked against a reading, 22 print a conditional (not trusted IR; algorithm route), 14
    are damaged in the text layer, and 21 need what the trusted IR or the published data lack (industry neutralisation,
    cross-sectional scale, ts_argmax, market cap). A change of these counts is a change of research coverage."""
    import collections
    from types import SimpleNamespace as N
    from paper_agent.printed import Unsupported, evaluate_printed, has_conditional, numbered_definition, parse_printed
    from paper_agent.reconcile import _panels
    if not Path(FIX).is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(FIX, "rt", encoding="utf-8"))
    ev, panels, cat = N(doc=d["doc"], by_id={}), _panels(rows=320), collections.Counter()
    for n in range(1, 102):
        r = numbered_definition(ev, "Alpha", n)
        try:
            assert not r["uncertain"]
            t = parse_printed(r["expressions"][0])
        except (AssertionError, Unsupported):
            cat["damaged"] += 1
            continue
        if has_conditional(t):
            cat["conditional"] += 1
            continue
        try:
            evaluate_printed(t, panels)
            cat["checkable"] += 1
        except Unsupported:
            cat["unsupported"] += 1
    assert dict(cat) == {"checkable": 44, "conditional": 22, "damaged": 14, "unsupported": 21}


def test_printed_expressions_parse_and_compute_with_the_trusted_conventions():
    from paper_agent.printed import compare_printed, has_conditional, parse_printed
    from paper_research.factor_ir import parse_formula
    t = parse_printed("sign(delta(volume, 1)) * (-1 * delta(close, 1))")              # Alpha#12
    ir = parse_formula(r"\operatorname{sign}(volume_{t} - volume_{t-1}) \cdot (-1 \cdot (close_{t} - close_{t-1}))")["ir"]
    assert not has_conditional(t) and compare_printed(t, ir, {"volume": "volume", "close": "close"})["agree"]
    wrong = parse_formula(r"-1 \cdot (close_{t} - close_{t-1})")["ir"]
    assert not compare_printed(t, wrong, {"volume": "volume", "close": "close"})["agree"]
    t = parse_printed("((close - open) / ((high - low) + .001))")                        # Alpha#101
    ir = parse_formula(r"\frac{close_{t} - open_{t}}{(high_{t} - low_{t}) + 0.001}")["ir"]
    assert compare_printed(t, ir, {k: k for k in ("close", "open", "high", "low")})["agree"]
    t = parse_printed("(-1 * correlation(open, volume, 10))")                            # Alpha#6
    ir = parse_formula(r"-1 \cdot \mathrm{corr}_{k=0}^{9}(open_{t-k}, volume_{t-k})")["ir"]
    assert compare_printed(t, ir, {"open": "open", "volume": "volume"})["agree"]
    for s in ("(a < b) ? c : d", "x || y", "(close > open) * 2"):
        assert has_conditional(parse_printed(s)), s


def test_prose_scope_keeps_another_variables_condition_out_and_a_back_reference_in():
    """George-Hwang's real wording: the winner dummy's 'if ... zero otherwise' is another variable's definition."""
    from types import SimpleNamespace as N
    from paper_agent.printed import CONDITIONAL, prose_definition

    def ev(*texts):
        blocks = [{"id": "B%d" % i, "text": t, "kind": "paragraph", "section": "S"} for i, t in enumerate(texts)]
        return N(by_id={"P%d" % i: {"text": t, "block_id": "B%d" % i, "char_start": 0} for i, t in enumerate(texts)}, doc={"blocks": blocks})
    gh = ("FHH^{i,t-j} (FHL^{i,t-j}) is the 52-week high winner (loser) dummy that takes the value of 1 if the 52-week high "
          "measure for stock i is ranked in the top (bottom) 30% in month t - j, and zero otherwise. The 52-week high measure "
          "in month t - j is the ratio of price level in month t - j to the maximum price achieved in months t - j - 12 to t - j.")
    texts = prose_definition(ev(gh), [{"passage": "P0", "quote": "the ratio of price level in month t - j to the maximum price"}],
                             [], ["52-week high measure"])
    assert texts and not any(CONDITIONAL.search(t) for t in texts)
    later = gh + " This measure is set to zero when the stock was suspended, otherwise it is kept."
    texts = prose_definition(ev(later), [{"passage": "P0", "quote": "the ratio of price level in month t - j to the maximum price"}],
                             [], ["52-week high measure"])
    assert any(CONDITIONAL.search(t) for t in texts)
    before = "The measure below is replaced by zero if the stock is suspended, otherwise kept. The 52-week high measure is the ratio of price to the maximum price."
    texts = prose_definition(ev(before), [{"passage": "P0", "quote": "the ratio of price to the maximum price"}], [], ["52-week high measure"])
    assert any(CONDITIONAL.search(t) for t in texts)


def test_the_conditional_recogniser_works_and_c6s_backspace_defect_is_gone():
    from paper_agent.printed import CONDITIONAL
    from paper_agent.understanding import CONDITIONAL as U
    assert U is CONDITIONAL and "\x08" not in CONDITIONAL.pattern
    for s in ("if high > 0.5 then -delta else 0", "IF X > 1 ELSE 0", "a ? b : c", "x when y, otherwise 0", "若 x>0 则 y", "zero unless y",
              "CASE WHEN a THEN b ELSE c END", "当 x 大于 0 时取 y，否则为 0"):
        assert CONDITIONAL.search(s), s
    for s in ("(close - open) / ((high - low) + 0.001)", "1.5 * close", "sum(high, 20) / 20", "the ratio of price to the maximum price"):
        assert not CONDITIONAL.search(s), s


def test_c6r2_holdout_miss_a_condition_in_words_without_any_keyword(tmp_path):
    """Hold-out H-M01 found on C6R2 (recorded as a failure): "used whenever high is above ...; in all other cases it is 0"
    has no if/else/otherwise, so a reading that silently dropped it was admitted. Any prose beside a printed expression
    now makes the definition uncertain, whatever its wording."""
    blocks = ["Alpha#23: (-1 * delta(high, 2))",
              "Remark. The value above is used whenever high is above sum(high, 20) / 20; in all other cases it is 0."]
    p, _ = run(tmp_path, blocks, Q, "dropped")
    codes = {h["code"] for h in p["hard_stops"]}
    assert p["status"] == "BLOCKED" and "DEFINITION_SCOPE_UNCERTAIN" in codes, codes


def test_prose_restrictions_of_a_factor_are_not_trusted_ir():
    from paper_agent.printed import MODIFIER
    for s in ("For limit-hit stocks the measure is set to zero.", "The ratio is only computed on trading days with volume.",
              "Values are winsorized at the 1% level.", "The factor equals zero for suspended stocks.", "停牌日该因子设为0。"):
        assert MODIFIER.search(s), s
    for s in ("The 52-week high measure is the ratio of price to the maximum price.", "The range is widely used in volatility studies.",
              "MACD is the difference of two exponential moving averages."):
        assert not MODIFIER.search(s), s
