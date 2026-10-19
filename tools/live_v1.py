"""Live acceptance driver for the ISOLATED v1.0 Beta CLI over an SSH PTY (real official DeepSeek).

The operator types the DeepSeek key once (hidden, never stored). Each session sends plain Chinese user lines exactly as a
user would (no IDs, SHAs, tools). Definition decisions and new-code approvals are NEVER answered by this script: it stops
and forwards the operator's own typed line. Transcripts: docs/v1beta/live/<session>.<stamp>.txt (key never written).
"""
import codecs
import getpass
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import paramiko

HOST, PORT, USER = 'your-ssh-host.example', 27182, 'root'
LAUNCH = '/usr/bin/python3 -I /opt/jijigua-quant-agent/v1beta/deploy/launcher_v1.py chat'
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'v1beta' / 'live'
PROMPT = re.compile(r'\[\d\d:\d\d:\d\d\] 你> ')
DECISION = '回复“同意”后才会执行该替代研究'
CODE = '回复“同意”即批准运行这一份代码'
SESSIONS = {
    'S1_new_paper': ['列出我上传的论文。', '研究我刚上传的论文。', '给我看Train、Validation、Test结果。',
                     '为什么2026最近几天还是N/A？', '这个因子的效果稳定吗？', '解释一下你的研究结论。'],
    'S2_known_papers': ['读取Amihud那篇论文，提取非流动性因子并做完整研究。', '研究George和Hwang那篇52周高点论文。'],
    'S3_user_factor_and_block': ['研究五日反转因子：过去5个交易日收益取负，预测期5日，给我完整的三阶段报告。',
                                 '研究Heston那篇期权动量论文里的因子。', '继续刚刚中断的论文研究。'],
}


def ask(prompt):
    """One operator reply; lines pasted together are joined; empty lines are not sent."""
    lines = [input(prompt).strip()]
    if os.name == 'nt':
        import msvcrt
        time.sleep(.3)
        buf = ''
        while msvcrt.kbhit():
            buf += msvcrt.getwch()
            if not msvcrt.kbhit():
                time.sleep(.2)
        lines += [x.strip() for x in buf.replace('\r', '\n').split('\n')]
    text = ' '.join(x for x in lines if x)
    return text or ask('（空行不会发送）' + prompt)


def run_session(client, key, name, lines):
    print(f'\n===== {name} =====', flush=True)
    ch = client.get_transport().open_session()
    ch.get_pty(width=200, height=50)
    ch.exec_command(LAUNCH)
    dec = codecs.getincrementaldecoder('utf-8')('replace')
    buf = {'out': ''}

    def until(pattern, start=0, timeout=2400):
        deadline = time.monotonic() + timeout
        while not (pattern.search(buf['out'], start) if hasattr(pattern, 'search') else pattern in buf['out'][start:]):
            if ch.recv_ready():
                chunk = dec.decode(ch.recv(65536))
                buf['out'] += chunk
                sys.stdout.write(chunk.replace(key, '[KEY]'))
                sys.stdout.flush()
            elif ch.exit_status_ready():
                raise RuntimeError('CLI exited')
            elif time.monotonic() > deadline:
                raise RuntimeError('timeout')
            else:
                time.sleep(.2)
        if key in buf['out']:
            raise RuntimeError('SECRET ECHOED; transcript discarded')
    steps, t0 = [], time.time()
    try:
        until('Key (not echoed):')
        ch.send(key + '\n')
        until(PROMPT)
        queue = list(lines)
        while queue:
            line = queue.pop(0)
            start = len(buf['out'])
            ch.send(line + '\n')
            steps.append(dict(sent=line, by='script (user wording)', at=time.time() - t0))
            until(PROMPT, start)
            answer = buf['out'][start:]
            if DECISION in answer:
                typed = ask('\n>>> 以上为研究口径确认。请输入你的答复（例如“同意”或“拒绝”）：\n决策> ')
                queue.insert(0, typed)
                steps[-1]['gate'] = 'definition'
                steps.append(dict(note='next line typed by operator'))
            elif CODE in answer:
                typed = ask('\n>>> 以上为新代码审核包。请审核后输入你的答复（“同意”批准运行，“拒绝”不运行）：\n审核> ')
                queue.insert(0, typed)
                steps[-1]['gate'] = 'code'
                steps.append(dict(note='next line typed by operator'))
        ch.send('/exit\n')
        time.sleep(1)
    finally:
        while ch.recv_ready():
            buf['out'] += dec.decode(ch.recv(65536))
        ch.close()
    text = buf['out']
    if key in text:
        raise RuntimeError('SECRET ECHOED; transcript discarded')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{name}.{stamp}.txt').write_text(f'# {name} {datetime.now().astimezone().isoformat()}\n\n' + text, encoding='utf-8')
    summary = OUT / 'live_summary.json'
    rows = json.loads(summary.read_text(encoding='utf-8')) if summary.exists() else []
    rows.append(dict(session=name, transcript=f'{name}.{stamp}.txt', seconds=round(time.time() - t0, 1), steps=steps))
    summary.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')


def main():
    only = sys.argv[1:] or list(SESSIONS)
    key = getpass.getpass('DeepSeek Key (not echoed): ').strip()
    if not key:
        raise SystemExit('no key')
    client = paramiko.SSHClient()
    client.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(HOST, PORT, USER, key_filename=os.path.expanduser('~/.ssh/id_ed25519_gpushare'), look_for_keys=False, allow_agent=False)
    for name in only:
        run_session(client, key, name, SESSIONS[name])
    client.close()
    print('\n完成。转录：', OUT, flush=True)


if __name__ == '__main__':
    main()
