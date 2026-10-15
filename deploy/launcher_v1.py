"""Root-owned v1.0 Beta launcher. Standard library only; drops identity before any Agent code runs.

  chat            DeepSeek key (hidden) -> [rolling configured] socketpair + fork:
                    child  : quantagent (+quantdata), Agent CLI, inherits only the socket FD
                    parent : exec of the root-owned runtime as the rolling-evaluation broker for this session only
  paper-import    root checks one staged upload (root-owned, regular, single link, size) and passes an open FD to the
                  dropped Agent, which verifies the SHA-256 and registers it; root never writes into Agent directories
  paper-list      dropped Agent lists the registered papers
  status|logs|result|session|history|session_tasks  as before (no key)
"""
import getpass
import grp
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
HOST = HERE / 'host.json'
STAGED = re.compile(r'^up-[0-9a-f]{16}-[0-9a-f]{8}\.pdf$')
MAX_UPLOAD = 50 * 1024 ** 2


def host_config():
    st = os.stat(HOST, follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise SystemExit('Launcher host configuration is not root-controlled')
    return json.loads(HOST.read_text(encoding='utf-8'))


def drop(account, groups=('quantdata',)):
    if os.geteuid() == 0:
        os.setgroups([grp.getgrnam(g).gr_gid for g in groups])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    if os.geteuid() != account.pw_uid:
        raise SystemExit('Identity drop failed')


def agent_args(h, command, *, chat=False):
    args = [h['agent_python'], '-I', h['runner'], '--state-dir', h['state_dir'], '--profile', 'development', '--provider', 'deepseek']
    if chat:
        args += ['--skill', 'data_query', '--resources-manifest', h['resources_manifest']]
    return args + ['--research-config', h['research_config']] + command


def environment(h):
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': h['agent_home'], 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'TERM': os.environ.get('TERM', 'dumb'), 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
           'MKL_NUM_THREADS': '1', 'MPLCONFIGDIR': h['agent_home'] + '/matplotlib'}
    if h.get('test_fault_injection') and '/v1beta/' not in h['root'] + '/':
        env['QRA_TEST_CORRUPT_JSON_ONCE'] = '1'          # pre-release staging only (root-owned host.json); never production
    return env


def paper_import(h, account, staged, name_b64, sha):
    if not STAGED.fullmatch(staged) or not re.fullmatch(r'[A-Za-z0-9_-]{1,700}', name_b64) or not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise SystemExit('Invalid upload reference')
    root = Path(h['paper_staging'])
    st = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o077:
        raise SystemExit('Upload staging directory is not root-private')
    fd = os.open(root / staged, os.O_RDONLY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0 or not 0 < info.st_size <= MAX_UPLOAD:
        os.close(fd)
        raise SystemExit('Upload is not a single root-owned regular file within the size limit')
    os.unlink(root / staged)                 # the open descriptor keeps the bytes; no half-file remains
    now = time.time()
    for old in root.iterdir():               # interrupted uploads never become papers; remove after a day
        try:
            s = os.stat(old, follow_symlinks=False)
            if stat.S_ISREG(s.st_mode) and s.st_uid == 0 and now - s.st_mtime > 86400:
                old.unlink()
        except OSError:
            pass
    os.set_inheritable(fd, True)
    os.umask(0o077)
    os.chdir(h['root'])
    drop(account, ())
    args = agent_args(h, ['paper-import', f'fd:{fd}', name_b64, sha])
    os.execve(args[0], args, environment(h))


def main():
    account = pwd.getpwnam('quantagent')
    if account.pw_uid == 0 or os.geteuid() not in {0, account.pw_uid}:
        raise SystemExit('Launcher identity denied')
    h = host_config()
    command = sys.argv[1:] or ['chat']
    if command[0] == 'paper-import' and len(command) == 4:
        if os.geteuid() != 0:
            raise SystemExit('paper-import requires the trusted operator account')
        return paper_import(h, account, *command[1:])
    os.umask(0o077)
    os.chdir(h['root'])
    env = environment(h)
    if command[0] == 'paper-list':
        drop(account, ())
        args = agent_args(h, ['paper-list'])
        os.execve(args[0], args, env)
    if command[0] in {'status', 'logs', 'result', 'session', 'history', 'session_tasks'}:
        drop(account)
        args = agent_args(h, command)
        os.execve(args[0], args, env)
    secret = os.environ.get('QRA_DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek Key (not echoed): ')
    if not secret:
        raise SystemExit('DeepSeek Key required')
    args = agent_args(h, command, chat=True)
    rolling = h.get('rolling')
    if not rolling or os.geteuid() != 0:
        drop(account)
        os.execve(args[0], args, env | {'QRA_DEEPSEEK_API_KEY': secret})
    parent, child = socket.socketpair()
    pid = os.fork()
    if pid == 0:
        parent.close()
        os.set_inheritable(child.fileno(), True)
        drop(account)
        os.execve(args[0], args, env | {'QRA_DEEPSEEK_API_KEY': secret, 'QRA_ROLLING_FD': str(child.fileno()),
                                         'QRA_ROLLING_RECEIPTS': rolling['receipt_dir']})
    child.close()
    del secret
    os.set_inheritable(parent.fileno(), True)
    program = ('import sys;sys.path[:0]=' + repr([rolling['broker_code']]) + ';from rolling_test.broker_main import main;'
               'main(' + repr(parent.fileno()) + ',' + repr(pid) + ',' + repr(rolling['config']) + ')')
    os.execve(rolling['runtime_python'], [rolling['runtime_python'], '-I', '-B', '-c', program],
              {'PATH': '/usr/sbin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'OPENBLAS_NUM_THREADS': '1'})


if __name__ == '__main__':
    main()
