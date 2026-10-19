"""Separate evaluator protocol. Never registered as a normal data reader.

Real mode requires a host-owned approved snapshot contract and separate identity.
An operator owns the approval HMAC key and private data reader; neither is in the
Agent request. Synthetic mode is engineering evidence, not OS isolation proof.
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from .contracts import fingerprint, object_schema, validate
from .factor_expression import SCHEMA, inspect, compute
from .security import Denied

VERSION='independent-evaluator/1.0.0'
DEFINITION_SCHEMA=object_schema({
    'expression':SCHEMA,'standardization':{'enum':['raw','zscore']},
    'horizon':{'type':'integer','minimum':1},
    'n_groups':{'type':'integer','minimum':2},
    'direction':{'const':1},'lag':{'const':1},
    'code_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
    'research_study_id':{'type':'string','pattern':'^[0-9a-f]{32}:[0-9a-f]{16}$'},
    'approved_train_validation_fingerprint':{'type':'string','pattern':'^[0-9a-f]{64}$'},
})


def freeze(definition):
    validate(definition,DEFINITION_SCHEMA);inspect(definition['expression'])
    # Round-trip removes shared mutable references. No arbitrary object/pickle.
    d=json.loads(json.dumps(definition,sort_keys=True))
    return dict(protocol=VERSION,definition=d,definition_sha256=fingerprint(d))


class IndependentEvaluator:
    def __init__(self, ledger, private_reader, approval_key, *, synthetic=True,
                 expected_uid=None, researcher_uid=None, max_evaluations=3,approved_release=None):
        if len(approval_key)<32:raise ValueError('approval key must have >=32 bytes')
        if not synthetic:
            if expected_uid is None or researcher_uid is None or expected_uid==researcher_uid:
                raise Denied('EVALUATOR_IDENTITY_NOT_ISOLATED')
            if not hasattr(os,'geteuid') or os.geteuid()!=expected_uid or expected_uid==0:
                raise Denied('EVALUATOR_IDENTITY_INVALID')
            # Host configuration is never accepted through an Agent Tool or permit payload.
            if approved_release is None:raise Denied('REAL_TEST_PUBLICATION_NOT_APPROVED')
            validate(approved_release,object_schema({
                'approval_ref':{'type':'string','minLength':1,'maxLength':120},
                'version':{'type':'string','minLength':1,'maxLength':120},
                'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
                'certified_end':{'type':'string','pattern':'^2026-\\d{2}-\\d{2}$'},
                'quality_status':{'const':'PROFILED_EXPLORATORY_ONLY'},
                'prior_exposure':{'type':'string','minLength':1,'maxLength':500}}))
            approved_release=json.loads(json.dumps(approved_release))
        if type(max_evaluations) is not int or not 1<=max_evaluations<=3:raise ValueError('evaluation limit1-3')
        self.path=ledger;self.reader=private_reader;self.key=bytes(approval_key)
        self.max_evaluations=max_evaluations;self.synthetic=synthetic;self.release=approved_release
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, definition_sha TEXT UNIQUE, payload TEXT, status TEXT);'
                             'CREATE TABLE IF NOT EXISTS audit (at REAL, event TEXT, payload TEXT);')

    def db(self):return sqlite3.connect(self.path,timeout=10,isolation_level=None)

    def _record(self,event,payload):
        with self.db() as db:db.execute('INSERT INTO audit VALUES (?,?,?)',(time.time(),event,json.dumps(payload,sort_keys=True)))

    def operator_permit(self,frozen,approval_ref,*,evaluation_type='synthetic_engineering',prior_exposure='synthetic only'):
        """Operator-only API, not an Agent Tool. No model text grants permission."""
        validate(frozen['definition'],DEFINITION_SCHEMA)
        if frozen['definition_sha256']!=fingerprint(frozen['definition']):raise Denied('FROZEN_DEFINITION_MISMATCH')
        if not re.fullmatch(r'[a-zA-Z0-9_:/-]{1,120}',approval_ref):raise ValueError('invalid approval reference')
        if evaluation_type not in ('synthetic_engineering','retrospective_2026','candidate_first_controlled_test','prospective_blind'):
            raise ValueError('invalid evaluation type')
        if self.synthetic and evaluation_type!='synthetic_engineering':raise Denied('SYNTHETIC_CANNOT_CLAIM_REAL_TEST')
        if not self.synthetic and (evaluation_type not in ('retrospective_2026','candidate_first_controlled_test') or prior_exposure!=self.release['prior_exposure']):
            raise Denied('REAL_TEST_EXPOSURE_CONTRACT')
        payload=dict(definition_sha256=frozen['definition_sha256'],approval_ref=approval_ref,
            evaluation_type=evaluation_type,prior_exposure=prior_exposure,expires=time.time()+300,
            evaluation_id=__import__('uuid').uuid4().hex)
        signature=hmac.new(self.key,json.dumps(payload,sort_keys=True).encode(),hashlib.sha256).hexdigest()
        return dict(payload=payload,signature=signature)

    def evaluate(self, frozen, permit):
        try:
            validate(frozen['definition'],DEFINITION_SCHEMA)
            if set(frozen)!={'protocol','definition','definition_sha256'} or frozen['protocol']!=VERSION:
                raise Denied('INVALID_EVALUATION_PROTOCOL')
            inspect(frozen['definition']['expression'])
            sha=fingerprint(frozen['definition'])
            if sha!=frozen['definition_sha256']:raise Denied('FROZEN_DEFINITION_MISMATCH')
            payload=permit['payload']
            if set(permit)!={'payload','signature'} or set(payload)!={'definition_sha256','approval_ref','evaluation_type','prior_exposure','expires','evaluation_id'}:
                raise Denied('INVALID_APPROVAL_PROTOCOL')
            sig=hmac.new(self.key,json.dumps(payload,sort_keys=True).encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig,permit['signature']) or payload['definition_sha256']!=sha or payload['expires']<time.time():
                raise Denied('INDEPENDENT_APPROVAL_REQUIRED')
            if not re.fullmatch(r'[0-9a-f]{32}',payload['evaluation_id']):raise Denied('INVALID_EVALUATION_ID')
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                count=db.execute('SELECT count(*) FROM evaluations').fetchone()[0]
                if count>=self.max_evaluations:raise Denied('TEST_EVALUATION_BUDGET_EXHAUSTED')
                if db.execute('SELECT 1 FROM evaluations WHERE definition_sha=?',(sha,)).fetchone():raise Denied('TEST_DEFINITION_ALREADY_EXPOSED')
                db.execute('INSERT INTO evaluations VALUES (?,?,?,?)',(payload['evaluation_id'],sha,json.dumps(payload),'RUNNING'))
                db.commit()
        except Exception as exc:
            self._record('DENIED',dict(error=str(exc) if isinstance(exc,Denied) else 'INVALID_PARAMETERS'))
            raise
        self._record('AUTHORIZED',dict(evaluation_id=payload['evaluation_id'],definition_sha256=sha))
        try:
            # Reader capability lives exclusively inside this evaluator process.
            panels,universe,metadata=self.reader()
            import numpy as np
            import pandas as pd
            import qrtk
            from .factor_evaluation import describe, _period
            from qrtk_skills.tools import j
            dates=panels['open'].index
            if not dates.is_unique or not dates.is_monotonic_increasing:raise Denied('EVALUATOR_DATE_AXIS')
            if self.synthetic:
                if metadata['data_kind']!='synthetic' or dates.min().year!=2026 or dates.max().year!=2026:
                    raise Denied('SYNTHETIC_EVALUATOR_DATA_CONTRACT')
            else:
                end=pd.Timestamp(self.release['certified_end'])
                if (metadata.get('data_kind')!='independent_test' or metadata.get('version')!=self.release['version'] or
                    metadata.get('sha256')!=self.release['sha256'] or dates.max()>end or
                    end.date()>__import__('datetime').date.today() or not (dates.year==2026).any() or
                    (dates.year<2026).sum()>120 or dates.min().year<2025):
                    raise Denied('REAL_TEST_SNAPSHOT_CONTRACT')
                if payload['evaluation_type'] not in ('retrospective_2026','candidate_first_controlled_test') or payload['prior_exposure']!=self.release['prior_exposure']:
                    raise Denied('REAL_TEST_EXPOSURE_CONTRACT')
            if panels['close'].size>8_000_000:raise Denied('EVALUATOR_RESOURCE_BUDGET')
            if (not panels['open'].index.equals(panels['close'].index) or not panels['open'].columns.equals(panels['close'].columns)
                or not universe.index.equals(dates) or not universe.columns.equals(panels['open'].columns)):
                raise Denied('EVALUATOR_PANEL_AXIS')
            definition=frozen['definition'];factor=compute(definition['expression'],panels,max_cells=8_000_000)
            if definition['standardization']=='zscore':factor=factor.sub(factor.mean(axis=1),axis=0).div(factor.std(axis=1,ddof=1).replace(0,np.nan),axis=0)
            values=qrtk.evaluate_factor(factor,panels['open'],direction=1,horizon=definition['horizon'],lag=1,
                                        n_groups=definition['n_groups'],universe=universe,min_obs=10)
            # Optional authorized2025 warm-up is feature history, never part of Test statistics.
            dates=dates[dates.year==2026];factor=factor.loc[dates]
            values={k:(v.reindex(dates) if isinstance(v,(pd.Series,pd.DataFrame)) else v) for k,v in values.items()}
            daily=pd.DataFrame(dict(ic=values['ic'],rank_ic=values['rank_ic'],
                coverage=factor.notna().mean(axis=1),n_pairs=(values['valid']&values['forward_returns'].notna()).sum(axis=1),
                long_short_gross=values['long_short'],group_monotonicity=np.nan,
                factor_lag1=qrtk.cross_sectional_corr(factor.where(universe),factor.where(universe).shift(1),min_obs=10),
                rank_lag1=values['rank_autocorr'],split='test'),index=dates)
            daily.loc[daily[['ic','rank_ic']].isna().all(axis=1),'n_pairs']=np.nan
            period=_period(daily,definition['horizon'],'test','test')
            annual=[_period(g,definition['horizon'],int(y),'test') for y,g in daily.groupby(daily.index.year)]
            monthly=[_period(g,definition['horizon'],str(p),'test') for p,g in daily.groupby(daily.index.to_period('M'))]
            # Never return price matrices, future labels, raw FD/path or unbounded traces.
            result=j(dict(protocol=VERSION,evaluation_id=payload['evaluation_id'],definition_sha256=sha,
                frozen_definition=definition,research_study_id=definition['research_study_id'],
                data_version=metadata['version'],data_sha256=metadata['sha256'],status='COMPLETED',
                evaluation_type=payload['evaluation_type'],prior_exposure=payload['prior_exposure'],
                synthetic=self.synthetic,ic=describe(values['ic'],definition['horizon']),rank_ic=describe(values['rank_ic'],definition['horizon']),
                start=str(dates.min().date()),end=str(dates.max().date()),label_tail_purged=definition['horizon']+1,
                formal_backtest_ready=False,raw_data_returned=False,
                test=dict(status='COMPLETED',access='CONTROLLED_EVALUATOR',evaluation_type=payload['evaluation_type'],
                    exposure={'prior':payload['prior_exposure'],'evaluation_id':payload['evaluation_id']},
                    start=str(dates.min().date()),end=str(dates.max().date()),
                    metrics=period,annual=annual,monthly=monthly,
                    daily=[dict(date=str(d.date()),ic=v.ic,rank_ic=v.rank_ic,coverage=v.coverage)
                           for d,v in daily.iterrows()])))
            with self.db() as db:db.execute('UPDATE evaluations SET status=?,payload=? WHERE id=?',('COMPLETED',json.dumps(result),payload['evaluation_id']))
            self._record('RESULT_EXPOSED',dict(evaluation_id=payload['evaluation_id'],definition_sha256=sha,source_sha256=metadata['sha256']))
            return result
        except Exception:
            with self.db() as db:db.execute('UPDATE evaluations SET status=? WHERE id=?',('FAILED',payload['evaluation_id']))
            self._record('FAILED',dict(evaluation_id=payload['evaluation_id'],error='EVALUATOR_EXECUTION_FAILED'))
            raise

    def result_receipt(self, result):
        """Operator channel only. Authenticate an exposed result, never model JSON."""
        from .contracts import canonical
        with self.db() as db:
            row=db.execute('SELECT payload,status FROM evaluations WHERE id=?',(result['evaluation_id'],)).fetchone()
        if not row or row[1]!='COMPLETED' or json.loads(row[0])!=result:raise Denied('RESULT_NOT_IN_EVALUATOR_LEDGER')
        raw=canonical(result,max_bytes=65536)
        return dict(result=result,signature=hmac.new(self.key,raw.encode(),hashlib.sha256).hexdigest())
