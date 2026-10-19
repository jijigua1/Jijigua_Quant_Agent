"""Independent P1: changing a research-writable report must not change certified Test numbers."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from research_agent.report_versions import latest_report, TEST_DAILY_SOURCE
from research_agent.security import Denied

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj),encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()

def example(root,field=None):
    sid='synthetic-binding-probe';eid='0'*32
    signed=dict(study_id=sid,evaluation_id=eid,evaluation_type='ROLLING_EXPOSED_TEST',
        maturity={'immature_signal_dates':[]},snapshot=dict(version='synthetic',certified_end='2026-03-31',manifest_sha256='a'*64,status='READY'),
        test=dict(exposure={'evaluation_id':eid},start='2026-01-02',end='2026-03-31',metrics={'rank_ic_mean':.01},
                  annual=[],monthly=[],daily=[],group_columns=[],group_definition={}))
    receipt=dict(result=signed,signature='synthetic-only-registry-copy')
    registry_sha=hashlib.sha256(json.dumps(receipt).encode()).hexdigest()
    t=signed['test']
    test=dict(status='COMPLETED',access='CONTROLLED_EVALUATOR',evaluation_type='ROLLING_EXPOSED_TEST',
        **{k:copy.deepcopy(v) for k,v in t.items() if k!='daily'},daily_rows=0,daily_source=TEST_DAILY_SOURCE,
        maturity=signed['maturity'],snapshot=signed['snapshot'],receipt_sha256=registry_sha)
    if field=='metrics':test['metrics']['rank_ic_mean']=.99
    elif field=='monthly':test['monthly']=[{'period':'2026-01','observed_dates':2,'rank_ic_n_dates':2}]
    elif field=='snapshot':test['snapshot']=dict(test['snapshot'],certified_end='2099-01-01')
    elif field=='daily_rows':test['daily_rows']=999
    elif field=='evaluation_type':test['evaluation_type']='SOME_OTHER_EVALUATION'
    elif field=='legacy_downgrade':
        receipt=copy.deepcopy(receipt)
        receipt['result'].update(evaluation_type='LEGACY_ONESHOT',research_study_id=sid)
        receipt['signature']='DELIBERATELY_INVALID'
        test['evaluation_type']='LEGACY_ONESHOT';test['metrics']['rank_ic_mean']=.99
    elif field in ('legacy_inline','legacy_inline_wrong'):
        test.pop('daily_rows');test.pop('daily_source');test['daily']=copy.deepcopy(t['daily'])
        if field=='legacy_inline_wrong':test['daily']=[{'date':'2026-01-02','rank_ic':.99}]
    original=root/'original';rev=root/'revision'
    a=save(rev/'data/analysis.json',dict(metrics={'professional':{'test':test}},figure_paths=[]))
    r=save(rev/'data/test_receipt.json',receipt)
    files=[dict(path='data/analysis.json',sha256=a),dict(path='data/test_receipt.json',sha256=r)]
    if field=='missing_receipt':files=files[:1]
    m=save(rev/'manifest.json',dict(study_id=sid,files=files))
    idx=save(original/'reports/report_versions.json',[{'revision':1},dict(revision=2,rolling_status='COMPLETED',
        artifact_path=str(rev),manifest_sha256=m,evaluation_id=eid,html='x.html',markdown='x.md')])
    save(original/'manifest.json',dict(files=[dict(path='reports/report_versions.json',sha256=idx)]))
    class Arts:
        def checked_run(self,p):return Path(p)
    class Registry:
        receipt_dir=root/'synthetic-registry'
        def load_receipt(self,*args):return receipt|dict(registry_sha256=registry_sha)
    return Arts(),original,{'study_id':sid},None if field=='legacy_downgrade' else Registry()

@pytest.mark.parametrize('representation',[None,'legacy_inline'])
def test_unchanged_registered_fields_are_read(tmp_path,representation):
    out=latest_report(*example(tmp_path,representation))
    assert out['metrics']['professional']['test']['metrics']['rank_ic_mean']==.01

@pytest.mark.parametrize('field',['metrics','monthly','snapshot','daily_rows','evaluation_type','missing_receipt','legacy_downgrade','legacy_inline_wrong'])
def test_all_local_hashes_agree_but_certified_fields_differ(tmp_path,field):
    with pytest.raises(Denied,match='REPORT_(?:RECEIPT_|LEGACY_TEST_UNVERIFIED)'):
        latest_report(*example(tmp_path,field))

def test_unverifiable_legacy_read_keeps_intermediates_and_never_claims_complete(tmp_path):
    from research_agent.quant import QuantBackend
    arts,original,identity,rolling=example(tmp_path,'legacy_downgrade')
    data=identity|dict(resource_id='synthetic:train',mode='synthetic',metrics={'professional':{'test':{'status':'NOT_EVALUATED'}}})
    evidence=dict(resource_id=data['resource_id'],analysis_sha256='0'*64,artifact_path=str(original),report_path='historical.md',report_status='incomplete')
    arts.root=tmp_path
    arts.locate=lambda *a:(original,evidence)
    arts.read_analysis=lambda *a:data
    backend=object.__new__(QuantBackend);backend.artifacts=arts;backend.rolling=rolling
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=backend.read_study(data['resource_id'],data['study_id'],{})
    assert result['research_status']=='BLOCKED_TEST' and not result['final_report_ready'] and not result['html_path']
    assert result['completion_reason']=='LEGACY_TEST_RECEIPT_UNVERIFIED'
    assert {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
