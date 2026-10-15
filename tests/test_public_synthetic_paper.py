"""Original public numerical/semantic examples, independent of copyrighted replay inputs."""
import numpy as np
import pandas as pd
import pytest
from paper_research.factor_ir import parse_formula, evaluate, warmup, IRError
from paper_agent.trusted_ir import evaluate as fast

def panel():
    return pd.DataFrame({'A':[10.,12.,15.,18.,20.,21.], 'B':[20.,19.,16.,14.,12.,10.]},
                        index=pd.bdate_range('2023-01-02',periods=6))

def test_cumulative_return_is_not_a_lagged_single_period_return():
    c=panel(); formula=r'F_{i,t}=\frac{C_{i,t}}{C_{i,t-3}}-1'
    ir=parse_formula(formula)['ir']
    a=evaluate(ir,{'close':c},{'C':'close'})
    b=fast(ir,{'close':c},{'C':'close'})
    pd.testing.assert_frame_equal(a,b)
    assert a.iloc[3,0] == pytest.approx(.8)  # hand value: 18 / 10 - 1
    assert np.isnan(a.iloc[:3].to_numpy()).all()
    assert warmup(ir)['observations_required']==4

def test_future_expression_is_rejected_by_both_executors():
    ir=parse_formula(r'F_{i,t}=C_{i,t+1}')['ir']
    assert warmup(ir)['uses_future']
    for fn in (evaluate,fast):
        with pytest.raises(IRError): fn(ir,{'close':panel()},{'C':'close'})

def test_trailing_mean_reference_and_truncation_are_causal():
    c=panel();ir=parse_formula(r'F_{i,t}=\frac{1}{3}\sum_{k=0}^{2}C_{i,t-k}')['ir']
    got=fast(ir,{'close':c},{'C':'close'})
    assert got.iloc[2,0]==pytest.approx(37/3)
    full=fast(ir,{'close':c},{'C':'close'})
    c.iloc[4:]=999
    perturbed=fast(ir,{'close':c},{'C':'close'})
    pd.testing.assert_frame_equal(full.iloc[:4],perturbed.iloc[:4])
