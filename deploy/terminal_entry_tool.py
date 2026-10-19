#!/usr/bin/env python3
"""Explicit, backed-up quant-paper entry transaction. No Agent/data/config writes.

Use --rehearsal PREFIX under the existing AB area for this round. --production
is reserved for a separately approved deployment and selects /usr/local/bin.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from release_tool import Root,Stop,sha,lock,_seal,inside,REHEARSAL_AREA

HERE=Path(__file__).resolve().parent
MARKER='.paper_entry_in_progress'

def target(args):
    if os.geteuid()!=0:raise Stop('operator root required')
    prefix='/usr/local/bin' if args.production else args.rehearsal
    if not os.path.isabs(prefix) or os.path.realpath(prefix)!=prefix.rstrip('/'):
        raise Stop('entry prefix must be canonical, absolute and without links')
    if not args.production and not inside(prefix,os.path.realpath(REHEARSAL_AREA)):
        raise Stop('rehearsal entry prefix must be inside AB area')
    root=Root(prefix)
    store='/root' if args.production else str(Path(prefix).parent)
    return root,store

def apply(args):
    if not re.fullmatch(r'[A-Za-z0-9._-]{8,80}',args.approval):raise Stop('explicit approval reference required')
    root,store=target(args);lk=lock(store)
    try:
        if root.lstat(MARKER):raise Stop('unfinished entry transaction; roll back first')
        agent=root.check_file('quant-agent')
        if agent is None or agent.st_uid!=0 or agent.st_mode&0o022:raise Stop('sibling quant-agent is not root controlled')
        payload=Root(str(HERE)).read('quant-paper')
        if sha(payload)!=args.wrapper_sha:raise Stop('wrapper differs from approved SHA')
        old=root.check_file('quant-paper')
        if old and (old.st_uid!=0 or old.st_mode&0o022):raise Stop('existing entry metadata drift')
        backup=tempfile.mkdtemp(prefix='paper_entry_backup_',dir=store);os.chmod(backup,0o700)
        record=dict(target=root.path,target_id=f'{root.dev}:{root.ino}',production=args.production,
            approval=args.approval,new_sha256=sha(payload),old=None)
        if old:
            raw=root.read('quant-paper')
            Path(backup,'old').write_bytes(raw)
            record['old']=dict(sha256=sha(raw),mode=stat.S_IMODE(old.st_mode),uid=old.st_uid,gid=old.st_gid)
        Path(backup,'TARGET.json').write_text(json.dumps(record),encoding='utf-8');_seal(backup)
        root.write(MARKER,backup.encode(),0o600)
        root.write('quant-paper',payload,0o755)
        if sha(root.read('quant-paper'))!=args.wrapper_sha:raise Stop('entry postcheck failed')
        root.unlink(MARKER)
        print(json.dumps(dict(status='INSTALLED',backup=backup,target=root.path,sha256=args.wrapper_sha)))
    finally:os.close(lk)

def rollback(args):
    root,store=target(args);backup=Root(os.path.abspath(args.backup))
    record=json.loads(backup.read('TARGET.json'))
    if record['target']!=root.path or record['target_id']!=f'{root.dev}:{root.ino}' or record['production']!=args.production:
        raise Stop('entry backup belongs to a different target')
    sums=json.loads(backup.read('BACKUP_SHA256.json'))
    for rel,digest in sums.items():
        if sha(backup.read(rel))!=digest:raise Stop('entry backup damaged')
    lk=lock(store)
    try:
        root.check_file('quant-paper');root.check_file(MARKER)
        previous=record['old']
        if previous:
            raw=backup.read('old')
            if sha(raw)!=previous['sha256']:raise Stop('old entry fingerprint')
            root.write('quant-paper',raw,previous['mode'],previous['uid'],previous['gid'])
        else:root.unlink('quant-paper')
        root.unlink(MARKER)
        print(json.dumps(dict(status='ROLLED_BACK',target=root.path)))
    finally:os.close(lk)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('apply','rollback'):
        p=sub.add_parser(command);g=p.add_mutually_exclusive_group(required=True)
        g.add_argument('--production',action='store_true');g.add_argument('--rehearsal',metavar='PREFIX')
        if command=='apply':
            p.add_argument('--approval',required=True);p.add_argument('--wrapper-sha',required=True)
        else:p.add_argument('--backup',required=True)
    args=parser.parse_args()
    try:(apply if args.command=='apply' else rollback)(args)
    except (Stop,OSError,ValueError,KeyError) as exc:
        parser.exit(3,'STOP: '+str(exc)+'\n')

if __name__=='__main__':main()
