"""Local Skill Runtime: manifests, a mock tool protocol, and the checks around every call.

Not an agent. It only answers: may this skill call this tool with these arguments, and what
came back. A host (the future Codex adapter) can replace the registry, catalog and grants.

Call protocol (plain, JSON-serialisable dicts):
  ToolCall   {"skill": str, "tool": str, "args": {...}}
  ToolResult {"ok": bool, "tool": str, "skill": str, "data": {...} | None,
              "error": {"code": str, "message": str} | None, "audit_id": int}

Checks, in order (error codes in parentheses):
  1. skill is loaded                                   (UNKNOWN_SKILL)
  2. tool exists in the registry                       (UNKNOWN_TOOL)
  3. tool is declared in the skill's manifest          (CAPABILITY_DENIED)
  4. tool permissions are requested by the skill AND granted by the host
     -- a manifest alone never grants anything        (PERMISSION_DENIED)
  5. args match the tool's input schema                (SCHEMA_INVALID)
  6. data refs resolve in the registered catalog; no file paths are accepted
                                                       (DATA_NOT_REGISTERED / DATA_MISSING)
  7. the tool runs; any exception becomes              (TOOL_FAILED, or the tool's SkillError code)
  8. the output matches the tool's output schema       (OUTPUT_INVALID)
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
DATA_REF = re.compile(r"^data:[a-z0-9_]+$")
ART_REF = re.compile(r"^art:[0-9a-f]{12}$")


class SkillError(Exception):
    """Raise inside a tool to return a specific error code (e.g. INSUFFICIENT_EVIDENCE)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------- schema validation (small JSON-Schema subset) ----------------

def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Supported: type (object, array, string, integer, number, boolean, data_ref, artifact_ref,
    any), required, properties, additionalProperties=false, enum, minimum, maximum, items,
    minItems. Returns a list of error strings (empty = valid)."""
    t = schema.get("type", "any")
    errs: list[str] = []
    ok = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "data_ref": isinstance(value, str) and bool(DATA_REF.match(value)),
        "artifact_ref": isinstance(value, str) and bool(ART_REF.match(value)),
        "any": True,
    }
    if t not in ok:
        return [f"{path}: unsupported schema type {t}"]
    if not ok[t]:
        return [f"{path}: expected {t}, got {value!r}"[:200]]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in {schema['enum']}")
    if "minimum" in schema and value < schema["minimum"]:
        errs.append(f"{path}: {value} < {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errs.append(f"{path}: {value} > {schema['maximum']}")
    if t == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: required")
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties", True) is False:
                errs.append(f"{path}.{k}: not allowed")
    if t == "array":
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        for i, v in enumerate(value):
            errs += validate(v, schema.get("items", {}), f"{path}[{i}]")
    return errs


# ---------------- manifests ----------------

@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str
    description: str
    tools: tuple
    permissions: tuple
    resources: dict
    depends_python: tuple
    schemas: dict          # tool name -> {"input": schema, "output": schema}
    path: Path

    @classmethod
    def load(cls, folder: Path) -> "SkillManifest":
        meta = tomllib.loads((folder / "skill.toml").read_text(encoding="utf-8"))
        schemas = json.loads((folder / "schemas.json").read_text(encoding="utf-8"))
        s = meta["skill"]
        tools = tuple(meta["tools"]["allowed"])
        missing = [t for t in tools if t not in schemas]
        if missing:
            raise ValueError(f"{s['name']}: no schema for tools {missing}")
        if not (folder / "SKILL.md").is_file():
            raise ValueError(f"{s['name']}: SKILL.md missing")
        return cls(s["name"], s["version"], s["description"], tools,
                   tuple(meta["permissions"]["requested"]), dict(meta.get("resources", {})),
                   tuple(meta.get("dependencies", {}).get("python", [])), schemas, folder)


def load_skills(root: Path = SKILLS_DIR) -> dict[str, SkillManifest]:
    out = {}
    for folder in sorted(p for p in root.iterdir() if (p / "skill.toml").is_file()):
        m = SkillManifest.load(folder)
        if m.name in out:
            raise ValueError(f"duplicate skill {m.name}")
        out[m.name] = m
    return out


def manifest_index(skills: dict) -> dict:
    """Machine-readable index of all skills (written to skills/manifest.json)."""
    return {"format": "qrtk-skills-manifest/0.1", "skills": [
        {"name": m.name, "version": m.version, "description": m.description, "tools": list(m.tools),
         "permissions_requested": list(m.permissions), "resources": m.resources,
         "dependencies": list(m.depends_python), "schemas": f"skills/{m.path.name}/schemas.json"}
        for m in skills.values()]}


# ---------------- registry, catalog, artifacts ----------------

@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable[..., dict]
    permissions: tuple          # e.g. ("read:catalog", "compute", "write:artifacts")


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, name: str, fn: Callable, permissions=("compute",)):
        if name in self._tools:
            raise ValueError(f"tool {name} already registered")
        self._tools[name] = ToolSpec(name, fn, tuple(permissions))

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)


def _fingerprint(obj) -> str:
    try:
        import pandas as pd
        if isinstance(obj, (pd.DataFrame, pd.Series)):
            return hashlib.sha256(pd.util.hash_pandas_object(obj, index=True).values.tobytes()
                                  + str(list(getattr(obj, "columns", []))).encode()).hexdigest()
    except ImportError:
        pass
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class DataCatalog:
    """The only way a tool sees data: objects registered by the host under data:<name>."""

    def __init__(self):
        self._items: dict[str, tuple[Any, dict]] = {}

    def register(self, name: str, obj, **meta):
        if not DATA_REF.match(name):
            raise ValueError("catalog names look like data:<lowercase_name>")
        meta = {**meta, "sha256": _fingerprint(obj)}
        self._items[name] = (obj, meta)

    def get(self, ref: str):
        if ref not in self._items:
            raise SkillError("DATA_NOT_REGISTERED", f"{ref} is not in the data catalog")
        obj, _ = self._items[ref]
        if obj is None:
            raise SkillError("DATA_MISSING", f"{ref} is registered but has no data")
        return copy.deepcopy(obj)

    def meta(self, ref: str) -> dict:
        return dict(self._items[ref][1])


class ArtifactStore:
    """Immutable results passed between tools/skills by art:<id> (content-addressed)."""

    def __init__(self):
        self._items: dict[str, tuple[Any, dict]] = {}

    def put(self, obj, kind: str, producer: str) -> str:
        fp = _fingerprint(obj)
        ref = f"art:{hashlib.sha256((kind + fp).encode()).hexdigest()[:12]}"
        self._items[ref] = (copy.deepcopy(obj), {"kind": kind, "producer": producer, "sha256": fp})
        return ref

    def get(self, ref: str, kind: str | None = None):
        if ref not in self._items:
            raise SkillError("ARTIFACT_NOT_FOUND", f"{ref} does not exist")
        obj, meta = self._items[ref]
        if kind and meta["kind"] != kind:
            raise SkillError("SCHEMA_INVALID", f"{ref} is a {meta['kind']}, expected {kind}")
        return copy.deepcopy(obj)

    def meta(self, ref: str) -> dict:
        return dict(self._items[ref][1])


@dataclass
class ToolContext:
    """What a tool may use. No filesystem access except artifact_dir (if write is granted)."""
    catalog: DataCatalog
    artifacts: ArtifactStore
    artifact_dir: Path | None
    skill: str
    tool: str

    def put(self, obj, kind: str) -> str:
        return self.artifacts.put(obj, kind, f"{self.skill}/{self.tool}")


# ---------------- runtime ----------------

@dataclass
class SkillRuntime:
    skills: dict
    registry: ToolRegistry
    catalog: DataCatalog
    granted: frozenset = frozenset({"read:catalog", "compute"})
    artifact_dir: Path | None = None
    artifacts: ArtifactStore = field(default_factory=ArtifactStore)
    audit: list = field(default_factory=list)

    def call(self, skill: str, tool: str, args: dict) -> dict:
        audit_id = len(self.audit)
        entry = {"audit_id": audit_id, "skill": skill, "tool": tool, "args_sha256": _fingerprint(args)}

        def fail(code, msg):
            entry.update(ok=False, error_code=code)
            self.audit.append(entry)
            return {"ok": False, "skill": skill, "tool": tool, "data": None,
                    "error": {"code": code, "message": str(msg)[:500]}, "audit_id": audit_id}

        m = self.skills.get(skill)
        if m is None:
            return fail("UNKNOWN_SKILL", f"skill {skill} not loaded")
        spec = self.registry.get(tool)
        if spec is None:
            return fail("UNKNOWN_TOOL", f"tool {tool} is not registered")
        if tool not in m.tools:
            return fail("CAPABILITY_DENIED", f"skill {skill} does not declare tool {tool}")
        need = set(spec.permissions)
        if not need <= set(m.permissions):
            return fail("PERMISSION_DENIED", f"skill {skill} did not request {sorted(need - set(m.permissions))}")
        if not need <= set(self.granted):
            return fail("PERMISSION_DENIED", f"host did not grant {sorted(need - set(self.granted))}")
        if not isinstance(args, dict):
            return fail("SCHEMA_INVALID", "args must be an object")
        errs = validate(args, m.schemas[tool]["input"])
        if errs:
            return fail("SCHEMA_INVALID", "; ".join(errs))
        writable = self.artifact_dir if "write:artifacts" in need else None
        ctx = ToolContext(self.catalog, self.artifacts, writable, skill, tool)
        try:
            data = spec.fn(ctx, **copy.deepcopy(args))
        except SkillError as e:
            return fail(e.code, e)
        except Exception as e:  # noqa: BLE001 - every tool failure becomes a structured error
            return fail("TOOL_FAILED", f"{type(e).__name__}: {e}")
        errs = validate(data, m.schemas[tool]["output"])
        if errs:
            return fail("OUTPUT_INVALID", "; ".join(errs))
        entry.update(ok=True, output_sha256=_fingerprint(data))
        self.audit.append(entry)
        return {"ok": True, "skill": skill, "tool": tool, "data": data, "error": None, "audit_id": audit_id}
