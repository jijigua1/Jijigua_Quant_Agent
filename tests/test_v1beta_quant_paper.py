"""Windows upload client (quant-paper) with a fake ssh/scp: validation, naming, error messages, no registration on failure."""
import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'quant_paper'))
import quant_paper as qp  # noqa: E402

FIX = Path(__file__).parent / 'fixtures_v1beta'


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(qp.shutil, 'which', lambda name: '/usr/bin/' + name)
    key = tmp_path / 'id_test'
    key.write_text('not a real key')
    calls = []

    def run(args, **kw):
        calls.append(args)
        if args[-1] == 'true':
            return subprocess.CompletedProcess(args, 0, '', '')
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(qp.subprocess, 'run', run)
    qp.main(['setup', '--host', 'example.test', '--port', '2222', '--user', 'root', '--identity', str(key)])
    calls.clear()
    return calls, monkeypatch, tmp_path


def test_setup_stores_no_secret_and_checks_host_keys(configured):
    calls, monkeypatch, tmp = configured
    cfg = json.loads((tmp / 'appdata/quant-paper/config.json').read_text(encoding='utf-8'))
    assert cfg['host'] == 'example.test' and 'password' not in json.dumps(cfg) and 'not a real key' not in json.dumps(cfg)
    assert 'StrictHostKeyChecking=yes' in qp.ssh_base(cfg) and 'BatchMode=yes' in qp.ssh_base(cfg)


def test_upload_sends_ascii_staging_name_and_utf8_name(configured, tmp_path):
    calls, monkeypatch, tmp = configured
    pdf = tmp_path / '论文 Amihud 2002 (final).pdf'
    pdf.write_bytes((FIX / 'amihud2002.pdf').read_bytes())
    answers = iter([subprocess.CompletedProcess([], 0, '', ''),
                    subprocess.CompletedProcess([], 0, json.dumps(dict(paper_id='x', name=pdf.name, version=1, title='t', pages=26,
                                                                       bytes=1, uploaded_at='2026-10-13T00:00:00+08:00', duplicate=False)), '')])
    monkeypatch.setattr(qp.subprocess, 'run', lambda args, **kw: (calls.append(args), next(answers))[1])
    qp.main(['upload', str(pdf)])
    scp, ssh = calls
    remote_name = scp[-1].rsplit('/', 1)[1]
    assert remote_name.isascii() and remote_name.startswith('up-') and ' ' not in remote_name
    command = ssh[-1].split()
    assert command[:2] == ['quant-agent', 'paper-import'] and command[2] == remote_name
    assert base64.urlsafe_b64decode(command[3] + '=' * (-len(command[3]) % 4)).decode('utf-8') == pdf.name
    assert len(command[4]) == 64


@pytest.mark.parametrize('content,suffix,message', [(None, '.pdf', '不存在'), (b'hello', '.txt', '只支持 PDF'), (b'', '.pdf', '为空'),
                                                    (b'not a pdf at all', '.pdf', '不是 PDF')])
def test_local_validation_refuses_before_any_network(configured, tmp_path, content, suffix, message):
    calls, monkeypatch, tmp = configured
    path = tmp_path / ('x' + suffix)
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(SystemExit) as exc:
        qp.main(['upload', str(path)])
    assert message in str(exc.value) and calls == []


def test_failed_scp_never_registers(configured, tmp_path):
    calls, monkeypatch, tmp = configured
    pdf = tmp_path / 'a.pdf'
    pdf.write_bytes((FIX / 'gh4-paper.pdf').read_bytes())
    monkeypatch.setattr(qp.subprocess, 'run', lambda args, **kw: (calls.append(args), subprocess.CompletedProcess(args, 1, '', 'lost connection'))[1])
    with pytest.raises(SystemExit) as exc:
        qp.main(['upload', str(pdf)])
    assert '没有登记' in str(exc.value) and len(calls) == 1       # no paper-import call after a failed copy


def test_host_key_problem_is_explained():
    assert '主机密钥' in qp.explain_ssh_error('Host key verification failed.')
    assert '认证失败' in qp.explain_ssh_error('root@x: Permission denied (publickey).')
