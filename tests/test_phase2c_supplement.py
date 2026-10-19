import base64,json,re
from datetime import datetime as RealDateTime
from pathlib import Path
import pytest
from research_agent.artifacts import ResearchArtifacts
from research_agent.factor_math import formula,render
from research_agent.security import Denied
from test_quant_integration import research,engine

def test_directory_collision_names_timezone_and_safety(tmp_path,monkeypatch):
    import research_agent.artifacts as module
    class Clock:
        @staticmethod
        def now(tz):return RealDateTime(2026,10,12,12,21,5,tzinfo=tz)
    monkeypatch.setattr(module,'datetime',Clock)
    (tmp_path/'research_runs').mkdir();a=ResearchArtifacts(tmp_path)
    sid,p=a.create('a'*32,'volume_stall_5d');other,q=a.create('b'*32,'volume_stall_5d')
    assert p.parent.name=='2026-10-12' and p.name=='12-21-05_volume_stall_5d'
    assert q!=p and q.name.startswith(p.name+'_') and sid!=other
    for name in ['../escape','/etc','x;rm','中','a'*49]:
        with pytest.raises(Denied):a.create('c'*32,name)
    with pytest.raises(Denied):a.checked_run(tmp_path)

def test_real_study_human_directory_and_historical_uuid_compatibility(research,tmp_path):
    app=engine(research,tmp_path);t=app.run(app.create('factor').id);assert t.status=='COMPLETED',t.error
    r=t.experiments[0]['result']['data'];p=Path(r['artifact_path']);m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}',p.parent.name) and re.match(r'\d{2}-\d{2}-\d{2}_reversal_5d',p.name)
    assert m['created_at'].endswith('+08:00') and m['completed_at'].endswith('+08:00')
    assert m['factor_output_cutoff']==r['spec']['valid'][1] and m['data_cutoff']==str(research['close'].index[-1].date())
    assert r['formula_rendering']['latex']==(p/'code/factor_formula.tex').read_text().strip()
    # Existing IDs use ledger paths, never a directory-name inference.
    from research_agent.quant import QuantBackend
    from research_agent.data import ResourceCatalog
    b=QuantBackend(ResourceCatalog(research['manifest']),research['config']);ctx=dict(task_id=t.id,session_id=t.session_id,store=app.store)
    assert b.read_study('synthetic:history',r['study_id'],ctx)['artifact_path']==str(p)
    legacy=p.parents[1]/t.id/r['study_id'].split(':')[1];legacy.parent.mkdir();p.rename(legacy)
    data=t.experiments[0]['result']['data'];data['artifact_path']=str(legacy);app.store.save(t,'LEGACY_FIXTURE',{})
    assert b.artifacts.locate(r['study_id'],ctx)[0]==legacy

@pytest.mark.parametrize('kind',['reversal','volume_stall','expression'])
def test_offline_math_true_svg_and_ast(kind):
    if kind=='expression':d={'expression':{'nodes':[{'op':'field','field':'close'},{'op':'returns','args':[0],'window':5},{'op':'rolling_std','args':[1],'window':5},{'op':'neg','args':[1]},{'op':'sub','args':[3,2]}],'output':4}}
    else:d={'factor_id':kind,'lookback':5,'standardization':'raw'}
    x=render(d);assert x['latex']==formula(d) and 'f_{t,i}' in x['latex']
    svg=base64.b64decode(x['html'].split('base64,')[1].split('"')[0]).decode()
    assert '<svg' in svg and '<path' in svg and 'script' not in svg
    if kind=='volume_stall':assert r'\sum_{k=1}^{5}V_{t-k,i}' in x['latex']
    d['formula']='<script>unsafe</script>';assert formula(d)==x['latex']

def test_math_operator_whitelist_all_supported():
    from research_agent.factor_expression import OPS
    for op in OPS:
        if op=='constant':continue
        nodes=[{'op':'field','field':'close'}]
        if op!='field':
            node={'op':op,'args':[0,0] if op in {'add','sub','mul','div','min','max','rolling_corr'} else [0]}
            if op in {'delay','diff','returns','rolling_mean','rolling_std','rolling_rank','rolling_corr'}:node['window']=5
            nodes.append(node)
        assert render({'expression':{'nodes':nodes,'output':len(nodes)-1}})['latex']

def test_terminal_cjk_wrap_preserves_path_and_controls():
    from research_agent.terminal import wrapped
    text='中文输入与输出'*12;lines=wrapped(text,24).splitlines()
    assert ''.join(lines)==text and all(len(s)<=12 for s in lines)
    path='/hy-tmp/public-agent/research_runs/2026-10-12/12-21-05_volume_stall_5d/reports/report.html'
    assert wrapped(path,24)==path and '\x1b' not in wrapped('\x1b[31mevil',24)

def test_expression_name_cannot_grant_paths_or_change_math(research,tmp_path):
    from test_quant_integration import QuantProvider
    from test_phase2b import expression_args
    from research_agent.llm import ToolCall
    app=engine(research,tmp_path,QuantProvider(ToolCall('bad','qrtk_expression_study',expression_args(factor_name='../private'))))
    t=app.run(app.create('bad name').id);assert t.status=='INVALID_PARAMETERS' and not t.experiments
    value=0.1234567890123456
    d={'expression':{'nodes':[{'op':'field','field':'close'},{'op':'constant','value':value},{'op':'mul','args':[0,1]}],'output':2}}
    assert str(value) in formula(d)
    d['expression']['nodes'][1]['value']=1e-8
    assert r'10^{-8}' in render(d)['latex']

def test_query_and_reexport_preserve_prior_artifacts(research,tmp_path):
    from research_agent.app import build_chat
    from test_quant_integration import QuantProvider
    from research_agent.llm import ToolCall
    p=QuantProvider();app=build_chat(tmp_path/'state',provider=p,profile='development',resources_manifest=research['manifest'],research_config=research['config'])
    app.turn('compute');first=app.store.load(app.store.session_turns(app.session_id)[0]['research_task_id'])
    r=first.experiments[0]['result']['data'];root=Path(r['artifact_path']);before={f.name:f.read_bytes() for f in [root/'manifest.json',root/'data/factor.pkl']}
    p.call=ToolCall('read','qrtk_export_factor',dict(resource_id='synthetic:history',study_id=r['study_id']))
    app.turn('show prior factor')
    second=app.store.load(app.store.session_turns(app.session_id)[1]['research_task_id'])
    assert second.status=='COMPLETED',second.error
    assert second.experiments[0]['result']['data']['study_id']==r['study_id']
    assert (root/'manifest.json').read_bytes()==before['manifest.json'] and (root/'data/factor.pkl').read_bytes()==before['factor.pkl']
