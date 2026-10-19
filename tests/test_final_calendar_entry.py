"""Calendar checks stay ON at upload -> real conversation -> research entry.

Complements the historical nineteen mechanism tests that explicitly turn the
calendar detector off. This module never requests that fixture or changes it.
All model replies are recorded/scripted; the broker only sees synthetic data.
"""
import json
from pathlib import Path
import pytest
from paper_agent import reconcile
from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ModelResponse
from research_agent.paper_library import PaperLibrary
from test_v1beta_papers import PaperProvider,decision,stage,FIX,patched_rolling,paper_call
from test_v1beta_semantics import load,insisting
from v1beta_fixtures import build,broker

CALENDAR_PATTERN=reconcile.CALENDAR_COUNT.pattern

class GHProvider(PaperProvider):
    def __init__(self,decisions):
        super().__init__(decisions)
        _,script=load('gh')
        self.queues['understanding']=script['paper_understanding']
        self.queues['repair']=script['formula_repair']
        self.gh=insisting('gh')['factor']
        self.queues['rationale']=[canonical(dict(
            intuition=dict(measures='当前价格接近过去一年高点的程度',high_value_means='更接近高点',low_value_means='距离高点更远'),
            mechanisms=[dict(name='锚定效应',category='behavioral',source='hypothesis',literature='',explanation='历史高点可能影响投资者参考价格。',citations=[])],
            narrative=['历史高点形成参考价格','价格接近高点','投资者可能缓慢调整预期','后续收益可能延续'],
            expected_direction='positive',direction_reason='待检验的锚定机制。',conditions='信息逐步进入价格。',
            data_implications='月度论文按明确披露的交易日换算探索；不声称忠实月度复现。',
            alternative_explanations=['一般动量'],failure_regimes=['市场急剧反转'],next_tests=['控制动量后检验'],mechanism_clarity='tentative'))]

    def complete(self,request):
        if paper_call(request) and 'Write its formula at observation date t' in request.messages[-2].content:
            self.calls.append(request)
            return ModelResponse(canonical(dict(formula_latex=self.gh['formula_latex'],parameters=self.gh.get('parameters') or [],symbols=self.gh['symbols'])))
        return super().complete(request)

def paper_chat(tmp_path,provider,patched_rolling,paper):
    assert reconcile.CALENDAR_COUNT.pattern==CALENDAR_PATTERN and reconcile.CALENDAR_COUNT.search('当年有数据的交易日数')
    fx=build(tmp_path)
    cfg=json.loads(fx['config'].read_text());cfg['require_rolling_test']=True
    fx['config'].write_text(json.dumps(cfg),encoding='utf-8')
    patched_rolling['client'],_=broker(fx)
    lib=PaperLibrary(tmp_path/'papers')
    entry=lib.import_pdf(stage(lib,FIX/paper),paper)
    app=build_chat(tmp_path/'state',provider=provider,profile='development',resources_manifest=fx['manifest'],research_config=fx['config'])
    return app,fx,entry

def test_gh_upload_read_gate_and_complete_report_with_calendar_checks_on(tmp_path,patched_rolling):
    p=GHProvider([decision('skill',skill_id='paper_research',goal='研究刚上传的GH论文因子'),decision(consent='accept')])
    app,fx,entry=paper_chat(tmp_path,p,patched_rolling,'gh4-paper.pdf')
    first=app.turn('研究我刚上传的论文，提取52周高点因子。')
    assert '回复“同意”' in first,first
    assert not list((fx['workspace']/'research_runs').glob('*/*'))
    result=app.turn('同意，按这个口径探索性研究。')
    task=app.store.load(app.store.session_turns(app.session_id)[-1]['research_task_id'])
    assert task.status=='COMPLETED',(result,task.error)
    data=next(e['result']['data'] for e in task.experiments if e['tool']=='qrtk_paper_research')
    assert data['final_report_ready'] and data['paper']['route']=='trusted_ir'
    original=Path(data['factor_path']).parents[1]
    assert data['html_path']==str(original/'reports/report.html')
    assert len(list(original.parent.iterdir()))==1
    assert '完整研究已完成' in result and '2026滚动暴露评价' in result
    assert reconcile.CALENDAR_COUNT.pattern==CALENDAR_PATTERN

def test_genuine_amihud_upload_is_explained_and_never_executed(tmp_path,patched_rolling):
    p=PaperProvider([decision('skill',skill_id='paper_research',goal='研究刚上传的Amihud论文')])
    app,fx,_=paper_chat(tmp_path,p,patched_rolling,'amihud2002.pdf')
    result=app.turn('研究我刚上传的论文因子。')
    # I5 attempts the autonomous route; this legacy scripted provider has no
    # autonomous contract response. Report the actual failure, not the obsolete
    # calendar-operator limitation, and still never execute an unapproved study.
    assert 'AUTONOMOUS_CONTRACT_MODEL_FAILED' in result,result
    assert 'CALENDAR_WINDOW_UNSUPPORTED' not in result,result
    assert '没有执行任何计算' in result,result
    assert not list((fx['workspace']/'research_runs').glob('*/*'))
    assert not app.store.session(app.session_id).get('pending_code_approval')
    assert reconcile.CALENDAR_COUNT.pattern==CALENDAR_PATTERN
