"""Final-study completion and the single public report, outside the evaluator.

Only the existing authenticated report reader admits Test evidence. No new
formula, evaluator, signature scheme or evaluation request is introduced here.
"""
import hashlib
import json
import os
from pathlib import Path
import uuid

from .artifacts import check_directory
from .contracts import canonical
from .security import Denied

POLICY = 'controlled_2026_test'
WAITING = {'NOT_AUTHORIZED','EVALUATOR_UNAVAILABLE','NO_TEST_DATA','NO_MATURE_LABELS','PENDING','FINAL_REPORT_PUBLICATION_PENDING'}


def preserve_initial_report(artifacts, original):
    """Before any Test, freeze revision 1 independently of the public report alias."""
    audit=original
    for name in ('.audit','pretest_report'):
        check_directory(audit)
        audit=audit/name
        if not audit.exists():audit.mkdir(mode=0o700)
        check_directory(audit)
    saved=[]
    for name in ('report.html','report.md'):
        raw=(original/'reports'/name).read_bytes()
        target=audit/name
        with target.open('xb') as out:out.write(raw)
        saved.append(dict(path=target.relative_to(original).as_posix(),sha256=hashlib.sha256(raw).hexdigest()))
    index=original/'reports/report_versions.json'
    if index.exists():
        versions=json.loads(index.read_text(encoding='utf-8'))
        versions[0].update(html=str(audit/'report.html'),markdown=str(audit/'report.md'))
        _replace(index,(canonical(versions)+'\n').encode('utf-8'))
    artifacts.update_manifest(original,dict(pretest_report=saved))


def _checked(run, name, records, limit=32*1024*1024):
    path=run/name
    record=next((x for x in records if x['path']==name),None)
    if record is None or path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>limit:
        raise Denied('FINAL_REPORT_SOURCE_DENIED')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record['sha256']:
        raise Denied('FINAL_REPORT_SOURCE_FINGERPRINT')
    return raw


def _replace(path, raw):
    if path.exists() and (path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1):
        raise Denied('FINAL_REPORT_TARGET_DENIED')
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def status_fields(answer, reason):
    status='WAITING_TEST' if reason in WAITING else 'BLOCKED_TEST'
    return answer|dict(completion_policy=POLICY,research_status=status,completion_reason=reason,
                       final_report_ready=False,report_status='incomplete',html_path='')


def finish_study(artifacts, original, answer, rolling, *, publish=True):
    """Promote only a verified complete revision; preserve pre-Test bytes and all archives.

    Historical studies without the formal-policy marker keep their old contract.
    Re-reading an already published report does not write or request evaluation.
    """
    original=artifacts.checked_run(original)
    answer=dict(answer,artifact_path=str(original))
    manifest=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('require_rolling_test'):
        return answer
    from .report_versions import latest_report
    try:
        verified=latest_report(artifacts,original,answer,rolling)
        # A report revision is evidence within the study, never a different
        # research identity, including when Test fails and completion is blocked.
        verified['artifact_path']=str(original)
        test=verified.get('metrics',{}).get('professional',{}).get('test',{})
        if test.get('status')!='COMPLETED':
            return status_fields(verified,test.get('reason') or verified.get('completion_reason') or 'TEST_NOT_COMPLETED')
        if test.get('evaluation_type')!='ROLLING_EXPOSED_TEST' or not str(test.get('start','')).startswith('2026-'):
            return status_fields(verified,'CONTROLLED_2026_TEST_REQUIRED')
        revision=artifacts.checked_run(verified['report_artifact_path'])
        vm=json.loads((revision/'manifest.json').read_text(encoding='utf-8'))
        if vm.get('rolling_status')!='COMPLETED' or vm.get('source_study')!=str(original):
            return status_fields(verified,'STUDY_INVALIDATED_OR_INCOMPLETE')
        check=json.loads(_checked(revision,'data/report_consistency.json',vm['files']))
        if check.get('status')!='PASSED':
            return status_fields(verified,'REPORT_CONSISTENCY_FAILED')
        payloads={name:_checked(revision,name,vm['files']) for name in ['reports/report.html','reports/report.md']}
        # HTML embeds its images. Markdown keeps explicit links to the immutable
        # revision's figures, so the public copy never shows pre-Test charts.
        relative=revision.relative_to(original).as_posix()
        payloads['reports/report.md']=payloads['reports/report.md'].replace(b'(../figures/',('(../'+relative+'/figures/').encode())
    except (Denied,OSError,ValueError,KeyError) as exc:
        return status_fields(answer,getattr(exc,'code','TEST_RECEIPT_UNVERIFIED'))

    html_sha=hashlib.sha256(payloads['reports/report.html']).hexdigest()
    ready=(manifest.get('final_report_sha256')==html_sha and
           manifest.get('final_report_revision')==verified['report_revision'])
    if ready:
        # A mutable, user-facing alias must still equal the authenticated archive.
        for name,raw in payloads.items():
            if _checked(original,name,manifest['files'])!=raw:
                raise Denied('FINAL_REPORT_FINGERPRINT')
    else:
        if not publish:
            return status_fields(verified,'FINAL_REPORT_PUBLICATION_PENDING')
        if not manifest.get('pretest_report'):
            return status_fields(verified,'INITIAL_REPORT_ARCHIVE_MISSING')
        for item in manifest['pretest_report']:
            _checked(original,item['path'],manifest['pretest_report'])
        try:
            for name,raw in payloads.items():_replace(original/name,raw)
        except OSError:
            # The original analysis/index and immutable revision remain intact.
            # A later explicit refresh retries publication without evaluation.
            return status_fields(verified,'FINAL_REPORT_PUBLICATION_PENDING')
        artifacts.update_manifest(original,dict(pretest_report=manifest['pretest_report'],
            final_report_revision=verified['report_revision'],final_report_sha256=html_sha,
            research_status='COMPLETED',completion_policy=POLICY,final_report_ready=True,
            files=artifacts.inventory(original)))
    return verified|dict(artifact_path=str(original),html_path=str(original/'reports/report.html'),
        report_path=str(original/'reports/report.md'),completion_policy=POLICY,research_status='COMPLETED',
        completion_reason='',final_report_ready=True,report_status='complete')
