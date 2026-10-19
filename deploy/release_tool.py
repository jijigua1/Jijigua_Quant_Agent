#!/usr/bin/env python3
"""Install / roll back a reviewed release on the GPUShare host (Candidate6 recovery, 2026-10-18). Run as root.

    release_tool.py apply    (--production | --rehearsal DIR) --approval REF --manifest-sha SHA256
    release_tool.py rollback (--production | --rehearsal DIR) --backup DIR

Written for Linux 5.4 (no openat2): every path is walked one component at a time with
os.open(name, O_NOFOLLOW | O_DIRECTORY, dir_fd=parent), so a symbolic link anywhere below the target root stops the
run; every directory and file must be on the target root's device; /proc/self/mountinfo must show no mount point inside
the target (a same-device bind mount is not visible to st_dev). Files are written as a new temporary file in their
directory (O_CREAT | O_EXCL | O_NOFOLLOW), fsynced, given their recorded owner and mode, then renamed over the old name
inside that same directory fd.

The target is chosen explicitly and never from the environment. A rehearsal directory must lie strictly inside the
rehearsal area and must not be production, the staging copy, or their parent or child, by path or by device:inode. An
exclusive flock serialises every run; each run gets its own backup directory (mkdtemp). A marker file in the target
records an unfinished run, which is refused until it is rolled back. A rollback accepts only a backup made for the same
mode, the same resolved target and the same device:inode, and checks every path before its first write. Every check
completes before the first write; anything unexpected stops the run (exit 3) without changing the target.
"""
import argparse
import datetime
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PROD = "/opt/jijigua-quant-agent/v1beta"
RC = str(Path(__file__).resolve().parents[1])             # this reviewed candidate, never a separately installed v1rc
REHEARSAL_AREA = "/var/lib/jijigua-quant-agent/ab"
VENV_PYTHON = "/opt/jijigua-quant-agent/v1beta/.venv/bin/python"
PROD_MANIFEST_SHA = "249cee8f8c9daef65f91fb8bd1b01791bcd43d002edc415e75310ad536d4335a"
PRODUCTION_BACKUP_DIR = "/var/lib/jijigua-quant-agent/ab/i5_mac_takeover_20261019/deployment_backups"
NEW_MANIFEST = "docs/release_v1_sha256_recovery.txt"
OLD_MANIFEST = "docs/release_v1_sha256.txt"
SELFTEST_FIXTURE_SHA = "ce93f327a1054a21dba0467d2c956c0da2fa20ca96135046936a23b673b99300"   # tests/v1beta_fixtures.py
MARKER = ".release_recovery_in_progress"
LOCK_FILE = "/root/.release_tool.lock"
FREE_BYTES = 1 << 30
SMOKE = ("import sys; sys.path[:0]=[{src!r},{vendor!r}]\n"
         "import research_agent.conversation, research_agent.metric_system, research_agent.test_access, research_agent.paper_tools, "
         "research_agent.api_budget, paper_agent.planner, paper_agent.canonical, paper_agent.definitions, paper_agent.printed, "
         "paper_agent.user_edit, rolling_test.evaluator\nprint('imports ok as', __import__('os').geteuid())")
RX_REL = re.compile(r"(?:(?:src|deploy)/[A-Za-z0-9_.\-/]+|client/(?:quant_paper\.py|quant-paper(?:\.ps1)?))")
LEFTOVER = re.compile(r"\.new\.")


class Stop(Exception):
    """A check failed: nothing (more) is written."""


def log(msg):
    print(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


# ------------------------------------------------------------------------------------------------ safe file access
class Root:
    """A directory held open by fd; every access goes component by component below it without following links."""

    def __init__(self, path):
        real = os.path.realpath(path)
        if real != os.path.normpath(path):
            raise Stop(f"target {path!r} resolves to {real!r} (a link in its path)")
        self.path = real
        self.fd = os.open(real, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st = os.fstat(self.fd)
        self.dev, self.ino = st.st_dev, st.st_ino

    def _dir(self, parts, create=False):
        fd = os.dup(self.fd)
        try:
            for name in parts:
                if name in ("", ".", "..") or "/" in name:
                    raise Stop(f"bad path component {name!r}")
                try:
                    nfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(name, 0o755, dir_fd=fd)
                    os.chown(name, 0, 0, dir_fd=fd, follow_symlinks=False)
                    nfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except OSError as e:
                    if e.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise Stop(f"{name!r} below {self.path} is not a plain directory (link or file)") from None
                    raise
                os.close(fd)
                fd = nfd
                if os.fstat(fd).st_dev != self.dev:
                    raise Stop(f"{name!r} below {self.path} is on another device")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def split(self, rel):
        if not RX_REL.fullmatch(rel) and rel not in (OLD_MANIFEST, NEW_MANIFEST, MARKER, "docs/release_v1_sha256.before_recovery.txt",
                                                     "tests/v1beta_fixtures.py", "deploy/rolling/broker.json", "deploy/host.json",
                                                     "config/research.json", "quant-agent", "quant-paper", ".paper_entry_in_progress",
                                                     "TARGET.json", "BACKUP_SHA256.json", "old"):
            raise Stop(f"path {rel!r} is outside the release scope")
        if ".." in rel.split("/"):
            raise Stop(f"path {rel!r} climbs")
        parts = rel.split("/")
        return parts[:-1], parts[-1]

    def lstat(self, rel):
        """os.stat_result of the final component (not followed), or None when absent."""
        dirs, name = self.split(rel)
        try:
            fd = self._dir(dirs)
        except FileNotFoundError:
            return None
        try:
            return os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        finally:
            os.close(fd)

    def check_file(self, rel):
        """None when absent; else (stat) of a single-link regular file on the root's device -- anything else stops."""
        st = self.lstat(rel)
        if st is None:
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_dev != self.dev:
            raise Stop(f"{rel} is not a single-link regular file on the target device")
        return st

    def read(self, rel):
        dirs, name = self.split(rel)
        fd = self._dir(dirs)
        try:
            f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            st = os.fstat(f)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_dev != self.dev:
                raise Stop(f"{rel} is not a single-link regular file on the target device")
            chunks = []
            while True:
                b = os.read(f, 1 << 20)
                if not b:
                    return b"".join(chunks)
                chunks.append(b)
        finally:
            os.close(f)

    def write(self, rel, data, mode, uid=0, gid=0):
        dirs, name = self.split(rel)
        fd = self._dir(dirs, create=True)
        tmp = f".{name}.new.{os.getpid()}"
        try:
            f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                os.write(f, data)
                os.fchown(f, uid, gid)
                os.fchmod(f, mode)
                os.fsync(f)
            finally:
                os.close(f)
            st = os.stat(name, dir_fd=fd, follow_symlinks=False) if _exists(name, fd) else None
            if st is not None and not stat.S_ISREG(st.st_mode):
                os.unlink(tmp, dir_fd=fd)
                raise Stop(f"{rel} is not a regular file")
            os.rename(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)

    def unlink(self, rel):
        dirs, name = self.split(rel)
        try:
            fd = self._dir(dirs)
        except FileNotFoundError:
            return
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False) if _exists(name, fd) else None
            if st is None:
                return
            if not stat.S_ISREG(st.st_mode):
                raise Stop(f"{rel} is not a regular file; not removed")
            os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)

    def leftovers(self):
        """Temporary files of an interrupted write anywhere under src/ and deploy/ (this tool: ".<name>.new.<pid>"; the
        earlier shell scripts: "<name>.new.<stamp>"); the first one found is enough to stop."""
        for top in ("src", "deploy", "client"):
            if top == 'client' and not os.path.lexists(os.path.join(self.path, top)):
                continue
            fd = self._dir([top])                     # a link in place of src/ or deploy/ stops here
            os.close(fd)
            for base, dirs, files in os.walk(os.path.join(self.path, top), followlinks=False):
                hit = next((f for f in files if LEFTOVER.search(f)), None)
                if hit:
                    return [os.path.join(base, hit)]
        return []


def _exists(name, dir_fd):
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(data):
    out = {}
    for line in data.decode("utf-8").splitlines():
        if line.strip():
            h, p = line.split(None, 1)
            out[p.strip().lstrip("*")] = h
    return out


def mount_points_inside(path):
    with open("/proc/self/mountinfo", encoding="utf-8") as f:
        points = [line.split()[4].replace("\\040", " ") for line in f if line.strip()]
    return sorted({p for p in points if p != path and (p + "/").startswith(path + "/")} |
                  ({path} if path in points else set()))


def inside(child, parent):
    return (child + "/").startswith(parent.rstrip("/") + "/")


# ------------------------------------------------------------------------------------------------ target selection
def select(args):
    if os.geteuid() != 0:
        raise SystemExit("must run as root")
    prod = os.path.realpath(PROD)
    rc = os.path.realpath(RC)
    if args.production:
        target, store = prod, PRODUCTION_BACKUP_DIR
        backup_root = Root(store)
        backup_stat = os.fstat(backup_root.fd)
        os.close(backup_root.fd)
        if backup_stat.st_uid != 0 or stat.S_IMODE(backup_stat.st_mode) != 0o700:
            raise Stop("production backup directory must be root-owned mode 0700")
    else:
        given = args.rehearsal
        if os.path.islink(given.rstrip("/") or "/"):
            raise Stop("a rehearsal target must not be a symbolic link")
        target = os.path.realpath(given)
        area = os.path.realpath(REHEARSAL_AREA)
        if not os.path.isdir(target) or target == area or not inside(target, area):
            raise Stop(f"rehearsal target {target} is not a directory strictly inside {area}")
        for guarded in (prod, rc):
            if target == guarded or inside(target, guarded) or inside(guarded, target):
                raise Stop(f"rehearsal target {target} overlaps {guarded}")
            a, b = os.stat(target), os.stat(guarded)
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                raise Stop(f"rehearsal target {target} is {guarded} under another name")
        store = os.path.dirname(target)
    root = Root(target)
    try:
        points = mount_points_inside(root.path)
    except OSError:
        raise Stop("/proc/self/mountinfo is not readable: mount aliases cannot be excluded") from None
    if points:
        raise Stop(f"mount points at or inside the target: {points}")
    return ("production" if args.production else "rehearsal"), root, store


def lock(store):
    path = LOCK_FILE if store in ("/root", PRODUCTION_BACKUP_DIR) else os.path.join(store, ".release_tool.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise Stop("another release_tool run holds the lock") from None
    return fd


def active_research_processes(target, proc_root='/proc'):
    """Read-only maintenance gate. Never print commands/environments or terminate a process."""
    active=[];prefix=(target.rstrip('/')+'/').encode()
    for entry in Path(proc_root).iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
        try:command=(entry/'cmdline').read_bytes()
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:raise Stop('cannot establish that production sessions are drained') from None
        if prefix in command and any(token in command for token in (
                b'/deploy/run_v1.py',b'rolling_test.broker_main',b'rolling_test.evaluator',b'/deploy/selftest_agent.py')):
            active.append(int(entry.name))
    return sorted(active)


# ------------------------------------------------------------------------------------------------ apply
def apply(args):
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,80}", args.approval) or not re.fullmatch(r"[0-9a-f]{64}", args.manifest_sha):
        raise Stop("bad approval reference or manifest SHA")
    mode, root, store = select(args)
    if mode=='production':
        active=active_research_processes(root.path)
        if active:raise Stop(f'active production sessions/evaluations {active}; save and drain before deployment; nothing terminated')
    lk = lock(store)                     # the lock covers every check below through the last write
    log(f"apply: mode {mode}; target {root.path} ({root.dev}:{root.ino}); approval {args.approval}; manifest {args.manifest_sha}")
    # ---- 0 preflight: nothing is written before every check passed
    if shutil.disk_usage(store).free < FREE_BYTES:
        raise Stop(f"less than 1 GiB free under {store}")
    if root.lstat(MARKER) is not None:
        raise Stop(f"an earlier run did not finish ({MARKER} in the target): roll it back first")
    left = root.leftovers()
    if left:
        raise Stop(f"leftovers of an interrupted write: {left[:3]}")
    old_bytes = root.read(OLD_MANIFEST)
    if sha(old_bytes) != PROD_MANIFEST_SHA:
        raise Stop("target manifest is not the production baseline")
    old = manifest(old_bytes)
    for rel, h in old.items():
        if sha(root.read(rel)) != h:
            raise Stop(f"target differs from its manifest: {rel}")
    staging = Root(RC)
    new_bytes = staging.read(NEW_MANIFEST)
    if sha(new_bytes) != args.manifest_sha:
        raise Stop("candidate manifest is not the approved one")
    new = manifest(new_bytes)
    payload = {}
    for rel, h in new.items():
        if not RX_REL.fullmatch(rel) or rel in ("deploy/host.json",) or rel.startswith("deploy/rolling/"):
            raise Stop(f"manifest names a path outside the release scope: {rel}")
        data = staging.read(rel)
        if sha(data) != h:
            raise Stop(f"staging copy differs from the candidate manifest: {rel}")
        payload[rel] = data
    if shutil.disk_usage(root.path).free < max(64 << 20, 2 * sum(map(len, payload.values()))):
        raise Stop("insufficient target space for atomic code installation")
    broker_rel='deploy/rolling/broker.json'
    broker=json.loads(root.read(broker_rel))
    if type(broker.get('authorized')) is not bool:
        raise Stop('broker authorization state is not a boolean')
    # Preserve the operator's existing permission; this release neither grants
    # permission nor revokes the previously approved automatic 2026 evaluation.
    broker_bytes=(json.dumps(broker,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if b"test_fault_injection" in root.read("deploy/host.json"):
        raise Stop("host.json has a test flag")
    if sha(root.read("tests/v1beta_fixtures.py")) != SELFTEST_FIXTURE_SHA:
        raise Stop("self-test fixture changed")
    # Formal policy is a small, backed-up operator config merge. Resource paths,
    # state, papers, approvals and all historical data remain exactly as configured.
    formal_rel='config/research.json'
    formal=json.loads(root.read(formal_rel))
    formal['require_rolling_test']=True
    formal_bytes=(json.dumps(formal,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    meta = {}
    for rel in list(new) + [OLD_MANIFEST,formal_rel,broker_rel]:
        st = root.check_file(rel)                  # walks every directory without following links
        if st is not None:
            if (st.st_uid, st.st_gid) != (0, 0):
                raise Stop(f"metadata drift: {rel} is {st.st_uid}:{st.st_gid}, expected root:root")
            meta[rel] = dict(mode=stat.S_IMODE(st.st_mode), uid=st.st_uid, gid=st.st_gid)
    # ---- 1 backup (own directory per run)
    backup = tempfile.mkdtemp(prefix="v1_recovery_backup_", dir=store)
    os.chmod(backup, 0o700)
    files = {}
    for rel in meta:
        files[rel] = sha(root.read(rel))
        dst = os.path.join(backup, "files", rel)
        os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
        with open(dst, "xb") as f:
            f.write(root.read(rel))
    record = dict(mode=mode, target=root.path, target_id=f"{root.dev}:{root.ino}", approval=args.approval,
                  manifest=args.manifest_sha, baseline=PROD_MANIFEST_SHA, meta=meta, sha256=files,
                  new_files=sorted(set(new) - set(meta)), created=datetime.datetime.now().isoformat())
    with open(os.path.join(backup, "TARGET.json"), "x", encoding="utf-8") as f:
        json.dump(record, f, indent=1)
    _seal(backup)
    log(f"backup {backup}: {len(meta)} existing files with mode/uid/gid, {len(record['new_files'])} new files")
    log(f"if this run stops from here on: release_tool.py rollback --{mode}{' ' + root.path if mode == 'rehearsal' else ''} --backup {backup}")
    # ---- 2 install
    root.write(MARKER, backup.encode("utf-8"), 0o600)
    bm=meta[broker_rel]
    root.write(broker_rel,broker_bytes,bm['mode'],bm['uid'],bm['gid'])
    fm=meta[formal_rel]
    root.write(formal_rel,formal_bytes,fm['mode'],fm['uid'],fm['gid'])
    stop_after = int(os.environ.get("RELEASE_TOOL_REHEARSAL_INTERRUPT_AFTER", "0") or 0) if mode == "rehearsal" else 0
    for n, rel in enumerate(sorted(new), 1):
        # an existing file keeps its recorded mode; a new deploy script is executable, everything else 0644
        new_mode = 0o755 if rel.startswith("deploy/") and rel.endswith((".sh", ".py")) else 0o644
        root.write(rel, payload[rel], meta[rel]["mode"] if rel in meta else new_mode)
        if stop_after and n >= stop_after:
            log(f"REHEARSAL: interrupted after {n} files")
            raise SystemExit(9)
    root.write("docs/release_v1_sha256.before_recovery.txt", old_bytes, meta[OLD_MANIFEST]["mode"])
    root.write(OLD_MANIFEST, new_bytes, meta[OLD_MANIFEST]["mode"])
    _clear_pycache(root)
    # ---- 3 post-check
    for rel, h in manifest(root.read(OLD_MANIFEST)).items():
        if sha(root.read(rel)) != h:
            raise Stop(f"post-check: {rel} does not match the installed manifest")
    root.unlink(MARKER)
    # ---- 4 smoke
    src = os.path.join(root.path, "src")
    code = SMOKE.format(src=src, vendor=os.path.join(src, "rolling_test", "vendor"))
    if mode == "production":
        subprocess.run(["runuser", "-u", "quantagent", "--", "env", "-i", "HOME=/tmp", "PATH=/usr/bin:/bin", VENV_PYTHON, "-I", "-B",
                        "-c", code], check=True)
        log('production-data selftest is not automatic; run the separately approved AB-only synthetic OS acceptance from the runbook')
    else:
        subprocess.run([VENV_PYTHON, "-I", "-B", "-c", code], check=True)
        log("rehearsal: the OS-level rolling self-test is pinned to production and was not run")
    os.close(lk)
    log(f"done: mode {mode}; target {root.path}; manifest {args.manifest_sha}; backup {backup}")


def _seal(backup):
    sums = []
    for base, _, files in os.walk(backup):
        for f in files:
            if f != "BACKUP_SHA256.json":
                p = os.path.join(base, f)
                with open(p, "rb") as fh:
                    sums.append((os.path.relpath(p, backup).replace(os.sep, "/"), sha(fh.read())))
    with open(os.path.join(backup, "BACKUP_SHA256.json"), "x", encoding="utf-8") as f:
        json.dump(dict(sorted(sums)), f, indent=1)


def _clear_pycache(root):
    for base, dirs, _ in os.walk(os.path.join(root.path, "src"), followlinks=False):
        for d in [d for d in dirs if d == "__pycache__"]:
            p = os.path.join(base, d)
            if not os.path.islink(p):
                shutil.rmtree(p)
        dirs[:] = [d for d in dirs if d != "__pycache__"]


# ------------------------------------------------------------------------------------------------ rollback
def _backup_record(backup, mode, root):
    """Read-only: the backup is intact and was made for this mode and this resolved target (path and device:inode)."""
    try:
        with open(os.path.join(backup, "TARGET.json"), encoding="utf-8") as f:
            record = json.load(f)
        with open(os.path.join(backup, "BACKUP_SHA256.json"), encoding="utf-8") as f:
            sums = json.load(f)
    except (OSError, ValueError):
        raise Stop("not a release_tool backup") from None
    for rel, h in sums.items():
        with open(os.path.join(backup, rel), "rb") as fh:
            if sha(fh.read()) != h:
                raise Stop(f"backup damaged: {rel}")
    if record["mode"] != mode:
        raise Stop(f"backup was made in {record['mode']} mode, not {mode}")
    if record["target"] != root.path or record["target_id"] != f"{root.dev}:{root.ino}":
        raise Stop(f"target {root.path} ({root.dev}:{root.ino}) is not the backup's target {record['target']} ({record['target_id']})")
    return record


def rollback(args):
    mode, root, store = select(args)
    if mode=='production':
        active=active_research_processes(root.path)
        if active:raise Stop(f'active production sessions/evaluations {active}; save and drain before rollback; nothing terminated')
    backup = os.path.realpath(args.backup)
    _backup_record(backup, mode, root)   # a wrong backup is refused before the lock file is even created
    lk = lock(store)
    record = _backup_record(backup, mode, root)          # and re-read under the lock
    log(f"rollback: mode {mode}; target {root.path}; backup {backup}")
    current_broker = json.loads(root.read('deploy/rolling/broker.json'))
    if type(current_broker.get('authorized')) is not bool:
        raise Stop('broker authorization state is not a boolean')
    # every path checked before the first write: no links, same device, regular files
    for rel in list(record["meta"]) + record["new_files"] + [MARKER, "docs/release_v1_sha256.before_recovery.txt"]:
        st = root.lstat(rel)
        if st is not None and (not stat.S_ISREG(st.st_mode) or st.st_dev != root.dev):
            raise Stop(f"{rel} in the target is not a regular file on the target device")
    for top in ("src", "deploy", "client"):        # temporary files of an interrupted write
        if top=='client' and not os.path.lexists(os.path.join(root.path,top)):
            continue
        os.close(root._dir([top]))
        for base, _, files in os.walk(os.path.join(root.path, top), followlinks=False):
            for f in files:
                if LEFTOVER.search(f):
                    root.unlink(os.path.relpath(os.path.join(base, f), root.path).replace(os.sep, "/"))
    for rel in record["new_files"]:
        root.unlink(rel)
    for rel, m in record["meta"].items():
        with open(os.path.join(backup, "files", rel), "rb") as fh:
            data = fh.read()
        if sha(data) != record["sha256"][rel]:
            raise Stop(f"backup copy of {rel} does not match the recorded SHA")
        if rel=='deploy/rolling/broker.json':
            broker=json.loads(data)
            # Preserve existing authorization, but never resurrect permission
            # that an operator revoked after the backup was made.
            broker['authorized'] = broker['authorized'] and current_broker['authorized']
            data=(json.dumps(broker,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        root.write(rel, data, m["mode"], m["uid"], m["gid"])
    root.unlink("docs/release_v1_sha256.before_recovery.txt")
    _clear_pycache(root)
    for rel, h in manifest(root.read(OLD_MANIFEST)).items():
        if sha(root.read(rel)) != h:
            raise Stop(f"after rollback {rel} does not match the restored manifest")
    if sha(root.read(OLD_MANIFEST)) != record["baseline"]:
        raise Stop("restored manifest is not the recorded baseline")
    root.unlink(MARKER)
    os.close(lk)
    log(f"rolled back to the baseline manifest {record['baseline'][:12]}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("apply", "rollback"):
        s = sub.add_parser(name)
        g = s.add_mutually_exclusive_group(required=True)
        g.add_argument("--production", action="store_true")
        g.add_argument("--rehearsal", metavar="DIR")
        if name == "apply":
            s.add_argument("--approval", required=True)
            s.add_argument("--manifest-sha", required=True)
        else:
            s.add_argument("--backup", required=True)
    args = p.parse_args(argv)
    try:
        (apply if args.cmd == "apply" else rollback)(args)
    except Stop as e:
        log(f"STOP: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
