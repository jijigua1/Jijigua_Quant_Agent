"""Portable OpenSSH client; local paths travel as bytes/JSON, never shell code."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MAX_BYTES=50*1024*1024

def connection(args,config):
    allowed={'host','port','user','identity','server_command'}
    if not isinstance(config,dict) or set(config)-allowed:raise ValueError('CONNECTION_CONFIG_KEYS_INVALID')
    values={k:getattr(args,k,None) or config.get(k) for k in allowed}
    host=values['host']
    if not isinstance(host,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,252}',host):raise ValueError('Configure --host or ~/.quant-paper/config.json')
    command=values['server_command'] or '/usr/local/bin/quant-paper'
    if not isinstance(command,str) or not re.fullmatch('/[A-Za-z0-9_./-]+',command) or '..' in command.split('/'):raise ValueError('SERVER_COMMAND_PATH_INVALID')
    ssh=shutil.which('ssh')
    if not ssh:raise ValueError('OpenSSH ssh is required')
    argv=[ssh,'-T','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=20','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    if values['port']:
        port=int(values['port'])
        if not 1<=port<=65535:raise ValueError('SSH_PORT_INVALID')
        argv+=['-p',str(port)]
    if values['user']:
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_-]{0,63}',values['user']):raise ValueError('SSH_USER_INVALID')
        argv+=['-l',values['user']]
    if values['identity']:argv+=['-i',str(Path(values['identity']).expanduser())]
    return argv+['--',host],command

def spool_pdf(path):
    path=Path(path).expanduser();info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.suffix.lower()!='.pdf' or not 0<info.st_size<=MAX_BYTES:raise ValueError('Only a regular PDF of 1 byte to 50 MiB is accepted')
    if len(path.name.encode())>500 or any(c in path.name for c in '\0\r\n'):raise ValueError('PDF_NAME_INVALID')
    spool=tempfile.TemporaryFile('w+b');digest,total=hashlib.sha256(),0
    try:
        with path.open('rb') as source:
            if b'%PDF-' not in source.read(1024):raise ValueError('NOT_A_PDF')
            source.seek(0)
            while block:=source.read(1<<20):
                total+=len(block)
                if total>MAX_BYTES:raise ValueError('PDF_TOO_LARGE')
                digest.update(block);spool.write(block)
        after=path.stat()
        if (info.st_size,info.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or total!=info.st_size:raise ValueError('PDF_CHANGED_DURING_READ')
        head={'protocol':1,'bytes':total,'sha256':digest.hexdigest(),'name_b64':base64.urlsafe_b64encode(path.name.encode()).decode().rstrip('=')}
        spool.seek(0);return spool,head
    except BaseException:spool.close();raise

def main(argv=None):
    p=argparse.ArgumentParser(description='本机通过已有SSH上传PDF并统一登记；无需API Key。')
    p.add_argument('command',choices=['upload','list','import']);p.add_argument('path',nargs='?')
    p.add_argument('--config',type=Path,default=Path.home()/'.quant-paper/config.json')
    for key in ('host','port','user','identity','server-command'):p.add_argument('--'+key)
    args=p.parse_args(argv)
    config=json.loads(args.config.read_text(encoding='utf-8')) if args.config.exists() else {}
    ssh,server=connection(args,config)
    if args.command=='list':
        if args.path:p.error('list does not accept a path')
        return subprocess.call(ssh+[server+' list'])
    if not args.path:p.error('a PDF path is required')
    spool=None
    if args.command=='upload':spool,head=spool_pdf(args.path);remote='receive'
    else:head={'protocol':1,'path':args.path};remote='import-stream'
    proc=subprocess.Popen(ssh+[server+' '+remote],stdin=subprocess.PIPE)
    try:
        proc.stdin.write((json.dumps(head,ensure_ascii=True)+'\n').encode('ascii'))
        if spool:
            for block in iter(lambda:spool.read(1<<20),b''):proc.stdin.write(block)
        proc.stdin.close();return proc.wait(timeout=720)
    except (BrokenPipeError,subprocess.TimeoutExpired):
        proc.kill();proc.wait();print('上传中断或状态待确认；请用 list 核对。重传按SHA去重。',file=sys.stderr);return 2
    except KeyboardInterrupt:
        proc.terminate();proc.wait();print('已取消；没有自动重试。请用 list 核对。',file=sys.stderr);return 130
    finally:
        if spool:spool.close()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
