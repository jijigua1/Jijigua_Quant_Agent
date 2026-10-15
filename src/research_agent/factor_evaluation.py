"""Professional descriptive evaluation from the same reviewed daily qrtk results.

No account metrics, new factor choice, test data access or model-generated numbers.
"""
import math
import time
import numpy as np
import pandas as pd
import qrtk
from qrtk_skills.tools import j
from .contracts import fingerprint, validate
from .research_metrics import hac_mean

VERSION = 'factor-evaluation/1.0.0'


def inference(values, horizon):
    """Trim structural edge gaps only; never compress interior missing sessions."""
    x = np.asarray(values, dtype=float)
    finite = np.flatnonzero(np.isfinite(x))
    if not len(finite):
        return dict(status='insufficient', n=0, n_valid=0, lags=0, se=None,
                    t_stat=None, p_value=None, ci_low=None, ci_high=None,
                    trimmed_edge_dates=len(x), reason='no finite correlations')
    first, last = finite[0], finite[-1] + 1
    result = hac_mean(x[first:last], horizon)
    result.update(trimmed_edge_dates=int(first + len(x) - last),
                  t_stat=None, p_value=None, method='Bartlett Newey-West; asymptotic normal',
                  annualized=False)
    if result['status'] == 'approximate':
        t = float(np.mean(x[first:last]) / result['se'])
        result.update(t_stat=t, p_value=math.erfc(abs(t) / math.sqrt(2)))
    return result


def describe(values, horizon):
    s = pd.Series(values, dtype=float)
    v = s[np.isfinite(s)]
    std = v.std(ddof=1)
    return dict(mean=v.mean(), median=v.median(), std=std,
                ir=v.mean()/std if np.isfinite(std) and std > 0 else None,
                positive_ratio=(v > 0).mean() if len(v) else None,
                n_dates=len(v), inference=inference(s, horizon))


def _period(daily, horizon, name, split):
    out = dict(period=name, split=split, observed_dates=len(daily),
               mean_coverage=daily.coverage.mean(), mean_stocks=daily.n_pairs.mean(),
               long_short_mean_gross=daily.long_short_gross.mean(),
               long_short_std_gross=daily.long_short_gross.std(ddof=1),
               group_monotonicity=daily.group_monotonicity.mean(),
               factor_lag1=daily.factor_lag1.mean(), rank_lag1=daily.rank_lag1.mean())
    for metric in ('ic', 'rank_ic'):
        stats = describe(daily[metric], horizon)
        out.update({metric+'_'+k:v for k,v in stats.items() if k != 'inference'})
        out.update({metric+'_'+k:v for k,v in stats['inference'].items()
                    if k in ('status','se','t_stat','p_value','ci_low','ci_high','lags','n_valid')})
    out['effect_status'] = 'insufficient' if min(out['ic_n_dates'],out['rank_ic_n_dates']) < 60 else 'descriptive_exploratory'
    return out


def verdict(periods, annual, monthly, quality, *, data_status):
    """A transparent evidence assessment, never investment/trading approval."""
    rows={r['split']:r for r in periods}
    evidence=[]
    if data_status not in ('PROFILED_EXPLORATORY_ONLY','synthetic'):
        status='BLOCKED_BY_DATA';evidence.append('输入质量准入状态不支持当前因子研究。')
    elif any(rows[s]['rank_ic_n_dates'] < 60 for s in ('train','valid')):
        status='NEEDS_MORE_EVIDENCE';evidence.append('至少一个分区不足60个有效评价日。')
    else:
        a,b=rows['train'],rows['valid'];direction=np.sign(a['rank_ic_mean'])
        same=direction != 0 and np.sign(b['rank_ic_mean']) == direction
        year_support=sum(np.sign(r['rank_ic_mean']) == direction for r in annual if pd.notna(r['rank_ic_mean']))
        n_years=sum(pd.notna(r['rank_ic_mean']) for r in annual)
        excluded=[r for r in (a,b) if r['rank_ic_status']!='approximate' or r['rank_ic_ci_low'] is None
                  or r['rank_ic_ci_low'] <= 0 <= r['rank_ic_ci_high']]
        if not same or n_years and year_support < math.ceil(.6*n_years):status='UNSTABLE'
        elif excluded:status='NEEDS_MORE_EVIDENCE'
        elif min(a['mean_coverage'],b['mean_coverage']) < .5:status='NEEDS_MORE_EVIDENCE'
        elif direction < 0:status='REJECTED'
        else:status='PROMISING_EXPLORATORY'
        evidence.extend([f"Train / Validation RankIC：{a['rank_ic_mean']:+.4f} / {b['rank_ic_mean']:+.4f}。",
                         f'与Train方向一致的年度：{year_support}/{n_years}。',
                         'HAC区间均不跨0。' if not excluded else '至少一个分区HAC区间不足或跨0。'])
        evidence.extend([f"正RankIC月份占比：{quality['monthly_positive_share']:.1%}；最长非正月份连续{quality['longest_nonpositive_month_streak']}个月。",
                         f"Validation因子覆盖率：{b['mean_coverage']:.1%}；高低组理论毛收益差：{b['long_short_mean_gross']:+.3%}；日度单调性均值：{b['group_monotonicity']:+.3f}。"])
        if status=='PROMISING_EXPLORATORY' and (quality['monthly_positive_share']<.5 or b['long_short_mean_gross']<=0 or b['group_monotonicity']<=0):
            status='NEEDS_MORE_EVIDENCE';evidence.append('月份或分组证据与整体正相关尚未一致，保留进一步验证要求。')
        if direction < 0:evidence.append('预先冻结的高分看多方向不获支持；反向定义需新实验，不能事后翻转方向冒充成功。')
    evidence.append('原始未复权收益、未认证历史股票池及已曝光Validation限制证据强度；不构成可交易结论。')
    return dict(status=status, evidence=evidence, tradable=False,
                policy_version='evidence-verdict/1', data_status=data_status,
                selection_bias='validation exposed; no multiple-experiment selection correction',
                threshold_disclosure='n>=60; annual directional support>=60%; coverage>=50%; HAC CI excludes0; no IC size cutoff')


def calculate(run, result, factor, price, universe, evaluation, *, panels=None):
    start=time.monotonic();index=factor.loc[:result['spec']['valid'][1]].index
    base=pd.read_csv(run/'data/ic_rankic.csv',index_col=0,parse_dates=True)
    daily=base.reindex(index)
    for split in ('train','valid'):
        lo,hi=map(pd.Timestamp,result['spec'][split]);daily.loc[(index>=lo)&(index<=hi),'split']=split
    daily['coverage']=factor.reindex(index).notna().mean(axis=1)
    masked=factor.where(qrtk.valid_mask(factor,universe))
    # Forward labels here are the already-computed split-purged labels, not a new evaluation.
    labels=evaluation['forward_returns']
    daily['n_pairs']=(masked.notna() & np.isfinite(labels)).sum(axis=1).reindex(index)
    daily.loc[daily[['ic','rank_ic']].isna().all(axis=1),'n_pairs']=np.nan
    groups=pd.read_csv(run/'data/group_returns_gross.csv',index_col=0,parse_dates=True).reindex(index)
    daily['long_short_gross']=groups.iloc[:,0]-groups.iloc[:,-1]
    def monotonic(row):
        v=row.to_numpy();ok=np.isfinite(v)
        if ok.sum()<2 or np.ptp(v[ok])==0:return np.nan
        return -np.corrcoef(np.arange(len(v))[ok],pd.Series(v[ok]).rank().to_numpy())[0,1]
    daily['group_monotonicity']=groups.apply(monotonic,axis=1)
    auto=pd.read_csv(run/'data/factor_autocorrelation.csv',parse_dates=['date'])
    lag1=auto[auto.lag==1].set_index('date')
    daily['factor_lag1']=lag1.autocorrelation.reindex(index)
    daily['rank_lag1']=lag1.rank_autocorrelation.reindex(index)
    for metric in ('ic','rank_ic'):
        for w in (20,60):
            daily[f'{metric}_rolling{w}']=daily.groupby('split')[metric].transform(lambda s:s.rolling(w,min_periods=w).mean())
        daily[metric+'_cumulative']=daily.groupby('split')[metric].cumsum()
    daily.to_csv(run/'data/evaluation_daily.csv')
    h=result['spec']['horizon']
    periods=[_period(g,h,s,s) for s,g in daily.groupby('split')]
    annual=[_period(g,h,int(y),str(g.split.iloc[0])) for y,g in daily.groupby(daily.index.year)]
    monthly=[_period(g,h,str(p),str(g.split.iloc[0])) for p,g in daily.groupby(daily.index.to_period('M'))]
    pd.DataFrame(annual).to_csv(run/'data/evaluation_annual.csv',index=False)
    pd.DataFrame(monthly).to_csv(run/'data/evaluation_monthly.csv',index=False)
    pd.DataFrame(periods).to_csv(run/'data/evaluation_partitions.csv',index=False)
    extremes=[]
    for split,g in daily.groupby('split'):
        for metric in ('ic','rank_ic'):
            v=g[metric].dropna();denom=v.abs().sum()
            for date,value in v.loc[v.abs().nlargest(min(5,len(v))).index].items():
                extremes.append(dict(split=split,metric=metric,date=str(date.date()),value=value,
                                     absolute_contribution=value.__abs__()/denom if denom else None))
    pd.DataFrame(extremes).to_csv(run/'data/evaluation_extreme_dates.csv',index=False)
    # Robust-z outlier removal is a prespecified sensitivity diagnostic, not a new selected factor.
    med=masked.median(axis=1);dev=masked.sub(med,axis=0).abs();mad=dev.median(axis=1)
    extreme=dev.gt(mad*1.4826*5,axis=0)&mad.gt(0).to_numpy()[:,None]
    clean=masked.mask(extreme)
    sensitivity=[]
    for metric,method in [('ic','pearson'),('rank_ic','spearman')]:
        corr=qrtk.cross_sectional_corr(clean,labels,method,10)
        for split,g in daily.groupby('split'):
            v=corr.reindex(g.index).where(g[metric].notna())
            sensitivity.append(dict(split=split,metric=metric,original_mean=g[metric].mean(),
                                    no_extreme_mean=v.mean(),n_dates=int(v.count()),
                                    delta=v.mean()-g[metric].mean(),removed_cells=int(extreme.reindex(g.index).sum().sum())))
    pd.DataFrame(sensitivity).to_csv(run/'data/evaluation_sensitivity.csv',index=False)
    bins=[]
    if panels is not None:
        for field,edges,unit in [('close',[0,5,10,20,np.inf],'CNY/share'),('volume',[0,1000,10000,100000,np.inf],'lots/100shares')]:
            a=panels[field].reindex(index).to_numpy();finite=np.isfinite(factor.reindex(index).to_numpy())
            for left,right in zip(edges[:-1],edges[1:]):
                select=(a>left)&(a<=right);n=int(select.sum())
                bins.append(dict(field=field,lower=left,upper=right if np.isfinite(right) else None,unit=unit,
                                 input_cells=n,factor_cells=int((select&finite).sum()),coverage=float((select&finite).sum()/n) if n else None))
    pd.DataFrame(bins,columns=['field','lower','upper','unit','input_cells','factor_cells','coverage']).to_csv(run/'data/evaluation_coverage_buckets.csv',index=False)
    poor=[m for m in monthly if pd.notna(m['rank_ic_mean'])]
    streak=longest=0
    for m in monthly:
        streak=streak+1 if pd.notna(m['rank_ic_mean']) and m['rank_ic_mean']<=0 else 0;longest=max(longest,streak)
    quality=dict(data_status='synthetic' if result['mode']=='synthetic' else 'PROFILED_EXPLORATORY_ONLY',
        invalid_cross_sections=int(daily.rank_ic.isna().sum()),n_observed_dates=len(daily),
        mean_coverage=daily.coverage.mean(),monthly_positive_share=np.mean([m['rank_ic_mean']>0 for m in poor]) if poor else None,
        worst_month=min(poor,key=lambda m:m['rank_ic_mean'])['period'] if poor else None,
        longest_nonpositive_month_streak=longest,constant_or_unavailable_days=int(masked.std(axis=1).le(0).sum()))
    assessment=verdict(periods,annual,monthly,quality,data_status=quality['data_status'])
    files={p.name:dict(path='data/'+p.name,sha256=__import__('hashlib').sha256(p.read_bytes()).hexdigest())
           for p in (run/'data').glob('evaluation_*.csv')}
    report=dict(schema_version='factor-report/2',evaluation_version=VERSION,study_id=result['study_id'],report_revision=1,
        definition_sha256=result.get('definition_sha256',result['spec_fingerprint']),
        data_fingerprint=result['data_sha256'],partitions={r['split']:r for r in periods},
        test=dict(status='NOT_RUN',access='SEALED',evaluation_type=None,exposure=None),
        annual=annual,monthly_rows=len(monthly),quality=quality,verdict=assessment,files=files,
        definitions={'ir':'mean/sample std, nonannualized',
            'inference':'Bartlett HAC, B=max(H-1,floor(4*(n/100)^(2/9))); min60 and10*(B+1); trim edge missing only; interior gaps rejected; asymptotic normal two-sided p/95% CI; no multiple-testing adjustment',
            'month_status':'<60 valid dates => insufficient; no monthly significance assertion',
            'annual_and_monthly':'group each signal-date daily result; labels can cross year/month within same authorized partition; partition boundary purged',
            'sensitivity':'fixed robust z>5 removal; undefined MAD=0 left unchanged; descriptive only, no factor selection',
            'cumulative_ic':'arithmetic sum of correlations, not investment NAV',
            'long_short':'G0 minus last group, overlapping future raw-open gross labels, not tradable returns',
            'calendar':'consecutive observed sessions assumed equally spaced; exchange/PIT calendar not certified'},
        elapsed_seconds=round(time.monotonic()-start,3))
    report=j(report);report['evaluation_fingerprint']=fingerprint(dict(version=VERSION,spec=result['spec_fingerprint'],data=result['data_sha256'],files=files))
    schema=__import__('json').loads((__import__('pathlib').Path(__file__).parent/'resources/factor_report.schema.json').read_text())
    validate(report,schema)
    (run/'data/evaluation_summary.json').write_text(__import__('json').dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    return report
