"""Deterministic fixture provider, not a language model or market researcher."""

from dataclasses import asdict

from ..contracts import canonical, parse_json
from ..llm import Capabilities, ModelRequest, ModelResponse, ProviderConfig, Role, StreamEvent, ToolCall, Usage


class MockProvider:
    capabilities = Capabilities(True, True, True, True)

    def __init__(self, config=None):
        self.config = config or ProviderConfig("mock", "mock-research-v1")

    def complete(self, request: ModelRequest):
        results = [parse_json(x.content) for x in request.messages if x.role == Role.TOOL]
        query_done = any(x.get("tool") == "query_mock_data" for x in results)
        factors = [x["data"] for x in results if x.get("tool") == "compute_mock_factor" and x.get("status") == "ok"]
        if request.output_schema:
            done = len(factors) >= 2
            value = {"action": "complete" if done else "continue",
                     "hypothesis": "固定模拟价格与成交量的联合指标对窗口选择是否敏感。",
                     "change_reason": "完成两个窗口的模拟对照，停止追加实验。" if done else
                                      "先查询固定模拟数据。" if not query_done else
                                      "先测3期窗口。" if not factors else "将窗口从3改为5，检验参数敏感性。",
                     "summary": "仅模拟研究：完成3期与5期量价指标对照；数值随窗口变化。没有真实行情、回测收益或有效性结论。" if done else ""}
            return ModelResponse(canonical(value), usage=Usage(20, 30, 50), actual_model=self.config.model)
        name = "query_mock_data" if not query_done else "compute_mock_factor"
        args = {"resource_id": "mock:ohlcv-v1"}
        if name == "compute_mock_factor":
            args["lookback"] = 3 if not factors else 5
        call_id = "mock_query" if name == "query_mock_data" else "mock_factor_" + str(args["lookback"])
        return ModelResponse(tool_calls=(ToolCall(call_id, name, args),), usage=Usage(20, 10, 30), actual_model=self.config.model)

    def stream(self, request):
        result = self.complete(request)
        if result.content:
            yield StreamEvent("text", {"text": result.content})
        for call in result.tool_calls:
            yield StreamEvent("tool_call", asdict(call))
        yield StreamEvent("usage", asdict(result.usage))
        yield StreamEvent("done", {"response": asdict(result)})
