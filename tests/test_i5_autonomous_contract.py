from copy import deepcopy

import pytest

from paper_agent import autonomous_route as route
from research_agent.contracts import ContractError, validate


class Ledger:
    def __init__(self):self.items={}
    def read_artifact(self,name):return self.items.get(name)
    def write_artifact(self,name,value):self.items[name]=deepcopy(value)


class Evidence:
    by_id={'P0001':{'text':'Synthetic exact definition.'}}
    def verify_quote(self,passage,quote):
        return {'passage':passage,'quote':quote} if passage=='P0001' and quote=='Synthetic exact definition.' else None


def setup():
    citation={'passage':'P0001','quote':'Synthetic exact definition.'}
    plan={'factor':'synthetic','route':'algorithm','status':'AWAITING_USER_DECISION','definition_sha256':'a'*64,
          'hard_stops':[],'choices':{'horizon':{'n':1}},'substitutions':[]}
    understanding={'factors':[{'name':'synthetic','formula':{'citations':[citation]}}]}
    profile={'fields':['close','amount'],'splits':{}}
    contract={'formula':'close','inputs':['close'],'warmup':1,'time_semantics':'after close','missing_semantics':'propagate',
        'steps':['return close'],'citations':[citation],'unresolved':[]}
    return plan,understanding,profile,contract


def test_scope_is_passed_and_cached_separately_and_exact_fields_required(monkeypatch):
    import json
    plan,understanding,profile,contract=setup();calls=[];ledger=Ledger()
    def model(*args,**kwargs):
        calls.append(kwargs)
        return deepcopy(contract),{}
    monkeypatch.setattr(route,'ask_json',model)
    for scope in ('original raw prices','original raw prices','changed timing'):
        result=route.propose(plan,understanding,Evidence(),profile,object(),ledger,user_request=scope)
        assert result['route']=='autonomous_python'
    assert len(calls)==2
    assert json.loads(calls[0]['user'])['user_request']=='original raw prices'
    assert calls[0]['schema']['properties']['inputs']['items']['enum']==['close','amount']
    with pytest.raises(ContractError,match='enum'):
        validate(contract|{'inputs':['close (raw price)']},calls[0]['schema'])


def test_bad_citation_is_a_structured_stop_not_an_unclassified_exception(monkeypatch):
    plan,understanding,profile,contract=setup()
    contract['citations'][0]['quote']='Invented quotation'
    monkeypatch.setattr(route,'ask_json',lambda *a,**k:(contract,{}))
    result=route.propose(plan,understanding,Evidence(),profile,object(),Ledger())
    assert result['status']=='BLOCKED'
    assert result['hard_stops'][-1]['code']=='AUTONOMOUS_CONTRACT_EVIDENCE_INVALID'


def test_nested_factor_citations_are_supplied_as_verifiable_passages(monkeypatch):
    import json
    plan,understanding,profile,contract=setup()
    understanding['factors'][0]['window']={'citations':[{'passage':'P0069','quote':'Annual sample condition.'}]}
    evidence=Evidence();evidence.by_id=dict(evidence.by_id,P0069={'text':'Annual sample condition.'})
    calls=[]
    def model(*args,**kwargs):
        calls.append(kwargs);return deepcopy(contract),{}
    monkeypatch.setattr(route,'ask_json',model)
    route.propose(plan,understanding,evidence,profile,object(),Ledger())
    assert {'id':'P0069','text':'Annual sample condition.'} in json.loads(calls[0]['user'])['passages']
    enum=calls[0]['schema']['properties']['citations']['items']['properties']['passage']['enum']
    assert 'P0069' in enum and 'P9999' not in enum


@pytest.mark.parametrize('corrected', [True, False])
def test_nonverbatim_quote_has_one_bounded_repair_and_preserves_blocker_provenance(monkeypatch, corrected):
    import json
    plan,understanding,profile,contract=setup()
    plan['hard_stops']=[{'code':'CALENDAR_WINDOW_UNSUPPORTED','detail':'legacy capability'}]
    calls=[]
    def model(*args,**kwargs):
        calls.append(kwargs)
        obj=deepcopy(contract)
        if len(calls)==1 or not corrected:obj['citations'][0]['quote']='Paraphrased evidence'
        return obj,{}
    monkeypatch.setattr(route,'ask_json',model)
    result=route.propose(plan,understanding,Evidence(),profile,object(),Ledger(),user_request='exact requested definition')
    assert len(calls)==2
    retry=json.loads(calls[1]['user'])
    assert retry['user_request']=='exact requested definition'
    assert retry['validation_errors']['nonverbatim_citations'][0]['quote']=='Paraphrased evidence'
    if corrected:
        assert result['status']=='AWAITING_USER_DECISION' and result['route']=='autonomous_python'
    else:
        assert result['status']=='BLOCKED'
        assert [x['code'] for x in result['hard_stops']]==['AUTONOMOUS_CONTRACT_EVIDENCE_INVALID']
        assert result['original_hard_stops']==plan['hard_stops']


@pytest.mark.parametrize('resolved',[True,False])
def test_explicit_user_choices_get_one_review_but_missing_choices_still_block(monkeypatch,resolved):
    plan,understanding,profile,contract=setup();calls=[]
    def model(*a,**kw):
        calls.append(kw)
        out=deepcopy(contract)
        out['unresolved']=[] if len(calls)==2 and resolved else ['Whether to reinstate a user-excluded filter']
        return out,{}
    monkeypatch.setattr(route,'ask_json',model)
    result=route.propose(plan,understanding,Evidence(),profile,object(),Ledger(),user_request='Exclude that sample filter for this run')
    assert len(calls)==2 and calls[1]['purpose']=='autonomous_choices_review'
    assert result['status']==('AWAITING_USER_DECISION' if resolved else 'BLOCKED')
    if not resolved:assert result['hard_stops'][0]['code']=='ALGORITHM_DEFINITION_REQUIRED'
