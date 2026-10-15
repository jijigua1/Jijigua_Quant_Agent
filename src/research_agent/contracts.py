"""Bounded JSON contracts. Validation never fetches remote schema references."""

import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

MAX_JSON_BYTES = 65536


class ContractError(ValueError):
    pass


def canonical(value: Any, *, max_bytes=MAX_JSON_BYTES) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("not finite JSON") from exc
    if len(text.encode("utf-8")) > max_bytes:
        raise ContractError("JSON exceeds size limit")
    return text


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def parse_json(text: str, *, max_bytes=MAX_JSON_BYTES) -> Any:
    if not isinstance(text, str) or len(text.encode("utf-8")) > max_bytes:
        raise ContractError("invalid JSON size")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ContractError("non-finite JSON")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
        canonical(value,max_bytes=max_bytes)
        return value
    except (ValueError, RecursionError) as exc:
        raise ContractError("invalid JSON") from exc


def validate(value: Any, schema: dict) -> None:
    canonical(value)

    def inspect(node, depth=0):
        if depth > 24:
            raise ContractError("schema too deep")
        if isinstance(node, dict):
            if any(k in node for k in ("$ref", "$dynamicRef", "$schema")):
                raise ContractError("external or recursive schema references are disabled")
            for item in node.values():
                inspect(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                inspect(item, depth + 1)

    inspect(schema)
    try:
        Draft202012Validator.check_schema(schema)
        error = next(Draft202012Validator(schema).iter_errors(value), None)
    except Exception as exc:
        raise ContractError("invalid local schema") from exc
    if error:
        # Values in jsonschema messages can contain secrets; persist only the constraint.
        raise ContractError("schema violation: " + str(error.validator))


def object_schema(properties: dict, required=None) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
PLAN_SCHEMA = object_schema({
    "action": {"enum": ["continue", "complete"]},
    "hypothesis": TEXT, "change_reason": TEXT,
    "summary": {"type": "string", "maxLength": 2000},
    "definition_change": {"type": "string", "maxLength": 1000},
}, required=["action", "hypothesis", "change_reason", "summary"])
