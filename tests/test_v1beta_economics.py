"""Economic rationale: ex-ante freeze, program fact checks, deterministic evidence comparison, report rendering."""
import json
from pathlib import Path

from research_agent.contracts import canonical
from research_agent.economic_rationale import check, compare, verdict_text
from research_agent.llm import ModelResponse
from v1beta_fixtures import REVERSAL, TRAIN, broker, build, context

ANALYSIS = dict(
    intuition=dict(measures='过去5个观察日收盘价收益的相反数', high_value_means='近期跌幅较大', low_value_means='近期涨幅较大'),
    mechanisms=[dict(name='短期过度反应', category='overreaction', source='literature', literature='Jegadeesh (1990); Lehmann (1990)',
                     explanation='投资者对短期信息过度反应，价格偏离后部分回归。', citations=[]),
                dict(name='流动性冲击后的价格修正', category='liquidity_shock_reversal', source='paper_author',
                     explanation='临时卖压由做市与套利资金吸收后价格反弹，已被证明是主要来源。',
                     citations=[dict(passage='P0001', quote='not in the paper at all')])],
    narrative=['短期大幅下跌', '因子值升高', '卖压消退、价格修正', '未来短期收益相对较高'],
    expected_direction='positive', direction_reason='过度反应与流动性冲击后的修正都预示近期跌幅大的股票相对反弹。',
    conditions='流动性正常、无持续信息冲击时更可能成立。', data_implications='未复权价格会把除权当作价格冲击。',
    alternative_explanations=['买卖价差反弹（bid-ask bounce）'], failure_regimes=['趋势性行情或连续跌停'],
    next_tests=['按成交额分组检验反转是否集中在低流动性股票'], mechanism_clarity='tentative')


def test_fact_checks_relabel_unverifiable_attribution_and_causal_language():
    paper = dict(passages=[dict(id='P0001', page=3, text='Prices react to order flow.')], verify_quote=lambda pid, q: None)
    r = check(json.loads(json.dumps(ANALYSIS)), paper=paper, horizon=5)
    sources = {m['name']: m['source'] for m in r['mechanisms']}
    assert sources['短期过度反应'] == 'literature' and sources['流动性冲击后的价格修正'] == 'agent_hypothesis'
    assert '已被证明' not in json.dumps(r, ensure_ascii=False) and any('因果' in n for n in r['check_notes'])
    assert r['generated_before_results'] and len(r['sha256']) == 64 and r['deployment_limits']
    no_lit = check(dict(ANALYSIS, mechanisms=[dict(ANALYSIS['mechanisms'][0], literature='')]), horizon=5)
    assert no_lit['mechanisms'][0]['source'] == 'agent_hypothesis'
    empty = check(dict(ANALYSIS, mechanisms=[]), horizon=5)
    assert empty['mechanism_clarity'] == 'unclear'


def test_unverified_author_wording_is_marked_not_only_relabelled():
    """Live Amihud run: 'Amihud 提出…/作者指出…' stayed in the text of mechanisms relabelled as Agent hypotheses."""
    from research_agent.economic_rationale import UNVERIFIED
    mech = [dict(name='非流动性补偿', category='liquidity_premium', source='paper_author', citations=[],
                 explanation='Amihud 提出预期收益随非流动性上升。'),
            dict(name='逆向选择', category='information_diffusion', source='agent_hypothesis', citations=[],
                 explanation='作者指出非流动性反映逆向选择成本。'),
            dict(name='交易摩擦', category='trading_constraints', source='agent_hypothesis', citations=[], explanation='高摩擦延缓价格调整。')]
    raw = dict(ANALYSIS, mechanisms=mech, direction_reason='论文作者提出的核心假设是预期收益随非流动性上升。')
    paper = dict(passages=[dict(id='P1', page=2, text='expected returns increase in illiquidity')],
                 verify_quote=lambda pid, q: pid == 'P1' and q in 'expected returns increase in illiquidity')
    r = check(json.loads(json.dumps(raw)), paper=paper, horizon=1)
    text = {m['name']: m['explanation'] for m in r['mechanisms']}
    assert text['非流动性补偿'].startswith(UNVERIFIED) and text['逆向选择'].startswith(UNVERIFIED)
    assert not text['交易摩擦'].startswith(UNVERIFIED) and r['direction_reason'].startswith(UNVERIFIED)
    assert r['paper_cited'] is False and r['paper_passages_provided'] is True
    cited = dict(mech[0], citations=[dict(passage='P1', quote='expected returns increase in illiquidity')])
    ok = check(json.loads(json.dumps(dict(raw, mechanisms=[cited]))), paper=paper, horizon=1)
    assert ok['paper_cited'] is True and ok['mechanisms'][0]['source'] == 'paper_author'
    assert not ok['mechanisms'][0]['explanation'].startswith(UNVERIFIED) and not ok['direction_reason'].startswith(UNVERIFIED)


def test_bare_quote_citations_are_located_in_the_passages_or_rejected():
    """Live R2: DeepSeek returned citations as plain quotes; all were dropped although they were verbatim paper text."""
    text = 'traders use the 52-week high as a reference point against which they evaluate news'
    passages = [dict(id='P0009', page=2, text='Unrelated text.'), dict(id='P0010', page=2, text='We argue ' + text + '.')]
    paper = dict(passages=passages, verify_quote=lambda pid, q: any(p['id'] == pid and q in p['text'] for p in passages))
    mech = [dict(name='锚定', category='anchoring_reference_point', source='paper_author', explanation='作者提出参考点解释。', citations=[text]),
            dict(name='虚构', category='other', source='paper_author', explanation='作者认为价格永远上涨。', citations=['prices always rise'])]
    r = check(json.loads(json.dumps(dict(ANALYSIS, mechanisms=mech))), paper=paper, horizon=10)
    real, fake = r['mechanisms']
    assert real['source'] == 'paper_author' and real['citations'] == [dict(passage='P0010', quote=text, page=2)]
    assert fake['source'] == 'agent_hypothesis' and fake['citations'] == [] and fake['explanation'].startswith('【')
    assert r['paper_cited'] is True


def test_passage_references_with_a_page_suffix_are_checked_strictly():
    """Live P1: DeepSeek cited {"passage": "P0010 p2", ...} (the prompt shows `[P0010 p2]`); the id never matched."""
    text = 'traders use the 52-week high as a reference point against which they evaluate the potential impact of news'
    passages = [dict(id='P0010', page=2, text='An explanation is that ' + text + '.'), dict(id='P0011', page=3, text='Other.')]
    paper = dict(passages=passages, verify_quote=lambda pid, q: any(p['id'] == pid and q in p['text'] for p in passages))

    def one(ref, quote=text):
        mech = [dict(name='锚定', category='anchoring_reference_point', source='paper_author', explanation='作者提出参考点解释。',
                     citations=[dict(passage=ref, quote=quote)])]
        return check(json.loads(json.dumps(dict(ANALYSIS, mechanisms=mech))), paper=paper, horizon=10)['mechanisms'][0]
    for ref in ('P0010', 'P0010 p2', 'P0010, p.2', ' P0010  p2 '):
        m = one(ref)
        assert m['source'] == 'paper_author' and m['citations'] == [dict(passage='P0010', quote=text, page=2)], ref
    for ref in ('P0010 p3', 'P0011 p3', 'P9999', 'p2 P0010', 'P0010 page two', '', None):          # wrong page / id / shape
        assert one(ref)['source'] == 'agent_hypothesis' and one(ref)['citations'] == [], ref
    assert one('P0010 p2', quote='traders always anchor on the 52-week high')['source'] == 'agent_hypothesis'   # quote not in text


def test_comparison_statuses_are_deterministic():
    part = lambda m, lo, hi, n=900, ls=.001: dict(rank_ic_mean=m, rank_ic_ci_low=lo, rank_ic_ci_high=hi, rank_ic_n_dates=n, long_short_mean_gross=ls)
    pro = dict(partitions=dict(train=part(.02, .01, .03), valid=part(.01, -.01, .03)),
               test=dict(status='COMPLETED', metrics=part(-.03, -.05, -.01, 120, -.002)))
    rows = compare(dict(expected_direction='positive'), pro, {})
    assert [r['status'] for r in rows] == ['SUPPORTS', 'CONSISTENT_INCONCLUSIVE', 'CONTRADICTS']
    text = verdict_text(dict(status='CHECKED', expected_direction='positive'), rows)
    assert '没有得到稳定支持' in text and '事前' in text
    rows = compare(dict(expected_direction='positive'), dict(partitions=pro['partitions'], test=dict(status='NOT_EVALUATED', reason='NOT_AUTHORIZED')), {})
    assert rows[-1]['status'] == 'NO_DATA' and 'NOT_AUTHORIZED' in rows[-1]['note']


def test_rationale_is_frozen_before_computation_and_rendered(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    calls, events = [], []

    def model(request):
        calls.append(request)
        assert not any(k == 'RESEARCH_STAGE' and p['stage'] == 'factor_construction' for k, p in events)  # nothing computed yet
        assert not any(w in request.messages[-1].content for w in ('RankIC均值', 'IC均值', 'HAC', 'Validation结果'))  # no results exist yet
        return ModelResponse(canonical(ANALYSIS))
    ctx = context(events=events) | {'model': model, 'model_live': True}
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', ctx)
    assert len(calls) == 1
    kinds = [k for k, p in events]
    frozen = kinds.index('ECONOMIC_RATIONALE_FROZEN')
    assert frozen < next(i for i, (k, p) in enumerate(events) if k == 'RESEARCH_STAGE' and p['stage'] == 'factor_construction')
    original = Path(result['factor_path']).parents[1]
    stored = json.loads((original / 'code/economic_rationale.json').read_text(encoding='utf-8'))
    assert stored['sha256'] == result['economic_rationale']['sha256'] == next(p for k, p in events if k == 'ECONOMIC_RATIONALE_FROZEN')['sha256']
    for report in (Path(result['html_path']), Path(result['html_path']).with_suffix('.md')):   # latest = rolling revision
        text = report.read_text(encoding='utf-8')
        for heading in ('Economic Rationale', '经济直觉', '作用路径', '事前预期方向', '经济解释的局限', '经济假设与实证证据对照'):
            assert heading in text, (report.name, heading)
        assert 'Jegadeesh (1990)' in text and 'Agent提出的理论假设' in text and '统计相关不构成因果证明' in text
    tables = {t['id']: t for t in json.loads((Path(result['report_artifact_path']) / 'data/report_tables.json').read_text(encoding='utf-8'))}
    stages = [row[0] for row in tables['economic_evidence']['values']]
    assert stages == ['Train', 'Validation', 'Test'] and tables['economic_evidence']['values'][2][2] is not None   # Test compared


def test_without_a_model_the_report_says_so_and_invents_nothing(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    assert result['economic_rationale']['status'] == 'UNAVAILABLE'
    text = Path(result['html_path']).read_text(encoding='utf-8')
    assert '经济逻辑分析不可用' in text and '经济直觉' not in text
