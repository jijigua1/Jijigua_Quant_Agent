"""Read-only view of recent Agent ledger events (operator diagnostics; run on the server)."""
import json
import sqlite3
import sys

db = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60
kinds = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None
rows = db.execute('select sequence, task_id, kind, payload, at_utc from events order by sequence desc limit ?', (limit,)).fetchall()
for seq, task, kind, payload, at in reversed(rows):
    if kinds and kind not in kinds:
        continue
    text = payload if len(payload) < 600 else payload[:600] + '…'
    print(seq, at[11:19], task[:6], kind, text)
