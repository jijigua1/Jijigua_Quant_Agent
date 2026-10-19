"""Provider-neutral messages, requests, results, capabilities and credentials."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import os
import re
from typing import Any, Iterator, Protocol

from .contracts import ContractError, canonical, parse_json, validate


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    tool: str
    version: str
    status: str
    data: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class Capabilities:
    tool_calling: bool = True
    structured_json: bool = True
    strict_schema: bool = False
    streaming: bool = False

    def __post_init__(self):
        if any(type(x) is not bool for x in asdict(self).values()):
            raise ContractError("capabilities must be explicit booleans")


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    version: str = "1"
    temperature: float = 0.0
    max_output_tokens: int = 1024
    timeout_seconds: float = 20.0
    max_retries: int = 1
    credential_ref: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", self.provider):
            raise ContractError("invalid provider id")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", self.model):
            raise ContractError("invalid model id")
        if type(self.temperature) not in (int, float) or not 0 <= self.temperature <= 2:
            raise ContractError("invalid temperature")
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 4096:
            raise ContractError("invalid token limit")
        if type(self.timeout_seconds) not in (int, float) or not 0 < self.timeout_seconds <= 60:
            raise ContractError("invalid timeout")
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 2:
            raise ContractError("invalid retries")
        if self.credential_ref is not None and not re.fullmatch(r"env:[A-Z][A-Z0-9_]{2,80}", self.credential_ref):
            raise ContractError("invalid credential reference")


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None

    def __post_init__(self):
        for value in (self.input_tokens, self.output_tokens, self.total_tokens):
            if value is not None and (type(value) is not int or value < 0):
                raise ContractError("invalid token usage")
        if self.cost is not None and (type(self.cost) not in (int, float) or not 0 <= self.cost < 1e9):
            raise ContractError("invalid cost")


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()
    output_schema: dict | None = None
    require_strict_schema: bool = False
    require_tool_call: bool = False
    json_object: bool = field(default=False, repr=False)   # provider JSON mode; repr=False keeps the byte-based token reservation unchanged; (syntactically valid object) without a runtime schema check


@dataclass(frozen=True)
class ModelResponse:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None
    actual_model: str | None = None


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    data: dict


class ModelError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False, *, http_status=None, retry_after=None,
                 usage=None, validation_issue=None, provider_detail=None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.retry_after = retry_after if type(retry_after) in (int, float) and 0 <= retry_after <= 60 else None
        self.usage = usage if isinstance(usage, Usage) else None
        self.provider_detail = provider_detail[:1000] if isinstance(provider_detail, str) else None
        self.validation_issue = validation_issue if validation_issue in {"invalid JSON", "schema violation: required",
            "schema violation: additionalProperties", "schema violation: enum", "schema violation: type", "schema violation: maxLength"} else None


class Provider(Protocol):
    config: ProviderConfig
    capabilities: Capabilities

    def complete(self, request: ModelRequest) -> ModelResponse: ...
    def stream(self, request: ModelRequest) -> Iterator[StreamEvent]: ...


class Redactor:
    def __init__(self, values=()):
        self._values = set(values)

    def add(self, value: str):
        if value:
            self._values.add(value)

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in sorted(self._values, key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", value)
            return value
        if isinstance(value, dict):
            return {str(self.clean(k)): self.clean(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.clean(x) for x in value]
        return value


class SecretStore(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecrets:
    """Only explicitly configured references; never registered as a Tool."""
    def __init__(self, allowed_refs: set[str]):
        self._allowed_refs = frozenset(allowed_refs)

    def resolve(self, reference: str) -> str:
        if reference not in self._allowed_refs or not reference.startswith("env:"):
            raise ModelError("CREDENTIAL_REFERENCE_DENIED")
        value = os.environ.get(reference[4:])
        if not value:
            raise ModelError("CREDENTIAL_MISSING")
        return value


class MemorySecrets:
    """Operator prompt injection; values remain in process memory, never in config."""
    def __init__(self, values: dict[str, str]):
        self._values = dict(values)

    def resolve(self, reference):
        value = self._values.get(reference)
        if not value:
            raise ModelError("CREDENTIAL_MISSING")
        return value


def message_dict(message: Message) -> dict:
    return asdict(message)


def message_from_dict(value: dict) -> Message:
    return Message(Role(value["role"]), value["content"],
                   tuple(ToolCall(**x) for x in value.get("tool_calls", [])), value.get("tool_call_id"))


def check_request(provider: Provider, request: ModelRequest, streaming=False):
    caps = provider.capabilities
    if request.require_tool_call and not request.tools:
        raise ModelError("REQUIRED_TOOL_LIST_EMPTY")
    if request.tools and not caps.tool_calling:
        raise ModelError("CAPABILITY_TOOL_CALLING_MISSING")
    if request.output_schema and not caps.structured_json:          # json_object is only a provider hint
        raise ModelError("CAPABILITY_STRUCTURED_OUTPUT_MISSING")
    if request.require_strict_schema and (not request.output_schema or not caps.strict_schema):
        raise ModelError("CAPABILITY_STRICT_SCHEMA_MISSING")
    if streaming and not caps.streaming:
        raise ModelError("CAPABILITY_STREAMING_MISSING")
    canonical([message_dict(x) for x in request.messages])


def check_response(response: ModelResponse, request: ModelRequest):
    if not isinstance(response, ModelResponse) or not isinstance(response.content, str) or not isinstance(response.usage, Usage):
        raise ModelError("INVALID_NORMALIZED_RESPONSE")
    if any(not isinstance(x, ToolCall) or not isinstance(x.name, str) or not isinstance(x.arguments, dict) for x in response.tool_calls):
        raise ModelError("INVALID_NORMALIZED_TOOL_CALL")
    canonical(asdict(response))
    if len(response.tool_calls) > 4:
        raise ModelError("INVALID_TOOL_CALL_COUNT")
    ids = [x.id for x in response.tool_calls]
    if any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", x) for x in ids):
        raise ModelError("INVALID_TOOL_CALL_ID")
    if request.output_schema:
        if response.tool_calls:
            raise ModelError("UNEXPECTED_TOOL_CALL_DURING_PLAN")
        try:
            validate(parse_json(response.content), request.output_schema)
        except ContractError as exc:
            issue = str(exc)
            detail = None
            if issue == 'schema violation: required':
                # Only disclose trusted schema keys, never rejected values.
                value = parse_json(response.content)
                if isinstance(value, dict):
                    missing = [key for key in request.output_schema.get('required', []) if key not in value]
                    if missing:
                        detail = 'Missing required fields: ' + ', '.join(missing)
            raise ModelError("INVALID_STRUCTURED_OUTPUT", issue in {"invalid JSON", "schema violation: required", "schema violation: maxLength"},
                             usage=response.usage, validation_issue=issue, provider_detail=detail) from None
