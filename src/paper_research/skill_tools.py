"""The paper_research skill as tools for the existing qrtk_skills runtime (kept separate from
the five quantitative skills, whose manifest index is unchanged).

Documents reach tools only as host-registered DocumentRef objects in the DataCatalog; tools
never receive raw paths from a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qrtk_skills import DataCatalog, build_registry, load_skills
from qrtk_skills.runtime import SkillError, SkillRuntime

from . import export_research_spec, extract_research_spec, ingest_document, validate_research_spec
from .errors import PaperError

PAPER_SKILL_DIR = Path(__file__).resolve().parent / "skill"


@dataclass(frozen=True)
class DocumentRef:
    """A document the host allows to be read: the file and the root it must stay under."""
    path: str
    allowed_root: str


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except PaperError as e:
        raise SkillError(e.code, e.message) from e


def paper_ingest(ctx, document: str):
    ref = ctx.catalog.get(document)
    if not isinstance(ref, DocumentRef):
        raise SkillError("SCHEMA_INVALID", f"{document} is not a registered document reference")
    doc = _wrap(ingest_document, ref.path, allowed_roots=[ref.allowed_root])
    rep = doc["extraction_report"]
    out = {"doc_id": doc["doc_id"], "format": doc["source"]["format"], "language": doc["language"],
           "n_blocks": len(doc["blocks"]), "n_formulas": len(doc["formulas"]), "n_tables": len(doc["tables"]),
           "n_references": len(doc["references"]), "pages_unreadable": rep.get("pages_unreadable", []),
           "injection_findings": len(doc["security"]["injection_findings"]),
           "hidden_text_blocks": doc["security"]["hidden_text_blocks"]}
    out["document_ref"] = ctx.put(doc, "paper_document")
    out["ref"] = ctx.put(out, "paper_ingest_summary")
    return out


def paper_extract_spec(ctx, document: str):
    doc = ctx.artifacts.get(document, "paper_document")
    spec = extract_research_spec(doc)
    out = {"spec_id": spec["spec_id"], "supported_fields": sorted(spec["A_supported"]),
           "n_deductions": len(spec["B_deductions"]), "n_missing": len(spec["C_missing"]),
           "n_factors": len(spec["factors"]), "n_formulas": len(spec["formulas"]),
           "formulas_unresolved": spec["extraction_quality"]["formulas_unresolved"],
           "reproduction_status": spec["reproduction_status"]}
    out["spec_ref"] = ctx.put(spec, "paper_spec")
    out["ref"] = ctx.put(out, "paper_spec_summary")
    return out


def paper_validate_spec(ctx, spec: str, document: str):
    res = validate_research_spec(ctx.artifacts.get(spec, "paper_spec"), ctx.artifacts.get(document, "paper_document"))
    return {"valid": res["valid"], "errors": res["errors"][:20], "warnings": res["warnings"]}


def paper_export_spec(ctx, spec: str, basename: str):
    if ctx.artifact_dir is None:
        raise SkillError("PERMISSION_DENIED", "no writable artifact directory granted")
    import re
    if not re.fullmatch(r"[a-z0-9_]{1,64}", basename):
        raise SkillError("SCHEMA_INVALID", "basename must be 1-64 lowercase letters, digits or underscores")
    paths = _wrap(export_research_spec, ctx.artifacts.get(spec, "paper_spec"), ctx.artifact_dir, basename)
    return {"files": [Path(p).name for p in paths.values()]}


def register_paper_tools(registry):
    registry.register("paper.ingest", paper_ingest, ("read:catalog", "compute"))
    registry.register("paper.extract_spec", paper_extract_spec, ("compute",))
    registry.register("paper.validate_spec", paper_validate_spec, ("compute",))
    registry.register("paper.export_spec", paper_export_spec, ("compute", "write:artifacts"))
    return registry


def create_paper_runtime(catalog: DataCatalog, granted=("read:catalog", "compute"), artifact_dir=None) -> SkillRuntime:
    """The five quantitative skills plus paper_research, with their tools, under the host's grants."""
    skills = {**load_skills(), **load_skills(PAPER_SKILL_DIR)}
    return SkillRuntime(skills, register_paper_tools(build_registry()), catalog, frozenset(granted),
                        Path(artifact_dir) if artifact_dir else None)
