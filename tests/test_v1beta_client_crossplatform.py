"""Cross-platform local client (quant-paper / quant-agent, 2026-10-15): macOS-specific path rules, the chat/report
forwarding, version compatibility and the macOS installer. Fake ssh/scp; no server is contacted. Tests that need a POSIX
shell run on Linux in CI -- that is POSIX evidence, not a native macOS acceptance."""
import ast
import base64
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools' / 'quant_paper'
sys.path.insert(0, str(TOOLS))
import quant_paper as qp  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(qp, 'expand'), reason='Historical client protocol is absent from deployed ver1.0; formal client tested in test_portable_paper_upload.py')

FIX = Path(__file__).parent / 'fixtures_v1beta'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(qp, 'tool', lambda name: '/usr/bin/' + name)
    key = tmp_path / 'id_test'
    key.write_text('not a real key')
    monkeypatch.setattr(qp.subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 0, '', ''))
    qp.main(['setup', '--host', 'example.test', '--port', '27182', '--user', 'root', '--identity', str(key),
             '--research-root', '/var/lib/jijigua-quant-agent/v1rc/research_runs'])
    calls = []
    return calls, monkeypatch, tmp_path


def fake(calls, monkeypatch, answer):
    def run(args, **kw):
        calls.append(args)
        return answer(args)
    monkeypatch.setattr(qp.subprocess, 'run', run)


def test_the_client_stays_python39_compatible():
    """macOS ships python3 3.9 with the Apple command line tools."""
    for name in ('quant_paper.py', 'quant_agent.py'):
        ast.parse((TOOLS / name).read_text(encoding='utf-8'), feature_version=(3, 9))


def test_tilde_quoted_wildcards_hidden_appledouble_files_and_nfd_names(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    papers = home / 'Documents' / '论文 资料'
    papers.mkdir(parents=True)
    nfd = unicodedata.normalize('NFD', 'ドキュメント 动量因子.pdf')        # how macOS often hands out names
    shutil.copyfile(FIX / 'amihud2002.pdf', papers / nfd)
    shutil.copyfile(FIX / 'gh4-paper.pdf', papers / 'b.pdf')
    (papers / '._b.pdf').write_bytes(b'\x00\x05\x16\x07 AppleDouble')     # resource fork companion, not a PDF
    (papers / '.hidden.pdf').write_bytes(b'%PDF-1.4 hidden')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    folder = qp.expand(['~/Documents/论文 资料'])                            # a quoted '~' is not expanded by the shell
    star = qp.expand(['~/Documents/论文 资料/*.pdf'])                        # a quoted wildcard is expanded by the client
    assert [p.name for p in folder] == [p.name for p in star] and len(folder) == 2
    assert not any(p.name.startswith('.') for p in folder)
    named = next(p for p in folder if p.name != 'b.pdf')
    assert qp.display_name(named) == unicodedata.normalize('NFC', nfd) != nfd


def test_the_server_receives_the_nfc_name_and_an_old_server_is_named(client, capsys):
    calls, monkeypatch, tmp = client
    pdf = tmp / unicodedata.normalize('NFD', '动量 因子.pdf')
    shutil.copyfile(FIX / 'amihud2002.pdf', pdf)
    old = dict(paper_id='x', name='动量 因子.pdf', version=1, title='', pages=26, bytes=1, uploaded_at='2026-10-15T12:00:00+08:00',
               duplicate=True)                                                # no "protocol": a server before 2026-10-15
    fake(calls, monkeypatch, lambda a: subprocess.CompletedProcess(a, 0, '' if '/usr/bin/scp' == a[0] else json.dumps(old), ''))
    qp.main(['upload', str(pdf)])
    command = calls[1][-1].split()
    assert base64.urlsafe_b64decode(command[3] + '=' * (-len(command[3]) % 4)).decode('utf-8') == unicodedata.normalize('NFC', '动量 因子.pdf')
    out = capsys.readouterr().out
    assert '服务器端版本较旧' in out and '已记为最近上传' not in out
    calls.clear()
    fake(calls, monkeypatch, lambda a: subprocess.CompletedProcess(a, 0, '' if '/usr/bin/scp' == a[0] else json.dumps(
        dict(old, protocol=qp.IMPORT_PROTOCOL)), ''))
    qp.main(['upload', str(pdf)])
    out = capsys.readouterr().out
    assert '已记为最近上传' in out and '服务器端版本较旧' not in out


def test_chat_checks_the_connection_then_opens_one_tty_session_without_the_key(client, monkeypatch):
    calls, monkeypatch, tmp = client
    fake(calls, monkeypatch, lambda a: subprocess.CompletedProcess(a, 0, '', ''))
    interactive = []
    monkeypatch.setattr(qp.subprocess, 'call', lambda args: (interactive.append(args), 0)[1])
    monkeypatch.setenv('QRA_DEEPSEEK_API_KEY', 'synthetic-not-a-key')
    assert qp.agent_main(['chat', '--resume', 'a1b2c3']) == 0
    assert calls[0][-1] == 'true'                                             # captured preflight first
    args = interactive[0]
    assert '-t' in args and 'StrictHostKeyChecking=yes' in args and args[-1] == 'quant-agent chat --resume a1b2c3'
    assert not any('sk-' in x for x in args)
    with pytest.raises(SystemExit):
        qp.agent_main(['chat', '--resume', 'x; rm -rf /'])                    # nothing but plain tokens reaches the server shell
    monkeypatch.setattr(qp.subprocess, 'call', lambda args: 255)
    with pytest.raises(SystemExit) as exc:
        qp.agent_main(['chat'])
    assert '--resume' in str(exc.value)


def test_a_failed_preflight_explains_itself_in_chinese(client, monkeypatch):
    calls, monkeypatch, tmp = client
    fake(calls, monkeypatch, lambda a: subprocess.CompletedProcess(a, 255, '', 'root@example.test: Permission denied (publickey).'))
    monkeypatch.setattr(qp.subprocess, 'call', lambda args: pytest.fail('no interactive session after a failed check'))
    with pytest.raises(SystemExit) as exc:
        qp.agent_main(['chat'])
    assert 'SSH 认证失败' in str(exc.value)
    fake(calls, monkeypatch, lambda a: subprocess.CompletedProcess(a, 255, '', 'Host key verification failed.'))
    with pytest.raises(SystemExit) as exc:
        qp.agent_main(['chat'])
    assert '主机密钥' in str(exc.value) and '不要直接覆盖' in str(exc.value)


def test_report_download_stays_inside_the_research_root_and_picks_the_newest_success(client, monkeypatch):
    calls, monkeypatch, tmp = client
    monkeypatch.setattr(qp, 'local_reports_dir', lambda: tmp / 'Downloads' / 'QuantAgentReports')
    root = '/var/lib/jijigua-quant-agent/v1rc/research_runs'
    for bad in ('/etc/passwd', root + '/../secret.html', '/var/lib/jijigua-quant-agent/v1beta/research_runs/x/reports/report.html'):
        with pytest.raises(SystemExit):
            qp.agent_main(['report', bad, '--no-open'])
    versions = [dict(revision=1, html=root + '/2026-10-14/20-19-52_m/reports/report.html'),
                dict(revision=2, rolling_status='COMPLETED', html=root + '/2026-10-14/20-21-04_report_revision_2/reports/report.html'),
                dict(revision=3, rolling_status='NOT_EVALUATED', html=root + '/2026-10-15/09-00-00_report_revision_3/reports/report.html')]

    def scp(a):
        source, local = a[-2], Path(a[-1])
        local.write_text(json.dumps(versions) if source.endswith('report_versions.json') else '<html>' + source + '</html>', encoding='utf-8')
        return subprocess.CompletedProcess(a, 0, '', '')
    fake(calls, monkeypatch, scp)
    local = qp.agent_main(['report', root + '/2026-10-14/20-19-52_m', '--no-open'])
    assert local == 0
    got = list((tmp / 'Downloads' / 'QuantAgentReports').glob('*.html'))
    assert [p.name for p in got] == ['20-21-04_report_revision_2__report.html']   # revision 2, not the failed revision 3
    assert 'StrictHostKeyChecking=yes' in calls[0]


def test_setup_refuses_server_paths_rewritten_by_git_bash(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(qp, 'tool', lambda name: '/usr/bin/' + name)
    with pytest.raises(SystemExit) as exc:
        qp.main(['setup', '--host', 'h', '--staging-dir', 'C:/Program Files/Git/var/lib/jijigua-quant-agent/v1rc_staging'])
    assert '被改写' in str(exc.value)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX file modes')
def test_the_config_is_private_on_posix(client):
    calls, monkeypatch, tmp = client
    path = qp.config_path()
    assert path.stat().st_mode & 0o777 == 0o600 and path.parent.stat().st_mode & 0o777 == 0o700


def test_help_matches_the_platform():
    if os.name == 'nt':
        assert 'PowerShell' in qp.HELP and 'D:\\' in qp.HELP
    else:
        assert 'PowerShell' not in qp.HELP and 'D:\\' not in qp.HELP and '.exe' not in qp.HELP and '~/Documents' in qp.HELP


@pytest.mark.skipif(os.name == 'nt' or not shutil.which('sh'), reason='POSIX sh installer')
def test_the_macos_installer_writes_working_wrappers(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    env = {'HOME': str(home), 'PATH': os.environ['PATH'], 'APPDATA': ''}
    p = subprocess.run(['sh', str(TOOLS / 'install_macos.sh'), '--add-path'], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    for name in ('quant-paper', 'quant-agent'):
        out = subprocess.run([str(home / '.local/bin' / name), 'version'], capture_output=True, text=True, env=env)
        assert out.returncode == 0 and qp.VERSION in out.stdout
    again = subprocess.run(['sh', str(TOOLS / 'install_macos.sh'), '--add-path'], capture_output=True, text=True, env=env)
    assert again.returncode == 0 and (home / '.zshrc').read_text().count('.local/bin') == 1     # idempotent
