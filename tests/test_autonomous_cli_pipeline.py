"""Real conversation/tool/broker/report code, synthetic market, scripted model.

The numerical worker is genuine Linux seccomp. No live model or market evaluation.
"""
import json
import os
from pathlib import Path
import sys

import pytest

from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ModelResponse
from research_agent.paper_library import PaperLibrary
from test_v1beta_papers import PaperProvider, decision, stage, FIX, patched_rolling, paper_call
from v1beta_fixtures import build, broker

SOURCE = '''import numpy as np
import pandas as pd
def compute(panels):
 close=panels['close']
 ratio=(close/close.shift(1)-1).abs()/(panels['amount']*1000).replace(0,np.nan)
 ratio=ratio.replace([np.inf,-np.inf],np.nan)
 result=pd.DataFrame(np.nan,index=close.index,columns=close.columns)
 for year in sorted(set(close.index.year)):
  previous=ratio.loc[ratio.index.year==year-1]
  if len(previous)==0:continue
  valid=previous.notna().sum()
  value=previous.sum()/valid.replace(0,np.nan)
  result.loc[result.index.year==year]=value.to_numpy()
 return result
'''

REFERENCE = '''import numpy as np
import pandas as pd
def compute(panels):
 c=panels['close']; a=panels['amount']
 result=pd.DataFrame(np.nan,index=c.index,columns=c.columns)
 for year in sorted(set(c.index.year)):
  for col in c.columns:
   values=[]
   for i in range(1,len(c)):
    if c.index[i].year!=year-1:continue
    before=c[col].iloc[i-1];now=c[col].iloc[i];amount=a[col].iloc[i]
    if np.isfinite(before) and np.isfinite(now) and np.isfinite(amount) and before!=0 and amount!=0:
     values.append(abs(now/before-1)/(amount*1000))
   if values:result.loc[result.index.year==year,col]=sum(values)/len(values)
 return result
'''


class AutonomousProvider(PaperProvider):
    def complete(self, request):
        if paper_call(request):
            system=request.messages[0].content
            if 'Read the supplied original paper evidence' in system:
                prompt=json.loads(request.messages[-2].content)
                passage=next(p for p in prompt['passages'] if 'number of days' in p['text'])
                contract=dict(formula='previous complete calendar year mean(abs(close/lag(close,1)-1)/(amount*1000))',
                    inputs=['close','amount'],warmup=530,
                    time_semantics='上一完整日历年的值在次年使用；测试采用原始价格日收益与人民币成交额，非美元样本复现。',
                    missing_semantics='只统计有效收益且成交额非零的日期；分母是该股票有效日数；没有有效日则缺失。',
                    steps=['计算日收益绝对值除以当日成交额','按股票和完整日历年求有效观测均值','次年使用上年值'],
                    citations=[dict(passage=passage['id'],quote=passage['text'])],unresolved=[])
                return ModelResponse(canonical(contract))
            if 'Write an independent,' in system:
                return ModelResponse(canonical(dict(source=REFERENCE,explanation='scripted literal reference',unresolved=[])))
            if 'Implement the confirmed factor contract in Python' in system:
                return ModelResponse(canonical(dict(source=SOURCE,explanation='scripted calendar algorithm',unresolved=[])))
        return super().complete(request)


@pytest.mark.skipif(sys.platform!='linux' or getattr(os,'geteuid',lambda:0)()==0,
                    reason='requires real non-root Linux isolation')
def test_uploaded_calendar_paper_to_single_three_stage_report(tmp_path,patched_rolling,monkeypatch):
    from research_agent.paper_tools import PaperPipeline
    original=PaperPipeline.research
    def diagnostic(self,*a,**kw):
        try:return original(self,*a,**kw)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    monkeypatch.setattr(PaperPipeline,'research',diagnostic)
    from research_agent.artifacts import ResearchArtifacts
    finalize=ResearchArtifacts.finalize
    def diagnose_final(self,*a,**kw):
        try:return finalize(self,*a,**kw)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    monkeypatch.setattr(ResearchArtifacts,'finalize',diagnose_final)
    fx=build(tmp_path,snapshot_warmup=590)
    cfg=json.loads(fx['config'].read_text());cfg['require_rolling_test']=True
    fx['config'].write_text(json.dumps(cfg),encoding='utf-8')
    patched_rolling['client'],_=broker(fx)
    library=PaperLibrary(tmp_path/'papers')
    library.import_pdf(stage(library,FIX/'amihud2002.pdf'),'amihud2002.pdf')
    provider=AutonomousProvider([decision('skill',skill_id='paper_research',goal='研究刚上传论文的年度非流动性因子'),decision(consent='accept')])
    app=build_chat(tmp_path/'state',provider=provider,profile='development',resources_manifest=fx['manifest'],research_config=fx['config'])
    first=app.turn('研究刚上传的Amihud论文，使用原始价格与人民币成交额，先展示具体定义。')
    assert '回复“同意”' in first,first
    assert not list((fx['workspace']/'research_runs').glob('*/*'))
    response=app.turn('同意')
    assert app.store.session_turns(app.session_id)[-1]['research_task_id'],response
    task=app.store.load(app.store.session_turns(app.session_id)[-1]['research_task_id'])
    assert task.status=='COMPLETED',(response,task.error)
    result=next(e['result']['data'] for e in task.experiments if e['tool']=='qrtk_paper_research')
    assert '自主 Python 算法（独立合成数值验证通过' in response
    assert '与可信IR逐格一致' not in response
    assert result['paper']['route']=='autonomous_python'
    assert result['final_report_ready']
    run=Path(result['factor_path']).parents[1]
    assert result['html_path']==str(run/'reports/report.html')
    assert len(list(run.parent.iterdir()))==1
    assert '2026' in (run/'reports/report.html').read_text(encoding='utf-8')
    definition=json.loads((run/'code/factor_definition.json').read_text(encoding='utf-8'))
    from rolling_test.factors import frozen_from_study
    analysis=json.loads((run/'data/analysis.json').read_text(encoding='utf-8'))
    frozen=frozen_from_study(analysis,definition)
    assert frozen['definition']['bundle']['source_sha256']==definition['bundle']['source_sha256']


@pytest.mark.skipif(sys.platform!='linux' or getattr(os,'geteuid',lambda:0)()==0,
                    reason='requires real non-root Linux isolation')
def test_path_dependent_algorithm_uses_i5_default_route_and_all_three_stages(tmp_path,patched_rolling):
    """Synthetic computational mechanism fixture, not a claim about Amihud's paper."""
    from test_v1beta_algorithm_route import AlgorithmProvider, COMPUTE, REFERENCE as DRAWDOWN_REFERENCE

    class PathProvider(AlgorithmProvider):
        def complete(self, request):
            if paper_call(request):
                system = request.messages[0].content
                if 'Read the supplied original paper evidence' in system:
                    prompt = json.loads(request.messages[-2].content)
                    passage = prompt['passages'][0]
                    contract = dict(formula='minimum(close / running maximum - 1) within the last 60 daily rows',
                        inputs=['close'], warmup=60,
                        time_semantics='Current row after close; use exactly rows t-59 through t.',
                        missing_semantics='Return NaN if any of the 60 closes is non-finite; zero denominator yields NaN.',
                        steps=['Select the trailing 60 rows', 'Compute the running peak from the first row of that window',
                               'Return the most negative drawdown in the window'],
                        citations=[dict(passage=passage['id'],quote=passage['text'])], unresolved=[])
                    return ModelResponse(canonical(contract))
                if 'Write an independent,' in system:
                    return ModelResponse(canonical(dict(source=DRAWDOWN_REFERENCE.replace('def reference(', 'def compute('),
                        explanation='Independent literal path-dependent fixture', unresolved=[])))
                if 'Implement the confirmed factor contract in Python' in system:
                    return ModelResponse(canonical(dict(source=COMPUTE, explanation='Vectorized path-dependent fixture', unresolved=[])))
            return super().complete(request)

    # 60-row algorithm history plus the separate overlap verification period.
    fx=build(tmp_path,snapshot_warmup=330)
    cfg=json.loads(fx['config'].read_text());cfg['require_rolling_test']=True
    fx['config'].write_text(json.dumps(cfg))
    patched_rolling['client'],_=broker(fx)
    library=PaperLibrary(tmp_path/'papers')
    library.import_pdf(stage(library,FIX/'amihud2002.pdf'),'synthetic-mechanism-carrier.pdf')
    provider=PathProvider([decision('skill',skill_id='paper_research',goal='检验合成的60日路径依赖算法'),decision(consent='accept')])
    app=build_chat(tmp_path/'state',provider=provider,profile='development',resources_manifest=fx['manifest'],research_config=fx['config'])
    first=app.turn('检验合成的60日路径依赖算法，先展示定义。')
    assert '自主编程' in first and not list((fx['workspace']/'research_runs').glob('*/*')), first
    response=app.turn('同意')
    task=app.store.load(app.store.session_turns(app.session_id)[-1]['research_task_id'])
    assert task.status=='COMPLETED',(response,task.error)
    result=next(e['result']['data'] for e in task.experiments if e['tool']=='qrtk_paper_research')
    assert '自主 Python 算法（独立合成数值验证通过' in response
    assert '与可信IR逐格一致' not in response
    assert result['paper']['route']=='autonomous_python' and result['final_report_ready']
    run=Path(result['factor_path']).parents[1]
    definition=json.loads((run/'code/factor_definition.json').read_text())
    assert definition['bundle']['contract']['warmup']==60
    assert 'range(59, -1, -1)' in definition['bundle']['source']
    assert result['html_path']==str(run/'reports/report.html')
    assert '2026' in (run/'reports/report.html').read_text()
