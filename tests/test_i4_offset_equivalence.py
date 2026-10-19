"""I4: the original P1, scale variants, and positive controls through understand -> plan.

Only synthetic definition blocks and recorded/scripted readers are used. The
real calendar detector, admission gates and original test assertions stay on.
"""
from decimal import Decimal
import numpy as np
import pytest
from paper_agent.reconcile import numerical_matches
from test_recovery_math import run

SCALES=[('1','1e-12'),('-17','1e-11'),('1e8','1e-4'),('1e-100','1e-112'),
        ('1e100','1e88'),('0','1e-300'),('0','-1e-250'),('1e-268','1e-280')]

def fixed(x):
    return format(Decimal(x),'f')

def entry(tmp_path,printed,reading):
    p,_=run(tmp_path,['Alpha#23: ('+printed+')'],printed,'custom',latex=reading)
    return p

@pytest.mark.parametrize('offset,coefficient',SCALES)
@pytest.mark.parametrize('error',['reverse','constant','double'])
def test_wrong_offset_signal_is_blocked_at_real_entry(tmp_path,offset,coefficient,error):
    k=Decimal(coefficient)
    wrong={'reverse':-k,'constant':Decimal(0),'double':2*k}[error]
    printed=f'{fixed(offset)} + ({fixed(k)}) * close'
    reading=f'{fixed(offset)} + ({fixed(wrong)}) * close_{{i,t}}'
    p=entry(tmp_path,printed,reading)
    assert p['status']=='BLOCKED' and p.get('route') not in ('dsl','trusted_ir'),p
    assert any(h['code'] in ('MODEL_FORMULA_CONTRADICTS_PAPER','FORMULA_READINGS_DISAGREE',
                            'FORMULA_RECONSTRUCTION_UNVERIFIED') for h in p['hard_stops']),p

@pytest.mark.parametrize('offset,coefficient',SCALES)
def test_correct_offset_signal_remains_researchable_at_real_entry(tmp_path,offset,coefficient):
    expression=f'{fixed(offset)} + ({fixed(coefficient)}) * close'
    p=entry(tmp_path,expression,expression.replace('close','close_{i,t}'))
    assert p['status']=='AWAITING_USER_DECISION' and p.get('route') in ('dsl','trusted_ir'),p
    assert p['admission']['gates']['formula']['status']=='pass'
    assert p['admission']['gates']['semantics']['status']=='pass'

def test_dropping_one_of_two_small_addends_is_not_equivalence(tmp_path):
    p=entry(tmp_path,'1 + 0.000000000001 * close + 0.000000000001 * open',
                    '1 + 0.000000000001 * close_{i,t} + 0 * open_{i,t}')
    assert p['status']=='BLOCKED' and p.get('route') not in ('dsl','trusted_ir'),p

@pytest.mark.parametrize('printed,reading',[
    ('1 + 0.00000000000000000001 * close','1 + 0 * close_{i,t}'),
    ('(1e100 + close) - 1e100','0 * close_{i,t}'),
    ('1e-200 * close * 1e-200 * 1e100','0 * close_{i,t}'),
    ('1 + 0.0000000000000001 * close','1 + 0.0000000000000001 * close_{i,t}'),
])
def test_unresolvable_arithmetic_is_blocked_at_real_entry(tmp_path,printed,reading):
    p=entry(tmp_path,printed,reading)
    assert p['status']=='BLOCKED' and p.get('route') not in ('dsl','trusted_ir'),p

def test_changes_checked_on_each_axis_not_just_the_global_range():
    # A large variation across dates cannot hide an erased cross-sectional signal.
    a=np.array([[1.,1.+1e-12,1.+2e-12],[100.,100.+1e-12,100.+2e-12]])
    b=np.array([[1.,1.,1.],[100.,100.,100.]])
    assert not numerical_matches(a,b).all()
    assert not numerical_matches(a.T,b.T).all()
    assert numerical_matches(a,a).all()

def test_a_small_rank_swap_within_the_old_relative_error_is_rejected():
    a=np.array([[1.,2.,2.+1e-10,3.]])
    b=np.array([[1.,2.+1e-10,2.,3.]])
    assert not numerical_matches(a,b).all()

def test_unchanged_ties_and_normal_rounding_remain_allowed():
    a=np.array([[1.,1.,2.,3.],[np.nan,2.,4.,6.]])
    assert numerical_matches(a,np.nextafter(a,np.inf)).all()

def test_subnormal_signal_does_not_certify_equality_after_rounding():
    a=np.array([[1e-320,2e-320]])
    assert numerical_matches(a,a) is None
