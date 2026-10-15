"""Operator's local driver for the old-vs-new paper flow comparison on the pre-release host (v1rc).

usage:
  python tools/paper_ab_remote.py [dev,exposed,holdout2] [--only D02,D03] [--labels new] [--repeat 2]
  python tools/paper_ab_remote.py --fetch run_20261015_101500      (copy a finished or interrupted run's results)
  python tools/paper_ab_remote.py --status                          (is a comparison running on the host?)
  python tools/paper_ab_remote.py --health                          (after an outage: 3 tiny calls, PROVIDER_HEALTHY?)

The DeepSeek key is typed here once (not echoed), sent over the SSH channel's stdin to tools/paper_ab.py drive (run as
quantagent), never written to disk or put on a command line. Progress lines are shown as each case finishes. Ctrl+C stops
THIS run on the host (only the processes of its own run directory) and copies what is finished. The host refuses a second
comparison while one is running (one model bill at a time). Results land in docs/v1beta/live/ab_<stamp>/.
"""
import getpass
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import paramiko

HOST, PORT, USER = 'gpu.example.org', 2222, 'root'
NEW = '/opt/jijigua-quant-agent/v1rc'
OLD = '/srv/jijigua-quant-agent/ab/old_src'
LIB = '/srv/jijigua-quant-agent/v1rc/papers'
PY = '/opt/jijigua-quant-agent/v1beta/.venv/bin/python'
ROOT = '/srv/jijigua-quant-agent/ab'
LOCAL = Path(__file__).resolve().parents[1] / 'docs' / 'v1beta' / 'live'


def connect():
    c = paramiko.SSHClient()
    c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
    c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.connect(HOST, PORT, USER, key_filename=os.path.expanduser('~/.ssh/id_ed25519_gpushare'), look_for_keys=False, allow_agent=False)
    c.get_transport().set_keepalive(20)
    return c


def run(c, cmd):
    _, o, e = c.exec_command(cmd)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')


def fetch(c, out, key=None):
    stamp = out.rstrip('/').rsplit('run_', 1)[-1]
    dest = LOCAL / f'ab_{stamp}'
    dest.mkdir(parents=True, exist_ok=True)
    sftp = c.open_sftp()
    for name in run(c, f'ls {out}').split():
        if name.endswith(('.json', '.md', '.log')):
            sftp.get(f'{out}/{name}', str(dest / name))
    sftp.close()
    for p in dest.glob('*'):
        if key and key in p.read_text(encoding='utf-8', errors='replace'):
            p.unlink()
            raise RuntimeError(f'SECRET FOUND in {p.name}; file deleted')
    return dest


def arg(name, default=''):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    c = connect()
    if '--status' in sys.argv:
        print(run(c, f'cat {ROOT}/locks/AB_RUNNING.lock 2>/dev/null || echo "no comparison running"'))
        return
    if '--health' in sys.argv:
        # first step after a provider outage: 3 tiny calls (a few dozen tokens) before any large run
        key = getpass.getpass('DeepSeek Key (not echoed): ').strip()
        stdin, stdout, _ = c.exec_command(f"su quantagent -s /bin/sh -c 'cd /tmp && PYTHONPATH={NEW}/src exec {PY} -X utf8 {NEW}/tools/paper_ab.py health'")
        stdin.write(key + '\n')
        stdin.flush()
        stdin.channel.shutdown_write()
        text = stdout.read().decode('utf-8', 'replace')
        print(text.replace(key, '***'))
        return
    if '--fetch' in sys.argv:
        print('结果：', fetch(c, f'{ROOT}/{arg("--fetch")}'))
        return
    cases = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'dev,exposed,holdout2'
    held = run(c, f'cat {ROOT}/locks/AB_RUNNING.lock 2>/dev/null').strip()
    if held:
        print('服务器上已有一次对比在运行或残留锁：', held, '\n如确认它已结束，可用 --status 查看；不会重复启动（避免费用翻倍）。')
    key = getpass.getpass('DeepSeek Key (not echoed): ').strip()
    if not key:
        raise SystemExit('no key')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = f'{ROOT}/run_{stamp}'
    extra = ''.join(f' --{k} {arg("--" + k)}' for k in ('only', 'labels', 'repeat') if arg('--' + k))
    inner = (f'cd /tmp && exec {PY} -X utf8 {NEW}/tools/paper_ab.py drive --key-stdin --old {OLD} --new {NEW}/src '
             f'--library {LIB} --out {out} --cases {cases}{extra}')
    cmd = (f"mkdir -p {out} {ROOT}/locks && chown quantagent:quantagent {out} {ROOT}/locks && chmod 700 {out} && "
           f"su quantagent -s /bin/sh -c '{inner}'")
    stdin, stdout, _ = c.exec_command(cmd, get_pty=False)
    stdin.write(key + '\n')
    stdin.flush()
    stdin.channel.shutdown_write()
    t0 = time.time()
    print(f'运行编号：run_{stamp}（服务器目录 {out}）。每完成一个案例显示一行；Ctrl+C 会停止本次运行并取回已完成的结果。', flush=True)
    try:
        for line in iter(stdout.readline, ''):
            if key in line:
                raise RuntimeError('SECRET ECHOED; output discarded')
            print(line.rstrip(), flush=True)
    except KeyboardInterrupt:
        print('\n正在停止服务器上的本次运行……', flush=True)
        run(c, f"pkill -f 'paper_ab.py (drive|run) .*--out {out}( |$)'; sleep 1; rm -f {ROOT}/locks/AB_RUNNING.lock")
    dest = fetch(c, out, key)
    c.close()
    print(f'\n完成（{round(time.time() - t0)} 秒）。结果：{dest}')


if __name__ == '__main__':
    main()
