"""C6R4: three small fixes after the C6R3 isolated DeepSeek run (records/deepseek_isolated/LIVE1_REPORT_CN.md).

1. Amihud's ILLIQ_iy averages |R|/VOLD over D_iy = "the number of days for which data are available for stock i in year
   y" (Amihud 2002, p.4). The trusted IR has only fixed-row windows; a fixed number of days (250) is a different definition.
   The window is blocked with its own reason, never replaced by a nominal length.
2. "同意，但先解释一下风险" is not consent (no approval event, nothing runs), and the reply is an actual explanation of the
   risks / limits / differences from the paper, not the proposal again.
3. A block names its source in the user's terms: unreadable original, unsupported operator, uncertain mathematics, or a
   genuine misreading by the model.
"""
import gzip
import json
import time
from types import SimpleNamespace

import pytest

from paper_agent.reconcile import CALENDAR_COUNT, SOURCE_CN, SOURCE_HINT, bind_parameters, classify
from paper_agent.understanding import verify
from research_agent.definition_gate import explanation, proposal, risk_text
from test_definition_gate import GateProvider, chat, decision
from test_v1beta_semantics import FIX, PROFILE, codes, load, plan, read

D_MEANING = "number of days for which data are available for stock i in year y"


# ------------------------------------------------------------------ 1. calendar windows (Amihud D_iy)

@pytest.mark.parametrize("text", [D_MEANING, "the actual number of trading days in the month", "D 为当月实际交易日数",
                                  "当年有数据的交易日数", "days with data", "count of valid days in the quarter"])
def test_calendar_counts_are_recognised(text):
    assert CALENDAR_COUNT.search(text)


@pytest.mark.parametrize("text", ["the past 250 trading days", "52-week high", "12-month momentum", "过去20个交易日",
                                  "number of shares outstanding", "number of days to maturity", "21 trading days"])
def test_fixed_windows_are_not_calendar_counts(text):
    assert not CALENDAR_COUNT.search(text)


def test_a_declared_calendar_count_blocks_once_with_its_own_reason():
    latex = r"ILLIQ_{i,y} = \frac{1}{D_{i,y}} \sum_{d=1}^{D_{i,y}} \frac{|R_{i,y,d}|}{VOLD_{i,y,d}}"
    params = [{"symbol": "D_{i,y}", "meaning": D_MEANING, "value": None, "status": "unstated", "citations": []}]
    _, records, conf = bind_parameters(latex, params, lambda cits: [], data_symbols=("R", "VOLD"))
    assert [c["code"] for c in conf] == ["CALENDAR_WINDOW_UNSUPPORTED"]          # not also UNDECLARED_SYMBOLIC_COUNT
    assert conf[0]["blocking"] and "250" in conf[0]["detail"] and "代码审批" in conf[0]["detail"]
    assert classify(conf[0]) == "unsupported_notation"


def test_amihud_first_reading_with_D_is_blocked_not_repaired_to_a_fixed_length():
    ev, _ = load("amihud")
    if not Path(FIX / "amihud.json.gz").is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(FIX / "amihud.json.gz", "rt", encoding="utf-8"))
    raw = json.loads(next(r["raw_output"] for r in d["replies"] if r["purpose"] == "paper_understanding"))
    assert "D_{i,y}" in raw["factors"][0]["formula_latex"]
    f = verify(raw, ev)["factors"][0]
    assert "CALENDAR_WINDOW_UNSUPPORTED" in codes(f) and f["status"] == "BLOCKED"
    c = next(c for c in f["conflicts"] if c["code"] == "CALENDAR_WINDOW_UNSUPPORTED")
    assert c["source"] == "unsupported_notation" and c["source_cn"].startswith("算子不支持")


def test_amihud_nominal_250_reading_never_reaches_execution(tmp_path):
    ev, u, _ = read("amihud", tmp_path)                    # the recorded repair: mean_{k=0}^{249}
    f = u["factors"][0]
    assert "249" in f["formula"]["latex"] and "CALENDAR_WINDOW_UNSUPPORTED" in codes(f)
    p, _, _ = plan(ev, u, PROFILE, factor=f["name"])
    assert p["status"] == "BLOCKED" and not p.get("ir_execution_json") and not p.get("warmup_rows")
    from research_agent.paper_tools import blocked_text
    text = blocked_text(dict(p, name="Amihud_2002.pdf", factor=f["name"]))
    assert "CALENDAR_WINDOW_UNSUPPORTED" in text and "算子不支持" in text and "不是模型读错" in text
    assert "没有执行任何计算，也没有改用替代定义" in text


def test_the_prompts_no_longer_offer_a_nominal_length():
    from paper_agent import understanding
    src = open(understanding.__file__, encoding="utf-8").read()
    assert "one year of daily data = 250 trading days" not in src and "use its nominal length" not in src
    assert "never replace it with a nominal length" in src


@pytest.mark.parametrize("name", ["gh", "macd", "ma", "alpha101", "huatai", "aqr", "heston", "condmat", "ti1110"])
def test_recorded_readings_of_other_papers_have_no_calendar_window(name):
    ev, _ = load(name)
    if not Path(FIX / f"{name}.json.gz").is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(FIX / f"{name}.json.gz", "rt", encoding="utf-8"))
    checked = 0
    for r in d["replies"]:
        if r["purpose"] == "paper_understanding":
            try:
                raw = json.loads(r["raw_output"])
            except json.JSONDecodeError:
                continue                        # a recorded malformed model output (the pipeline retried it)
            checked += 1
            for f in verify(raw, ev)["factors"]:
                assert "CALENDAR_WINDOW_UNSUPPORTED" not in codes(f), (name, f["name"])
    assert checked


# ------------------------------------------------------------------ 2. "同意，但先解释风险"

CHANGE = ("论文原文与当前方案的差异：\n- 论文按年度计算，本方案按日滚动计算\n- 论文使用美国股票，本方案使用A股个股\n"
          "- 回看窗口未在论文中写明，由程序按交易日行数换算")
MODEL_RISK = ("主要风险有三点：第一，论文按年度计算而本方案按日滚动，因子含义会变化。第二，A股涨跌停会使流动性指标失真。"
              "第三，回看窗口是程序换算的，不是论文原文。按你的同意，现在执行已保存方案。")


class _Stop(Exception):
    pass


def talk(tmp_path, words, reply, *, code=None, required_phrase=None):
    from test_quant_integration import research
    fx = research.__wrapped__(tmp_path)
    app = chat(fx, tmp_path, GateProvider([decision("reply", reply=reply, consent="accept")]))
    session = app.store.session(app.session_id)
    if code:
        session["pending_code_approval"] = code
    else:
        args = {"paper": "a" * 64, "factor": "ILLIQ", "plan_sha256": "b" * 64}
        pending = proposal(source="paper_program", skill_id="paper_research", original_goal="研究论文因子", change=CHANGE,
                           research_goal="研究论文因子", tool="qrtk_paper_research", arguments=args)
        if required_phrase:
            pending["required_phrase"] = required_phrase
        session["pending_definition"] = pending
    app.store.save_session(session)
    ran = []

    class Sentinel:
        skill = SimpleNamespace(id="paper_research", version="test", digest="a" * 64)
        policy = SimpleNamespace(budget=SimpleNamespace(max_model_calls=8))

        def create(self, *a, **k):
            ran.append("create")
            raise _Stop()
    app.workflow_factory = lambda skill: Sentinel()
    text = app.turn(words)
    rows = app.store.session_turns(app.session_id)
    kinds = [e["kind"] for e in app.store.events(rows[-1]["route_task_id"])]
    return text, kinds, ran, app.store.session(app.session_id)


@pytest.mark.parametrize("words", ["同意，但先解释一下风险", "可以，但先解释一下风险", "同意吗？先说说风险"])
def test_explain_the_risks_first_answers_the_question_and_approves_nothing(tmp_path, words):
    text, kinds, ran, session = talk(tmp_path, words, MODEL_RISK)
    assert "DEFINITION_CHANGE_CONFIRMED" not in kinds and not ran and session["pending_definition"]
    assert "A股涨跌停会使流动性指标失真" in text                      # the model's actual explanation
    assert "按你的同意" not in text and "现在执行" not in text           # a claim that something runs is removed
    assert "受阻原因与拟议改变" not in text                              # not the proposal again
    assert "尚未执行" in text and "回复“同意”" in text


def test_without_a_model_explanation_the_program_lists_the_risks_and_differences(tmp_path):
    text, kinds, ran, session = talk(tmp_path, "同意，但先解释一下风险", "按你的同意，现在执行。")
    assert "DEFINITION_CHANGE_CONFIRMED" not in kinds and not ran
    assert "当前方案的主要风险、限制及与论文原文的差异" in text
    assert "论文按年度计算，本方案按日滚动计算" in text and "论文使用美国股票，本方案使用A股个股" in text


def test_an_asset_substitution_also_explains_and_still_needs_its_exact_words(tmp_path):
    text, kinds, ran, _ = talk(tmp_path, "同意，但先解释一下风险", MODEL_RISK + "回复“同意”即可执行。", required_phrase="同意用A股个股做探索性替代")
    assert "DEFINITION_CHANGE_CONFIRMED" not in kinds and not ran
    assert "A股涨跌停会使流动性指标失真" in text and "回复“同意”即可执行" not in text
    assert "同意用A股个股做探索性替代" in text


def test_explain_the_risks_of_new_code_approves_no_code(tmp_path):
    code = {"id": "c" * 32, "source_sha256": "d" * 64, "what": "按年度计算ILLIQ", "why_not_dsl": "可信公式没有按日历期间分组的算子",
            "review": "已知真值测试", "permissions": "只读行情", "risks": "按日历年分组时缺失日处理与论文可能不同",
            "expires_at": time.time() + 600}
    text, kinds, ran, session = talk(tmp_path, "同意，但先解释一下风险", "", code=code)
    assert "CODE_APPROVED" not in kinds and "CODE_APPROVAL_UNCLEAR" in kinds and not ran and session["pending_code_approval"]
    assert "尚未运行新代码" in text and "按日历年分组时缺失日处理与论文可能不同" in text and "可信公式没有按日历期间分组的算子" in text


def test_the_live1_reply_loses_only_its_claim_that_the_experiment_runs():
    # the recorded DeepSeek reply to "同意，但先解释一下风险。" (records/deepseek_isolated/live1_evidence, 2026-10-18), abridged
    live = ("主要风险：\n1. 不是论文复现：论文原文公式不可机读，本次公式是按原文文字重述的。2. 价格口径：数据只有未复权价格，"
            "拆股、分红会造成虚假跳变。3. 窗口严格性：252个交易日窗口内每天都必须有有效值，新股或停牌较多的股票会被剔除。"
            "以上风险不改变已保存的替代定义，现按你的明确同意执行该探索性实验。")
    text = explanation(live, {"change": CHANGE})
    assert "执行该探索性实验" not in text and "按你的明确同意" not in text
    assert "不是论文复现" in text and "未复权价格" in text and "新股或停牌较多的股票会被剔除" in text


def test_risk_text_and_explanation_helpers():
    value = {"change": CHANGE}
    assert risk_text(value).count("\n") == 3
    assert explanation("", value) == risk_text(value)
    assert explanation("这个方案有风险。回复“同意”即可执行。", value) == risk_text(value)        # what is left is too short
    assert explanation(MODEL_RISK, value).endswith("不是论文原文。")


# ------------------------------------------------------------------ 3. where a block comes from

@pytest.mark.parametrize("conflict,source", [
    ({"code": "FORMULA_RECONSTRUCTION_UNVERIFIED", "detail": "第二次独立重建程序也无法读取（UNSUPPORTED_WINDOW_BOUNDS: _{k=0}）"},
     "unsupported_notation"),
    ({"code": "FORMULA_RECONSTRUCTION_UNVERIFIED", "detail": "原文第[4]页的公式程序无法读取，尚未经过独立复核"}, "extraction_error"),
    ({"code": "FORMULA_READINGS_DISAGREE", "detail": "两次独立重建结果不一致"}, "paper_ambiguity"),
    ({"code": "CONDITIONAL_NOT_REPRESENTABLE", "detail": "条件运算"}, "unsupported_notation"),
    ({"code": "CALENDAR_WINDOW_UNSUPPORTED", "detail": "日历期间"}, "unsupported_notation"),
    ({"code": "DEFINITION_SCOPE_UNCERTAIN", "reason": "PRINTED_EXPRESSION_UNBALANCED"}, "extraction_error"),
    ({"code": "DEFINITION_SCOPE_UNCERTAIN", "reason": "TWO_DEFINITIONS"}, "paper_ambiguity"),
    ({"code": "PRINTED_FORMULA_NOT_CHECKED", "detail": "uses function 'rank' the program cannot evaluate"}, "unsupported_notation"),
    ({"code": "MODEL_FORMULA_CONTRADICTS_PAPER", "detail": "读数与原文矛盾"}, "ai_misreading"),
])
def test_blocks_are_attributed_to_their_real_source(conflict, source):
    assert classify(conflict) == source


def test_the_four_sources_read_as_the_user_named_them_and_carry_a_hint():
    assert SOURCE_CN["extraction_error"].startswith("原文无法解析")
    assert SOURCE_CN["unsupported_notation"].startswith("算子不支持")
    assert SOURCE_CN["paper_ambiguity"].startswith("数学语义不确定")
    assert SOURCE_CN["ai_misreading"].startswith("模型理解错误")
    assert set(SOURCE_HINT) == set(SOURCE_CN)
    from research_agent.paper_tools import blocked_text
    stops = [{"code": "CALENDAR_WINDOW_UNSUPPORTED", "detail": "x", "source": "unsupported_notation",
              "source_cn": SOURCE_CN["unsupported_notation"]},
             {"code": "FORMULA_RECONSTRUCTION_UNVERIFIED", "detail": "y", "source": "extraction_error",
              "source_cn": SOURCE_CN["extraction_error"]},
             {"code": "CONDITIONAL_NOT_REPRESENTABLE", "detail": "z", "source": "unsupported_notation",
              "source_cn": SOURCE_CN["unsupported_notation"]}]
    text = blocked_text({"name": "p.pdf", "factor": "F", "hard_stops": stops})
    assert text.count("说明（算子不支持）") == 1 and text.count("说明（原文无法解析）") == 1 and "说明（模型理解错误）" not in text
