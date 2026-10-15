"""Append-only register of studies whose research DEFINITION was later found wrong (e.g. a look-back read as a lag).

Nothing is deleted or rewritten: the study directory, its reports and receipts stay byte-identical. A record names the
study, the reason and the evidence; records are hash-chained (each line carries the SHA-256 of the previous line), so an
edited or removed line is detected. Readers attach the latest record to the study; an operator renders one more report
revision whose first lines say the definition is invalid; an invalid study is never evaluated again.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

VERSION = "study_invalidations/1"
CODES = {"DEFINITION_LOOKBACK_READ_AS_LAG": "论文的回看期累计收益被执行成了滞后单期收益",
         "DEFINITION_ASSET_SUBSTITUTED_WITHOUT_CONSENT": "论文研究的资产被替换为A股个股，且当时没有经过资产替代的明确确认",
         "DEFINITION_SEMANTICS_WRONG": "执行定义与论文原文的语义不一致"}


class InvalidationError(ValueError):
    pass


def path(workspace):
    return Path(workspace) / "state" / "study_invalidations.jsonl"


def records(workspace):
    """All records, chain-verified (raises InvalidationError on a broken chain)."""
    p = path(workspace)
    if not p.exists():
        return []
    prev, out = "0" * 64, []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("prev_sha256") != prev:
            raise InvalidationError("INVALIDATION_CHAIN_BROKEN")
        prev = hashlib.sha256(line.encode("utf-8")).hexdigest()
        out.append(rec)
    return out


def lookup(workspace, study_id):
    found = [r for r in records(workspace) if r["study_id"] == study_id]
    return found[-1] if found else None


def register(workspace, *, study_id, artifact_path, code, evidence, recorded_by, detail=""):
    if code not in CODES:
        raise InvalidationError("UNKNOWN_INVALIDATION_CODE")
    if not evidence or not isinstance(evidence, list):
        raise InvalidationError("EVIDENCE_REQUIRED")
    existing = records(workspace)
    p = path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = hashlib.sha256(p.read_text(encoding="utf-8").splitlines()[-1].encode("utf-8")).hexdigest() if existing else "0" * 64
    rec = {"version": VERSION, "study_id": study_id, "artifact_path": str(artifact_path), "code": code,
           "reason_cn": CODES[code] + (("：" + detail) if detail else ""), "evidence": evidence[:8],
           "recorded_by": recorded_by, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "prev_sha256": prev}
    line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec
