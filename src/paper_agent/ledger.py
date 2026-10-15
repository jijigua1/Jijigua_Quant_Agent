"""Task directory, hash-chained event ledger, artifacts with fingerprints, budgets and resumable state."""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj) -> str:
    return sha256_text(canonical(obj))


class BudgetExceeded(RuntimeError):
    def __init__(self, what):
        super().__init__(f"BUDGET_EXHAUSTED: {what}")
        self.what = what


DEFAULT_BUDGET = {"model_calls": 24, "total_tokens": 400_000, "wall_seconds": 3600, "design_revisions": 3,
                  "orchestration_turns": 16}


class TaskLedger:
    """One research goal = one task directory. State is JSON; events are an append-only hash chain."""

    def __init__(self, root, task_id=None, *, goal=None, budget=None):
        self.root = Path(root)
        self.task_id = task_id or uuid.uuid4().hex
        self.dir = self.root / "tasks" / self.task_id
        new = not (self.dir / "state.json").exists()
        if new:
            if goal is None:
                raise FileNotFoundError(self.task_id)
            for sub in ("artifacts", "model_io", "candidates"):
                (self.dir / sub).mkdir(parents=True, exist_ok=True)
            self.state = {"task_id": self.task_id, "goal": goal, "status": "CREATED", "stage": None,
                          "created_at": datetime.now().astimezone().isoformat(), "budget": dict(budget or DEFAULT_BUDGET),
                          "usage": {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                                    "model_seconds": 0.0, "compute_seconds": 0.0, "by_purpose": {}},
                          "started_monotonic_wall": time.time(), "stages": {}, "decisions": [], "approvals": [],
                          "artifacts": {}, "messages": []}
            self.save()
            self.event("TASK_CREATED", {"goal": goal})
        else:
            self.state = json.loads((self.dir / "state.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- persistence
    def save(self):
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, self.dir / "state.json")

    def _last_hash(self):
        p = self.dir / "events.jsonl"
        if not p.exists():
            return "0" * 64
        lines = p.read_text(encoding="utf-8").strip().split("\n")
        return json.loads(lines[-1])["hash"] if lines and lines[-1] else "0" * 64

    def event(self, kind, payload=None):
        rec = {"time": datetime.now().astimezone().isoformat(), "kind": kind, "payload": payload or {}, "prev": self._last_hash()}
        rec["hash"] = sha256_text(rec["prev"] + canonical({k: rec[k] for k in ("time", "kind", "payload")}))
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(canonical(rec) + "\n")
        return rec

    def verify_chain(self):
        prev = "0" * 64
        p = self.dir / "events.jsonl"
        for line in p.read_text(encoding="utf-8").strip().split("\n"):
            rec = json.loads(line)
            if rec["prev"] != prev or rec["hash"] != sha256_text(prev + canonical({k: rec[k] for k in ("time", "kind", "payload")})):
                return False
            prev = rec["hash"]
        return True

    def events(self):
        p = self.dir / "events.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").strip().split("\n")] if p.exists() else []

    def write_artifact(self, name, obj, *, kind="json"):
        path = self.dir / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = obj if kind == "text" else json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True, default=str)
        path.write_text(text, encoding="utf-8")
        digest = sha256_text(text)
        self.state["artifacts"][name] = {"path": str(path), "sha256": digest}
        self.save()
        self.event("ARTIFACT_WRITTEN", {"name": name, "sha256": digest})
        return path, digest

    def read_artifact(self, name):
        rec = self.state["artifacts"].get(name)
        if not rec:
            return None
        text = Path(rec["path"]).read_text(encoding="utf-8")
        if sha256_text(text) != rec["sha256"]:
            raise RuntimeError(f"ARTIFACT_TAMPERED: {name}")
        return json.loads(text) if name.endswith(".json") else text

    # ---------------------------------------------------------------- budget
    def charge_model(self, purpose, usage, seconds):
        u = self.state["usage"]
        u["model_calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            u[k] += int(usage.get(k) or 0)
        u["model_seconds"] = round(u["model_seconds"] + seconds, 3)
        b = u["by_purpose"].setdefault(purpose, {"calls": 0, "total_tokens": 0, "seconds": 0.0})
        b["calls"] += 1
        b["total_tokens"] += int(usage.get("total_tokens") or 0)
        b["seconds"] = round(b["seconds"] + seconds, 3)
        self.save()

    def human_wait_seconds(self, now=None):
        """Time spent in AWAITING_* states (waiting for a person), from the hash-chained STATUS events."""
        total, since = 0.0, None
        for e in self.events():
            if e["kind"] != "STATUS":
                continue
            t = datetime.fromisoformat(e["time"]).timestamp()
            if since is not None:
                total += t - since
                since = None
            if str(e["payload"].get("status", "")).startswith("AWAITING_"):
                since = t
        if since is not None:
            total += (now or time.time()) - since
        return total

    def active_seconds(self, now=None):
        """Wall time of the task minus the time it waited for a human decision or approval."""
        now = now or time.time()
        return now - self.state["started_monotonic_wall"] - self.human_wait_seconds(now)

    def check_budget(self, purpose="model"):
        u, b = self.state["usage"], self.state["budget"]
        if u["model_calls"] >= b["model_calls"]:
            raise BudgetExceeded("model_calls")
        if u["total_tokens"] >= b["total_tokens"]:
            raise BudgetExceeded("total_tokens")
        if self.active_seconds() > b["wall_seconds"]:          # waiting for a person is not Agent time
            raise BudgetExceeded("wall_seconds")

    def set_status(self, status, **extra):
        self.state["status"] = status
        self.state.update(extra)
        self.save()
        self.event("STATUS", {"status": status, **{k: v for k, v in extra.items() if k != "messages"}})
