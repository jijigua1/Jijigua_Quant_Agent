from dataclasses import asdict, replace
import json

import pytest

from research_agent.app import build, load_policy
from research_agent.cli import DEMO_GOAL
from research_agent.contracts import canonical, parse_json
from research_agent.llm import Capabilities, ModelError, ModelResponse, ProviderConfig, Redactor, ToolCall
from research_agent.providers.mock import MockProvider
from research_agent.security import Budget, Denied
from research_agent.store import LedgerError, StateConflict
from research_agent.tools import ToolRegistry, mock_registry


class SelectingProvider(MockProvider):
    def __init__(self, call):
        super().__init__()
        self.call = call

    def complete(self, request):
        if request.tools:
            return ModelResponse(tool_calls=(self.call,))
        return super().complete(request)


def test_complete_mock_research(app):
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "COMPLETED"
    assert state.result["mode"] == "synthetic"
    assert state.result["factor_experiments"] == 2
    assert [x["parameters"].get("lookback") for x in state.experiments] == [None, 3, 5]
    assert state.counters == {"iterations": 4, "model_calls": 7, "tool_calls": 3}
    for experiment in state.experiments:
        assert experiment["hypothesis"] and experiment["change_reason"]
        assert len(experiment["code_sha256"]) == 64
        assert experiment["result"]["data"]["mode"] == "synthetic"
    kinds = [x["kind"] for x in app.store.events(state.id)]
    assert kinds[0] == "AUTHORIZATION_ISSUED"
    assert kinds.count("RESEARCH_PLAN") == 4
    assert kinds.count("AUTHORIZATION_ALLOWED") == 3
    assert kinds.count("EXPERIMENT_RECORDED") == 3


def test_checkpoint_resume_without_repeating_experiments(tmp_path):
    first = build(tmp_path)
    state = first.run(first.create(DEMO_GOAL).id, max_steps=1)
    assert state.status == "PAUSED" and len(state.experiments) == 1
    restored = build(tmp_path).run(state.id)
    assert restored.status == "COMPLETED"
    assert restored.counters["tool_calls"] == 3
    assert len(restored.experiments) == 3


def test_semantic_experiments_reproducible(tmp_path):
    a = build(tmp_path / "a")
    b = build(tmp_path / "b")
    x = a.run(a.create(DEMO_GOAL).id)
    y = b.run(b.create(DEMO_GOAL).id)
    assert x.experiments == y.experiments
    assert x.result == y.result


def test_provider_switch_does_not_change_workflow(tmp_path):
    a = build(tmp_path / "a", "mock")
    b = build(tmp_path / "b", "mock_alt")
    x = a.run(a.create(DEMO_GOAL).id)
    y = b.run(b.create(DEMO_GOAL).id)
    assert (x.provider, x.model) != (y.provider, y.model)
    assert x.result == y.result and x.experiments == y.experiments
    assert next(e for e in b.store.events(y.id) if e['kind']=='MODEL_ATTEMPT')["payload"]["provider_config"]["provider"] == "mock-alt"


@pytest.mark.parametrize("field", ["max_iterations", "max_model_calls", "max_tool_calls"])
def test_budget_exhaustion_stops(app, field):
    budget = replace(Budget(), **{field: 1})
    state = app.run(app.create(DEMO_GOAL, budget).id)
    assert state.status == "BUDGET_EXHAUSTED"
    assert state.counters[field[4:]] <= 1
    assert app.run(state.id).counters == state.counters


def test_requested_budget_cannot_expand_policy(app):
    state = app.create(DEMO_GOAL, Budget(99, 99, 99))
    assert state.budget == asdict(app.policy.budget.intersect(app.skill.budget))


@pytest.mark.parametrize("call,code", [
    (ToolCall("forged", "shell", {"command": "echo unsafe"}), "UNKNOWN_TOOL"),
    (ToolCall("forged", "query_mock_data", {"resource_id": "mock:ohlcv-v1", "approved": True}), "INVALID_PARAMETERS"),
    (ToolCall("forged", "compute_mock_factor", {"resource_id": "mock:ohlcv-v1", "lookback": 3, "python": "print(1)"}), "INVALID_PARAMETERS"),
])
def test_forgery_and_unauthorized_operation_denied(tmp_path, call, code):
    app = build(tmp_path, provider=SelectingProvider(call))
    state = app.run(app.create(DEMO_GOAL).id)
    expected_status = "INVALID_PARAMETERS" if code == "INVALID_PARAMETERS" else "AUTHORIZATION_DENIED"
    assert state.status == expected_status and state.error["code"] == code
    assert state.counters["tool_calls"] == 1 and not state.experiments
    event_kind = "TOOL_PARAMETERS_REJECTED" if code == "INVALID_PARAMETERS" else "AUTHORIZATION_DENIED"
    assert any(x["kind"] == event_kind for x in app.store.events(state.id))


@pytest.mark.parametrize("path", ["../../secret", "/home/other/data", "C:\\secret", "mock:../", "..%2fsecret"])
def test_illegal_path_is_not_a_resource(tmp_path, path):
    app = build(tmp_path, provider=SelectingProvider(ToolCall("bad_path", "query_mock_data", {"resource_id": path})))
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "INVALID_PARAMETERS" and state.error["code"] == "INVALID_PARAMETERS"
    assert not state.experiments


def test_tool_error_is_distinct(tmp_path):
    registry = mock_registry()
    def fail(**kwargs):
        raise RuntimeError("DUMMY_PRIVATE_ERROR")
    tools = ToolRegistry([replace(x, handler=fail) if x.id == "query_mock_data" else x for x in registry._tools.values()])
    app = build(tmp_path, tools=tools)
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "TOOL_ERROR"
    assert "DUMMY_PRIVATE_ERROR" not in canonical(app.store.events(state.id))


def test_timeout_retry_is_counted(tmp_path):
    class TimeoutOnce(MockProvider):
        def __init__(self):
            super().__init__()
            self.calls = 0
        def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ModelError("TIMEOUT", True)
            return super().complete(request)
    app = build(tmp_path, provider=TimeoutOnce())
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "COMPLETED" and state.counters["model_calls"] == 8
    assert any(x["kind"] == "MODEL_FAILURE" for x in app.store.events(state.id))


def test_retry_stops_at_budget(tmp_path):
    class TimeoutAlways(MockProvider):
        def complete(self, request):
            raise ModelError("TIMEOUT", True)
    app = build(tmp_path, provider=TimeoutAlways())
    state = app.run(app.create(DEMO_GOAL, Budget(max_model_calls=1)).id)
    assert state.status == "BUDGET_EXHAUSTED" and state.counters["model_calls"] == 1


def test_model_error_is_terminal(tmp_path):
    class Broken(MockProvider):
        def complete(self, request):
            raise ModelError("AUTHENTICATION")
    app = build(tmp_path, provider=Broken())
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "MODEL_ERROR" and state.counters["model_calls"] == 1


def test_missing_provider_capability_refuses_task(tmp_path):
    provider = MockProvider()
    provider.capabilities = Capabilities(False, True)
    app = build(tmp_path, provider=provider)
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "MODEL_ERROR" and state.error["code"] == "CAPABILITY_TOOL_CALLING_MISSING"
    assert state.counters["tool_calls"] == 0


def test_model_cannot_approve_itself(tmp_path):
    class Forged(MockProvider):
        def complete(self, request):
            response = super().complete(request)
            if request.output_schema:
                plan = parse_json(response.content)
                plan["approved"] = True
                return replace(response, content=canonical(plan))
            return response
    app = build(tmp_path, provider=Forged())
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "MODEL_ERROR" and not state.experiments
    assert app.store.authorization(state.id).authority == "offline_mock_policy"


def test_policy_approval_cannot_be_disabled_by_skill(tmp_path):
    app = build(tmp_path, policy=replace(load_policy(), requires_approval=True))
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "AUTHORIZATION_DENIED"
    assert state.error["code"] == "INDEPENDENT_APPROVAL_REQUIRED"


def test_config_change_refuses_resume(tmp_path):
    a = build(tmp_path)
    paused = a.run(a.create(DEMO_GOAL).id, max_steps=1)
    state = build(tmp_path, "mock_alt").run(paused.id)
    assert state.status == "BLOCKED_CONFIG" and state.counters["tool_calls"] == 1


def test_active_task_not_taken_over(app):
    state = app.create(DEMO_GOAL)
    state.status = "RUNNING"
    app.store.save(state, "TEST_RUNNING", {})
    with pytest.raises(StateConflict):
        app.run(state.id)
    assert app.store.load(state.id).status == "RUNNING"


def test_uncertain_tool_not_replayed(app):
    state = app.create(DEMO_GOAL)
    state.status = "INTERRUPTED"
    state.pending = {"kind": "tool", "call_id": "uncertain"}
    app.store.save(state, "TEST_INTERRUPT", {})
    state = app.run(state.id)
    assert state.status == "BLOCKED_RECOVERY" and not state.experiments


def test_audit_failure_prevents_model_call(app, monkeypatch):
    calls = []
    state = app.create(DEMO_GOAL)
    monkeypatch.setattr(app.provider, "complete", lambda req: calls.append(req))
    monkeypatch.setattr(app.store, "save", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(LedgerError):
        app.run(state.id)
    assert calls == []


def test_root_start_is_refused_before_state_write(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    with pytest.raises(Denied, match="ROOT_AGENT_DENIED"):
        build(tmp_path / "not_created")
    assert not (tmp_path / "not_created").exists()


def test_secret_canary_not_persisted(tmp_path):
    canary = "DUMMY_SECRET_CANARY_123456"
    app = build(tmp_path, redactor=Redactor([canary]))
    state = app.run(app.create(DEMO_GOAL + canary).id)
    assert state.status == "COMPLETED"
    assert canary not in canonical(asdict(state))
    assert canary not in canonical(app.store.events(state.id))


def test_live_provider_not_enabled(tmp_path):
    with pytest.raises(Denied, match="LIVE_PROVIDER_NOT_ENABLED"):
        build(tmp_path, "deepseek")


@pytest.mark.parametrize("varying", [True, False])
def test_endless_model_plan_is_bounded(tmp_path, varying):
    class Endless(MockProvider):
        def complete(self, request):
            if request.output_schema:
                return ModelResponse(canonical({"action": "continue", "hypothesis": "Mock endless test", "change_reason": "Test budget termination", "summary": ""}))
            index = sum(x.role.value == "tool" for x in request.messages)
            if varying:  # new arguments every step: only the budget bounds it
                return ModelResponse(tool_calls=(ToolCall("vary_" + str(index), "compute_mock_factor", {"resource_id": "mock:ohlcv-v1", "lookback": 2 + index}),))
            return ModelResponse(tool_calls=(ToolCall("repeat_" + str(index), "query_mock_data", {"resource_id": "mock:ohlcv-v1"}),))
    app = build(tmp_path, provider=Endless())
    state = app.run(app.create(DEMO_GOAL).id)
    if varying:
        assert state.status == "BUDGET_EXHAUSTED"
        assert state.counters == {"iterations": 4, "model_calls": 8, "tool_calls": 4}
    else:  # an identical call adds no information and is stopped before it runs again
        assert state.status == "BLOCKED_NO_PROGRESS" and len(state.experiments) == 1
        assert state.counters == {"iterations": 2, "model_calls": 4, "tool_calls": 2}


def test_premature_summary_cannot_replace_experiment_evidence(tmp_path):
    class Early(MockProvider):
        def complete(self, request):
            return ModelResponse(canonical({"action": "complete", "hypothesis": "Mock hypothesis", "change_reason": "Premature claim", "summary": "Claim success"}))
    app = build(tmp_path, provider=Early())
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "INVALID_RESULT" and not state.result


def test_secret_error_code_not_in_state_or_logs(tmp_path):
    canary = "DUMMY_EXCEPTION_KEY_123456"
    class Broken(MockProvider):
        def complete(self, request):
            raise ModelError(canary)
    app = build(tmp_path, provider=Broken(), redactor=Redactor([canary]))
    state = app.run(app.create("mock").id)
    assert state.status == "MODEL_ERROR"
    assert canary not in canonical(asdict(state))
    assert canary not in canonical(app.store.events(state.id))
    assert canary not in app.store.path.read_bytes().decode("utf-8", errors="ignore")


def test_secret_in_tool_call_id_is_not_persisted(tmp_path):
    canary = "DUMMY_CALL_ID_KEY_123456"
    provider = SelectingProvider(ToolCall(canary, "query_mock_data", {"resource_id": "mock:ohlcv-v1"}))
    app = build(tmp_path, provider=provider, redactor=Redactor([canary]))
    state = app.run(app.create("mock").id)
    assert state.status == "MODEL_ERROR"
    assert canary not in canonical(asdict(state))
    assert canary not in canonical(app.store.events(state.id))


def test_authorization_audit_failure_prevents_tool_handler(app, monkeypatch):
    calls = []
    original = app.store.save
    def save(state, kind, payload):
        if kind == "AUTHORIZATION_ALLOWED":
            raise OSError("audit unavailable")
        return original(state, kind, payload)
    monkeypatch.setattr(app.store, "save", save)
    monkeypatch.setattr(app.tools, "execute", lambda *a, **k: calls.append(1))
    state = app.run(app.create("mock").id)
    assert state.status == "AUDIT_ERROR" and calls == []
