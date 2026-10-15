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

HOST, PORT, USER = 'gpu.example.org', 2222, 'root'
LAUNCH = '/usr/local/bin/quant-agent chat'      # production entry (v1.0 Beta since KEVIN-20261013-V1-PROD); rounds 1-2 used launcher_v1.py directly
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'v1beta' / 'live'
PROMPT = re.compile(r'\[\d\d:\d\d:\d\d\] 你> ')
DECISION = '回复“同意”后才会执行该替代研究'
CODE = '回复“同意”即批准运行这一份代码'
UNCLEAR_CODE, UNCLEAR_DEFINITION = '新算法代码尚未运行，仍待你审核', '替代研究仍待你确认'   # a refused unclear reply: the operator answers again
ASSET_DECISION, ASSET_UNCLEAR = '后才会执行该非忠实替代研究', '属于非忠实的探索性替代'          # asset substitution: exact phrase only
STAGING = '/usr/bin/python3 -I /opt/jijigua-quant-agent/v1rc/deploy/launcher_v1.py chat'   # isolated pre-release copy (v1rc)
INTERRUPT = '@CTRL_C_AFTER:'                     # '@CTRL_C_AFTER:<s>' sends the next line, waits s seconds, then Ctrl+C
SESSIONS = {
    'S1_new_paper': ['列出我上传的论文。', '研究我刚上传的论文。', '给我看Train、Validation、Test结果。',
                     '为什么2026最近几天还是N/A？', '这个因子的效果稳定吗？', '解释一下你的研究结论。'],
    'S2_known_papers': ['读取Amihud那篇论文，提取非流动性因子并做完整研究。', '研究George和Hwang那篇52周高点论文。'],
    'S3_user_factor_and_block': ['研究五日反转因子：过去5个交易日收益取负，预测期5日，给我完整的三阶段报告。',
                                 '研究Heston那篇期权动量论文里的因子。', '继续刚刚中断的论文研究。'],
    # Round 2 (after the fixes for the round-1 defects); round-1 transcripts are kept unchanged.
    'R2_S1_new_paper': ['列出我上传的论文。', '研究我刚上传的论文。', '给我看Train、Validation、Test结果。',
                        '为什么2026最近几天还是N/A？', '这个因子的效果稳定吗？', '解释一下你的研究结论。'],
    # at the first 52-week-high decision the operator pauses; the next line resumes the interrupted paper study
    'R2_S2_resume_block_regress': ['研究George和Hwang那篇52周高点论文。', '继续刚刚中断的论文研究。',
                                   '研究Heston那篇期权动量论文里的因子。', '读取Amihud那篇论文，提取非流动性因子并做完整研究。'],
    # Round 3: the MA paper after the JSON-repair fix; the operator pauses at the first decision and answers the code gate
    # vaguely once, so resumption and the no-bypass rule are both exercised.
    # Production acceptance: the frozen 52-week-high study had never been evaluated on 2026; first real rolling Test.
    'P1_prod_first_real_test': ['研究George和Hwang那篇52周高点论文。', '给我看Train、Validation、Test结果。',
                                '为什么2026最近几天还是N/A？', '这个因子的效果稳定吗？', '解释一下你的研究结论。'],
    'R3_ma_resume_gates': ['研究我刚上传的论文。', '继续刚刚中断的论文研究。', '给我看Train、Validation、Test结果。',
                           '为什么2026最近几天还是N/A？', '这个因子的效果稳定吗？', '解释一下你的研究结论。'],
    # Final-quality stability matrix on the isolated v1rc staging copy (rolling Test not authorized there).
    'Q1_STAGING_new_papers': ['列出我上传的论文。', '研究1110.3383那篇技术指标论文里的因子。', '研究MACD那篇论文的因子。'],
    'Q2_STAGING_blocks': ['研究AQR那篇趋势跟踪论文里的因子。', '研究华泰那份量化月报里的因子。',
                          '研究0212641那篇成交量风险论文里的因子。'],
    # run after Q1 (the operator pauses at the MACD decision there): the first line resumes it across sessions
    'Q3_STAGING_ma_gates_interrupt': ['继续刚刚中断的论文研究。', '研究moving average（移动平均）那篇论文的因子。',
                                      INTERRUPT + '25', '研究moving average（移动平均）那篇论文的因子。', '继续刚刚中断的论文研究。',
                                      '给我看Train、Validation、Test结果。', '这个因子的效果稳定吗？'],
    # Re-test after the Q1-Q3 fixes: block reasons shown, a named paper resolved without a clarifying question, the MA code
    # gate (vague answer first), then a repeated submission interrupted mid-computation and resumed in plain words.
    'Q4_STAGING_retest': ['研究1110.3383那篇技术指标论文里的因子。', '研究华泰那份量化月报里的因子。',
                          '研究0212641那篇成交量风险论文里的因子。', '研究moving average（移动平均）那篇论文的因子。',
                          INTERRUPT + '20', '研究moving average（移动平均）那篇论文的因子。', '继续刚刚中断的论文研究。',
                          '给我看Train、Validation、Test结果。'],
    # MA only: code gate (vague answer first), real run, repeated submission interrupted mid-computation, plain-word resume
    'Q5_STAGING_ma_run_interrupt': ['研究moving average（移动平均）那篇论文的因子。', INTERRUPT + '25',
                                    '研究moving average（移动平均）那篇论文的因子。', '继续刚刚中断的论文研究。',
                                    '给我看Train、Validation、Test结果。'],
    # Ctrl+C while a computation runs (a user-defined DSL factor needs no gate), then a plain-word resume
    'Q6_STAGING_interrupt_compute': [INTERRUPT + '20', '研究五日反转因子：过去5个交易日收益取负，预测期5日。',
                                     '继续刚刚中断的研究。', '给我看Train、Validation、Test结果。'],
    # Hardening acceptance (2026-10-14): dev papers re-read by the new reader, then the frozen holdout set (never opened
    # during development), then interruption / repetition on the trusted IR route.
    'H1_STAGING_dev_regression': ['研究AQR那篇趋势跟踪论文里的因子。', '研究MACD那篇论文的因子。', '研究1110.3383那篇技术指标论文里的RSI因子。',
                                  '研究0212641那篇成交量风险论文里的因子。', '研究moving average（移动平均）那篇论文的因子。',
                                  '研究Heston那篇期权动量论文里的因子。', '研究华泰那份量化月报里的因子。'],
    'H2_STAGING_holdout_a': ['研究greatwall那份研报里的因子。', '研究xiangcai那份ETF趋势研报里的因子。',
                             '研究hans那篇择时论文里的因子。', '研究CN03那篇论文里的VRP因子。', '研究CN12那篇论文里的因子。'],
    'H3_STAGING_holdout_b': ['研究CORE04那篇论文里的因子。', '研究CORE09那篇论文里的因子。', '研究CORE17那篇论文里的因子。',
                             '研究ML03那篇论文里的因子。', '研究ROOT08那篇论文里的因子。'],
    # run after H1 (where the MACD definition is confirmed): the same paper starts computing at once, Ctrl+C lands mid-study
    'H4_STAGING_interrupt_repeat': [INTERRUPT + '20', '研究MACD那篇论文的因子。', '继续刚刚中断的论文研究。',
                                    '研究MACD那篇论文的因子。', '给我看Train、Validation、Test结果。'],
    # Round 3 (AI investigation x program reconciliation): at most four papers per session (round 2 ran out of the
    # session token budget on the seventh); free parameters answered by the user in plain words.
    'J1_STAGING_params': ['研究MACD那篇论文的MACD因子。', '研究1110.3383那篇技术指标论文里的RSI因子。',
                          '研究1110.3383那篇技术指标论文里的RSI因子，X=14。'],
    'J2_STAGING_condmat_ma': ['研究0212641那篇成交量风险论文里的经典动量指标CMI。', '研究0212641那篇成交量风险论文里的广义动量指标GMI。',
                              '研究moving average（移动平均）那篇论文的因子。'],
    'J3_STAGING_blocks_cn': ['研究AQR那篇趋势跟踪论文里的因子。', '研究华泰那份量化月报里的因子。',
                             '研究greatwall那份研报里的因子。', '研究xiangcai那份ETF趋势研报里的因子。'],
    'J4_STAGING_exposed': ['研究hans那篇择时论文里的因子。', '研究ROOT08那篇论文里的因子。', '研究CN03那篇论文里的VRP因子。',
                           '研究CORE04那篇论文里的因子。'],
    # never opened during development (file names only): the second holdout set
    'J5_STAGING_holdout2': ['研究101 Formulaic Alphas那篇论文里的Alpha#12。', '研究CN04那篇论文的因子。',
                            '研究CORE05那篇论文的因子。', '研究ML08那篇论文的因子。'],
    'J6_STAGING_holdout2b': ['研究ROOT11那篇论文的因子。', '研究101 Formulaic Alphas那篇论文里的Alpha#101。'],
}
LAUNCH_FOR = {name: STAGING for name in SESSIONS if '_STAGING_' in name}


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
    ch.exec_command(LAUNCH_FOR.get(name, LAUNCH))
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
            interrupt = None
            if line.startswith(INTERRUPT):
                interrupt, line = float(line[len(INTERRUPT):]), queue.pop(0)
            start = len(buf['out'])
            ch.send(line + '\n')
            steps.append(dict(sent=line, by='script (user wording)', at=time.time() - t0))
            if interrupt is not None:
                time.sleep(interrupt)
                ch.send('\x03')                            # Ctrl+C in the PTY: the CLI's own interrupt path
                steps.append(dict(sent='<Ctrl+C>', by='script (interrupt test)', at=time.time() - t0))
            until(PROMPT, start)
            answer = buf['out'][start:]
            if ASSET_DECISION in answer or ASSET_UNCLEAR in answer:
                typed = ask('\n>>> 以上为【资产替代】确认：论文资产与A股个股不同，只有你原样输入要求的短语才会运行；'
                            '输入“不要替代”则保留原定义。\n决策> ')
                queue.insert(0, typed)
                steps[-1]['gate'] = 'asset'
                steps.append(dict(note='next line typed by operator'))
            elif DECISION in answer or UNCLEAR_DEFINITION in answer:
                typed = ask('\n>>> 以上为研究口径确认。请输入你的答复（例如“同意”或“拒绝”）：\n决策> ')
                queue.insert(0, typed)
                steps[-1]['gate'] = 'definition'
                steps.append(dict(note='next line typed by operator'))
            elif CODE in answer or UNCLEAR_CODE in answer:
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
    client.get_transport().set_keepalive(20)        # R3 2026-10-13: the link was reset while the operator was deciding
    for name in only:
        run_session(client, key, name, SESSIONS[name])
    client.close()
    print('\n完成。转录：', OUT, flush=True)


if __name__ == '__main__':
    main()
