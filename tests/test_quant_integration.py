"""Independent numerical baselines and integration gates, synthetic fixtures only."""
from dataclasses import asdict,replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research_agent.app import build,build_chat
from research_agent.contracts import canonical,ContractError
from research_agent.llm import ModelResponse,Role,ToolCall
from research_agent.providers.mock import MockProvider
from research_agent.quant import QuantBackend,QUANT_SKILLS
from research_agent.quant_factors import build_factor
from research_agent.data import ResourceCatalog
from research_agent.security import Budget,Denied
import qrtk

@pytest.fixture
def research(tmp_path):
    rng=np.random.default_rng(712)
    days=pd.bdate_range('2023-01-02',periods=360)
    codes=[f'{i:06d}' for i in range(1,21)]
    close=pd.DataFrame(10*np.exp(rng.normal(0,.015,(len(days),len(codes))).cumsum(axis=0)),index=days,columns=codes)
    records=[]
    for i,d in enumerate(days):
        for j,c in enumerate(codes):
            p=float(close.iloc[i,j]);op=p*.999
            records.append(dict(Stkcd=c,Trddt=str(d.date()),Opnprc=op,Hiprc=p*1.02,Loprc=p*.98,
                                Clsprc=p,Dnshrtrd=100000+int(rng.integers(100000))))
    source=tmp_path/'history.csv';pd.DataFrame(records).to_csv(source,index=False)
    resource=dict(id='synthetic:history',path=str(source),format='csv',source='fixed seeded synthetic fixture',
        approval_ref='offline test fixture',data_kind='synthetic',frequency='daily',timezone='Asia/Shanghai',
        start_date=str(days[0].date()),end_date=str(days[-1].date()),date_column='Trddt',
        fields={'Stkcd':'string','Trddt':'date',**{c:'float' for c in ['Opnprc','Hiprc','Loprc','Clsprc','Dnshrtrd']}},
        adjustment='none',available_time='synthetic after close',sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    manifest=tmp_path/'resources.json';manifest.write_text(canonical({'version':'1','resources':[resource]}),encoding='utf-8')
    workspace=tmp_path/'workspace';workspace.mkdir();(workspace/'research_runs').mkdir()
    contract=dict(adjustment='none',volume_unit='shares',calendar='observed_union',available_time='synthetic after close',
                  corporate_actions='not_modelled',universe='synthetic fixed twenty codes',limits=['synthetic only'],research_use='synthetic')
    config=tmp_path/'research.json';config.write_text(canonical(dict(version='1',workspace=str(workspace),resources={'synthetic:history':contract})),encoding='utf-8')
    return dict(manifest=manifest,config=config,workspace=workspace,close=close,contract=contract,source=source)

class QuantProvider(MockProvider):
    def __init__(self,call=None):
        super().__init__();self.call=call or ToolCall('factor_study','qrtk_factor_study',args());self.requests=[]
    def complete(self,request):
        self.requests.append(request)
        results=[x for x in request.messages if x.role==Role.TOOL]
        if request.output_schema and 'research_goal' in request.output_schema['properties']:
            return ModelResponse(canonical(dict(action='skill',reply='',skill_id='factor_research',research_goal='计算固定五日反转因子',reason='固定路由测试')))
        if request.tools:
            return ModelResponse(tool_calls=(self.call,))
        return ModelResponse(canonical(dict(action='complete' if results else 'continue',hypothesis='五日反转可能有预测性',
            change_reason='记录实际计算，不调优测试段',summary='合成数据指标已计算；不是市场有效性结论。')))

def args(**changes):
    return dict(resource_id='synthetic:history',factor_id='reversal',lookback=5,horizon=5,n_groups=5,standardization='raw')|changes

def engine(research,tmp_path,provider=None,skill='factor_research'):
    return build(tmp_path/'state',provider=provider or QuantProvider(),profile='development',skill_id=skill,
                 resources_manifest=research['manifest'],research_config=research['config'])

def test_manual_pearson_and_tied_spearman():
    x=pd.DataFrame([[1,2,2,4]],index=pd.to_datetime(['2023-01-02']))
    y=pd.DataFrame([[4,1,3,2]],index=x.index)
    assert qrtk.cross_sectional_corr(x,y,min_obs=2).iloc[0]==pytest.approx(-2.5/math.sqrt(4.75*5))
    assert qrtk.cross_sectional_corr(x,y,method='spearman',min_obs=2).iloc[0]==pytest.approx(-3/math.sqrt(4.5*5))

def test_manual_labels_and_maturity():
    days=pd.bdate_range('2023-01-02',periods=6)
    p=pd.DataFrame({'A':[10,11,12,13,14,15]},index=days)
    labels=qrtk.forward_returns(p,horizon=2,lag=1)
    assert labels.iloc[0,0]==pytest.approx(13/11-1)
    assert labels.iloc[2,0]==pytest.approx(15/13-1)
    assert labels.iloc[-3:].isna().all().all()
    assert qrtk.label_exit_dates(days,horizon=2,lag=1).iloc[0]==days[3]

def test_fixed_builder_zscore_and_no_future_change(research):
    close=research['close'];volume=close*0+1000
    raw=build_factor('reversal',close,volume,5,'raw')
    assert raw.iloc[5,0]==pytest.approx(-(close.iloc[5,0]/close.iloc[0,0]-1))
    z=build_factor('reversal',close,volume,5,'zscore')
    assert np.nanmax(np.abs(z.mean(axis=1).to_numpy()))<1e-12
    assert np.nanmax(np.abs(z.std(axis=1,ddof=1).to_numpy()-1))<1e-12
    for kind in ('reversal','volume_stall'):
        full=build_factor(kind,close,volume,5,'raw')
        prefix=build_factor(kind,close.iloc[:100],volume.iloc[:100],5,'raw')
        pd.testing.assert_frame_equal(full.iloc[:100],prefix)

def test_full_main_workflow_writes_traceable_study(research,tmp_path):
    app=engine(research,tmp_path);state=app.run(app.create('五日反转').id)
    assert state.status=='COMPLETED',state.error
    result=state.experiments[0]['result']['data']
    assert result['splits']['test']=='sealed' and result['mode']=='synthetic'
    assert result['lookahead']['passed'] and not result['formal_backtest_ready']
    assert result['evidence']['verdict']=='insufficient' # no tradable account
    run=Path(result['artifact_path']);manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['task_status']=='COMPLETED' and manifest['task_id']==state.id
    assert manifest['provider']['provider']=='mock' and manifest['spec_fingerprint']==result['spec_fingerprint']
    assert len(manifest['files'])<100 and sum(f['bytes'] for f in manifest['files'])<20*1024*1024
    assert (run/'data/frozen_spec.json').exists() and Path(result['report_path']).exists()
    assert (run/'data/input_slice.csv').read_text().find(result['spec']['test'][0])==-1
    for file in manifest['files']:
        assert hashlib.sha256((run/file['path']).read_bytes()).hexdigest()==file['sha256']
    kinds=[e['kind'] for e in app.store.events(state.id)]
    assert kinds.count('AUTHORIZATION_ALLOWED')==1
    stages=[e['payload'] for e in app.store.events(state.id) if e['kind']=='RESEARCH_STAGE']
    assert any(e['stage']=='chart_generation' and e['status']=='COMPLETED' for e in stages)
    assert all(e['status'] in {'RUNNING','COMPLETED','FAILED','BLOCKED','SKIPPED','PENDING'} for e in stages)
    assert 'artifact_path' not in asdict(app.store.authorization(state.id)) # grants are distinct
    assert app.store.authorization(state.id).authority=='development_research_policy'

def test_five_skills_are_registered_with_real_bindings(research,tmp_path):
    app=build_chat(tmp_path/'state',provider=QuantProvider(),profile='development',resources_manifest=research['manifest'],research_config=research['config'])
    assert set(QUANT_SKILLS)<= {s['id'] for s in app.skills}
    for s in app.skills:
        if s['id'] in QUANT_SKILLS:
            assert s['tools'] and all(t['id'].startswith(('qrtk_','list_research_')) for t in s['tools'])
    reply=app.turn('五日反转')
    assert '成果目录：' in reply and '报告：' in reply
    task=app.store.load(app.store.session_turns(app.session_id)[0]['research_task_id'])
    result=task.experiments[0]['result']['data']
    other=build_chat(tmp_path/'state',provider=QuantProvider(),profile='development',resources_manifest=research['manifest'],research_config=research['config'])
    backend=QuantBackend(ResourceCatalog(research['manifest']),research['config'])
    context=dict(task_id='0'*32,session_id=other.session_id,store=other.store)
    with pytest.raises(Denied,match='STUDY_NOT_IN_SESSION'):
        backend.read_study('synthetic:history',result['study_id'],context)
    context['session_id']=app.session_id
    assert backend.read_study('synthetic:history',result['study_id'],context)['splits']==result['splits']

@pytest.mark.parametrize('changes',[{'lookback':True},{'lookback':21},{'resource_id':'/home/other'},
    {'code':'print(1)'},{'reveal_test':True},{'workspace':'/tmp'},{'_task_context':{'approved':True}}])
def test_quant_extra_parameters_paths_and_escalation_denied(research,tmp_path,changes):
    app=engine(research,tmp_path,QuantProvider(ToolCall('bad','qrtk_factor_study',args(**changes))))
    task=app.run(app.create('test').id)
    assert task.status=='INVALID_PARAMETERS' and task.error['code']=='INVALID_PARAMETERS'
    assert not task.experiments and not list((research['workspace']/'research_runs').iterdir())

def test_momentum_schema_rejection_is_not_authorization_denial(research,tmp_path):
    call=ToolCall('long_momentum','qrtk_expression_study',dict(resource_id='synthetic:history',
        expression={'nodes':[{'op':'field','field':'close'},{'op':'delay','args':[0],'window':65}], 'output':1},
        hypothesis='60日动量跳过最近5日',reason='用户要求默认完整动量',horizon=20,n_groups=5,
        standardization='zscore'))
    app=engine(research,tmp_path,QuantProvider(call))
    task=app.run(app.create('完整动量').id)
    assert task.status=='INVALID_PARAMETERS' and task.error['code']=='INVALID_PARAMETERS'
    event=next(x for x in app.store.events(task.id) if x['kind']=='TOOL_PARAMETERS_REJECTED')['payload']
    assert event['tool']=='qrtk_expression_study' and event['arguments']==call.arguments
    assert {(x['path'],x['constraint']) for x in event['violations']} == {
        ('$.expression.nodes[1].window','maximum'),('$.horizon','maximum')}
    grant=app.store.authorization(task.id)
    assert 'qrtk_expression_study' in grant.allowed_tools and 'synthetic:history' in grant.resources
    assert not any(e['kind']=='AUTHORIZATION_DENIED' for e in app.store.events(task.id))
    assert any(e['kind']=='TASK_INVALID_PARAMETERS' for e in app.store.events(task.id))
    assert not task.experiments

def test_short_momentum_alternative_uses_supported_causal_expression(research,tmp_path):
    expression={'nodes':[{'op':'field','field':'close'}, {'op':'returns','args':[0],'window':20},
        {'op':'delay','args':[1],'window':5}], 'output':2}
    call=ToolCall('short_momentum','qrtk_expression_study',dict(resource_id='synthetic:history',
        expression=expression,factor_name='momentum_20d_skip5_exploratory',
        hypothesis='短窗口探索替代：20日价格动量跳过最近5日；不代表标准长周期动量。',
        reason='65日样本无法支撑60日形成期和充分成熟标签；用户明确允许先完成可做部分。',
        horizon=5,n_groups=5,standardization='zscore'))
    app=engine(research,tmp_path,QuantProvider(call));task=app.run(app.create('短窗口动量').id)
    # A substitute is held until the conversation records the user's confirmation of exactly these arguments.
    assert task.status=='AWAITING_CONFIRMATION' and not task.experiments
    from research_agent.definition_gate import proposal
    app=engine(research,tmp_path,QuantProvider(call))
    app.definition_authorization=proposal(source='test',skill_id='factor_research',original_goal='完整动量',
        change='短窗口替代',research_goal='短窗口动量',tool=call.name,arguments=call.arguments)
    task=app.run(app.create('短窗口动量').id)
    assert task.status=='COMPLETED',task.error
    result=task.experiments[0]['result']['data']
    assert result['parameters']['definition']['expression']==expression
    assert result['parameters']['definition']['warmup_observations']==25
    assert result['factor_name']=='momentum_20d_skip5_exploratory'
    assert result['delivery_status']=='VERIFIED' and result['factor_path']
    assert not result['formal_backtest_ready']

def test_system_write_policy_cannot_be_overridden(research,tmp_path):
    app=engine(research,tmp_path);app.policy=replace(app.policy,write_scopes=())
    task=app.run(app.create('test').id)
    assert task.status=='AUTHORIZATION_DENIED' and task.error['code']=='TOOL_EFFECT_DENIED'

def test_unknown_adjustment_blocks_real_research(research,tmp_path):
    cfg=json.loads(research['config'].read_text());cfg['resources']['synthetic:history']['adjustment']='unknown'
    research['config'].write_text(canonical(cfg),encoding='utf-8')
    app=engine(research,tmp_path);task=app.run(app.create('test').id)
    assert task.status=='AUTHORIZATION_DENIED' and task.error['code']=='RESEARCH_DATA_CONTRACT_INCOMPLETE'

def test_false_predictive_contract_and_unknown_volume_refused(research,tmp_path):
    cfg=json.loads(research['config'].read_text());c=cfg['resources']['synthetic:history'];c['research_use']='predictive_research'
    research['config'].write_text(canonical(cfg),encoding='utf-8')
    app=engine(research,tmp_path);task=app.run(app.create('test').id)
    assert task.error['code']=='RESEARCH_DATA_CONTRACT_INCOMPLETE'
    c['research_use']='synthetic';c['volume_unit']='unknown';research['config'].write_text(canonical(cfg),encoding='utf-8')
    app=engine(research,tmp_path/'next',QuantProvider(ToolCall('volume','qrtk_factor_study',args(factor_id='volume_stall'))))
    assert app.run(app.create('test').id).error['code']=='VOLUME_UNIT_UNVERIFIED'

def test_backtest_skill_is_readiness_only(research,tmp_path):
    app=engine(research,tmp_path,QuantProvider(ToolCall('ready','qrtk_backtest_readiness',{'resource_id':'synthetic:history'})),skill='strategy_backtest')
    task=app.run(app.create('评估回测条件').id)
    assert task.status=='COMPLETED'
    result=task.experiments[0]['result']['data']
    assert result['status']=='BLOCKED_DATA_CONTRACT' and not result['real_backtest_enabled']
    assert 'qrtk_reference'==result['engine'] and 'cumulative_return' not in result

def test_resource_catalogue_can_complete_data_research_without_computation(research,tmp_path):
    app=engine(research,tmp_path,QuantProvider(ToolCall('catalog','list_research_resources',{})),skill='data_research')
    task=app.run(app.create('有哪些资源').id)
    assert task.status=='COMPLETED' and task.result['mode']=='catalog'
    assert task.result['analysis_scope']=='resource_catalog' and task.counters['tool_calls']==1

def test_premature_completion_must_obtain_authorized_tool_evidence(research,tmp_path):
    class Eager(QuantProvider):
        def complete(self,request):
            response=super().complete(request)
            if request.output_schema:
                value=json.loads(response.content);value['action']='complete'
                return ModelResponse(canonical(value))
            return response
    app=engine(research,tmp_path,Eager());task=app.run(app.create('直接完成').id)
    assert task.status=='COMPLETED' and task.counters['tool_calls']==1
    assert 'EVIDENCE_REQUIRED' in [e['kind'] for e in app.store.events(task.id)]

def test_independent_nav_fees_and_reconciliation():
    days=pd.bdate_range('2023-01-02',periods=3)
    prices=pd.DataFrame({'A':[10,10,11]},index=days)
    orders=pd.DataFrame([dict(signal_date=days[0],code='A',side='buy',shares=100),dict(signal_date=days[1],code='A',side='sell',shares=100)])
    costs=qrtk.CostModel(commission_rate=0,min_commission=5,stamp_duty_rate=.001)
    r=qrtk.run_backtest(orders,prices,prices,initial_cash=2000,costs=costs)
    assert r.daily.cash.iloc[1]==995 and r.daily.cash.iloc[2]==pytest.approx(2088.9)
    assert qrtk.reconcile(r)['ok']
    assert qrtk.performance_metrics(r)['cumulative_return']==pytest.approx(2088.9/2000-1)

def test_candidate_daily_normalizer_limitation_is_documented():
    # Audit evidence: upstream keeps negative volume; Agent's _load gate rejects it.
    raw=pd.DataFrame([dict(code='A',trade_date='2023-01-02',open=10,high=11,low=9,close=10,volume=-1,amount=-10)])
    data,issues=qrtk.normalize_daily_bars(raw,qrtk.DailyBarContract('share','CNY'),['2023-01-02'])
    assert data.volume.iloc[0]==-1

def test_adapter_rejects_negative_volume(research,tmp_path):
    frame=pd.read_csv(research['source'],dtype={'Stkcd':str});frame.loc[0,'Dnshrtrd']=-1
    frame.to_csv(research['source'],index=False)
    manifest=json.loads(research['manifest'].read_text());manifest['resources'][0]['sha256']=hashlib.sha256(research['source'].read_bytes()).hexdigest()
    research['manifest'].write_text(canonical(manifest),encoding='utf-8')
    app=engine(research,tmp_path);task=app.run(app.create('test').id)
    assert task.status=='TOOL_ERROR' and not task.experiments

def test_volume_stall_fixed_numerical_baseline():
    close=pd.DataFrame({'A':[10.]*6});volume=pd.DataFrame({'A':[100.]*5+[200.]})
    assert build_factor('volume_stall',close,volume,5,'raw').iloc[5,0]==pytest.approx(1.)

def test_failed_computation_has_failed_manifest(research,tmp_path,monkeypatch):
    from qrtk_skills import tools
    def fail(*args,**kwargs):raise RuntimeError('controlled test failure')
    monkeypatch.setattr(tools,'factor_evaluate',fail)
    app=engine(research,tmp_path);task=app.run(app.create('test').id)
    assert task.status=='TOOL_ERROR'
    manifests=[p for p in (research['workspace']/'research_runs').glob('*/*/manifest.json') if json.loads(p.read_text())['task_id']==task.id]
    assert len(manifests)==1
    manifest=json.loads(manifests[0].read_text(encoding='utf-8'))
    assert manifest['task_status']=='TOOL_ERROR' and manifest['result_sha256'] is None
    assert manifest['error']['code']=='TOOL_EXECUTION_FAILED'

def test_manifest_failure_cannot_leave_completed_ledger(research,tmp_path,monkeypatch):
    app=engine(research,tmp_path)
    def fail(task,events=()):raise OSError('controlled artifact failure')
    monkeypatch.setattr(app.artifacts,'finalize',fail)
    task=app.run(app.create('test').id)
    assert task.status=='AUDIT_ERROR' and app.store.load(task.id).status=='AUDIT_ERROR'

def test_study_evidence_tamper_rejected(research,tmp_path):
    app=engine(research,tmp_path);task=app.run(app.create('test').id)
    result=task.experiments[0]['result']['data'];run=Path(result['artifact_path'])
    (run/'data/analysis.json').write_text('{}',encoding='utf-8')
    backend=QuantBackend(ResourceCatalog(research['manifest']),research['config'])
    with pytest.raises(Denied,match='ARTIFACT_FINGERPRINT_MISMATCH'):
        backend.read_study('synthetic:history',result['study_id'],dict(task_id=task.id,session_id=app.session_id,store=app.store))
