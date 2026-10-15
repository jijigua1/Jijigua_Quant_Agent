"""Aggregate and per-file SHA-256 of a source tree (posix relative paths, .py only, no __pycache__).

usage: python src_fingerprint.py <src dir> [--files]
The aggregate is sha256 over "relpath\\0bytes" in sorted order: the same value as tools/paper_ab.py run_meta.
"""
import hashlib
import sys
from pathlib import Path


def fingerprint(root):
    root = Path(root)
    h = hashlib.sha256()
    files = [f for f in sorted(root.rglob("*.py")) if "__pycache__" not in f.parts]
    rows = []
    for f in files:
        data = f.read_bytes()
        h.update(f.relative_to(root).as_posix().encode() + b"\0" + data)
        rows.append((f.relative_to(root).as_posix(), hashlib.sha256(data).hexdigest()))
    return h.hexdigest(), rows


if __name__ == "__main__":
    agg, rows = fingerprint(sys.argv[1])
    print(len(rows), agg)
    if "--files" in sys.argv:
        for r, s in rows:
            print(s, r)
