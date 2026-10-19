"""Linux-only, fresh-process numerical worker. Never import into an Agent process.

The parent supplies arrays and source through stdin. Scientific libraries are
loaded before an allowlist seccomp filter is installed. Generated code cannot
open files, create sockets/processes, signal other processes, or change the
filter. Failure to install the filter prevents ALL candidate execution.
"""
from __future__ import annotations

import ctypes
import io
import os
import resource
import sys

# Import before denying filesystem syscalls. Threads are disabled by the parent.
import numpy as np
import pandas as pd


def lock_down(cpu_seconds, memory_bytes, output_bytes):
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("NONROOT_LINUX_REQUIRED")
    for kind, bound in ((resource.RLIMIT_CPU, cpu_seconds),
                        (resource.RLIMIT_AS, memory_bytes),
                        (resource.RLIMIT_FSIZE, output_bytes),
                        (resource.RLIMIT_CORE, 0),
                        (resource.RLIMIT_NPROC, 0)):
        inherited_soft, inherited_hard = resource.getrlimit(kind)
        # The evaluator already runs with limits. A child may only tighten them.
        finite = [x for x in (bound, inherited_soft, inherited_hard) if x != resource.RLIM_INFINITY]
        effective = min(finite)
        resource.setrlimit(kind, (effective, effective))
    # libseccomp checks architecture as well as syscall numbers.
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x80000000)  # KILL_PROCESS; no fallback to permissive mode
    if not ctx:
        raise RuntimeError("SECCOMP_INIT_FAILED")
    try:
        # No open/stat/readlink, networking, clone/fork, exec, ptrace, signals,
        # namespace changes, ioctl, prctl, or further seccomp operations.
        for name in ("read", "write", "close", "lseek", "fstat", "futex",
                     "brk", "mmap", "munmap", "mremap", "mprotect", "madvise",
                     "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack",
                     "clock_gettime", "gettimeofday", "time", "getrandom",
                     "getpid", "gettid", "sched_yield", "restart_syscall",
                     "exit", "exit_group"):
            number = lib.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0 or lib.seccomp_rule_add(ctx, 0x7FFF0000, number, 0):
                raise RuntimeError("SECCOMP_RULE_FAILED:" + name)
        if lib.seccomp_load(ctx):
            raise RuntimeError("SECCOMP_LOAD_FAILED")
    finally:
        lib.seccomp_release(ctx)


def main():
    cpu, memory, output = map(int, sys.argv[1:4])
    raw = sys.stdin.buffer.read()
    with np.load(io.BytesIO(raw), allow_pickle=False) as pack:
        source = pack["__source"].tobytes().decode("utf-8")
        entrypoint = pack["__entrypoint"].tobytes().decode("ascii")
        index = pd.DatetimeIndex(pack["__index"].astype("datetime64[ns]"))
        columns = pack["__columns"].tolist()
        panels = {k: pd.DataFrame(pack[k], index=index, columns=columns)
                  for k in pack.files if not k.startswith("__")}
    del raw
    if entrypoint not in ("compute", "reference"):
        raise ValueError("BAD_ENTRYPOINT")
    # Warm lazy Python helpers before lockdown; no candidate code has run yet.
    pd.DataFrame([[1., 2.], [3., 4.]]).rolling(2).mean()
    # pandas renders a Series while checking groupby keys. Its repr asks shutil
    # for terminal dimensions even in this noninteractive worker. Fixed positive
    # dimensions avoid ioctl without granting generated code terminal access.
    os.environ['COLUMNS'] = '80'
    os.environ['LINES'] = '24'
    np.linalg.lstsq(np.array([[1.], [2.]]), np.array([1., 2.]), rcond=None)
    lock_down(cpu, memory, output)
    namespace = {"__name__": "isolated_factor"}
    exec(compile(source, "<generated-factor>", "exec"), namespace)
    result = namespace[entrypoint](panels)
    if not isinstance(result, pd.DataFrame) or not result.index.equals(index) or list(result.columns) != columns:
        raise ValueError("OUTPUT_GRID_MISMATCH")
    values = result.to_numpy(dtype=np.float64)
    if np.isinf(values).any():
        raise ValueError("NONFINITE_OUTPUT")
    buf = io.BytesIO()
    np.save(buf, values, allow_pickle=False)
    sys.stdout.buffer.write(buf.getvalue())
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
