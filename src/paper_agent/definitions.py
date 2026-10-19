"""Registry of canonical research definitions for one paper (2026-10-16).

One record per canonical definition SHA (paper_agent.canonical), kept next to the paper's ledger:
    definitions/<sha>.json            record, status, approvals, executions, supersession / invalidation
    definitions/<sha>.sources.json    the verified reading, plan and research task the definition was built from
    definitions/events.jsonl          append-only, hash-chained log of every transition

Lifecycle:  PROPOSED -> APPROVAL_REQUIRED -> APPROVED -> FROZEN -> EXECUTED          (BLOCKED, SUPERSEDED, INVALIDATED)
A plan that needs no decision goes PROPOSED -> FROZEN when it is first executed. Approval is bound to the definition SHA
and records its scope (session, the substitutions shown, whether the exact asset phrase was given). A frozen definition is
reused for the same paper, the same requested factor and the same user-typed values of the CURRENT session: the stored
reading is checked again by the current program and must give the same SHA, otherwise the old record is SUPERSEDED and
the new definition goes through the normal decision. An INVALIDATED definition is never reused. Nothing is deleted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

VERSION = "paper_agent.definitions/1"
STATES = ("PROPOSED", "APPROVAL_REQUIRED", "BLOCKED", "APPROVED", "FROZEN", "EXECUTED", "SUPERSEDED", "INVALIDATED")
REUSABLE = ("APPROVED", "FROZEN", "EXECUTED")
SHA = re.compile(r"[0-9a-f]{64}")


class RegistryError(ValueError):
    pass


class DefinitionRegistry:
    def __init__(self, ledger_root):
        self.root = Path(ledger_root) / "definitions"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise RegistryError("DEFINITIONS_LINK")
        self.events = self.root / "events.jsonl"

    # ------------------------------------------------------------------ storage
    def _path(self, sha, suffix=".json"):
        if not SHA.fullmatch(sha or ""):
            raise RegistryError("DEFINITION_SHA_INVALID")
        return self.root / (sha + suffix)

    def get(self, sha):
        p = self._path(sha)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def sources(self, sha):
        p = self._path(sha, ".sources.json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _write(self, sha, rec):
        p = self._path(sha)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, p)

    def _event(self, kind, sha, **payload):
        prev = "0" * 64
        if self.events.exists():
            lines = self.events.read_text(encoding="utf-8").splitlines()
            if lines:
                prev = json.loads(lines[-1])["hash"]
        body = {"kind": kind, "definition_sha256": sha, "time": time.time(), "payload": payload, "prev": prev}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        with self.events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(body, ensure_ascii=False, default=str) + "\n")

    def verify_chain(self):
        prev = "0" * 64
        if not self.events.exists():
            return True
        for line in self.events.read_text(encoding="utf-8").splitlines():
            body = json.loads(line)
            h = body.pop("hash")
            if body["prev"] != prev or hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest() != h:
                raise RegistryError("DEFINITION_EVENTS_CHAIN_BROKEN")
            prev = h
        return True

    def all(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.root.glob("*.json"))
                if SHA.fullmatch(p.stem) and p.name.count(".") == 1]

    # ------------------------------------------------------------------ lifecycle
    def propose(self, record, *, plan_status, user_params, session_id, sources=None):
        """Register a canonical definition (idempotent). Returns the stored record."""
        sha = record["definition_sha256"]
        rec = self.get(sha)
        if rec is None:
            status = "BLOCKED" if plan_status == "BLOCKED" else ("APPROVAL_REQUIRED" if plan_status == "AWAITING_USER_DECISION" else "PROPOSED")
            rec = dict(record, version=VERSION, status=status, created_at=time.time(), user_params=dict(user_params or {}),
                       proposed_in_sessions=[session_id], approvals=[], executions=[], superseded_by=None, invalidation=None)
            self._write(sha, rec)
            if sources is not None:
                self._path(sha, ".sources.json").write_text(json.dumps(sources, ensure_ascii=False, default=str), encoding="utf-8")
            self._event("PROPOSED", sha, status=status, factor_key=record.get("factor_key"), session_id=session_id)
        elif session_id not in rec.get("proposed_in_sessions", []):
            rec["proposed_in_sessions"] = rec.get("proposed_in_sessions", []) + [session_id]
            self._write(sha, rec)
        return rec

    def approved(self, sha, *, asset_consent_required=False):
        """An approval of exactly this definition whose scope covers what it needs (the asset phrase when required)."""
        rec = self.get(sha)
        if not rec or rec["status"] not in REUSABLE:
            return None
        for a in rec.get("approvals", []):
            if asset_consent_required and not a.get("asset_phrase"):
                continue
            return a
        return None

    def approve(self, sha, *, session_id, task_id, substitutions, asset_phrase):
        rec = self._require(sha)
        if rec["status"] in ("INVALIDATED", "SUPERSEDED", "BLOCKED"):
            raise RegistryError("DEFINITION_NOT_APPROVABLE_" + rec["status"])
        approval = {"session_id": session_id, "task_id": task_id, "time": time.time(), "asset_phrase": bool(asset_phrase),
                    "substitutions_shown": sorted({s.get("kind") for s in substitutions or []})}
        rec["approvals"].append(approval)
        if rec["status"] in ("PROPOSED", "APPROVAL_REQUIRED"):
            rec["status"] = "APPROVED"
        self._write(sha, rec)
        self._event("APPROVED", sha, **approval)
        return rec

    def freeze(self, sha, *, needs_approval):
        rec = self._require(sha)
        if rec["status"] in ("INVALIDATED", "SUPERSEDED", "BLOCKED"):
            raise RegistryError("DEFINITION_NOT_EXECUTABLE_" + rec["status"])
        if needs_approval and not rec.get("approvals"):
            raise RegistryError("DEFINITION_NOT_APPROVED")
        if rec["status"] in ("PROPOSED", "APPROVAL_REQUIRED", "APPROVED"):
            rec["status"] = "FROZEN"
            rec["frozen_at"] = time.time()
            self._write(sha, rec)
            self._event("FROZEN", sha)
        return rec

    def executed(self, sha, execution):
        rec = self._require(sha)
        rec["executions"].append(dict(execution, time=time.time()))
        rec["status"] = "EXECUTED"
        self._write(sha, rec)
        self._event("EXECUTED", sha, **{k: execution.get(k) for k in ("study_id", "execution_sha256")})
        return rec

    def supersede(self, old, new, reason):
        rec = self._require(old)
        if rec["status"] != "INVALIDATED":
            rec["status"] = "SUPERSEDED"
        rec["superseded_by"] = {"definition_sha256": new, "reason": reason, "time": time.time()}
        self._write(old, rec)
        self._event("SUPERSEDED", old, by=new, reason=reason)

    def invalidate(self, sha, *, code, reason, evidence, recorded_by):
        rec = self._require(sha)
        rec["status"] = "INVALIDATED"
        rec["invalidation"] = {"code": code, "reason": reason, "evidence": list(evidence), "recorded_by": recorded_by, "time": time.time()}
        self._write(sha, rec)
        self._event("INVALIDATED", sha, code=code, recorded_by=recorded_by)
        return rec

    def _require(self, sha):
        rec = self.get(sha)
        if rec is None:
            raise RegistryError("DEFINITION_UNKNOWN")
        return rec

    # ------------------------------------------------------------------ reuse
    def reusable(self, *, paper_sha256, requested_factor, user_params):
        """The newest reusable definition for this paper, requested factor and exactly these user-typed values."""
        from .canonical import NUMBERED, factor_key
        want = factor_key("", requested_factor) if requested_factor else ""
        number = NUMBERED.search(requested_factor or "")
        hits = []
        for rec in self.all():
            if rec["status"] not in REUSABLE or rec["math"]["paper_sha256"] != paper_sha256:
                continue
            if (rec.get("user_params") or {}) != dict(user_params or {}) or rec.get("user_version"):
                continue                           # a user's own version belongs to the session that made it
            if rec["math"].get("algorithm") or rec["math"].get("formula_ir") is None:
                continue                           # a non-IR algorithm is model prose: never reused, confirmed afresh each time
            shown = (rec.get("display") or {}).get("factor") or ""
            if number:
                if f"alpha#{int(number.group(2))}" != rec.get("factor_key"):
                    continue                       # numbered factors never match another number
            elif want and not (want == rec.get("factor_key") or (requested_factor or "").lower() in shown.lower()
                               or shown.lower() in (requested_factor or "").lower()):
                continue
            elif not want and rec.get("requested_factor_key"):
                continue                           # a request without a factor reuses only a definition made the same way
            hits.append(rec)
        return max(hits, key=lambda r: r.get("frozen_at") or r.get("created_at") or 0) if hits else None
