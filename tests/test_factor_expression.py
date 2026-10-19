"""Hand-checkable arithmetic, causality, schemas and resource budgets."""
import numpy as np
import pandas as pd
import pytest

from research_agent.factor_expression import compute,inspect,OPS
from research_agent.contracts import ContractError

def field(name='close'): return {'op':'field','field':name}
def node(op,*args,**kw): return dict(op=op,args=list(args),**kw)
def graph(tree):
    nodes=[]
    def visit(t):
        n={k:v for k,v in t.items() if k!='args'}
        if 'args' in t:n['args']=[visit(a) for a in t['args']]
        nodes.append(n);return len(nodes)-1
    output=visit(tree)
    return dict(nodes=nodes,output=output)
def calc(tree,panels):return compute(graph(tree),panels)

@pytest.fixture
def panels():
    close=pd.DataFrame({'A':[1.,2,4,8,16,32],'B':[2.,3,5,7,11,13]},index=pd.bdate_range('2023-01-02',periods=6))
    return {k:close.copy()*(10 if k=='volume' else 1) for k in ('open','high','low','close','volume')}

@pytest.mark.parametrize('op',sorted(set(OPS)-{'field','constant'}))
def test_every_operator_prefix_invariance(op,panels):
    args=[field()]
    if op in {'add','sub','mul','div','min','max','rolling_corr'}:args.append(field('close'))
    window={'window':2} if op in {'delay','diff','returns','rolling_mean','rolling_std','rolling_rank','rolling_corr'} else {}
    expr=node(op,*args,**window)
    full=calc(expr,panels);prefix=calc(expr,{k:v.iloc[:4] for k,v in panels.items()})
    pd.testing.assert_frame_equal(full.iloc[:4],prefix)

def test_manual_rolling_lag_corr_and_rank(panels):
    p=panels
    assert calc(node('returns',field(),window=2),p).iloc[2,0]==3
    assert calc(node('rolling_mean',field(),window=3),p).iloc[2,0]==pytest.approx(7/3)
    assert calc(node('rolling_std',field(),window=2),p).iloc[1,0]==pytest.approx(1/np.sqrt(2))
    assert calc(node('rolling_corr',field(),field('volume'),window=3),p).iloc[-1,0]==pytest.approx(1)
    assert calc(node('rolling_rank',field(),window=3),p).iloc[-1,0]==1
    p['close'].iloc[1]=[2,2]
    assert list(calc(node('cs_rank',field()),p).iloc[1])==[.75,.75]
    assert calc(node('cs_zscore',field()),p).iloc[1].isna().all()

def test_division_zero_missing_and_future_perturbation(panels):
    expr=node('div',field(),{'op':'constant','value':0})
    assert calc(expr,panels).isna().all().all()
    expr=node('neg',node('returns',field(),window=2))
    old=calc(expr,panels)
    panels['close'].iloc[4:]*=1e6
    pd.testing.assert_frame_equal(old.iloc[:4],calc(expr,panels).iloc[:4])

@pytest.mark.parametrize('expr',[
 {'op':'__import__','field':'os'}, {'op':'field','field':'next_open'},
 {'op':'delay','args':[field()],'window':-1}, {'op':'returns','args':[field()],'window':True},
 {'op':'field','field':'close','path':'/etc/passwd'}, {'op':'constant','value':float('nan')},
 {'op':'rolling_corr','args':[field(),field()],'window':1},
 {'op':'add','args':[field()]}, {'op':'field'}, {'op':'constant','value':1},
])
def test_invalid_expression_rejected(expr):
    with pytest.raises((ContractError,KeyError)):inspect(graph(expr))

def test_depth_and_nodes_rejected():
    expr=field()
    for _ in range(9):expr=node('neg',expr)
    with pytest.raises(ContractError):inspect(graph(expr))

def test_units_cycles_and_forward_edges_denied():
    with pytest.raises(ContractError,match='units'):inspect(graph(node('add',field(),field('volume'))))
    with pytest.raises(ContractError,match='earlier'):inspect(dict(nodes=[field(),dict(op='delay',args=[1],window=2)],output=1))
    expr=field()
    for _ in range(6):expr=node('add',expr,expr)
    with pytest.raises(ContractError):inspect(graph(expr))
