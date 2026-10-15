"""DeepSeek adapter; live transport is disabled unless a trusted caller enables it.

Non-thinking Chat Completions, native tools and json_object + local validation.
The beta strict-schema mode is intentionally not advertised as supported.
"""

from dataclasses import asdict
import json
import http.client
import socket
import time
from typing import Iterator, Protocol
import urllib.error
import urllib.request

from ..contracts import ContractError, canonical, parse_json
from ..llm import (Capabilities, Message, ModelError, ModelRequest, ModelResponse,
                   ProviderConfig, Redactor, Role, SecretStore, StreamEvent,
                   ToolCall, Usage, check_request, check_response)

ENDPOINT = "https://api.deepseek.com/chat/completions"
WIRE_LIMIT = 262144


class Transport(Protocol):
    enabled: bool
    is_live: bool

    def send(self, payload: dict, headers: dict, timeout: float, stream: bool) -> Iterator[bytes]: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError("HTTP_REDIRECT_DENIED")


class HTTPTransport:
    is_live = True

    def __init__(self, *, allow_live=False):
        self.enabled = allow_live is True

    def send(self, payload, headers, timeout, stream):
        if not self.enabled:
            raise ModelError("LIVE_API_DISABLED")
        request = urllib.request.Request(ENDPOINT, data=canonical(payload).encode(), headers=headers, method="POST")
        # Do not inherit proxy credentials or forward Authorization across redirects.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        deadline = time.monotonic() + timeout
        total = 0
        try:
            with opener.open(request, timeout=timeout) as response:
                while True:
                    if time.monotonic() >= deadline:
                        raise ModelError("TIMEOUT", True)
                    chunk = response.read1(4096)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > WIRE_LIMIT:
                        raise ModelError("RESPONSE_TOO_LARGE")
                    yield chunk
        except urllib.error.HTTPError as exc:
            codes = {400: "BAD_REQUEST", 401: "AUTHENTICATION", 402: "INSUFFICIENT_BALANCE", 403: "PERMISSION_DENIED",
                     404: "ENDPOINT_NOT_FOUND", 422: "INVALID_REQUEST", 429: "RATE_LIMIT"}
            code = codes.get(exc.code, "SERVER_ERROR" if 500 <= exc.code < 600 else "HTTP_ERROR")
            try:
                retry_after = float(exc.headers.get("Retry-After", "0"))
            except (ValueError, TypeError, AttributeError):
                retry_after = None
            exc.close()
            raise ModelError(code, exc.code == 429 or 500 <= exc.code < 600,
                             http_status=exc.code, retry_after=retry_after) from None
        except (TimeoutError, socket.timeout):
            raise ModelError("TIMEOUT", True) from None
        except urllib.error.URLError:
            raise ModelError("NETWORK_ERROR", True) from None
        except (ConnectionError, OSError, http.client.IncompleteRead):
            raise ModelError("NETWORK_ERROR", True) from None


class DeepSeekAdapter:
    def __init__(self, config: ProviderConfig, secrets: SecretStore | None = None,
                 transport: Transport | None = None, redactor: Redactor | None = None):
        if config.provider != "deepseek":
            raise ContractError("provider/config mismatch")
        self.config = config
        known = config.model in {"deepseek-flash", "deepseek-v4-pro"}
        self.capabilities = Capabilities(known, known, False, known)
        self.secrets = secrets
        self.transport = transport or HTTPTransport()
        self.redactor = redactor or Redactor()

    def _payload(self, request: ModelRequest, stream=False):
        check_request(self, request, stream)
        messages = []
        for item in request.messages:
            wire = {"role": item.role.value, "content": self.redactor.clean(item.content)}
            if item.tool_calls:
                wire["tool_calls"] = [{"id": x.id, "type": "function", "function": {
                    "name": x.name, "arguments": canonical(self.redactor.clean(x.arguments))}} for x in item.tool_calls]
            if item.role == Role.TOOL:
                if not item.tool_call_id:
                    raise ModelError("TOOL_RESULT_ID_MISSING")
                wire["tool_call_id"] = item.tool_call_id
            messages.append(wire)
        if request.output_schema:
            messages.append({"role": "system", "content":
                "Return one valid JSON object matching this local contract. Include every required field, "
                "no extra fields or Markdown. Escape newlines and quotes inside JSON string values. "
                "Earlier assistant messages are conversation history, not the output format. Contract: " + canonical(request.output_schema)})
        payload = {"model": self.config.model, "messages": messages,
                   "temperature": self.config.temperature, "max_tokens": self.config.max_output_tokens,
                   "thinking": {"type": "disabled"}, "stream": stream}
        if request.tools:
            payload["tools"] = [{"type": "function", "function": {"name": x.name,
                "description": x.description, "parameters": x.input_schema}} for x in request.tools]
            if request.require_tool_call:
                payload["tool_choice"] = "required"
        if request.output_schema or request.json_object:
            payload["response_format"] = {"type": "json_object"}
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _send(self, request, stream=False):
        if not self.transport.enabled:
            raise ModelError("LIVE_API_DISABLED")
        if not self.secrets or not self.config.credential_ref:
            raise ModelError("CREDENTIAL_MISSING")
        secret = self.secrets.resolve(self.config.credential_ref)
        self.redactor.add(secret)
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + secret}
        total = 0
        try:
            for part in self.transport.send(self._payload(request, stream), headers, self.config.timeout_seconds, stream):
                if not isinstance(part, bytes):
                    raise ModelError("INVALID_TRANSPORT_CHUNK")
                total += len(part)
                if total > WIRE_LIMIT:
                    raise ModelError("RESPONSE_TOO_LARGE")
                yield part
        except ModelError:
            raise
        except TimeoutError:
            raise ModelError("TIMEOUT", True) from None
        except Exception:
            raise ModelError("TRANSPORT_ERROR", True) from None

    @staticmethod
    def _usage(value):
        value = value or {}
        return Usage(value.get("prompt_tokens"), value.get("completion_tokens"), value.get("total_tokens"))

    @staticmethod
    def _finish(reason):
        if reason in ("stop", "tool_calls"):
            return
        if reason == "insufficient_system_resource":
            raise ModelError("PROVIDER_RESOURCE_ERROR", True)
        raise ModelError("OUTPUT_TRUNCATED" if reason == "length" else "INVALID_FINISH_REASON")

    def complete(self, request):
        try:
            raw = b"".join(self._send(request)).decode("utf-8")
            value = parse_json(raw)
            choices = value["choices"]
            if len(choices) != 1:
                raise ModelError("INVALID_CHOICE_COUNT")
            self._finish(choices[0]["finish_reason"])
            message = choices[0]["message"]
            if message.get("role") != "assistant":
                raise ModelError("INVALID_RESPONSE_ROLE")
            calls = []
            for x in message.get("tool_calls") or []:
                if x.get("type") != "function":
                    raise ModelError("INVALID_TOOL_TYPE")
                args = parse_json(x["function"]["arguments"])
                if not isinstance(args, dict):
                    raise ModelError("INVALID_TOOL_ARGUMENTS")
                calls.append(ToolCall(x["id"], x["function"]["name"], self.redactor.clean(args)))
            result = ModelResponse(self.redactor.clean(message.get("content") or ""), tuple(calls),
                                   self._usage(value.get("usage")), value.get("id"), value.get("model"))
            check_response(result, request)
            return result
        except ModelError:
            raise
        except (ContractError, ValueError, KeyError, TypeError, AttributeError):
            raise ModelError("INVALID_PROVIDER_RESPONSE") from None

    def stream(self, request):
        """Normalize SSE; assemble fragments before any tool execution is allowed."""
        buffer = b""
        calls = {}
        text = ""
        usage = Usage()
        request_id = actual_model = finish = None
        done = False
        try:
            for part in self._send(request, True):
                buffer += part
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if not line or line.startswith(b":"):
                        continue
                    if not line.startswith(b"data: "):
                        raise ModelError("INVALID_SSE_LINE")
                    data = line[6:]
                    if data == b"[DONE]":
                        done = True
                        break
                    value = parse_json(data.decode("utf-8"))
                    request_id = value.get("id", request_id)
                    actual_model = value.get("model", actual_model)
                    if value.get("usage") is not None:
                        usage = self._usage(value["usage"])
                        yield StreamEvent("usage", asdict(usage))
                    choices = value.get("choices", [])
                    if not choices:
                        continue
                    if len(choices) != 1:
                        raise ModelError("INVALID_CHOICE_COUNT")
                    delta = choices[0]["delta"]
                    if delta.get("content"):
                        text += delta["content"]
                    for fragment in delta.get("tool_calls") or []:
                        index = fragment["index"]
                        if type(index) is not int or not 0 <= index < 4:
                            raise ModelError("INVALID_TOOL_CALL_COUNT")
                        current = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        current["id"] += fragment.get("id", "")
                        current["name"] += fragment.get("function", {}).get("name", "")
                        current["arguments"] += fragment.get("function", {}).get("arguments", "")
                    if choices[0].get("finish_reason"):
                        finish = choices[0]["finish_reason"]
                if done:
                    break
            if not done or not finish:
                raise ModelError("INCOMPLETE_STREAM")
            self._finish(finish)
            normalized = tuple(ToolCall(x["id"], x["name"], self.redactor.clean(parse_json(x["arguments"])))
                               for _, x in sorted(calls.items()))
            result = ModelResponse(self.redactor.clean(text), normalized, usage, request_id, actual_model)
            check_response(result, request)
            # Emit only finalized, redacted content: secrets can span arbitrary wire chunks.
            if result.content:
                yield StreamEvent("text", {"text": result.content})
            for call in result.tool_calls:
                yield StreamEvent("tool_call", asdict(call))
            yield StreamEvent("done", {"response": asdict(result)})
        except ModelError:
            raise
        except (ContractError, ValueError, KeyError, TypeError, AttributeError):
            raise ModelError("INVALID_PROVIDER_STREAM") from None
