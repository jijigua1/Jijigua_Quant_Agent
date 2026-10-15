from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from research_agent.app import build, load_provider_config
from research_agent.contracts import canonical, parse_json
from research_agent.data import MAX_BYTES, ResourceCatalog
from research_agent.llm import MemorySecrets, ModelResponse, Role, ToolCall
from research_agent.providers.mock import MockProvider
from research_agent.security import Budget, Denied


@pytest.fixture
def published(tmp_path):
    data = tmp_path / "daily.csv"
    data.write_text("date,code,close\n2026-10-08,000001,11.8\n2026-10-09,000001,11.59\n2026-10-09,000002,\n", encoding="utf-8")
    record = {"id": "fixture:daily", "path": str(data), "format": "csv", "source": "fixed test fixture",
              "approval_ref": "test-only operator", "data_kind": "synthetic", "frequency": "daily",
              "timezone": "Asia/Shanghai", "start_date": "2026-10-08", "end_date": "2026-10-09",
              "date_column": "date", "fields": {"date": "date", "code": "string", "close": "float"},
              "adjustment": "unknown", "available_time": "unknown", "sha256": hashlib.sha256(data.read_bytes()).hexdigest()}
    manifest = tmp_path / "resources.json"
    manifest.write_text(json.dumps({"version": "1", "resources": [record]}), encoding="utf-8")
    return manifest, data, record


class DataProvider(MockProvider):
    def complete(self, request):
        count = sum(x.role == Role.TOOL for x in request.messages)
        if request.output_schema:
            return ModelResponse(canonical({"action": "complete" if count == 3 else "continue", "hypothesis": "描述固定输入",
                "change_reason": "用核验后的工具证据回答", "summary": "仅固定测试数据描述，不作回测结论。" if count == 3 else ""}))
        calls = (ToolCall("catalog", "list_resources", {}),
                 ToolCall("describe", "describe_resource", {"resource_id": "fixture:daily"}),
                 ToolCall("slice", "read_data_slice", {"resource_id": "fixture:daily", "fields": ["date", "code", "close"],
                    "start_date": "2026-10-08", "end_date": "2026-10-09", "limit": 2}))
        return ModelResponse(tool_calls=(calls[count],))


def data_app(tmp_path, published, provider=None):
    return build(tmp_path / "state", provider=provider or DataProvider(), profile="development",
                 skill_id="data_query", resources_manifest=published[0])


def test_data_workflow_and_token_unknown_are_explicit(tmp_path, published):
    app = data_app(tmp_path, published)
    state = app.run(app.create("列出并描述数据，然后取两行").id)
    assert state.status == "COMPLETED" and state.result["mode"] == "synthetic"
    assert state.result["analysis_scope"] == "data_description"
    assert state.usage["unknown_calls"] == 7
    assert state.counters["tool_calls"] == 3
    assert state.experiments[1]["result"]["data"]["null_counts"]["close"] == 1
    assert str(published[1]) not in canonical(state.experiments)
    grant = app.store.authorization(state.id)
    assert grant.authority == "development_readonly_policy"


def test_resource_description_and_slice_are_readonly(published):
    catalog = ResourceCatalog(published[0])
    before = published[1].read_bytes()
    description = catalog.describe_resource("fixture:daily")
    assert description["row_count"] == 3 and description["observed_end"] == "2026-10-09"
    assert description["formal_backtest_ready"] is False
    result = catalog.read_data_slice("fixture:daily", ["code", "close"], "2026-10-08", "2026-10-09", 1)
    assert result["truncated"] is True and result["rows"][0]["code"] == "000001"
    assert before == published[1].read_bytes()


@pytest.mark.parametrize("arguments", [
    {"path": "/etc/passwd"}, {"resource_id": "../secret"},
    {"resource_id": "fixture:daily", "approved": True},
])
def test_data_tool_forgery_is_denied(tmp_path, published, arguments):
    app = data_app(tmp_path, published)
    state = app.create("test")
    with pytest.raises(Denied, match="INVALID_PARAMETERS"):
        app.tools.execute(ToolCall("forged", "describe_resource", arguments), policy=app.policy,
                          grant=app.store.authorization(state.id), skill=app.skill)


@pytest.mark.parametrize("change", [{"limit": 201}, {"limit": True}, {"fields": ["secret"]}, {"start_date": "2026-10-07"}])
def test_slice_bounds_are_enforced(tmp_path, published, change):
    app = data_app(tmp_path, published)
    state = app.create("test")
    args = {"resource_id": "fixture:daily", "fields": ["close"], "start_date": "2026-10-08", "end_date": "2026-10-09", "limit": 2, **change}
    with pytest.raises(Denied):
        app.tools.execute(ToolCall("bounds", "read_data_slice", args), policy=app.policy,
                          grant=app.store.authorization(state.id), skill=app.skill)


def test_changed_resource_fingerprint_refused(published):
    catalog = ResourceCatalog(published[0])
    published[1].write_text("changed", encoding="utf-8")
    with pytest.raises(Denied, match="FINGERPRINT_MISMATCH"):
        catalog.describe_resource("fixture:daily")


def test_oversized_resource_refused(published):
    catalog = ResourceCatalog(published[0])
    with published[1].open("wb") as f:
        f.truncate(MAX_BYTES + 1)
    with pytest.raises(Denied, match="SIZE_OR_TYPE"):
        catalog.describe_resource("fixture:daily")


def test_offline_cannot_enable_data(tmp_path, published):
    with pytest.raises(Denied, match="DATA_PROFILE_REQUIRED"):
        build(tmp_path / "state", resources_manifest=published[0], skill_id="data_query")
    assert not (tmp_path / "state").exists()


def test_live_profile_missing_key_is_sanitized_before_state(tmp_path, monkeypatch):
    monkeypatch.delenv("QRA_DEEPSEEK_API_KEY", raising=False)
    from research_agent.llm import ModelError
    with pytest.raises(ModelError, match="CREDENTIAL_MISSING"):
        build(tmp_path / "state", "deepseek", profile="development")
    assert not (tmp_path / "state").exists()


def test_operator_key_is_not_a_model_tool_and_preloaded_for_redaction(tmp_path):
    secret = "DUMMY_DEVELOPMENT_KEY_CANARY"
    app = build(tmp_path, "deepseek", profile="development", secrets=MemorySecrets({"env:QRA_DEEPSEEK_API_KEY": secret}))
    state = app.create("Never retain " + secret)
    assert secret not in canonical(asdict(state))
    assert app.provider.transport.enabled and app.provider.transport.is_live
    assert "credential" not in app.tools.versions
    assert app.provider.config.max_output_tokens == 4096  # v1.0 Beta: paper understanding needs the ProviderConfig maximum
    assert app.provider.config.version == "v1beta-live-1"  # v1.0 Beta provider limits (4096 / 60 s)


def test_native_batch_tools_execute_sequentially_with_feedback(tmp_path):
    class Batch(MockProvider):
        def complete(self, request):
            if request.tools and any(x.role == Role.TOOL for x in request.messages):
                return ModelResponse(tool_calls=tuple(ToolCall("window" + str(n), "compute_mock_factor",
                    {"resource_id": "mock:ohlcv-v1", "lookback": n}) for n in (3, 5)))
            return super().complete(request)
    app = build(tmp_path, provider=Batch())
    state = app.run(app.create("Mock batch comparison").id)
    assert state.status == "COMPLETED" and state.counters == {"iterations": 3, "model_calls": 5, "tool_calls": 3}
    calls = [x for x in state.messages if x["tool_calls"]]
    assert len(calls[-1]["tool_calls"]) == 2
    assert [x["tool_call_id"] for x in state.messages if x["role"] == "tool"] == ["mock_query", "window3", "window5"]


def test_native_batch_budget_refuses_before_partial_execution(tmp_path):
    class Batch(MockProvider):
        def complete(self, request):
            if request.tools:
                return ModelResponse(tool_calls=(ToolCall("one", "query_mock_data", {"resource_id": "mock:ohlcv-v1"}),
                                                ToolCall("two", "query_mock_data", {"resource_id": "mock:ohlcv-v1"})))
            return super().complete(request)
    app = build(tmp_path, provider=Batch())
    state = app.run(app.create("mock", Budget(max_tool_calls=1)).id)
    assert state.status == "BUDGET_EXHAUSTED" and state.counters["tool_calls"] == 0


def test_interrupted_native_batch_is_not_replayed(tmp_path, monkeypatch):
    class Batch(MockProvider):
        def complete(self, request):
            if request.tools:
                return ModelResponse(tool_calls=tuple(ToolCall(name, "query_mock_data", {"resource_id": "mock:ohlcv-v1"}) for name in ("first", "second")))
            return super().complete(request)
    app = build(tmp_path, provider=Batch())
    original = app.store.save
    def save(state, kind, payload):
        original(state, kind, payload)
        if kind == "EXPERIMENT_RECORDED":
            raise KeyboardInterrupt()
    monkeypatch.setattr(app.store, "save", save)
    state = app.run(app.create("mock").id)
    assert state.status == "INTERRUPTED" and state.pending["remaining_call_ids"] == ["second"]
    monkeypatch.setattr(app.store, "save", original)
    recovered = app.run(state.id)
    assert recovered.status == "BLOCKED_RECOVERY" and recovered.counters["tool_calls"] == 1


def test_sessions_share_program_without_overwriting_tasks(tmp_path):
    a, b = build(tmp_path), build(tmp_path)
    x, y = a.create("session A"), b.create("session B")
    assert x.id != y.id and x.session_id != y.session_id
    assert a.run(x.id).status == b.run(y.id).status == "COMPLETED"
    assert a.store.load(x.id).goal == "session A" and b.store.load(y.id).goal == "session B"


def test_parquet_small_fixture_is_supported(tmp_path, published):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    manifest, _, record = published
    data = tmp_path / "tiny.parquet"
    pq.write_table(pa.table({"date": ["2026-10-09"], "code": ["000001"], "close": [11.59]}), data)
    record = {**record, "path": str(data), "format": "parquet", "sha256": hashlib.sha256(data.read_bytes()).hexdigest()}
    manifest.write_text(json.dumps({"version": "1", "resources": [record]}), encoding="utf-8")
    result = ResourceCatalog(manifest).read_data_slice("fixture:daily", ["close"], "2026-10-08", "2026-10-09", 5)
    assert result["row_count"] == 1 and result["rows"][0]["close"] == 11.59
