"""paper_agent: DeepSeek-driven paper-to-factor research workflow built on paper_research v0.3.

Layers (each reuses existing code; nothing here re-implements PDF parsing, Factor IR or candidate generation):

  evidence      bounded, cached evidence index over a paper_research document (pages, blocks, formulas, tables)
  understanding DeepSeek structured paper reading; every claim must cite a verbatim quote that is re-checked locally,
                and is cross-checked against the deterministic v0.3 interpretation (conflicts block)
  planner       paper -> research plan: modes PAPER_ORIGINAL / EXPLORATORY_REPLICATION / APPROVED_RESEARCH_IMPLEMENTATION,
                v0.3 admission, data requirements, user decisions, frozen definition fingerprint
  algorithm     DSL first; otherwise DeepSeek designs a Python candidate, v0.3 static analysis + repair loop, bundle
  registry      human approval of an exact candidate SHA-256, post-approval known-truth tests, trusted registration
  trusted_ir    reviewed vectorised Factor IR executor used as the independent reference on real panels
  study_bridge  runs an approved implementation or a DSL expression through the Agent's own study/report pipeline
  orchestrator  one research goal across stages (paper, specification, development, evaluation, report) with
                machine-checked stage outputs, budgets, resume and gates the model cannot bypass
  cli           `chat` terminal entry for the isolated deployment

Model-generated code is never executed before a human approves its exact hash, and no part of this package is, or
claims to be, a security sandbox.
"""
__version__ = "0.1.0"
