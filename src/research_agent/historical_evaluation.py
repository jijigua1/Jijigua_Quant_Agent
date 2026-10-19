"""Reuse qrtk numerical primitives once; summarize fixed, split-purged evidence."""
from dataclasses import asdict
from pathlib import Path
import pandas as pd
import qrtk
from qrtk_skills.tools import j


def summarize(full, spec):
    s=qrtk.ResearchSpec(**spec)
    if s.direction != 1: raise ValueError('full-data direction must be frozen +1')
    splits={'test':'sealed'};warnings=[]
    if s.horizon>1:warnings.append(f'labels overlap (h={s.horizon}); ICIR not annualised')
    for name in ('train','valid'):
        start,end=map(pd.Timestamp,getattr(s,name))
        inside=(full['ic'].index>=start)&(full['ic'].index<=end)
        keep=inside & (full['label_exit_dates']<=end).to_numpy()
        gr=full['group_returns'][keep];cov=full['coverage'][keep]
        splits[name]=dict(n_signal_dates=int(inside.sum()),n_purged=int(inside.sum()-keep.sum()),
            predictive={k:qrtk.ic_summary(full[k][keep]) for k in ('rank_ic','ic')},
            theoretical_groups=dict(mean_group_return_gross=gr.mean().to_dict(),
                long_short_mean_gross=float(full['long_short'][keep].mean()),monotonicity=qrtk.monotonicity(gr)),
            mean_factor_coverage=float(cov['factor_coverage'].mean()),mean_label_coverage=float(cov['label_coverage'].mean()))
        if splits[name]['predictive']['rank_ic']['n_dates']<s.min_dates_per_split:
            warnings.append(name+': insufficient valid dates')
    return j(dict(spec=asdict(s),spec_fingerprint=s.fingerprint(),direction=1,direction_source='fixed',
                  splits=splits,warnings=warnings,note='raw open-price prediction and gross groups; no tradable account'))


def evaluate(ctx,factor,price,universe,spec):
    full=qrtk.evaluate_factor(factor,price,direction=1,horizon=spec['horizon'],lag=spec['lag'],
        n_groups=spec['n_groups'],universe=universe,min_obs=spec['min_obs'])
    # No boundary-crossing label is retained in any exported series or downstream diagnostic.
    allowed=pd.Series(False,index=factor.index)
    for name in ('train','valid'):
        start,end=map(pd.Timestamp,spec[name])
        allowed |= (factor.index>=start)&(factor.index<=end)&(full['label_exit_dates']<=end)
    rep=summarize(full,spec)
    for key in ('forward_returns','ic','rank_ic','group_returns','long_short'):
        full[key]=full[key].where(allowed,axis=0)
    series={k:full[k].loc[allowed] for k in ('ic','rank_ic','group_returns','long_short','coverage')}
    series.update(horizon=spec['horizon'],splits={k:spec[k] for k in ('train','valid','test')},test_revealed=False)
    rep['series_ref']=ctx.put(series,'factor_series');rep['ref']=ctx.put(rep,'factor_evaluation')
    return rep,full


def reproduction(run,train,validation):
    """Reference immutable releases, not a copied full input CSV or original PKL."""
    import json
    config={r['id']:r for r in (train,validation)}
    (run/'code/release_resources.json').write_text(json.dumps({'version':'1','withheld_from':'2026-01-01',
        'resources':list(config.values())},ensure_ascii=False),encoding='utf-8')
    (run/'code/reproduce.py').write_text('''from pathlib import Path
import json
import pandas as pd
from research_agent.data import ResourceCatalog
from research_agent.factor_expression import compute
from research_agent.quant_factors import build_factor
r=Path(__file__).resolve().parents[1]
c=ResourceCatalog(r/'code/release_resources.json')
p={}
for rid in c.records:
 rec,x,m=c.published(rid)
 for field,a in x.fields.items():
  p.setdefault(field,[]).append(pd.DataFrame(a,index=pd.to_datetime(x.dates,format='%Y%m%d'),columns=[v[:6] for v in x.codes]))
p={k:pd.concat(v) for k,v in p.items()}
d=json.loads((r/'code/factor_definition.json').read_text(encoding='utf-8'))
params=json.loads((r/'manifest.json').read_text(encoding='utf-8'))['parameters']
if d.get('kind') == 'isolated_python':
 from paper_agent.algorithm_bundle import compute as isolated
 f=isolated(d['bundle'],p)
elif d.get('kind') in ('approved_implementation','trusted_ir'):
 from paper_agent.trusted_ir import evaluate
 f=evaluate(d['ir'],p,d['symbols'])
else:
 f=compute(d['expression'],p,max_cells=8000000) if d.get('expression') is not None else build_factor(d['factor_id'],p['close'],p['volume'],d['lookback'],d['standardization'])
if (d.get('expression') is not None or d.get('ir') is not None or d.get('kind') == 'isolated_python') and params['standardization']=='zscore':f=f.sub(f.mean(axis=1),axis=0).div(f.std(axis=1,ddof=1).replace(0,float('nan')),axis=0)
expected=pd.read_csv(r/'data/factor_values.csv',index_col=0,parse_dates=True,float_precision='round_trip')
pd.testing.assert_frame_equal(f,expected,check_names=False,check_freq=False,rtol=1e-12,atol=1e-12)
print('Verified full-axis factor reproduction; no Holdout access or backtest approval.')
''',encoding='utf-8')
