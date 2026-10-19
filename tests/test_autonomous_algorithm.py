"""Offline orchestration tests. Scripted models are not live DeepSeek evidence."""
import numpy as np
import pandas as pd
import pytest

from paper_agent import autonomous_algorithm as aa
from paper_agent.ledger import sha256_obj


def frame(values):
    return pd.DataFrame(values, index=pd.date_range("2020-01-01", periods=len(values)), columns=["A"])


@pytest.mark.parametrize("scale", [1e-3, 1e-9, 1e-12, 1e-15])
def test_offset_signal_cannot_disappear_or_reverse(scale):
    x = np.arange(10).reshape(-1, 1)
    expected = frame(1 + scale*x)
    assert aa.comparison(frame(1-scale*x), expected)
    assert aa.comparison(frame(np.ones_like(x)), expected)
    assert aa.comparison(expected, expected) is None


def contract():
    return dict(inputs=["close"], formula="2 * close", time_semantics="current row", missing_semantics="propagate",
                warmup=1, citations=[dict(page=1, quote="synthetic fixture")])


def test_subnormal_or_rounded_oracle_is_not_a_pass():
    tiny = frame([[1e-320], [2e-320], [3e-320]])
    assert aa.comparison(tiny, tiny) == "INSUFFICIENT_NUMERIC_PRECISION"
    rounded = frame([[1.], [np.nextafter(1., 2.)]])
    assert aa.comparison(rounded, rounded) == "INSUFFICIENT_NUMERIC_PRECISION"


def fixtures():
    x = frame([[1.], [2.], [3.], [4.]])
    return [dict(name="known multiplication", panels={"close": x}, expected=2*x,
                 data_class="synthetic", oracle_basis="exact hand calculation", prefix_cutoffs=[3])]


class Ledger:
    def __init__(self):
        self.artifacts, self.events = {}, []
    def write_artifact(self, path, value, **kw):
        self.artifacts[path] = value
    def event(self, name, value):
        self.events.append((name, value))


def test_repair_uses_same_contract_and_keeps_versions(monkeypatch):
    calls = []
    def scripted(client, ledger, **kwargs):
        calls.append(kwargs)
        return dict(source="WRONG" if len(calls) == 1 else "CORRECT", explanation="synthetic", unresolved=[]), {"record": len(calls)}
    def runner(source, panels, **kwargs):
        return panels["close"] * (3 if source == "WRONG" else 2)
    monkeypatch.setattr(aa, "ask_json", scripted)
    ledger = Ledger()
    result = aa.develop(contract(), fixtures(), None, ledger, confirmed_contract_sha256=sha256_obj(contract()), runner=runner)
    assert result["status"] == "SYNTHETIC_VALIDATED"
    assert len(result["history"]) == 2 and len(calls) == 2
    assert "VALUE_MISMATCH" in calls[1]["user"]
    assert len(ledger.artifacts) == 4
    assert all(c["repair"] == 1 for c in calls)
    assert not result["trusted_ir_certified"]


def test_definition_question_does_not_execute(monkeypatch):
    monkeypatch.setattr(aa, "ask_json", lambda *a, **k: (dict(source="", explanation="", unresolved=["calendar cutoff?"]), {"record": 1}))
    def forbidden(*a, **k):
        pytest.fail("must not execute with unresolved semantics")
    result = aa.develop(contract(), fixtures(), None, Ledger(), confirmed_contract_sha256=sha256_obj(contract()), runner=forbidden)
    assert result["status"] == "NEEDS_DEFINITION"


def test_no_evaluation_data_can_enter_repair(monkeypatch):
    cases = fixtures()
    cases[0]["data_class"] = "2026_rolling_test"
    with pytest.raises(ValueError, match="SYNTHETIC"):
        aa.develop(contract(), cases, None, Ledger(), confirmed_contract_sha256=sha256_obj(contract()))


def test_repair_limit_is_not_reset(monkeypatch):
    count = []
    def scripted(*a, **k):
        count.append(1)
        return dict(source="WRONG", explanation="", unresolved=[]), {"record": len(count)}
    monkeypatch.setattr(aa, "ask_json", scripted)
    result = aa.develop(contract(), fixtures(), None, Ledger(), confirmed_contract_sha256=sha256_obj(contract()),
                        runner=lambda s, p, **k: p["close"])
    assert result["status"] == "VALIDATION_FAILED" and len(count) == 3


def test_future_dependence_is_detected():
    cases = fixtures()
    cases[0]["expected"] = cases[0]["panels"]["close"] * 4
    result = aa.validate_candidate("scripted", cases, runner=lambda s, p, **k: p["close"] * len(p["close"]))
    assert not result["passed"]
    assert any(f["code"].startswith("PREFIX_") for f in result["failures"])


@pytest.mark.parametrize("fixed", [True, False])
def test_real_json_path_repairs_missing_unresolved_once(tmp_path, fixed):
    import json
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ModelFailure
    class Client:
        def __init__(self):self.calls=[]
        def raw(self, messages, **kwargs):
            self.calls.append(messages)
            obj=dict(source="CORRECT",explanation="synthetic")
            if fixed and len(self.calls)>1:obj['unresolved']=[]
            return dict(content=json.dumps(obj),usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
    client=Client();ledger=TaskLedger(tmp_path,goal='synthetic JSON repair')
    executed=[]
    def runner(source, panels, **kwargs):
        executed.append(source);return panels['close']*2
    if fixed:
        result=aa.develop(contract(),fixtures(),client,ledger,confirmed_contract_sha256=sha256_obj(contract()),runner=runner)
        assert result['status']=='SYNTHETIC_VALIDATED'
    else:
        with pytest.raises(ModelFailure,match='unresolved'):
            aa.develop(contract(),fixtures(),client,ledger,confirmed_contract_sha256=sha256_obj(contract()),runner=runner)
        assert not executed
    assert len(client.calls)==2 and ledger.state['usage']['model_calls']==2
    assert 'unresolved' in client.calls[1][-1]['content']


def test_independent_reference_repairs_missing_unresolved_without_candidate_code(tmp_path):
    import json
    from paper_agent.ledger import TaskLedger
    from paper_agent.autonomous_route import build
    class Client:
        def __init__(self):self.calls=[]
        def raw(self,messages,**kwargs):
            self.calls.append(messages)
            obj=dict(source='',explanation='requires a missing assumption')
            if len(self.calls)>1:obj['unresolved']=['missing computational choice']
            return dict(content=json.dumps(obj),usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
    client=Client();ledger=TaskLedger(tmp_path,goal='independent reference repair')
    with pytest.raises(ValueError,match='INDEPENDENT_REFERENCE_NEEDS_DEFINITION'):
        build({'autonomous_contract':contract()},client,ledger)
    assert len(client.calls)==2 and ledger.state['usage']['model_calls']==2
    assert json.loads(client.calls[0][1]['content'])==contract()
