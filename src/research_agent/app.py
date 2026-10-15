"""Composition root. Config chooses providers; research code knows only Protocol."""

from dataclasses import replace
from pathlib import Path
import tomllib

from .contracts import ContractError, parse_json
from .llm import EnvironmentSecrets, ProviderConfig, Redactor
from .providers.deepseek import DeepSeekAdapter, HTTPTransport
from .providers.mock import MockProvider
from .security import Budget, Denied, Policy, require_non_root
from .skills import SkillRegistry
from .store import TaskStore
from .tools import mock_registry
from .workflow import Workflow

RESOURCES = Path(__file__).parent / "resources"


def load_policy(path=RESOURCES / "policy.toml"):
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    data["budget"] = Budget(**data["budget"])
    for field in ("allowed_tools", "resources", "write_scopes"):
        data[field] = tuple(data[field])
    try:
        return Policy(**data)
    except TypeError:
        raise ContractError("invalid policy fields") from None


def load_provider_config(name="mock", path=RESOURCES / "agent.toml"):
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    if set(data) != {"version", "default_provider", "providers"} or name not in data["providers"]:
        raise ContractError("invalid provider config")
    try:
        return ProviderConfig(**data["providers"][name])
    except TypeError:
        raise ContractError("invalid provider fields") from None


def make_provider(name, profile, secrets=None, redactor=None):
    config = load_provider_config(name)
    if config.provider != "deepseek":
        return MockProvider(config)
    if profile != "development":
        raise Denied("LIVE_PROVIDER_NOT_ENABLED_IN_PHASE1_D")
    secrets = secrets or EnvironmentSecrets({config.credential_ref})
    redactor = redactor or Redactor()
    redactor.add(secrets.resolve(config.credential_ref))
    return DeepSeekAdapter(config, secrets, HTTPTransport(allow_live=True), redactor)


def build(directory, provider_name="mock", *, provider=None, policy=None, tools=None, redactor=None,
          profile="offline", skill_id="mock_research", resources_manifest=None, secrets=None, research_config=None, _backend=None):
    require_non_root()
    if profile not in {"offline", "development"}:
        raise Denied("INVALID_PROFILE")
    policy = policy or load_policy()
    tools = tools or mock_registry()
    if profile == "development":
        policy = replace(policy, phase="development", version=policy.version + ":development")
    if resources_manifest is not None:
        from .quant import QUANT_SKILLS
        if profile != "development" or skill_id not in ('data_query',*QUANT_SKILLS):
            raise Denied("DATA_PROFILE_REQUIRED")
        from .data import ResourceCatalog
        try:
            catalog = ResourceCatalog(resources_manifest)
        except (OSError, ValueError, ContractError):
            raise Denied("DATA_CONFIGURATION_INVALID") from None
        if skill_id in QUANT_SKILLS:
            if research_config is None:
                raise Denied('RESEARCH_CONFIGURATION_REQUIRED')
            from .quant import QuantBackend
            backend=_backend or QuantBackend(catalog,research_config)
            tools=backend.registry()
            policy=replace(policy,allowed_tools=tuple(tools.versions),resources=tuple(backend.contracts),write_scopes=('research_runs',))
        else:
            tools = catalog.registry()
            policy = replace(policy, allowed_tools=tuple(tools.versions), resources=tuple(catalog.records))
    elif skill_id == "data_query":
        raise Denied("RESOURCE_MANIFEST_REQUIRED")
    if provider is None:
        provider = make_provider(provider_name, profile, secrets, redactor)
    manifest = parse_json((RESOURCES / "approved_skills.json").read_text(encoding="utf-8"))
    skills = SkillRegistry(RESOURCES / "skills", manifest, tools, policy)
    skill = skills.load(skill_id)
    workflow=Workflow(provider, tools, skill, policy, TaskStore(directory), redactor)
    if resources_manifest is not None and skill_id in QUANT_SKILLS:
        workflow.artifacts=backend.artifacts
        if backend.validation_pairs:workflow.tool_wall_seconds=600
    return workflow


def build_chat(directory, provider_name="deepseek", *, profile="development", resources_manifest=None,
               secrets=None, provider=None, session_id=None, research_config=None):
    from .conversation import Conversation
    require_non_root()
    if profile not in {"offline", "development"}:
        raise Denied("INVALID_PROFILE")
    provider = provider or make_provider(provider_name, profile, secrets)
    manifest = parse_json((RESOURCES / "approved_skills.json").read_text())
    registry = SkillRegistry(RESOURCES / "skills", manifest, mock_registry(), load_policy())
    from .quant import QUANT_SKILLS
    available = [x for x in registry.discover() if x["id"] == "mock_research" or
                 x["id"] == "data_query" and profile == "development" and resources_manifest is not None or
                 x['id'] in QUANT_SKILLS and profile=='development' and research_config is not None and resources_manifest is not None]
    configuration = {"policy": load_policy().digest, "profile": profile, "resources": None}
    registries = {"mock_research": mock_registry()}
    if resources_manifest is not None:
        if profile != "development":
            raise Denied("DATA_PROFILE_REQUIRED")
        from .data import ResourceCatalog
        catalog = ResourceCatalog(resources_manifest)
        configuration["resources"] = catalog.digest
        registries["data_query"] = catalog.registry()
        if research_config is not None:
            from .quant import QuantBackend
            backend=QuantBackend(catalog,research_config)
            configuration['research']=backend.digest
            registries.update({s:backend.registry() for s in QUANT_SKILLS})
    for metadata in available:
        metadata["tools"] = [t for t in registries[metadata["id"]].discover()
                             if metadata["tools"].get(t["id"]) == t["version"]]
        # Router needs capabilities, not repeated full argument schemas for every Skill.
        metadata["tools"] = [{k: t[k] for k in ('id', 'version', 'description','required_parameters')} for t in metadata['tools']]

    def workflow(skill_id):
        if skill_id not in {x["id"] for x in available}:
            raise Denied("SKILL_NOT_APPROVED")
        return build(directory, provider=provider, profile=profile, skill_id=skill_id,
                     resources_manifest=resources_manifest if skill_id in ('data_query',*QUANT_SKILLS) else None,
                     research_config=research_config,_backend=backend if research_config is not None and resources_manifest is not None and skill_id in QUANT_SKILLS else None)

    chat=Conversation(provider, TaskStore(directory), available, workflow, manifest, session_id=session_id,
                        configuration=configuration)
    if research_config is not None and resources_manifest is not None:
        chat.code_registry=backend.approved_registry
    if research_config is not None and resources_manifest is not None:
        from .test_access import describe
        try:              # the broker's status answer is side-effect free (no evaluation, no audit row)
            chat.test_access=describe(backend.rolling.status() if backend.rolling.available else None)
        except Exception:  # noqa: BLE001 -- an unreachable broker is stated, never guessed
            chat.test_access=describe(None)
        chat.published_resources=[{k:r[k] for k in ('id','partition','release_id','start_date','end_date','access_status')}
                                  for r in catalog.records.values() if r['format']=='published_npy']
    return chat
