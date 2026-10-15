"""Operator tool: register a study whose research definition was found wrong, and render its invalidation revision.

usage: python -I invalidate_study.py --workspace W --study-dir D --code CODE --evidence "..." [--evidence ...]
                                     [--detail "..."] --recorded-by NAME
Nothing in the study directory is deleted or rewritten; the record goes to the append-only, hash-chained register
<workspace>/state/study_invalidations.jsonl and one report revision is appended (its first lines state the invalidity).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]


def main(argv=None):
    from research_agent.artifacts import ResearchArtifacts
    from research_agent.invalidations import CODES, lookup, register
    from research_agent.report_versions import append_invalidation_report
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--study-dir", required=True)
    ap.add_argument("--code", required=True, choices=sorted(CODES))
    ap.add_argument("--evidence", action="append", required=True)
    ap.add_argument("--detail", default="")
    ap.add_argument("--recorded-by", required=True)
    a = ap.parse_args(argv)
    artifacts = ResearchArtifacts(a.workspace)
    run = artifacts.checked_run(a.study_dir)
    m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    study_id = m["task_id"] + ":" + m["run_id"]
    rec = lookup(a.workspace, study_id) or register(a.workspace, study_id=study_id, artifact_path=str(run), code=a.code,
                                                    evidence=a.evidence, recorded_by=a.recorded_by, detail=a.detail)
    row = append_invalidation_report(artifacts, run, rec)
    print(json.dumps({"study_id": study_id, "code": rec["code"], "revision": row["revision"], "html": row["html"],
                      "reused": row.get("reused")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
