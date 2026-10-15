"""Research-definition consent gate. Code, not model text, decides whether a changed definition may run."""
import re
import uuid

from .contracts import fingerprint

# Tools that create a new study and therefore fix a research definition.
DEFINITION_TOOLS = frozenset({"qrtk_factor_study", "qrtk_expression_study", "qrtk_paper_research"})
# Tools whose substitutions are decided by deterministic program code, not by the model's plan text.
SELF_GATED_TOOLS = frozenset({"qrtk_paper_research"})
# Data discovery tools: a Skill limited to them can report a blocker but never calculate.
DISCOVERY_TOOLS = frozenset({"list_research_resources", "qrtk_data_quality"})
# Free-text arguments do not change what is computed.
DESCRIPTIVE_ARGUMENTS = frozenset({"hypothesis", "reason", "parent_study_id"})
SUBSTITUTE_NAME = re.compile(r"exploratory|substitut|proxy|fallback|surrogate")
REJECT = ("不要", "不同意", "拒绝", "不用", "不行", "不可以", "取消", "算了", "不接受", "不替代", "别替代", "别换")
ACCEPT = ("同意", "可以", "好的", "好吧", "行吧", "确认", "接受", "先完成", "就这样", "按这个", "执行", "开始", "没问题",
          "跑吧", "做吧")
REJECT_EN = re.compile(r"\b(no|don't|do not|reject|decline)\b")
ACCEPT_EN = re.compile(r"\b(ok|okay|yes|agree|sure|go ahead)\b")
CONFIRM_HINT = "回复“同意”后才会执行该替代研究；回复“不要替代”将保留原研究定义，不运行替代实验。"


class ValidationPassed(Exception):
    """Raised by a calculation Tool in validate-only mode after Schema, policy, contract and sample checks, before computing."""


class DefinitionDecisionRequired(Exception):
    """A paper pipeline found substitutions the user must accept first. Carries a program-built proposal; nothing ran."""
    def __init__(self, proposal):
        super().__init__('DEFINITION_DECISION_REQUIRED')
        self.proposal = proposal


class CodeApprovalRequired(Exception):
    """A new (model-written) implementation needs human approval before any execution. Carries the review package."""
    def __init__(self, package):
        super().__init__('CODE_APPROVAL_REQUIRED')
        self.package = package


CODE_APPROVAL_SECONDS = 1800


def code_approval_text(p):
    """Program-rendered review package; the model cannot alter it."""
    lines = ['新算法需要你的审核才能运行（审核前没有执行任何候选代码）：',
             '· 计算什么：' + p['what'], '· 为什么现有DSL不能完成：' + p['why_not_dsl'],
             '· 可信审核：' + p['review'], '· 数据与权限：' + p['permissions'], '· 风险：' + p['risks'],
             '· 代码指纹：' + p['source_sha256'][:12] + '（完整SHA-256与审核包已登记）', '',
             '----- 候选源码 -----', p['source'].rstrip(), '-------------------', '',
             '回复“同意”即批准运行这一份代码（仅此SHA、仅此研究定义，30分钟内有效）；回复“拒绝”则不运行，研究记录为阻断。']
    return '\n'.join(lines)


CODE_ACCEPT = ("同意", "批准", "确认运行", "允许运行", "可以运行", "同意运行", "批准运行")
CODE_ACCEPT_EN = re.compile(r"\b(approve|approved|i approve)\b")
HEDGE = ("看起来", "好像", "似乎", "还行", "大概", "也许", "吗", "?", "？", "不确定", "再看看", "先别")


def code_consent(text):
    """Stricter reading for running new code: an explicit approval word, no hedge or question; any refusal wins."""
    value = text.strip().lower()
    if user_consent(value) == "reject":
        return "reject"
    if any(h in value for h in HEDGE):
        return "unclear"
    if any(x in value for x in CODE_ACCEPT) or CODE_ACCEPT_EN.search(value):
        return "accept"
    return "unclear"


def user_consent(text):
    """Lexical reading of the user's own words; one of accept / reject / unclear. Any refusal wins."""
    value = text.strip().lower()
    if any(x in value for x in REJECT) or REJECT_EN.search(value):
        return "reject"
    if any(x in value for x in ACCEPT) or ACCEPT_EN.search(value):
        return "accept"
    return "unclear"


def definitional_arguments(arguments):
    return {k: v for k, v in arguments.items() if k not in DESCRIPTIVE_ARGUMENTS}


def describe_call(tool, arguments):
    """Deterministic, program-rendered description of what a held tool call would compute."""
    items = []
    if tool == "qrtk_paper_research":
        return "论文研究：%s；因子：%s；冻结计划 %s" % (arguments.get("paper", "")[:12], arguments.get("factor", ""),
                                             arguments.get("plan_sha256", "")[:12])
    if tool == "qrtk_expression_study":
        try:
            from .factor_expression import inspect
            items.append("公式：" + inspect(arguments["expression"])["formula"])
        except Exception:
            items.append("公式：表达式未通过本地检查")
        if arguments.get("factor_name"):
            items.append("因子名：" + arguments["factor_name"])
    else:
        items.append("固定因子：%s，回看 %s 日" % (arguments.get("factor_id"), arguments.get("lookback")))
    items.append("预测期 horizon：%s" % arguments.get("horizon"))
    items.append("分组：%s；标准化：%s" % (arguments.get("n_groups"), arguments.get("standardization")))
    items.append("数据：%s" % arguments.get("resource_id"))
    return "；".join(items)


def proposal(*, source, skill_id, original_goal, change, research_goal, tool=None, arguments=None):
    value = {"id": uuid.uuid4().hex, "source": source, "skill_id": skill_id, "original_goal": original_goal[:2000],
             "change": change[:1000], "research_goal": research_goal[:2000]}
    if tool is not None:
        # The exact arguments are stored so a confirmed run executes what the user saw, not a regenerated call.
        value.update(tool=tool, arguments=arguments, description=describe_call(tool, arguments),
                     definition_sha256=fingerprint(definitional_arguments(arguments)))
    return value


def proposal_text(value):
    lines = ["当前研究定义没有执行，也没有运行替代实验。", "受阻原因与拟议改变：" + value["change"]]
    if value.get("description"):
        lines.append("拟执行的替代方案（由程序根据工具参数生成）：" + value["description"])
    if value.get("required_phrase"):
        # an asset substitution: "同意" alone never confirms it
        lines.append("回复“" + value["required_phrase"] + "”后才会执行该非忠实替代研究（只回复“同意”不会执行）；"
                     "回复“不要替代”将保留原研究定义，不运行替代实验。")
    else:
        lines.append(CONFIRM_HINT)
    return "\n".join(lines)


def held_call(arguments, *, plan, tool):
    """Return the declared/marked definition change for a new-study call, or ''."""
    if tool not in DEFINITION_TOOLS or tool in SELF_GATED_TOOLS:
        return ""
    declared = str(plan.get("definition_change", "")).strip()
    if declared:
        return declared
    if SUBSTITUTE_NAME.search(str(arguments.get("factor_name", ""))):
        return "工具参数将因子标记为替代或探索版本（%s），但规划未声明与原研究定义的差异。" % arguments["factor_name"]
    return ""


def authorized(authorization, tool, arguments):
    """An accepted proposal authorizes only the exact definition the user saw."""
    if not authorization or authorization.get("tool") is None:
        return False
    return authorization["tool"] == tool and authorization["definition_sha256"] == fingerprint(definitional_arguments(arguments))
