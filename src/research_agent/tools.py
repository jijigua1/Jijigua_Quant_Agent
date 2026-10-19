"""Only audited, deterministic in-memory Mock Tools. No file or code executor."""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from statistics import mean
from typing import Callable

from .contracts import ContractError, fingerprint, object_schema, validate
from .llm import ToolDefinition, ToolResult
from .security import Denied, authorize

RESOURCE = "mock:ohlcv-v1"
ROWS = (("2026-01-05", 100, 1000), ("2026-01-06", 101, 1100),
        ("2026-01-07", 99, 900), ("2026-01-08", 102, 1200),
        ("2026-01-09", 103, 1300), ("2026-01-12", 105, 1400))
DATA_HASH = fingerprint(ROWS)
RESOURCE_SCHEMA = {"type": "string", "enum": [RESOURCE]}


@dataclass(frozen=True)
class ToolSpec:
    id: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Callable
    kind: str = "mock"
    risk: str = "L0"
    requires_approval: bool = False
    write_scopes: tuple[str, ...] = ()
    resource_mode: str = "single"


class ToolRegistry:
    def __init__(self, tools=(), *, context=None):
        self._tools = {}
        self.context = context or {}
        for tool in tools:
            self.register(tool)

    def register(self, tool):
        if tool.id in self._tools:
            raise ContractError("duplicate tool")
        if tool.resource_mode not in {"single", "catalog"}:
            raise ContractError("invalid resource authorization mode")
        if tool.id in {"shell", "exec", "run_python", "run_shell", "sudo", "kill", "rm", "chmod", "chown", "systemctl", "crontab", "trade", "git_reset"}:
            raise Denied("PROHIBITED_TOOL")
        self._tools[tool.id] = tool

    @property
    def versions(self):
        return {k: v.version for k, v in self._tools.items()}

    @property
    def digest(self):
        return fingerprint({"context": self.context, "tools": {k: {"version": v.version, "kind": v.kind, "risk": v.risk,
             "input": fingerprint(v.input_schema), "output": fingerprint(v.output_schema), "writes": v.write_scopes, "resource_mode": v.resource_mode}
             for k, v in self._tools.items()}})

    def definitions(self, skill, policy):
        return tuple(ToolDefinition(t.id, t.description, t.input_schema)
                     for t in self._tools.values() if t.id in skill.tools and t.id in policy.allowed_tools and
                     (t.kind == "mock" or policy.phase == "development" and t.kind in {"data_readonly", "quant_compute"}))

    def discover(self):
        return [{"id": t.id, "version": t.version, "description": t.description,
                 "required_parameters": t.input_schema.get("required", []), "input_schema": t.input_schema}
                for t in self._tools.values()]

    def check_authorization(self, call, *, policy, grant, skill):
        tool = self._tools.get(call.name)
        if tool is None:
            raise Denied("UNKNOWN_TOOL")
        authorize(tool, call.arguments, policy, grant, skill)
        return tool

    def execute(self, call, *, policy, grant, skill, task_context=None):
        tool = self.check_authorization(call, policy=policy, grant=grant, skill=skill)
        if tool.kind == 'quant_compute':
            if not task_context or task_context.get('task_id') != grant.task_id:
                raise Denied('TRUSTED_TASK_CONTEXT_REQUIRED')
            context=dict(task_context,authorized_resources=tuple(r for r in grant.resources if r in policy.resources))
            result = tool.handler(**call.arguments, _task_context=context)
            if isinstance(result, dict):
                # a research result can outgrow the JSON contract (live C6R4-I1: 72,241 bytes after a real 2026 Test)
                from .result_fit import NOTE, fit
                result = fit(result, allows_note=NOTE in (tool.output_schema.get('properties') or {}))
        else:
            result = tool.handler(**call.arguments)
        validate(result, tool.output_schema)
        return asdict(ToolResult(call.id, tool.id, tool.version, "ok", result))


def query_mock_data(resource_id):
    return {"mode": "synthetic", "resource_id": resource_id, "data_sha256": DATA_HASH,
            "rows": [{"date": d, "close": c, "volume": v} for d, c, v in ROWS]}


def compute_mock_factor(resource_id, lookback):
    window = ROWS[-lookback:]
    momentum = window[-1][1] / window[0][1] - 1
    volume_ratio = window[-1][2] / mean(x[2] for x in window)
    return {"mode": "synthetic", "resource_id": resource_id, "data_sha256": DATA_HASH,
            "lookback": lookback, "momentum": momentum, "volume_ratio": volume_ratio,
            "factor_value": momentum * volume_ratio,
            "formula": "(last_close / first_close - 1) * (last_volume / mean_volume)"}


def mock_registry():
    common = {"mode": {"const": "synthetic"}, "resource_id": RESOURCE_SCHEMA,
              "data_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}
    rows_schema = object_schema({"date": {"type": "string"}, "close": {"type": "number"}, "volume": {"type": "number"}})
    query_output = object_schema({**common, "rows": {"type": "array", "minItems": 6, "maxItems": 6, "items": rows_schema}})
    factor_output = object_schema({**common, "lookback": {"type": "integer", "minimum": 2, "maximum": 6},
        "momentum": {"type": "number"}, "volume_ratio": {"type": "number"},
        "factor_value": {"type": "number"}, "formula": {"type": "string"}})
    return ToolRegistry([
        ToolSpec("query_mock_data", "1.0.0", "查询六行固定模拟量价数据，无文件访问。", object_schema({"resource_id": RESOURCE_SCHEMA}), query_output, query_mock_data),
        ToolSpec("compute_mock_factor", "1.0.0", "计算固定模拟数据的量价联合指标。", object_schema({"resource_id": RESOURCE_SCHEMA,
            "lookback": {"type": "integer", "minimum": 2, "maximum": 6}}), factor_output, compute_mock_factor),
    ])


def code_fingerprint():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
