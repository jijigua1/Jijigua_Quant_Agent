"""Isolated reviewed Pyx ledger subset, not qualification of the whole engine."""
from decimal import Decimal
from types import SimpleNamespace
import hashlib
from pathlib import Path
import importlib.util
import pandas as pd
import numpy as np
import pytest

if not (Path(__file__).parent/'fixtures/pyx_ledger.py').is_file():
    pytest.skip('Third-party fixture redistribution rights not established',allow_module_level=True)
spec=importlib.util.spec_from_file_location('reviewed_pyx',Path(__file__).parent/'fixtures/pyx_ledger.py')
pyx=importlib.util.module_from_spec(spec);spec.loader.exec_module(pyx)

def execute(trades,prices,tradable,shares,cash):
    plan=SimpleNamespace(decision_date='2026-01-05',trade_shares=pd.Series(trades))
    config=SimpleNamespace(buy_fee_rate=.001,sell_fee_rate=.002)
    return pyx._execute_plan(plan,'2026-01-06',pd.Series(prices),pd.Series(tradable),pd.Series(shares,dtype=int),cash,config)

def test_manual_decimal_cash_holdings_and_costs():
    s,c,r=execute({'000001':100},{'000001':10},{'000001':True},{},2000)
    assert s['000001']==100 and r[0]['status']=='FILLED'
    assert c==pytest.approx(float(Decimal(2000)-Decimal(100)*Decimal(10)*Decimal('1.001')),abs=1e-12)
    s,c,r=execute({'000001':-100},{'000001':11},{'000001':True},s.to_dict(),c)
    assert s['000001']==0 and c==pytest.approx(2096.8)
    assert c==pytest.approx(float(Decimal(999)+Decimal(100)*Decimal(11)*Decimal('.998')),abs=1e-12)

@pytest.mark.parametrize('prices,tradable,shares,cash,status',[
 ({'000001':np.nan},{'000001':True},{},2000,'REJECTED_INVALID_VWAP'),
 ({'000001':0},{'000001':True},{},2000,'REJECTED_INVALID_VWAP'),
 ({'000001':10},{'000001':False},{},2000,'REJECTED_UNTRADABLE'),
 ({'000001':10},{'000001':np.nan},{},2000,'REJECTED_UNTRADABLE'),
 ({'000001':10},{'000001':True},{},1000,'REJECTED_INSUFFICIENT_CASH'),
])
def test_rejections_preserve_cash_and_positions(prices,tradable,shares,cash,status):
    s,c,r=execute({'000001':100},prices,tradable,shares,cash)
    assert c==cash and s.sum()==0 and r[0]['filled_shares']==0 and r[0]['status']==status

def test_sell_rejection_keeps_held_shares():
    s,c,r=execute({'000001':-100},{'000001':10},{'000001':False},{'000001':100},5)
    assert s['000001']==100 and c==5

def test_sells_before_buys_and_deterministic_cash():
    args=({'000002':100,'000001':-100},{'000001':10,'000002':9},{'000001':True,'000002':True},{'000001':100},0)
    a=execute(*args);b=execute(*args)
    pd.testing.assert_series_equal(a[0],b[0]);assert a[1:]==b[1:]
    assert [x['side'] for x in a[2]]==['SELL','BUY'] and a[1]==pytest.approx(97.1)

def test_unsorted_axes_normalized_in_pyx():
    out=pyx._normalize_columns(pd.DataFrame([[2],[1]],index=['2026-01-06','2026-01-05'],columns=[1]),'test')
    assert list(out.index)==['2026-01-05','2026-01-06'] and list(out.columns)==['000001']

def test_missing_nav_refused_not_zero_return():
    with pytest.raises(ValueError):pyx._calculate_performance(pd.DataFrame({'date':['2026-01-05'],'nav':[np.nan]}),pd.DataFrame())

def test_independent_qrtk_next_session_reference_ledger_matches():
    import qrtk
    days=pd.bdate_range('2026-01-05',periods=3)
    price=pd.DataFrame({'000001':[10.,10.,11.]},index=days)
    orders=pd.DataFrame([dict(signal_date=days[0],code='000001',side='buy',shares=100,value=np.nan),
                         dict(signal_date=days[1],code='000001',side='sell',shares=100,value=np.nan)])
    out=qrtk.run_backtest(orders,price,price,initial_cash=2000,
        costs=qrtk.CostModel(commission_rate=.001,min_commission=0,stamp_duty_rate=.001))
    assert out.daily.iloc[-1]['cash']==pytest.approx(2096.8)
    assert qrtk.reconcile(out)['ok']
    assert list(out.trades['date'])==list(days[1:])
