"""SQLite checkpoints, experiments and authorization events in an explicit workspace."""

from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .contracts import canonical, parse_json
from .security import Authorization, Budget, Denied, valid_task_id

# A checkpoint aggregates several separately validated 64 KiB tool results.
MAX_LEDGER_BYTES = 1024 * 1024


class StateConflict(RuntimeError):
    pass


class LedgerError(RuntimeError):
    pass


@dataclass
class TaskState:
    id: str
    goal: str
    binding: str
    provider: str
    model: str
    skill_id: str
    skill_hash: str
    budget: dict
    status: str = "CREATED"
    stage: str = "planning"
    revision: int = 0
    counters: dict = field(default_factory=lambda: {"iterations": 0, "model_calls": 0, "tool_calls": 0})
    messages: list = field(default_factory=list)
    experiments: list = field(default_factory=list)
    plan: dict | None = None
    pending: dict | None = None
    result: dict | None = None
    error: dict | None = None
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "unknown_calls": 0})
    execution_mode: str = "offline_mock"
    session_id: str | None = None


class TaskStore:
    def __init__(self, directory):
        path = Path(directory).absolute()
        for component in (path, *path.parents):
            junction = getattr(component, "is_junction", lambda: False)()
            if component.is_symlink() or junction:
                raise Denied("STATE_DIRECTORY_LINK_DENIED")
        path.mkdir(parents=True, exist_ok=True)
        self.directory = path
        self.path = path / "research.sqlite3"
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            raise Denied("STATE_DATABASE_LINK_DENIED")
        with closing(self._connect()) as db, db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS authorizations(task_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, at_utc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_turns(session_id TEXT NOT NULL, turn INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(session_id,turn));
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _event(db, task_id, kind, payload):
        db.execute("INSERT INTO events(task_id,kind,payload,at_utc) VALUES(?,?,?,?)",
                   (task_id, kind, canonical(payload,max_bytes=MAX_LEDGER_BYTES), datetime.now(timezone.utc).isoformat()))

    def create(self, state, grant):
        valid_task_id(state.id)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO tasks VALUES(?,?,?)", (state.id, 0, canonical(asdict(state),max_bytes=MAX_LEDGER_BYTES)))
            db.execute("INSERT INTO authorizations VALUES(?,?)", (state.id, canonical(asdict(grant))))
            self._event(db, state.id, "AUTHORIZATION_ISSUED", asdict(grant))

    def load(self, task_id):
        valid_task_id(task_id)
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise Denied("TASK_NOT_FOUND")
        return TaskState(**parse_json(row[0],max_bytes=MAX_LEDGER_BYTES))

    def authorization(self, task_id):
        valid_task_id(task_id)
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload FROM authorizations WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise Denied("AUTHORIZATION_NOT_FOUND")
        data = parse_json(row[0])
        data["budget"] = Budget(**data["budget"])
        data["allowed_tools"] = tuple(data["allowed_tools"])
        data["resources"] = tuple(data["resources"])
        return Authorization(**data)

    def save(self, state, kind, payload):
        old_revision = state.revision
        value = asdict(state)
        value["revision"] = old_revision + 1
        with closing(self._connect()) as db, db:
            row = db.execute("UPDATE tasks SET revision=?,payload=? WHERE id=? AND revision=?",
                             (old_revision + 1, canonical(value,max_bytes=MAX_LEDGER_BYTES), state.id, old_revision))
            if row.rowcount != 1:
                raise StateConflict("task changed or another run claimed it")
            self._event(db, state.id, kind, payload)
        state.revision += 1

    def events(self, task_id):
        valid_task_id(task_id)
        with closing(self._connect()) as db:
            rows = db.execute("SELECT sequence,kind,payload,at_utc FROM events WHERE task_id=? ORDER BY sequence", (task_id,)).fetchall()
        return [{"sequence": s, "kind": k, "payload": parse_json(p,max_bytes=MAX_LEDGER_BYTES), "at_utc": t} for s, k, p, t in rows]

    def create_session(self, value):
        valid_task_id(value["id"])
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (value["id"], 0, canonical(value,max_bytes=MAX_LEDGER_BYTES)))

    def session(self, session_id):
        valid_task_id(session_id)
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise Denied("SESSION_NOT_FOUND")
        return parse_json(row[0],max_bytes=MAX_LEDGER_BYTES)

    def save_session(self, value, turn=None):
        old = value["revision"]
        updated = {**value, "revision": old + 1}
        with closing(self._connect()) as db, db:
            row = db.execute("UPDATE sessions SET revision=?,payload=? WHERE id=? AND revision=?",
                             (old + 1, canonical(updated,max_bytes=MAX_LEDGER_BYTES), value["id"], old))
            if row.rowcount != 1:
                raise StateConflict("session changed or claimed by another process")
            if turn is not None:
                db.execute("INSERT INTO conversation_turns VALUES(?,?,?)", (value["id"], value["turn_count"], canonical(turn)))
        value["revision"] += 1

    def session_turns(self, session_id, limit=50):
        self.session(session_id)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise Denied("INVALID_HISTORY_LIMIT")
        with closing(self._connect()) as db:
            rows = db.execute("SELECT payload FROM conversation_turns WHERE session_id=? ORDER BY turn DESC LIMIT ?",
                              (session_id, limit)).fetchall()
        return [parse_json(x[0]) for x in reversed(rows)]
