"""Independent program authorization. A model plan is never a grant."""

from dataclasses import asdict, dataclass
import os
import re

from .contracts import ContractError, fingerprint, validate


class Denied(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class InvalidParameters(Denied):
    """A registered tool was selected, but its arguments failed the closed schema."""
    def __init__(self, violations=()):
        super().__init__("INVALID_PARAMETERS")
        self.violations = tuple(violations)


class BudgetExhausted(RuntimeError):
    pass


def require_non_root():
    if getattr(os, "geteuid", lambda: 1)() == 0:
        raise Denied("ROOT_AGENT_DENIED")


@dataclass(frozen=True)
class Budget:
    max_iterations: int = 4
    max_model_calls: int = 8
    max_tool_calls: int = 6

    def __post_init__(self):
        if any(type(x) is not int or not 0 <= x <= 100 for x in asdict(self).values()):
            raise ContractError("invalid budget")

    def intersect(self, other):
        return Budget(**{k: min(v, asdict(other)[k]) for k, v in asdict(self).items()})


@dataclass(frozen=True)
class Policy:
    version: str
    allowed_tools: tuple[str, ...]
    resources: tuple[str, ...]
    write_scopes: tuple[str, ...] = ()
    max_risk: str = "L0"
    requires_approval: bool = False
    budget: Budget = Budget()
    phase: str = "offline"

    def __post_init__(self):
        if (self.phase not in {"offline", "development"} or self.max_risk != "L0" or
                any(x != 'research_runs' for x in self.write_scopes) or self.write_scopes and self.phase != 'development'):
            raise ContractError("unsupported policy effects")

    @property
    def digest(self):
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class Authorization:
    task_id: str
    policy_hash: str
    skill_hash: str
    allowed_tools: tuple[str, ...]
    resources: tuple[str, ...]
    budget: Budget
    authority: str = "offline_mock_policy"
    # No approved field or model-controlled principal exists in this contract.


def authorize(tool, args, policy: Policy, grant: Authorization, skill):
    if tool.kind != "mock" and not (policy.phase == "development" and tool.kind in {"data_readonly", "quant_compute"}):
        raise Denied("BLOCKED_SECURITY")
    authority = "offline_mock_policy" if policy.phase == "offline" else (
        "development_research_policy" if policy.write_scopes else "development_readonly_policy")
    if grant.authority != authority or grant.policy_hash != policy.digest or grant.skill_hash != skill.digest:
        raise Denied("AUTHORIZATION_BINDING_MISMATCH")
    if tool.id not in policy.allowed_tools or tool.id not in grant.allowed_tools or tool.id not in skill.tools:
        raise Denied("TOOL_NOT_AUTHORIZED")
    if skill.tools[tool.id] != tool.version:
        raise Denied("TOOL_VERSION_MISMATCH")
    if policy.requires_approval or skill.permissions["requires_approval"] or tool.requires_approval:
        raise Denied("INDEPENDENT_APPROVAL_REQUIRED")
    if tool.risk != "L0" or (tool.write_scopes and (tool.kind != 'quant_compute' or
            any(x not in policy.write_scopes or x not in skill.permissions['write_scopes'] for x in tool.write_scopes))):
        raise Denied("TOOL_EFFECT_DENIED")
    try:
        validate(args, tool.input_schema)
    except ContractError:
        from jsonschema import Draft202012Validator
        violations=[]
        try:
            for error in Draft202012Validator(tool.input_schema).iter_errors(args):
                path=[];schema=tool.input_schema
                for part in error.absolute_path:
                    if type(part) is int:
                        path.append(part);schema=schema.get("items", {})
                    elif part in schema.get("properties", {}):
                        path.append(part);schema=schema["properties"][part]
                    else:
                        path.append("<extra-field>")
                violations.append({"path": "$"+"".join(f"[{x}]" if type(x) is int else "."+x for x in path),
                                   "constraint": error.validator})
        except Exception:
            violations=[]
        raise InvalidParameters(violations) from None
    if tool.resource_mode == "catalog":
        if not policy.resources or any(x not in grant.resources for x in policy.resources) or "resource:catalog" not in skill.permissions["data_paths"]:
            raise Denied("RESOURCE_NOT_AUTHORIZED")
        return
    resource = args.get("resource_id")
    if (resource not in policy.resources or resource not in grant.resources or
            "resource:" + resource not in skill.permissions["data_paths"] and not (
                tool.kind in {"data_readonly", "quant_compute"} and policy.phase == "development" and "resource:catalog" in skill.permissions["data_paths"])):
        raise Denied("RESOURCE_NOT_AUTHORIZED")


def valid_task_id(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise Denied("INVALID_TASK_ID")
    return value
