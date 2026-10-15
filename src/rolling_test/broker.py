"""Root broker for ROLLING_EXPOSED_TEST, living only for one CLI session (parent of the dropped Agent process).

It accepts two requests from the Agent over an inherited socketpair: `status`, and `evaluate <study_id, artifact_path>`.
Everything else is fixed host configuration (root-owned JSON). It never executes Agent-supplied code, never returns
file contents, never follows links in Agent-owned directories, and refuses everything while `authorized` is false.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from . import CONTRACT, OVERLAP_DAYS, PROTOCOL
from .evaluator import EvaluationDenied, verify
from .factors import frozen_from_study

NOT = 'NOT_EVALUATED'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


class Refused(ValueError):
    pass


class Broker:
    def __init__(self, config, *, runner=None):
        self.c = config
        self.runner = runner or self._run_evaluator
        self.synthetic = bool(config.get('synthetic'))
        # OS ownership/identity checks are on unless this is an in-process engineering test (synthetic, no identities).
        self.enforce = bool(config.get('enforce_identity', not self.synthetic))
        self._source_cache = {}

    # ------------------------------------------------------------------ audit
    def audit(self, event, details):
        path = Path(self.c['audit_path'])
        previous = '0' * 64
        if path.exists():
            if self.enforce and (path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077):
                raise Refused('AUDIT_FILE_INVALID')
            lines = path.read_text(encoding='utf-8').splitlines()
            if lines:
                previous = json.loads(lines[-1])['sha256']
        row = dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), event=event, previous=previous, details=details)
        row['sha256'] = hashlib.sha256(_canonical(row).encode()).hexdigest()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        try:
            os.write(fd, (_canonical(row) + '\n').encode())
        finally:
            os.close(fd)

    # ------------------------------------------------------------------ Agent-owned files, read defensively as root
    def _study_dir(self, artifact_path, study_id):
        root = Path(self.c['research_root'])
        path = Path(artifact_path)
        if not path.is_absolute() or '..' in path.parts:
            raise Refused('STUDY_PATH_DENIED')
        try:
            rel = path.relative_to(root)
        except ValueError:
            raise Refused('STUDY_OUTSIDE_RESEARCH_ROOT') from None
        if len(rel.parts) != 2:
            raise Refused('STUDY_PATH_SHAPE')
        current = root
        for part in rel.parts:
            current = current / part
            st = os.lstat(current)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise Refused('STUDY_PATH_LINK_OR_FILE')
            if self.enforce and st.st_uid != self.c['agent_uid']:
                raise Refused('STUDY_OWNER')
        return path

    def _read(self, directory, name, limit):
        fd = os.open(directory / name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_BINARY', 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
                raise Refused('STUDY_FILE_DENIED')
            if self.enforce and st.st_uid != self.c['agent_uid']:
                raise Refused('STUDY_FILE_OWNER')
            chunks = []
            while block := os.read(fd, 1 << 20):
                chunks.append(block)
            return b''.join(chunks)
        finally:
            os.close(fd)

    def _tail_rows(self, directory, name, dates, limit=400 * 1024 ** 2):
        """Header + the requested date rows from the end of a CSV; bounded tail read, no full parse."""
        fd = os.open(directory / name, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
                raise Refused('STUDY_FILE_DENIED')
            head = os.pread(fd, 1 << 20, 0) if hasattr(os, 'pread') else None
            if head is None:
                os.lseek(fd, 0, os.SEEK_SET)
                head = os.read(fd, 1 << 20)
            header = head.split(b'\n', 1)[0].decode().rstrip('\r')    # a CRLF file must not leave '\r' on the last code
            want = set(dates)
            size = min(st.st_size, (len(dates) + 2) * max(len(header) * 3, 4096) + (1 << 20))
            os.lseek(fd, st.st_size - size, os.SEEK_SET)
            tail = os.read(fd, size).decode('utf-8', 'replace').splitlines()[1:]
        finally:
            os.close(fd)
        rows = {}
        for line in tail:
            cells = line.split(',')
            day = cells[0][:10]
            if day in want:
                values = []
                for x in cells[1:]:
                    try:
                        values.append(float(x) if x else float('nan'))
                    except ValueError:
                        values.append(float('nan'))
                rows[day] = values
        return header.split(',')[1:], rows

    # ------------------------------------------------------------------ snapshot
    def snapshot(self):
        if self.synthetic:
            return self.c['synthetic_snapshot']
        from .publish import publish, source_spec
        source, self._source_cache = source_spec(self.c['source_root'], self._source_cache)
        codes = json.loads(Path(self.c['baseline_manifest']).read_text(encoding='utf-8'))['codes']
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
        listing = None
        if self.c.get('listing_candidate'):
            import sys
            vendor = str(Path(__file__).parent / 'vendor')
            if vendor not in sys.path:
                sys.path.insert(0, vendor)
            from linux_publisher import _listing_candidate
            listing = _listing_candidate
        row = publish(source_root=self.c['source_root'], private_root=self.c['snapshot_root'],
                      staging_root=self.c['staging_root'], expected_codes=codes, approval_ref=self.c['approval_ref'],
                      implementation=self.c.get('implementation', {}), today=today, source=source, listing=listing)
        if not row['reused']:
            self.audit('SNAPSHOT_PUBLISHED', {k: row[k] for k in ('version', 'manifest_sha256', 'certified_end', 'source_fingerprint', 'dropped_incomplete')})
        return {k: row[k] for k in ('version', 'manifest_sha256', 'certified_end')}

    # ------------------------------------------------------------------ evaluation
    def _run_evaluator(self, request_path):
        e = self.c['evaluator']
        program = ('import sys;sys.path[:0]=' + repr(e['code_path']) + ';from rolling_test.evaluator import main;main('
                   + repr([self.c['evaluator_config'], str(request_path)]) + ')')
        env = dict(PATH='/usr/local/bin:/usr/bin:/bin', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                   MKL_NUM_THREADS='1', LANG='C.UTF-8', MPLBACKEND='Agg', MPLCONFIGDIR=e['mpl_dir'])
        process = subprocess.run(['/usr/sbin/runuser', '-u', e['user'], '--', e['python'], '-I', '-B', '-c', program],
                                 capture_output=True, text=True, env=env, cwd=e['cwd'], timeout=e.get('timeout', 300))
        if process.returncode:
            raise Refused('EVALUATOR_FAILED: ' + process.stderr.strip().splitlines()[-1][:300] if process.stderr.strip() else 'EVALUATOR_FAILED')
        out = json.loads(process.stdout.strip().splitlines()[-1])
        path = Path(out['receipt'])
        if path.parent != Path(self.c['evaluator']['outbox']) or path.is_symlink():
            raise Refused('RECEIPT_PATH')
        return json.loads(path.read_text(encoding='utf-8')), out['reused']

    def evaluate(self, study_id, artifact_path):
        if not self.c.get('authorized'):
            return dict(status=NOT, reason='NOT_AUTHORIZED',
                        detail='2026 rolling evaluation is not yet authorized for this deployment')
        run = self._study_dir(artifact_path, study_id)
        manifest = json.loads(self._read(run, 'manifest.json', 1024 ** 2))
        if manifest.get('task_id', '') + ':' + manifest.get('run_id', '') != study_id:
            raise Refused('STUDY_ID_MISMATCH')
        raw = self._read(run / 'data', 'analysis.json', 4 * 1024 ** 2)
        files = {f['path']: f for f in manifest.get('files', [])}
        if 'data/analysis.json' not in files or hashlib.sha256(raw).hexdigest() != files['data/analysis.json']['sha256']:
            raise Refused('STUDY_ANALYSIS_FINGERPRINT')
        analysis = json.loads(raw)
        definition = json.loads(self._read(run / 'code', 'factor_definition.json', 256 * 1024))
        try:
            frozen = frozen_from_study(analysis, definition)
        except (KeyError, ValueError) as exc:
            return dict(status=NOT, reason='UNSUPPORTED_STUDY', detail=str(exc)[:200])
        if frozen['synthetic'] != self.synthetic:
            return dict(status=NOT, reason='SYNTHETIC_REAL_MIXING_DENIED')
        snap = self.snapshot()
        valid_end = analysis['spec']['valid'][1]
        snapshot_dates = self.c.get('synthetic_overlap_dates') if self.synthetic else None
        if snapshot_dates is None:
            snapshot_dates = self._snapshot_dates(snap)
        overlap_dates = [d for d in snapshot_dates if d <= valid_end][-OVERLAP_DAYS:]
        request = dict(protocol=PROTOCOL, contract=CONTRACT, study_id=study_id, frozen=frozen['definition'],
                       definition_sha256=frozen['definition_sha256'], snapshot={k: snap[k] for k in ('version', 'manifest_sha256')},
                       overlap_dates=overlap_dates, synthetic=self.synthetic)
        # one request file per (definition, study, snapshot): a second study of the same definition is not a conflict
        study_tag = hashlib.sha256(study_id.encode('utf-8')).hexdigest()[:12]
        request_path = Path(self.c['request_dir']) / (frozen['definition_sha256'][:16] + '_' + study_tag + '_' + snap['version'] + '.json')
        if not request_path.exists():
            with request_path.open('x', encoding='utf-8') as out:
                out.write(_canonical(request))
            if self.enforce:
                import grp
                os.chown(request_path, 0, grp.getgrnam(self.c['evaluator']['user']).gr_gid)
                os.chmod(request_path, 0o440)
        elif json.loads(request_path.read_text(encoding='utf-8')) != request:
            raise Refused('REQUEST_FILE_CONFLICT')
        self.audit('EVALUATION_REQUESTED', dict(study_id=study_id, definition_sha256=frozen['definition_sha256'], snapshot=snap['version']))
        try:
            receipt, reused = self.runner(request_path)
        except EvaluationDenied as exc:
            self.audit('EVALUATION_DENIED', dict(study_id=study_id, code=str(exc)))
            return dict(status=NOT, reason='FAILED', detail=str(exc))
        key = Path(self.c['key_path']).read_bytes()
        result = receipt['result']
        if not verify(key, receipt) or result['study_id'] != study_id or result['definition_sha256'] != frozen['definition_sha256'] \
                or result['snapshot']['version'] != snap['version']:
            self.audit('RECEIPT_REJECTED', dict(study_id=study_id))
            return dict(status=NOT, reason='FAILED', detail='RECEIPT_VERIFICATION_FAILED')
        mismatch = self._overlap_mismatch(run, result['overlap'])
        if mismatch:
            self.audit('HISTORY_MISMATCH', dict(study_id=study_id, evaluation_id=result['evaluation_id'], first=mismatch))
            return dict(status=NOT, reason='HISTORY_MISMATCH', detail=mismatch)
        path = self._register(receipt)
        self.audit('RECEIPT_REGISTERED', dict(study_id=study_id, evaluation_id=result['evaluation_id'], reused=reused,
                                              receipt_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()))
        return dict(status='COMPLETED', evaluation_id=result['evaluation_id'], receipt_path=str(path), reused=reused,
                    snapshot=snap['version'], certified_end=snap['certified_end'])

    def _snapshot_dates(self, snap):
        m = json.loads((Path(self.c['snapshot_root']) / snap['version'] / 'manifest.json').read_text(encoding='utf-8'))
        return [d[:4] + '-' + d[4:6] + '-' + d[6:] for d in m['dates']]

    def _overlap_mismatch(self, run, overlap):
        import math
        dates = [o['date'] for o in overlap if o.get('count') is not None]
        if not dates:
            return 'NO_OVERLAP_DATES'
        codes, rows = self._tail_rows(run / 'data', 'factor_values.csv', dates)
        from . import code_weights
        weights = code_weights(codes) if any('proj' in o for o in overlap) else None
        for o in overlap:
            if o.get('count') is None:
                continue
            values = [v for v in rows.get(o['date'], []) if math.isfinite(v)]
            if o['date'] not in rows:
                return o['date'] + ': date missing from study factor values'
            s = sum(values)
            q = sum(v * v for v in values)
            if len(values) != o['count'] or not math.isclose(s, o['sum'], rel_tol=1e-9, abs_tol=1e-9) or \
                    not math.isclose(q, o['sum_sq'], rel_tol=1e-9, abs_tol=1e-9):
                return o['date'] + f': study count/sum {len(values)}/{s:.12g} vs evaluator {o["count"]}/{o["sum"]:.12g}'
            if weights is not None and 'proj' in o:
                # stock by stock: a code-keyed weighted sum changes when values move between stocks (count/sum do not)
                row = rows[o['date']]
                tol = 1e-9 * max(o.get('proj_scale') or 0.0, 1e-300) + 1e-12
                for i, p in enumerate(o['proj']):
                    mine = sum(w * v for w, v in zip(weights[i], row) if math.isfinite(v))
                    if abs(mine - p) > tol:
                        return o['date'] + f': study per-stock projection {i} {mine:.12g} vs evaluator {p:.12g}'
        return None

    def _register(self, receipt):
        directory = Path(self.c['receipt_dir'])
        path = directory / (receipt['result']['evaluation_id'] + '.json')
        if path.exists():
            if json.loads(path.read_text(encoding='utf-8')) != receipt:
                raise Refused('RECEIPT_REGISTRY_CONFLICT')
            return path
        temp = directory / ('.' + receipt['result']['evaluation_id'] + '.tmp')
        with temp.open('x', encoding='utf-8') as out:
            out.write(_canonical(receipt))
        if self.enforce:
            import grp
            os.chown(temp, 0, grp.getgrnam(self.c['agent_group']).gr_gid)
            os.chmod(temp, 0o440)
        os.replace(temp, path)
        return path

    # ------------------------------------------------------------------ dispatcher
    def handle(self, request):
        from .protocol import ProtocolError, check_request
        try:
            check_request(request)
            if request['op'] == 'status':
                return dict(status='OK', authorized=bool(self.c.get('authorized')), synthetic=self.synthetic,
                            contract=CONTRACT)
            return self.evaluate(request['study_id'], request['artifact_path'])
        except (ProtocolError, Refused, OSError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
            code = type(exc).__name__ + ': ' + str(exc)[:200]
            try:
                self.audit('REQUEST_FAILED', dict(error=code))
            except Exception:
                pass
            return dict(status=NOT, reason='FAILED', detail=code)


def serve(sock, broker):
    """Blocking loop in the root parent until the Agent closes its end."""
    from .protocol import MAX_REQUEST, MAX_RESPONSE, receive, send
    while True:
        try:
            request = receive(sock, MAX_REQUEST)
        except (EOFError, ConnectionError, OSError):
            return
        except ValueError:
            send(sock, dict(status=NOT, reason='FAILED', detail='INVALID_MESSAGE'), MAX_RESPONSE)
            continue
        send(sock, broker.handle(request), MAX_RESPONSE)
