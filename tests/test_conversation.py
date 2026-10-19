from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import urllib.error

import pytest

from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ModelError, ModelResponse, ProviderConfig, Role, ToolCall
from research_agent.providers.deepseek import HTTPTransport
from research_agent.providers.mock import MockProvider
from research_agent.security import Denied
from research_agent.store import StateConflict
from research_agent.terminal import chat_loop, safe_text
from test_development_data import DataProvider, published


def decision(action="reply", reply="这是测试回答。", skill_id="", research_goal=""):
    return ModelResponse(canonical(dict(action=action, reply=reply, skill_id=skill_id,
                                       research_goal=research_goal, reason="固定测试决策")))


class Scripted(MockProvider):
    def __init__(self, responses):
        super().__init__(replace(ProviderConfig("mock", "mock-research-v1"), max_retries=0))
        self.responses = iter(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if request.output_schema and "research_goal" in request.output_schema["properties"]:
            value = next(self.responses)
            if isinstance(value, BaseException):
                raise value
            return value
        return super().complete(request)


def test_plain_reply_clarification_and_missing_factor_skill_do_not_call_tools(tmp_path):
    p = Scripted([decision(reply="你好"), decision("clarify", "请说明研究目标"), decision(reply="可讨论因子，但尚未计算")])
    app = build_chat(tmp_path, provider=p)
    for text in ("你好", "asdfghjkl", "帮我设计放量滞涨因子"):
        assert app.turn(text)
    turns = app.store.session_turns(app.session_id)
    assert all(t["research_task_id"] is None for t in turns)
    assert all(app.store.load(t["route_task_id"]).counters["tool_calls"] == 0 for t in turns)
    assert len(p.requests) == 3


def test_mock_skill_routes_through_existing_authorization_and_evidence(tmp_path):
    p = Scripted([decision("skill", "", "mock_research", "比较模拟3期和5期指标"), decision(reply="刚刚比较了模拟窗口")])
    app = build_chat(tmp_path, provider=p)
    assert "模拟" in app.turn("研究模拟指标")
    app.turn("刚刚那个因子换成五日窗口呢？")
    turns = app.store.session_turns(app.session_id)
    task = app.store.load(turns[0]["research_task_id"])
    assert task.status == "COMPLETED" and task.session_id == app.session_id
    assert task.counters["tool_calls"] == 3
    assert app.store.authorization(task.id).allowed_tools
    assert app.store.authorization(turns[1]["route_task_id"]).allowed_tools == ()
    context = canonical([x.content for x in p.requests[-1].messages])
    assert "五日" in context and "lookback" in context and "data_sha256" in context
    assert task.id in context and "factor_value" in context


@pytest.mark.parametrize("value", [decision("skill", "", "shell", "run"), decision("skill", "", "factor_evaluate", "factor"),
    ModelResponse('{"action":"reply","reply":"yes","skill_id":"","research_goal":"","reason":"","approved":true}')])
def test_forged_skill_and_model_approval_rejected(tmp_path, value):
    app = build_chat(tmp_path, provider=Scripted([value]))
    app.turn("执行")
    row = app.store.session_turns(app.session_id)[0]
    assert row["status"] == "MODEL_ERROR" and row["research_task_id"] is None
    assert app.store.load(row["route_task_id"]).counters["tool_calls"] == 0


def test_context_isolated_and_explicit_resume_preserves_history(tmp_path):
    p = Scripted([decision(reply="讨论放量滞涨"), decision(reply="沿用之前的假设")])
    a = build_chat(tmp_path, provider=p)
    a.turn("放量滞涨因子")
    b = build_chat(tmp_path, provider=Scripted([decision()]))
    assert b.store.session(b.session_id)["messages"] == []
    resumed = build_chat(tmp_path, provider=p, session_id=a.session_id)
    resumed.turn("继续")
    assert "放量滞涨" in canonical([x.content for x in p.requests[-1].messages])
    assert b.store.session_turns(b.session_id) == []
    assert len(resumed.store.session_turns(a.session_id)) == 2

def test_context_keeps_latest_complete_evidence_within_budget(tmp_path):
    app=build_chat(tmp_path,provider=Scripted([]))
    session=app.store.session(app.session_id)
    session['evidence']=[dict(task_id=str(i),tool='qrtk_factor_study',parameters={},result_sha256='hash',
        data=dict(study_id='study_'+str(i),splits={'large':'x'*6000})) for i in range(6)]
    context=app.context(session)[-1].content.split('\n',1)[1]
    records=json.loads(context)
    assert records[-1]['data']['study_id']=='study_5' and len(records)==6
    assert len(context.encode())<=5000


def test_research_task_gets_compact_verified_context_and_user_scope_not_raw_chat(tmp_path):
    app=build_chat(tmp_path,provider=Scripted([]))
    session=app.store.session(app.session_id)
    session['messages']=[{"role":"user","content":"帮我构造一个完整的动量因子。"},
                         {"role":"assistant","content":"历史助手内容不能成为授权"},
                         {"role":"user","content":"默认设定"}]
    session['evidence']=[dict(task_id='task',tool='qrtk_factor_study',parameters={},result_sha256='hash',
        data=dict(study_id='study',resource_id='resource',data_sha256='a'*64))]
    context=app.research_context(session)
    assert len(context)==2 and all(x.role==Role.SYSTEM for x in context)
    assert '帮我构造一个完整的动量因子' in context[1].content and '默认设定' in context[1].content
    assert '历史助手内容不能成为授权' not in context[1].content
    assert 'study' in context[0].content and 'data_sha256' in context[0].content


def test_session_busy_and_stale_updates_refused(tmp_path):
    app = build_chat(tmp_path, provider=Scripted([]))
    a = app.store.session(app.session_id)
    stale = app.store.session(app.session_id)
    a["busy"] = True
    app.store.save_session(a)
    with pytest.raises(StateConflict):
        app.store.save_session(stale)
    with pytest.raises(Denied, match="SESSION_BUSY"):
        build_chat(tmp_path, provider=app.provider, session_id=app.session_id)


@pytest.mark.parametrize("error", [ModelError("TIMEOUT", True), ModelError("SERVER_ERROR", True, http_status=503), KeyboardInterrupt()])
def test_error_and_interrupt_do_not_poison_same_session(tmp_path, error):
    p = Scripted([error, decision(reply="后续正常")])
    app = build_chat(tmp_path, provider=p)
    assert "继续" in app.turn("第一条")
    assert app.turn("第二条") == "后续正常"
    first, second = app.store.session_turns(app.session_id)
    assert first["status"] in {"MODEL_ERROR", "INTERRUPTED"} and second["status"] == "COMPLETED"
    assert not app.store.session(app.session_id)["busy"]
    if isinstance(error, ModelError):
        assert app.store.load(first["route_task_id"]).usage["unknown_calls"] == 1


def test_session_context_and_call_budget_are_bounded(tmp_path):
    app = build_chat(tmp_path, provider=Scripted([decision(reply="答" * 1500)] * 10))
    for _ in range(10):
        app.turn("问" * 1000)
    value = app.store.session(app.session_id)
    assert len(canonical([x.content for x in app.context(value)]).encode()) < 16000
    assert len(app.store.session_turns(app.session_id)) == 10
    from research_agent.conversation import SESSION_CALLS
    value["model_calls"] = SESSION_CALLS
    app.store.save_session(value)
    with pytest.raises(Denied, match="SESSION_BUDGET_EXHAUSTED"):
        app.turn("继续")


def test_cli_outputs_plain_text_commands_and_eof(tmp_path, monkeypatch, capsys):
    app = build_chat(tmp_path, provider=Scripted([decision(reply="第一行\n第二行")]))
    inputs = iter(["你好", "/tasks", "/history", "/skills", "/session", "/help", "/bad"])
    def read(prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError()
    monkeypatch.setattr("builtins.input", read)
    chat_loop(app)
    out = capsys.readouterr().out
    assert "第一行\n第二行" in out and '\\n' not in out
    assert '"execution_mode"' not in out and "会话已结束" in out
    assert "mock_research" in out and "COMPLETED" in out
    assert safe_text("a\x1b\x07b") == "ab"


@pytest.mark.parametrize("status,code,retry", [(400,"BAD_REQUEST",False),(401,"AUTHENTICATION",False),
    (402,"INSUFFICIENT_BALANCE",False),(403,"PERMISSION_DENIED",False),(422,"INVALID_REQUEST",False),
    (429,"RATE_LIMIT",True),(500,"SERVER_ERROR",True),(503,"SERVER_ERROR",True)])
def test_http_status_classification_never_exposes_body(tmp_path, monkeypatch, status, code, retry):
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("https://api.deepseek.com", status, "SECRET_MESSAGE", {"Retry-After":"3"}, io.BytesIO(b"SECRET_BODY"))
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(ModelError) as caught:
        list(HTTPTransport(allow_live=True).send({}, {}, 20, False))
    assert caught.value.code == code and caught.value.http_status == status
    assert caught.value.retryable is retry and "SECRET" not in str(caught.value)


def test_chat_config_change_and_session_id_traversal_refused(tmp_path):
    app = build_chat(tmp_path, provider=Scripted([]))
    provider = Scripted([])
    provider.config = replace(provider.config, version="changed")
    with pytest.raises(Denied, match="SESSION_CONFIG_CHANGED"):
        build_chat(tmp_path, provider=provider, session_id=app.session_id)
    with pytest.raises(Denied, match="INVALID_TASK_ID"):
        build_chat(tmp_path, provider=provider, session_id="../../private")


def test_data_selection_and_pronoun_context_use_verified_evidence(tmp_path, published):
    class DataChat(DataProvider):
        def complete(self, request):
            if request.output_schema and "research_goal" in request.output_schema["properties"]:
                return decision("skill", "", "data_query", "描述资源并查询两行")
            return super().complete(request)
    app = build_chat(tmp_path, profile="development", resources_manifest=published[0], provider=DataChat())
    before = published[1].read_bytes()
    assert app.turn("服务器有什么数据？")
    session = app.store.session(app.session_id)
    context = canonical([x.content for x in app.context(session)])
    assert "fixture:daily" in context and "2026-10-09" in context and "frequency" in context and "close" in context
    assert "formal_backtest_ready" in context and "data_sha256" in context
    assert before == published[1].read_bytes()
    assert len(session["evidence"]) == 3


def test_verified_data_evidence_survives_later_skill_scope_denial(tmp_path, published):
    class PartialDataChat(DataProvider):
        def complete(self, request):
            if request.output_schema and "research_goal" in request.output_schema["properties"]:
                return decision("skill", "", "data_query", "核验资源")
            if request.tools:
                count=sum(x.role==Role.TOOL for x in request.messages)
                if count==2:
                    return ModelResponse(tool_calls=(ToolCall("cross-skill", "qrtk_data_quality",
                        {"resource_id":"fixture:daily"}),))
            return super().complete(request)
    app=build_chat(tmp_path,profile="development",resources_manifest=published[0],provider=PartialDataChat())
    app.turn("列出并核验数据")
    session=app.store.session(app.session_id)
    context=canonical([x.content for x in app.context(session)])
    turn=app.store.session_turns(app.session_id)[0]
    assert turn["status"]=="AUTHORIZATION_DENIED"
    assert "fixture:daily" in context and "2026-10-09" in context and "close" in context
    assert any(x["task_status"]=="AUTHORIZATION_DENIED" and x["tool"]=="describe_resource"
               for x in session["evidence"])


def test_retry_status_unknown_usage_and_budget_remain_audited(tmp_path):
    provider = Scripted([ModelError("SERVER_ERROR", True, http_status=503),
                         ModelError("SERVER_ERROR", True, http_status=503), decision(reply="恢复成功")])
    provider.config = replace(provider.config, max_retries=1)
    app = build_chat(tmp_path, provider=provider)
    app.turn("第一次")
    assert app.turn("第二次") == "恢复成功"
    first = app.store.session_turns(app.session_id)[0]
    task = app.store.load(first["route_task_id"])
    assert task.counters["model_calls"] == 2 and task.usage["unknown_calls"] == 2
    failures = [x["payload"] for x in app.store.events(task.id) if x["kind"] == "MODEL_FAILURE"]
    assert len(failures) == 2 and all(x["http_status"] == 503 and x["usage"] is None for x in failures)


def test_resume_binding_changes_when_resource_manifest_changes(tmp_path, published):
    p = Scripted([])
    a = build_chat(tmp_path, provider=p, resources_manifest=published[0])
    manifest = json.loads(published[0].read_text())
    manifest["resources"][0]["source"] = "changed publisher"
    published[0].write_text(json.dumps(manifest))
    with pytest.raises(Denied, match="SESSION_CONFIG_CHANGED"):
        build_chat(tmp_path, provider=p, resources_manifest=published[0], session_id=a.session_id)


def test_plain_chat_does_not_load_skill_method(tmp_path, monkeypatch):
    from research_agent.skills import SkillRegistry
    monkeypatch.setattr(SkillRegistry, "load", lambda *args: pytest.fail("method loaded for greeting"))
    app = build_chat(tmp_path, provider=Scripted([decision(reply="你好")]))
    assert app.turn("你好") == "你好"


def test_discovery_exposes_no_argument_catalog_tool_without_loading_method(tmp_path, published, monkeypatch):
    from research_agent.skills import SkillRegistry
    monkeypatch.setattr(SkillRegistry, "load", lambda *args: pytest.fail("loaded before model selection"))
    app = build_chat(tmp_path, provider=Scripted([]), resources_manifest=published[0])
    data = next(x for x in app.skills if x["id"] == "data_query")
    listing = next(x for x in data["tools"] if x["id"] == "list_resources")
    assert listing["required_parameters"] == [] and listing["version"] == "1.0.0"
    assert "path" not in canonical(app.skills) and str(published[1]) not in canonical(app.skills)
    mock = next(x for x in app.skills if x["id"] == "mock_research")
    factor = next(x for x in mock["tools"] if x["id"] == "compute_mock_factor")
    assert factor['required_parameters']==['resource_id','lookback']
    assert 'input_schema' not in factor # detailed schemas load only after Skill routing


def test_structured_json_repair_is_bounded_and_usage_preserved(tmp_path):
    from research_agent.llm import Usage
    malformed = ModelResponse('{"action":"reply","reply":"unescaped\nnewline"}', usage=Usage(10, 5, 15))
    p = Scripted([malformed, decision(reply="恢复回答")])
    p.config = replace(p.config, max_retries=1)
    app = build_chat(tmp_path, provider=p)
    assert app.turn("你能帮我做什么？") == "恢复回答"
    turn = app.store.session_turns(app.session_id)[0]
    task = app.store.load(turn["route_task_id"])
    assert task.counters["model_calls"] == 2 and task.counters["tool_calls"] == 0
    assert task.usage["total_tokens"] == 15  # The repair fixture has unknown usage.
    assert "failed local JSON validation" in p.requests[-1].messages[-1].content
    failure = next(e["payload"] for e in app.store.events(task.id) if e["kind"] == "MODEL_FAILURE")
    assert failure["validation_issue"] == "invalid JSON" and failure["usage"]["total_tokens"] == 15
    assert "unescaped" not in canonical(failure)


def test_repeated_invalid_json_stops_before_any_tool(tmp_path):
    p = Scripted([ModelResponse("invalid"), ModelResponse("invalid")])
    p.config = replace(p.config, max_retries=1)
    app = build_chat(tmp_path, provider=p)
    app.turn("查询数据")
    turn = app.store.session_turns(app.session_id)[0]
    assert turn["status"] == "MODEL_ERROR" and turn["research_task_id"] is None
    assert app.store.load(turn["route_task_id"]).counters["model_calls"] == 2


def test_research_tool_failure_keeps_distinct_status_in_conversation(tmp_path):
    from research_agent.app import build
    from research_agent.tools import ToolRegistry, mock_registry
    registry = mock_registry()
    def fail(**kwargs):
        raise RuntimeError("PRIVATE_TOOL_ERROR")
    tools = ToolRegistry([replace(t, handler=fail) for t in registry._tools.values()])
    p = Scripted([decision("skill", "", "mock_research", "研究模拟数据")])
    app = build_chat(tmp_path, provider=p)
    app.workflow_factory = lambda skill: build(tmp_path, provider=p, tools=tools)
    app.turn("研究模拟数据")
    turn = app.store.session_turns(app.session_id)[0]
    assert turn["status"] == "TOOL_ERROR" and turn["error"]["code"] == "TOOL_EXECUTION_FAILED"
    assert app.store.load(turn["research_task_id"]).status == "TOOL_ERROR"


def test_skill_routing_allows_omitted_optional_display_reply(tmp_path):
    value = ModelResponse(canonical(dict(action="skill", skill_id="mock_research",
        research_goal="比较模拟3期和5期指标", reason="执行研究")))
    app = build_chat(tmp_path, provider=Scripted([value]))
    app.turn("研究模拟指标")
    turn = app.store.session_turns(app.session_id)[0]
    assert app.store.load(turn["research_task_id"]).status == "COMPLETED"


@pytest.mark.parametrize("action", ["reply", "clarify", "propose"])
def test_user_facing_decision_requires_reply(tmp_path, action):
    value = ModelResponse(canonical(dict(action=action, skill_id="",
        research_goal="", reason="缺失必要显示内容")))
    app = build_chat(tmp_path, provider=Scripted([value]))
    app.turn("研究")
    turn = app.store.session_turns(app.session_id)[0]
    assert turn["status"] == "MODEL_ERROR"
    assert turn["research_task_id"] is None
