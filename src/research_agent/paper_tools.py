"""Paper research pipeline as reviewed Tools inside the existing QuantBackend.

One deterministic Tool `qrtk_paper_research(paper, factor)`:
  locate paper (library) -> evidence (cached by SHA) -> model understanding with verified quotes (cached)
  -> plan (substitutions / route) -> [user decision gate] -> DSL route: production expression study
  -> new-algorithm route: model design + static review (cached) -> [human code approval gate]
  -> approved implementation through the production study (cell-by-cell trusted-IR cross-check)
  -> default ROLLING_EXPOSED_TEST revision -> report.
Model calls go through the Workflow's audited runtime (task budget, ledger); the model cannot approve anything.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

from .contracts import ContractError, fingerprint
from .definition_gate import CODE_APPROVAL_SECONDS, CodeApprovalRequired, DefinitionDecisionRequired
from .security import BudgetExhausted, Denied

PIPELINE = 'paper-pipeline/1'
# plans are re-derived (deterministically, no model call) when the planner or the understanding they came from changes
PLANNER_REV = 'planner/4-reconcile-parameters-numbered-factors'
_PROGRAM = None


def program_sha256():
    """Fingerprint of the program that verifies readings and builds plans (paper_agent, paper_research, this module and the
    DSL validator). Cached readings and plans made by another program are never reused as they are (live recheck J1)."""
    global _PROGRAM
    if _PROGRAM is None:
        import hashlib
        src = Path(__file__).resolve().parents[1]
        files = sorted([*(src / 'paper_agent').rglob('*.py'), *(src / 'paper_research').rglob('*.py'),
                        src / 'research_agent' / 'paper_tools.py', src / 'research_agent' / 'factor_expression.py'])
        h = hashlib.sha256()
        for f in files:
            h.update(f.relative_to(src).as_posix().encode() + b'\0' + f.read_bytes() + b'\0')
        _PROGRAM = h.hexdigest()
    return _PROGRAM
from paper_agent.planner import ASSET_PHRASE  # noqa: E402


def _unit_unstated(understanding):
    """True for a non-daily factor whose window repair did not state the unit it counts (the planner cannot convert it)."""
    freq = {f['name']: ((f.get('frequency') or {}).get('value') or '').lower() for f in understanding['factors']}
    return any('window_unit' not in r and not freq.get(r['factor'], '').startswith('daily')
               for r in understanding.get('formula_repairs') or [])


JSON_RULE = ('Reply with exactly one JSON object and nothing else: no Markdown fences, no prose. Inside JSON strings write '
             'every LaTeX backslash doubled (\\\\frac, \\\\operatorname, \\\\le), and escape quotes and newlines.')


class RuntimeClient:
    """paper_agent model-client shape over the Workflow runtime (`_task_context['model']`)."""
    live = True
    _fault_used = False

    def __init__(self, model_call):
        self.model_call = model_call
        self.model = 'workflow-runtime'

    def raw(self, messages, *, purpose, max_tokens, json_mode=True, tools=None):
        from .llm import Message, ModelRequest, Role
        # JSON is parsed by paper_agent.ask_json, which keeps the raw reply and asks for one correction naming the exact
        # parse error. A runtime schema check would discard the reply and retry blind (live R2: two lost understanding calls).
        rule = (Message(Role.SYSTEM, JSON_RULE),) if json_mode else ()
        # Provider JSON mode guarantees a syntactically complete object (live R2: 6 of 9 papers lost a call to a bracket
        # mismatch that the model then repeated verbatim); content is still validated only by ask_json.
        request = ModelRequest(tuple(Message(Role(m['role']), m.get('content') or '') for m in messages) + rule,
                               json_object=json_mode)
        try:
            r = self.model_call(request)
        except BudgetExhausted:
            raise
        u = r.usage
        content = r.content
        if json_mode and os.environ.get('QRA_TEST_CORRUPT_JSON_ONCE') == '1' and not RuntimeClient._fault_used:
            # Pre-release staging only (set by the launcher from a root-owned host.json flag): the first paper reply of the
            # process loses its last character, so the real repair path (ask_json + one corrective call) is exercised.
            RuntimeClient._fault_used = True
            content = content.rstrip()[:-1]
        return {'content': content, 'tool_calls': [], 'model': r.actual_model, 'request_id': r.request_id,
                'usage': {'prompt_tokens': u.input_tokens, 'completion_tokens': u.output_tokens, 'total_tokens': u.total_tokens}}


BLOCK_REASONS = {
    'FORMULA_NOT_ESTABLISHED': '没有找到经原文核验的因子公式或算法步骤，无法确定要计算的内容。',
    'FORMULA_UNPARSEABLE': '程序解析未完成：读出的公式含有当前解析器不支持的写法，经有限次修复与调查后仍无法转为受控公式（这不表示论文没有定义）。',
    'FREE_PARAMETER_UNBOUND': '公式中的参数（窗口/平滑长度等）在论文中没有确定的数值，程序不会自行选择；请在请求中直接给出数值后重试。',
    'PARAMETER_VALUE_UNVERIFIED': '模型给出的参数数值在其引用的原文中找不到，不予采用；请在请求中给出数值，或指出论文中的出处。',
    'FORMULA_DEGENERATE_TERMS': '读出的公式含有恒为常数的项（同一项相减或相除），很可能是PDF公式文本层提取错误；需要人工核对原页。',
    'FIELD_NOT_AVAILABLE': '公式需要的输入不在已发布数据字段中（已发布：开高低收、成交量、成交额）。',
    'INSTRUMENT_NOT_AVAILABLE': '论文因子基于股票以外的金融工具（期权、期货、债券、外汇等），已发布数据只有A股股票行情，不能用股票价格替代。',
    'LOOKBACK_EXCEEDS_SAMPLE': '因子需要的历史长度超过已发布Train样本能支持的长度。',
    'WINDOW_UNIT_AMBIGUOUS': '修复后的窗口没有说明按交易日还是按论文周期计，无法确定实际回看长度。',
    'WINDOW_NOT_DERIVABLE': '论文窗口长度无法换算为整数个交易日。',
    'FUTURE_REFERENCE': '公式引用了未来数据。',
    'FACTOR_NOT_UNDERSTOOD': '没有在论文中找到所指的因子。',
    'NO_FACTOR_UNDERSTOOD': '没有从论文中识别出可研究的因子。',
    'LOOKBACK_READ_AS_LAG': '论文描述的是回看期累计收益，读出的公式却把它写成了滞后的单期收益；纠错重读后仍不一致，不执行错误定义。',
    'CUMULATIVE_READ_AS_SINGLE_PERIOD': '论文是多期累计收益，公式只用了当期单期收益。',
    'LAG_READ_AS_LOOKBACK': '论文是某一期的单期收益，定义却写成了累计收益。',
    'LOOKBACK_WINDOW_MISMATCH': '定义的回看长度与原文不一致。',
    'WINDOW_LENGTH_CONTRADICTS_PAPER': '公式窗口的期数与原文给出的期间长度不一致（例如原文“12个月”，公式取了13期）；纠错重读后仍不一致，不执行。',
    'LOG_RETURN_READ_AS_SIMPLE': '论文使用对数收益，定义按简单收益计算。',
    'EXPONENTIAL_READ_AS_MEAN': '论文是指数平滑（EMA），定义却是简单平均。',
    'EXPONENTIAL_SMOOTHING_MISSING': '论文定义使用指数平滑，公式中没有。',
    'SKIP_PERIOD_MISSING': '论文要求跳过最近的期，定义没有跳过期。',
    'CONSTANT_WITHOUT_SOURCE': '公式中的窗口、滞后或参数数值在原文中找不到出处。',
    'SYMBOL_NOT_IN_TABLE': '公式中的符号没有原文定义。',
    'SYMBOL_DEFINITION_UNVERIFIED': '符号的定义没有通过原文逐字核验。',
    'SYMBOL_UNDEFINED': '符号含义无法从原文确定，不能把它映射为任何行情字段。',
    'FIELD_MAPPING_UNSUPPORTED': '符号被映射到的行情字段在其原文定义中没有依据。',
    'FIELD_NOT_IN_PANEL': '符号是已发布行情以外的数据（换手率、市值、估值、分析师等）。',
    'DERIVATION_DIFFERS_FROM_DECLARATION': '执行公式与声明的定义在数值核对中不一致（程序自检失败）。',
    'RETURN_NOT_DERIVABLE': '收益的回看或跳过期无法换算为整数个论文周期。',
    'ALGORITHM_LOOKBACK_UNSTATED': '算法没有说明读取多少期历史，无法保证不使用未来数据。',
    'DERIVATION_UNPARSEABLE': '论文自定义量的定义式无法解析。',
    'ALGORITHM_STEP_AMBIGUOUS': '算法步骤含有不确定的表述（如“可选”“例如”“某种”），无法确定唯一的计算方法。',
    'MODEL_FORMULA_CONTRADICTS_PAPER': '模型读出的公式与程序从PDF版面重建的公式不一致，无法确定哪一个是论文定义。',
    'WINDOW_AGGREGATE_READ_AS_FIELD': '原文是窗口聚合量（如过去N期最高价），读出的定义却是单日字段。',
    'AGGREGATE_MISMATCH': '原文的窗口聚合方式（最大/最小/均值等）与读出的定义不一致。',
    'WINDOW_MISMATCH': '原文的窗口长度与读出的定义不一致。',
    'HISTORICAL_MAX_MAPPED_TO_INTRADAY_HIGH': '历史最高价被误读为当日最高价。',
    'ASSET_CLASS_NOT_AVAILABLE': '论文研究的资产不是A股个股，当前数据无法忠实研究。',
}


TOOL_FAILURE_TEXT = {
    'CANDIDATE_FAILED_STATIC_REVIEW': '模型编写的算法代码经有限次修订后仍未通过静态审核，没有运行任何代码。',
    'MODEL_PROVIDER_UNAVAILABLE': '模型服务（DeepSeek）没有响应或暂时不可用，这一步没有完成，也没有计算任何数据。这是服务商侧问题，不是论文或研究定义的问题；服务恢复后重试即可。',
    'PAPER_UNDERSTANDING_FAILED': '论文理解的模型调用在有限次重试后仍失败，没有计算任何数据；可以稍后重试。',
    'PARSE_FAILED': 'PDF 文件内部损坏或格式错误（解析器报告内容流/压缩流错误），无法读取正文；请重新导出或换一个版本后上传。',
    'NO_TEXT_LAYER': 'PDF 没有可提取的文字层（例如扫描件）；当前不做OCR，无法读取正文。',
    'ENCRYPTED': 'PDF 已加密，无法读取。',
    'FILE_TOO_LARGE': 'PDF 超出大小限制。',
    'PDF_UNREADABLE': 'PDF 无法打开或解析。',
    'SPEC_PROVENANCE_INVALID': '论文抽取结果的出处校验失败（引文不在所标位置），不使用这份抽取结果。',
    'IMPLEMENTATION_MISMATCH': '实现与独立参考结果不一致，计算已中止，没有交付结果。',
    'TRUSTED_IR_SELF_CHECK_FAILED': '可信执行器与参考求值器的逐格核对不一致，计算已中止，没有交付结果。',
    'PAPER_TASK_MISSING': '论文研究任务文件缺失，请重新发起这篇论文的研究。',
}


PROVIDER_FAILURES = {'TIMEOUT', 'NETWORK_ERROR', 'TRANSPORT_ERROR', 'SERVER_ERROR', 'RATE_LIMIT', 'INCOMPLETE_STREAM',
                     'PROVIDER_RESOURCE_ERROR', 'INVALID_PROVIDER_STREAM'}


def understanding_failure(exc):
    """A model-provider outage is not a paper-reading failure: it is reported and counted separately (2026-10-15)."""
    detail = str(getattr(exc, 'detail', '') or '')
    if getattr(exc, 'code', '') == 'MODEL_ERROR' and detail in PROVIDER_FAILURES:
        return 'MODEL_PROVIDER_UNAVAILABLE: ' + detail
    return 'PAPER_UNDERSTANDING_FAILED: ' + str(getattr(exc, 'code', 'MODEL_ERROR'))


def user_parameters(text):
    """Parameter values typed by the user, e.g. “研究RSI，X=14” or “N_fast=12, τ=21” -> {'X': 14}. At most 6, 1..5000."""
    out = {}
    for name, value in re.findall(r'(?<![A-Za-z0-9_\\])(\\?[A-Za-z][A-Za-z0-9_{}]{0,15}|[α-ωΑ-Ω])\s*[=＝]\s*(\d{1,4})(?![\d.])', text or ''):
        if 1 <= int(value) <= 5000 and len(out) < 6:
            if not _evaluation_name(name, text):
                out[name] = int(value)
    return out


def _evaluation_name(name, text):
    key=name.lower()
    if key in ('horizon','n_groups','label_lag'):
        return key
    if key=='lag' and re.search(r'(?:预测|收益|评估|评价|回测|horizon|forward|label).{0,100}\blag\s*[=＝]',text or '',re.I):
        return 'label_lag'
    return None


def user_evaluation_parameters(text):
    out={}
    for name,value in re.findall(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*[=＝]\s*(\d+)(?![\d.])',text or ''):
        key=_evaluation_name(name,text)
        if key:
            out[key]=int(value)
    return out


def apply_evaluation_parameters(plan, values):
    if not values:
        return plan
    import copy
    from paper_agent.ledger import sha256_obj
    plan=copy.deepcopy(plan)
    if values.get('label_lag',1)!=1 or values.get('horizon',1)<1 or values.get('n_groups',5)<2:
        plan['status']='BLOCKED'
        plan['hard_stops']=list(plan.get('hard_stops') or [])+[dict(code='EVALUATION_PARAMETERS_INVALID',
            detail='评价参数单独校验：当前标签从下一观测日开盘起算（label_lag=1），horizon必须为正整数，n_groups至少为2。该错误不是论文因子算子缺失。')]
        return plan
    choices=plan.get('choices') or {}
    plan['choices']=choices
    if 'horizon' in values:choices['horizon']=dict(n=values['horizon'],unit='trading_day')
    if 'n_groups' in values:choices['n_groups']=values['n_groups']
    choices['label_lag']=1
    plan['definition_sha256']=sha256_obj(dict(original=plan['definition_sha256'],evaluation=values))
    plan.setdefault('notes',[]).append('用户指定评价参数：'+', '.join(f'{k}={v}' for k,v in sorted(values.items())))
    return plan


def user_rereads(text):
    """The user's own words ask for a fresh reading of the paper (“重新阅读/重新解读这篇论文”, “re-read”)."""
    return bool(re.search(r'重新(?:阅读|解读|理解|读取|读一遍|读)|重读|re-?read', text or '', re.I))


def named_factor(names, description):
    """The one factor whose short name ("MACD" of "MACD (Moving Average ...)") the user's description names as a whole
    word; '' when none or several do ("MACD那篇" -> MACD, never "VPVMA modified MACD")."""
    def forms(n):
        # the name before the parenthesis, and an acronym inside it ("Generalized momentum indicator (GMI)" -> GMI)
        out = [re.split(r'\s*[\(（]', n)[0].strip()]
        out += [a for a in re.findall(r'[\(（]\s*([A-Za-z][A-Za-z0-9#]{1,9})\s*[\)）]', n)]
        return [s for s in out if len(s) >= 2]
    said = [n for n in names if any(re.search(r'(?<![A-Za-z0-9])' + re.escape(s) + r'(?![A-Za-z0-9])', description or '', re.I)
                                    for s in forms(n))]
    return said[0] if len(said) == 1 else ''


def tool_failure_text(code, detail=''):
    """The user-facing reason of a failed paper tool call: what failed, what did NOT happen, the program's own detail."""
    base = TOOL_FAILURE_TEXT.get(code) or ('研究工具执行失败（' + str(code) + '），没有交付结果。')
    extra = str(detail or '')
    extra = extra.split(':', 1)[1].strip() if ':' in extra else ''
    return base + (('\n程序明细：' + extra[:240]) if extra else '') + '\n可以继续提问或重试；完整诊断见 /tasks。'


def blocked_text(paper):
    """Program-written reason for a blocked paper study (the model summary does not see the hard stops)."""
    lines = []
    for h in (paper.get('hard_stops') or [])[:6]:
        code = str(h.get('code', ''))
        reason = BLOCK_REASONS.get(code) or ('数据准入检查未通过。' if code.startswith('ADMISSION_') else '程序检查未通过。')
        what = ('（' + str(h['symbol']) + '）') if h.get('symbol') else ''
        detail = str(h.get('detail') or '')[:300]
        source = f"〔问题来源：{h['source_cn']}〕" if h.get('source_cn') else ''
        lines.append(f'· {code}{what}{source}：{reason}' + (f' 明细：{detail}' if detail else ''))
    # what each kind of blocking source means for the user and what they can do, once per kind (C6R4)
    from paper_agent.reconcile import SOURCE_CN, SOURCE_HINT
    kinds = [k for k in dict.fromkeys(h.get('source') for h in (paper.get('hard_stops') or [])[:6]) if k in SOURCE_HINT]
    hints = ''.join(f'\n说明（{SOURCE_CN[k].split("（")[0]}）：{SOURCE_HINT[k]}' for k in kinds)
    others = [f for f in (paper.get('factors') or []) if f != paper.get('factor')]
    head = ''
    if paper.get('asset_blocked') and paper.get('research_object'):
        # the research object comes first: with options/futures/... data absent, fixing a formula would not make it researchable
        head = ('· 研究资产不匹配：论文研究对象为' + str(paper['research_object']) + '，已发布数据只有A股个股日频行情，'
                '不能忠实研究这篇论文（即使公式可以解析）。\n')
    text = '程序阻断原因（论文《' + str(paper.get('name', '')) + '》，因子“' + str(paper.get('factor', '')) + '”）：\n' + head + '\n'.join(lines) + hints
    if paper.get('research_object') and not head:
        text += '\n论文研究对象（程序从全文识别）：' + str(paper['research_object'])
    if others:
        text += '\n论文中还识别到：' + '、'.join(others[:4]) + '（可以点名让我研究其中之一；若同样受限，会给出原因）。'
    return text + '\n没有执行任何计算，也没有改用替代定义。'


def _bundle_candidate(bundle, source_sha256):
    """Candidate record rebuilt from its bundle for a review request; never executes it. Static review runs again."""
    from paper_agent.ledger import sha256_text
    from paper_research.candidate import analyze_source
    source = (bundle / 'candidate.py.txt').read_text(encoding='utf-8')
    if sha256_text(source) != source_sha256:
        raise ContractError('CANDIDATE_BUNDLE_CHANGED')
    contract = json.loads((bundle / 'contract.json').read_text(encoding='utf-8'))
    analysis = analyze_source(source, contract)
    tests = json.loads((bundle / 'tests.json').read_text(encoding='utf-8'))
    if tests.get('mode') == 'pair':
        # compute() + reference(): the security/time review applies to the whole file (loops are expected in reference())
        from paper_agent.algorithm import SECURITY_CODES
        bad = [i['code'] for i in analysis['issues'] if i['code'] in SECURITY_CODES]
        if bad:
            raise ContractError('CANDIDATE_FAILED_STATIC_REVIEW: ' + ','.join(bad)[:200])
        return dict(status='READY_FOR_REVIEW', files={'candidate.py': source}, contract=contract, tests=tests,
                    analysis=dict(passed=True, issues=analysis['issues']),
                    manifest=dict(candidate_id='pair_' + source_sha256[:16], origin='pair (rebuilt from its bundle)'))
    if not analysis['passed']:
        raise ContractError('CANDIDATE_FAILED_STATIC_REVIEW: ' + ','.join(i['code'] for i in analysis['issues'])[:200])
    return dict(status='READY_FOR_REVIEW', files={'candidate.py': source}, contract=contract, analysis=analysis,
                tests=json.loads((bundle / 'tests.json').read_text(encoding='utf-8')),
                manifest=json.loads((bundle / 'manifest.json').read_text(encoding='utf-8')))


def candidates_text(status, papers):
    """Program-written list of the papers the user can choose from (the model summary does not see them)."""
    head = {'AMBIGUOUS': '有多篇论文都符合你的描述，请说出其中一篇的名称或标题中的关键词：',
            'NOT_FOUND': '没有找到符合描述的论文。目前已上传的论文有：',
            'NO_PAPERS': '还没有上传任何论文，请先用 quant-paper upload 上传 PDF。'}.get(status, '')
    rows = [f"· {p.get('name', '')}" + (f"（{str(p['title'])[:60]}）" if p.get('title') else '') for p in (papers or [])[:8]]
    return head + ('\n' + '\n'.join(rows) if rows else '')


PAGE_IMAGE_BOUNDARY = ('DeepSeek 是纯文本模型，不能查看页面图像。被调查的页面由程序另行提取 PDF 原始文本层（含未解析公式区域内的文字）'
                       '交给模型对照；页面截图只保存供人工复核。')


def reconciliation_record(understanding, u_factor, factor_name, executed=None):
    """AI reading x program analysis for one factor: the AI's first reading, the program's parse, every conflict with its
    source, the reader's investigation (requests, pages, claims and whether the program accepted them), the final
    definition, what remains uncertain, and the parameter values the user supplied."""
    reading = understanding.get('reading') or {}
    initial = next((x for x in reading.get('initial') or [] if x.get('name') == factor_name), None)
    formula = u_factor.get('formula') or {}
    status = ('PARSED' if formula.get('ir_rendered') else 'ALGORITHM' if u_factor.get('algorithm')
              else 'PARAMETER_UNBOUND' if any(c['code'] == 'FREE_PARAMETER_UNBOUND' for c in u_factor.get('conflicts') or [])
              else 'PROGRAM_PARSE_INCOMPLETE' if formula.get('latex') else 'NO_FORMULA')
    inv = [r for r in understanding.get('investigations') or [] if r.get('factor') == factor_name]
    rec = dict(
        version='reconciliation/1',
        ai_initial=dict(formula=(initial or {}).get('formula_latex'), status=(initial or {}).get('formula_status'),
                        parameters=(initial or {}).get('parameters'), algorithm=(initial or {}).get('algorithm')),
        program_parse=dict(status=status, written=formula.get('latex_as_written') or formula.get('latex'), bound=formula.get('latex'),
                           layout_formula=formula.get('v03_formula')),
        parameters=[dict(symbol=p['symbol'], value=p.get('value'), status=p['status'], paper_values=p.get('paper_values'),
                         meaning=p.get('meaning'), citations=[dict(page=c.get('page'), passage=c.get('passage'), quote=c.get('quote', '')[:200])
                                                              for c in p.get('citations') or []][:2])
                    for p in u_factor.get('parameters') or []],
        conflicts=[dict(code=c['code'], symbol=c.get('symbol'), blocking=bool(c.get('blocking')), source=c.get('source'),
                        source_cn=c.get('source_cn'), source_basis=c.get('source_basis'), detail=str(c.get('detail', ''))[:300])
                   for c in u_factor.get('conflicts') or []],
        investigations=[dict(attempt=r.get('attempt'), rounds=r.get('rounds'), changed=r.get('changed'),
                             conflicts_before=r.get('conflicts_before'), conflicts_after=r.get('conflicts_after'),
                             formula_before=r.get('formula_before'), formula_after=r.get('formula_after'),
                             requests=[dict({k: q.get(k) for k in ('tool', 'query', 'pages', 'raw_text_layer')}, passages=(q.get('passages') or [])[:8])
                                       for q in r.get('requests') or []][:12],
                             pages_consulted=r.get('pages_consulted'), page_images=r.get('page_images'),
                             findings=[{k: f.get(k) for k in ('issue', 'symbol', 'source', 'accepted', 'why', 'explanation')}
                                       for f in r.get('findings') or []][:8], records=r.get('records'))
                        for r in inv],
        final=dict(formula=executed or formula.get('latex'), status=u_factor.get('status')),
        uncertainties=[str(c.get('detail', ''))[:300] for c in u_factor.get('conflicts') or [] if not c.get('blocking')][:8],
        user_parameters={p['symbol']: p['value'] for p in u_factor.get('parameters') or [] if p['status'] == 'USER'},
        boundary=PAGE_IMAGE_BOUNDARY)
    if len(json.dumps(rec, ensure_ascii=False, default=str)) > 16000:      # the study result is capped at 64 KB as a whole
        for r in rec['investigations']:
            for q in r['requests']:
                q.pop('passages', None)
        rec['conflicts'] = rec['conflicts'][:10]
        rec['ai_initial'].pop('algorithm', None)
        rec['truncated'] = True
    return rec


def paper_definition_record(entry, evidence, understanding, u_factor, plan):
    """What the report shows about paper -> structured definition -> executed formula (all program-checked facts)."""
    def cites(items):
        return [dict(page=c.get('page'), passage=c.get('passage'), quote=c.get('quote', '')[:300]) for c in items or []][:4]
    conflicts = u_factor.get('conflicts') or []
    examples = plan.get('worked_examples') or []
    nonblocking = [dict(code=c['code'], detail=str(c.get('detail', ''))[:300]) for c in conflicts if not c.get('blocking')]
    checks = [
        dict(name='原文引文逐字核验', status='PASSED' if u_factor['verbal_definition']['status'] == 'PAPER' else 'NOT_VERIFIED',
             detail=f"定义引文 {len(u_factor['verbal_definition']['citations'])} 条、公式引文 {len(u_factor['formula']['citations'])} 条在原文中逐字定位"),
        dict(name='时间语义与常数出处（确定性规则）', status='PASSED' if not any(c.get('blocking') for c in conflicts) else 'FAILED',
             detail='回看/滞后、累计/单期、跳过期、对数/简单、指数平滑、窗口与参数数值的原文出处'
                    + (f"；需用户确认的解释/参数选择 {len(nonblocking)} 项" if nonblocking else '')),
        dict(name='符号表与字段映射', status='PASSED', detail='每个公式符号均有核验通过的原文定义，映射到行情字段有对应词语'),
        dict(name='研究资产识别', status='PASSED' if (plan.get('assets') or {}).get('decision') == 'EQUITY_STOCK_COMPATIBLE' else 'SUBSTITUTED',
             detail=((plan.get('assets') or {}).get('summary_cn') or 'A股个股') + '（全文、因子页面与符号引文三层判定）'),
        dict(name='定义→执行数值核对', status=('PASSED' if all(e['match'] for e in examples) else 'FAILED') if examples else 'NOT_APPLICABLE',
             detail=f"{len(examples)} 个收益类符号按声明手算与执行公式一致" if examples else '公式中没有需要派生的收益类符号'),
    ]
    assets = plan.get('assets') or {}
    return dict(version='paper_definition/1', paper=dict(name=entry['name'], title=entry.get('title', ''), sha256=entry['sha256'],
                                                          version=entry.get('version')),
                factor=plan['factor'], mode=plan['mode'], route=plan['route'], definition_sha256=plan['definition_sha256'],
                canonical_definition_sha256=plan.get('canonical_definition_sha256'),
                faithful=plan['mode'] == 'PAPER_ORIGINAL',
                asset=dict(decision=assets.get('decision'), summary_cn=assets.get('summary_cn'),
                           substituted=bool(plan.get('asset_consent_required')),
                           evidence=[dict(page=e.get('page'), quote=(e.get('quote') or '')[:200]) for k in (assets.get('blocking_classes') or [])
                                     for e in ((assets.get('factor_inputs') or {}).get(k) or (assets.get('evidence') or {}).get(k) or [])][:3]),
                paper_text=dict(verbal=u_factor['verbal_definition'].get('value'), verbal_citations=cites(u_factor['verbal_definition']['citations']),
                                formula_latex=u_factor['formula']['latex'], formula_status=u_factor['formula']['status'],
                                formula_citations=cites(u_factor['formula']['citations'])),
                symbols=[dict(symbol=s['symbol'], meaning=(s.get('meaning') or '')[:200], kind=s.get('kind'), field=s.get('data_field'),
                              window=s.get('window'), skip=s.get('skip'), compounding=s.get('compounding'), status=s.get('status'),
                              citations=cites(s.get('citations'))) for s in u_factor['symbols']][:12],
                executed=dict(formula=plan['ir_execution'], warmup_rows=plan['warmup_rows'], timeline=plan.get('timeline') or [],
                              worked_examples=examples),
                substitutions=[dict(kind=s['kind'], item=s['item'], paper=str(s['paper'])[:300], ours=str(s['ours'])[:300])
                               for s in plan['substitutions']][:16],
                checks=checks, nonblocking_findings=nonblocking,
                reconciliation=reconciliation_record(understanding, u_factor, plan['factor'], plan['ir_execution']),
                semantic_repairs=[{k: r.get(k) for k in ('attempt', 'conflicts_before', 'conflicts_after')}
                                  for r in understanding.get('semantic_repairs') or [] if r.get('factor') == plan['factor']])


def _slug(text):
    s = re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')
    s = s if re.match(r'[a-z]', s or '') else 'f_' + s
    return (s or 'paper_factor')[:40].rstrip('_')


class PaperPipeline:
    def __init__(self, backend):
        self.backend = backend
        self.library = backend.papers
        self.registry = backend.approved_registry

    # ------------------------------------------------------------------ Tools
    def list_papers(self, _task_context):
        rows = sorted(self.library.entries(), key=lambda r: r['uploaded_at'])
        return {'mode': 'catalog', 'implementation_version': '0.4.0', 'analysis_scope': 'paper_library',
                'papers': [self.library.public(r) for r in rows[-30:]], 'paper_count': len(rows)}

    def research(self, paper, factor, _task_context, plan_sha256=''):
        found = self.library.resolve(paper)
        if _task_context.get('validate_only'):
            # Proposal mode: argument, policy and library checks passed; no model call, nothing computed.
            from .definition_gate import ValidationPassed
            if found['status'] != 'FOUND':
                raise Denied('PAPER_' + found['status'])
            raise ValidationPassed()
        if found['status'] != 'FOUND':
            return {'mode': 'catalog', 'implementation_version': '0.4.0', 'analysis_scope': 'paper_resolution',
                    'paper_status': found['status'], 'papers': found.get('candidates', [])}
        entry = found['paper']
        self.library.touch(entry['sha256'])
        from paper_agent.ledger import TaskLedger
        # One paper task per paper content: understanding, plans, candidates and rationale are reused across turns.
        key = hashlib.sha256((entry['sha256'] + '|' + PIPELINE).encode()).hexdigest()[:32]
        ledger = TaskLedger(self.library.root, key, goal=f"{entry['name']}",
                            budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7, design_revisions=2,
                                        orchestration_turns=0))
        # The paper ledger lives across sessions: its model-call allowance applies to each request, not to the paper for ever
        # (a paper re-read after a reader upgrade would otherwise run out). Every window is recorded.
        used = ledger.state['usage']
        ledger.state['budget'].update(model_calls=used['model_calls'] + 40, total_tokens=used['total_tokens'] + 2_000_000)
        ledger.event('BUDGET_WINDOW', {'model_calls_used_before': used['model_calls'], 'allowance_model_calls': 40})
        client = RuntimeClient(_task_context['model']) if _task_context.get('model') else None
        self._live = bool(_task_context.get('model_live'))
        emit = _task_context['emit']
        started = time.monotonic()

        def stage(name, status='RUNNING', **extra):
            emit('RESEARCH_STAGE', dict(stage=name, status=status, elapsed_seconds=0 if status == 'RUNNING' else round(time.monotonic() - started, 3), **extra))
        from paper_agent.evidence import PaperEvidence
        stage('paper_reading')
        evidence = PaperEvidence.build(self.library.path(entry), cache_dir=self.library.root / 'cache',
                                       allowed_roots=[self.library.root / 'files'])
        stage('paper_reading', 'COMPLETED')
        understanding = ledger.read_artifact('understanding.json')
        from paper_agent.understanding import VERSION as UNDERSTANDING_VERSION
        if understanding and (_unit_unstated(understanding) or understanding.get('version') != UNDERSTANDING_VERSION):
            understanding = None                 # read by an older reader (no time-index semantics / research object): re-read
        # values the USER typed belong to the session that typed them (live J1 23:25: an earlier session's X=14 was reused)
        by_session = ledger.state.setdefault('user_parameters_by_session', {})
        session_params = dict(by_session.get(str(_task_context.get('session_id') or '')) or {})
        # parameter values the USER typed in THIS session (never the model's tool arguments), shown as user choices
        evaluation = ledger.state.setdefault('evaluation_parameters_by_session', {}).setdefault(_task_context.get('session_id'), {})
        evaluation.update(user_evaluation_parameters(_task_context.get('user_text') or ''))
        typed = user_parameters(_task_context.get('user_text') or '')
        if typed:
            session_params.update(typed)
            by_session[str(_task_context.get('session_id') or '')] = session_params
            ledger.save()
            ledger.event('USER_PARAMETERS', {'values': typed, 'session_id': _task_context.get('session_id')})
        from paper_agent.definitions import DefinitionRegistry
        registry = DefinitionRegistry(ledger.dir)
        # mode 3 of 3 (first reading / frozen reuse / re-read on the user's request): only the user's own words select it
        reread = user_rereads(_task_context.get('user_text') or '')
        if reread:
            understanding = None
            ledger.event('USER_REREAD_REQUESTED', {'session_id': _task_context.get('session_id')})
        sid = str(_task_context.get('session_id') or '')
        # frozen reuse serves a session's first request about this paper; later turns may edit what was shown
        edited = any(ledger.state.get('user_versions_by_session', {}).get(sid, {}).values()) \
            or bool(ledger.state.get('plans_shown_by_session', {}).get(sid))
        frozen = None if reread or edited else registry.reusable(paper_sha256=entry['sha256'], requested_factor=factor or '',
                                                                  user_params=session_params)
        if frozen and plan_sha256 and frozen.get('plan_sha256') != plan_sha256:
            frozen = None       # the user is confirming another plan (e.g. one from a re-read): never swap in the frozen one
        reused = self._reuse(registry, frozen, ledger, evidence, entry, factor, session_params, _task_context) if frozen else None
        if reused:
            understanding = reused[0]            # the frozen definition's own verified reading: no model call
        if understanding and understanding.get('program_sha256') != program_sha256() and understanding.get('reading'):
            # the same model reading, checked again by the CURRENT program (no model call; this session's typed values)
            from paper_agent.understanding import reverify
            understanding = reverify(understanding, evidence, session_params)
            understanding['program_sha256'] = program_sha256()
            ledger.write_artifact('understanding.json', understanding)
            ledger.event('READING_REVERIFIED', {'program_sha256': program_sha256()})
        if not understanding:
            if client is None:
                raise Denied('MODEL_UNAVAILABLE_FOR_PAPER_UNDERSTANDING')
            from paper_agent.understanding import understand
            from paper_agent.ledger import BudgetExceeded
            from paper_agent.model import ModelFailure
            stage('paper_understanding')
            try:
                understanding = understand(evidence, client, ledger, focus=factor or '')
            except BudgetExceeded:
                raise BudgetExhausted('paper_model_calls') from None
            except ModelFailure as exc:
                raise ContractError(understanding_failure(exc)) from None
            understanding['program_sha256'] = program_sha256()
            ledger.write_artifact('understanding.json', understanding)
            stage('paper_understanding', 'COMPLETED')
        if not reused and understanding.get('reading') and (understanding.get('user_parameters') or {}) != session_params:
            # the stored reading carries another session's values (or none): verify it again with exactly this session's
            from paper_agent.understanding import reverify
            understanding = reverify(understanding, evidence, session_params)
        names = [f['name'] for f in understanding['factors']]
        if not factor and len(names) > 1:
            factor = named_factor(names, paper) or factor
        from paper_agent.planner import PlanError
        try:
            try:
                plan = reused[1] if reused else self._plan(ledger, evidence, understanding, factor)
            except PlanError as exc:
                # the cached reading focused on another factor of this paper (Alpha#1 read, Alpha#12 asked): read once more,
                # this time for the factor the user named; a factor still not found is reported, never substituted
                if exc.code != 'FACTOR_NOT_UNDERSTOOD' or client is None or understanding.get('focus') == factor:
                    raise
                from paper_agent.understanding import understand
                from paper_agent.ledger import BudgetExceeded
                from paper_agent.model import ModelFailure
                stage('paper_understanding')
                try:
                    understanding = understand(evidence, client, ledger, focus=factor,
                                               user_params=session_params or None)
                except BudgetExceeded:
                    raise BudgetExhausted('paper_model_calls') from None
                except ModelFailure as exc2:
                    raise ContractError(understanding_failure(exc2)) from None
                understanding['program_sha256'] = program_sha256()
                ledger.write_artifact('understanding.json', understanding)
                stage('paper_understanding', 'COMPLETED')
                names = [f['name'] for f in understanding['factors']]
                plan = self._plan(ledger, evidence, understanding, factor)
        except PlanError as exc:                 # unknown factor name: show what the paper defines so the user can choose
            return {'mode': 'catalog', 'implementation_version': '0.4.0', 'analysis_scope': 'paper_factor_choice',
                    'paper_status': exc.code, 'paper': dict(name=entry['name'], title=entry.get('title', ''), requested_factor=factor,
                                                            factors=names, usage=ledger.state['usage'])}
        plan, understanding, edited_now = self._user_version(ledger, evidence, understanding, plan, factor, client, _task_context, sid)
        from paper_agent.autonomous_route import propose as propose_algorithm, eligible as algorithm_eligible
        if client is not None and algorithm_eligible(plan):
            from paper_agent.canonical import factor_key
            from .definition_gate import user_consent
            requests = ledger.state.setdefault('autonomous_requests_by_session', {}).setdefault(sid, {})
            request_key = factor_key(plan['factor'], '')
            user_text = (_task_context.get('user_text') or '').strip()
            if user_text and not _task_context.get('definition_confirmed') and user_consent(user_text) not in ('accept', 'reject'):
                requests[request_key] = user_text[:2000]
                ledger.save()
            plan = propose_algorithm(plan, understanding, evidence, self.backend.paper_data_profile(), client, ledger,
                                     user_request=requests.get(request_key, ''))
        plan = apply_evaluation_parameters(plan, evaluation)
        canon, canon_sha = self._canonical(ledger, plan, understanding, entry, factor)
        uv = next((f.get('user_version') for f in understanding['factors'] if f['name'] == plan['factor']), None)
        if uv:
            canon['user_version'] = uv          # a user's version: shown as such, never reused by another session
            canon['display']['user_version'] = uv
        registry.propose(canon, plan_status=plan['status'], user_params=session_params,
                         session_id=_task_context.get('session_id'),
                         sources={'understanding': understanding, 'plan': plan, 'task': ledger.read_artifact('research_task.json')})
        plan['canonical_definition_sha256'] = canon_sha
        if plan['status'] == 'BLOCKED':
            return self._blocked(entry, plan, names, ledger, understanding)
        if plan_sha256 and plan_sha256 != plan['definition_sha256']:
            raise Denied('PAPER_PLAN_CHANGED_SINCE_CONFIRMATION')
        # an approval belongs to exactly this canonical definition and covers the asset phrase when one is required;
        # approvals recorded by an older program (ledger 'accepted_plan_sha256') are not carried over
        if _task_context.get('definition_confirmed') and not plan_sha256:
            # a confirmation of words only (no plan SHA) never runs anything (K3: it re-ran the frozen definition)
            raise Denied('PAPER_CONFIRMATION_WITHOUT_DEFINITION')
        approval = registry.approved(canon_sha, asset_consent_required=bool(plan.get('asset_consent_required')))
        fresh = bool(_task_context.get('definition_confirmed')) and plan_sha256 == plan['definition_sha256']
        # a non-IR algorithm is model prose: it runs only on a confirmation given in THIS conversation for exactly the shown
        # plan; an approval recorded earlier (another session, an older registry) never stands in for it (C7 audit F03)
        algorithm = plan.get('route') in ('algorithm','autonomous_python') or 'algorithm' in (canon.get('math') or {})
        if (edited_now or algorithm) and not fresh:
            approval = None                      # after an edit / undo / restore, or for an algorithm: shown before it runs
        if (plan['status'] == 'AWAITING_USER_DECISION' or edited_now or algorithm) and not approval:
            if _task_context.get('definition_confirmed') and plan_sha256 == plan['definition_sha256']:
                registry.approve(canon_sha, session_id=_task_context.get('session_id'), task_id=_task_context['task_id'],
                                 substitutions=plan['substitutions'], asset_phrase=bool(plan.get('asset_consent_required')))
                ledger.state.setdefault('decisions', []).append(dict(decision='accepted', plan=plan['definition_sha256'],
                                                                     definition=canon_sha, task_id=_task_context['task_id'],
                                                                     time=time.time()))
                ledger.save()
            else:
                raise DefinitionDecisionRequired(self._decision(entry, plan, names, _task_context))
        registry.freeze(canon_sha, needs_approval=plan['status'] == 'AWAITING_USER_DECISION')
        args = dict(paper=entry['sha256'], factor=plan['factor'], plan_sha256=plan['definition_sha256'])
        name = _slug(plan['factor'])
        u_factor = next(f for f in understanding['factors'] if f['name'] == plan['factor'])
        hypothesis = ((u_factor.get('verbal_definition') or {}).get('value') or plan['factor'])[:550]
        reason = f"paper {entry['name']!r} ({entry['sha256'][:12]}); {plan['mode']}; definition {plan['definition_sha256'][:12]}"[:590]
        horizon = int(plan['choices']['horizon']['n'])
        n_groups = int(plan['choices'].get('n_groups',5))
        train = next(iter(self.backend.validation_pairs))
        provenance = {'paper_agent_plan.json': json.dumps(plan, ensure_ascii=False, indent=1, default=str),
                      'paper_agent_understanding.json': json.dumps(understanding, ensure_ascii=False, indent=1, default=str)}
        context = dict(_task_context, extra_code_files=provenance, hypothesis=hypothesis, change_reason=reason,
                       economic_rationale=self._rationale(ledger, evidence, plan, u_factor, entry, client, horizon),
                       paper_definition=paper_definition_record(entry, evidence, understanding, u_factor, plan))
        if plan['route'] == 'dsl':
            from .factor_expression import inspect
            definition = inspect(plan['dsl']['expression']) | {'hypothesis': hypothesis, 'generation_reason': reason, 'name': name}
            stage('paper_dsl_study')
            result = self.backend._study(train, 'expression', max(2, definition['warmup_observations']), horizon, n_groups, 'raw',
                                         context, definition)
        elif plan['route'] == 'trusted_ir':
            # The reviewed IR executor computes the frozen definition; no model-written code exists or runs.
            from paper_research.candidate import contract_from_task
            from paper_agent.study_bridge import ir_latex
            contract = contract_from_task(ledger.read_artifact('research_task.json'), trusted_ir=True)
            stage('paper_trusted_ir_study')
            result = self.backend.trusted_ir_study(train, contract['ir'], {i['symbol']: i['field'] for i in contract['inputs']},
                                                   hypothesis, reason, horizon, n_groups, 'raw', context, factor_name=name,
                                                   latex=ir_latex(contract['ir']))
        elif plan['route'] == 'autonomous_python':
            from paper_agent.autonomous_route import build as build_algorithm
            stage('autonomous_algorithm_design_and_test')
            bundle = build_algorithm(plan, client, ledger)
            result = self.backend.autonomous_study(train,bundle,hypothesis,reason,horizon,n_groups,'raw',context,factor_name=name)
        else:
            impl = self._implementation(ledger, plan, client, args, entry, _task_context)
            from paper_agent.study_bridge import ir_latex
            ir = impl['contract'].get('ir')
            result = self.backend.approved_study(train, impl['implementation_id'], hypothesis, reason, horizon, n_groups, 'raw', context,
                                                 factor_name=name, latex=ir_latex(ir) if ir else r'f_{t,i}=\mathrm{Algorithm}')
        execution = {'study_id': result.get('study_id'), 'artifact_path': result.get('artifact_path'),
                     'data_sha256': result.get('data_sha256'), 'horizon': horizon, 'label_lag': (plan.get('choices') or {}).get('label_lag', 1),
                     'evaluation_version': (((result.get('metrics') or {}).get('professional') or {}).get('evaluation_version'))}
        execution['execution_sha256'] = hashlib.sha256(json.dumps(dict(execution, definition=canon_sha), sort_keys=True,
                                                                  default=str).encode()).hexdigest()
        stored = registry.executed(canon_sha, execution)
        result['paper'] = dict(name=entry['name'], version=entry['version'], sha256=entry['sha256'], title=entry.get('title', ''),
                               definition=dict(sha256=canon_sha, status=stored['status'], reused=bool(reused), reread=reread,
                                               reread_matches_earlier=reread and len(stored.get('executions') or []) > 1,
                                               approved_at=(stored.get('approvals') or [{}])[0].get('time'),
                                               executions=len(stored.get('executions') or [])),
                               factor=plan['factor'], other_factors=[n for n in names if n != plan['factor']],
                               mode=plan['mode'], route=plan['route'], substitutions=plan['substitutions'],
                               plan_sha256=plan['definition_sha256'], usage=ledger.state['usage'])
        ledger.state['study'] = {k: result.get(k) for k in ('study_id', 'artifact_path', 'html_path', 'report_revision')}
        ledger.save()
        return result

    # ------------------------------------------------------------------ helpers
    def _user_version(self, ledger, evidence, understanding, plan, factor, client, ctx, sid):
        """(plan, understanding) of this session's current version of the factor: the paper's (v1) or the user's latest
        edit. A message after a plan was shown is read for an edit / undo / restore (one small model call); consent,
        a confirmed run and a re-read are never read as edits."""
        from paper_agent import user_edit
        from paper_agent.canonical import factor_key
        from .definition_gate import user_consent
        # the paper's own factor name, never the model's tool argument (K3 rerun: "MACD 8/17 horizon 5", "MACD(12,26,9,1)"
        # gave five keys, every edit looked like a first request and the approved paper definition ran again)
        key = factor_key(plan['factor'], '')
        versions = ledger.state.setdefault('user_versions_by_session', {}).setdefault(sid, {}).setdefault(key, [])
        seen = ledger.state.setdefault('plans_shown_by_session', {}).setdefault(sid, [])
        text = ctx.get('user_text') or ''
        if key in seen and client is not None and text.strip() and not ctx.get('definition_confirmed') \
                and user_consent(text) != 'accept' and not user_rereads(text):
            fac = next(f for f in understanding['factors'] if f['name'] == plan['factor'])
            current = versions[-1] if versions else {}
            obj = user_edit.interpret(
                client, ledger, factor=plan['factor'], paper_formula=fac['formula'].get('latex'),
                paper_meanings=[f"{s['symbol']}: {s.get('meaning') or ''}"[:160] for s in fac.get('symbols') or []][:8],
                blockers=[str(h.get('detail') or h.get('code'))[:200] for h in plan.get('hard_stops') or []][:4],
                current_formula=current.get('formula_latex') or (plan.get('ir_execution') or fac['formula'].get('latex')),
                current_horizon=current.get('horizon_days') or ((plan.get('choices') or {}).get('horizon') or {}).get('n'), text=text)
            intent = obj.get('intent')
            h = obj.get('horizon_days') if type(obj.get('horizon_days')) is int and obj.get('horizon_days') >= 1 else None
            if intent == 'edit' and (obj.get('formula_latex') or h):
                versions.append({'formula_latex': obj.get('formula_latex') or current.get('formula_latex') or '',
                                 'horizon_days': h or current.get('horizon_days'),
                                 'changes_cn': (obj.get('changes_cn') or '')[:300], 'user_text': text[:300]})
            elif intent == 'undo' and versions:
                versions.pop()
            elif intent == 'restore':
                versions.clear()
            elif intent == 'unsupported':
                # said and blocked, never run in another form (e.g. "weekly" rewritten in daily rows)
                ledger.event('USER_EDIT', {'session_id': sid, 'factor': key, 'intent': intent, 'version': len(versions) + 1})
                ledger.save()
                return dict(plan, status='BLOCKED', hard_stops=list(plan.get('hard_stops') or []) + [
                    {'code': 'USER_EDIT_NOT_SUPPORTED', 'detail': '修改无法执行：' + (obj.get('changes_cn') or '')[:300]
                     + '（已发布数据为A股日频；当前方案未改变，可继续修改或撤销）'}]), understanding, True
            ledger.event('USER_EDIT', {'session_id': sid, 'factor': key, 'intent': intent, 'version': len(versions) + 1})
            changed = True       # a later message about this factor that is not a confirmation: show the version, never re-run it
        else:
            changed = False
        if key not in seen:
            seen.append(key)
        ledger.save()
        if not versions:
            return plan, understanding, changed
        u = user_edit.apply(understanding, plan['factor'], versions[-1], len(versions) + 1)
        return self._plan(ledger, evidence, u, plan['factor']), u, changed

    def _canonical(self, ledger, plan, understanding, entry, factor):
        from paper_agent.canonical import definition
        return definition(plan, ledger.read_artifact('research_task.json') if plan.get('task_id') else None, understanding,
                          paper=entry, requested_factor=factor or '', program=program_sha256())

    def _reuse(self, registry, rec, ledger, evidence, entry, factor, session_params, _task_context):
        """(understanding, plan) of a frozen definition, re-planned from its own stored reading by the CURRENT program
        (no model call). A different canonical SHA means the program now reads that definition differently: the old record
        is SUPERSEDED and the request goes through the normal reading and decision."""
        src = registry.sources(rec['definition_sha256'])
        if not src or not src.get('understanding'):
            return None
        understanding = src['understanding']
        if understanding.get('reading') and ((understanding.get('user_parameters') or {}) != session_params
                                             or understanding.get('program_sha256') != program_sha256()):
            from paper_agent.understanding import reverify
            understanding = reverify(understanding, evidence, session_params)
            understanding['program_sha256'] = program_sha256()
        from paper_agent.planner import PlanError
        try:
            plan = self._plan(ledger, evidence, understanding, (rec.get('display') or {}).get('factor') or factor)
        except PlanError:
            return None
        _, sha = self._canonical(ledger, plan, understanding, entry, factor)
        if sha != rec['definition_sha256']:
            registry.supersede(rec['definition_sha256'], sha, 'the current program reads the stored definition differently')
            return None
        ledger.event('DEFINITION_REUSED', {'definition_sha256': sha, 'session_id': _task_context.get('session_id')})
        return understanding, plan

    def _rationale(self, ledger, evidence, plan, u_factor, entry, client, horizon):
        """Ex-ante economic rationale from passages already parsed for this paper; cached per frozen plan."""
        from .economic_rationale import VERSION, generate, unavailable
        cached = ledger.read_artifact('economic_rationale.json')
        if cached and cached.get('plan_sha256') == plan['definition_sha256'] and cached['analysis'].get('version') == VERSION:
            return cached['analysis']
        if client is None or not self._live:
            return unavailable('OFFLINE_OR_NO_LIVE_MODEL', horizon)
        name = plan['factor']
        queries = [f'{name} explanation investors why returns', 'hypothesis behavioral anchoring underreaction overreaction',
                   'illiquidity premium compensation risk price impact', 'we argue that this suggests because investors']
        ctx = evidence.context(queries, budget_chars=6000, must=[])
        paper = dict(title=evidence.summary()['title'] or entry['name'],
                     verbal_definition=(u_factor.get('verbal_definition') or {}).get('value', ''),
                     substitutions=[s['item'] + '：论文=' + str(s['paper'])[:80] + '；本次=' + str(s['ours'])[:80] for s in plan['substitutions']],
                     passages=[dict(id=p['id'], page=p.get('page'), text=p['text'][:900]) for p in ctx],
                     verify_quote=evidence.verify_quote)
        analysis = generate(lambda request: client.model_call(request), factor_name=name, formula=plan['ir_execution'],
                            definition=f"{plan['mode']}；路线{plan['route']}；暖机{plan['warmup_rows']}行", horizon=horizon,
                            data_profile=self.backend.paper_data_profile(), paper=paper,
                            user_hypothesis=(u_factor.get('verbal_definition') or {}).get('value', ''))
        ledger.write_artifact('economic_rationale.json', dict(plan_sha256=plan['definition_sha256'], analysis=analysis))
        return analysis


    def _plan(self, ledger, evidence, understanding, factor):
        from paper_agent.ledger import sha256_obj
        basis = sha256_obj({'understanding': understanding, 'planner': PLANNER_REV, 'program': program_sha256()})
        cached = ledger.read_artifact('plan.json')
        same_number = set(re.findall(r'#\s*(\d+)', factor or '')) <= set(re.findall(r'#\s*(\d+)', (cached or {}).get('factor') or ''))
        if cached and cached.get('basis_sha256') == basis and same_number and (
                not factor or factor.lower() in cached['factor'].lower() or cached['factor'].lower() in factor.lower()):
            return cached
        from paper_agent.planner import plan as make_plan
        plan, task, spec_used = make_plan(evidence, understanding, self.backend.paper_data_profile(), factor=factor or None)
        plan['basis_sha256'] = basis
        if plan['route'] == 'dsl':
            from .factor_expression import inspect
            try:
                inspect(plan['dsl']['expression'])
                plan['dsl']['production_preflight'] = {'accepted': True}
            except Exception as exc:  # noqa: BLE001 - the executing Agent's validator is authoritative
                plan['dsl']['production_preflight'] = {'accepted': False, 'error': f'{type(exc).__name__}: {exc}'[:300]}
                plan['route'] = 'trusted_ir'
                plan['notes'].append('the production DSL validator rejects this expression (' + str(exc)[:120] +
                                     '); the formula is kept unchanged and computed by the reviewed Factor-IR executor')
                from paper_agent.ledger import sha256_obj
                plan['definition_sha256'] = sha256_obj({k: plan[k] for k in ('factor', 'mode', 'route', 'ir_execution', 'symbol_map', 'choices')})
        if task is not None:
            ledger.write_artifact('research_task.json', task)
        ledger.write_artifact('plan.json', plan)
        return plan

    def _blocked(self, entry, plan, names, ledger, understanding=None):
        ledger.state['blocked'] = True
        ledger.save()
        u_factor = next((f for f in (understanding or {}).get('factors') or [] if f['name'] == plan['factor']), None)
        if u_factor:                             # the audit of a blocked study: AI reading x program analysis, kept in the ledger
            ledger.write_artifact('reconciliation.json', dict(reconciliation_record(understanding, u_factor, plan['factor']),
                                                              hard_stops=plan['hard_stops'][:8]))
        return {'mode': 'catalog', 'implementation_version': '0.4.0', 'analysis_scope': 'paper_blocked',
                'paper_status': 'BLOCKED', 'paper': dict(name=entry['name'], factor=plan['factor'], factors=names,
                hard_stops=plan['hard_stops'][:8], substitutions=plan['substitutions'][:8], usage=ledger.state['usage'],
                research_object=(plan.get('assets') or {}).get('summary_cn'),
                asset_blocked=(plan.get('assets') or {}).get('decision') == 'ASSET_CLASS_NOT_AVAILABLE')}

    def _decision(self, entry, plan, names, ctx):
        from paper_agent.planner import decision_question, decision_text
        args = dict(paper=entry['sha256'], factor=plan['factor'], plan_sha256=plan['definition_sha256'])
        return dict(id=hashlib.sha256((ctx['task_id'] + plan['definition_sha256']).encode()).hexdigest()[:32],
                    source='paper_pipeline', skill_id='paper_research', tool='qrtk_paper_research', arguments=args,
                    definition_sha256=fingerprint(args), original_goal=ctx.get('goal', '')[:2000], research_goal=ctx.get('goal', '')[:2000],
                    change=('论文《' + (entry.get('title') or entry['name'])[:80] + '》的因子“' + plan['factor'][:80] + '”：' +
                            decision_question(plan))[:1000],
                    description='\n'.join(decision_text(plan).splitlines()[1:])[:3000],    # the question is already in `change`
                    other_factors=[n for n in names if n != plan['factor']][:6],
                    # an asset substitution (futures/options/... -> A-share stocks) needs these exact words, not "同意"
                    required_phrase=ASSET_PHRASE if plan.get('asset_consent_required') else None)

    def _implementation(self, ledger, plan, client, args, entry, ctx):
        """Registered implementation for this plan, or a CodeApprovalRequired package. Never runs unapproved code."""
        from paper_agent.ledger import sha256_text
        cand = ledger.state.get('candidate')
        if not cand or cand.get('plan_sha256') != plan['definition_sha256']:
            if client is None:
                raise Denied('MODEL_UNAVAILABLE_FOR_ALGORITHM_DESIGN')
            from paper_agent.algorithm import design, design_pair
            from paper_agent.ledger import BudgetExceeded
            task = ledger.read_artifact('research_task.json') if plan['route'] != 'algorithm' else None
            if task is None and plan['route'] != 'algorithm':
                raise ContractError('PAPER_TASK_MISSING')
            if (plan.get('dsl') or {}).get('production_preflight', {}).get('accepted') is False:
                task = dict(task, dsl=dict(task['dsl'], status='requires_new_implementation', expression=None,
                            reasons=[{'code': 'PRODUCTION_DSL_REJECTED', 'detail': plan['dsl']['production_preflight']['error']}]))
            ctx['emit']('RESEARCH_STAGE', dict(stage='algorithm_design', status='RUNNING', elapsed_seconds=0))
            try:
                if plan['route'] == 'algorithm':
                    candidate, history = design_pair(plan['algorithm_contract'], client, ledger, out_dir=ledger.dir / 'candidates' / 'bundle')
                else:
                    candidate, history = design(task, client, ledger, out_dir=ledger.dir / 'candidates' / 'bundle')
            except BudgetExceeded:
                raise BudgetExhausted('paper_model_calls') from None
            source = candidate['files']['candidate.py']
            cand = dict(status=candidate['status'], source_sha256=sha256_text(source), plan_sha256=plan['definition_sha256'],
                        bundle=str(ledger.dir / 'candidates' / 'bundle'), revisions=len(history),
                        static_issues=[i['code'] for i in candidate['analysis']['issues']],
                        tests=[c['name'] for c in candidate['tests']['cases']], design_summary=candidate['design'].get('summary', ''),
                        pair=plan['route'] == 'algorithm')
            ledger.state['candidate'] = cand
            ledger.save()
            if cand['status'] != 'READY_FOR_REVIEW':
                raise ContractError('CANDIDATE_FAILED_STATIC_REVIEW: ' + ','.join(cand['static_issues'][:6]))
            self.registry.request(candidate, task_id=ledger.task_id, plan_sha256=plan['definition_sha256'],
                                  bundle_dir=ledger.dir / 'candidates' / 'bundle')
        entry_reg = self.registry.registered(cand['source_sha256'])
        if entry_reg:
            return entry_reg
        bundle = Path(cand['bundle'])
        if not (self.registry.root / 'requests' / f"{cand['source_sha256']}.json").exists():
            # A cached candidate whose review request is missing (e.g. a copied or restored paper ledger, live Q5): rebuild
            # the request from the bundle after a fresh static review; the source must still match its recorded SHA.
            self.registry.request(_bundle_candidate(bundle, cand['source_sha256']), task_id=ledger.task_id,
                                  plan_sha256=plan['definition_sha256'], bundle_dir=bundle)
        source = (bundle / 'candidate.py.txt').read_text(encoding='utf-8')
        contract = json.loads((bundle / 'contract.json').read_text(encoding='utf-8'))
        dsl = plan.get('dsl') or {}
        reasons = [r.get('detail') or r.get('code') for r in (dsl.get('reasons') or [])]
        if dsl.get('production_preflight', {}).get('error'):
            reasons.append(dsl['production_preflight']['error'])
        pair = plan['route'] == 'algorithm'
        if pair:
            reasons = ['论文因子超出可信算子语法（路径依赖/条件/窗口内排序或回归残差等），只能由新算法计算']
        package = dict(kind='code', tool='qrtk_paper_research', arguments=args, definition_sha256=fingerprint(args),
            source_sha256=cand['source_sha256'], plan_sha256=plan['definition_sha256'],
            contract_sha256=sha256_text(json.dumps(contract, sort_keys=True)), paper_task=ledger.task_id,
            created_at=time.time(), expires_at=time.time() + CODE_APPROVAL_SECONDS, source=source,
            what=f"{plan['factor']}：{plan['ir_execution']}（{cand['design_summary'][:200]}）",
            why_not_dsl='；'.join(str(x) for x in reasons[:3]) or '受控DSL缺少该公式所需的算子或字段',
            review=(f"这份文件含两份独立实现：compute()（向量化）与 reference()（逐行循环，另一次模型调用写成，未看过 compute()）；"
                    f"静态审核通过（compute 完整审核，reference 安全与时间方向审核）。批准后先在 {len(cand['tests'])} 组合成数据上要求两者逐格一致，"
                    "并检查未来扰动不影响过去、缺失与零值处理一致；真实计算时抽样列与 reference() 逐格核对，不一致即中止。"
                    if pair else
                    f"静态检查通过（{cand['revisions']}次修订）；批准后先运行独立已知真值测试：{', '.join(cand['tests'])}；"
                    '真实计算时每个单元格与可信IR求值器交叉校验，不一致即中止。'),
            permissions=('只读取已发布 Train 2020–2023 / Validation 2024–2025 的 ' + ', '.join(sorted({i['field'] for i in contract['inputs']})) +
                         ' 面板；在 Agent 进程内以 quantagent（非root）运行，不能访问原始行情、密钥或 2026 私有数据；' +
                         ('受控评价器不运行模型代码，本研究的 2026 Test 将标为不可评价。' if pair else
                          '2026 Test 由独立评价身份用可信IR重算，不执行这段代码。')),
            risks='模型生成代码在Agent进程权限内执行，这不是操作系统沙箱；程序只接受这一份SHA，任何改动都需要重新审核。',
            research_goal=ctx.get('goal', '')[:2000], skill_id='paper_research',
            id=hashlib.sha256((ctx['task_id'] + cand['source_sha256']).encode()).hexdigest()[:32])
        raise CodeApprovalRequired(package)
