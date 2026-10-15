import hashlib,json,pickle
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from research_agent.factor_export import panel,server_panel,export,verify
from research_agent.research_metrics import hac_mean
from research_agent.security import Denied
from research_agent.llm import ToolCall
from test_quant_integration import research,engine,QuantProvider,args
from test_phase2b import expression_args
from fixtures.server_factor_readers import norm_index,load_and_pivot_factors

def test_server_contract_nan_exact_and_dictionary(tmp_path):
    (tmp_path/'data').mkdir()
    f=pd.DataFrame({'000001':[1.25,np.nan],'000002':[2.,3.5]},index=pd.date_range('2024-01-01',periods=2))
    p=dict(parameters={'factor_id':'reversal'},data_sha256='a'*64,research_contract={'available_time':'T close'})
    result=export(tmp_path,f,{'lookback':5},p);x=server_panel(f)
    assert result['delivery_status']=='VERIFIED' and x.index.tolist()==['20240101','20240102']
    pd.testing.assert_frame_equal(verify(tmp_path/'data/factor.pkl',x),x,check_exact=True)
    pd.testing.assert_frame_equal(pd.read_pickle(tmp_path/'data/factor.pkl.zip'),x,check_exact=True)
    # Original public contract probes; historical third-party consumer code is quarantined for licensing.
    pd.testing.assert_frame_equal(norm_index(pd.read_pickle(tmp_path/'data/factor.pkl')),panel(f),check_exact=True)
    daily=load_and_pivot_factors(tmp_path/'data/factor_dict.pkl')
    assert list(daily)==['20240101','20240102'] and np.isnan(daily['20240102'].loc['000001.SZ','reversal'])
    assert daily['20240101'].loc['000002.SZ','reversal']==2.
    for record in result['factor_export']['files']:assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256']
    with pytest.raises(Denied,match='ALREADY_EXISTS'):export(tmp_path,f,{},p)

def test_unknown_pickle_refused_before_any_load(tmp_path,monkeypatch):
    frame=pd.DataFrame({'000001':[1.]},index=pd.date_range('2024-01-01',periods=1))
    p=tmp_path/'evil.pkl';p.write_bytes(pickle.dumps({'unexpected':'object'}))
    monkeypatch.setattr(pickle,'loads',lambda _:pytest.fail('untrusted deserialization'))
    with pytest.raises(Denied,match='UNTRUSTED'):verify(p,panel(frame))

@pytest.mark.parametrize('change',['infinite','code','duplicate','intraday','unsorted'])
def test_factor_contract_rejects_bad_inputs(change):
    f=pd.DataFrame({'000001':[1.,2.]},index=pd.date_range('2024-01-01',periods=2))
    if change=='infinite':f.iloc[0,0]=np.inf
    if change=='code':f.columns=['000001.SZ']
    if change=='duplicate':f.index=[f.index[0]]*2
    if change=='intraday':f.index=f.index+pd.Timedelta(hours=12)
    if change=='unsorted':f=f.iloc[::-1]
    with pytest.raises(ValueError):panel(f)

def test_hac_hand_baseline_and_short_gate():
    x=np.tile([-.1,.1],50);h=hac_mean(x,1);n=len(x);y=x-x.mean()
    bandwidth=h['lags'];v=sum(float(z*z) for z in y)/n
    for k in range(1,bandwidth+1):v+=2*(1-k/(bandwidth+1))*sum(float(y[i]*y[i-k]) for i in range(k,n))/n
    assert h['se']==pytest.approx(np.sqrt(v/n)) and h['ci_high']==pytest.approx(1.95996398454*h['se'])
    assert hac_mean(x[:15],5)['status']=='insufficient'
    assert hac_mean(np.zeros(100),1)['status']=='unsupported'
    x[0]=np.nan;h=hac_mean(x,5);assert h['status']=='insufficient' and h['n']==100 and h['n_valid']==99

def test_ledger_aggregates_results_without_expanding_model_json_limit(tmp_path):
    from research_agent.store import TaskStore,TaskState
    from research_agent.security import Authorization,Budget
    from research_agent.contracts import canonical,ContractError
    t=TaskState('a'*32,'research','binding','mock','mock','mock','hash',{})
    t.experiments=[{'result':{'summary':'x'*35000}}]*2
    with pytest.raises(ContractError,match='size limit'):canonical(t.experiments)
    s=TaskStore(tmp_path/'state');s.create(t,Authorization(t.id,'p','s',(),(),Budget(),'test'))
    assert s.load(t.id).experiments==t.experiments
    s.save(t,'AGGREGATED_RESULTS',t.experiments)
    assert s.events(t.id)[-1]['payload']==t.experiments
    t.messages=[{'content':'x'*(1024*1024)}]
    with pytest.raises(ContractError,match='size limit'):s.save(t,'OVERSIZE',{})
    assert s.load(t.id).revision==1

def test_autocorrelation_independent_pairs_and_future_prefix(research,tmp_path):
    app=engine(research,tmp_path)
    t=app.run(app.create('factor').id);r=t.experiments[0]['result']['data'];run=Path(r['artifact_path'])
    f=pd.read_csv(run/'data/factor_values.csv',index_col=0,parse_dates=True,float_precision='round_trip')
    source=pd.read_csv(run/'data/input_slice.csv',dtype={'Stkcd':str},parse_dates=['Trddt'])
    p=source.pivot(index='Trddt',columns='Stkcd',values='Opnprc').reindex_like(f)
    v=source.pivot(index='Trddt',columns='Stkcd',values='Dnshrtrd').reindex_like(f)
    eligible=f.where(p.notna()&v.gt(0));rows=pd.read_csv(run/'data/factor_autocorrelation.csv',parse_dates=['date'])
    for row in rows.itertuples():
        i=f.index.get_loc(row.date);lag=row.lag
        if i<lag:assert np.isnan(row.autocorrelation);continue
        a=eligible.iloc[i].to_numpy();b=eligible.iloc[i-lag].to_numpy();both=np.isfinite(a)&np.isfinite(b)
        assert row.n_pairs==both.sum()
        if both.sum()<10 or np.ptp(a[both])==0 or np.ptp(b[both])==0:assert np.isnan(row.autocorrelation);continue
        assert row.autocorrelation==pytest.approx(np.corrcoef(a[both],b[both])[0,1])
        ra=pd.Series(a[both]).rank().to_numpy();rb=pd.Series(b[both]).rank().to_numpy()
        assert row.rank_autocorrelation==pytest.approx(np.corrcoef(ra,rb)[0,1])
    from research_agent.factor_expression import compute
    from test_phase2b import reversal
    close=research['close'].copy();cut=40;original=compute(reversal(5),{'close':close}).iloc[:cut]
    close.iloc[cut:]*=10000
    pd.testing.assert_frame_equal(compute(reversal(5),{'close':close}).iloc[:cut],original)

def test_fixed_factor_parameter_change_uses_same_parent_contract(research,tmp_path):
    from research_agent.app import build_chat
    provider=QuantProvider()
    chat=build_chat(tmp_path/'state',provider=provider,profile='development',resources_manifest=research['manifest'],research_config=research['config'])
    chat.turn('five days');t=chat.store.load(chat.store.session_turns(chat.session_id)[-1]['research_task_id'])
    old=t.experiments[0]['result']['data'];before=Path(old['factor_path']).read_bytes()
    provider.call=ToolCall('changed','qrtk_factor_study',args(lookback=10,parent_study_id=old['study_id']))
    chat.turn('ten days and compare');t=chat.store.load(chat.store.session_turns(chat.session_id)[-1]['research_task_id'])
    assert t.status=='COMPLETED',t.error
    new=t.experiments[0]['result']['data']
    assert new['comparison']['parent_study_id']==old['study_id'] and new['delivery_status']=='VERIFIED'
    assert Path(new['factor_path']).read_bytes()!=before and Path(old['factor_path']).read_bytes()==before
    assert (Path(new['artifact_path'])/'data/experiment_comparison.csv').exists()

@pytest.mark.parametrize('tool,arguments',[('qrtk_export_factor',{'study_id':'../private'}),
    ('qrtk_export_factor',{'study_id':'a'*32+':'+'b'*16,'path':'/etc/passwd'}),('forged_pickle_loader',{})])
def test_export_path_escalation_and_forged_tool_denied(research,tmp_path,tool,arguments):
    app=engine(research,tmp_path,QuantProvider(ToolCall('bad',tool,dict(resource_id='synthetic:history',**arguments))))
    t=app.run(app.create('unauthorized').id)
    expected='INVALID_PARAMETERS' if tool=='qrtk_export_factor' else 'AUTHORIZATION_DENIED'
    assert t.status==expected and not t.experiments

def test_default_export_and_metric_table_csv_consistency(research,tmp_path):
    app=engine(research,tmp_path,QuantProvider(ToolCall('x','qrtk_expression_study',expression_args())))
    t=app.run(app.create('compute only; no export request').id);assert t.status=='COMPLETED',t.error
    r=t.experiments[0]['result']['data'];run=Path(r['artifact_path'])
    f=pd.read_csv(run/'data/factor_values.csv',index_col=0,parse_dates=True,float_precision='round_trip')
    pd.testing.assert_frame_equal(verify(run/'data/factor.pkl',panel(f)),panel(f),check_exact=True)
    m=r['metrics'];values=f.to_numpy().ravel();v=pd.Series(values[np.isfinite(values)])
    from research_agent import __version__
    assert r['factor_export']['core_version']==__version__ and len(r['factor_export']['writer_sha256'])==64
    assert r['implementation_sha256'] in Path(r['html_path']).read_text(encoding='utf-8')
    for name in ('mean','std','skew'):assert m['distribution'][name]==pytest.approx(getattr(v,name)())
    assert m['distribution']['excess_kurtosis']==pytest.approx(v.kurt())
    assert m['distribution']['coverage']==pytest.approx(np.isfinite(values).mean())
    stats=pd.read_csv(run/'data/factor_stability.csv')
    for row in m['stability']:
        s=stats[(stats.split==row['split'])&(stats.lag==row['lag'])].iloc[0]
        assert s.correlation==pytest.approx(row['correlation'])
    tables=json.loads((run/'data/report_tables.json').read_text(encoding='utf-8'))
    core=next(x for x in tables if x['id']=='core')
    assert len(core['values']) == 6
    for row in core['values']:
        if row[0] in ('train','valid'):
            assert row[2]==r['splits'][row[0]]['predictive'][row[1]]['mean']
        else:
            assert row[0] == 'Test / NOT_RUN / SEALED' and row[1] in ('ic','rank_ic')
            assert row[2:] == [None,None,None,None]
    assert not any('nav' in x.name for x in (run/'figures').iterdir())
    # Re-export existing experiment reads fixed CSV and verifies PKL; no new factor/model call.
    ctx=dict(task_id=t.id,session_id=t.session_id,store=app.store)
    from research_agent.quant import QuantBackend
    from research_agent.data import ResourceCatalog
    b=QuantBackend(ResourceCatalog(research['manifest']),research['config'])
    before=(run/'manifest.json').read_bytes();out=b.export_factor('synthetic:history',r['study_id'],ctx)
    assert out['factor_path']==r['factor_path'] and (run/'manifest.json').read_bytes()==before

def test_export_failure_preserves_result_and_is_not_completed(research,tmp_path,monkeypatch):
    import research_agent.factor_export as module
    monkeypatch.setattr(module,'verify',lambda *a: (_ for _ in ()).throw(ValueError('verification failed')))
    app=engine(research,tmp_path);t=app.run(app.create('factor research').id)
    assert t.status=='EXPORT_FAILED' and t.error['code']=='FACTOR_EXPORT_FAILED'
    runs=[p.parent for p in (research['workspace']/'research_runs').glob('*/*/manifest.json') if json.loads(p.read_text())['task_id']==t.id];assert len(runs)==1
    r=runs[0];m=json.loads((r/'manifest.json').read_text())
    assert m['task_status']=='EXPORT_FAILED' and m['computation_status']=='COMPLETED'
    assert (r/'data/factor_values.csv').is_file() and (r/'data/analysis.json').is_file()

def test_constant_factor_keeps_pkl_but_marks_undefined_statistics(research,tmp_path):
    call=ToolCall('constant','qrtk_expression_study',expression_args(expression={'nodes':[{'op':'field','field':'close'},{'op':'div','args':[0,0]}],'output':1}))
    app=engine(research,tmp_path,QuantProvider(call));t=app.run(app.create('constant diagnostic').id)
    assert t.status=='COMPLETED',t.error
    r=t.experiments[0]['result']['data'];d=r['metrics']['distribution']
    assert d['std']==0 and d['skew'] is None and d['excess_kurtosis'] is None
    assert r['metrics']['direction_consistent'] is None and r['delivery_status']=='VERIFIED'
    assert not any(Path(p).stem in {'ic_rankic','ic_distribution','ic_decay','factor_autocorrelation'} for p in r['figure_paths'])
    assert '尚无法判断方向一致性' in Path(r['html_path']).read_text(encoding='utf-8')

def test_repair_failed_export_creates_new_run_without_factor_recalculation(research,tmp_path,monkeypatch):
    import research_agent.factor_export as module
    original=module.verify
    monkeypatch.setattr(module,'verify',lambda *a: (_ for _ in ()).throw(ValueError('fail once')))
    app=engine(research,tmp_path);t=app.run(app.create('research').id)
    old=next(p.parent for p in (research['workspace']/'research_runs').glob('*/*/manifest.json') if json.loads(p.read_text())['task_id']==t.id);before=(old/'data/factor_values.csv').read_bytes()
    monkeypatch.setattr(module,'verify',original)
    from research_agent.quant import QuantBackend
    from research_agent.data import ResourceCatalog
    backend=QuantBackend(ResourceCatalog(research['manifest']),research['config'])
    repair=app.create('repair export')
    ctx=dict(task_id=repair.id,session_id=t.session_id,store=app.store,provider={},core_code_sha256='a'*64,goal='repair',emit=lambda *a:None)
    # The same session may retrieve its failed task, with ARTIFACT_CREATED as trusted evidence.
    app.store.create_session({'id':t.session_id})
    app.store.save_session({'id':t.session_id,'revision':0,'turn_count':1},dict(turn=1,research_task_id=t.id,route_task_id=None))
    old_id=t.id+':'+json.loads((old/'manifest.json').read_text())['run_id']
    out=backend.export_factor('synthetic:history',old_id,ctx)
    assert out['delivery_status']=='VERIFIED' and out['study_id']!=old_id
    assert (old/'data/factor_values.csv').read_bytes()==before
    assert (Path(out['artifact_path'])/'data/factor_values.csv').read_bytes()==before
