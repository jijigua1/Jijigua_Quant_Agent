"""Independent, exploratory daily-data release prototype. No raw PKL deserialization.

Only a trusted publisher may pass decoded panels into this module. Research readers
receive immutable, hashed Train/Validation files, never the raw full-history PKL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

import numpy as np


VERSION = "qra-release/0.1.1"
FIELDS = ("open", "high", "low", "close", "volume", "amount")
SPLITS = {"train": ("20200101", "20231231"), "validation": ("20240101", "20251231")}
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ReleaseError(ValueError):
    pass


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def capture_source(root: Path, *, max_mtime_span_seconds: float = 120.0) -> dict:
    """Capture a candidate six-file cohort without loading or unpickling values."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ReleaseError("INVALID_SOURCE_ROOT")
    paths = {f: root / (f + ".pkl") for f in FIELDS}
    initial = {f: os.stat(p, follow_symlinks=False) for f, p in paths.items()}
    if any(stat.S_ISLNK(st.st_mode) for st in initial.values()):
        raise ReleaseError("SOURCE_SYMLINK")
    files = {}
    for field in FIELDS:
        path = paths[field]
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ReleaseError("UNSAFE_SOURCE_FILE")
            h = hashlib.sha256()
            while chunk := os.read(fd, 1 << 20):
                h.update(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ReleaseError("SOURCE_CHANGED_DURING_READ")
        first = initial[field]
        if (first.st_size, first.st_mtime_ns, first.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ReleaseError("SOURCE_CHANGED_DURING_READ")
        files[field] = {"bytes": before.st_size, "sha256": h.hexdigest(), "mtime_ns": before.st_mtime_ns}
    final = {f: os.stat(p, follow_symlinks=False) for f, p in paths.items()}
    if any((initial[f].st_size, initial[f].st_mtime_ns, initial[f].st_ino) !=
           (final[f].st_size, final[f].st_mtime_ns, final[f].st_ino) for f in FIELDS):
        raise ReleaseError("SOURCE_COHORT_CHANGED")
    span = (max(v["mtime_ns"] for v in files.values()) - min(v["mtime_ns"] for v in files.values())) / 1e9
    if span > max_mtime_span_seconds:
        raise ReleaseError("SOURCE_COHORT_PARTIAL_UPDATE")
    return {"version": VERSION, "files": files, "cohort_mtime_span_seconds": span,
            "status": "SOURCE_FINGERPRINTED_NOT_QUALITY_CERTIFIED"}


def inspect_source(root: Path, pinned: dict) -> dict:
    """Read only the six named files. Reject a moving or unpinned source cohort."""
    candidate = capture_source(root)
    for field in FIELDS:
        spec = pinned["datasets"]["daily_update_core"]["fields"][field]
        if (spec["file"] != field + ".pkl" or
                spec["bytes"] != candidate["files"][field]["bytes"] or
                spec["sha256"] != candidate["files"][field]["sha256"]):
            raise ReleaseError("SOURCE_NOT_PINNED:" + field)
    candidate["status"] = "SOURCE_PINNED_ONLY_NOT_QUALITY_CERTIFIED"
    return candidate


@dataclass(frozen=True)
class Panel:
    dates: tuple[str, ...]
    codes: tuple[str, ...]
    fields: dict[str, np.ndarray]


def panel_from_reader(reader, split: str) -> Panel:
    """Decode one fixed research partition with the Phase 3-A static reader."""
    if split not in SPLITS:
        raise ReleaseError("INVALID_SPLIT")
    result = reader.read("daily_update_core", FIELDS, *SPLITS[split], purpose="profile")
    if not result.dates:
        raise ReleaseError("EMPTY_SPLIT")
    return Panel(tuple(result.dates), tuple(result.codes), result.fields)


def mask_prelisting(panel: Panel, listing_dates: dict[str, str]) -> tuple[Panel, int]:
    """Return a copy with all pre-listing cells missing, never zero-filled."""
    if set(panel.codes) - set(listing_dates):
        raise ReleaseError("LISTING_DATES_REQUIRED")
    masked = {f: arr.copy() for f, arr in panel.fields.items()}
    dates = np.asarray(panel.dates)
    count = 0
    for j, code in enumerate(panel.codes):
        listed = listing_dates[code]
        if not isinstance(listed, str) or not re.fullmatch(r"[0-9]{8}", listed):
            raise ReleaseError("INVALID_LISTING_DATE")
        before = dates < listed
        count += int(np.isfinite(masked["close"][before, j]).sum())
        for arr in masked.values():
            arr[before, j] = np.nan
    return Panel(panel.dates, panel.codes, masked), count


def exclude_identity_conflicts(panel: Panel, codes: tuple[str, ...]) -> tuple[Panel, int]:
    """Keep the fixed axis but make every value of ambiguous historical identities missing."""
    if len(set(codes)) != len(codes) or not set(codes) <= set(panel.codes):
        raise ReleaseError("INVALID_IDENTITY_EXCLUSIONS")
    values = {f: arr.copy() for f, arr in panel.fields.items()}
    removed_close = 0
    for code in codes:
        j = panel.codes.index(code)
        removed_close += int(np.isfinite(values["close"][:, j]).sum())
        for arr in values.values():
            arr[:, j] = np.nan
    return Panel(panel.dates, panel.codes, values), removed_close


def validate_panel(panel: Panel, split: str, *, listing_dates: dict[str, str] | None = None) -> list[dict]:
    """Reuse Phase 3-A numeric validators; keep unverified PIT/listing caveats visible."""
    from qra_data.validators import (Panel as AuditPanel, check_axes, check_coverage,
                                     check_listing_bounds, check_ohlc, check_volume_amount)

    if split not in SPLITS or not panel.dates or not panel.codes or set(panel.fields) != set(FIELDS):
        raise ReleaseError("INVALID_PANEL_CONTRACT")
    lo, hi = SPLITS[split]
    if panel.dates[0] < lo or panel.dates[-1] > hi:
        raise ReleaseError("CROSS_SPLIT")
    for name in FIELDS:
        values = panel.fields[name]
        if values.shape != (len(panel.dates), len(panel.codes)) or values.dtype.kind != "f":
            raise ReleaseError("INVALID_FIELD_SHAPE_OR_DTYPE:" + name)
    audited = AuditPanel(list(panel.dates), list(panel.codes), panel.fields)
    findings = (check_axes(audited) + check_ohlc(audited) +
                check_volume_amount(audited, price_per_unit=10.0) + check_coverage(audited))
    if listing_dates is None or any(c not in listing_dates for c in panel.codes):
        raise ReleaseError("LISTING_DATES_REQUIRED")
    findings += check_listing_bounds(audited, listing_dates, {}, "close")
    out = [vars(f) for f in findings]
    if any(f["severity"] == "error" for f in out):
        raise ReleaseError("QUALITY_GATE_FAILED:" + ",".join(f["check"] for f in out if f["severity"] == "error"))
    return out


def _root(root: Path) -> Path:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ReleaseError("RELEASE_ROOT_NOT_APPROVED")
    return root.resolve(strict=True)


def _release_path(root: Path, split: str, release_id: str) -> Path:
    if split not in SPLITS or not ID.fullmatch(release_id):
        raise ReleaseError("INVALID_RELEASE_ID_OR_SPLIT")
    directory = _root(root) / split
    if directory.is_symlink():
        raise ReleaseError("RELEASE_SPLIT_SYMLINK")
    return directory / release_id


def publish(root: Path, split: str, release_id: str, panel: Panel, *, source: dict,
            parent_id: str | None = None, listing_dates: dict[str, str] | None = None) -> Path:
    """Publish one immutable baseline or changed-date batch; never overwrite a release."""
    target = _release_path(root, split, release_id)
    if len(panel.dates) * len(panel.codes) * len(FIELDS) * 8 > 1_000_000_000:
        raise ReleaseError("PUBLICATION_BUDGET")
    findings = validate_panel(panel, split, listing_dates=listing_dates)
    if (not source.get("files") or set(source["files"]) != set(FIELDS) or
            any(not re.fullmatch(r"[0-9a-f]{64}", source["files"][f].get("sha256", "")) for f in FIELDS)):
        raise ReleaseError("UNPINNED_SOURCE")
    parent_digest = None
    if parent_id:
        old = read(root, split, parent_id, fields=())
        parent_digest = _digest(_release_path(root, split, parent_id) / "manifest.json")
        if old.codes != panel.codes:
            raise ReleaseError("CODE_AXIS_CHANGED")
        if any(d not in old.dates and d <= old.dates[-1] for d in panel.dates):
            raise ReleaseError("NON_APPEND_NEW_DATE")
    elif panel.dates[0] != min(panel.dates):
        raise ReleaseError("UNSORTED_DATES")
    target.parent.mkdir(mode=0o700, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise ReleaseError("RELEASE_ALREADY_EXISTS")
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=target.parent) as temp:
        stage = Path(temp)
        hashes = {}
        for field in FIELDS:
            path = stage / (field + ".npy")
            with path.open("wb") as out:
                np.save(out, panel.fields[field], allow_pickle=False)
            os.chmod(path, 0o640)
            hashes[path.name] = _digest(path)
        metadata = {"version": VERSION, "split": split, "release_id": release_id,
                    "parent_id": parent_id, "parent_manifest_sha256": parent_digest,
                    "dates": panel.dates, "codes": panel.codes,
                    "source": source, "quality_findings": findings,
                    "listing_dates_sha256": hashlib.sha256(_json_bytes(listing_dates)).hexdigest(),
                    "status": "PROFILED_EXPLORATORY_ONLY", "sha256": hashes,
                    "published_at": datetime.now().astimezone().isoformat()}
        manifest_path = stage / "manifest.json"
        manifest_path.write_bytes(_json_bytes(metadata))
        os.chmod(manifest_path, 0o640)
        os.chmod(stage, 0o750)
        # Atomic directory rename; if it fails, TemporaryDirectory removes the stage.
        os.replace(stage, target)
    return target


def read(root: Path, split: str, release_id: str, *, start: str | None = None,
         end: str | None = None, fields: tuple[str, ...] = FIELDS,
         codes: tuple[str, ...] | None = None, max_cells: int = 2_000_000,
         _seen: frozenset[str] = frozenset()) -> Panel:
    """Research side reads only hash-checked published arrays, never raw paths/holdout."""
    path = _release_path(root, split, release_id)
    if release_id in _seen or len(_seen) >= 32:
        raise ReleaseError("RELEASE_CHAIN_INVALID")
    if path.is_symlink() or not path.is_dir() or not set(fields) <= set(FIELDS):
        raise ReleaseError("UNAUTHORIZED_RELEASE_OR_FIELD")
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink():
        raise ReleaseError("UNSAFE_MANIFEST")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["version"] != VERSION or manifest["split"] != split or manifest["release_id"] != release_id:
        raise ReleaseError("MANIFEST_MISMATCH")
    dates = tuple(manifest["dates"])
    all_codes = tuple(manifest["codes"])
    if len(set(dates)) != len(dates) or dates != tuple(sorted(dates)) or len(set(all_codes)) != len(all_codes):
        raise ReleaseError("AXIS_CORRUPT")
    rows = [i for i, d in enumerate(dates) if (start is None or d >= start) and (end is None or d <= end)]
    wanted_codes = all_codes if codes is None else codes
    if not set(wanted_codes) <= set(all_codes) or len(set(wanted_codes)) != len(wanted_codes):
        raise ReleaseError("UNKNOWN_OR_DUPLICATE_CODE")
    cols = [all_codes.index(c) for c in wanted_codes]
    if len(rows) * len(cols) * len(fields) > max_cells:
        raise ReleaseError("OUTPUT_BUDGET")
    values = {}
    for field in fields:
        filename = field + ".npy"
        candidate = path / filename
        if candidate.is_symlink() or _digest(candidate) != manifest["sha256"][filename]:
            raise ReleaseError("RELEASE_FILE_CHANGED")
        arr = np.load(candidate, mmap_mode="r", allow_pickle=False)
        if arr.shape != (len(dates), len(all_codes)) or arr.dtype.kind != "f":
            raise ReleaseError("RELEASE_ARRAY_CORRUPT")
        values[field] = np.array(arr[np.ix_(rows, cols)], copy=True)
    parent_id = manifest.get("parent_id")
    if parent_id:
        parent = _release_path(root, split, parent_id)
        if _digest(parent / "manifest.json") != manifest.get("parent_manifest_sha256"):
            raise ReleaseError("PARENT_RELEASE_CHANGED")
        previous = read(root, split, parent_id, start=start, end=end, fields=fields,
                        codes=wanted_codes, max_cells=max_cells, _seen=_seen | {release_id})
        combined = {d: {f: previous.fields[f][i] for f in fields} for i, d in enumerate(previous.dates)}
        for i, d in enumerate(tuple(dates[j] for j in rows)):
            combined[d] = {f: values[f][i] for f in fields}
        ordered = tuple(sorted(combined))
        if len(ordered) * len(cols) * len(fields) > max_cells:
            raise ReleaseError("OUTPUT_BUDGET")
        values = {f: np.stack([combined[d][f] for d in ordered]) if ordered else np.empty((0, len(cols)))
                  for f in fields}
        return Panel(ordered, wanted_codes, values)
    return Panel(tuple(dates[i] for i in rows), wanted_codes, values)


def daily_inference(panel: Panel, *, asof: str, frozen_model_sha256: str,
                    holdout_end: str = "20261009", lookback: int = 1) -> Panel:
    """Inputs only. No future date, label, test metric or automatic training access."""
    if (not isinstance(frozen_model_sha256, str) or
            not re.fullmatch(r"[0-9a-f]{64}", frozen_model_sha256) or
            not isinstance(asof, str) or not re.fullmatch(r"[0-9]{8}", asof) or asof <= holdout_end):
        raise ReleaseError("INFERENCE_REQUIRES_FROZEN_MODEL_AND_POST_HOLDOUT_DATE")
    if type(lookback) is not int or lookback < 1 or lookback > 120 or asof not in panel.dates:
        raise ReleaseError("INVALID_INFERENCE_WINDOW")
    i = panel.dates.index(asof)
    if i + 1 < lookback or set(panel.fields) != set(FIELDS):
        raise ReleaseError("INCOMPLETE_INFERENCE_INPUT")
    return Panel(panel.dates[i + 1 - lookback:i + 1], panel.codes,
                 {f: panel.fields[f][i + 1 - lookback:i + 1].copy() for f in FIELDS})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read-only six-file source fingerprint check")
    parser.add_argument("source_root")
    parser.add_argument("pinned_manifest")
    args = parser.parse_args()
    pinned = json.loads(Path(args.pinned_manifest).read_text(encoding="utf-8"))
    print(json.dumps(inspect_source(Path(args.source_root), pinned), ensure_ascii=False, sort_keys=True))
