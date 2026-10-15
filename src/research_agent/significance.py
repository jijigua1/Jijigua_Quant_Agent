"""Program-computed significance statements (RankIC HAC 95% intervals) and a check of model summaries against them.

Live P1 (2026-10-13): a model summary said the Validation interval contained zero; it was [-0.0880, -0.0200]. Every
statement about whether an interval crosses zero is made here from the numbers, and a model summary that contradicts
them is not shown.
"""
import re

LABEL = {'train': 'Train', 'valid': 'Validation', 'test': 'Test（2026滚动暴露）'}
MENTION = {'train': re.compile(r'Train|训练'), 'valid': re.compile(r'Validation|验证'), 'test': re.compile(r'Test|2026|测试')}
BOTH = re.compile(r'两分区|两个分区|两阶段|两个阶段')
ALL = re.compile(r'三阶段|三个阶段|各阶段|所有阶段')
CROSSES = re.compile(r'(?<!不)(跨\s*0|跨零|含\s*0|含零|包含\s*0|包含零)')
EXCLUDES = re.compile(r'不跨\s*0|不跨零|不含\s*0|不含零|不包含\s*0|不包含零')
INTERVAL = re.compile(r'区间')


def judgements(professional):
    """[(split, low, high, verdict)] with verdict in crosses / excludes_positive / excludes_negative / unavailable."""
    rows = []
    stages = [(s, (professional.get('partitions') or {}).get(s)) for s in ('train', 'valid')]
    test = professional.get('test') or {}
    if test.get('status') == 'COMPLETED':
        stages.append(('test', test.get('metrics')))
    for split, r in stages:
        lo, hi = (r or {}).get('rank_ic_ci_low'), (r or {}).get('rank_ic_ci_high')
        if lo is None or hi is None:
            verdict = 'unavailable'
        elif lo <= 0 <= hi:
            verdict = 'crosses'
        else:
            verdict = 'excludes_positive' if lo > 0 else 'excludes_negative'
        rows.append((split, lo, hi, verdict))
    return rows


def line(rows):
    words = {'crosses': '跨0（当前样本未提供明确预测证据）', 'excludes_positive': '不跨0（正向，统计上可与0区分）',
             'excludes_negative': '不跨0（负向，统计上可与0区分）', 'unavailable': '区间不可用'}
    parts = []
    for split, lo, hi, verdict in rows:
        span = '' if verdict == 'unavailable' else f' [{lo:+.4f}, {hi:+.4f}]'
        parts.append(f'{LABEL[split]}{span} {words[verdict]}')
    return '统计显著性（程序按RankIC HAC 95%区间判定）：' + '；'.join(parts) + '。'


def contradictions(text, rows):
    """Sentences whose claim about an interval crossing zero disagrees with the computed verdict."""
    verdict = {s: v for s, _, _, v in rows}
    found = []
    for sentence in re.split(r'[。；;\n]', text or ''):
        if not INTERVAL.search(sentence):
            continue
        says_excludes, says_crosses = bool(EXCLUDES.search(sentence)), bool(CROSSES.search(sentence))
        if says_excludes == says_crosses:                 # no claim, or both in one sentence: not decidable here
            continue
        named = [s for s, rx in MENTION.items() if rx.search(sentence)]
        if ALL.search(sentence):
            named = list(verdict)
        elif BOTH.search(sentence) and not named:
            named = ['train', 'valid']
        for s in named:
            v = verdict.get(s)
            if v in (None, 'unavailable'):
                continue
            if (says_crosses and v != 'crosses') or (says_excludes and v == 'crosses'):
                found.append((s, sentence.strip()[:120]))
    return found
