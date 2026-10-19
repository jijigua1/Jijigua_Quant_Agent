"""New independent semantic counterexamples: factor scale cannot erase zeros, signs, or missingness."""
import numpy as np
import pytest
from test_recovery_math import run
from paper_agent.reconcile import numerical_matches

@pytest.mark.parametrize('reading',['0 * close_{i,t}','-0.000000000001 * close_{i,t}',
    '0.000000000002 * close_{i,t}'])
def test_small_printed_factor_is_never_zero_opposite_or_doubled(tmp_path,reading):
    printed='0.000000000001 * close'
    p,_=run(tmp_path,['Alpha#23: ('+printed+')'],printed,'custom',latex=reading)
    assert p['status']=='BLOCKED' and p.get('route') not in ('dsl','trusted_ir'),p
    assert any(h['code']=='MODEL_FORMULA_CONTRADICTS_PAPER' for h in p['hard_stops'])

def test_correct_small_printed_factor_remains_researchable(tmp_path):
    printed='0.000000000001 * close'
    p,_=run(tmp_path,['Alpha#23: ('+printed+')'],printed,'custom',latex='0.000000000001 * close_{i,t}')
    assert p['status']!='BLOCKED' and p['route'] in ('dsl','trusted_ir'),p

def test_small_values_and_nan_patterns_are_not_tolerance_equivalent():
    a=np.array([[1e-12,2e-12]])
    assert numerical_matches(a,a).all()
    assert not numerical_matches(a,np.zeros_like(a)).any()
    assert not numerical_matches(a,-a).any()
    assert numerical_matches(a,np.array([[np.nan,2e-12]])) is None
    assert numerical_matches(a,np.nextafter(a,np.inf)).all() # ordinary rounding is still allowed

@pytest.mark.parametrize('printed',['1e-200 * close * 1e-200 * 1e100','(1e100 + close) - 1e100'])
def test_intermediate_precision_loss_cannot_certify_zero(tmp_path,printed):
    p,_=run(tmp_path,['Alpha#23: ('+printed+')'],printed,'custom',latex='0 * close_{i,t}')
    assert p['status']=='BLOCKED' and any(h['code']=='PRINTED_FORMULA_NOT_CHECKED' for h in p['hard_stops']),p
