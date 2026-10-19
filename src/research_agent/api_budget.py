"""Cumulative DeepSeek budget across sessions and processes (Candidate6 recovery, design E).

One SQLite file holds operator-created campaigns: a request limit and a token limit. Before EVERY HTTP send the adapter
reserves, in one `BEGIN IMMEDIATE` transaction, one request and a conservative token amount (request bytes + the output
limit). After the reply the reservation is settled against the reported usage, conservatively:

    charged = max(reserved, total_tokens, prompt_tokens + completion_tokens, prompt_tokens, completion_tokens)

using only values that are non-negative integers; unknown or malformed usage keeps the reservation. Nothing is ever
refunded (a crash after reserving keeps the charge). When the charged total passes the token limit the campaign is
FROZEN: every later reservation, from any process or session, is refused before the HTTP request. Campaigns are never
created, reset or unfrozen by the agent itself; `python -m research_agent.api_budget` is the operator's tool.

Enabled by QRA_API_BUDGET_DB (+ QRA_API_BUDGET_CAMPAIGN). With a budget active, automatic HTTP retries are off.
"""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

from .llm import ModelError

ENV_DB, ENV_CAMPAIGN = "QRA_API_BUDGET_DB", "QRA_API_BUDGET_CAMPAIGN"
SCHEMA = """CREATE TABLE IF NOT EXISTS campaign (id TEXT PRIMARY KEY, max_requests INTEGER NOT NULL, max_tokens INTEGER NOT NULL,
    used_requests INTEGER NOT NULL DEFAULT 0, used_tokens INTEGER NOT NULL DEFAULT 0, frozen INTEGER NOT NULL DEFAULT 0,
    frozen_reason TEXT, created REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS ticket (id TEXT PRIMARY KEY, campaign TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER,
    usage TEXT, state TEXT NOT NULL, created REAL NOT NULL, settled REAL);"""


def _connect(path):
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn


def create_campaign(path, campaign, *, max_requests, max_tokens, note=""):
    """Operator only. Refuses to touch an existing campaign (no reset)."""
    if type(max_requests) is not int or type(max_tokens) is not int or max_requests < 1 or max_tokens < 1:
        raise ValueError("positive integer limits required")
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM campaign WHERE id=?", (campaign,)).fetchone():
            conn.execute("ROLLBACK")
            raise ValueError("campaign exists; campaigns are never reset")
        conn.execute("INSERT INTO campaign (id, max_requests, max_tokens, created, note) VALUES (?,?,?,?,?)",
                     (campaign, max_requests, max_tokens, time.time(), note))
        conn.execute("COMMIT")
    finally:
        conn.close()


def charged(reserved, usage):
    """(tokens charged, anomaly). Only non-negative integers count; a missing or contradictory total never hides the parts."""
    usage = usage if isinstance(usage, dict) else {}
    vals, anomaly = {}, not isinstance(usage, dict) or not usage
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        v = usage.get(k)
        if type(v) is int and v >= 0:
            vals[k] = v
        elif v is not None:
            anomaly = True
    if not vals:
        return reserved, True
    candidates = [reserved] + list(vals.values())
    if "prompt_tokens" in vals and "completion_tokens" in vals:
        parts = vals["prompt_tokens"] + vals["completion_tokens"]
        candidates.append(parts)
        if "total_tokens" in vals and vals["total_tokens"] < parts:
            anomaly = True                           # total contradicts its own parts: the parts are kept
    return max(candidates), anomaly


class Budget:
    def __init__(self, path, campaign):
        self.path, self.campaign = Path(path), campaign

    @classmethod
    def from_environment(cls):
        db = os.environ.get(ENV_DB)
        return cls(db, os.environ.get(ENV_CAMPAIGN) or "") if db else None

    def reserve(self, estimate):
        """One request + `estimate` tokens, atomically, before the HTTP send. Returns the ticket id."""
        if not self.path.is_file():
            raise ModelError("API_BUDGET_MISSING")              # configured but absent: never fall back to unlimited
        conn = _connect(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT max_requests, max_tokens, used_requests, used_tokens, frozen FROM campaign WHERE id=?",
                               (self.campaign,)).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise ModelError("API_BUDGET_CAMPAIGN_MISSING")
            max_req, max_tok, used_req, used_tok, frozen = row
            if frozen:
                conn.execute("ROLLBACK")
                raise ModelError("API_BUDGET_FROZEN")
            if used_req + 1 > max_req or used_tok + estimate > max_tok:
                conn.execute("ROLLBACK")
                raise ModelError("API_BUDGET_EXHAUSTED")
            ticket = uuid.uuid4().hex
            conn.execute("UPDATE campaign SET used_requests=used_requests+1, used_tokens=used_tokens+? WHERE id=?",
                         (int(estimate), self.campaign))
            conn.execute("INSERT INTO ticket (id, campaign, reserved, state, created) VALUES (?,?,?,?,?)",
                         (ticket, self.campaign, int(estimate), "RESERVED", time.time()))
            conn.execute("COMMIT")
            return ticket
        finally:
            conn.close()

    def settle(self, ticket, usage):
        """Charge the reply's usage conservatively (never below the reservation); freeze when the limit is passed."""
        conn = _connect(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT reserved, state FROM ticket WHERE id=? AND campaign=?", (ticket, self.campaign)).fetchone()
            if row is None or row[1] != "RESERVED":
                conn.execute("ROLLBACK")
                return None
            reserved = row[0]
            amount, anomaly = charged(reserved, usage)
            conn.execute("UPDATE campaign SET used_tokens=used_tokens+? WHERE id=?", (amount - reserved, self.campaign))
            conn.execute("UPDATE ticket SET charged=?, usage=?, state=?, settled=? WHERE id=?",
                         (amount, json.dumps(usage if isinstance(usage, dict) else None, default=str)[:2000],
                          "SETTLED_ANOMALY" if anomaly else "SETTLED", time.time(), ticket))
            used, limit = conn.execute("SELECT used_tokens, max_tokens FROM campaign WHERE id=?", (self.campaign,)).fetchone()
            if used > limit:
                conn.execute("UPDATE campaign SET frozen=1, frozen_reason=? WHERE id=?",
                             (f"tokens {used} > limit {limit} after ticket {ticket}", self.campaign))
            conn.execute("COMMIT")
            return amount
        finally:
            conn.close()

    def state(self):
        conn = _connect(self.path)
        try:
            row = conn.execute("SELECT max_requests, max_tokens, used_requests, used_tokens, frozen, frozen_reason FROM campaign "
                               "WHERE id=?", (self.campaign,)).fetchone()
        finally:
            conn.close()
        keys = ("max_requests", "max_tokens", "used_requests", "used_tokens", "frozen", "frozen_reason")
        return dict(zip(keys, row)) if row else None


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="python -m research_agent.api_budget", description="operator: create or show a campaign")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("db"), c.add_argument("campaign"), c.add_argument("--max-requests", type=int, required=True)
    c.add_argument("--max-tokens", type=int, required=True), c.add_argument("--note", default="")
    s = sub.add_parser("show")
    s.add_argument("db"), s.add_argument("campaign")
    a = p.parse_args(argv)
    if a.cmd == "create":
        create_campaign(a.db, a.campaign, max_requests=a.max_requests, max_tokens=a.max_tokens, note=a.note)
    print(json.dumps(Budget(a.db, a.campaign).state(), ensure_ascii=False))


if __name__ == "__main__":
    main()
