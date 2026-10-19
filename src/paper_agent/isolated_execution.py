"""Fail-closed numerical code execution, separate from the legacy human registry.

No automatic approval records are created. This module is not yet connected to
production routing. Linux/non-root and libseccomp are mandatory, including tests.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd


class IsolationError(RuntimeError):
    pass


def execute(source, panels, *, source_sha256, entrypoint="compute", timeout=45,
            memory_bytes=2 * 1024**3, output_bytes=128 * 1024**2):
    if sys.platform != "linux" or os.geteuid() == 0:
        raise IsolationError("NONROOT_LINUX_REQUIRED")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != source_sha256:
        raise IsolationError("SOURCE_SHA_MISMATCH")
    if entrypoint not in ("compute", "reference") or not panels:
        raise IsolationError("INVALID_EXECUTION_REQUEST")
    if not 1 <= timeout <= 120 or not 64*1024**2 <= memory_bytes <= 8*1024**3 or not 1024 <= output_bytes <= 256*1024**2:
        raise IsolationError("INVALID_LIMITS")
    first = next(iter(panels.values()))
    if not first.index.is_unique or not first.index.is_monotonic_increasing or not first.columns.is_unique:
        raise IsolationError("INVALID_PANEL_AXIS")
    arrays = {}
    for field, frame in panels.items():
        if field.startswith("__") or not field.isidentifier():
            raise IsolationError("INVALID_FIELD")
        if not frame.index.equals(first.index) or not frame.columns.equals(first.columns):
            raise IsolationError("INPUT_GRID_MISMATCH")
        arrays[field] = frame.to_numpy(dtype=np.float64)
    arrays.update(__source=np.frombuffer(source.encode("utf-8"), dtype=np.uint8),
                  __entrypoint=np.frombuffer(entrypoint.encode("ascii"), dtype=np.uint8),
                  __index=first.index.asi8, __columns=np.asarray(first.columns, dtype=str))
    payload = io.BytesIO()
    np.savez(payload, **arrays)
    worker = Path(__file__).with_name("isolated_worker.py").resolve()
    # Never inherit API keys, Python injection variables, SSH agent or campaign state.
    env = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
           "NUMEXPR_NUM_THREADS": "1", "LC_ALL": "C.UTF-8"}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            proc = subprocess.run([sys.executable, "-I", "-B", str(worker), str(timeout),
                                   str(memory_bytes), str(output_bytes)],
                                  input=payload.getvalue(), stdout=stdout, stderr=stderr,
                                  env=env, cwd="/", close_fds=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise IsolationError("EXECUTION_TIMEOUT") from exc
        if proc.returncode:
            # Generated error text is untrusted diagnostic data, not instructions.
            stderr.seek(0)
            detail = stderr.read(4096).decode("utf-8", errors="replace")
            raise IsolationError(f"WORKER_FAILED:{proc.returncode}:{detail}")
        if stdout.tell() > output_bytes:
            raise IsolationError("OUTPUT_LIMIT")
        stdout.seek(0)
        try:
            version = np.lib.format.read_magic(stdout)
            if version == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(stdout, max_header_size=10000)
            elif version == (2, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(stdout, max_header_size=10000)
            else:
                raise ValueError('unsupported array format')
            # Validate before allocation: an untrusted NPY header must not make
            # the parent allocate an enormous array or decode object/pickle data.
            if shape != first.shape or dtype != np.dtype('float64'):
                raise ValueError('invalid array header')
            stdout.seek(0)
            result = np.load(stdout, allow_pickle=False)
            if stdout.read(1) or result.dtype != np.float64 or result.shape != first.shape or np.isinf(result).any():
                raise ValueError("invalid numeric output")
        except Exception as exc:
            raise IsolationError("INVALID_WORKER_OUTPUT") from exc
    return pd.DataFrame(result, index=first.index, columns=first.columns)
