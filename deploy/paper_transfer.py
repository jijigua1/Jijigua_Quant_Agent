"""Bounded standard SSH stream/inbox import; uses the existing dropped importer."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terminal_paper_upload import LAUNCHER, MAX_BYTES, private_staging, check_received, import_received, upload

def metadata(stream):
    raw = stream.readline(4097)
    if not raw.endswith(b'\n') or len(raw) > 4096: raise SystemExit('UPLOAD_HEADER_INVALID')
    try: value = json.loads(raw)
    except (ValueError, UnicodeError): raise SystemExit('UPLOAD_HEADER_INVALID') from None
    if not isinstance(value, dict): raise SystemExit('UPLOAD_HEADER_INVALID')
    return value

def receive(stream, directory):
    head = metadata(stream)
    if set(head) != {'protocol','name_b64','bytes','sha256'} or head['protocol'] != 1: raise SystemExit('UPLOAD_HEADER_INVALID')
    if type(head['bytes']) is not int or not 0 < head['bytes'] <= MAX_BYTES: raise SystemExit('PDF_SIZE_LIMIT_50_MIB')
    if not isinstance(head['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',head['sha256']): raise SystemExit('UPLOAD_SHA_INVALID')
    if not isinstance(head['name_b64'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,700}',head['name_b64']): raise SystemExit('UPLOAD_NAME_INVALID')
    try: name = base64.urlsafe_b64decode(head['name_b64']+'='*(-len(head['name_b64'])%4)).decode('utf-8')
    except (ValueError, UnicodeError): raise SystemExit('UPLOAD_NAME_INVALID') from None
    if not name or name in {'.','..'} or any(x in name for x in '/\\\0\r\n') or Path(name).suffix.lower() != '.pdf': raise SystemExit('UPLOAD_NAME_INVALID')
    path = directory/name
    total,digest = 0,hashlib.sha256()
    with path.open('xb') as out:
        while total < head['bytes']:
            block = stream.read(min(1<<20,head['bytes']-total))
            if not block: raise SystemExit('UPLOAD_INTERRUPTED_NO_IMPORT')
            out.write(block);total+=len(block);digest.update(block)
        out.flush();os.fsync(out.fileno())
    if stream.read(1): raise SystemExit('UPLOAD_TRAILING_BYTES')
    if digest.hexdigest()!=head['sha256']: raise SystemExit('UPLOAD_SHA_MISMATCH')
    checked=check_received(directory)
    assert len(checked)==1
    return checked[0]

def inbox_source(stream, staging, directory):
    head=metadata(stream)
    if set(head)!={'protocol','path'} or head['protocol']!=1 or not isinstance(head['path'],str): raise SystemExit('IMPORT_HEADER_INVALID')
    path=Path(head['path']);inbox=staging/'inbox'
    if not path.is_absolute() or path.parent!=inbox or path.name in {'.','..'} or path.suffix.lower()!='.pdf': raise SystemExit('IMPORT_OUTSIDE_CONTROLLED_INBOX')
    fd=os.open(inbox,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if info.st_uid!=0 or info.st_mode&0o077: raise SystemExit('IMPORT_INBOX_NOT_PRIVATE')
        source=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    finally:os.close(fd)
    target=directory/path.name
    try:
        before=os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=0 or before.st_mode&0o022: raise SystemExit('IMPORT_SOURCE_PERMISSIONS')
        if not 0<before.st_size<=MAX_BYTES: raise SystemExit('PDF_SIZE_LIMIT_50_MIB')
        with target.open('xb') as out:
            total=0
            while block:=os.read(source,1<<20):
                total+=len(block)
                if total>MAX_BYTES: raise SystemExit('PDF_SIZE_LIMIT_50_MIB')
                out.write(block)
        after=os.fstat(source)
        if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns): raise SystemExit('IMPORT_SOURCE_CHANGED')
    finally:os.close(source)
    checked=check_received(directory)
    assert len(checked)==1
    return checked[0]

def transfer(command, stream=None):
    staging=private_staging();os.umask(0o077)
    stream=stream or sys.stdin.buffer
    with tempfile.TemporaryDirectory(prefix='ssh-',dir=staging) as tmp:
        directory=Path(tmp)
        path,sha=receive(stream,directory) if command=='receive' else inbox_source(stream,staging,directory)
        result=import_received(path,sha,staging)
        result['sha256']=sha
        print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0

def main(argv=None):
    p=argparse.ArgumentParser(description='统一论文入口：本地SSH、显式ZMODEM或受控inbox导入。')
    p.add_argument('command',nargs='?',default='help',choices=['upload','receive','import','import-stream','list','help'])
    p.add_argument('path',nargs='?');p.add_argument('--mode',choices=['zmodem'])
    args=p.parse_args(argv)
    if args.command=='list':return subprocess.call([sys.executable,'-I','-B',str(LAUNCHER),'paper-list'])
    if args.command=='upload':
        if args.path:raise SystemExit('这是服务器入口；本地路径请在本机 quant-paper upload "本地路径.pdf" 运行。')
        if args.mode!='zmodem':
            if not sys.stdin.isatty():raise SystemExit('请选择 --mode zmodem，或在本机用SSH客户端上传。')
            print('仅支持ZMODEM的终端（如FinalShell）可弹窗上传。普通SSH/VS Code Remote请从本机上传。')
            if input('确认使用ZMODEM请输入 zmodem；其他输入取消：').strip()!='zmodem':return 0
        return upload()
    if args.command in {'receive','import-stream'}:
        if args.path or args.mode:raise SystemExit('UPLOAD_ARGUMENTS_INVALID')
        def timeout(*_):raise SystemExit('UPLOAD_TIMEOUT')
        signal.signal(signal.SIGALRM,timeout);signal.alarm(600)
        try:return transfer(args.command)
        finally:signal.alarm(0)
    if args.command=='import':
        if not args.path:raise SystemExit('用法：quant-paper import <本部署staging/inbox/文件.pdf>')
        import io
        return transfer('import-stream',io.BytesIO((json.dumps({'protocol':1,'path':args.path})+'\n').encode()))
    p.print_help()
    print('本机：quant-paper upload "本地论文.pdf"；FinalShell：quant-paper upload --mode zmodem')
    print('服务器：quant-paper import <本部署staging/inbox/文件.pdf>；统一清单：quant-paper list')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError) as exc:
        print('PAPER_TRANSFER_ERROR: '+type(exc).__name__,file=sys.stderr);raise SystemExit(2)
