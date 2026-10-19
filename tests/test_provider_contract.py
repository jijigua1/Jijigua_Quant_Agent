from dataclasses import asdict
import json

import pytest

from research_agent.contracts import PLAN_SCHEMA, canonical
from research_agent.llm import Message, ModelError, ModelRequest, ProviderConfig, Role, ToolCall, Usage
from research_agent.providers.deepseek import DeepSeekAdapter, HTTPTransport, _NoRedirect
from research_agent.tools import mock_registry


CANARY = "DUMMY_PROVIDER_KEY_987654321"


class FixtureSecrets:
    def resolve(self, reference):
        assert reference == "env:QRA_TEST_KEY"
        return CANARY


class FixtureTransport:
    enabled = True
    is_live = False
    def __init__(self, chunks):
        self.chunks = chunks
        self.requests = []
    def send(self, payload, headers, timeout, stream):
        self.requests.append((payload, headers, timeout, stream))
        yield from self.chunks


def adapter(chunks):
    transport = FixtureTransport(chunks)
    return DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", credential_ref="env:QRA_TEST_KEY"), FixtureSecrets(), transport), transport


def wire(message, finish="stop", usage=None):
    return json.dumps({"id": "fixture-response-1", "model": "deepseek-flash",
        "choices": [{"message": {"role": "assistant", **message}, "finish_reason": finish}],
        "usage": usage}).encode()


def test_deepseek_tool_request_and_response_mapping(app):
    message = {"content": None, "tool_calls": [{"id": "call_1", "type": "function",
              "function": {"name": "query_mock_data", "arguments": '{"resource_id":"mock:ohlcv-v1"}'}}]}
    provider, transport = adapter([wire(message, "tool_calls", {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18})])
    request = ModelRequest((Message(Role.USER, "mock"),), app.tools.definitions(app.skill, app.policy))
    result = provider.complete(request)
    assert result.tool_calls == (ToolCall("call_1", "query_mock_data", {"resource_id": "mock:ohlcv-v1"}),)
    assert result.usage == Usage(11, 7, 18)
    payload = transport.requests[0][0]
    assert payload["tools"][0]["function"]["name"] == "query_mock_data"
    assert CANARY not in canonical(payload)
    assert payload["thinking"] == {"type": "disabled"}


def test_tool_feedback_mapping():
    provider, transport = adapter([wire({"content": "done"})])
    call = ToolCall("call_1", "query_mock_data", {"resource_id": "mock:ohlcv-v1"})
    request = ModelRequest((Message(Role.ASSISTANT, tool_calls=(call,)), Message(Role.TOOL, '{"status":"ok"}', tool_call_id="call_1")))
    provider.complete(request)
    messages = transport.requests[0][0]["messages"]
    assert messages[0]["tool_calls"][0]["id"] == "call_1"
    assert messages[1]["tool_call_id"] == "call_1"


def test_json_object_mode_is_locally_validated():
    plan = {"action": "continue", "hypothesis": "mock hypothesis", "change_reason": "first", "summary": ""}
    provider, transport = adapter([wire({"content": canonical(plan)})])
    result = provider.complete(ModelRequest((Message(Role.USER, "plan"),), output_schema=PLAN_SCHEMA))
    assert json.loads(result.content) == plan
    assert transport.requests[0][0]["response_format"] == {"type": "json_object"}
    assert provider.capabilities.strict_schema is False
    assert "local contract" in transport.requests[0][0]["messages"][0]["content"]
    assert "Earlier assistant messages" in transport.requests[0][0]["messages"][0]["content"]
    assert transport.requests[0][0]["messages"][-1] == {"role": "user", "content": "plan"}


def test_late_system_feedback_preserves_tool_exchange_order():
    provider, _ = adapter([])
    call = ToolCall('call_1', 'query_mock_data', {'resource_id': 'mock:ohlcv-v1'})
    request = ModelRequest((Message(Role.SYSTEM, 'policy'), Message(Role.USER, 'query'),
        Message(Role.ASSISTANT, tool_calls=(call,)),
        Message(Role.TOOL, '{"status":"ok"}', tool_call_id='call_1'),
        Message(Role.SYSTEM, 'Return JSON; repair the format.')))
    messages = provider._payload(request)['messages']
    assert [m['role'] for m in messages] == ['system', 'user', 'assistant', 'tool']
    assert messages[0]['content'] == 'policy\n\nReturn JSON; repair the format.'
    assert messages[2]['tool_calls'][0]['id'] == messages[3]['tool_call_id'] == 'call_1'


@pytest.mark.parametrize("message,finish", [
    ({"content": ""}, "stop"),
    ({"content": "{}"}, "length"),
    ({"content": '{"action":"approved"}'}, "stop"),
])
def test_empty_truncated_and_invalid_structured_outputs_rejected(message, finish):
    provider, _ = adapter([wire(message, finish)])
    with pytest.raises(ModelError):
        provider.complete(ModelRequest((Message(Role.USER, "plan"),), output_schema=PLAN_SCHEMA))


def test_unknown_model_capability_is_not_assumed():
    transport = FixtureTransport([])
    provider = DeepSeekAdapter(ProviderConfig("deepseek", "unknown-future-model", credential_ref="env:QRA_TEST_KEY"), FixtureSecrets(), transport)
    with pytest.raises(ModelError, match="CAPABILITY_STRUCTURED_OUTPUT_MISSING"):
        provider.complete(ModelRequest((Message(Role.USER, "plan"),), output_schema=PLAN_SCHEMA))
    assert transport.requests == []


def test_native_strict_schema_requirement_cannot_silently_degrade():
    provider, transport = adapter([])
    with pytest.raises(ModelError, match="CAPABILITY_STRICT_SCHEMA_MISSING"):
        provider.complete(ModelRequest((Message(Role.USER, "strict"),), output_schema=PLAN_SCHEMA, require_strict_schema=True))
    assert transport.requests == []


def test_default_adapter_never_reads_key_or_sends_network():
    class NoSecrets:
        def resolve(self, reference):
            raise AssertionError("must not read credentials")
    provider = DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", credential_ref="env:QRA_TEST_KEY"), NoSecrets())
    with pytest.raises(ModelError, match="LIVE_API_DISABLED"):
        provider.complete(ModelRequest((Message(Role.USER, "hi"),)))


def test_transport_timeout_normalized():
    class TimeoutTransport(FixtureTransport):
        def send(self, *args):
            raise TimeoutError(CANARY)
            yield b""
    provider = DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", credential_ref="env:QRA_TEST_KEY"), FixtureSecrets(), TimeoutTransport([]))
    with pytest.raises(ModelError, match="TIMEOUT") as exc:
        provider.complete(ModelRequest((Message(Role.USER, "hi"),)))
    assert exc.value.retryable and CANARY not in str(exc.value)


def test_redirect_never_forwards_credential():
    with pytest.raises(ModelError, match="HTTP_REDIRECT_DENIED"):
        _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid")


def test_usage_unknown_is_not_zero():
    provider, _ = adapter([wire({"content": "hi"})])
    response = provider.complete(ModelRequest((Message(Role.USER, "hi"),)))
    assert response.usage.total_tokens is None and response.usage.cost is None


def sse(value):
    return b"data: " + json.dumps(value, ensure_ascii=False).encode() + b"\n\n"


def test_stream_tool_fragments_and_usage(app):
    chunks = b"".join([
        sse({"id": "s1", "model": "deepseek-flash", "choices": [{"delta": {"tool_calls": [{"index": 0,
            "id": "call_stream", "type": "function", "function": {"name": "query_mock_data", "arguments": '{"resource_id":'}}]}, "finish_reason": None}]}),
        sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"mock:ohlcv-v1"}'}}]}, "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}),
        b"data: [DONE]\n\n",
    ])
    provider, transport = adapter([chunks[i:i+7] for i in range(0, len(chunks), 7)])
    events = list(provider.stream(ModelRequest((Message(Role.USER, "mock"),), app.tools.definitions(app.skill, app.policy))))
    call = next(x.data for x in events if x.kind == "tool_call")
    assert call["arguments"] == {"resource_id": "mock:ohlcv-v1"}
    assert events[-1].kind == "done" and events[-1].data["response"]["usage"]["total_tokens"] == 8
    assert transport.requests[0][0]["stream_options"]["include_usage"] is True


def test_secret_split_across_stream_chunks_not_emitted():
    text = "prefix " + CANARY + " suffix"
    chunks = b"".join([sse({"choices": [{"delta": {"content": text[:20]}, "finish_reason": None}]}),
                        sse({"choices": [{"delta": {"content": text[20:]}, "finish_reason": "stop"}]}), b"data: [DONE]\n\n"])
    provider, _ = adapter([chunks])
    events = list(provider.stream(ModelRequest((Message(Role.USER, "hi"),))))
    assert CANARY not in canonical([asdict(x) for x in events])
    assert "[REDACTED]" in next(x.data["text"] for x in events if x.kind == "text")


def test_incomplete_stream_rejected():
    provider, _ = adapter([sse({"choices": [{"delta": {"content": "partial"}, "finish_reason": None}]})])
    with pytest.raises(ModelError, match="INCOMPLETE_STREAM"):
        list(provider.stream(ModelRequest((Message(Role.USER, "hi"),))))


def test_deepseek_adapter_can_replace_mock_for_entire_offline_workflow(tmp_path):
    from research_agent.app import build
    from research_agent.cli import DEMO_GOAL
    def plan(reason, action="continue"):
        return wire({"content": canonical({"action": action, "hypothesis": "Mock window sensitivity",
                    "change_reason": reason, "summary": "Synthetic fixture only" if action == "complete" else ""})})
    def tool(name, args, call_id):
        return wire({"content": None, "tool_calls": [{"id": call_id, "type": "function",
            "function": {"name": name, "arguments": canonical(args)}}]}, "tool_calls")
    replies = iter([plan("Query fixed fixture"), tool("query_mock_data", {"resource_id": "mock:ohlcv-v1"}, "query"),
                    plan("First window 3"), tool("compute_mock_factor", {"resource_id": "mock:ohlcv-v1", "lookback": 3}, "factor3"),
                    plan("Change window to 5 for sensitivity"), tool("compute_mock_factor", {"resource_id": "mock:ohlcv-v1", "lookback": 5}, "factor5"),
                    plan("Stop after bounded comparison", "complete")])
    class SequenceTransport(FixtureTransport):
        def send(self, payload, headers, timeout, stream):
            self.requests.append((payload, {}, timeout, stream))
            yield next(replies)
    transport = SequenceTransport([])
    provider = DeepSeekAdapter(ProviderConfig("deepseek", "deepseek-flash", credential_ref="env:QRA_TEST_KEY"), FixtureSecrets(), transport)
    app = build(tmp_path, provider=provider)
    state = app.run(app.create(DEMO_GOAL).id)
    assert state.status == "COMPLETED" and state.provider == "deepseek"
    assert state.result["mode"] == "synthetic" and state.counters["model_calls"] == 7
    assert len(transport.requests) == 7
    assert CANARY not in canonical(app.store.events(state.id))
