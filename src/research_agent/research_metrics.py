"""Descriptive diagnostics over reviewed qrtk formulas; no test-period output."""
import math
import numpy as np
import pandas as pd
import qrtk
from qrtk_skills.tools import j

VERSION='1.0.0'

def hac_mean(values, horizon):
    """Bartlett/Newey-West mean SE; conservative admission, no significance stars."""
    x=np.asarray(values,dtype=float)
    n_valid=int(np.isfinite(x).sum())
    if type(horizon) is not int or horizon<1:raise ValueError('invalid horizon')
    lags=max(horizon-1,int(4*(len(x)/100)**(2/9)))
    if len(x)<max(60,10*(lags+1)) or not np.isfinite(x).all():
        return dict(status='insufficient',n=len(x),n_valid=n_valid,lags=lags,se=None,ci_low=None,ci_high=None,
                    reason='requires complete finite grid and >=60, >=10*(bandwidth+1) dates')
    y=x-x.mean();n=len(y);variance=float(y@y/n)
    for lag in range(1,lags+1):variance+=2*(1-lag/(lags+1))*float(y[lag:]@y[:-lag]/n)
    if variance<=0:return dict(status='unsupported',n=n,n_valid=n_valid,lags=lags,se=None,ci_low=None,ci_high=None,reason='zero/invalid long-run variance')
    se=math.sqrt(variance/n)
    return dict(status='approximate',n=n,n_valid=n_valid,lags=lags,se=se,ci_low=float(x.mean()-1.95996398454*se),
                ci_high=float(x.mean()+1.95996398454*se),reason='asymptotic 95% interval; no multiple-testing adjustment or causality claim')

def calculate(run,result,factor,price,universe,*,evaluation=None,panels=None):
    end=pd.Timestamp(result['spec']['valid'][1]);f=factor.loc[:end].replace([np.inf,-np.inf],np.nan)
    u=universe.reindex_like(f).fillna(False).astype(bool);eligible=f.where(u)
    per_date,dist=qrtk.factor_distribution(f,u)
    per_date['skew']=eligible.skew(axis=1);per_date['excess_kurtosis']=eligible.kurt(axis=1)
    per_date.to_csv(run/'data/factor_distribution_by_date.csv')
    finite=f.to_numpy().ravel();finite=finite[np.isfinite(finite)];pooled=pd.Series(finite)
    missing=f.isna();longest=0
    streak=np.zeros(f.shape[1],dtype=np.int32)
    for row in missing.to_numpy():
        streak=np.where(row,streak+1,0);longest=max(longest,int(streak.max()))
    pairs=[];stability=[]
    for lag in (1,5,10):
        raw=qrtk.cross_sectional_corr(eligible,eligible.shift(lag),min_obs=10)
        ranked=qrtk.rank_autocorr(f,u,lag=lag,min_obs=10)
        n=(eligible.notna()&eligible.shift(lag).notna()).sum(axis=1)
        pairs.append(pd.DataFrame({'date':f.index,'lag':lag,'autocorrelation':raw.values,'rank_autocorrelation':ranked.values,'n_pairs':n.values}))
        for split in ('train','valid'):
            start,stop=map(pd.Timestamp,result['spec'][split]);mask=(f.index>=start)&(f.index<=stop)
            stability.append(dict(split=split,lag=lag,correlation=raw[mask].mean(),rank_correlation=ranked[mask].mean(),
                n_dates=int(raw[mask].count()),rank_n_dates=int(ranked[mask].count()),mean_pairs=n[mask&raw.notna().to_numpy()].mean()))
    pd.concat(pairs,ignore_index=True).to_csv(run/'data/factor_autocorrelation.csv',index=False)
    pd.DataFrame(stability).to_csv(run/'data/factor_stability.csv',index=False)
    data=pd.read_csv(run/'data/ic_rankic.csv',index_col=0,parse_dates=True)
    metrics=[];inference=[];windows=[];counts=[]
    full=evaluation if evaluation is not None else qrtk.evaluate_factor(factor,price,direction=1,horizon=result['spec']['horizon'],lag=1,
        n_groups=result['spec']['n_groups'],universe=universe,min_obs=10)
    forward=full['forward_returns'] if 'forward_returns' in full else qrtk.forward_returns(price,result['spec']['horizon'],1)
    both=qrtk.valid_mask(factor,universe)&np.isfinite(forward)
    for split in ('train','valid'):
        rows=data[data['split']==split];stats=result['splits'][split]
        count=both.reindex(rows.index).sum(axis=1)
        counts.append(dict(split=split,mean_stocks=count.mean(),min_stocks=int(count.min()) if len(count) else None,n_dates=len(count)))
        for name in ('ic','rank_ic'):
            s=stats['predictive'][name]
            metrics.append(dict(split=split,metric=name,**s,mean_stocks=count[rows[name].notna()].mean()))
            inference.append(dict(split=split,metric=name,**hac_mean(rows[name].to_numpy(),result['spec']['horizon'])))
            v=rows[name]
            for label,chunk in (('first_half',v.iloc[:len(v)//2]),('second_half',v.iloc[len(v)//2:])):
                windows.append(dict(split=split,metric=name,window=label,**qrtk.ic_summary(chunk)))
    pd.DataFrame(metrics).to_csv(run/'data/factor_metrics.csv',index=False)
    pd.DataFrame(inference).to_csv(run/'data/factor_inference.csv',index=False)
    pd.DataFrame(windows).to_csv(run/'data/factor_windows.csv',index=False)
    decay=[]
    for h in sorted({1,3,5,10,result['spec']['horizon']}):
        spec=qrtk.ResearchSpec(**(result['spec']|{'horizon':h}))
        if evaluation is None:
            rep=qrtk.evaluate_splits(factor,price,spec,universe=universe,reveal_test=False)
        else:
            labels=qrtk.forward_returns(price,h,1)
            x=factor.where(qrtk.valid_mask(factor,universe))
            corr={k:qrtk.cross_sectional_corr(x,labels,m,10) for k,m in [('ic','pearson'),('rank_ic','spearman')]}
            exits=qrtk.label_exit_dates(price.index,h,1)
            rep={'splits':{}}
            for split in ('train','valid'):
                start,stop=map(pd.Timestamp,result['spec'][split])
                keep=(factor.index>=start)&(factor.index<=stop)&(exits<=stop).to_numpy()
                rep['splits'][split]={'predictive':{k:qrtk.ic_summary(v[keep]) for k,v in corr.items()}}
        for split in ('train','valid'):
            stats=rep['splits'][split]['predictive']
            decay.append(dict(split=split,horizon=h,ic_mean=stats['ic']['mean'],rank_ic_mean=stats['rank_ic']['mean'],n_dates=stats['rank_ic']['n_dates']))
    pd.DataFrame(decay).to_csv(run/'data/ic_decay.csv',index=False)
    groups=full['groups'];turnover=qrtk.group_turnover(groups,group=0).loc[:end]
    turnover.to_csv(run/'data/rank_turnover_proxy.csv')
    group_rows=[]
    gross=pd.read_csv(run/'data/group_returns_gross.csv',index_col=0,parse_dates=True)
    for split in ('train','valid'):
        start,stop=map(pd.Timestamp,result['spec'][split])
        for g in range(result['spec']['n_groups']):
            v=gross.loc[(gross.index>=start)&(gross.index<=stop),str(g)]
            group_rows.append(dict(split=split,group='G'+str(g),mean_return_gross=v.mean(),std_return_gross=v.std(ddof=1),n_dates=int(v.count())))
    pd.DataFrame(group_rows).to_csv(run/'data/factor_groups.csv',index=False)
    density=dict(n_cells=int(f.size),finite_cells=len(finite),missing_cells=int(missing.sum().sum()),
        coverage=float(len(finite)/f.size),missing_rate=float(missing.to_numpy().mean()),longest_missing_observations=longest,
        mean=pooled.mean(),std=pooled.std(ddof=1),skew=pooled.skew(),excess_kurtosis=pooled.kurt(),
        quantiles={str(q):pooled.quantile(q) for q in (.01,.05,.25,.5,.75,.95,.99)},
        eligible_distribution=dist,mean_eligible_stocks=per_date['n_valid'].mean(),
        extreme_eligible_ratio=dist['total_outliers']/int(per_date['n_valid'].sum()) if per_date['n_valid'].sum() else None,
        extreme_rule='per date |x-median|/(1.4826*MAD)>5; MAD=0 is undefined, not zero',
        extreme_assessable_cells=int(eligible.notna().sum().sum()-eligible.loc[eligible.sub(eligible.median(axis=1),axis=0).abs().median(axis=1)==0].notna().sum().sum()))
    # qrtk counts undefined MAD rows as no flags; expose the denominator rather than imply no extremes.
    density['extreme_eligible_ratio']=dist['total_outliers']/density['extreme_assessable_cells'] if density['extreme_assessable_cells'] else None
    if not np.isfinite(density['std']) or density['std']==0:density['skew']=density['excess_kurtosis']=np.nan
    direction={s:np.sign(result['splits'][s]['predictive']['rank_ic']['mean']) if result['splits'][s]['predictive']['rank_ic']['mean'] is not None else None for s in ('train','valid')}
    answer=j(dict(version=VERSION,predictive=metrics,inference=inference,stability=stability,windows=windows,
        decay=decay,groups=group_rows,distribution=density,effective_stocks=counts,
        rank_turnover_proxy_mean=turnover.mean(),direction_sign=direction,
        direction_consistent=direction['train']==direction['valid'] if all(x is not None for x in direction.values()) else None,
        definitions={'autocorrelation':'cross-sectional Pearson over common finite eligible stocks at T and T-lag, then equal-date mean; minimum 10 pairs',
            'rank_autocorrelation':'same common pairs, Spearman average tied ranks; lag in observed rows',
            'predictive_decay':'separate H=1/3/5/10 forward open labels, each split purged by label exit; not factor autocorrelation',
            'rank_turnover_proxy':'1 - intersection(top group T,T-1)/size(top group T); not account turnover',
            'moments':'pooled finite train+valid values; sample std, pandas unbiased skew/excess kurtosis; no test values',
            'inference':'Bartlett HAC bandwidth max(H-1,floor(4*(n/100)^(2/9))); complete finite grid required, conservative n gate; no annualisation'},
        unsupported=['industry/size neutralisation','existing-factor correlation without authorized reference','true independent OOS','tradable NAV, Sharpe, drawdown, costs']))
    from .factor_evaluation import calculate as professional
    answer['professional']=professional(run,result,factor,price,universe,full,panels=panels)
    answer['inference']=[dict(split=s,metric=m,**{k.replace(m+'_','',1):v for k,v in r.items()
        if k.startswith(m+'_') and k[len(m)+1:] in ('status','se','ci_low','ci_high','lags','n_valid')},
        n=r[m+'_n_dates']) for s,r in answer['professional']['partitions'].items() for m in ('ic','rank_ic')]
    pd.DataFrame(answer['inference']).to_csv(run/'data/factor_inference.csv',index=False)
    return answer
