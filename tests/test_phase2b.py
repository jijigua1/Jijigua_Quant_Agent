import json
import hashlib
from pathlib import Path
import pytest
import pandas as pd

from test_quant_integration import research,QuantProvider,args,engine
from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ToolCall,Usage,ModelResponse,ModelError
from research_agent.factor_expression import compute
from research_agent.security import Denied
from research_agent.data import ResourceCatalog

def reversal(window):
    return dict(nodes=[dict(op='field',field='close'),dict(op='returns',args=[0],window=window),dict(op='neg',args=[1])],output=2)

def expression_args(**kw):
    return dict(resource_id='synthetic:history',expression=reversal(5),hypothesis='反转预测假设',reason='自然语言构造',
        horizon=5,n_groups=5,standardization='raw')|kw

def test_expression_real_handler_reports_manifest_and_reproduction(research,tmp_path):
    app=engine(research,tmp_path,QuantProvider(ToolCall('newfactor','qrtk_expression_study',expression_args())))
    events=[];task=app.run(app.create('研究反转 <script>alert(1)</script>').id,notify=events.append)
    assert task.status=='COMPLETED',task.error
    result=task.experiments[0]['result']['data'];run=Path(result['artifact_path'])
    assert result['parameters']['definition']['formula']=='neg(returns(close,5))'
    assert result['holdout']['independent_blind'] is False and not result['formal_backtest_ready']
    # Seven base plots plus seven professional/interactive export artifacts.
    assert len(result['figure_paths'])==14 and all(Path(p).is_file() for p in result['figure_paths']) and Path(result['html_path']).is_file()
    html=Path(result['html_path']).read_text(encoding='utf-8')
    assert '<script>alert' not in html and '&lt;script&gt;' in html and html.count('data:image/png;base64,')==14
    assert 'class="metrics-table"' in html and 'overflow-wrap:anywhere' in html
    assert '不是全系统盲测' in Path(result['report_path']).read_text(encoding='utf-8')
    assert (run/'logs/stages.json').is_file()
    series=pd.read_csv(run/'data/ic_rankic.csv',index_col=0,parse_dates=True)
    for split in ('train','valid'):
        values=series.loc[series['split']==split]
        for column,key in [('ic','ic'),('rank_ic','rank_ic')]:
            stats=result['splits'][split]['predictive'][key]
            assert values[column].count()==stats['n_dates']
            assert values[column].mean()==pytest.approx(stats['mean'])
        assert series.index.max()<=pd.Timestamp(result['spec']['valid'][1])
    assert any(isinstance(x,dict) and x.get('total')==14 and x.get('completed')==14 for x in events)
    assert not any('nav' in p.name.lower() for p in (run/'figures').iterdir())
    saved=pd.read_csv(run/'data/factor_values.csv',index_col=0,parse_dates=True)
    expected=compute(reversal(5),{'close':research['close']}).loc[saved.index]
    pd.testing.assert_frame_equal(saved,expected,check_names=False,check_freq=False)
    for f in json.loads((run/'manifest.json').read_text(encoding='utf-8'))['files']:
        assert hashlib.sha256((run/f['path']).read_bytes()).hexdigest()==f['sha256']

def test_parameter_change_new_experiment_with_parent(research,tmp_path):
    provider=QuantProvider()
    chat=build_chat(tmp_path/'state',provider=provider,profile='development',resources_manifest=research['manifest'],research_config=research['config'])
    chat.turn('五日反转')
    oldtask=chat.store.load(chat.store.session_turns(chat.session_id)[-1]['research_task_id'])
    old=oldtask.experiments[0]['result']['data'];before=Path(old['report_path']).read_bytes()
    provider.call=ToolCall('new','qrtk_expression_study',expression_args(expression=reversal(10),parent_study_id=old['study_id']))
    reply=chat.turn('换十日窗口')
    task=chat.store.load(chat.store.session_turns(chat.session_id)[-1]['research_task_id'])
    assert task.status=='COMPLETED',task.error
    new=task.experiments[0]['result']['data']
    assert new['comparison']['parent_study_id']==old['study_id']
    assert new['study_id']!=old['study_id'] and Path(old['report_path']).read_bytes()==before
    assert not new['comparison']['independent_test'] and 'HTML报告：' in reply
    # Executed formula remains auditable in artifacts, without dense raw DSL in chat.
    assert new['parameters']['definition']['formula']=='neg(returns(close,10))'
    assert (Path(new['artifact_path'])/'code/factor_formula.tex').is_file()

@pytest.mark.parametrize('change',[{'expression':{'nodes':[{'op':'field','field':'next_open'}],'output':0}},
    {'parent_study_id':'../secret'},{'shell':'rm -rf /'}, {'expression':{'nodes':[{'op':'delay','args':[0],'window':-1}],'output':0}}])
def test_expression_unsafe_requests_denied(research,tmp_path,change):
    app=engine(research,tmp_path,QuantProvider(ToolCall('bad','qrtk_expression_study',expression_args(**change))))
    task=app.run(app.create('bad').id)
    assert task.status=='INVALID_PARAMETERS' and not task.experiments

def test_holdout_gate_covers_aliases_and_actual_file_contents(research,tmp_path):
    value=json.loads(research['manifest'].read_text());value['withheld_from']='2024-01-01'
    p=tmp_path/'embargo.json';p.write_text(canonical(value))
    with pytest.raises(Denied,match='HOLDOUT_PUBLICATION_OVERLAP'):ResourceCatalog(p)
    # Lying about metadata cannot expose the embargoed rows through a renamed resource.
    value['resources'][0]['id']='synthetic:alias';value['resources'][0]['end_date']='2023-12-29'
    p.write_text(canonical(value));catalog=ResourceCatalog(p)
    with pytest.raises(Denied,match='HOLDOUT_DATA_ACCESS_DENIED'):catalog.describe_resource('synthetic:alias')

def test_token_limit_prevents_call_and_unknown_usage_reserved(app):
    app.token_limit=1
    task=app.run(app.create('mock').id)
    assert task.status=='BUDGET_EXHAUSTED' and task.counters['model_calls']==0

def test_progress_failure_does_not_fake_completion(research,tmp_path):
    app=engine(research,tmp_path,QuantProvider(ToolCall('x','qrtk_expression_study',expression_args(
        expression=dict(nodes=[dict(op='field',field='close'),dict(op='delay',args=[1],window=1)],output=1)))))
    events=[];task=app.run(app.create('bad cycle').id,notify=events.append)
    assert task.status=='TOOL_ERROR' and not task.experiments
