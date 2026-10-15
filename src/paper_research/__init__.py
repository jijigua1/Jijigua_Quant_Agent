"""paper_research: local-first academic paper / research report understanding.

ingest_document -> extract_research_spec -> validate_research_spec -> export_research_spec
                -> build_research_task -> validate_research_task -> export_research_task      (paper -> research task)
                -> build_candidate -> write_candidate_bundle                                  (untrusted, never executed)

All document content is untrusted data: nothing is executed, no URL is fetched, no file outside
the caller's allowed roots is read. Extraction is rule-based (no language model); supported
statements are verbatim quotes with source locations, and nothing absent is filled in.
Candidate factor code is generated and analysed as text only; it is never imported or executed here.
"""
from .document import ingest_document
from .errors import PaperError
from .extract import SPEC_SCHEMA, extract_research_spec
from .common import DOC_SCHEMA
from .spec import (export_research_spec, load_research_spec, spec_markdown, validate_document,
                   validate_research_spec)
from .factor_ir import IR_VERSION, IRError, parse_formula
from .dsl import DSL_CATALOG, compile_ir
from .task import (TASK_SCHEMA, build_research_task, export_research_task, task_markdown, to_qrtk_research_spec,
                   validate_research_task)
from .candidate import (analyze_source, build_candidate, promote_candidate, verify_candidate_bundle,
                        write_candidate_bundle)

__version__ = "0.3.0"
__all__ = ["ingest_document", "extract_research_spec", "validate_research_spec", "validate_document",
           "export_research_spec", "load_research_spec", "spec_markdown", "PaperError", "SPEC_SCHEMA", "DOC_SCHEMA",
           "IR_VERSION", "IRError", "parse_formula", "DSL_CATALOG", "compile_ir", "TASK_SCHEMA", "build_research_task",
           "validate_research_task", "export_research_task", "task_markdown", "to_qrtk_research_spec",
           "analyze_source", "build_candidate", "write_candidate_bundle", "verify_candidate_bundle", "promote_candidate"]
