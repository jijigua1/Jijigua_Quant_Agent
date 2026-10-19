"""Server-side PDF upload over an existing FinalShell ZMODEM session.

The root operator receives files into a private temporary directory, then hands
each checked PDF to the existing privilege-dropping quant-agent paper importer.
No listener, client-side Python, model call or change to the Agent is needed.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata

HERE = Path(__file__).resolve().parent
HOST = HERE / 'host.json'
LAUNCHER = HERE / 'launcher_v1.py'
MAX_BYTES = 50 * 1024 * 1024
MAX_FILES = 30
RECEIVE_SECONDS = 600


def private_staging(host=HOST):
    if os.geteuid() != 0:
        raise SystemExit('请使用你平时登录服务器的 root 终端运行。')
    st = host.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise SystemExit('Agent 主机配置不是 root 管理的普通文件。')
    config = json.loads(host.read_text(encoding='utf-8'))
    if Path(config['root']).resolve() != host.parent.parent.resolve() or Path(config['runner']).resolve() != (host.parent / 'run_v1.py').resolve():
        raise SystemExit('上传与 Agent 不属于同一部署配置。')
    if Path(config['research_config']).resolve() != (host.parent.parent / 'config/research.json').resolve():
        raise SystemExit('上传与 Agent 研究配置不属于同一部署。')
    directory = Path(config['paper_staging'])
    st = directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o077:
        raise SystemExit('论文接收目录必须为 root 私有目录。')
    return directory


def _receive_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))


def receive_into(directory):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit('请在支持 ZMODEM 的 SSH 终端运行，例如 Windows/Mac 的 FinalShell。')
    receiver = shutil.which('rz')
    if not receiver:
        raise SystemExit('服务器缺少 rz（lrzsz），请联系管理员。')
    import termios
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    print('请在 FinalShell 弹出的窗口选择 PDF（可多选，每篇不超过 50 MB）。', flush=True)
    print('Word 请先另存为 PDF；取消选择后不会登记论文。', flush=True)
    try:
        # Restricted mode rejects remote commands and unsafe destination paths.
        result = subprocess.run([receiver, '--binary', '--restricted', '--protect', '--escape'],
                                cwd=directory, timeout=RECEIVE_SECONDS,
                                preexec_fn=_receive_limits)
    except subprocess.TimeoutExpired:
        raise SystemExit('上传等待超时（10 分钟），本次文件未导入论文库。') from None
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, previous)
    if result.returncode:
        raise SystemExit('上传已取消或传输失败，本次文件未导入论文库。')


def check_received(directory):
    paths = sorted(directory.iterdir())
    if not paths:
        return []
    if len(paths) > MAX_FILES:
        raise SystemExit(f'一次最多上传 {MAX_FILES} 篇，本批没有导入。')
    checked = []
    seen = set()
    for path in paths:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.geteuid():
            raise SystemExit('接收内容包含非普通文件，本批没有导入。')
        if path.suffix.lower() != '.pdf':
            raise SystemExit(f'{path.name}：目前只支持 PDF；Word 请先另存为 PDF。本批没有导入。')
        if not 0 < st.st_size <= MAX_BYTES:
            raise SystemExit(f'{path.name}：文件为空或超过 50 MB，本批没有导入。')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            if b'%PDF-' not in stream.read(1024):
                raise SystemExit(f'{path.name}：内容不是 PDF，本批没有导入。')
            stream.seek(0)
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        sha = digest.hexdigest()
        if sha not in seen:
            checked.append((path, sha))
            seen.add(sha)
    return checked


def import_received(path, sha, staging, launcher=LAUNCHER):
    name = unicodedata.normalize('NFC', path.name)
    name = ''.join(c for c in name if unicodedata.category(c)[0] != 'C')[:160]
    encoded = base64.urlsafe_b64encode(name.encode('utf-8')).decode('ascii').rstrip('=')
    staged = staging / f'up-{sha[:16]}-{secrets.token_hex(4)}.pdf'
    os.replace(path, staged)
    os.chmod(staged, 0o600)
    try:
        response = subprocess.run([sys.executable, '-I', str(launcher), 'paper-import', staged.name, encoded, sha],
                                  capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=120)
        if response.returncode:
            raise SystemExit('论文导入失败：' + (response.stderr or response.stdout).strip()[-400:])
        try:
            entry = json.loads(response.stdout.strip().splitlines()[-1])
            if not isinstance(entry, dict) or not all(k in entry for k in ('name', 'version', 'pages')):
                raise ValueError('missing importer fields')
        except (ValueError, IndexError):
            raise SystemExit('导入器返回异常，无法确认登记状态，请用 quant-paper list 核对。') from None
        return entry
    except subprocess.TimeoutExpired:
        raise SystemExit('导入器响应超时，登记状态尚未确认，请用 quant-paper list 核对。') from None
    finally:
        # Only the exact file generated by this invocation can be removed here.
        staged.unlink(missing_ok=True)


def upload():
    staging = private_staging()
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='terminal-', dir=staging) as tmp:
        directory = Path(tmp)
        receive_into(directory)
        checked = check_received(directory)  # Validate the entire batch before importing anything.
        if not checked:
            print('没有收到文件，没有导入论文。')
            return 0
        failed = 0
        for path, sha in checked:
            try:
                entry = import_received(path, sha, staging)
            except SystemExit as exc:
                failed += 1
                print(f'{path.name}：{exc}', file=sys.stderr)
                continue
            label = '已在论文库中，未重复保存' if entry.get('duplicate') else '已上传并登记'
            print(f"{label}：{entry['name']}（第 {entry['version']} 版，{entry['pages']} 页）。")
            print(f"进入 quant-agent chat 后说：研究《{entry['name']}》这篇论文。")
        print(f'本批：登记成功 {len(checked) - failed} 篇，失败或状态待确认 {failed} 篇。')
        print('请保留本机原件；服务器 /hy-tmp 不作为永久备份。')
        return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='在服务器 FinalShell 终端上传 PDF 并自动登记到 Agent 论文库。')
    parser.add_argument('command', nargs='?', choices=['upload', 'list', 'help'], default='help')
    args = parser.parse_args(argv)
    if args.command == 'upload':
        try:
            return upload()
        except KeyboardInterrupt:
            print('\n已中断上传；请用 quant-paper list 核对已经登记的论文。', file=sys.stderr)
            return 130
    if args.command == 'list':
        return subprocess.call([sys.executable, '-I', str(LAUNCHER), 'paper-list'])
    parser.print_help()
    print('Windows 和 Mac 均可使用 FinalShell 登录后运行：quant-paper upload')
    print('普通 Terminal / PowerShell 的 ssh 不自带文件选择功能，需支持 ZMODEM 的终端。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
