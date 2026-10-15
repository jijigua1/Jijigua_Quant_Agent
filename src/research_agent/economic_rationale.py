"""Economic rationale: an ex-ante, evidence-checked mechanism analysis, then a deterministic comparison with results.

Order is enforced by the caller: the analysis is generated and frozen (hash + ledger event) before the factor is
computed, so the expected direction cannot be chosen after seeing Train/Validation/Test. One constrained model call;
paper factors reuse passages already parsed for the study (no re-parsing). Fact checks are program code:
  * an author attribution needs a quote that matches the parsed paper text, otherwise it is relabelled as a hypothesis
  * external literature is labelled "cited by the Agent, not verified against source text here"
  * causal/proof language is flagged; data limitations of this deployment are appended by the program
The comparison table (ex-ante direction vs Train/Validation/Test RankIC, HAC interval, group ordering) is computed
from the report's own statistics at every render, so a new Test revision updates it without another model call.
"""
import hashlib
import json
import re
import time

VERSION = 'economic-rationale/4'   # /4: "P0010 p2" references checked strictly; /3: bare quotes located; /2: unverified wording marked
CATEGORIES = ('overreaction', 'underreaction', 'anchoring_reference_point', 'limited_attention', 'liquidity_premium',
              'liquidity_shock_reversal', 'risk_premium', 'microstructure', 'information_diffusion', 'trading_constraints', 'other')
SOURCES = ('paper_author', 'literature', 'agent_hypothesis')
SOURCE_LABEL = {'paper_author': '论文作者观点（已核对原文）', 'literature': '外部文献观点（Agent引述，未在本系统核对原文）',
                'agent_hypothesis': 'Agent提出的理论假设（待实证检验）'}
DIRECTIONS = ('positive', 'negative', 'unclear')
EX_ANTE_NOTE = ('分析在本次计算任何结果之前生成并冻结；但若该因子已有公开研究或本系统既往结果，'
                '事前预期可能受到既有知识影响，不能视为对结果完全未知。')
CAUSAL = re.compile(r'已(被)?(证明|证实|验证)|证明了|因果关系成立|必然导致|一定会')
AUTHOR_CLAIM = re.compile(r'作者|论文(中)?(指出|认为|提出|发现|主张|强调|假设)|原文|文中')
UNVERIFIED = '【作者归属未经原文核对，以下仅作为Agent假设】'

SYSTEM = """你是严谨的实证资产定价研究员，为一项尚未计算结果的A股日频因子研究撰写事前经济逻辑。读者具备金融与量化基础。
规则：
1. 只依据给定的因子定义、研究定义、数据口径和（若有）论文原文段落；此时没有任何回测或IC结果，不得提及或推测数值结果。
2. 机制只选真正相关的1–3个，说明为何相关；不得机械罗列。没有可信机制时 mechanism_clarity=unclear 并如实说明“经济机制尚不明确”。
3. source=paper_author 仅当给定原文段落中作者明确提出该解释，并在 citations 中逐字摘录（quote须是该段落中连续出现的原文，≤200字符）；
   source=literature 用于公认的已发表文献观点，literature 字段写作者与年份；其他一律 source=agent_hypothesis。不得把未解释的机制归于作者。
4. narrative 写完整链条：可观察市场现象 → 因子信号 → 潜在定价或交易行为 → 预期收益关系；明确这是待检验机制，不是因果证明。
5. expected_direction：基于经济逻辑，原始因子值越高，未来H日开盘到开盘收益预期更高(positive)/更低(negative)/无法事前判断(unclear)；
   conditions 写适用条件。若研究口径与论文不同（未复权价格、日频替代月频、近似窗口、A股市场），data_implications 说明经济含义可能如何变化。
6. 中文正式、具体，避免空泛套话；每个字段1–4句。输出严格JSON，字段与示例一致。
示例结构：{"intuition":{"measures":"...","high_value_means":"...","low_value_means":"..."},
"mechanisms":[{"name":"...","category":"overreaction","source":"paper_author","explanation":"...","literature":"",
"citations":[{"passage":"P0032","quote":"该段落中连续出现的英文原文"}]},{"name":"...","category":"other","source":"agent_hypothesis","explanation":"...","literature":"","citations":[]}],
"narrative":["...","...","...","..."],"expected_direction":"negative","direction_reason":"...","conditions":"...",
"data_implications":"...","alternative_explanations":["..."],"failure_regimes":["..."],"next_tests":["..."],"mechanism_clarity":"tentative"}
category 取值：""" + ', '.join(CATEGORIES)


def _text(x, n=600):
    return str(x or '').strip()[:n]


def _deployment_limits(horizon):
    return ['价格为未复权原始价格，除权除息会在收益与因子中制造非经济跳变。',
            '股票池为固定发布证券轴与候选上市掩码，历史成分与上市状态未做时点认证。',
            f'标签为重叠的{horizon}日开盘到开盘毛收益，未扣交易成本，也未处理涨跌停、停牌等可交易性约束。',
            '统计关联只能检验机制的可观察含义，不能单独证明因果关系。']


def generate(model_call, *, factor_name, formula, definition, horizon, data_profile, paper=None, user_hypothesis=''):
    """One constrained model call. Returns the checked analysis (status, sha256) or an UNAVAILABLE record."""
    from .contracts import parse_json
    from .llm import Message, ModelRequest, Role
    started = time.time()
    lines = [f'因子名称：{factor_name}', f'公式（执行定义）：{formula}', f'研究定义：{definition}',
             f'预测期：H={horizon}个观察日；标签 open[T+1+H]/open[T+1]-1；横截面IC/RankIC与五分组毛收益。',
             '数据口径：' + _text(json.dumps(data_profile, ensure_ascii=False), 700)]
    if user_hypothesis:
        lines.append('用户/研究计划中的假设表述：' + _text(user_hypothesis, 500))
    passages = []
    if paper:
        lines.append(f"论文：{paper['title']}；作者对因子的文字定义：{_text(paper.get('verbal_definition'), 500)}")
        if paper.get('substitutions'):
            lines.append('本研究与论文的口径差异：' + '；'.join(_text(s, 160) for s in paper['substitutions'][:6]))
        passages = paper.get('passages', [])
        lines.append('论文原文段落（仅可从这些段落摘录作者观点）：\n' + '\n'.join(f"[{p['id']} p{p['page']}] {p['text']}" for p in passages))
    request = ModelRequest((Message(Role.SYSTEM, SYSTEM), Message(Role.USER, '\n'.join(lines))), output_schema={'type': 'object'})
    try:
        raw = parse_json(model_call(request).content)
    except Exception as exc:  # noqa: BLE001 - recorded; the report states the analysis is unavailable
        return unavailable('MODEL_CALL_FAILED: ' + type(exc).__name__, horizon)
    return check(raw, paper=paper, horizon=horizon, seconds=time.time() - started)


PASSAGE_REF = re.compile(r'\s*(P\d{1,6})(?:\s*[,;]?\s*p\.?\s*(\d{1,4}))?\s*')


def _passage_id(ref, paper):
    """The passage id of a citation reference. The prompt shows passages as `[P0010 p2]`, and the model may copy the page
    (live P1: "P0010 p2"). Only `P<id>` with an optional page is read, and a stated page must be that passage's real page;
    anything else returns None, so the citation stays unverified (the quote itself is still checked afterwards)."""
    m = PASSAGE_REF.fullmatch(ref) if isinstance(ref, str) else None
    if not m:
        return None
    pid, page = m.group(1), m.group(2)
    if page is not None:
        real = next((p.get('page') for p in (paper or {}).get('passages', []) if p['id'] == pid), None)
        if real is None or int(page) != int(real):
            return None
    return pid


def unavailable(reason, horizon):
    record = dict(version=VERSION, status='UNAVAILABLE', reason=reason, expected_direction='unclear',
                  deployment_limits=_deployment_limits(horizon), generated_before_results=True)
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return record


def check(raw, *, paper=None, horizon=5, seconds=0.0):
    """Program-side fact checks; never trusts the model's own attribution."""
    notes = []
    if not isinstance(raw, dict):
        return unavailable('MODEL_OUTPUT_NOT_OBJECT', horizon)
    verify = paper.get('verify_quote') if paper else None
    mechanisms = []
    for m in (raw.get('mechanisms') or [])[:3]:
        if not isinstance(m, dict):
            continue
        source = m.get('source') if m.get('source') in SOURCES else 'agent_hypothesis'
        good = []
        for c in (m.get('citations') or [])[:3]:
            if isinstance(c, str) and verify:    # a bare quote (live R2): located in the supplied passages, never taken as given
                c = dict(passage=next((p['id'] for p in paper.get('passages', []) if verify(p['id'], c)), None), quote=c)
            if isinstance(c, dict):
                c = dict(c, passage=_passage_id(c.get('passage'), paper))
            if isinstance(c, dict) and verify and c.get('passage') and verify(c.get('passage'), c.get('quote')):
                good.append(dict(passage=c.get('passage'), quote=_text(c.get('quote'), 200),
                                 page=next((p['page'] for p in paper.get('passages', []) if p['id'] == c.get('passage')), None)))
        if source == 'paper_author' and not good:
            source = 'agent_hypothesis'
            notes.append(f"机制“{_text(m.get('name'), 40)}”标为作者观点但原文引用未能核对，已改标为Agent假设。")
        if source == 'literature' and not _text(m.get('literature')):
            source = 'agent_hypothesis'
            notes.append(f"机制“{_text(m.get('name'), 40)}”未给出文献出处，已改标为Agent假设。")
        explanation = _text(m.get('explanation'), 700)
        if CAUSAL.search(explanation):
            notes.append(f"机制“{_text(m.get('name'), 40)}”的表述含因果/证明措辞，已标注为待检验。")
            explanation = CAUSAL.sub('（待检验）', explanation)
        if source == 'agent_hypothesis' and (m.get('source') == 'paper_author' or AUTHOR_CLAIM.search(explanation)):
            # the label alone is not enough: wording that still credits the author is marked as unverified
            notes.append(f"机制“{_text(m.get('name'), 40)}”的表述涉及作者观点但没有核对过的原文引用，已在正文标注。")
            explanation = UNVERIFIED + explanation
        mechanisms.append(dict(name=_text(m.get('name'), 60), category=m.get('category') if m.get('category') in CATEGORIES else 'other',
                               source=source, source_label=SOURCE_LABEL[source], explanation=explanation,
                               literature=_text(m.get('literature'), 160) if source == 'literature' else '', citations=good))
    direction = raw.get('expected_direction') if raw.get('expected_direction') in DIRECTIONS else 'unclear'
    clarity = raw.get('mechanism_clarity') if raw.get('mechanism_clarity') in ('clear', 'tentative', 'unclear') else 'unclear'
    if not mechanisms:
        clarity = 'unclear'
        notes.append('模型未给出可用机制；经济机制记为尚不明确。')
    intuition = raw.get('intuition') if isinstance(raw.get('intuition'), dict) else {}
    verified = any(m['citations'] for m in mechanisms if m['source'] == 'paper_author')
    reason = _text(raw.get('direction_reason'), 500)
    if not verified and AUTHOR_CLAIM.search(reason):
        notes.append('方向理由引用了作者观点，但没有核对过的原文引用，已在正文标注。')
        reason = UNVERIFIED + reason
    record = dict(version=VERSION, status='CHECKED', generated_before_results=True, mechanism_clarity=clarity,
        intuition={k: _text(intuition.get(k), 500) for k in ('measures', 'high_value_means', 'low_value_means')},
        mechanisms=mechanisms, narrative=[CAUSAL.sub('（待检验）', _text(x, 300)) for x in (raw.get('narrative') or [])[:6]],
        expected_direction=direction, direction_reason=reason,
        conditions=_text(raw.get('conditions'), 400), data_implications=_text(raw.get('data_implications'), 600),
        alternative_explanations=[_text(x, 300) for x in (raw.get('alternative_explanations') or [])[:4]],
        failure_regimes=[_text(x, 300) for x in (raw.get('failure_regimes') or [])[:4]],
        next_tests=[_text(x, 300) for x in (raw.get('next_tests') or [])[:4]],
        deployment_limits=_deployment_limits(horizon), check_notes=notes, ex_ante_note=EX_ANTE_NOTE,
        paper_passages_provided=bool(paper), paper_cited=verified, model_seconds=round(seconds, 2))
    record['sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return record


def compare(rationale, professional, splits):
    """Deterministic ex-ante vs observed table. Never alters the ex-ante text or direction."""
    want = {'positive': 1, 'negative': -1}.get((rationale or {}).get('expected_direction'))
    parts = professional['partitions']
    rows = []
    test = professional.get('test', {})
    stages = [('Train', parts.get('train')), ('Validation', parts.get('valid'))]
    stages.append(('Test', test.get('metrics') if test.get('status') == 'COMPLETED' else None))
    for label, r in stages:
        if r is None:
            rows.append(dict(stage=label, expected=want, rank_ic=None, ci=None, groups=None, status='NO_DATA',
                             note='Test未评价：' + str(test.get('reason', test.get('status'))) if label == 'Test' else '无数据'))
            continue
        mean, low, high, n = r.get('rank_ic_mean'), r.get('rank_ic_ci_low'), r.get('rank_ic_ci_high'), r.get('rank_ic_n_dates')
        ls = r.get('long_short_mean_gross')
        if want is None:
            status = 'NO_EX_ANTE_DIRECTION'
        elif mean is None or not n:
            status = 'NO_DATA'
        elif mean * want > 0 and low is not None and high is not None and (low > 0 if want > 0 else high < 0):
            status = 'SUPPORTS'
        elif mean * want > 0:
            status = 'CONSISTENT_INCONCLUSIVE'
        elif low is not None and high is not None and (high < 0 if want > 0 else low > 0):
            status = 'CONTRADICTS'
        else:
            status = 'OPPOSITE_INCONCLUSIVE'
        rows.append(dict(stage=label, expected=want, rank_ic=mean, n_dates=n, ci=[low, high] if low is not None else None,
                         long_short=ls, groups_agree=None if ls is None or want is None else bool(ls * want > 0), status=status))
    return rows


STATUS_TEXT = {'SUPPORTS': '方向一致且HAC区间不跨0：支持该可观察含义', 'CONSISTENT_INCONCLUSIVE': '方向一致但区间跨0或样本不足：不足以判断',
               'CONTRADICTS': '方向相反且区间不跨0：不支持事前假设', 'OPPOSITE_INCONCLUSIVE': '方向相反但不显著：不支持且证据不足',
               'NO_DATA': '无可用数据', 'NO_EX_ANTE_DIRECTION': '事前未给出方向，无法对照'}


def verdict_text(rationale, rows):
    if not rationale or rationale.get('status') != 'CHECKED':
        return '经济逻辑分析不可用：' + str((rationale or {}).get('reason', '未生成')) + '。以下仅为统计结果。'
    direction = {'positive': '正相关', 'negative': '负相关', 'unclear': '无法事前判断'}[rationale['expected_direction']]
    parts = [f"事前预期：原始因子值与未来收益{direction}（在计算任何结果之前冻结）。"]
    for r in rows:
        if r['status'] in ('NO_DATA', 'NO_EX_ANTE_DIRECTION'):
            parts.append(f"{r['stage']}：{STATUS_TEXT[r['status']]}" + (f"（{r.get('note')}）" if r.get('note') else '') + '。')
        else:
            parts.append(f"{r['stage']}：RankIC均值{r['rank_ic']:+.4f}，{STATUS_TEXT[r['status']]}"
                         + ('' if r['groups_agree'] is None else '；高低组毛收益差方向' + ('一致' if r['groups_agree'] else '不一致')) + '。')
    observed = [r['status'] for r in rows if r['status'] not in ('NO_DATA', 'NO_EX_ANTE_DIRECTION')]
    if observed and all(s == 'SUPPORTS' for s in observed):
        parts.append('各已评价阶段均与事前方向一致；这只说明机制的可观察含义未被否定，不构成因果验证。')
    elif any(s in ('CONTRADICTS', 'OPPOSITE_INCONCLUSIVE') for s in observed):
        parts.append('至少一个阶段的方向与事前机制相反，该机制在当前数据与样本中没有得到稳定支持。')
    elif observed:
        parts.append('方向大体一致但统计证据不足，机制仍处于待检验状态。')
    return ''.join(parts)
