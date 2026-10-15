"""Small views of validated results; originals remain in the immutable evidence ledger."""
def parameters(value):
    out={k:v for k,v in value.items() if k!='definition'}
    if 'definition' in value:
        out['definition']={k:v for k,v in value['definition'].items() if k in
            {'formula','expression','expression_sha256','operator_version','warmup_observations','output_units'}}
    return out


def report_summary(data):
    """Compact current report facts; no daily arrays, prices or new permissions."""
    p=data.get('metrics',{}).get('professional')
    if not p:return {}
    fields=('ic_mean','rank_ic_mean','ic_n_dates','rank_ic_n_dates','ic_ci_low','ic_ci_high',
            'rank_ic_ci_low','rank_ic_ci_high','mean_coverage')
    test=p['test']
    counts={s:{'market_observation_days':r.get('observed_dates'),
               'valid_ic_evaluation_days':r.get('ic_n_dates'),
               'valid_rank_ic_evaluation_days':r.get('rank_ic_n_dates')} for s,r in p['partitions'].items()}
    if test.get('status')=='COMPLETED':
        r=test.get('metrics',{});counts['test']={'market_observation_days':r.get('observed_dates'),
            'valid_ic_evaluation_days':r.get('ic_n_dates'),'valid_rank_ic_evaluation_days':r.get('rank_ic_n_dates')}
    return dict(revision=data.get('report_revision',p.get('report_revision',1)),
        html_path=data.get('html_path'),report_path=data.get('report_path'),
        parameters=parameters(data.get('parameters',{})),
        verdict=p['verdict']['status'],data_status=p['verdict'].get('data_status'),formal_backtest_ready=False,
        annual=[{k:r.get(k) for k in ('period','split','ic_mean','rank_ic_mean','rank_ic_n_dates')} for r in p['annual']],
        partitions={s:{k:r.get(k) for k in fields} for s,r in p['partitions'].items()},
        sample_counts=counts,
        count_contract='行情观察日不是有效评价日；有效IC/RankIC日必须使用valid_ic_evaluation_days/valid_rank_ic_evaluation_days，不使用market_observation_days。',
        test={k:test.get(k) for k in ('status','evaluation_type','start','end','exposure','reason','detail')} |
             {'metrics':{k:test.get('metrics',{}).get(k) for k in fields},
              'monthly_label_status':data.get('test_monthly_label_status',[])},
        ordinary_test_resource_readable=False)

def summary(data):
    if data.get('report_revision'):
        return {k:data[k] for k in ('mode','resource_id','study_id','data_sha256','artifact_path',
                                   'html_path','report_path','factor_path','factor_name') if k in data} | {'current_report':report_summary(data)}
    keys={'mode','resource_id','data_sha256','study_id','analysis_scope','n_dates','n_codes','row_count',
        'frequency','format','source','fields','metadata','profiles',
        'observed_start','observed_end','formal_backtest_ready','limitations','artifact_path','report_path',
        'html_path','figure_paths','report_status','status','missing','holdout','resources','adjustment',
        'available_time','null_counts','factor_value','lookback','factor_path','delivery_status','created_at','factor_name','test_request'}
    out={k:v for k,v in data.items() if k in keys}
    if 'paper_status' in data:out['paper_status']=data['paper_status']
    if isinstance(data.get('papers'),list):
        out['papers']=[{k:p.get(k) for k in ('name','title','version','pages','uploaded_at')} for p in data['papers'][:30]]
        if 'paper_count' in data:out['paper_count']=data['paper_count']
    if isinstance(data.get('paper'),dict):
        # paper results: name, factor and the program's hard stops (codes and short details), never raw paper text
        p=data['paper'];out['paper']={k:p[k] for k in ('name','title','factor','factors','mode','route','plan_sha256') if k in p}
        if p.get('hard_stops'):out['paper']['hard_stops']=[{k:str(h.get(k,''))[:200] for k in ('code','symbol','detail')} for h in p['hard_stops'][:6]]
    if 'parameters' in data:out['parameters']=parameters(data['parameters'])
    if 'spec' in data:out['spec']={k:v for k,v in data['spec'].items() if k in {'train','valid','test','horizon','lag','n_groups','execution_rule'}}
    if 'splits' in data:
        out['splits']={s:({k:v for k,v in x.items() if k in {'predictive','theoretical_groups','n_purged','n_signal_dates',
            'mean_factor_coverage','mean_label_coverage'}} if isinstance(x,dict) else x) for s,x in data['splits'].items()}
    if 'evidence' in data:out['evidence']={k:v for k,v in data['evidence'].items() if k in {'verdict','reasons'}}
    if 'lookahead' in data:out['lookahead']={'passed':data['lookahead']['passed']}
    if 'profiles' in data:out['profiles']=[{k:v for k,v in p.items() if k in {'panel','status','missing_rate','issues','rows','cols'}} for p in data['profiles']]
    if 'comparison' in data:
        c=data['comparison'];out['comparison']={k:v for k,v in c.items() if k not in {'current_parameters','parent_parameters'}}
        out['comparison']['parent_parameters']=parameters(c['parent_parameters'])
    if 'metrics' in data:
        m=data['metrics'];out['metrics']={k:m[k] for k in ('version','stability','distribution','inference','direction_consistent','unsupported')}
        if 'professional' in m:
            p=m['professional'];out['metrics']['professional']={k:p[k] for k in
                ('schema_version','evaluation_version','verdict','quality','test','monthly_rows','evaluation_fingerprint')}
            out['metrics']['professional']['annual']=[{k:r[k] for k in
                ('period','split','ic_mean','rank_ic_mean','rank_ic_n_dates','mean_coverage')} for r in p['annual']]
    return out
