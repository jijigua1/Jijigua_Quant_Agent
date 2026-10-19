"""General research regression: preserve definitions, empirical limits, custom algorithms."""
import json
import sys
import uuid
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from research_agent.factor_expression import inspect,compute
from research_agent.contracts import validate,canonical
from research_agent.quant import QuantBackend
from research_agent.data import ResourceCatalog
from research_agent.definition_gate import ValidationPassed
from research_agent.security import Denied
from research_agent.llm import ModelResponse,ToolCall,Role
from research_agent.providers.mock import MockProvider
from v1beta_fixtures import TRAIN,VALID,build,broker,context


def expression(window=60,skip=5):
 return dict(nodes=[dict(op='field',field='close'),dict(op='returns',args=[0],window=window),dict(op='delay',args=[1],window=skip)],output=2)

@pytest.mark.parametrize('window,skip,horizon',[(60,5,20),(252,21,60),(500,60,120)])
def test_long_parameters_are_preserved_and_feasibility_uses_actual_data(tmp_path,window,skip,horizon):
 fx=build(tmp_path);b=QuantBackend(ResourceCatalog(fx['manifest']),fx['config'])
 args=dict(resource_id=TRAIN,expression=expression(window,skip),hypothesis='h',reason='r',horizon=horizon,n_groups=10,standardization='zscore')
 validate(args,b.registry()._tools['qrtk_expression_study'].input_schema)
 events=[]
 with pytest.raises(ValidationPassed): b.expression_study(**args,_task_context=context(events=events)|{'validate_only':True})
 sample=next(v for k,v in events if k=='RESEARCH_SAMPLE_CHECK')
 assert sample['observed_dates']>900 and sample['required_history']==window+skip and sample['horizon']==horizon
 p=pd.DataFrame(np.exp(np.arange(700)*.001),index=pd.bdate_range('2020-01-01',periods=700))
 pd.testing.assert_frame_equal(compute(args['expression'],{'close':p}),p.shift(skip)/p.shift(window+skip)-1)


def test_impossible_history_has_measured_evidence_and_writes_no_report(tmp_path):
 fx=build(tmp_path);b=QuantBackend(ResourceCatalog(fx['manifest']),fx['config']);events=[]
 with pytest.raises(Denied,match='INSUFFICIENT_RESEARCH_SAMPLE'):
  b.expression_study(TRAIN,expression(2000,5),'h','r',20,5,'raw',context(events=events))
 e=next(v for k,v in events if k=='RESEARCH_SAMPLE_CHECK')
 assert e['required_history']==2005 and e['potential_mature_dates']==0
 assert not list((fx['workspace']/'research_runs').glob('*'))


def test_long_horizon_three_stage_report_preserves_definition_and_maturity(tmp_path):
 fx=build(tmp_path,snapshot_warmup=400);b=QuantBackend(ResourceCatalog(fx['manifest']),fx['config']);b.rolling,_=broker(fx)
 result=b.expression_study(TRAIN,expression(252,21),'h','r',20,10,'zscore',context(),factor_name='long_history')
 assert result['rolling_test']['status']=='COMPLETED',result.get('rolling_test')
 assert result['parameters']['horizon']==20 and result['parameters']['n_groups']==10
 assert result['parameters']['lookback']==273
 test=result['metrics']['professional']['test'];assert test['status']=='COMPLETED'
 import csv
 annual=list(csv.DictReader((Path(result['report_artifact_path'])/'data/evaluation_annual.csv').open()))
 assert sorted({int(r['period']) for r in annual})==list(range(2020,2027))
 assert Path(result['factor_path']).exists() and Path(result['html_path']).exists()

CONTRACT=dict(formula='log(close / delay(close,21))',inputs=['close'],warmup=21,
 time_semantics='Use only values observed at or before close of row t.',missing_semantics='Missing or nonpositive endpoints produce NaN.',
 steps=['For each stock take log of close at t divided by close at t-21.'])
SOURCE="""import numpy as np
def compute(panels):
 p=panels['close']
 return np.log(p/p.shift(21)).where((p>0)&(p.shift(21)>0))
"""
REFERENCE="""import numpy as np
import pandas as pd
def compute(panels):
 p=panels['close'];out=p* np.nan
 for j in range(len(p.columns)):
  for t in range(21,len(p)):
   a=p.iloc[t,j];b=p.iloc[t-21,j]
   if np.isfinite(a) and np.isfinite(b) and a>0 and b>0:out.iloc[t,j]=np.log(a/b)
 return out
"""

class CustomProvider(MockProvider):
 def __init__(self,invalid_first=False):super().__init__();self.selected=0;self.invalid_first=invalid_first
 def complete(self,request):
  system=request.messages[0].content
  if 'Write an independent,' in system:return ModelResponse(canonical(dict(source=REFERENCE,explanation='literal',unresolved=[])))
  if 'Implement the confirmed factor contract' in system:return ModelResponse(canonical(dict(source=SOURCE,explanation='vectorized',unresolved=[])))
  if request.tools:
   self.selected+=1
   args=dict(resource_id=TRAIN,contract=CONTRACT,hypothesis='log momentum',reason='user exact definition',horizon=20,n_groups=5,standardization='raw',factor_name='log_momentum')
   if self.invalid_first and self.selected==1:
    return ModelResponse(tool_calls=(ToolCall('bad','qrtk_expression_study',dict(resource_id=TRAIN,expression={'nodes':[{'op':'log','args':[0]}],'output':0},hypothesis='h',reason='r',horizon=20,n_groups=5,standardization='raw')),))
   return ModelResponse(tool_calls=(ToolCall('custom','qrtk_algorithm_study',args),))
  done=any(m.role==Role.TOOL and 'study_id' in m.content for m in request.messages)
  if request.output_schema and 'hypothesis' in request.output_schema.get('properties',{}):
   return ModelResponse(canonical(dict(action='complete' if done else 'continue',hypothesis='log momentum',change_reason='same definition',summary='实际计算已完成' if done else '实现原始定义',definition_change='')))
  # Optional rationale is deliberately unavailable; computation cannot invent metrics from it.
  return ModelResponse('{}')

@pytest.mark.skipif(sys.platform != 'linux', reason='requires real Linux numerical isolation')
@pytest.mark.parametrize('invalid_first',[False,True])
def test_direct_custom_algorithm_and_parameter_repair_finish_without_reconfirmation(tmp_path,invalid_first,monkeypatch):
 from research_agent.app import build as build_app
 fx=build(tmp_path)
 provider=CustomProvider(invalid_first)
 app=build_app(tmp_path/'state',provider=provider,profile='development',skill_id='factor_research',resources_manifest=fx['manifest'],research_config=fx['config'])
 # Independent numerical workers actually run; only the model responses are fixtures.
 task=app.run(app.create('Compute log(close[t]/close[t-21]), horizon20, raw,5groups. Missing/nonpositive endpoints NaN.').id)
 assert task.status=='COMPLETED',(task.error,app.store.events(task.id)[-4:])
 result=next(e['result']['data'] for e in task.experiments if e['tool']=='qrtk_algorithm_study')
 definition=json.loads((Path(result['artifact_path'])/'code/factor_definition.json').read_text())
 assert definition['kind']=='isolated_python' and definition['bundle']['validation']['passed']
 assert result['parameters']['horizon']==20
 assert not any(e['kind']=='DEFINITION_CHANGE_HELD' for e in app.store.events(task.id))
 assert sum(e['kind']=='TOOL_PARAMETER_REPAIR' for e in app.store.events(task.id))==int(invalid_first)


def test_new_workspace_accepts_only_operator_registered_legacy_roots(tmp_path):
 from research_agent.artifacts import ResearchArtifacts
 old=tmp_path/'old';new=tmp_path/'ver1.0';foreign=tmp_path/'foreign'
 for p in (old,new,foreign):(p/'research_runs').mkdir(parents=True)
 old_art=ResearchArtifacts(old);_,run=old_art.create('a'*32)
 art=ResearchArtifacts(new,legacy_roots=[old]);assert art.checked_run(run)==run
 _,fresh=art.create('b'*32);assert str(new) in str(fresh)
 with pytest.raises(Denied):ResearchArtifacts(new).checked_run(run)
 with pytest.raises(Denied):art.checked_run(foreign/'research_runs')


@pytest.mark.parametrize('changes',[
 {'formula':'factor=close/lag(close,21)-1; label=open[t+21]/open[t+1]-1'},
 {'steps':['计算因子','输出PKL和报告']},
 {'time_semantics':'按每只股票有效交易日序列回溯21日'}])
def test_contract_scope_errors_are_repairable_before_model_or_market_computation(changes):
 from research_agent.algorithm_research import validate_factor_contract
 from research_agent.security import InvalidParameters
 with pytest.raises(InvalidParameters) as error:validate_factor_contract(CONTRACT|changes)
 assert error.value.violations[0]['instruction']


def test_intrinsic_cross_sectional_operator_remains_a_valid_factor():
 from research_agent.algorithm_research import validate_factor_contract
 validate_factor_contract(CONTRACT|{'formula':'zscore(log(close / delay(close,21)))'})


def test_independent_reference_execution_error_repairs_without_seeing_candidate(tmp_path,monkeypatch):
 from paper_agent.autonomous_route import build as build_algorithm
 from paper_agent.ledger import TaskLedger
 from paper_agent.isolated_execution import IsolationError
 import paper_agent.autonomous_route as route
 import paper_agent.isolated_execution as isolation
 import paper_agent.autonomous_algorithm as algorithm
 calls=[]; attempts=[]
 def model(*a,**kw):
  calls.append(kw)
  return dict(source='broken' if len(calls)==1 else 'fixed',explanation='',unresolved=[]),{}
 def execute(source,panels,**kw):
  attempts.append(source)
  if source=='broken':raise IsolationError('INVALID_WORKER_OUTPUT')
  return next(iter(panels.values()))
 def develop(contract,fixtures,*a,**kw):
  assert all(f['expected'] is not None for f in fixtures if not f.get('performance_only'))
  performance=next(f for f in fixtures if f.get('performance_only'))
  assert next(iter(performance['panels'].values())).shape==(1455,5427)
  assert performance['timeout']==30
  return {'status':'VALIDATION_FAILED'}
 monkeypatch.setattr(route,'ask_json',model);monkeypatch.setattr(isolation,'execute',execute);monkeypatch.setattr(algorithm,'develop',develop)
 with pytest.raises(ValueError,match='AUTONOMOUS_ALGORITHM_VALIDATION_FAILED'):
  build_algorithm({'autonomous_contract':CONTRACT|{'citations':[{'passage':'USER_REQUEST','quote':'test'}],'unresolved':[]}},None,TaskLedger(tmp_path,goal='test'))
 assert len(calls)==2 and 'INVALID_WORKER_OUTPUT' in calls[1]['user']
 assert attempts==['broken','fixed','fixed','fixed']


@pytest.mark.parametrize('semantics',[
 'Align on the published grid without dropping per-stock missing rows.',
 'Missing rows are preserved and never compressed into nonmissing-observation offsets.',
 '不删除缺失行，不压缩个股有效交易日序列。'])
def test_negative_date_axis_instructions_are_not_misread_as_compression(semantics):
 from research_agent.algorithm_research import validate_factor_contract
 validate_factor_contract(CONTRACT|{'time_semantics':semantics,'steps':[semantics]})



def test_slow_algorithm_gets_actionable_synthetic_performance_feedback():
 from paper_agent.autonomous_algorithm import validate_candidate
 from paper_agent.isolated_execution import IsolationError
 panel=pd.DataFrame(np.ones((20,512)),index=pd.bdate_range('2020-01-01',periods=20))
 def slow(*a,**kw):
  assert kw['timeout']==6 and kw['memory_bytes']==8*1024**3
  raise IsolationError('EXECUTION_TIMEOUT')
 result=validate_candidate('source',[dict(name='wide',data_class='synthetic',oracle_basis='performance only',panels={'close':panel},performance_only=True,timeout=6)],runner=slow)
 assert not result['passed'] and result['failures'][0]['code']=='SYNTHETIC_PERFORMANCE_FAILED'
 assert 'do not shorten history' in result['failures'][0]['instruction']


def test_evidence_repair_offers_only_exact_spans_without_normalizing_minus():
 from types import SimpleNamespace
 from paper_agent.autonomous_route import verbatim_repair_options
 text='estimated from data in year y\x051 and known to investors at the beginning of year y'
 evidence=SimpleNamespace(by_id={'P0001':{'text':text}})
 bad=[{'passage':'P0001','quote':text.replace('\x05',' ')}]
 options=verbatim_repair_options(evidence,bad)
 assert options and all(o['quote'] in text for o in options)
 assert all(o['quote']!=bad[0]['quote'] for o in options)
 assert any('known to investors' in o['quote'] for o in options)
 assert verbatim_repair_options(evidence,[{'passage':'FAKE','quote':'invented'}])==[]


def test_paper_evaluation_settings_are_not_mistaken_for_formula_parameters():
 from research_agent.paper_tools import user_parameters,user_evaluation_parameters,apply_evaluation_parameters
 text='N=63；预测未来20日收益，lag=1，horizon=20，n_groups=10'
 assert user_parameters(text)=={'N':63}
 values=user_evaluation_parameters(text)
 assert values=={'label_lag':1,'horizon':20,'n_groups':10}
 plan={'status':'AWAITING_USER_DECISION','definition_sha256':'a'*64,'choices':{'horizon':{'n':1}},'hard_stops':[]}
 out=apply_evaluation_parameters(plan,values)
 assert out['choices']['horizon']['n']==20 and out['choices']['n_groups']==10
 assert plan['choices']['horizon']['n']==1
 assert apply_evaluation_parameters(plan|{'choices':None},{'label_lag':1})['choices']['label_lag']==1
 assert out['definition_sha256']!=plan['definition_sha256']
 assert apply_evaluation_parameters(plan,{'label_lag':2})['hard_stops'][-1]['code']=='EVALUATION_PARAMETERS_INVALID'
 assert user_parameters('公式参数 lag=3')=={'lag':3}
