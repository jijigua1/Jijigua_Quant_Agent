"""Model access. Live calls go through the Research Agent's own DeepSeek adapter (no proxy, no redirect, response cap,
secret redaction); tests use a scripted client. Every call is budgeted, timed and logged (redacted) to the task ledger."""
from __future__ import annotations

import json
import re
import time

from .ledger import BudgetExceeded, canonical, sha256_text


class ModelFailure(RuntimeError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class InvalidStructuredOutput(RuntimeError):
    """The production adapter rejected a structured reply; `out` keeps the redacted reply and its usage for the ledger."""
    def __init__(self, out, issue):
        super().__init__(issue)
        self.out, self.issue = out, issue


def _strict_issue(text):
    """The production parser's view of a reply (duplicate keys and NaN/Infinity are invalid), in words the model can fix."""
    def pairs(items):
        seen = {}
        for k, v in items:
            if k in seen:
                raise ValueError(f"duplicate JSON key {k!r}")
            seen[k] = v
        return seen

    def nonfinite(c):
        raise ValueError(f"non-finite number {c}")
    try:
        json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
        return None
    except ValueError as e:
        return str(e)[:300]


def _first_mismatch(doc):
    """(position, expected closer) of the first closing bracket that does not match its opener (strings skipped)."""
    stack, in_str, esc = [], False, False
    for i, ch in enumerate(doc):
        if in_str:
            esc, in_str = (False, True) if esc else (ch == "\\", ch != '"')
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and {"}": "{", "]": "["}[ch] == stack[-1]:
                stack.pop()
            else:
                return i, ({"{": "}", "[": "]"}[stack[-1]] if stack else None)
    return None


def _bracket_repair(text, max_fixes=3):
    """Structure-only repair of a reply whose ONLY defect is a missing closing bracket before a mismatched one (live A/B:
    DeepSeek wrote '"}]}]' for '"}]}}]' and, at temperature 0, repeated it verbatim when asked to correct it). No character
    of any string or value changes: the expected closer is inserted at the mismatch. Returns (object, positions) or None;
    the caller still validates the schema and every claim is verified as usual."""
    start = text.find("{")
    if start < 0:
        return None
    doc, fixes = text[start:text.rfind("}") + 1], []

    def progress(d):
        try:
            json.loads(d)
            return float("inf")
        except json.JSONDecodeError as e:
            return e.pos if not str(e).startswith("Extra data") else -1

    for _ in range(max_fixes + 1):
        try:
            return json.loads(doc), fixes
        except json.JSONDecodeError as e:
            pos = e.pos
        cands = []
        m = _first_mismatch(doc)
        if m and m[1]:
            cands.append((f"insert {m[1]} at {m[0]}", doc[:m[0]] + m[1] + doc[m[0]:]))
        early = _premature_close(doc)
        if early is not None:          # A/B E08: one closer too many ended the root object early ("Extra data")
            cands.append((f"remove {doc[early]} at {early}", doc[:early] + doc[early + 1:]))
        for ch in "}],":
            cands.append((f"insert {ch} at {pos}", doc[:pos] + ch + doc[pos:]))
        scored = [(progress(d), what, d) for what, d in cands]
        best = max(scored, key=lambda x: x[0]) if scored else None
        if not best or best[0] <= pos:
            return None
        doc = best[2]
        fixes.append(best[1])
    return None


def _premature_close(doc):
    """Position of the closer that empties the bracket stack while non-blank text still follows (strings skipped)."""
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(doc):
        if in_str:
            esc, in_str = (False, True) if esc else (ch == "\\", ch != '"')
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i if doc[i + 1:].strip() else None
    return None


def _syntax_hint(e):
    """Where a JSON syntax error is, in words the model can act on: a character offset alone was repeated verbatim
    twice in live R2. Shows the text around the error and the first closing bracket that does not match its opener."""
    doc, pos = getattr(e, "doc", None), getattr(e, "pos", None)
    if not isinstance(doc, str) or pos is None:
        return ""
    stack, in_str, esc, bad = [], False, False, None
    for i, ch in enumerate(doc):
        if in_str:
            esc, in_str = (False, True) if esc else (ch == "\\", ch != '"')
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append((ch, i))
        elif ch in "}]":
            if not stack or {"}": "{", "]": "["}[ch] != stack[-1][0]:
                bad = (ch, i, stack[-1] if stack else None)
                break
            stack.pop()
    out = f" Text at the error: ...{doc[max(0, pos - 160):pos]}<<HERE>>{doc[pos:pos + 60]}..."
    if bad:
        ch, i, opener = bad
        out += (f" The '{ch}' at <<HERE>> does not match the innermost open bracket"
                + (f" '{opener[0]}' opened at: ...{doc[max(0, opener[1] - 60):opener[1] + 1]}" if opener else "")
                + ". Close every object with '}' and every array with ']' in the right order.")
    return out[:700]


def _validate(obj, schema):
    """Minimal JSON-Schema subset (type/required/enum/properties/items); qrtk_skills.runtime.validate when present."""
    try:
        from qrtk_skills.runtime import validate as v
        return v(obj, schema)
    except ImportError:                       # pragma: no cover
        return []


class ScriptedClient:
    """Deterministic stand-in for tests: returns queued responses (dict or str) per purpose, in order."""
    model = "scripted"
    live = False

    def __init__(self, responses):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls = []

    def raw(self, messages, *, purpose, max_tokens, json_mode=True, tools=None):
        self.calls.append({"purpose": purpose, "messages": messages, "tools": [t["name"] for t in tools or []]})
        queue = self.responses.get(purpose) or []
        if not queue:
            raise ModelFailure("SCRIPT_EXHAUSTED", purpose)
        item = queue.pop(0)
        if isinstance(item, dict) and "tool_calls" in item:
            return {"content": item.get("content", ""), "tool_calls": item["tool_calls"], "usage": {"total_tokens": 100},
                    "model": "scripted", "request_id": None}
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return {"content": text, "tool_calls": [], "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
                "model": "scripted", "request_id": None}


class DeepSeekClient:
    """Wraps research_agent.providers.deepseek.DeepSeekAdapter (the Agent's audited adapter)."""
    live = True

    # the Agent's ProviderConfig limits: max_output_tokens <= 4096, timeout_seconds <= 60
    def __init__(self, model="deepseek-flash", max_output_tokens=4096, timeout_seconds=60.0):
        from research_agent.llm import EnvironmentSecrets, ProviderConfig
        from research_agent.providers.deepseek import DeepSeekAdapter, HTTPTransport
        self.model = model
        self._cfg = dict(model=model, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
        self.adapter = DeepSeekAdapter(ProviderConfig("deepseek", model, max_output_tokens=max_output_tokens,
                                                      timeout_seconds=timeout_seconds, credential_ref="env:QRA_DEEPSEEK_API_KEY"),
                                       EnvironmentSecrets({"env:QRA_DEEPSEEK_API_KEY"}), HTTPTransport(allow_live=True))

    def raw(self, messages, *, purpose, max_tokens, json_mode=True, tools=None):
        from dataclasses import replace
        from research_agent.llm import Message, ModelRequest, Role, ToolCall, ToolDefinition
        msgs = []
        for m in messages:
            calls = tuple(ToolCall(c["id"], c["name"], c["arguments"]) for c in m.get("tool_calls") or ())
            msgs.append(Message(Role(m["role"]), m.get("content") or "", calls, m.get("tool_call_id")))
        self.adapter.config = replace(self.adapter.config, max_output_tokens=min(int(max_tokens), 4096))
        req = ModelRequest(tuple(msgs), tuple(ToolDefinition(t["name"], t["description"], t["parameters"]) for t in tools or ()),
                           output_schema={"type": "object"} if json_mode and not tools else None)
        from research_agent.llm import ModelError
        captured, send = [], self.adapter._send

        def tee(request, stream=False):                # keep the provider reply: a rejected one is still evidence
            for part in send(request, stream):
                captured.append(part)
                yield part
        self.adapter._send = tee
        try:
            r = self.adapter.complete(req)
        except ModelError as e:
            if e.code != "INVALID_STRUCTURED_OUTPUT" or not captured:
                raise
            value = json.loads(b"".join(captured).decode("utf-8"))
            u = value.get("usage") or {}
            out = {"content": self.adapter.redactor.clean(value["choices"][0]["message"].get("content") or ""), "tool_calls": [],
                   "usage": {"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                             "total_tokens": u.get("total_tokens")}, "model": value.get("model"), "request_id": value.get("id")}
            raise InvalidStructuredOutput(out, e.validation_issue or "invalid JSON") from None
        finally:
            del self.adapter._send
        return {"content": r.content, "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in r.tool_calls],
                "usage": {"prompt_tokens": r.usage.input_tokens, "completion_tokens": r.usage.output_tokens,
                          "total_tokens": r.usage.total_tokens}, "model": r.actual_model, "request_id": r.request_id}


def _extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise ModelFailure("NO_JSON", text[:200])
    return json.loads(text[start:text.rfind("}") + 1])


def ask_json(client, ledger, *, purpose, system, user, schema, max_tokens=4000, repair=1):
    """One structured call (+ at most `repair` corrective calls); returns (obj, record). Raw output is kept."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(repair + 1):
        ledger.check_budget(purpose)
        t0 = time.time()
        rejected = None
        try:
            out = client.raw(messages, purpose=purpose, max_tokens=max_tokens, json_mode=True)
        except InvalidStructuredOutput as e:            # recorded, charged and repaired like any malformed reply
            out, rejected = e.out, e.issue
        except BudgetExceeded:
            raise
        except ModelFailure:
            raise
        except Exception as e:  # noqa: BLE001  -- provider errors are recorded, never retried blindly
            if type(e).__name__ == "BudgetExhausted":   # the session's own budget: reported as such, not as a model error
                ledger.event("MODEL_ERROR", {"purpose": purpose, "code": "SESSION_BUDGET_EXHAUSTED"})
                raise
            code = getattr(e, "code", type(e).__name__)
            u = getattr(e, "usage", None)
            if u is not None and getattr(u, "total_tokens", None):     # tokens the provider billed are still charged
                ledger.charge_model(purpose, {"prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                                              "total_tokens": u.total_tokens}, time.time() - t0)
            ledger.event("MODEL_ERROR", {"purpose": purpose, "code": str(code)})
            if str(code) == "OUTPUT_TRUNCATED" and attempt < repair:
                # live A/B (CN04, a long Chinese paper): the reply hit the output limit; ask once for a shorter one
                messages = messages + [{"role": "user", "content":
                    "Your previous answer exceeded the output limit and was cut off. Answer again, much shorter: only the "
                    "factor(s) asked about (at most 2), quotes of at most 100 characters, at most 1 citation per item, at most "
                    "3 results_vs_methods, 3 unstated_details and 3 replication_notes. Same JSON structure."}]
                continue
            raise ModelFailure("MODEL_ERROR", str(code)) from None
        seconds = time.time() - t0
        ledger.charge_model(purpose, out["usage"], seconds)
        rid = f"{purpose}_{ledger.state['usage']['model_calls']:02d}"
        ledger.write_artifact(f"../model_io/{rid}.json", {"purpose": purpose, "attempt": attempt, "model": out.get("model"),
                                                         "request_id": out.get("request_id"), "usage": out["usage"],
                                                         "seconds": round(seconds, 3),
                                                         "prompt_sha256": sha256_text(canonical(messages)),
                                                         "messages": messages, "raw_output": out["content"],
                                                         "provider_contract_rejected": rejected})
        try:
            if rejected:
                raise ValueError(f"rejected by the production JSON contract ({rejected}): "
                                 f"{_strict_issue(out['content']) or 'not one bare JSON object'}")
            obj = _extract_json(out["content"])
            if isinstance(obj, dict) and obj.get("type") == "object" and "type" not in (schema.get("properties") or {}):
                obj.pop("type")                # structure-only normalisation: a stray echo of the contract, content untouched
            errors = _validate(obj, schema)
        except (ValueError, ModelFailure) as e:
            obj, errors = None, [f"invalid JSON: {e}.{_syntax_hint(e)}"]
            fixed = _bracket_repair(out["content"]) if not rejected and isinstance(e, json.JSONDecodeError) else None
            if fixed and not _validate(fixed[0], schema):
                obj, errors = fixed[0], []
                ledger.event("JSON_BRACKETS_REPAIRED", {"purpose": purpose, "record": rid, "inserted_at": fixed[1],
                                                        "note": "structure only: missing closing bracket(s) inserted; no text changed"})
        ledger.event("MODEL_CALL", {"purpose": purpose, "record": rid, "attempt": attempt, "tokens": out["usage"].get("total_tokens"),
                                    "schema_errors": errors[:5], "seconds": round(seconds, 3)})
        if not errors:
            return obj, {"record": rid, "usage": out["usage"], "model": out.get("model")}
        messages = messages + [{"role": "assistant", "content": out["content"]},
                               {"role": "user", "content": "Your JSON does not satisfy the contract: " + "; ".join(errors[:8]) +
                                ". Return the complete corrected JSON object only."}]
    raise ModelFailure("SCHEMA_INVALID_AFTER_REPAIR", "; ".join(errors[:5]))
