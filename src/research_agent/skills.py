"""Discover small metadata first; load only content pinned by a trusted manifest."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tomllib

from .contracts import ContractError, fingerprint, object_schema, parse_json, validate
from .security import Budget, Denied

FILES = ("skill.toml", "SKILL.md", "input.schema.json", "output.schema.json", "example.json")


@dataclass(frozen=True)
class Skill:
    id: str
    version: str
    summary: str
    digest: str
    method: str
    tools: dict
    permissions: dict
    budget: Budget
    validator_id: str
    input_schema: dict
    output_schema: dict


SKILL_SCHEMA = object_schema({
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,40}$"},
    "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "contract_version": {"const": "research-v1"},
    "summary": {"type": "string", "minLength": 1, "maxLength": 300},
    "tools": {"type": "object", "minProperties": 1, "maxProperties": 8,
              "additionalProperties": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"}},
    "depends_on": {"type": "array", "items": {"enum": ["contracts-v1"]}, "uniqueItems": True},
    "validator": {"enum": ["mock_research_v1", "data_query_v1", "quant_research_v1"]},
    "permissions": object_schema({
        "data_paths": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string"}, "uniqueItems": True},
        "write_scopes": {"type": "array", "maxItems": 1, "items":{"enum":["research_runs"]}}, "network": {"const": "none"},
        "gpu": {"const": False}, "risk_level": {"const": "L0"}, "requires_approval": {"type": "boolean"},
    }),
    "budget": object_schema({
        "max_iterations": {"type": "integer", "minimum": 0, "maximum": 100},
        "max_model_calls": {"type": "integer", "minimum": 0, "maximum": 100},
        "max_tool_calls": {"type": "integer", "minimum": 0, "maximum": 100},
        "max_jobs": {"const": 0}, "cpu_cores": {"const": 1}, "memory_mib": {"enum": [64,1024,4096]},
        "pids": {"const": 1}, "job_wall_seconds": {"enum":[1,30,600]}, "output_mib": {"enum":[0,20,512]},
    }),
    "acceptance": object_schema({"cases": {"type": "array", "minItems": 1, "items": {"enum": ["mock_research_smoke", "data_query_smoke", "quant_research_smoke"]}},
                                 "stop_on": {"const": ["authorization_denied", "tool_error", "budget_exhausted"]}}),
})


class SkillRegistry:
    def __init__(self, root: Path, manifest: dict, tools, policy):
        self.root = Path(root)
        self.manifest = manifest
        self.tools = tools
        self.policy = policy
        self._metadata = {}
        self.loaded = set()

    def _read(self, skill_id, filename):
        if skill_id not in self.manifest or filename not in FILES:
            raise Denied("SKILL_NOT_APPROVED")
        path = self.root / skill_id / filename
        for parent in (self.root, self.root / skill_id, path):
            if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
                raise Denied("SKILL_LINK_DENIED")
        try:
            if path.stat().st_size > 65536 or path.stat().st_nlink != 1:
                raise Denied("SKILL_FILE_DENIED")
            value = path.read_bytes()
        except OSError:
            raise Denied("SKILL_FILE_UNAVAILABLE") from None
        if hashlib.sha256(value).hexdigest() != self.manifest[skill_id].get(filename):
            raise Denied("SKILL_HASH_MISMATCH")
        return value

    def discover(self):
        self._metadata = {}
        for skill_id in self.manifest:
            if not isinstance(skill_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", skill_id):
                raise Denied("INVALID_SKILL_ID")
            try:
                metadata = tomllib.loads(self._read(skill_id, "skill.toml").decode("utf-8"))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                raise Denied("INVALID_SKILL_DECLARATION") from None
            try:
                validate(metadata, SKILL_SCHEMA)
            except ContractError:
                raise Denied("INVALID_SKILL_DECLARATION") from None
            if metadata["id"] != skill_id:
                raise Denied("SKILL_ID_MISMATCH")
            self._metadata[skill_id] = metadata
        return [{"id": x["id"], "version": x["version"], "summary": x["summary"], "tools": x["tools"]}
                for x in self._metadata.values()]

    def load(self, skill_id):
        self.discover()
        if skill_id not in self._metadata:
            raise Denied("SKILL_NOT_APPROVED")
        files = {name: self._read(skill_id, name) for name in FILES}
        metadata = self._metadata[skill_id]
        for tool_id, version in metadata["tools"].items():
            if tool_id not in self.policy.allowed_tools or self.tools.versions.get(tool_id) != version:
                raise Denied("SKILL_TOOL_DENIED")
        allowed_paths = {"resource:" + v for v in self.policy.resources}
        if self.policy.phase == "development":
            allowed_paths.add("resource:catalog")
        if any(x not in allowed_paths for x in metadata["permissions"]["data_paths"]):
            raise Denied("SKILL_SCOPE_DENIED")
        if any(x not in self.policy.write_scopes for x in metadata['permissions']['write_scopes']):
            raise Denied('SKILL_WRITE_SCOPE_DENIED')
        input_schema = parse_json(files["input.schema.json"].decode())
        output_schema = parse_json(files["output.schema.json"].decode())
        example = parse_json(files["example.json"].decode())
        validate(example["input"], input_schema)
        validate(example["output"], output_schema)
        budget = Budget(**{k: metadata["budget"][k] for k in ("max_iterations", "max_model_calls", "max_tool_calls")})
        self.loaded.add(skill_id)
        return Skill(skill_id, metadata["version"], metadata["summary"], fingerprint(self.manifest[skill_id]),
                     files["SKILL.md"].decode("utf-8"), metadata["tools"], metadata["permissions"],
                     budget, metadata["validator"], input_schema, output_schema)
