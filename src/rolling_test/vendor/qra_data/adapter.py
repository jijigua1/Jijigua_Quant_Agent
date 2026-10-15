"""Controlled, read-only daily data adapter over existing wide-table pickles (no copy, no unpickling).

The manifest pins every file by path, size and SHA-256 and scopes each dataset's certification. A read is refused
when the purpose needs a higher certification, when a field is not allowed for that purpose, when the request
exceeds the budget, or when a file is not exactly the reviewed one. Values after a field's validity cutoff
(for example frozen status tables) are masked and reported.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import os
import stat

import numpy as np

from . import static_pickle as sp
from .contracts import CONTRACT_VERSION, DAILY_UPDATE_FIELDS, Level
from .validators import check_budget, check_field_semantics

ADAPTER_VERSION = "qra-data-adapter/1.0.0"
PURPOSE_LEVEL = {"profile": Level.PROFILED, "research": Level.RESEARCH_READY, "backtest": Level.BACKTEST_APPROVED}


class Refused(PermissionError):
    def __init__(self, code, detail=""):
        super().__init__(code + (": " + detail if detail else ""))
        self.code = code


@dataclass
class Budget:
    max_cells: int = 40_000_000
    max_file_bytes: int = 256 * 1024 ** 2
    max_result_bytes: int = 1024 ** 3


@dataclass
class ReadResult:
    dates: list
    codes: list
    fields: dict
    provenance: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def default_opener(path, allowed_roots):
    """Open read-only without following symlinks, only under allowed roots, regular single-link files."""
    norm = os.path.normcase
    real = os.path.realpath(path)
    if norm(os.path.abspath(path)) != norm(real):          # a symlink or '..' somewhere in the path
        raise Refused("PATH_NOT_CANONICAL", path)
    roots = [norm(os.path.realpath(r)) for r in allowed_roots]
    if not any(norm(real) == r or norm(real).startswith(r.rstrip(os.sep) + os.sep) for r in roots):
        raise Refused("PATH_OUTSIDE_ALLOWED_ROOTS", path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        return os.open(real, flags)
    except OSError as exc:
        raise Refused("OPEN_FAILED", "%s: %s" % (path, exc.strerror)) from None


class ControlledReader:
    def __init__(self, manifest, *, allowed_roots, budget=None, opener=None, contract_fields=DAILY_UPDATE_FIELDS):
        self.manifest, self.allowed_roots = manifest, [os.path.normpath(r) for r in allowed_roots]
        self.budget = budget or Budget()
        self.opener = opener or (lambda p: default_opener(p, self.allowed_roots))
        self.contract_fields = contract_fields
        self._axes = {}

    # ------------------------------------------------------------------ file access
    def _load(self, dataset, name):
        spec = self.manifest["datasets"][dataset]["fields"].get(name)
        if spec is None:
            raise Refused("FIELD_NOT_IN_MANIFEST", name)
        path = os.path.join(self.manifest["datasets"][dataset]["root"], spec["file"])
        fd = self.opener(path)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise Refused("NOT_A_SINGLE_LINK_REGULAR_FILE", path)
            if st.st_size != spec["bytes"]:
                raise Refused("SIZE_CHANGED", "%s %d != %d" % (path, st.st_size, spec["bytes"]))
            if st.st_size > self.budget.max_file_bytes:
                raise Refused("FILE_ABOVE_BUDGET", path)
            chunks, h = [], hashlib.sha256()
            while True:
                block = os.read(fd, 1 << 24)
                if not block:
                    break
                h.update(block)
                chunks.append(block)
        finally:
            os.close(fd)
        if h.hexdigest() != spec["sha256"]:
            raise Refused("SHA256_MISMATCH", path)
        try:
            dec = sp.decode_frame(b"".join(chunks))   # allow-listed static decode; never pickle.load
            mat = sp.frame_matrix(dec)
        except sp.UnsafePickle as exc:
            raise Refused("UNTRUSTED_PICKLE_STRUCTURE", "%s: %s" % (path, exc)) from None
        dates = [str(x) for x in dec["index"]]
        codes = [str(x) for x in dec["columns"]]
        return dates, codes, mat, {"field": name, "path": path, "sha256": spec["sha256"], "bytes": spec["bytes"],
                                   "decoder": "static_pickle (no execution)"}

    # ------------------------------------------------------------------ public API
    def read(self, dataset, fields, start, end, *, codes=None, purpose="research"):
        ds = self.manifest["datasets"].get(dataset)
        if ds is None:
            raise Refused("UNKNOWN_DATASET", dataset)
        need = PURPOSE_LEVEL.get(purpose)
        if need is None:
            raise Refused("UNKNOWN_PURPOSE", purpose)
        level = Level[ds["certification"]["level"]]
        if level < need:
            raise Refused("CERTIFICATION_TOO_LOW", "%s is %s; %s needs %s" % (dataset, level.name, purpose, need.name))
        scope = ds["certification"]
        if start < scope["start"] or end > scope["end"]:
            raise Refused("OUTSIDE_CERTIFIED_SCOPE", "%s..%s not within %s..%s" % (start, end, scope["start"], scope["end"]))
        allowed = set(scope.get("fields", []))
        if allowed and not set(fields) <= allowed:
            raise Refused("FIELD_NOT_CERTIFIED", ",".join(sorted(set(fields) - allowed)))
        problems = check_field_semantics(fields, self.contract_fields, purpose="signal" if purpose == "research" else purpose)
        notes = []
        if problems and purpose != "profile":
            raise Refused("FIELD_SEMANTICS", "; ".join("%s %s" % (p.check, p.sample) for p in problems))
        if problems:  # profiling may inspect rejected fields, but the result carries the verdict
            notes = [{"profile_only": p.check, "fields": p.sample} for p in problems]
        result, axes = None, None
        for name in fields:
            dates, all_codes, mat, prov = self._load(dataset, name)
            if axes is None:
                axes = (dates, all_codes)
                rows = [i for i, d in enumerate(dates) if start <= d <= end]
                if codes is None:
                    cols = list(range(len(all_codes)))
                else:
                    pos = {c: j for j, c in enumerate(all_codes)}
                    missing = [c for c in codes if c not in pos]
                    if missing:
                        raise Refused("UNKNOWN_CODES", ",".join(missing[:5]))
                    cols = [pos[c] for c in codes]
                over = check_budget(len(rows), len(cols), len(fields), max_cells=self.budget.max_cells,
                                    max_bytes=self.budget.max_result_bytes)
                if over:
                    raise Refused("BUDGET", over[0].detail)
                result = ReadResult([dates[i] for i in rows], [all_codes[j] for j in cols], {}, warnings=list(notes))
            elif (dates, all_codes) != axes:
                raise Refused("AXIS_MISMATCH", name)
            sub = np.array(mat[np.ix_(rows, cols)], copy=True)
            cutoff = ds.get("valid_until", {}).get(name)
            if cutoff:
                late = np.array([d > cutoff for d in result.dates])
                if late.any():
                    sub[late] = np.nan if sub.dtype.kind == "f" else False
                    result.warnings.append({"field": name, "masked_after": cutoff, "dates_masked": int(late.sum())})
            result.fields[name] = sub
            prov.update(contract=CONTRACT_VERSION, adapter=ADAPTER_VERSION, certification=level.name, purpose=purpose)
            result.provenance.append(prov)
        return result


def provenance_json(result):
    return {"dates": [result.dates[0], result.dates[-1], len(result.dates)] if result.dates else [],
            "codes": len(result.codes), "fields": sorted(result.fields), "provenance": result.provenance,
            "warnings": result.warnings}
