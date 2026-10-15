"""quant-paper / quant-agent: the local client of the shared research server (Windows 10/11 and macOS).

One core for both platforms; only the entry wrappers differ (quant-paper.cmd / quant-agent.cmd on Windows, the wrappers
written by install_macos.sh on macOS). Standard library only; the system OpenSSH client does the transport. No GUI, no
daemon, no stored passwords or keys. Host keys are always verified (StrictHostKeyChecking=yes): a new server must be
confirmed once by the user in a terminal. All research runs on the server; the client only uploads, starts and shows.

  quant-paper setup --host <host> --port <port> --user <user> --identity <private key>
  quant-paper upload <file | folder | wildcard> ...      quant-paper list | status | help
  quant-agent chat [--resume <session id>]               quant-agent session | history | status [<id>]
  quant-agent report <server study or report path>       quant-agent help
"""
import argparse
import base64
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import unicodedata

IS_WINDOWS = os.name == 'nt'
VERSION = '1.1.0'
IMPORT_PROTOCOL = 'paper-import/2'        # the server reports it; older servers do not refresh a re-upload's time
MAX_BYTES = 50 * 1024 ** 2
DEFAULTS = dict(host='', port=22, user='root', identity='', remote_command='quant-agent',
                staging_dir='/srv/jijigua-quant-agent/paper_staging', research_root='/srv/jijigua-quant-agent/v1beta/research_runs',
                timeout=180)
PERSISTENCE = '提示：服务器论文库位于 /hy-tmp 数据盘，实例释放、迁移或数据盘重置后不保证保留；请保留本地原件。'
TERMINAL = 'PowerShell' if IS_WINDOWS else '终端（Terminal / iTerm2）'

if IS_WINDOWS:
    EXAMPLES = ('  quant-paper upload "D:\\Papers\\论文 名称.pdf"          上传一篇 PDF（路径含空格或中文时请加英文双引号）\n'
                '  quant-paper upload "D:\\Papers\\a.pdf" "D:\\Papers\\b.pdf"   一次上传多篇\n'
                '  quant-paper upload "D:\\Papers"                     上传文件夹里的全部 PDF（不含子文件夹）\n'
                '  quant-paper upload "D:\\Papers\\*.pdf"              通配符（由工具展开）')
else:
    EXAMPLES = ('  quant-paper upload ~/Documents/Papers/paper.pdf          上传一篇 PDF\n'
                '  quant-paper upload "$HOME/Documents/论文资料/动量因子.pdf"   路径含空格或中文时加英文双引号（引号里用 $HOME 或 ~ 均可）\n'
                '  quant-paper upload ~/Documents/Papers/*.pdf              一次上传多篇（zsh 展开通配符）\n'
                '  quant-paper upload ~/Documents/Papers/                   上传文件夹里的全部 PDF（不含子文件夹）')

HELP = f"""quant-paper：把本地论文 PDF 上传到研究服务器，供 quant-agent chat 研究。（客户端 {VERSION}）

常用命令（在{TERMINAL}中输入）：
{EXAMPLES}
  quant-paper list                     列出已上传的论文（标出“刚上传的论文”指哪一篇）
  quant-paper status                   检查服务器连接和已登记论文数量
  quant-paper help                     显示本帮助

首次使用先保存服务器连接（只需一次，不保存密码）：
  quant-paper setup --host <主机> --port <端口> --user <用户> --identity <私钥路径>

说明：
  · 按文件内容（SHA-256）判断重复：重复上传不占空间，并记为最近上传；同名但内容不同登记为新版本。
  · 主机密钥必须先被信任（首次请手动运行一次 ssh 并核对指纹），工具不会自动接受未知或变化的主机密钥。
  · 上传后运行 quant-agent chat，说“研究我刚上传的论文。”即可；一次上传多篇时，它指最后登记的一篇，
    其余几篇请说出文件名或标题里的词（例如“研究 Amihud 那篇论文”）。
  · 论文库在服务器的 /hy-tmp 数据盘上：实例释放、迁移或数据盘重置后不保证保留，请始终保留本地原件。"""

AGENT_HELP = f"""quant-agent（本地客户端 {VERSION}）：从本机连接研究服务器上的 Quant-Agent。计算和 2026 受控评价都在服务器完成。

  quant-agent chat                      开始新的研究会话（服务器会提示输入 DeepSeek Key，输入不回显、不保存）
  quant-agent chat --resume <会话ID>     恢复已有会话（会话ID可在会话中输入 /session 查看）
  quant-agent session <会话ID>           查看会话信息（只读，不需要 Key；会话ID在 chat 开始时显示）
  quant-agent history <会话ID>           查看某个会话的对话记录（只读）
  quant-agent session_tasks <会话ID>     查看该会话的研究任务与进度（只读）
  quant-agent status <任务ID>            查看某个研究任务的状态（只读）
  quant-agent report <研究目录或报告路径>  把服务器上的 HTML 报告下载到本机并打开（研究目录会自动选最新一版）
  quant-agent help                      显示本帮助

连接配置与 quant-paper 共用（先运行一次 quant-paper setup）。退出会话：在会话中输入 /exit 或按 Ctrl+D。"""


# ------------------------------------------------------------------------------------------------ configuration
def config_path():
    base = os.environ.get('APPDATA') or str(Path.home() / '.config')
    return Path(base) / 'quant-paper' / 'config.json'


def load_config():
    path = config_path()
    if not path.exists():
        raise SystemExit('尚未配置服务器。请先运行：quant-paper setup --host <主机> --port <端口> --user <用户> --identity <私钥路径>')
    return {**DEFAULTS, **json.loads(path.read_text(encoding='utf-8'))}


def save_config(c):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
    if not IS_WINDOWS:
        os.chmod(path.parent, 0o700)
        os.chmod(path, 0o600)
    return path


def tool(name):
    # Windows' own OpenSSH first: a Git-Bash/MSYS ssh/scp on PATH rewrites '/hy-tmp/...' into 'C:/Program Files/Git/...'
    # (seen 2026-10-15 when the client was started from Git Bash). macOS and Linux use the system OpenSSH on PATH.
    native = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'OpenSSH' / (name + '.exe')
    if IS_WINDOWS and native.is_file():
        return str(native)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f'找不到 {name}。' + ('请启用 Windows 自带的 OpenSSH 客户端（设置 → 可选功能 → OpenSSH 客户端）。' if IS_WINDOWS
                                             else 'macOS 自带 OpenSSH；请确认 /usr/bin 在 PATH 中（echo $PATH）。'))
    return found


def ssh_base(c, program='ssh'):
    port_flag = '-P' if program == 'scp' else '-p'
    args = [tool(program), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
            '-o', 'ServerAliveInterval=30', port_flag, str(c['port'])]
    if c.get('identity'):
        args += ['-i', os.path.expanduser(c['identity'])]
    return args


def explain_ssh_error(stderr):
    text = (stderr or '').strip()
    if 'Host key verification failed' in text or 'No ECDSA host key' in text or 'host key' in text.lower():
        return (f'服务器主机密钥未被信任或已变化。请先在{TERMINAL}手动运行一次 ssh 连接并核对指纹，确认后再试：\n'
                '  ssh -p <端口> <用户>@<主机>\n若密钥意外变化，请先联系服务器管理员，不要直接覆盖。')
    if 'Permission denied' in text:
        return 'SSH 认证失败：请检查 --identity 指定的私钥及服务器授权' + ('' if IS_WINDOWS else '（私钥权限应为 600：chmod 600 <私钥>）') + '。'
    if 'UNPROTECTED PRIVATE KEY' in text or 'bad permissions' in text:
        return '私钥文件权限过宽，ssh 拒绝使用。请运行：chmod 600 <私钥路径>'
    if 'timed out' in text or 'Could not resolve' in text or 'Connection refused' in text or 'Network is unreachable' in text:
        return '无法连接服务器：请检查主机、端口和网络。'
    if 'Connection reset' in text or 'Broken pipe' in text or 'Connection closed' in text or 'lost connection' in text:
        return '网络连接中断：服务器没有登记本次内容，请稍后重试。'
    return 'SSH 失败：' + text.splitlines()[-1][:300] if text else 'SSH 失败（无错误输出）。'


def remote(c, args, timeout=None):
    command = ' '.join([c['remote_command']] + args)
    p = subprocess.run(ssh_base(c) + [f"{c['user']}@{c['host']}", command], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout or c['timeout'])
    if p.returncode:
        raise SystemExit(explain_ssh_error(p.stderr) if p.returncode == 255 else '服务器拒绝：' + (p.stderr or p.stdout).strip()[-400:])
    return p.stdout


def preflight(c):
    """A captured, non-interactive connection test so an interactive session never fails with a bare exit code."""
    p = subprocess.run(ssh_base(c) + [f"{c['user']}@{c['host']}", 'true'], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=60)
    if p.returncode:
        raise SystemExit('连接检查未通过：' + explain_ssh_error(p.stderr))


# ------------------------------------------------------------------------------------------------ papers
def display_name(path):
    """The name the server will register: NFC (macOS file systems often hand out decomposed NFD names)."""
    return unicodedata.normalize('NFC', Path(path).name)


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
        c.update(json.loads(path.read_text(encoding='utf-8')))
    for key in ('host', 'port', 'user', 'identity', 'remote_command', 'staging_dir', 'research_root'):
        value = getattr(a, key, None)
        if value not in (None, ''):
            c[key] = value
    if not c['host']:
        raise SystemExit('需要 --host。')
    if c['identity']:
        c['identity'] = os.path.expanduser(c['identity'])
        if not Path(c['identity']).is_file():
            raise SystemExit(f"私钥文件不存在：{c['identity']}")
    for key in ('remote_command', 'staging_dir', 'research_root'):
        if re.match(r'^[A-Za-z]:[/\\]', str(c[key])) or 'Program Files' in str(c[key]):
            # a Git-Bash/MSYS shell rewrote a server path into a Windows path before this program saw it
            raise SystemExit(f'{key} 看起来是被改写的 Windows 路径（{c[key]}）。请在 PowerShell 或 macOS 终端中重新运行 setup。')
    path = save_config(c)
    print(f'已保存配置：{path}（不保存密码或密钥内容）')
    p = subprocess.run(ssh_base(c) + [f"{c['user']}@{c['host']}", 'true'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    print('连接检查：成功。' if p.returncode == 0 else '连接检查未通过：' + explain_ssh_error(p.stderr))


def _visible_pdfs(paths):
    # hidden files are skipped: macOS writes '._name.pdf' AppleDouble companions on external drives and network shares
    return sorted(p for p in paths if p.is_file() and p.suffix.lower() == '.pdf' and not p.name.startswith('.'))


def expand(items):
    """Paths as typed: a file, a folder (its *.pdf, not recursive) or a wildcard. '~' is expanded here because a quoted
    '~' is not expanded by the shell, and cmd/PowerShell never expand wildcards."""
    out = []
    for item in items:
        item = os.path.expanduser(item)
        p = Path(item)
        if any(ch in item for ch in '*?[') and not p.exists():
            found = _visible_pdfs(Path(x) for x in glob.glob(item))
            if not found:
                raise SystemExit(f'没有匹配的 PDF 文件：{item}')
            out += found
        elif p.is_dir():
            found = _visible_pdfs(p.iterdir())
            if not found:
                raise SystemExit(f'文件夹里没有 PDF：{p}')
            out += found
        else:
            out.append(p)
    return out


def cmd_upload(a):
    paths = expand(a.pdf)
    if len(paths) == 1:
        checked = [check_pdf(paths[0])]
    else:
        # every file is checked before anything is sent: a typo never leaves a half-uploaded batch
        checked, errors = [], []
        for p in paths:
            try:
                checked.append(check_pdf(p))
            except SystemExit as exc:
                errors.append(f'  {p}：{exc}')
        if errors:
            raise SystemExit('以下文件未通过检查，没有上传任何文件：\n' + '\n'.join(errors))
    seen, unique = {}, []
    for path, size, sha in checked:
        if sha in seen:
            print(f'跳过：{display_name(path)} 与 {display_name(seen[sha])} 内容相同（同一批里只上传一次）。')
            continue
        seen[sha] = path
        unique.append((path, size, sha))
    c = load_config()
    done, failed = [], []
    for i, item in enumerate(unique, 1):
        prefix = f'[{i}/{len(unique)}] ' if len(unique) > 1 else ''
        try:
            done.append(upload_one(c, *item, prefix=prefix))
        except SystemExit as exc:
            if len(unique) == 1:
                raise
            failed.append((item[0], str(exc)))
            print(f'{prefix}失败：{display_name(item[0])}：{exc}')
    if len(unique) > 1:
        print(f'本批共 {len(unique)} 篇：成功 {len(done)} 篇，失败 {len(failed)} 篇。' + ('失败的文件服务器没有登记，可单独重新上传。' if failed else ''))
    if done:
        print(f'运行 quant-agent chat 后说“研究我刚上传的论文。”，指的是：{done[-1]["name"]}（第{done[-1]["version"]}版）。')
        if len(done) > 1:
            print('研究本批其它论文时，请说出文件名或标题里的词，例如“研究 ' + Path(done[0]['name']).stem[:20] + ' 那篇论文”。')
        if any(e.get('duplicate') and e.get('protocol') != IMPORT_PROTOCOL for e in done):
            print('注意：服务器端版本较旧，重复上传不会更新“最近上传”，“研究我刚上传的论文”可能仍指之前的论文。'
                  '请在 chat 中用文件名指定，或请管理员升级服务器端。')
        print(PERSISTENCE)
    if failed:
        raise SystemExit(1)


def upload_one(c, path, size, sha, *, prefix=''):
    name = display_name(path)
    staged = f"up-{sha[:16]}-{os.urandom(4).hex()}.pdf"
    print(f'{prefix}正在上传：{name}（{size / 1024:.0f} KB，SHA-256 {sha[:12]}…）', flush=True)
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
        fresh = '，已记为最近上传' if entry.get('protocol') == IMPORT_PROTOCOL else ''
        print(f"{prefix}内容与已登记论文相同，未重复保存：{entry['name']}（第{entry['version']}版）{fresh}。")
    else:
        print(f"{prefix}已上传并登记：{entry['name']}（第{entry['version']}版，{entry['pages']}页）。")
    return entry


def cmd_list(a):
    c = load_config()
    rows = json.loads(remote(c, ['paper-list']).strip().splitlines()[-1] or '[]')
    if not rows:
        print('尚未上传论文。')
        return
    when = lambda r: r.get('last_uploaded_at') or r['uploaded_at']
    rows = sorted(rows, key=when)
    for r in rows:
        title = (' · ' + r['title'][:60]) if r.get('title') else ''
        mark = '   ← “刚上传的论文”指这篇' if r is rows[-1] else ''
        print(f"{when(r)[:16].replace('T', ' ')}  {r['name']}（第{r['version']}版，{r['pages']}页）{title}{mark}")
    print(PERSISTENCE)


def cmd_status(a):
    c = load_config()
    print(f"客户端 {VERSION}（{'Windows' if IS_WINDOWS else sys.platform}）；服务器：{c['user']}@{c['host']}:{c['port']}；"
          f"私钥：{c['identity'] or 'ssh 默认'}；配置：{config_path()}")
    rows = json.loads(remote(c, ['paper-list']).strip().splitlines()[-1] or '[]')
    print(f'连接正常；已登记论文 {len(rows)} 篇。')
    print(PERSISTENCE)


def _utf8_streams():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


def main(argv=None):
    _utf8_streams()
    p = argparse.ArgumentParser(prog='quant-paper', description='上传论文 PDF 并登记给服务器上的 quant-agent chat 使用')
    sub = p.add_subparsers(dest='command')
    s = sub.add_parser('setup', help='保存服务器连接配置并测试连接')
    s.add_argument('--host'); s.add_argument('--port', type=int); s.add_argument('--user'); s.add_argument('--identity')
    s.add_argument('--remote-command', dest='remote_command'); s.add_argument('--staging-dir', dest='staging_dir')
    s.add_argument('--research-root', dest='research_root')
    u = sub.add_parser('upload', help='上传本地 PDF：一个或多个文件、文件夹或通配符')
    u.add_argument('pdf', nargs='+')
    sub.add_parser('list', help='列出已上传论文')
    sub.add_parser('status', help='检查连接与论文数量')
    sub.add_parser('help', help='显示帮助')
    sub.add_parser('version', help='显示客户端版本')
    a = p.parse_args(argv)
    if a.command in (None, 'help'):
        print(HELP)
        return 0
    if a.command == 'version':
        print(f'quant-paper {VERSION}')
        return 0
    try:
        {'setup': cmd_setup, 'upload': cmd_upload, 'list': cmd_list, 'status': cmd_status}[a.command](a)
    except subprocess.TimeoutExpired:
        raise SystemExit('连接超时：服务器没有在限定时间内响应，未登记任何内容。')
    return 0


# ------------------------------------------------------------------------------------------------ quant-agent
TOKEN = re.compile(r'[A-Za-z0-9_.:-]{1,120}')       # anything forwarded to the server shell is a plain token
REPORT_PATH = re.compile(r'/[A-Za-z0-9_./-]+')


def interactive(c, command):
    """Run one interactive server command over ssh -t. The DeepSeek Key is typed into the server's own prompt through the
    encrypted session: it never appears in a local argument, environment variable or log."""
    preflight(c)
    args = ssh_base(c) + ['-t', f"{c['user']}@{c['host']}", ' '.join([c['remote_command']] + command)]
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)     # Ctrl+C belongs to the server session, not this wrapper
    try:
        code = subprocess.call(args)
    finally:
        signal.signal(signal.SIGINT, previous)
    if code == 255:
        raise SystemExit('SSH 连接中断（退出码 255）。会话在服务器端可能已经结束；可用 quant-agent session <会话ID> 查看，并用 '
                         'quant-agent chat --resume <会话ID> 恢复。')
    return code


def local_reports_dir():
    return Path.home() / 'Downloads' / 'QuantAgentReports'


def open_locally(path):
    if IS_WINDOWS:
        os.startfile(str(path))                              # noqa: the default browser opens the HTML
    elif sys.platform == 'darwin':
        subprocess.call(['open', str(path)])
    else:
        opener = shutil.which('xdg-open')
        if opener:
            subprocess.call([opener, str(path)])


def fetch(c, remote_path, local):
    p = subprocess.run(ssh_base(c, 'scp') + [f"{c['user']}@{c['host']}:{remote_path}", str(local)], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=c['timeout'])
    if p.returncode:
        raise SystemExit('下载失败：' + explain_ssh_error(p.stderr))


def checked_report_path(c, path):
    root = c['research_root'].rstrip('/') + '/'
    if not REPORT_PATH.fullmatch(path) or '..' in path.split('/') or not (path + '/').startswith(root):
        raise SystemExit(f'只能下载服务器研究目录（{root}）里的报告，请复制 Agent 给出的完整路径。')
    return path


def cmd_report(c, path, *, open_it=True):
    path = checked_report_path(c, path.rstrip('/'))
    target = local_reports_dir()
    target.mkdir(parents=True, exist_ok=True)
    if not path.endswith('.html'):
        # a study directory: the newest successful revision, by the same rule as reports/LATEST_REPORT.html
        index = target / '.report_versions.json'
        fetch(c, path + '/reports/report_versions.json', index)
        versions = json.loads(index.read_text(encoding='utf-8'))
        index.unlink()
        best = next((v for v in reversed(versions) if v.get('rolling_status') in ('COMPLETED', 'INVALIDATED')), versions[-1])
        print(f"本研究共 {len(versions)} 个报告版本，下载最新的第 {best['revision']} 版（2026状态：{best.get('rolling_status') or '原始研究'}）。")
        path = checked_report_path(c, best['html'])
    run = Path(path).parent.parent.name if Path(path).parent.name == 'reports' else Path(path).parent.name
    local = target / f'{run}__{Path(path).name}'
    fetch(c, path, local)
    print(f'已下载：{local}')
    print('这是服务器报告的本地副本；服务器上的研究成果不受影响。报告页内图表可离线交互。')
    if open_it:
        open_locally(local)
    return local


def agent_main(argv=None):
    _utf8_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('help', '-h', '--help'):
        print(AGENT_HELP)
        return 0
    if argv[0] == 'version':
        print(f'quant-agent（本地客户端）{VERSION}')
        return 0
    if not all(TOKEN.fullmatch(x) for x in argv[1:] if not (argv[0] == 'report' and x.startswith('/'))):
        raise SystemExit('参数只能包含字母、数字和 _ . : -（会话ID、任务ID）。')
    c = load_config()
    try:
        if argv[0] == 'chat':
            if argv[1:] and (argv[1] != '--resume' or len(argv) != 3):
                raise SystemExit('用法：quant-agent chat 或 quant-agent chat --resume <会话ID>')
            print('正在连接研究服务器……服务器会提示输入 DeepSeek Key（输入不回显、不保存）。输入 /exit 或按 Ctrl+D 退出。', flush=True)
            return interactive(c, argv)
        if argv[0] in ('session', 'history', 'status', 'logs', 'result', 'session_tasks'):
            sys.stdout.write(remote(c, argv))
            return 0
        if argv[0] == 'report':
            if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != '--no-open'):
                raise SystemExit('用法：quant-agent report <研究目录或报告路径> [--no-open]')
            cmd_report(c, argv[1], open_it=len(argv) == 2)
            return 0
    except subprocess.TimeoutExpired:
        raise SystemExit('连接超时：服务器没有在限定时间内响应。')
    raise SystemExit(f'未知命令：{argv[0]}。运行 quant-agent help 查看用法。')


if __name__ == '__main__':
    raise SystemExit(main())
