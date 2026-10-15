"""Reviewed qrtk handlers inside the existing Agent, with bounded registered data."""
from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import os
import time
from pathlib import Path

from .artifacts import ResearchArtifacts
from .contracts import ContractError, canonical, fingerprint, object_schema, parse_json, validate
from .data import ResourceCatalog
from .security import Denied
from .tools import ToolRegistry, ToolSpec


def trusted_ir_sha256():
    """Fingerprint of the reviewed IR executor and its reference grammar (frozen into every trusted_ir study)."""
    root=Path(__file__).resolve().parents[1]
    h=hashlib.sha256()
    for rel in ('paper_agent/trusted_ir.py','paper_research/factor_ir.py'):
        h.update(rel.encode()+b'\0'+(root/rel).read_bytes())
    return h.hexdigest()

VERSION = '0.4.0'
QUANT_SKILLS = ('data_research','factor_research','strategy_backtest','research_diagnostics','research_reporting','paper_research')
CONTRACT = object_schema({
    'adjustment': {'enum':['none','adjusted_units','unknown']},
    'volume_unit': {'enum':['shares','lots','unknown']},
    'calendar': {'enum':['verified_exchange_sessions','observed_union']},
    'available_time': {'type':'string','minLength':1,'maxLength':500},
    'corporate_actions': {'enum':['not_modelled','adjusted_price_verified']},
    'universe': {'type':'string','minLength':1,'maxLength':300},
    'limits': {'type':'array','items':{'type':'string','maxLength':500},'maxItems':12},
    'research_use': {'enum':['exploratory_raw_price','predictive_research','synthetic']},
})
CONFIG = object_schema({'version':{'const':'1'},'workspace':{'type':'string'},
    'resources':{'type':'object','minProperties':1,'maxProperties':8,'additionalProperties':CONTRACT},
    'validation_pairs':{'type':'object','maxProperties':2,'additionalProperties':{'type':'string'}},
    'paper_root':{'type':'string','minLength':1,'maxLength':300}},
    required=['version','workspace','resources'])
REPORT_CATALOG = object_schema({'version':{'const':'1'},'approval_ref':{'type':'string','minLength':1,'maxLength':300},
    'studies':{'type':'array','maxItems':16,'items':object_schema({
        'study_id':{'type':'string','pattern':'^[0-9a-f]{32}:[0-9a-f]{16}$'},
        'resource_id':{'type':'string'},'title':{'type':'string','minLength':1,'maxLength':100},
        'artifact_path':{'type':'string'},'analysis_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}})}})

class QuantBackend:
    def __init__(self, catalog, config_path):
        ResourceCatalog._check_path(Path(config_path).absolute())
        value = parse_json(Path(config_path).read_text(encoding='utf-8'))
        validate(value, CONFIG)
        if any(r not in catalog.records for r in value['resources']):
            raise Denied('QUANT_RESOURCE_NOT_REGISTERED')
        self.catalog, self.contracts = catalog, value['resources']
        self.validation_pairs=value.get('validation_pairs',{})
        self._factor_cache=None
        for train, valid in self.validation_pairs.items():
            if train not in self.contracts or valid not in self.contracts or catalog.records[train].get('partition')!='train' or catalog.records[valid].get('partition')!='validation':
                raise Denied('VALIDATION_PAIR_INVALID')
        self.artifacts = ResearchArtifacts(value['workspace'])
        self.report_catalog = []
        report_catalog_path=Path(config_path).with_name('report_catalog.json')
        if report_catalog_path.exists():
            ResourceCatalog._check_path(report_catalog_path)
            st=report_catalog_path.stat()
            if st.st_size>16384 or (os.name=='posix' and
                (st.st_uid!=Path(config_path).stat().st_uid or st.st_mode&0o022)):
                raise Denied('REPORT_CATALOG_NOT_OPERATOR_CONTROLLED')
            published=parse_json(report_catalog_path.read_text(encoding='utf-8'));validate(published,REPORT_CATALOG)
            if len({s['study_id'] for s in published['studies']})!=len(published['studies']):
                raise Denied('REPORT_CATALOG_DUPLICATE')
            for s in published['studies']:
                if s['resource_id'] not in self.contracts:raise Denied('REPORT_CATALOG_RESOURCE_DENIED')
                self.artifacts.checked_run(s['artifact_path'])
            self.report_catalog=published['studies']
        self.report_catalog_digest=fingerprint(self.report_catalog)
        self.digest = fingerprint(value)
        from .rolling_client import RollingClient
        self.rolling = RollingClient.from_environment()
        self.approved_registry = None
        self.papers = None
        if value.get('paper_root'):
            from .paper_library import PaperLibrary
            from paper_agent.registry import TrustedRegistry
            self.papers = PaperLibrary(value['paper_root'])
            self.approved_registry = TrustedRegistry(self.papers.root/'approved_code', channels=('chat_user_turn',))
        self.source = parse_json((Path(__file__).parent/'resources/quant_source.json').read_text(encoding='utf-8'))
        for name, expected in self.source['vendored_files'].items():
            p = Path(__file__).parent.parent / name
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                raise Denied('QUANT_IMPLEMENTATION_HASH_MISMATCH')

    def paper_data_profile(self):
        """What the paper planner may assume about the published data (same facts the reports state)."""
        train=next(iter(self.validation_pairs));valid=self.validation_pairs[train]
        tr,va=self.catalog.records[train],self.catalog.records[valid]
        fields=[f for f in tr['fields'] if f not in ('date','code')]
        import numpy as np
        # weekdays less ~4% exchange holidays: an estimate for the planner only; _study's sample gate stays authoritative
        busdays=int(np.busday_count(str(tr['start_date'])[:10],(np.datetime64(str(tr['end_date'])[:10])+1).astype(str)))
        return {'fields':fields,'train_rows_estimate':int(busdays*0.96),'status':tr.get('access_status','PROFILED_EXPLORATORY_ONLY'),
            'adjustment':'none (raw unadjusted market prices)','units':{'volume':'lots (100 shares)','amount':'thousand CNY'},
            'splits':{'train':[tr['start_date'],tr['end_date']],'valid':[va['start_date'],va['end_date']],'test':['2026-01-01','2026-12-31']},
            'holdout':'2026 evaluated only by the controlled rolling evaluator (aggregates)',
            'certification':{'source':tr['source'],'level':tr.get('access_status','PROFILED_EXPLORATORY_ONLY'),'fields':fields,
                'certified':{'adjusted_prices':False,'listing_status':False,'trading_status':False}}}

    def list_resources(self, _task_context):
        return {'mode':'catalog','implementation_version':VERSION,'resources':[
            {k:v for k,v in self.catalog.records[r].items() if k != 'path'} | {'research_contract':c}
            for r,c in self.contracts.items()]}

    def _load(self, resource_id):
        import numpy as np
        import pandas as pd
        if resource_id not in self.contracts:
            raise Denied('QUANT_RESOURCE_NOT_REGISTERED')
        if self.catalog.records[resource_id]['format']=='published_npy':
            record,panel,_=self.catalog.published(resource_id)
            days=pd.DatetimeIndex(pd.to_datetime(panel.dates,format='%Y%m%d'))
            codes=[c[:6] for c in panel.codes]
            panels={k:pd.DataFrame(v,index=days,columns=codes,copy=False) for k,v in panel.fields.items()}
            for name,p in panels.items():
                if ((p<0) if name in ('volume','amount') else (p<=0)).any().any():
                    raise ContractError('invalid published price/volume')
            o,h,l,c=(panels[n] for n in ('open','high','low','close'))
            if ((h<o)|(h<c)|(h<l)|(l>o)|(l>c)).any().any():raise ContractError('daily OHLC inconsistent')
            valid=panels['open'].notna() & panels['close'].notna() & panels['volume'].gt(0)
            return record,None,panels,days,codes,valid
        record, rows = self.catalog._read(resource_id)
        required = {'Stkcd','Trddt','Opnprc','Hiprc','Loprc','Clsprc','Dnshrtrd'}
        if not required <= set(record['fields']) or not rows:
            raise ContractError('daily OHLCV contract incomplete')
        frame=pd.DataFrame(rows)
        frame['Trddt']=pd.to_datetime(frame['Trddt'])
        if frame.duplicated(['Trddt','Stkcd']).any():
            raise ContractError('duplicate date/code')
        if not frame['Stkcd'].map(lambda x:isinstance(x,str) and x.isdigit() and len(x)==6).all():
            raise ContractError('code must be six digits')
        days=pd.DatetimeIndex(sorted(frame['Trddt'].unique()))
        codes=sorted(frame['Stkcd'].unique())
        if len(days)>1000 or len(codes)>100 or len(frame)>10000:
            raise Denied('QUANT_SAMPLE_BUDGET_EXHAUSTED')
        panels={name:frame.pivot(index='Trddt',columns='Stkcd',values=col).reindex(index=days,columns=codes).astype(float)
                for name,col in [('open','Opnprc'),('high','Hiprc'),('low','Loprc'),('close','Clsprc'),('volume','Dnshrtrd')]}
        for name,panel in panels.items():
            if np.isinf(panel).any().any() or ((panel<0) if name=='volume' else (panel<=0)).any().any():
                raise ContractError('non-finite or invalid daily values')
        valid=panels['close'].notna() & panels['open'].notna() & (panels['volume']>0)
        o,h,l,c=(panels[n] for n in ['open','high','low','close'])
        if ((h<o)|(h<c)|(h<l)|(l>o)|(l>c)).any().any():
            raise ContractError('daily OHLC inconsistent')
        return record,frame,panels,days,codes,valid

    def _context(self, resource_id, panels, days):
        from qrtk_skills.runtime import DataCatalog,ArtifactStore,ToolContext
        cat=DataCatalog(); record=self.catalog.records[resource_id]
        for name,p in panels.items():
            cat.register('data:'+name,p,source=record['source'],synthetic=record['data_kind']=='synthetic')
        cat.register('data:calendar',days,source=self.contracts[resource_id]['calendar'])
        return ToolContext(cat,ArtifactStore(),None,'agent_adapter','reviewed_handler')

    def quality(self, resource_id, _task_context):
        from qrtk_skills.tools import data_profile_panel
        record,frame,panels,days,codes,valid=self._load(resource_id)
        ctx=self._context(resource_id,panels,days)
        profiles=[data_profile_panel(ctx,'data:'+name,'factor' if name in ('volume','amount') else 'price',
                    self.contracts[resource_id]['available_time'],'data:calendar') for name in panels]
        return self._provenance(resource_id) | {'row_count':len(days)*len(codes) if frame is None else len(frame),'n_dates':len(days),'n_codes':len(codes),
            'observed_start':str(days.min().date()),'observed_end':str(days.max().date()),
            'profiles':profiles,'excluded_no_volume_or_missing_price':int((~valid).sum().sum()),
            'formal_backtest_ready':False,'analysis_scope':'data_quality'}

    def _provenance(self, resource_id):
        r=self.catalog.records[resource_id]
        return {'mode':'synthetic' if r['data_kind']=='synthetic' else 'real_data','resource_id':resource_id,
                'data_sha256':r['sha256'],'implementation_version':VERSION,'qrtk_version':self.source['version'],
                'implementation_sha256':fingerprint(self.source),'research_contract':self.contracts[resource_id]}

    def study(self, resource_id, factor_id, lookback, horizon, n_groups, standardization, _task_context,parent_study_id=''):
        return self._study(resource_id,factor_id,lookback,horizon,n_groups,standardization,_task_context,parent_study_id=parent_study_id)

    def expression_study(self, resource_id, expression, hypothesis, reason, horizon, n_groups, standardization,
                         _task_context, parent_study_id='',factor_name=''):
        from .factor_expression import inspect
        definition=inspect(expression) | {'hypothesis':hypothesis,'generation_reason':reason}
        if factor_name:
            import re
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',factor_name):raise ContractError('unsafe factor name')
            definition['name']=factor_name
        return self._study(resource_id,'expression',max(2,definition['warmup_observations']),horizon,n_groups,
                           standardization,_task_context,definition,parent_study_id)

    def independent_test_request(self, resource_id, study_id, _task_context):
        # This is a request/readiness record. No2026 reader or evaluator capability is held here.
        run,evidence=self.artifacts.locate(study_id,_task_context)
        result=self.artifacts.read_analysis(run,evidence)
        if result['resource_id']!=resource_id:raise Denied('STUDY_RESOURCE_MISMATCH')
        if result.get('delivery_status')!='VERIFIED':raise Denied('FROZEN_STUDY_INCOMPLETE')
        definition=parse_json((run/'code/factor_definition.json').read_text(encoding='utf-8'))
        request=dict(status='READY_FOR_HOLDOUT_APPROVAL',submitted=False,
            study_id=study_id,definition_sha256=fingerprint(dict(definition=definition,parameters=result['parameters'])),
            code_sha256=_task_context['core_code_sha256'],data_partitions=result.get('data_partitions',{}),
            evaluation_type_required='retrospective or candidate first controlled test; never assume pristine2026',
            reason='real2026 publication, independent identity and first result release require separate operator approval',
            test_data_read=False,test_results_returned=False)
        _task_context['emit']('INDEPENDENT_TEST_APPROVAL_REQUIRED',request)
        # A readiness read references the verified source study, never a new Test result.
        return self._provenance(resource_id)|{k:result[k] for k in
            ('study_id','delivery_status','splits','formal_backtest_ready')}|{
            'artifact_path':str(run),'report_path':str(run/'reports/report.md'),
            'analysis_scope':'independent_test_readiness','test_request':request}

    def _study(self, resource_id, factor_id, lookback, horizon, n_groups, standardization, _task_context,
               definition=None,parent_study_id=''):
        import numpy as np
        import pandas as pd
        from qrtk_skills import tools as qt
        from .quant_factors import build_factor
        total_started=time.monotonic();timings={}
        load_started=time.monotonic()
        record,frame,panels,days,codes,valid=self._load(resource_id)
        timings['train_read_seconds']=round(time.monotonic()-load_started,3)
        published=record['format']=='published_npy'
        published_codes=None;partitions=None
        if published and resource_id not in self.validation_pairs:
            raise Denied('STUDY_REQUIRES_TRAIN_PARTITION')
        if published and any(r not in _task_context.get('authorized_resources',()) for r in (resource_id,self.validation_pairs[resource_id])):
            raise Denied('PAIRED_PARTITION_NOT_AUTHORIZED')
        contract=self.contracts[resource_id]
        if contract['adjustment']=='unknown' or contract['research_use']=='predictive_research' and (
            contract['adjustment']!='adjusted_units' or contract['calendar']!='verified_exchange_sessions'):
            raise Denied('RESEARCH_DATA_CONTRACT_INCOMPLETE')
        if (factor_id=='volume_stall' or definition and 'volume' in definition['input_fields']) and contract['volume_unit']=='unknown':
            raise Denied('VOLUME_UNIT_UNVERIFIED')
        if len(days)<max(30,lookback+horizon+10) or len(codes)<10:
            raise Denied('INSUFFICIENT_RESEARCH_SAMPLE')
        if _task_context.get('validate_only'):
            # Proposal check only: every input, contract and sample gate passed; nothing is computed or written.
            from .definition_gate import ValidationPassed
            raise ValidationPassed()
        if published:
            validation_id=self.validation_pairs[resource_id]
            definition_hash=fingerprint(dict(factor_id=factor_id,lookback=lookback,horizon=horizon,n_groups=n_groups,
                standardization=standardization,definition=definition))
            _task_context['emit']('RESEARCH_DEFINITION_FROZEN',dict(definition_sha256=definition_hash,
                train_resource_id=resource_id,validation_resource_id=validation_id))
            started_read=time.monotonic()
            vr,_,vp,vd,vc,vu=self._load(validation_id)
            timings['validation_read_seconds']=round(time.monotonic()-started_read,3)
            if vc!=codes or days[-1]>=vd[0]:raise Denied('PARTITION_AXIS_OR_TIME_MISMATCH')
            trmeta=self.catalog.published(resource_id)[2];vmeta=self.catalog.published(validation_id)[2]
            published_codes=trmeta['codes']
            partitions={s:dict(resource_id=r['id'],release_id=r['release_id'],manifest_sha256=r['sha256'],
                field_sha256=m['sha256'],start=r['start_date'],end=r['end_date'],n_dates=len(m['dates']),n_codes=len(m['codes']),
                status='PROFILED_EXPLORATORY_ONLY') for s,r,m in [('train',record,trmeta),('validation',vr,vmeta)]}
            train_days=days;validation_days=vd
            panels={k:pd.concat([p,vp[k]],copy=False) for k,p in panels.items()}
            days=panels['close'].index
            valid=pd.concat([valid,vu],copy=False)
            if len(days)*len(codes)>8_000_000:raise Denied('FULL_PANEL_BUDGET_EXHAUSTED')
        current=None;started=0
        def stage(name):
            nonlocal current,started
            if current:
                timings[current+'_seconds']=round(time.monotonic()-started,3)
                _task_context['emit']('RESEARCH_STAGE',{'stage':current,'status':'COMPLETED',
                    'elapsed_seconds':round(time.monotonic()-started,3),'resource_id':resource_id})
            if time.monotonic()>_task_context.get('deadline',float('inf')):
                from .security import BudgetExhausted
                raise BudgetExhausted('tool_wall_seconds')
            current=name;started=time.monotonic()
            if name:
                _task_context['emit']('RESEARCH_STAGE',{'stage':name,'status':'RUNNING','elapsed_seconds':0,'resource_id':resource_id})
        stage('data_quality')
        ctx=self._context(resource_id,panels,days)
        ctx.catalog.register('data:universe',valid,source='observed prices and positive volume, not trade permission')
        # A fixed builder registered by trusted code, not a callable or source supplied by the model.
        def builder(price):
            key=fingerprint(dict(catalog=self.catalog.digest,factor_id=factor_id,lookback=lookback,
                standardization=standardization,definition=definition))
            complete=published and price.index.equals(days)
            if complete and self._factor_cache and self._factor_cache[0]==key:
                timings['factor_cache_hit']=True
                return self._factor_cache[1]
            if definition is None:
                out=build_factor(factor_id,price,panels['volume'].reindex(price.index),lookback,standardization)
            elif definition.get('kind') in ('approved_implementation','trusted_ir'):
                # Human-approved implementation with an exact source hash; output contract and trusted-IR equality checked.
                # trusted_ir: the reviewed executor itself, cross-checked against the independent reference evaluator.
                inputs={k:v.loc[price.index] for k,v in panels.items() if k in definition['input_fields']} \
                    |({'close':price} if 'close' in definition['input_fields'] else {})
                out=self._trusted_ir_compute(definition,inputs) if definition['kind']=='trusted_ir' else self._approved_compute(definition,inputs)
                if standardization=='zscore':
                    out=out.sub(out.mean(axis=1),axis=0).div(out.std(axis=1,ddof=1).replace(0,np.nan),axis=0)
            else:
                from .factor_expression import compute
                out=compute(definition['expression'],{k:v.loc[price.index] for k,v in panels.items() if k in definition['input_fields']} | {'close':price},
                        max_cells=8_000_000 if published else 100000)
                if standardization=='zscore':
                    out=out.sub(out.mean(axis=1),axis=0).div(out.std(axis=1,ddof=1).replace(0,np.nan),axis=0)
            if complete:
                out.values.flags.writeable=False
                self._factor_cache=(key,out)
            return out
        ctx.catalog.register('data:builder',builder,source='reviewed fixed builder')
        # Ex-ante economic rationale: generated and frozen before any factor value or statistic exists.
        rationale=_task_context.get('economic_rationale')
        if rationale is None:
            from .economic_rationale import generate, unavailable
            if definition is None:
                formula=f'-(close[T]/close[T-{lookback}]-1)' if factor_id=='reversal' else f'max(volume[T]/mean(volume[T-{lookback}:T-1])-1,0)*exp(-abs(close[T]/close[T-{lookback}]-1)/0.02)'
            else:
                formula=definition.get('formula') or definition.get('latex') or factor_id
            if _task_context.get('model') and _task_context.get('model_live'):
                rationale=generate(_task_context['model'],factor_name=(definition or {}).get('name') or factor_id,formula=formula,
                    definition=f'标准化={standardization}；分组={n_groups}；方向+1（高分组G0）；暖机{lookback}观察日',horizon=horizon,
                    data_profile=self.paper_data_profile() if published else contract,user_hypothesis=_task_context.get('hypothesis',''))
            else:
                rationale=unavailable('OFFLINE_OR_NO_LIVE_MODEL',horizon)
        _task_context['emit']('ECONOMIC_RATIONALE_FROZEN',dict(sha256=rationale['sha256'],status=rationale['status'],
            expected_direction=rationale['expected_direction'],before_factor_computation=True))
        compute_started=time.monotonic()
        factor=builder(panels['close'])
        timings['factor_compute_seconds']=round(time.monotonic()-compute_started,3)
        ctx.catalog.register('data:factor',factor,source='fixed '+factor_id,synthetic=record['data_kind']=='synthetic')
        train_end=int(len(days)*.60)-1;valid_end=int(len(days)*.85)-1
        spec={'factor_name':factor_id,'direction':1,'horizon':horizon,'lag':1,'n_groups':n_groups,
              'min_obs':10,'train':[str(days[0].date()),str(days[train_end].date())],
              'valid':[str(days[train_end+1].date()),str(days[valid_end].date())],
              'test':[str(days[valid_end+1].date()),str(days[-1].date())],
              'universe_name':contract['universe'],'execution_rule':'next_observed_open','min_dates_per_split':60}
        if published:
            train_end=len(train_days)-1;valid_end=len(days)-1
            spec.update(train=[record['start_date'],record['end_date']],valid=[vr['start_date'],vr['end_date']],
                        test=['2026-01-01','2026-12-31'])
        parameters=dict(resource_id=resource_id,factor_id=factor_id,lookback=lookback,horizon=horizon,
                        n_groups=n_groups,standardization=standardization)
        if definition:
            parameters['definition']=definition
        parent=None
        if parent_study_id:
            parent_run,parent_evidence=self.artifacts.locate(parent_study_id,_task_context)
            parent=self.artifacts.read_analysis(parent_run,parent_evidence)
            if parent['data_sha256']!=record['sha256'] or any(parent['spec'][k]!=spec[k] for k in ('train','valid','test','horizon','lag','n_groups')):
                raise Denied('COMPARISON_CONTRACT_MISMATCH')
            parameters['parent_study_id']=parent_study_id
        directory_name=factor_id+'_'+str(lookback)+'d' if factor_id not in ('expression','approved') else definition.get('name') or (
            'volume_price_' if 'volume' in definition['input_fields'] else 'price_expression_')+str(lookback)+'d'
        study_id,run=self.artifacts.create(_task_context['task_id'],directory_name)
        created_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        self.artifacts.write_json(run/'manifest.json',dict(task_id=_task_context['task_id'],run_id=study_id.split(':')[1],
            session_id=_task_context['session_id'],goal=_task_context['goal'],factor_definition=parameters,
            provider=_task_context['provider'],code_sha256=_task_context['core_code_sha256'],
            implementation=self.source,resource=self._provenance(resource_id),parameters=parameters,spec=spec,
            ledger={'path':str(_task_context['store'].path),'task_id':_task_context['task_id']},
            task_status='RUNNING',computation_status='RUNNING',started_at=created_at,created_at=created_at,
            timezone='Asia/Shanghai',artifact_path=str(run),factor_name=directory_name,
            data_cutoff=str(days[-1].date()),factor_output_cutoff=spec['valid'][1],files=[]))
        if published:
            self.artifacts.update_manifest(run,dict(artifact_budget_bytes=512*1024*1024,data_partitions=partitions,
                definition_sha256=definition_hash,holdout_published=False))
        _task_context['emit']('ARTIFACT_CREATED',{'study_id':study_id,'artifact_path':str(run)})
        self.artifacts.write_json(run/'data/frozen_spec.json',dict(spec=spec,parameters=parameters,test_reveal_allowed=False))
        self.artifacts.write_json(run/'code/economic_rationale.json',rationale)
        profiles=[qt.data_profile_panel(ctx,'data:'+name,'factor' if name=='volume' else 'price',contract['available_time'],'data:calendar') for name in ('open','close','volume')]
        if any(p['status']=='fail' for p in profiles):
            raise ContractError('quality gate failed')
        stage('factor_construction')
        profile=qt.factor_profile(ctx,'data:factor',spec['valid'][1],universe='data:universe')
        la=qt.diag_lookahead_check(ctx,'data:close','data:builder',[spec['train'][1],spec['valid'][1]])
        if not la['passed']:
            raise ContractError('lookahead gate failed')
        stage('factor_evaluation')
        full=None
        if published:
            from .historical_evaluation import evaluate
            ev,full=evaluate(ctx,factor,panels['open'],valid,spec)
            decay={'cutoff':spec['valid'][1],'rows':[],'note':'split-purged predictive decay in metrics CSV; no account returns'}
            _task_context['emit']('VALIDATION_EXPOSURE',dict(study_id=study_id,definition_sha256=definition_hash,
                validation_manifest_sha256=vr['sha256'],matured_dates=ev['splits']['valid']['predictive']['rank_ic']['n_dates'],
                purpose='candidate evaluation; exposed validation cannot become blind OOS'))
        else:
            ev=qt.factor_evaluate(ctx,'data:factor','data:open',spec,universe='data:universe',reveal_test=False)
            decay=qt.factor_decay(ctx,'data:factor','data:open',spec,sorted({1,horizon}),1,universe='data:universe')
        review=qt.diag_evidence_review(ctx,ev['ref'],lookahead=la['ref'],min_dates=60)
        limitations=list(contract['limits'])+ev['warnings']+['test is sealed; no independent test claim',
            'IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores',
            'group returns are gross, equal weight, missing labels excluded; not account returns',
            'no industry/size neutralisation or multiple-testing adjustment; HAC inference has explicit sample admission',
            'positive observed volume is sample eligibility, not permission to buy/sell',
            'all parameter changes after seeing validation are exploratory; no certified out-of-sample performance']
        stage('evidence_review')
        result=self._provenance(resource_id) | {'study_id':study_id,'analysis_scope':'factor_prediction_exploratory',
            'parameters':parameters,'spec':spec,'spec_fingerprint':ev['spec_fingerprint'],
            'splits':ev['splits'],'profile':profile,'decay':decay,'lookahead':la,'evidence':review,
            'n_dates':len(days),'n_codes':len(codes),'formal_backtest_ready':False,'limitations':limitations,
            'economic_rationale':rationale}
        if _task_context.get('paper_definition'):
            # paper -> structured definition -> executed formula, verified before any value existed (shown in the report)
            result['paper_definition']=_task_context['paper_definition']
            self.artifacts.write_json(run/'code/paper_definition.json',_task_context['paper_definition'])
        if getattr(self,'crosscheck_log',None) and definition is not None and definition.get('kind') in ('approved_implementation','trusted_ir'):
            result['implementation_crosscheck']=list(self.crosscheck_log)[:4]
        result['holdout']={'independent_blind':False,'reason':'output statistics hidden only; raw resource remains accessible through data_query',
                          'statistics_hidden':True,'prior_exposure':'exploratory shared resource'}
        result['data_source']=record['source']
        result['created_at']=created_at
        result['factor_name']=directory_name
        if published:
            result.update(data_partitions=partitions,definition_sha256=definition_hash,
                validation_exposure={'status':'EXPOSED','previous_5d_raw_momentum_exposure':True,
                    'independent_blind':False},
                holdout={'independent_blind':False,'statistics_hidden':True,'prior_exposure':'legacy 2026 daily65 was previously exposed',
                    'reason':'2026 not published and all legacy 2026 reads denied in this profile; no retrospective blind claim'})
            result['limitations']=[x for x in limitations if x!='test is sealed; no independent test claim']+[
                'Train2020-2023 and Validation2024-2025 are separate hash-checked published partitions; 2026 unavailable',
                'Validation warm-up uses permitted Train history; Train labels crossing boundary purged, Validation tail not filled from 2026',
                'listing dates are unverified; published candidate prelisting mask does not certify a historical PIT stock universe',
                'no embargo gap requested: chronological factor diagnostics only, no supervised train-label fit; lag+H boundary purge applied',
                'volume is lots (100 shares), amount thousand CNY; price-relative label is not corporate-action-adjusted total return']
        if parent:
            result['comparison']=dict(parent_study_id=parent_study_id,parent_parameters=parent['parameters'],
                current_parameters=parameters,independent_test=False,
                parent_statistics={s:parent['splits'][s]['predictive'] for s in ('train','valid')},
                rank_ic_delta={s:ev['splits'][s]['predictive']['rank_ic']['mean']-parent['splits'][s]['predictive']['rank_ic']['mean']
                    if ev['splits'][s]['predictive']['rank_ic']['mean'] is not None and parent['splits'][s]['predictive']['rank_ic']['mean'] is not None else None
                    for s in ('train','valid')})
        # Full test-period prices and factor values are not exported while the test is sealed.
        if not published:
            frame[frame.Trddt<=pd.Timestamp(spec['valid'][1])].to_csv(run/'data/input_slice.csv',index=False)
        else:self.artifacts.write_json(run/'data/data_partitions.json',partitions)
        factor.loc[:spec['valid'][1]].to_csv(run/'data/factor_values.csv')
        series=ctx.artifacts.get(ev['series_ref'],'factor_series')
        # Export the same split-purged dates used by qrtk summary statistics.
        from qrtk import label_exit_dates
        index=series['ic'].index;exits=label_exit_dates(days,horizon,1).reindex(index)
        split_labels=pd.Series('',index=index)
        for name in ('train','valid'):
            start,end=map(pd.Timestamp,spec[name])
            split_labels.loc[(index>=start)&(index<=end)&(exits<=end).to_numpy()]=name
        keep=split_labels!=''
        series={k:v.loc[keep] if isinstance(v,(pd.Series,pd.DataFrame)) else v for k,v in series.items()}
        ev['series_ref']=ctx.put(series,'factor_series');ev['ref']=ctx.put(ev,'factor_evaluation')
        pd.DataFrame({'ic':series['ic'],'rank_ic':series['rank_ic'],'split':split_labels.loc[keep]}).to_csv(run/'data/ic_rankic.csv')
        series['group_returns'].to_csv(run/'data/group_returns_gross.csv')
        (run/'code/quant_factors.py').write_bytes((Path(__file__).parent/'quant_factors.py').read_bytes())
        factor_definition=definition or dict(factor_id=factor_id,lookback=lookback,standardization=standardization,
            hypothesis=_task_context.get('hypothesis',_task_context['goal']),generation_reason=_task_context.get('change_reason','user request'))
        if not definition:
            factor_definition['formula']=f'-(close[T]/close[T-{lookback}]-1)' if factor_id=='reversal' else f'max(volume[T]/mean(volume[T-{lookback}:T-1])-1,0)*exp(-abs(close[T]/close[T-{lookback}]-1)/0.02)'
            if standardization=='zscore':factor_definition['formula']='cs_zscore('+factor_definition['formula']+')'
        self.artifacts.write_json(run/'code/factor_definition.json',factor_definition)
        stage('factor_diagnostics')
        from .research_metrics import calculate
        result['metrics']=calculate(run,result,factor,panels['open'],valid,evaluation=full,panels=panels)
        if published:
            from .report_versions import ROLLING_REASONS
            answer=self.rolling.status() if self.rolling.available else {}
            reason='PENDING' if answer.get('authorized') else 'NOT_AUTHORIZED' if answer.get('status')=='OK' else 'EVALUATOR_UNAVAILABLE'
            pro=result['metrics']['professional']
            pro['test']=dict(status='NOT_EVALUATED',access='SEALED',evaluation_type=None,exposure=None,reason=reason,detail=ROLLING_REASONS[reason])
            (run/'data/evaluation_summary.json').write_text(__import__('json').dumps(pro,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
            rolling_reason=reason
        (run/'code/factor_expression.py').write_bytes((Path(__file__).parent/'factor_expression.py').read_bytes())
        for name,text in (_task_context.get('extra_code_files') or {}).items():
            if not __import__('re').fullmatch(r'[a-z_]{1,40}\.json',name) or len(text)>4*1024*1024:
                raise ContractError('provenance file contract')
            (run/'code'/name).write_text(text,encoding='utf-8')
        (run/'code/reproduce.py').write_text('''from pathlib import Path
import json
import pandas as pd
from research_agent.factor_expression import compute
from research_agent.quant_factors import build_factor
r=Path(__file__).resolve().parents[1]
d=json.loads((r/'code/factor_definition.json').read_text(encoding='utf-8'))
x=pd.read_csv(r/'data/input_slice.csv',dtype={'Stkcd':str},parse_dates=['Trddt'])
p={k:x.pivot(index='Trddt',columns='Stkcd',values=v).sort_index().sort_index(axis=1) for k,v in
   [('open','Opnprc'),('high','Hiprc'),('low','Loprc'),('close','Clsprc'),('volume','Dnshrtrd')]}
if d.get('kind') in ('approved_implementation','trusted_ir'):
 from paper_agent.trusted_ir import evaluate
 f=evaluate(d['ir'],p,d['symbols'])
else:
 f=compute(d['expression'],p) if d.get('expression') is not None else build_factor(d['factor_id'],p['close'],p['volume'],d['lookback'],d['standardization'])
if d.get('expression') is not None or d.get('ir') is not None:
 m=json.loads((r/'manifest.json').read_text(encoding='utf-8'))
 if m['parameters']['standardization']=='zscore': f=f.sub(f.mean(axis=1),axis=0).div(f.std(axis=1,ddof=1).replace(0,float('nan')),axis=0)
pd.testing.assert_frame_equal(f,pd.read_csv(r/'data/factor_values.csv',index_col=0,parse_dates=True),check_names=False,check_freq=False,rtol=1e-10,atol=1e-12)
print('Factor reproduction verified; no holdout/market validity claim.')
''',encoding='utf-8')
        if published:
            from .historical_evaluation import reproduction
            reproduction(run,record,vr)
        stage('factor_export')
        from .factor_export import export,ExportFailed
        try:
            result.update(export(run,factor.loc[:spec['valid'][1]],factor_definition,result,published_codes=published_codes))
            self.artifacts.update_manifest(run,{'factor_export':result['factor_export'],'delivery_status':'VERIFIED'})
        except Exception as exc:
            result['delivery_status']='EXPORT_FAILED'
            self.artifacts.write_json(run/'data/analysis.json',result)
            self.artifacts.update_manifest(run,dict(computation_status='COMPLETED',delivery_status='EXPORT_FAILED',
                analysis_sha256=hashlib.sha256((run/'data/analysis.json').read_bytes()).hexdigest(),files=self.artifacts.inventory(run)))
            raise ExportFailed('FACTOR_EXPORT_FAILED') from exc
        # One authoritative report uses the same split-purged metric files as its tables.
        stage('report_export')
        stage('chart_generation')
        from .research_report import render
        presentation=render(run,result,factor,series,_task_context['goal'],_task_context.get('hypothesis',_task_context['goal']),factor_definition,
            progress=lambda n,total,name:_task_context['emit']('RESEARCH_STAGE',dict(stage='chart_generation',status='RUNNING',
                elapsed_seconds=round(time.monotonic()-started,3),completed=n,total=total,detail=name)))
        result.update(presentation)
        if published:
            timings.update(end_to_end_compute_seconds=round(time.monotonic()-total_started,3),
                input_matrix_bytes=sum(p.size*8 for p in panels.values()),factor_cells=int(factor.size),
                cache='hash-checked immutable release arrays reused within this CLI session',
                chunking='complete row cross-sections; full combined time axis for causal warm-up; no stock/time truncation')
            result['performance']=timings
            try:
                import resource
                timings['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
                timings['rss_scope']='Linux process high-water mark; fresh candidate process for benchmark, cumulative for chat session'
            except ImportError:timings['rss_scope']='RSS unavailable on this platform'
            self.artifacts.write_json(run/'data/performance.json',timings)
        from .report_consistency import check as consistency
        result['report_consistency']=consistency(run,result)
        self.artifacts.write_json(run/'data/analysis.json',result)
        stage(None)
        files=self.artifacts.inventory(run)
        self.artifacts.update_manifest(run,dict(spec_fingerprint=ev['spec_fingerprint'],
            computation_status='COMPLETED',files=files))
        answer=result | {'analysis_sha256':hashlib.sha256((run/'data/analysis.json').read_bytes()).hexdigest(),
            'artifact_path':str(run),**presentation,
            'phases':['data_quality','factor_construction','factor_evaluation','evidence_review','factor_diagnostics','factor_export','report_export','chart_generation']}
        if published:
            answer=self._rolling_test(run,answer,rolling_reason,stage,_task_context)
        return answer

    def _rolling_test(self, run, answer, reason, stage, _task_context):
        """Default 2026 stage: request the controlled rolling evaluation, then add a report revision (or a status-only one)."""
        from .report_versions import append_rolling_report, latest_report
        stage('rolling_test')
        if reason=='PENDING':
            outcome=self.rolling.evaluate(answer['study_id'],run)
        else:
            outcome=dict(status='NOT_EVALUATED',reason=reason)
        _task_context['emit']('ROLLING_TEST_OUTCOME',{k:outcome.get(k) for k in ('status','reason','evaluation_id','snapshot','certified_end','reused','detail')})
        try:
            version=append_rolling_report(self.artifacts,run,outcome) if reason=='PENDING' else None
        except (ContractError,Denied) as exc:
            # The verified Train/Validation study stays delivered; the failed Test revision is recorded, never hidden.
            detail='REPORT_REVISION_FAILED: '+type(exc).__name__+': '+str(getattr(exc,'code',exc))[:200]
            _task_context['emit']('ROLLING_TEST_OUTCOME',dict(status='NOT_EVALUATED',reason='FAILED',detail=detail,
                                                              evaluation_id=outcome.get('evaluation_id')))
            outcome=dict(status='NOT_EVALUATED',reason='FAILED',detail=detail,evaluation_id=outcome.get('evaluation_id'),
                         receipt_evaluation_id=outcome.get('evaluation_id') if outcome.get('status')=='COMPLETED' else None)
            version=append_rolling_report(self.artifacts,run,outcome)
        stage(None)
        latest=latest_report(self.artifacts,run,answer)
        latest.setdefault('report_revision',1)
        # The computing task owns the original study directory; the newest report revision is referenced separately.
        latest['report_artifact_path']=latest.get('report_artifact_path',str(run));latest['artifact_path']=str(run)
        latest['rolling_test']=dict(status=outcome.get('status'),reason=outcome.get('reason'),evaluation_id=outcome.get('evaluation_id'),
            snapshot=outcome.get('snapshot'),certified_end=outcome.get('certified_end'),reused=outcome.get('reused'),
            report_revision=(version or {}).get('revision',1))
        return latest

    def _approved_compute(self, definition, inputs):
        import numpy as np
        import pandas as pd
        if self.approved_registry is None:
            raise Denied('APPROVED_REGISTRY_UNAVAILABLE')
        entry,fn=self.approved_registry.load(definition['implementation_id'])
        if entry['source_sha256']!=definition['source_sha256']:
            raise Denied('APPROVED_IMPLEMENTATION_CHANGED')
        ref=next(iter(inputs.values()))
        out=fn({k:v.copy() for k,v in inputs.items()})
        if not isinstance(out,pd.DataFrame) or not out.index.equals(ref.index) or list(out.columns)!=list(ref.columns):
            raise ContractError('approved implementation output contract')
        out=out.astype(float).replace([np.inf,-np.inf],np.nan)
        if definition.get('ir') is None:
            # Outside the trusted grammar: the approved, independently written reference() checks a column sample.
            reference=self.approved_registry.load_reference(definition['implementation_id'])
            step=max(1,len(out.columns)//12);cols=list(out.columns[::step])[:12]
            ref_values=reference({k:v[cols].copy() for k,v in inputs.items()})
            if not isinstance(ref_values,pd.DataFrame):raise ContractError('approved reference output contract')
            ref_values=ref_values.astype(float).replace([np.inf,-np.inf],np.nan)
            a,b=out[cols].to_numpy(),ref_values.to_numpy()
            checked='approved reference() (independent model call, human-approved)'
        else:
            # Every computation (full panel and look-ahead truncations) must equal the reviewed trusted IR executor.
            from paper_agent.trusted_ir import evaluate as trusted
            ref_values=trusted(definition['ir'],inputs,definition['symbols']).astype(float).replace([np.inf,-np.inf],np.nan)
            a,b=out.to_numpy(),ref_values.to_numpy()
            checked='paper_agent.trusted_ir (reviewed executor)'
        both=~np.isnan(a)&~np.isnan(b)
        scale=float(np.abs(b[both]).max()) if both.any() else 1.0
        bad=int((np.abs(a[both]-b[both])>1e-9*np.abs(b[both])+1e-12*scale).sum()) if both.any() else 0
        mismatch=int((np.isnan(a)!=np.isnan(b)).sum())
        self.crosscheck_log=getattr(self,'crosscheck_log',[])+[dict(rows=int(a.shape[0]),cols=int(a.shape[1]),
            non_nan_cells=int(both.sum()),nan_pattern_mismatch=mismatch,cells_outside_tolerance=bad,checked_against=checked)]
        if mismatch or bad:
            raise ContractError('IMPLEMENTATION_MISMATCH: approved code differs from its check ('+checked+')')
        return out

    def _trusted_ir_compute(self, definition, inputs):
        """The reviewed IR executor (no model code), checked cell by cell against the independent reference evaluator on a
        deterministic sample of columns over the whole time axis; the executor's source hash must equal the frozen one."""
        import numpy as np
        from paper_agent.trusted_ir import evaluate as trusted
        from paper_research.factor_ir import IRError, evaluate as reference, semantics_of
        try:
            semantics=semantics_of(definition)        # computed exactly under the version it was frozen with
        except IRError:
            raise Denied('TRUSTED_EXECUTOR_CHANGED') from None
        out=trusted(definition['ir'],inputs,definition['symbols'],semantics=semantics).astype(float).replace([np.inf,-np.inf],np.nan)
        ref=next(iter(inputs.values()))
        if not out.index.equals(ref.index) or list(out.columns)!=list(ref.columns):
            raise ContractError('trusted IR output contract')
        step=max(1,len(out.columns)//40)
        cols=list(out.columns[::step])[:40]
        expected=reference(definition['ir'],{k:v[cols] for k,v in inputs.items()},definition['symbols'],semantics=semantics).astype(float)
        a,b=out[cols].to_numpy(),expected.replace([np.inf,-np.inf],np.nan).to_numpy()
        both=~np.isnan(a)&~np.isnan(b)
        scale=float(np.abs(b[both]).max()) if both.any() else 1.0
        bad=int((np.abs(a[both]-b[both])>1e-9*np.abs(b[both])+1e-12*scale).sum()) if both.any() else 0
        mismatch=int((np.isnan(a)!=np.isnan(b)).sum())
        self.crosscheck_log=getattr(self,'crosscheck_log',[])+[dict(rows=int(a.shape[0]),cols=len(cols),checked_against='factor_ir.evaluate (reference)',
            non_nan_cells=int(both.sum()),nan_pattern_mismatch=mismatch,cells_outside_tolerance=bad)]
        if mismatch or bad:
            raise ContractError('TRUSTED_IR_SELF_CHECK_FAILED: executor differs from the reference evaluator')
        return out

    def trusted_ir_study(self, resource_id, ir, symbols, hypothesis, reason, horizon, n_groups, standardization,
                         _task_context, factor_name='', latex=''):
        """A paper factor whose frozen IR the reviewed executor computes; no model-written code runs."""
        import re
        from paper_research.factor_ir import warmup
        name=factor_name or 'paper_factor'
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',name):
            raise ContractError('unsafe factor name')
        if type(horizon) is not int or not 1<=horizon<=10:
            raise ContractError('horizon must be 1..10 observation days')
        wu=warmup(ir)
        if wu['uses_future']:
            raise ContractError('FUTURE_REFERENCE')
        definition={'kind':'trusted_ir','ir':ir,'symbols':dict(symbols),'input_fields':sorted(set(symbols.values())),
            'warmup_observations':int(wu['observations_required']),'executor_sha256':trusted_ir_sha256(),
            'ir_semantics':__import__('paper_research.factor_ir',fromlist=['IR_SEMANTICS']).IR_SEMANTICS,
            'latex':latex or 'f_{t,i}=\\mathrm{IR}','expression':None,'hypothesis':hypothesis,'generation_reason':reason,'name':name}
        self.crosscheck_log=[]
        out=self._study(resource_id,'approved',max(2,definition['warmup_observations']),horizon,n_groups,
                        standardization,_task_context,definition,'')
        out['implementation_crosscheck']=self.crosscheck_log[:4]
        return out

    def approved_study(self, resource_id, implementation_id, hypothesis, reason, horizon, n_groups, standardization,
                       _task_context, parent_study_id='', factor_name='', latex=''):
        import re
        if self.approved_registry is None:
            raise Denied('APPROVED_REGISTRY_UNAVAILABLE')
        entry,_=self.approved_registry.load(implementation_id)
        name=factor_name or 'approved_factor'
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',name):
            raise ContractError('unsafe factor name')
        if type(horizon) is not int or not 1<=horizon<=10:
            raise ContractError('horizon must be 1..10 observation days')
        c=entry['contract']
        definition={'kind':'approved_implementation','implementation_id':implementation_id,'source_sha256':entry['source_sha256'],
            'input_fields':sorted({i['field'] for i in c['inputs']}),'symbols':{i['symbol']:i['field'] for i in c['inputs']},
            'warmup_observations':int(c['warmup']['observations_required']),'ir':c['ir'],
            'latex':latex or 'f_{t,i}=\\mathrm{approved}','expression':None,
            'approval':{k:entry['approval'][k] for k in ('approved_at','channel','approved_text')},
            'tests':[{k:t[k] for k in ('name','passed')} for t in entry['tests']],
            'hypothesis':hypothesis,'generation_reason':reason,'name':name}
        self.crosscheck_log=[]
        out=self._study(resource_id,'approved',max(2,definition['warmup_observations']),horizon,n_groups,
                        standardization,_task_context,definition,parent_study_id)
        out['implementation_crosscheck']=self.crosscheck_log[:4]
        return out

    def read_study(self, resource_id, study_id, _task_context, refresh=False):
        """Read a study's newest report. refresh=False (default) has no side effect: no evaluator request, no new report
        revision. refresh=True asks for the newest rolling snapshot (or reuses its receipt) and, if a 2026 receipt was
        issued but its report was never built, finishes that report from the same receipt without a new evaluation."""
        try:run,evidence=self.artifacts.locate(study_id,_task_context)
        except Denied as exc:
            registered=next((s for s in self.report_catalog if s['study_id']==study_id and s['resource_id']==resource_id),None)
            if exc.code!='STUDY_NOT_IN_SESSION' or registered is None:raise
            run=self.artifacts.checked_run(registered['artifact_path'])
            m=parse_json((run/'manifest.json').read_text(encoding='utf-8'))
            if m['task_id']+':'+m['run_id']!=study_id:raise Denied('REPORT_CATALOG_STUDY_MISMATCH')
            data=self.artifacts.read_analysis(run,registered)
            evidence=registered|{k:data[k] for k in ('report_path','report_status')}
        if evidence['resource_id']!=resource_id:
            raise Denied('STUDY_RESOURCE_MISMATCH')
        result=self.artifacts.read_analysis(run,evidence) | {k:evidence[k] for k in ('analysis_sha256','artifact_path','report_path','report_status')}
        from .invalidations import lookup
        invalid=lookup(self.artifacts.root,study_id)
        refresh_info=dict(requested=bool(refresh),status='NOT_REQUESTED')
        recovered=None
        if refresh and invalid is not None:
            refresh_info=dict(requested=True,status='SKIPPED_INVALID_DEFINITION')   # an invalid definition is never evaluated again
        elif refresh:
            recovered=self._recover_rolling_report(run,study_id,_task_context)
            refresh_info=self._refresh_rolling(run,study_id,_task_context)
        from .report_versions import latest_report, report_access
        out=latest_report(self.artifacts,run,result)
        out['report_access']=report_access(run,out,refresh_info,recovered,
                                           evaluator=getattr(self.rolling,'available',False))
        if invalid:
            out['invalidation']={k:invalid[k] for k in ('code','reason_cn','evidence','recorded_by','recorded_at')}
        return out

    def _refresh_rolling(self, run, study_id, _task_context):
        """New trading days: the same frozen study is evaluated on the newest snapshot as a new report revision.
        An unchanged snapshot reuses the receipt (no revision); earlier revisions are never modified. The outcome is
        always returned to the caller (status, category, detail), so an old report is never presented as a new one."""
        if not getattr(self.rolling,'available',False):
            return dict(requested=True,status='EVALUATOR_UNAVAILABLE',category='EVALUATOR_UNAVAILABLE')
        from .report_versions import append_rolling_report
        try:
            if not self.rolling.status().get('authorized'):
                return dict(requested=True,status='NOT_AUTHORIZED',category='NOT_AUTHORIZED')
            outcome=self.rolling.evaluate(study_id,str(run))
        except Exception as exc:  # noqa: BLE001 - reading a report never fails because the refresh did
            _task_context['emit']('ROLLING_REFRESH',dict(status='ERROR',error=type(exc).__name__))
            return dict(requested=True,status='FAILED',category='EVALUATOR_ERROR',detail=type(exc).__name__)
        _task_context['emit']('ROLLING_REFRESH',{k:outcome.get(k) for k in ('status','reason','evaluation_id','snapshot','certified_end','reused')})
        info=dict(requested=True,evaluation_id=outcome.get('evaluation_id'),snapshot=outcome.get('snapshot'),
                  certified_end=outcome.get('certified_end'),reused=outcome.get('reused'))
        if outcome.get('status')!='COMPLETED':
            reason=str(outcome.get('reason') or 'FAILED')
            return info|dict(status=reason,category=reason if reason in ('NOT_AUTHORIZED','UNSUPPORTED_STUDY','HISTORY_MISMATCH',
                             'EVALUATOR_UNAVAILABLE','SYNTHETIC_REAL_MIXING_DENIED') else 'EVALUATOR_ERROR',
                             detail=str(outcome.get('detail') or '')[:200])
        try:
            version=append_rolling_report(self.artifacts,run,outcome)
        except (ContractError,Denied) as exc:
            # the receipt exists: record it, so a later refresh rebuilds the report from it without a new evaluation
            from .report_versions import append_rolling_report as status_revision
            detail='REPORT_REVISION_FAILED: '+type(exc).__name__+': '+str(getattr(exc,'code',exc))[:200]
            status_revision(self.artifacts,run,dict(status='NOT_EVALUATED',reason='FAILED',detail=detail,
                                                    receipt_evaluation_id=outcome.get('evaluation_id')))
            return info|dict(status='REPORT_FAILED',category='REPORT_FAILED',detail=detail)
        return info|dict(status='REUSED_NO_CHANGE' if version.get('reused') else 'NEW_REVISION',category='OK',
                         revision=version.get('revision'))

    def _recover_rolling_report(self, run, study_id, _task_context):
        """A 2026 receipt was issued and registered, but its report revision failed: build the report from that receipt.
        No evaluation request; idempotent (a revision for the same evaluation id is reused)."""
        from .report_versions import append_rolling_report, pending_receipts
        if getattr(self.rolling,'receipt_dir',None) is None:return None
        done=None
        for eid in pending_receipts(run):
            try:
                receipt=self.rolling.load_receipt(Path(self.rolling.receipt_dir)/(eid+'.json'),study_id)
                version=append_rolling_report(self.artifacts,run,dict(status='COMPLETED',receipt=receipt,evaluation_id=eid,reused=True))
            except (ContractError,Denied,OSError,KeyError,ValueError) as exc:
                _task_context['emit']('ROLLING_REPORT_RECOVERY',dict(evaluation_id=eid,status='FAILED',error=type(exc).__name__))
                return dict(status='FAILED',evaluation_id=eid,detail=type(exc).__name__)
            _task_context['emit']('ROLLING_REPORT_RECOVERY',dict(evaluation_id=eid,status='COMPLETED',revision=version.get('revision')))
            done=dict(status='COMPLETED',evaluation_id=eid,revision=version.get('revision'),reused=version.get('reused'))
        return done

    def backtest_readiness(self, resource_id, _task_context):
        quality=self.quality(resource_id,_task_context)
        _task_context['emit']('RESEARCH_STAGE',dict(stage='strategy_backtest',status='BLOCKED',elapsed_seconds=0,
            detail='BLOCKED_DATA_CONTRACT / BLOCKED_ENGINE_QUALIFICATION'))
        return quality | {'analysis_scope':'backtest_readiness','status':'BLOCKED_DATA_CONTRACT',
            'engine':'qrtk_reference','real_backtest_enabled':False,
            'missing':['reviewed corporate-action and delisting handling','validated buy/sell status and limit panels',
                       'verified exchange calendar','historical costs and engine deterministic cross-check'],
            'reference_scope':'135 synthetic tests verify implementation, not real market suitability'}

    def export_factor(self,resource_id,study_id,_task_context):
        import io
        import pandas as pd
        from .factor_export import export,verify,server_panel,ExportFailed
        from .research_report import render
        from .research_metrics import calculate
        old,evidence=self.artifacts.locate(study_id,_task_context)
        result=self.artifacts.read_analysis(old,evidence)
        if result['resource_id']!=resource_id:raise Denied('STUDY_RESOURCE_MISMATCH')
        manifest=parse_json((old/'manifest.json').read_text(encoding='utf-8'))
        if result.get('data_partitions'):
            if result.get('delivery_status')!='VERIFIED':raise Denied('PUBLISHED_EXPORT_REPAIR_REQUIRES_REVIEW')
            for item in result['factor_export']['files']:
                path=Path(item['path'])
                if path.parent!=old/'data' or path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>80*1024*1024:
                    raise Denied('ARTIFACT_FILE_DENIED')
                if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise Denied('ARTIFACT_FINGERPRINT_MISMATCH')
            return self.read_study(resource_id,study_id,_task_context)
        def checked(name):
            p=old/name;item=next((x for x in manifest['files'] if x['path']==name),None)
            if not item or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>4*1024*1024:raise Denied('ARTIFACT_FILE_DENIED')
            raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise Denied('ARTIFACT_FINGERPRINT_MISMATCH')
            return raw
        f=pd.read_csv(io.BytesIO(checked('data/factor_values.csv')),index_col=0,parse_dates=True,float_precision='round_trip')
        if f.index.max()>pd.Timestamp(result['spec']['valid'][1]):raise Denied('TEST_FACTOR_EXPORT_DENIED')
        if result.get('delivery_status')=='VERIFIED':
            checked('data/factor.pkl');checked('data/factor_dict.pkl');x=server_panel(f,result['mode']=='synthetic')
            verify(old/'data/factor.pkl',x);verify(old/'data/factor_dict.pkl',{result['parameters']['factor_id']:x})
            return self.read_study(resource_id,study_id,_task_context)
        new_id,run=self.artifacts.create(_task_context['task_id'],'factor_repair')
        self.artifacts.write_json(run/'manifest.json',dict(manifest,task_id=_task_context['task_id'],run_id=new_id.split(':')[1],
            session_id=_task_context['session_id'],task_status='RUNNING',delivery_status='PENDING',files=[],
            artifact_path=str(run),created_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            export_source_study_id=study_id,provider=_task_context['provider'],code_sha256=_task_context['core_code_sha256']))
        _task_context['emit']('ARTIFACT_CREATED',{'study_id':new_id,'artifact_path':str(run)})
        for name in ('data/factor_values.csv','data/input_slice.csv','data/ic_rankic.csv','data/group_returns_gross.csv',
                     'data/frozen_spec.json','code/factor_definition.json','code/reproduce.py'):
            with (run/name).open('xb') as out:out.write(checked(name))
        result.update(study_id=new_id,implementation_version=VERSION,created_at=parse_json((run/'manifest.json').read_text())['created_at'])
        definition=parse_json(checked('code/factor_definition.json').decode())
        try:result.update(export(run,f,definition,result))
        except Exception as exc:
            self.artifacts.write_json(run/'data/analysis.json',result|{'delivery_status':'EXPORT_FAILED'})
            self.artifacts.update_manifest(run,dict(delivery_status='EXPORT_FAILED',computation_status='COMPLETED',
                analysis_sha256=hashlib.sha256((run/'data/analysis.json').read_bytes()).hexdigest(),files=self.artifacts.inventory(run)))
            raise ExportFailed('FACTOR_EXPORT_FAILED') from exc
        source=pd.read_csv(io.BytesIO(checked('data/input_slice.csv')),dtype={'Stkcd':str},parse_dates=['Trddt'])
        price=source.pivot(index='Trddt',columns='Stkcd',values='Opnprc').reindex_like(f)
        volume=source.pivot(index='Trddt',columns='Stkcd',values='Dnshrtrd').reindex_like(f)
        if 'metrics' not in result:result['metrics']=calculate(run,result,f,price,price.notna()&volume.gt(0))
        else:
            for item in manifest['files']:
                if item['path'].startswith('data/') and item['path'].endswith('.csv') and not (run/item['path']).exists():
                    with (run/item['path']).open('xb') as out:out.write(checked(item['path']))
        result.update(render(run,result,f,{},_task_context['goal'],definition.get('hypothesis',_task_context['goal']),definition))
        self.artifacts.write_json(run/'data/analysis.json',result)
        self.artifacts.update_manifest(run,dict(delivery_status='VERIFIED',factor_export=result['factor_export'],computation_status='COMPLETED',files=self.artifacts.inventory(run)))
        return result|dict(analysis_sha256=hashlib.sha256((run/'data/analysis.json').read_bytes()).hexdigest(),artifact_path=str(run))

    def registry(self):
        resource={'type':'string','enum':list(self.contracts)}
        base={'resource_id':resource}
        study_base={'resource_id':{'type':'string','enum':list(self.validation_pairs)}} if self.validation_pairs else base
        study_id={'type':'string','pattern':'^[0-9a-f]{32}:[0-9a-f]{16}$'}
        # Closed top-level output plus explicit evidence fields; nested qrtk numerical output is finite JSON.
        number={'type':['number','null']}
        ic=object_schema({'mean':number,'std':number,'icir':number,'positive_ratio':number,'n_dates':{'type':'integer','minimum':0}})
        group=object_schema({'mean_group_return_gross':{'type':'object','additionalProperties':number},
            'long_short_mean_gross':number,'monotonicity':object_schema({'daily_mean':number,'share_positive':number,
                'pooled':number,'strictly_monotone':{'type':'boolean'},'n_dates':{'type':'integer','minimum':0}})})
        split=object_schema({'n_signal_dates':{'type':'integer','minimum':0},'n_purged':{'type':'integer','minimum':0},
            'predictive':object_schema({'rank_ic':ic,'ic':ic}),'theoretical_groups':group,
            'mean_factor_coverage':number,'mean_label_coverage':number})
        splits=object_schema({'train':split,'valid':split,'test':{'const':'sealed'}})
        common={'mode':{'enum':['real_data','synthetic','catalog']},'resource_id':resource,
            'data_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'implementation_version':{'enum':['0.2.0','0.3.0',VERSION]},
            'qrtk_version':{'const':'0.2.0'},'implementation_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'research_contract':CONTRACT,'row_count':{'type':'integer'},'n_dates':{'type':'integer'},'n_codes':{'type':'integer'},
            'observed_start':{'type':'string'},'observed_end':{'type':'string'},'profiles':{'type':'array'},
            'excluded_no_volume_or_missing_price':{'type':'integer'},'formal_backtest_ready':{'const':False},
            'analysis_scope':{'type':'string'},'study_id':study_id,'parameters':{'type':'object'},'spec':{'type':'object'},
            'spec_fingerprint':{'type':'string','pattern':'^[0-9a-f]{64}$'},'splits':splits,
            'profile':{'type':'object'},'decay':{'type':'object'},'lookahead':{'type':'object'},'evidence':{'type':'object'},
            'limitations':{'type':'array','items':{'type':'string'}},'analysis_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'artifact_path':{'type':'string'},'report_path':{'type':'string'},'report_status':{'enum':['incomplete','complete']},
            'phases':{'type':'array','items':{'type':'string'}},'resources':{'type':'array'},'status':{'const':'BLOCKED_DATA_CONTRACT'},
            'engine':{'const':'qrtk_reference'},'real_backtest_enabled':{'const':False},'missing':{'type':'array'},'reference_scope':{'type':'string'},
            'holdout':{'type':'object'},'data_source':{'type':'string'},'comparison':{'type':'object'},
            'html_path':{'type':'string'},'figure_paths':{'type':'array','items':{'type':'string'}}}
        common.update(factor_path={'type':'string'},factor_metadata_path={'type':'string'},factor_export={'type':'object'},
            delivery_status={'enum':['VERIFIED','EXPORT_FAILED']},metrics={'type':'object'},created_at={'type':'string'},factor_name={'type':'string'},formula_rendering={'type':'object'})
        common.update(data_partitions={'type':'object'},definition_sha256={'type':'string'},validation_exposure={'type':'object'},performance={'type':'object'},test_request={'type':'object'})
        common.update(economic_rationale={'type':'object'},paper_definition={'type':'object'},invalidation={'type':'object'})
        common.update(report_consistency={'type':'object'},rolling_test={'type':'object'},report_access={'type':'object'},implementation_crosscheck={'type':'array'},
            paper={'type':'object'},papers={'type':'array'},paper_count={'type':'integer'},paper_status={'type':'string'})
        month_status=object_schema({'period':{'type':'string','pattern':'^[0-9]{4}-[0-9]{2}$'},
            'observed_dates':{'type':'integer','minimum':0},'effective_dates':{'type':'integer','minimum':0},
            'unmatured_labels':{'type':'integer','minimum':0},'reason':{'enum':['ALL_FORWARD_LABELS_UNMATURED','AVAILABLE','INSUFFICIENT_VALID_PAIRS']}})
        common.update(report_revision={'type':'integer','minimum':1},report_artifact_path={'type':'string'},
            report_manifest_sha256={'type':'string','pattern':'^[0-9a-f]{64}$'},
            test_monthly_label_status={'type':'array','maxItems':12,'items':month_status})
        schema=object_schema(common,required=['mode','implementation_version'])
        def tool(name,description,args,handler,writes=(),required=None,definitions=None):
            inputs=object_schema(args,required=required)
            if definitions: inputs['$defs']=definitions
            return ToolSpec(name,VERSION,description,inputs,schema,handler,kind='quant_compute',write_scopes=writes,
                            resource_mode='catalog' if not args else 'single')
        read_args=base|{'study_id':study_id}
        from .factor_expression import SCHEMA as EXPRESSION_SCHEMA
        return ToolRegistry([
            tool('list_research_resources','查询已批准的研究样本与口径；不代表全服务器资源。',{},self.list_resources),
            tool('qrtk_data_quality','用受审 qrtk 检查已登记日频数据，不猜测交易或复权规则。',base,self.quality),
            tool('qrtk_factor_study','仅计算严格固定的反转或放量滞涨公式。volume_stall使用价格收益绝对值，不是有方向的价格反转，也不能代替量价组合研究；组合/新定义必须使用qrtk_expression_study。输出默认PKL/指标/报告。',study_base|{
                'factor_id':{'enum':['reversal','volume_stall']},'lookback':{'type':'integer','minimum':2,'maximum':20},
                'horizon':{'type':'integer','minimum':1,'maximum':10},'n_groups':{'type':'integer','minimum':2,'maximum':5},
                'standardization':{'enum':['raw','zscore']},'parent_study_id':{'type':'string','pattern':'^$|^[0-9a-f]{32}:[0-9a-f]{16}$'}},self.study,('research_runs',),
                required=['resource_id','factor_id','lookback','horizon','n_groups','standardization']),
            tool('qrtk_expression_study','组合因子与新因子的唯一受控入口：把价量变化、反转等基础量组合为一个DSL输出，不用多个固定因子的并列结果冒充组合。window1–60，累计历史120，horizon1–10，分组2–5。对发布Train自动配对Validation，冻结定义、计算全轴、默认PKL和报告。无Python执行。',study_base|{
                'factor_name':{'type':'string','pattern':'^[a-z][a-z0-9_]{0,39}$','description':'可选简短英文因子名，例如 volume_stall_5d；只用于目录与标题，不改变公式'},
                'expression':EXPRESSION_SCHEMA,'hypothesis':{'type':'string','minLength':1,'maxLength':600},
                'reason':{'type':'string','minLength':1,'maxLength':600},'horizon':{'type':'integer','minimum':1,'maximum':10},
                'n_groups':{'type':'integer','minimum':2,'maximum':5},'standardization':{'enum':['raw','zscore']},
                'parent_study_id':{'type':'string','pattern':'^$|^[0-9a-f]{32}:[0-9a-f]{16}$'}},self.expression_study,('research_runs',),
                required=['resource_id','expression','hypothesis','reason','horizon','n_groups','standardization']),
            tool('qrtk_read_study','查询本会话研究或操作者明确共享的报告。默认refresh=false：只读取已有最新报告，不请求评价、不写任何文件。'
                 '仅当用户明确要求更新到最新2026数据（如“刷新”“更新到最新”“最新行情的2026表现”）时refresh=true：请求受控评价器在最新快照上评价'
                 '（同快照复用已签发回执，不重复评价），并用已签发但未生成报告的回执补完报告；不重算Train/Validation、不改变定义，不授予新行情或Test权限。'
                 '已共享研究元数据：'+canonical([{k:s[k] for k in ('study_id','resource_id','title')} for s in self.report_catalog]),
                 read_args|{'refresh':{'type':'boolean'}},self.read_study,required=['resource_id','study_id']),
            tool('qrtk_independent_test_request','记录本会话已冻结候选的独立测试申请。当前真实2026未批准：返回READY_FOR_HOLDOUT_APPROVAL，不读测试数据，不执行测试，不允许调参搜索。',read_args,self.independent_test_request),
            tool('qrtk_diagnose_study','读取本会话已计算的缺失覆盖、截断因子未来函数和证据诊断。',read_args,self.read_study),
            tool('qrtk_export_report','查询固定工具已生成的证据报告及成果路径，不接受模型填写数值或任意路径。',read_args,self.read_study),
            tool('qrtk_export_factor','复核并返回本会话PKL；旧实验或失败导出在新任务目录补救，不重算因子、不覆盖历史。仅结构兼容，不代表合格回测。',read_args,self.export_factor,('research_runs',)),
            tool('qrtk_backtest_readiness','核验真实回测准入条件；本阶段真实账户引擎未启用。',base,self.backtest_readiness),
            *self._paper_tools(schema),
        ],context={'quant_config':self.digest,'qrtk_source':fingerprint(self.source),'report_catalog':self.report_catalog_digest,
                   'papers':bool(self.papers)})

    def _paper_tools(self, schema):
        if self.papers is None:
            return ()
        from .paper_tools import PaperPipeline
        pipeline=PaperPipeline(self)
        def spec(name,description,args,handler,writes=(),required=None):
            return ToolSpec(name,VERSION,description,object_schema(args,required=required),schema,handler,
                            kind='quant_compute',write_scopes=writes,resource_mode='catalog')
        return (spec('paper_list','列出本用户已上传并登记的论文（名称、标题、页数、上传时间）。只读，不读取PDF正文，不需要任何ID。',{},pipeline.list_papers),
            spec('qrtk_paper_research','研究一篇已上传论文中的因子并交付完整报告：paper填用户对论文的描述（如“刚上传的”“Amihud那篇”，空字符串=最近上传），'
                 'factor填用户点名的因子（未点名则空字符串，程序选论文主因子）。程序自动读论文、核对引文、生成研究定义、选择DSL或新算法、'
                 '在需要时暂停请用户确认替代口径或审核新代码、计算Train/Validation并进行2026滚动Test。不要填写SHA或内部ID。',
                 {'paper':{'type':'string','maxLength':200},'factor':{'type':'string','maxLength':120},
                  'plan_sha256':{'type':'string','pattern':'^$|^[0-9a-f]{64}$'}},
                 pipeline.research,('research_runs',),required=['paper','factor']))
