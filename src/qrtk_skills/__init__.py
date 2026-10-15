"""Quant research skills v0.1: manifests + local mock-tool runtime around qrtk.

Synthetic-data verified only. Not an agent: a host decides which skill and tool to call.
"""
from pathlib import Path

from .runtime import (ArtifactStore, DataCatalog, SkillError, SkillManifest, SkillRuntime,
                      ToolRegistry, load_skills, validate)
from .tools import ENGINES, build_registry, register_engine

__version__ = "0.1.0"


def create_runtime(catalog: DataCatalog, granted=("read:catalog", "compute"),
                   artifact_dir: Path | None = None, skills_dir: Path | None = None) -> SkillRuntime:
    """Load the five skills, register the local tools, apply the host's grants."""
    skills = load_skills(skills_dir) if skills_dir else load_skills()
    return SkillRuntime(skills, build_registry(), catalog, frozenset(granted),
                        Path(artifact_dir) if artifact_dir else None)
