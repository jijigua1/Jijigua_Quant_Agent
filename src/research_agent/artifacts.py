"""Task-scoped artifacts. Roots come from operator configuration, never model arguments."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import uuid
import re
from zoneinfo import ZoneInfo

from .contracts import canonical, parse_json
from .security import Denied, valid_task_id

MAX_OUTPUT_BYTES = 20 * 1024 * 1024
# program-written study JSON (analysis, manifest ...): a size guard, not a content check; the same order as the report
# revision files (1-2 MiB). 64 KiB was too small: a real GH study's analysis was 52 KiB before its 2026 Test (C6R4-I2).
STUDY_JSON_MAX_BYTES = 1024 * 1024

def check_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Denied('ARTIFACT_ROOT_INVALID')
    for p in (path, *path.parents):
        if p.is_symlink() or getattr(p, 'is_junction', lambda: False)():
            raise Denied('ARTIFACT_LINK_DENIED')
    if not path.is_dir():
        raise Denied('ARTIFACT_DIRECTORY_UNAVAILABLE')
    return path

class ResearchArtifacts:
    def __init__(self, root, *, legacy_roots=()):
        self.root = check_directory(root)
        self.legacy_roots=tuple(check_directory(p) for p in legacy_roots)
        check_directory(self.root / 'research_runs')
        if not os.access(self.root / 'research_runs', os.W_OK):
            raise Denied('ARTIFACT_DIRECTORY_NOT_WRITABLE')

    def create(self, task_id, factor_name='factor'):
        valid_task_id(task_id)
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',factor_name):
            raise Denied('INVALID_FACTOR_DIRECTORY_NAME')
        now=datetime.now(ZoneInfo('Asia/Shanghai'))
        parent = self.root / 'research_runs' / now.strftime('%Y-%m-%d')
        parent.mkdir(mode=0o700,exist_ok=True)
        check_directory(parent)
        run_id = uuid.uuid4().hex[:16]
        name=now.strftime('%H-%M-%S')+'_'+factor_name
        run = parent / name
        try:run.mkdir(mode=0o700)
        except FileExistsError:
            run=parent/(name+'_'+run_id[:8]);run.mkdir(mode=0o700)
        for name in ('code', 'data', 'figures', 'reports', 'logs'):
            (run / name).mkdir(mode=0o700)
        return task_id + ':' + run_id, run

    def _run_root(self,path):
        return next((p/'research_runs' for p in (self.root,*self.legacy_roots) if Path(path).is_relative_to(p/'research_runs')),self.root/'research_runs')

    def checked_run(self, path):
        path=Path(path)
        check_directory(path)
        root=self._run_root(path)
        if not path.is_relative_to(root):
            raise Denied('ARTIFACT_PATH_DENIED')
        parts=path.relative_to(root).parts
        if len(parts)!=2 and not (len(parts)==5 and parts[2:4]==('.audit','r')
                and re.fullmatch(r'r[0-9]{4}_[0-9a-f]{8}',parts[4])):
            raise Denied('ARTIFACT_PATH_DENIED')
        return path

    def create_revision(self, original, revision):
        """A report is an audit child of its study, never another top-level research."""
        original=self.checked_run(original)
        if len(original.relative_to(self._run_root(original)).parts)!=2 or type(revision) is not int or not 2<=revision<=9999:
            raise Denied('REPORT_REVISION_PATH_DENIED')
        m=parse_json((original/'manifest.json').read_text(encoding='utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)
        valid_task_id(m['task_id'])
        parent=original
        for name in ('.audit','r'):
            check_directory(parent)
            parent=parent/name
            if not parent.exists():parent.mkdir(mode=0o700)
            check_directory(parent)
        run_id=uuid.uuid4().hex[:16]
        run=parent/f'r{revision:04d}_{run_id[:8]}'
        run.mkdir(mode=0o700)
        for name in ('code','data','figures','reports','logs'):
            (run/name).mkdir(mode=0o700)
        return m['task_id']+':'+run_id,run

    def locate(self, study_id, context):
        import re
        if not re.fullmatch(r'[0-9a-f]{32}:[0-9a-f]{16}', study_id):
            raise Denied('INVALID_STUDY_ID')
        task_id, run_id = study_id.split(':')
        store = context['store']
        allowed = {context['task_id']}
        if task_id not in allowed:
            allowed.update(t['research_task_id'] for t in store.session_turns(context['session_id']) if t['research_task_id'])
        if task_id not in allowed:
            raise Denied('STUDY_NOT_IN_SESSION')
        task = store.load(task_id)
        evidence = [e['result']['data'] for e in task.experiments if e['result']['data'].get('study_id') == study_id]
        paths=[x['payload']['artifact_path'] for x in store.events(task_id)
            if x['kind']=='ARTIFACT_CREATED' and x['payload'].get('study_id')==study_id]
        run=self.checked_run(evidence[0]['artifact_path'] if evidence else paths[0] if paths else
            self.root/'research_runs'/task_id/run_id)
        m=parse_json((run/'manifest.json').read_text(encoding='utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)
        if m.get('task_id')!=task_id or m.get('run_id')!=run_id:raise Denied('ARTIFACT_ID_MISMATCH')
        if not evidence and task.status=='EXPORT_FAILED':
            if any(e['kind']=='ARTIFACT_CREATED' and e['payload'].get('study_id')==study_id for e in store.events(task_id)):
                m=parse_json((run/'manifest.json').read_text(encoding='utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)
                if m.get('task_id')==task_id and m.get('delivery_status')=='EXPORT_FAILED':
                    evidence=[{'analysis_sha256':m['analysis_sha256'],'artifact_path':str(run)}]
        if not evidence:raise Denied('STUDY_NOT_IN_LEDGER')
        return run, evidence[0]

    @staticmethod
    def write_json(path, data, *, max_bytes=STUDY_JSON_MAX_BYTES):
        # Exclusive creation keeps frozen configuration and evidence immutable.
        with Path(path).open('x', encoding='utf-8') as f:
            f.write(canonical(data,max_bytes=max_bytes) + '\n')

    @staticmethod
    def inventory(run):
        files = []
        total = 0
        archive_bytes = archive_files = 0
        budget=MAX_OUTPUT_BYTES
        m=run/'manifest.json'
        if m.exists():
            budget=parse_json(m.read_text(encoding='utf-8')).get('artifact_budget_bytes',budget)
        if type(budget) is not int or not MAX_OUTPUT_BYTES <= budget <= 512*1024*1024:
            raise Denied('ARTIFACT_BUDGET_INVALID')
        for p in sorted(run.rglob('*')):
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():
                raise Denied('ARTIFACT_LINK_DENIED')
            if p.is_file() and p.stat().st_nlink != 1:
                raise Denied('ARTIFACT_HARDLINK_DENIED')
            # Each revision has its own bounded manifest, authenticated from the
            # parent's report index. Do not recursively count it as current data.
            if p.relative_to(run).parts[0]=='.audit':
                if p.is_file():
                    archive_bytes+=p.stat().st_size;archive_files+=1
                    if archive_bytes>4*budget or archive_files>4096:
                        raise Denied('ARTIFACT_ARCHIVE_BUDGET_EXHAUSTED')
                continue
            if p.is_file() and p.name != 'manifest.json':
                st = p.stat()
                if st.st_nlink != 1:
                    raise Denied('ARTIFACT_HARDLINK_DENIED')
                total += st.st_size
                if total > budget or len(files) >= 100:
                    raise Denied('ARTIFACT_BUDGET_EXHAUSTED')
                files.append({'path': p.relative_to(run).as_posix(), 'bytes': st.st_size,
                              'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        return files

    @staticmethod
    def read_analysis(run, evidence):
        path = run / 'data/analysis.json'
        if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > STUDY_JSON_MAX_BYTES:
            raise Denied('ARTIFACT_FILE_DENIED')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence['analysis_sha256']:
            raise Denied('ARTIFACT_FINGERPRINT_MISMATCH')
        return parse_json(raw.decode('utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)

    def finalize(self, task, events=()):
        import re
        evidence = {e['result']['data'].get('study_id'):e for e in task.experiments
            if e['result']['data'].get('study_id','').startswith(task.id+':')}
        paths={x['payload']['study_id']:x['payload']['artifact_path'] for x in events if x['kind']=='ARTIFACT_CREATED'}
        paths.update({sid:e['result']['data']['artifact_path'] for sid,e in evidence.items() if sid})
        for sid,path in paths.items():
            run=self.checked_run(path)
            m=parse_json((run/'manifest.json').read_text(encoding='utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)
            if m['task_id']!=task.id or task.id+':'+m['run_id']!=sid:raise Denied('ARTIFACT_ID_MISMATCH')
            e = evidence.get(sid)
            self.write_json(run/'logs/stages.json',[x for x in events if x['kind']=='RESEARCH_STAGE'])
            self.write_json(run/'logs/task.json',dict(task_id=task.id,status=task.status,error=task.error,
                counters=task.counters,usage=task.usage,experiments=[{k:v for k,v in x.items()
                    if k in {'tool','tool_version','parameters','hypothesis','change_reason','skill_version',
                        'skill_hash','core_code_sha256','result_sha256'}} for x in task.experiments]))
            self.update_manifest(run, dict(task_status=task.status, error=task.error,
                completed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                result_sha256=e['result_sha256'] if e else None, model_usage=task.usage,
                files=self.inventory(run)))

    def update_manifest(self, run, changes):
        path = run / 'manifest.json'
        if path.is_symlink() or path.stat().st_nlink != 1:
            raise Denied('ARTIFACT_FILE_DENIED')
        manifest = parse_json(path.read_text(encoding='utf-8'),max_bytes=STUDY_JSON_MAX_BYTES)
        manifest.update(changes)
        temp = run / ('manifest.' + uuid.uuid4().hex + '.tmp')
        self.write_json(temp, manifest)
        os.replace(temp, path)
