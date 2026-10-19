"""Formal completion contract, synthetic data and the real in-process synthetic broker only."""
import hashlib
import json
from pathlib import Path
import pytest
from research_agent.data import ResourceCatalog
from research_agent.quant import QuantBackend
from research_agent.completion import finish_study, status_fields
from research_agent.security import Denied
from v1beta_fixtures import TRAIN,REVERSAL,build,broker,context

def formal(tmp_path,authorized=True):
    fx=build(tmp_path)
    cfg=json.loads(fx['config'].read_text());cfg['require_rolling_test']=True
    fx['config'].write_text(json.dumps(cfg),encoding='utf-8')
    backend=QuantBackend(ResourceCatalog(fx['manifest']),fx['config'])
    backend.rolling,b=broker(fx,authorized=authorized)
    return fx,backend,b

@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    fx,backend,b=formal(tmp_path_factory.mktemp('formal_complete'))
    result=backend.expression_study(TRAIN,REVERSAL,'短期反转','合成正式工作流',5,5,'raw',context())
    return fx,backend,result,b

def snapshot(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

def test_one_study_one_directory_one_public_report(completed):
    fx,backend,result,b=completed
    original=Path(result['factor_path']).parents[1]
    assert result['research_status']=='COMPLETED' and result['final_report_ready'] is True,result
    assert result['artifact_path']==str(original)
    assert result['html_path']==str(original/'reports/report.html')
    assert list(original.parent.iterdir())==[original]
    rev=Path(result['report_artifact_path'])
    assert rev.is_relative_to(original/'.audit/r')
    assert (original/'reports/report.html').read_bytes()==(rev/'reports/report.html').read_bytes()
    m=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    assert m['task_id']+':'+m['run_id']==result['study_id'] and m['require_rolling_test']
    versions=json.loads((original/'reports/report_versions.json').read_text(encoding='utf-8'))
    assert len(versions)==2 and versions[1]['study_id']==result['study_id']
    initial=Path(versions[0]['html'])
    assert initial.is_relative_to(original/'.audit') and initial.exists()
    assert hashlib.sha256(initial.read_bytes()).hexdigest()==versions[0]['html_sha256']
    assert result['metrics']['professional']['test']['start'].startswith('2026-')
    assert result['mode']=='synthetic'

def test_read_is_immutable_and_never_evaluates(completed,monkeypatch):
    fx,backend,result,_=completed
    from test_v1beta_stage2_access import readable,Spy
    original=readable(backend,result)
    spy=Spy(backend.rolling);monkeypatch.setattr(backend,'rolling',spy)
    before=snapshot(original)
    out=backend.read_study(TRAIN,result['study_id'],context())
    assert out['research_status']=='COMPLETED' and out['html_path']==result['html_path']
    assert spy.calls==0 and snapshot(original)==before

def test_canonical_tampering_is_not_complete(completed):
    _,backend,result,_=completed
    original=Path(result['factor_path']).parents[1]
    path=original/'reports/report.html';raw=path.read_bytes()
    try:
        path.write_bytes(raw+b'changed')
        with pytest.raises(Denied,match='FINAL_REPORT_'):
            finish_study(backend.artifacts,original,result,backend.rolling)
    finally:path.write_bytes(raw)

def test_missing_authorization_retains_intermediate_results(tmp_path):
    fx,backend,_=formal(tmp_path,authorized=False)
    result=backend.expression_study(TRAIN,REVERSAL,'短期反转','合成未授权测试',5,5,'raw',context())
    assert result['research_status']=='WAITING_TEST' and not result['final_report_ready']
    assert result['completion_reason']=='NOT_AUTHORIZED' and not result['html_path']
    original=Path(result['factor_path']).parents[1]
    assert Path(result['factor_path']).exists() and (original/'data/analysis.json').exists()
    assert len(list(original.parent.iterdir()))==1
    assert not list((tmp_path/'receipts').glob('*.json'))

def test_publication_interruption_recovers_without_another_evaluation(tmp_path,monkeypatch):
    from research_agent import completion
    fx,backend,_=formal(tmp_path)
    original_replace=completion._replace
    def fail(path,raw):
        if path.name=='report.md' and path.parent.name=='reports':raise OSError('synthetic power failure')
        return original_replace(path,raw)
    monkeypatch.setattr(completion,'_replace',fail)
    pending=backend.expression_study(TRAIN,REVERSAL,'短期反转','合成中断测试',5,5,'raw',context())
    assert pending['research_status']=='WAITING_TEST' and not pending['final_report_ready']
    original=next((fx['workspace']/'research_runs').glob('*/*'))
    result=json.loads((original/'data/analysis.json').read_text(encoding='utf-8'))
    before_receipts=snapshot(tmp_path/'receipts')
    monkeypatch.setattr(completion,'_replace',original_replace)
    out=finish_study(backend.artifacts,original,result,backend.rolling)
    assert out['final_report_ready'] and snapshot(tmp_path/'receipts')==before_receipts
    assert len(list((original/'.audit/r').iterdir()))==1

def test_formal_pending_workflow_cannot_be_completed_by_model(tmp_path):
    from test_quant_integration import research,engine
    fx=research.__wrapped__(tmp_path)
    cfg=json.loads(fx['config'].read_text());cfg['require_rolling_test']=True
    fx['config'].write_text(json.dumps(cfg),encoding='utf-8')
    app=engine(fx,tmp_path)
    state=app.run(app.create('合成研究：完整三阶段').id)
    assert state.status=='WAITING_TEST',state.error
    assert state.experiments and state.result['artifact_path']
    m=json.loads((Path(state.result['artifact_path'])/'manifest.json').read_text(encoding='utf-8'))
    assert m['task_status']=='WAITING_TEST'

@pytest.mark.parametrize('reason,status',[('FAILED','BLOCKED_TEST'),('TEST_RECEIPT_UNVERIFIED','BLOCKED_TEST'),
    ('EVALUATOR_UNAVAILABLE','WAITING_TEST'),('NOT_AUTHORIZED','WAITING_TEST')])
def test_failure_categories_are_honest(reason,status):
    out=status_fields({'artifact_path':'intermediate'},reason)
    assert out['research_status']==status and not out['final_report_ready'] and not out['html_path']
