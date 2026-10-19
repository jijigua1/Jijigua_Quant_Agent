"""quant-paper: upload a local PDF to the research server and register it for `quant-agent chat`.

Windows-first, standard library only; uses the system OpenSSH client (ssh/scp). No GUI, no daemon, no stored passwords.
Host keys are verified (StrictHostKeyChecking=yes, BatchMode=yes): a new server must be confirmed once by the user.

  quant-paper setup --host your-ssh-host.example --port 27182 --user root --identity C:\\Users\\me\\.ssh\\id_ed25519
  quant-paper upload "D:\\Papers\\Amihud_2002.pdf"
  quant-paper list
  quant-paper status
  quant-paper help
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

MAX_BYTES = 50 * 1024 ** 2
VERSION = '1.0.0-beta'
DEFAULTS = dict(host='', port=22, user='root', identity='', remote_command='quant-agent',
                staging_dir='/var/lib/jijigua-quant-agent/paper_staging', timeout=180)


def config_path():
    base = os.environ.get('APPDATA') or str(Path.home() / '.config')
    return Path(base) / 'quant-paper' / 'config.json'


def load_config():
    path = config_path()
    if not path.exists():
        raise SystemExit('尚未配置服务器。请先运行：quant-paper setup --host <主机> --port <端口> --user <用户> --identity <私钥路径>')
    return DEFAULTS | json.loads(path.read_text(encoding='utf-8'))


def tool(name):
    found = shutil.which(name)
    if not found:
        raise SystemExit(f'找不到 {name}。请启用 Windows 自带的 OpenSSH 客户端（设置 → 可选功能 → OpenSSH 客户端）。')
    return found


def ssh_base(c, program='ssh'):
    port_flag = '-P' if program == 'scp' else '-p'
    args = [tool(program), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', port_flag, str(c['port'])]
    if c.get('identity'):
        args += ['-i', c['identity']]
    return args


def explain_ssh_error(stderr):
    text = (stderr or '').strip()
    if 'Host key verification failed' in text or 'No ECDSA host key' in text or 'host key' in text.lower():
        return ('服务器主机密钥未被信任或已变化。请先在 PowerShell 手动运行一次 ssh 连接并核对指纹，确认后再上传：\n'
                '  ssh -p <端口> <用户>@<主机>\n若密钥意外变化，请先联系服务器管理员，不要直接覆盖。')
    if 'Permission denied' in text:
        return 'SSH 认证失败：请检查 --identity 指定的私钥及服务器授权。'
    if 'timed out' in text or 'Could not resolve' in text or 'Connection refused' in text:
        return '无法连接服务器：请检查主机、端口和网络。'
    return 'SSH 失败：' + text.splitlines()[-1][:300] if text else 'SSH 失败（无错误输出）。'


def remote(c, args, timeout=None):
    command = ' '.join([c['remote_command']] + args)
    p = subprocess.run(ssh_base(c) + [f"{c['user']}@{c['host']}", command], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout or c['timeout'])
    if p.returncode:
        raise SystemExit(explain_ssh_error(p.stderr) if p.returncode == 255 else '服务器拒绝：' + (p.stderr or p.stdout).strip()[-400:])
    return p.stdout


def check_pdf(path):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f'文件不存在：{path}')
    if not path.is_file():
        raise SystemExit(f'不是文件：{path}')
    if path.suffix.lower() != '.pdf':
        raise SystemExit('只支持 PDF 文件（扩展名 .pdf）。')
    size = path.stat().st_size
    if size == 0:
        raise SystemExit('文件为空。')
    if size > MAX_BYTES:
        raise SystemExit(f'文件过大（{size / 1024 ** 2:.1f} MB），上限 50 MB。')
    with path.open('rb') as fh:
        if b'%PDF-' not in fh.read(1024):
            raise SystemExit('文件内容不是 PDF（缺少 %PDF- 文件头）。')
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return path, size, h.hexdigest()


def cmd_setup(a):
    c = DEFAULTS.copy()
    path = config_path()
    if path.exists():
        c |= json.loads(path.read_text(encoding='utf-8'))
    for key in ('host', 'port', 'user', 'identity', 'remote_command', 'staging_dir'):
        value = getattr(a, key)
        if value not in (None, ''):
            c[key] = value
    if not c['host']:
        raise SystemExit('需要 --host。')
    if c['identity'] and not Path(c['identity']).is_file():
        raise SystemExit(f"私钥文件不存在：{c['identity']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'已保存配置：{path}（不保存密码或密钥内容）')
    p = subprocess.run(ssh_base(c) + [f"{c['user']}@{c['host']}", 'true'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    print('连接检查：成功。' if p.returncode == 0 else '连接检查未通过：' + explain_ssh_error(p.stderr))


def cmd_upload(a):
    c = load_config()
    path, size, sha = check_pdf(a.pdf)
    name = path.name
    staged = f"up-{sha[:16]}-{os.urandom(4).hex()}.pdf"
    print(f'正在上传：{name}（{size / 1024:.0f} KB，SHA-256 {sha[:12]}…）')
    target = f"{c['user']}@{c['host']}:{c['staging_dir']}/{staged}"
    p = subprocess.run(ssh_base(c, 'scp') + [str(path), target], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=c['timeout'])
    if p.returncode:
        raise SystemExit('上传失败，服务器没有登记任何内容。' + explain_ssh_error(p.stderr))
    encoded = base64.urlsafe_b64encode(name.encode('utf-8')).decode().rstrip('=')
    out = remote(c, ['paper-import', staged, encoded, sha])
    try:
        entry = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SystemExit('服务器返回无法解析：' + out[-300:])
    if entry.get('duplicate'):
        print(f"内容与已登记论文相同，未重复保存：{entry['name']}（第{entry['version']}版）。")
    else:
        print(f"已上传并登记：{entry['name']}（第{entry['version']}版，{entry['pages']}页）。")
    print('在服务器运行 quant-agent chat 后说：“研究我刚上传的论文。”')


def cmd_list(a):
    c = load_config()
    rows = json.loads(remote(c, ['paper-list']).strip().splitlines()[-1] or '[]')
    if not rows:
        print('尚未上传论文。')
        return
    for r in sorted(rows, key=lambda r: r['uploaded_at']):
        title = (' · ' + r['title'][:60]) if r.get('title') else ''
        print(f"{r['uploaded_at'][:16].replace('T', ' ')}  {r['name']}（第{r['version']}版，{r['pages']}页）{title}")


def cmd_status(a):
    c = load_config()
    print(f"服务器：{c['user']}@{c['host']}:{c['port']}；私钥：{c['identity'] or 'ssh 默认'}；配置：{config_path()}")
    rows = json.loads(remote(c, ['paper-list']).strip().splitlines()[-1] or '[]')
    print(f'连接正常；已登记论文 {len(rows)} 篇。')


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(prog='quant-paper', description='上传论文 PDF 并登记给服务器上的 quant-agent chat 使用')
    sub = p.add_subparsers(dest='command')
    s = sub.add_parser('setup', help='保存服务器连接配置并测试连接')
    s.add_argument('--host'); s.add_argument('--port', type=int); s.add_argument('--user'); s.add_argument('--identity')
    s.add_argument('--remote-command', dest='remote_command'); s.add_argument('--staging-dir', dest='staging_dir')
    u = sub.add_parser('upload', help='上传一个本地 PDF')
    u.add_argument('pdf')
    sub.add_parser('list', help='列出已上传论文')
    sub.add_parser('status', help='检查连接与论文数量')
    sub.add_parser('help', help='显示帮助')
    a = p.parse_args(argv)
    if a.command in (None, 'help'):
        print(__doc__)
        return 0
    try:
        {'setup': cmd_setup, 'upload': cmd_upload, 'list': cmd_list, 'status': cmd_status}[a.command](a)
    except subprocess.TimeoutExpired:
        raise SystemExit('连接超时：服务器没有在限定时间内响应，未登记任何内容。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
