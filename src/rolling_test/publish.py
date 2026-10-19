"""Root-orchestrated rolling snapshot publication (Linux). Never an Agent Tool.

root  : fingerprints the six source files (O_NOFOLLOW, single link, regular), pins read-only FDs, forks
child : drops to quantpub, rlimits, closes every other FD, statically decodes (no pickle execution), trims trailing
        incomplete days, masks pre-listing cells and identity conflicts, validates, writes a staging directory
root  : re-verifies every staged hash, seals ownership root:<evaluator group> 0440/0750, atomic rename, index update.
Identical source fingerprints reuse the existing snapshot (no re-publication).
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time

from .factors import fingerprint
from .snapshot import FIELDS, SnapshotError, digest, select_rows, version_id, write_panel

INDEX = 'index.json'


def source_spec(root, cache=None):
    """Size + SHA-256 of the six source files; an (inode,size,mtime) cache avoids re-hashing unchanged files."""
    root = Path(root)
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise SnapshotError('SOURCE_ROOT_LINK')
    spec, new_cache = {}, {}
    for f in FIELDS:
        fd = os.open(root / (f + '.pkl'), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_BINARY', 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not 0 < st.st_size <= 256 * 1024 ** 2:
                raise SnapshotError('SOURCE_FILE_DENIED')
            key = [st.st_ino, st.st_size, st.st_mtime_ns]
            hit = (cache or {}).get(f)
            if hit and hit['key'] == key:
                sha = hit['sha256']
            else:
                h = hashlib.sha256()
                while block := os.read(fd, 1 << 20):
                    h.update(block)
                sha = h.hexdigest()
            spec[f] = dict(bytes=st.st_size, sha256=sha)
            new_cache[f] = dict(key=key, sha256=sha)
        finally:
            os.close(fd)
    return spec, new_cache


def load_index(private_root):
    path = Path(private_root) / INDEX
    if not path.exists():
        return []
    st = path.stat()
    if path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022 or st.st_nlink != 1:
        raise SnapshotError('INDEX_NOT_ROOT_CONTROLLED')
    return json.loads(path.read_text(encoding='utf-8'))


def _write_index(private_root, rows, group_id):
    path = Path(private_root) / INDEX
    temp = path.with_name(INDEX + '.' + str(os.getpid()) + '.tmp')
    with temp.open('x', encoding='utf-8') as out:
        out.write(json.dumps(rows, ensure_ascii=False, sort_keys=True))
    os.chown(temp, 0, group_id)
    os.chmod(temp, 0o440)
    os.replace(temp, path)


def current(private_root, source, warmup=330):
    """The existing snapshot built from exactly these sources, if any."""
    want = fingerprint(source)
    return next((r for r in load_index(private_root) if r['source_fingerprint'] == want and r['warmup_rows'] == warmup), None)


def publish(*, source_root, private_root, staging_root, expected_codes, approval_ref, implementation,
            publisher_user='quantpub', evaluator_group='quanteval', today, source, listing=None, wall_seconds=240,
            synthetic=False, warmup=330):
    """Publish one snapshot for the pinned `source`; returns the index row. Caller is root."""
    import grp
    import pwd
    if os.geteuid() != 0:
        raise PermissionError('ROOT_BROKER_REQUIRED')
    if type(warmup) is not int or warmup < 330:
        raise SnapshotError('WARMUP_BOUND')
    existing = current(private_root, source, warmup)
    if existing:
        return dict(existing, reused=True)
    import sys
    vendor = str(Path(__file__).parent / 'vendor')
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from linux_publisher import _pinned_fds
    fds = _pinned_fds(Path(source_root), source)
    staging = Path(staging_root) / ('.pending-' + os.urandom(8).hex())
    pub = pwd.getpwnam(publisher_user)
    gid = grp.getgrnam(evaluator_group).gr_gid
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            import resource
            os.close(read_end)
            os.setgroups([])
            os.setgid(pub.pw_gid)
            os.setuid(pub.pw_uid)
            if os.geteuid() == 0:
                raise PermissionError('PUBLISHER_DROP_FAILED')
            os.environ.clear()
            os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
            os.umask(0o077)
            resource.setrlimit(resource.RLIMIT_AS, (3 * 1024 ** 3,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
            resource.setrlimit(resource.RLIMIT_FSIZE, (160 * 1024 ** 2,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            keep = {0, 1, 2, write_end, *fds.values()}
            for name in os.listdir('/proc/self/fd'):
                if int(name) not in keep:
                    try:
                        os.close(int(name))
                    except OSError:
                        pass
            import numpy as np
            from qra_data.adapter import Budget, ControlledReader, Refused
            from release import Panel, exclude_identity_conflicts, mask_prelisting

            def opener(path):
                name = Path(path).stem
                if name not in fds or path != str(Path(source_root) / (name + '.pkl')):
                    raise Refused('PATH_NOT_GRANTED')
                duplicate = os.dup(fds[name])
                os.lseek(duplicate, 0, os.SEEK_SET)
                return duplicate
            history_start = '20200101' if warmup > 330 else '20240101'
            manifest = {'datasets': {'daily_update_core': {'root': str(source_root),
                        'fields': {f: {'file': f + '.pkl', **source[f]} for f in FIELDS},
                        'certification': {'level': 'PROFILED', 'start': history_start, 'end': today, 'fields': list(FIELDS)}}}}
            reader = ControlledReader(manifest, allowed_roots=[str(source_root)], opener=opener,
                                      budget=Budget(max_cells=60_000_000, max_file_bytes=256 * 1024 ** 2,
                                                    max_result_bytes=512 * 1024 ** 2))
            data = reader.read('daily_update_core', FIELDS, history_start, today, purpose='profile')
            codes = tuple(data.codes)
            if set(expected_codes) - set(codes):
                raise SnapshotError('BASELINE_CODES_MISSING_IN_SOURCE')
            columns = [codes.index(c) for c in expected_codes]
            fields = {f: np.ascontiguousarray(a[:, columns], dtype=np.float64) for f, a in data.fields.items()}
            counts = np.isfinite(fields['close']).sum(axis=1)
            rows, certified_end, quality = select_rows(list(data.dates), counts, today=today, warmup=warmup)
            panel = Panel(tuple(data.dates[i] for i in rows), tuple(expected_codes), {f: a[rows] for f, a in fields.items()})
            listing_dates = listing(panel.codes) if listing else None
            masked_cells = 0
            if listing_dates is not None:
                panel, masked_cells = mask_prelisting(panel, listing_dates)
            conflicts = tuple(c for c in ('001914.SZ', '302132.SZ') if c in panel.codes)
            panel, excluded = exclude_identity_conflicts(panel, conflicts)
            target = staging.with_name(staging.name)
            write_panel(target, dates=list(panel.dates), codes=list(panel.codes), fields=dict(panel.fields), source=source,
                        certified_end=certified_end, quality=quality | dict(prelisting_masked_close_cells=masked_cells,
                        identity_excluded_close_cells=excluded, source_codes=len(codes), new_codes_not_in_axis=len(set(codes) - set(expected_codes))),
                        implementation=implementation, approval_ref=approval_ref,
                        listing_info=dict(certified=False, candidate_mask_applied=listing_dates is not None),
                        synthetic=synthetic)
            os.write(write_end, b'OK')
            os._exit(0)
        except BaseException as exc:
            try:
                os.write(write_end, ('ERR ' + type(exc).__name__ + ' ' + str(exc)[:200]).encode())
            except Exception:
                pass
            os._exit(1)
    os.close(write_end)
    for fd in fds.values():
        os.close(fd)
    deadline = time.monotonic() + wall_seconds
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if time.monotonic() > deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise TimeoutError('PUBLISHER_TIMEOUT')
        time.sleep(.1)
    message = os.read(read_end, 4096).decode('utf-8', 'replace')
    os.close(read_end)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) or message != 'OK':
        raise SnapshotError('PUBLISHER_FAILED: ' + message)
    # Root re-verifies what the unprivileged decoder wrote before sealing it.
    mpath = staging / 'manifest.json'
    st = os.stat(staging, follow_symlinks=False)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != pub.pw_uid:
        raise SnapshotError('STAGING_OWNER')
    m = json.loads(mpath.read_text(encoding='utf-8'))
    if m['source'] != source or set(m['sha256']) != {f + '.npy' for f in FIELDS}:
        raise SnapshotError('STAGED_SOURCE_MISMATCH')
    for name, sha in m['sha256'].items():
        p = staging / name
        if p.is_symlink() or digest(p) != sha:
            raise SnapshotError('STAGED_FINGERPRINT')
    version = version_id(m['certified_end'], source if warmup == 330 else dict(source=source, warmup=warmup))
    final = Path(private_root) / version
    if final.exists():
        raise SnapshotError('SNAPSHOT_VERSION_EXISTS')
    for p in staging.iterdir():
        os.chown(p, 0, gid)
        os.chmod(p, 0o440)
    os.chown(staging, 0, gid)
    os.chmod(staging, 0o750)
    # The manifest names its own directory; rewrite release_id before sealing.
    m['release_id'] = version
    os.chmod(mpath, 0o640)
    mpath.write_text(json.dumps(m, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding='utf-8')
    os.chmod(mpath, 0o440)
    os.rename(staging, final)
    row = dict(version=version, manifest_sha256=digest(final / 'manifest.json'), certified_end=m['certified_end'],
               source_fingerprint=fingerprint(source), test_rows=m['quality']['test_rows'],
               warmup_rows=m['quality']['warmup_rows'], dropped_incomplete=m['quality']['dropped_incomplete_trailing_dates'],
               published_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), status=m['status'])
    rows = load_index(private_root) + [row]
    _write_index(private_root, rows, gid)
    return dict(row, reused=False)
