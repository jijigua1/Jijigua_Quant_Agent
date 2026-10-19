"""Candidate6 recovery, design E: one cumulative request + token budget across sessions and processes, checked before every
HTTP send of the real DeepSeekAdapter (a fake transport counts sends; no network).

Recorded failures: C9 audit (a new session in the same state directory made request 51 past a 50-turn cap), C10-D04
(total_tokens=1,000,000 reported, the next send still went out), C11-D02 (usage parts 20000+1 with total missing or =1:
the next send went out).
"""
import json
import multiprocessing
import os
import sqlite3

import pytest

from research_agent.api_budget import Budget, charged, create_campaign
from research_agent.llm import Message, ModelError, ModelRequest, ProviderConfig, Role
from research_agent.providers.deepseek import DeepSeekAdapter


class Secrets:
    def resolve(self, reference):
        return "DUMMY_KEY_FOR_FAKE_TRANSPORT_ONLY"


class Transport:
    enabled, is_live = True, False

    def __init__(self, usages):
        self.usages, self.sends = list(usages), 0

    def send(self, payload, headers, timeout, stream):
        self.sends += 1
        usage = self.usages[min(self.sends - 1, len(self.usages) - 1)]
        yield json.dumps({"id": "r%d" % self.sends, "model": "deepseek-flash", "usage": usage,
                          "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}).encode()


def adapter(tmp_path, monkeypatch, usages, *, max_tokens=12000, max_requests=50, campaign="c1", create=True, retries=0):
    db = tmp_path / "budget.sqlite3"
    if create:
        create_campaign(db, campaign, max_requests=max_requests, max_tokens=max_tokens)
    monkeypatch.setenv("QRA_API_BUDGET_DB", str(db))
    monkeypatch.setenv("QRA_API_BUDGET_CAMPAIGN", campaign)
    t = Transport(usages)
    a = DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", max_output_tokens=100, max_retries=retries,
                                       credential_ref="env:QRA_TEST_KEY"), Secrets(), t)
    return a, t, db


REQ = ModelRequest((Message(Role.USER, "hello"),))


@pytest.mark.parametrize("case,usage", [
    ("c10_d04_total_over_limit", {"total_tokens": 1_000_000}),
    ("c11_d02_parts_without_total", {"prompt_tokens": 20000, "completion_tokens": 1}),
    ("c11_d02_parts_with_contradicting_total", {"prompt_tokens": 20000, "completion_tokens": 1, "total_tokens": 1}),
])
def test_observed_overspend_freezes_the_campaign_before_the_next_send(tmp_path, monkeypatch, case, usage):
    a, t, db = adapter(tmp_path, monkeypatch, [usage])
    a.complete(REQ)
    with pytest.raises(ModelError, match="API_BUDGET_FROZEN"):
        a.complete(REQ)
    assert t.sends == 1 and Budget(db, "c1").state()["frozen"] == 1
    # every other process / session / adapter sees the same frozen campaign
    b, t2, _ = adapter(tmp_path, monkeypatch, [{"total_tokens": 1}], create=False)
    with pytest.raises(ModelError, match="API_BUDGET_FROZEN"):
        b.complete(REQ)
    assert t2.sends == 0


def test_request_limit_holds_across_sessions_and_adapters(tmp_path, monkeypatch):
    a, t, db = adapter(tmp_path, monkeypatch, [{"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}], max_requests=3)
    for _ in range(3):
        a.complete(REQ)
    b, t2, _ = adapter(tmp_path, monkeypatch, [{"total_tokens": 10}], create=False)     # a "new session"
    with pytest.raises(ModelError, match="API_BUDGET_EXHAUSTED"):
        b.complete(REQ)
    assert t.sends == 3 and t2.sends == 0 and Budget(db, "c1").state()["used_requests"] == 3


def test_unknown_or_malformed_usage_keeps_the_conservative_reservation():
    assert charged(500, None) == (500, True)
    assert charged(500, {}) == (500, True)
    assert charged(500, {"prompt_tokens": -5, "completion_tokens": "x"}) == (500, True)
    assert charged(500, {"total_tokens": 10}) == (500, False)                       # never below the reservation
    assert charged(500, {"prompt_tokens": 400, "completion_tokens": 300}) == (700, False)
    assert charged(500, {"prompt_tokens": 400, "completion_tokens": 300, "total_tokens": 1})[0] == 700
    assert charged(500, {"total_tokens": True})[0] == 500                           # a bool is not a count


def test_a_reservation_is_made_before_the_send_and_never_refunded(tmp_path, monkeypatch):
    class Broken(Transport):
        def send(self, *a, **k):
            self.sends += 1
            raise TimeoutError()
            yield b""
    a, t, db = adapter(tmp_path, monkeypatch, [{"total_tokens": 1}])
    a.transport = Broken([None])
    with pytest.raises(ModelError):
        a.complete(REQ)
    s = Budget(db, "c1").state()
    assert s["used_requests"] == 1 and s["used_tokens"] > 100                      # charged although nothing came back
    rows = sqlite3.connect(db).execute("select state from ticket").fetchall()
    assert rows == [("RESERVED",)]


def test_a_configured_budget_never_falls_back_to_unlimited(tmp_path, monkeypatch):
    a, t, _ = adapter(tmp_path, monkeypatch, [{"total_tokens": 1}], create=False)   # file absent
    with pytest.raises(ModelError, match="API_BUDGET_MISSING"):
        a.complete(REQ)
    create_campaign(tmp_path / "budget.sqlite3", "other", max_requests=5, max_tokens=5000)
    with pytest.raises(ModelError, match="API_BUDGET_CAMPAIGN_MISSING"):
        a.complete(REQ)
    with pytest.raises(ValueError, match="never reset"):
        create_campaign(tmp_path / "budget.sqlite3", "other", max_requests=50, max_tokens=50000)
    assert t.sends == 0


@pytest.mark.parametrize("budget,sends", [(True, 1), (False, 3)])
def test_with_a_budget_the_runtime_makes_no_automatic_retry(tmp_path, monkeypatch, budget, sends):
    """The real ModelRuntime retry loop over the real adapter; the transport times out (a retryable error)."""
    from types import SimpleNamespace
    from research_agent.runtime import ModelRuntime

    class Timeout(Transport):
        def send(self, *a, **k):
            self.sends += 1
            raise TimeoutError()
            yield b""
    a, _, _ = adapter(tmp_path, monkeypatch, [None], retries=2)
    if not budget:
        a.budget = None
    a.transport = t = Timeout([None])
    rt = ModelRuntime(a, SimpleNamespace(save=lambda *x: None))
    state = SimpleNamespace(counters={"model_calls": 0}, budget={"max_model_calls": 10}, pending=None,
                            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "unknown_calls": 0},
                            stage="s", goal="", messages=[], plan=None, result=None, error=None, experiments=[])
    with pytest.raises(ModelError):
        rt._model(state, REQ)
    assert t.sends == sends


def _race(db, n, out):
    os.environ["QRA_API_BUDGET_DB"], os.environ["QRA_API_BUDGET_CAMPAIGN"] = str(db), "race"
    b = Budget(db, "race")
    ok = 0
    for _ in range(n):
        try:
            b.reserve(100)
            ok += 1
        except ModelError:
            pass
    out.put(ok)


def test_concurrent_processes_cannot_overrun_the_limit(tmp_path):
    db = tmp_path / "race.sqlite3"
    create_campaign(db, "race", max_requests=25, max_tokens=10 ** 9)
    q = multiprocessing.get_context("spawn").Queue()
    procs = [multiprocessing.get_context("spawn").Process(target=_race, args=(db, 20, q)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
    granted = sum(q.get(timeout=10) for _ in procs)
    assert granted == 25 and Budget(db, "race").state()["used_requests"] == 25


@pytest.mark.parametrize('request_limit,expected_sends', [(2, 2), (1, 1)])
def test_schema_correction_uses_same_campaign_and_cannot_cross_limit(tmp_path, monkeypatch, request_limit, expected_sends):
    from types import SimpleNamespace
    from research_agent.runtime import ModelRuntime

    a, _, db = adapter(tmp_path, monkeypatch, [None], retries=2, max_requests=request_limit, max_tokens=50000)
    class FormatReplies(Transport):
        def __init__(self):
            self.sends=0;self.payloads=[]
        def send(self, payload, headers, timeout, stream):
            self.payloads.append(payload);self.sends+=1
            content={'ok':True} if self.sends==1 else {'ok':True,'reason':''}
            yield json.dumps({'id':str(self.sends),'model':'deepseek-flash','usage':{'total_tokens':5},
                'choices':[{'message':{'role':'assistant','content':json.dumps(content)},'finish_reason':'stop'}]}).encode()
    a.transport=t=FormatReplies()
    events=[]
    rt=ModelRuntime(a,SimpleNamespace(save=lambda state,kind,data:events.append((kind,data))))
    state=SimpleNamespace(counters={'model_calls':0},budget={'max_model_calls':4},pending=None,
        usage={'input_tokens':0,'output_tokens':0,'total_tokens':0,'unknown_calls':0},
        stage='s',goal='',messages=[],plan=None,result=None,error=None,experiments=[])
    request=ModelRequest((Message(Role.USER,'format check'),),output_schema={'type':'object',
        'properties':{'ok':{'type':'boolean'},'reason':{'type':'string'}},'required':['ok','reason'],'additionalProperties':False})
    if request_limit==1:
        with pytest.raises(ModelError,match='API_BUDGET_EXHAUSTED'):
            rt._model(state,request)
    else:
        assert json.loads(rt._model(state,request).content)=={'ok':True,'reason':''}
        assert 'Missing required fields: reason' in t.payloads[1]['messages'][0]['content']
    assert t.sends==expected_sends
    assert Budget(db,'c1').state()['used_requests']==expected_sends
    failure=next(data for kind,data in events if kind=='MODEL_FAILURE')
    assert failure['provider_detail']=='Missing required fields: reason'
