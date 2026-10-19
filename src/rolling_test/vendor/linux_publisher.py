"""Trusted Linux entry point: root pins six read-only FDs; quantpub alone decodes and writes.

This module is not an Agent Tool. Real publication also requires an approved listing-date
contract and separate user approval; the current server has neither.
"""
from __future__ import annotations

import hashlib
import csv
import json
import os
from pathlib import Path
import signal
import stat
import time


FIELDS = ("open", "high", "low", "close", "volume", "amount")
SOURCE_ROOT = Path("/srv/quant-market/daily_update")
RELEASE_ROOT = Path("/var/lib/jijigua-quant-agent/data_releases")
WALL_SECONDS = 120
LISTING_CANDIDATE = Path("/hy-tmp/autodl-tmp/TRD_Co.csv")
LISTING_CANDIDATE_SHA256 = "f6f5d072d6502561a3ca3495f9132b84753584ddbef6d7ce459b4a0dfa10e209"
IDENTITY_EXCLUSIONS = ("001914.SZ", "302132.SZ")


def _listing_candidate(codes: tuple[str, ...]) -> dict[str, str]:
    if hashlib.sha256(LISTING_CANDIDATE.read_bytes()).hexdigest() != LISTING_CANDIDATE_SHA256:
        raise ValueError("LISTING_CANDIDATE_CHANGED")
    with LISTING_CANDIDATE.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) > 10000 or len({r["Stkcd"] for r in rows}) != len(rows):
        raise ValueError("LISTING_CANDIDATE_INVALID")
    by_code = {r["Stkcd"]: r["Listdt"].replace("-", "") for r in rows}
    if any(c[:6] not in by_code for c in codes):
        raise ValueError("LISTING_CANDIDATE_INCOMPLETE")
    return {c: by_code[c[:6]] for c in codes}


def _inside_synthetic(path: Path) -> bool:
    return path.is_absolute() and path.parts[:2] == ("/", "tmp") and any(
        x.startswith("qra-b2a-synth-") for x in path.parts[2:3])


def _pinned_fds(root: Path, pinned: dict) -> dict[str, int]:
    if root.is_symlink() or root.resolve(strict=True) != root or set(pinned) != set(FIELDS):
        raise ValueError("UNAPPROVED_SOURCE")
    opened = {}
    try:
        for field in FIELDS:
            spec = pinned[field]
            if set(spec) != {"bytes", "sha256"} or not isinstance(spec["bytes"], int) or spec["bytes"] < 1:
                raise ValueError("INVALID_SOURCE_SPEC")
            if not isinstance(spec["sha256"], str) or len(spec["sha256"]) != 64:
                raise ValueError("INVALID_SOURCE_SPEC")
            path = root / (field + ".pkl")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            opened[field] = fd
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != spec["bytes"]:
                raise ValueError("SOURCE_FILE_CHANGED")
            digest = hashlib.sha256()
            while block := os.read(fd, 1 << 20):
                digest.update(block)
            after = os.fstat(fd)
            by_name = os.stat(path, follow_symlinks=False)
            if (digest.hexdigest() != spec["sha256"] or
                    (before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_ino, after.st_size, after.st_mtime_ns) or
                    (after.st_ino, after.st_size, after.st_mtime_ns) !=
                    (by_name.st_ino, by_name.st_size, by_name.st_mtime_ns)):
                raise ValueError("SOURCE_COHORT_CHANGED")
            os.lseek(fd, 0, os.SEEK_SET)
        if len({os.fstat(fd).st_mtime_ns for fd in opened.values()}) > 1:
            span = max(os.fstat(fd).st_mtime_ns for fd in opened.values()) - min(
                os.fstat(fd).st_mtime_ns for fd in opened.values())
            if span > 120 * 1_000_000_000:
                raise ValueError("SOURCE_COHORT_PARTIAL_UPDATE")
        return opened
    except BaseException:
        for fd in opened.values():
            os.close(fd)
        raise


def _child(root: Path, output_root: Path, pinned: dict, listing_dates: dict[str, str],
           split: str, release_id: str, fds: dict[str, int], result_fd: int,
           *, synthetic: bool, dry_run: bool) -> None:
    import grp
    import pwd
    import resource

    account = pwd.getpwnam("quantpub")
    group = grp.getgrnam("quantdata")
    os.setgroups([group.gr_gid])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    if os.geteuid() == 0 or os.getgroups() != [group.gr_gid]:
        raise RuntimeError("PRIVILEGE_DROP_FAILED")
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (75, 75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ.clear()
    os.environ.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    os.umask(0o077)
    keep = {0, 1, 2, result_fd, *fds.values()}
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd not in keep:
            try:
                os.close(fd)
            except OSError:
                pass

    from qra_data.adapter import Budget, ControlledReader, Refused
    from qra_data import static_pickle
    import release
    from release import (ReleaseError, exclude_identity_conflicts, mask_prelisting,
                         panel_from_reader, publish, validate_panel)

    def opener(path):
        field = Path(path).name.removesuffix(".pkl")
        if path != str(root / (field + ".pkl")) or field not in fds:
            raise Refused("PATH_NOT_GRANTED")
        duplicate = os.dup(fds[field])
        os.lseek(duplicate, 0, os.SEEK_SET)
        return duplicate

    manifest = {"datasets": {"daily_update_core": {"root": str(root),
        "fields": {f: {"file": f + ".pkl", **pinned[f]} for f in FIELDS},
        "certification": {"level": "PROFILED", "start": "20190101", "end": "20261231",
                          "fields": list(FIELDS)}}}}
    reader = ControlledReader(manifest, allowed_roots=[str(root)], opener=opener,
                              budget=Budget(max_cells=40_000_000, max_file_bytes=256 * 1024 ** 2,
                                            max_result_bytes=1024 ** 3))
    try:
        panel = panel_from_reader(reader, split)
        dates = listing_dates if synthetic else _listing_candidate(panel.codes)
        panel, prelist_cells = mask_prelisting(panel, dates)
        exclusions = () if synthetic else IDENTITY_EXCLUSIONS
        panel, excluded_cells = exclude_identity_conflicts(panel, exclusions)
        source = {"files": pinned,
                  "publisher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "release_sha256": hashlib.sha256(Path(release.__file__).read_bytes()).hexdigest(),
                  "decoder_sha256": hashlib.sha256(Path(static_pickle.__file__).read_bytes()).hexdigest(),
                  "listing_basis": "SYNTHETIC" if synthetic else "UNVERIFIED_CANDIDATE",
                  "listing_candidate_sha256": None if synthetic else LISTING_CANDIDATE_SHA256,
                  "identity_exclusions": list(exclusions),
                  "candidate_prelisting_masked_close_cells": prelist_cells,
                  "excluded_close_cells_after_mask": excluded_cells,
                  "listing_certified": False, "formal_backtest_eligible": False}
        if dry_run:
            validate_panel(panel, split, listing_dates=dates)
            import numpy as np
            payload = {"status": "DRY_RUN_ONLY", "split": split,
                       "date_start": panel.dates[0], "date_end": panel.dates[-1],
                       "dates": len(panel.dates), "axis_codes": len(panel.codes),
                       "codes_with_close": int(np.isfinite(panel.fields["close"]).any(axis=0).sum()),
                       "finite_close_cells": int(np.isfinite(panel.fields["close"]).sum()),
                       "source": {k: v for k, v in source.items() if k != "files"}}
            os.write(result_fd, json.dumps(payload, sort_keys=True).encode())
        else:
            publish(output_root, split, release_id, panel, source=source,
                    listing_dates=dates)
            os.write(result_fd, b"OK")
    except (ReleaseError, Refused, ValueError) as exc:
        os.write(result_fd, ("DENIED:" + type(exc).__name__).encode())
        raise


def publish_once(root: Path, output_root: Path, pinned: dict, listing_dates: dict[str, str] | None,
                 split: str, release_id: str, *, synthetic: bool = False,
                 dry_run: bool = False) -> Path | dict:
    """Only trusted administrators call this with a fixed manifest, never model parameters."""
    if os.name != "posix" or os.geteuid() != 0:
        raise PermissionError("ROOT_OPENER_REQUIRED")
    root, output_root = Path(root), Path(output_root)
    if not ((synthetic and _inside_synthetic(root) and _inside_synthetic(output_root)) or
            (not synthetic and root == SOURCE_ROOT and output_root == RELEASE_ROOT)):
        raise PermissionError("ROOT_PATH_NOT_APPROVED")
    if split not in ("train", "validation") or (synthetic and not isinstance(listing_dates, dict)) or (
            not synthetic and listing_dates is not None):
        raise ValueError("INVALID_PUBLICATION_REQUEST")
    fds = _pinned_fds(root, pinned)
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            _child(root, output_root, pinned, listing_dates, split, release_id, fds, write_fd,
                   synthetic=synthetic, dry_run=dry_run)
            os._exit(0)
        except BaseException:
            os._exit(1)
    os.close(write_fd)
    for fd in fds.values():
        os.close(fd)
    deadline = time.monotonic() + WALL_SECONDS
    while True:
        finished, status = os.waitpid(pid, os.WNOHANG)
        if finished:
            break
        if time.monotonic() >= deadline:
            os.kill(pid, signal.SIGKILL)  # Only the child started above.
            os.waitpid(pid, 0)
            os.close(read_fd)
            raise TimeoutError("PUBLISHER_WALL_LIMIT")
        time.sleep(0.1)
    result = os.read(read_fd, 4096)
    os.close(read_fd)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0 or (not dry_run and result != b"OK"):
        raise RuntimeError("PUBLISHER_FAILED:" + result.decode(errors="ignore"))
    if dry_run:
        return json.loads(result)
    return output_root / split / release_id
