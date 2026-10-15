"""Shared audited model calls for conversations and research workflows."""
from dataclasses import asdict, replace
import hashlib
from pathlib import Path
import time

from .contracts import fingerprint
from .llm import Message, ModelError, Redactor, Role, check_request, check_response, message_dict
from .security import BudgetExhausted, require_non_root
from .store import LedgerError, StateConflict


class ModelRuntime:
    def __init__(self, provider, store, redactor=None):
        require_non_root()
        self.provider, self.store = provider, store
        self.redactor = redactor or getattr(provider, "redactor", None) or Redactor()
        root = Path(__file__).parent
        self.core_code_hash = fingerprint({str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted(root.rglob("*.py"))})

    def _save(self, state, kind, data):
        for field in ("goal", "messages", "plan", "pending", "result", "error", "experiments"):
            setattr(state, field, self.redactor.clean(getattr(state, field)))
        try:
            self.store.save(state, kind, self.redactor.clean(data))
        except StateConflict:
            raise
        except Exception:
            raise LedgerError("LOCAL_LEDGER_UNAVAILABLE") from None

    @staticmethod
    def _reserve(state, field):
        if state.counters[field] >= state.budget["max_" + field]:
            raise BudgetExhausted(field)
        state.counters[field] += 1

    def _model(self, state, request):
        for retry in range(self.provider.config.max_retries + 1):
            # Conservative byte-based reservation, not a claim about actual tokenizer counts.
            estimate = len(str(request).encode('utf-8')) + self.provider.config.max_output_tokens
            accounted = state.usage['total_tokens'] + state.usage.get('unknown_reserved_tokens',0)
            if accounted + estimate > getattr(self, 'token_limit', 60000):
                raise BudgetExhausted('model_tokens')
            self._reserve(state, "model_calls")
            state.pending = {"kind": "model", "stage": state.stage}
            self._save(state, "MODEL_ATTEMPT", {"attempt": state.counters["model_calls"], "retry": retry,
                "provider_config": asdict(self.provider.config), "capabilities": asdict(self.provider.capabilities),
                "config_sha256": fingerprint(asdict(self.provider.config)), "core_code_sha256": self.core_code_hash,
                "token_budget": getattr(self, 'token_limit', 60000), "conservative_request_reservation": estimate,
                "request_sha256": fingerprint({"messages": [message_dict(x) for x in request.messages],
                    "tools": [asdict(x) for x in request.tools], "output_schema": request.output_schema,
                    "require_strict_schema": request.require_strict_schema, "require_tool_call": request.require_tool_call,
                    "json_object": request.json_object})})
            try:
                check_request(self.provider, request)
                response = self.provider.complete(request)
                response = replace(response, content=self.redactor.clean(response.content),
                    tool_calls=tuple(replace(x, id=self.redactor.clean(x.id), name=self.redactor.clean(x.name),
                                            arguments=self.redactor.clean(x.arguments)) for x in response.tool_calls))
                check_response(response, request)
            except Exception as exc:
                error = exc if isinstance(exc, ModelError) else ModelError("PROVIDER_ERROR")
                state.pending = None
                self._usage(state, error.usage)
                if error.usage is None or error.usage.total_tokens is None:
                    state.usage['unknown_reserved_tokens']=state.usage.get('unknown_reserved_tokens',0)+estimate
                self._save(state, "MODEL_FAILURE", {"code": error.code, "retryable": error.retryable,
                    "http_status": error.http_status, "validation_issue": error.validation_issue,
                    "usage": asdict(error.usage) if error.usage else None})
                if error.retryable and retry < self.provider.config.max_retries:
                    if error.code == "INVALID_STRUCTURED_OUTPUT" and error.validation_issue:
                        request = replace(request, messages=request.messages + (Message(Role.SYSTEM,
                            "The previous response failed local JSON validation (" + error.validation_issue +
                            "). Return a fresh valid JSON object with all required fields, escaped strings, and no extra keys; "
                            "keep every text field well under its length limit (summarise, do not copy long proposal text). "
                            "No action from the invalid response was executed."),))
                    time.sleep(min(error.retry_after or 0.1 * (2 ** retry), 2.0))
                    continue
                raise error from None
            state.pending = None
            self._usage(state, response.usage)
            if response.usage.total_tokens is None:
                state.usage['unknown_reserved_tokens']=state.usage.get('unknown_reserved_tokens',0)+estimate
            self._save(state, "MODEL_RESULT", {"usage": asdict(response.usage), "request_id": response.request_id,
                                                "content": response.content, "tool_calls": [asdict(x) for x in response.tool_calls],
                                                "actual_model": response.actual_model or self.provider.config.model})
            if state.usage['total_tokens'] + state.usage.get('unknown_reserved_tokens',0) > getattr(self, 'token_limit', 60000):
                raise BudgetExhausted('model_tokens')
            return response

    @staticmethod
    def _usage(state, usage):
        fields = ("input_tokens", "output_tokens", "total_tokens")
        if usage is not None:
            for field in fields:
                value = getattr(usage, field)
                if value is not None:
                    state.usage[field] += value
        if usage is None or any(getattr(usage, x) is None for x in fields):
            state.usage["unknown_calls"] += 1

