"""Forced-command gate for an existing unprivileged SSH account (deployment approval required).

authorized_keys: restrict,command="/usr/bin/python3 -I -B /.../deploy/paper_ssh_gate.py" <EXISTING_PUBLIC_KEY>
No SFTP, shell, forwarding, arbitrary source paths, or client-specified installation.
Pair with the two exact sudoers command lines emitted by --policy; never broad sudo.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
LAUNCHER=HERE/'launcher_v1.py'

def select(original):
    actions={'/usr/local/bin/quant-paper receive':'receive','/usr/local/bin/quant-paper list':'list'}
    if original not in actions:raise SystemExit('SSH_UPLOAD_COMMAND_DENIED')
    return ['/usr/bin/python3','-I','-B',str(LAUNCHER),'paper-transfer',actions[original]]

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if argv==['--policy']:
        # This is a reviewable template, never automatically installed.
        for action in ('receive','list'):
            print('quantagent ALL=(root) NOPASSWD: /usr/bin/python3 -I -B '+str(LAUNCHER)+' paper-transfer '+action)
        return 0
    if argv:raise SystemExit('SSH_UPLOAD_ARGUMENTS_DENIED')
    command=select(os.environ.get('SSH_ORIGINAL_COMMAND',''))
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    return subprocess.call(['/usr/bin/sudo','-n','--',*command],env=env)

if __name__=='__main__':raise SystemExit(main())
