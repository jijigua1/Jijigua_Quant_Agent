"""Windows paper upload UX (2026-10-15): batch / folder / wildcard, validation before any network, in-batch dedupe, which
paper '刚上传的论文' means, and the server-side re-upload fix. Fake ssh/scp; no server is contacted."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'quant_paper'))
import quant_paper as qp  # noqa: E402

FIX = Path(__file__).parent / 'fixtures_v1beta'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(qp.shutil, 'which', lambda name: '/usr/bin/' + name)
    key = tmp_path / 'id_test'
    key.write_text('not a real key')
    monkeypatch.setattr(qp.subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 0, '', ''))
    qp.main(['setup', '--host', 'example.test', '--port', '2222', '--user', 'root', '--identity', str(key)])
    calls, state = [], {'fail': set(), 'version': 0}

    def run(args, **kw):
        calls.append(args)
        if 'scp' in args[0]:
            local = Path(args[-2])
            if local.name in state['fail']:
                return subprocess.CompletedProcess(args, 1, '', 'Connection reset by peer')
            state['last'] = local.name
            return subprocess.CompletedProcess(args, 0, '', '')
        state['version'] += 1
        entry = dict(paper_id='p%d' % state['version'], name=state['last'], version=1, title='', pages=3, bytes=1,
                     uploaded_at='2026-10-15T12:00:00+08:00', duplicate=False)
        return subprocess.CompletedProcess(args, 0, json.dumps(entry), '')
    monkeypatch.setattr(qp.subprocess, 'run', run)
    folder = tmp_path / '论文 待读'
    folder.mkdir()
    for name, src in (('甲 Amihud 2002.pdf', 'amihud2002.pdf'), ('乙 动量.pdf', 'gh4-paper.pdf')):
        shutil.copyfile(FIX / src, folder / name)
    return calls, state, folder


def scps(calls):
    return [Path(c[-2]).name for c in calls if 'scp' in c[0]]


def test_a_folder_and_a_wildcard_upload_every_pdf_and_say_which_one_is_latest(client, capsys):
    calls, state, folder = client
    qp.main(['upload', str(folder)])
    out = capsys.readouterr().out
    assert scps(calls) == ['乙 动量.pdf', '甲 Amihud 2002.pdf'] and '[2/2]' in out and '成功 2 篇，失败 0 篇' in out
    assert '指的是：甲 Amihud 2002.pdf' in out and '/hy-tmp' in out
    calls.clear()
    qp.main(['upload', str(folder / '*.pdf')])
    assert len(scps(calls)) == 2


def test_one_bad_file_stops_the_batch_before_any_network(client, tmp_path):
    calls, state, folder = client
    bad = tmp_path / 'notes.pdf'
    bad.write_bytes(b'not a pdf')
    with pytest.raises(SystemExit) as exc:
        qp.main(['upload', str(folder / '甲 Amihud 2002.pdf'), str(bad)])
    assert '没有上传任何文件' in str(exc.value) and 'notes.pdf' in str(exc.value) and calls == []


def test_identical_files_in_one_batch_are_sent_once_and_a_failure_is_reported(client, capsys):
    calls, state, folder = client
    shutil.copyfile(folder / '乙 动量.pdf', folder / '丙 副本.pdf')
    state['fail'].add('甲 Amihud 2002.pdf')
    with pytest.raises(SystemExit):
        qp.main(['upload', str(folder)])
    out = capsys.readouterr().out
    assert '跳过：' in out and '内容相同' in out
    assert '成功 1 篇，失败 1 篇' in out and '服务器没有登记' in out
    assert sum('paper-import' in c[-1] for c in calls if 'scp' not in c[0]) == 1        # nothing registered for the failure


def test_a_reupload_becomes_what_the_user_just_uploaded(tmp_path):
    """Before 2026-10-15 a duplicate kept its old time, so '研究我刚上传的论文' named a different paper."""
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')

    def stage(src):
        target = lib.root / 'incoming' / ('up-' + os.urandom(4).hex())
        shutil.copyfile(FIX / src, target)
        return target
    a = lib.import_pdf(stage('amihud2002.pdf'), 'Amihud 2002.pdf')
    time.sleep(1.1)
    b = lib.import_pdf(stage('gh4-paper.pdf'), 'GH 2004.pdf')
    assert lib.resolve('刚上传的')['paper']['sha256'] == b['sha256']
    time.sleep(1.1)
    again = lib.import_pdf(stage('amihud2002.pdf'), 'Amihud copy.pdf')
    assert again['duplicate'] is True and len(lib.entries()) == 2
    assert lib.resolve('研究我刚上传的论文')['paper']['sha256'] == a['sha256']
    first = next(r for r in lib.entries() if r['sha256'] == a['sha256'])
    assert first['uploaded_at'] == a['uploaded_at'] and first['last_uploaded_at'] > b['uploaded_at']
