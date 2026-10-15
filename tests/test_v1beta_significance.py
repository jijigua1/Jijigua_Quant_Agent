"""Interval significance is decided from the numbers; a summary that contradicts them is caught (live P1 sentences)."""
from research_agent import significance as S

# The real P1 report (52-week high, 2026-10-13): RankIC HAC 95% intervals per stage.
PRO = {'partitions': {'train': {'rank_ic_ci_low': -0.0466, 'rank_ic_ci_high': 0.0075},
                      'valid': {'rank_ic_ci_low': -0.0880, 'rank_ic_ci_high': -0.0200}},
       'test': {'status': 'COMPLETED', 'metrics': {'rank_ic_ci_low': -0.0777, 'rank_ic_ci_high': 0.0542}}}


def test_verdicts_and_line_come_from_the_numbers():
    rows = S.judgements(PRO)
    assert [(s, v) for s, _, _, v in rows] == [('train', 'crosses'), ('valid', 'excludes_negative'), ('test', 'crosses')]
    line = S.line(rows)
    assert 'Validation [-0.0880, -0.0200] 不跨0（负向' in line and 'Train [-0.0466, +0.0075] 跨0' in line and 'Test（2026滚动暴露）' in line


def test_the_live_p1_misstatements_are_caught():
    rows = S.judgements(PRO)
    live = ['Validation有效日474天，IC约-0.034、RankIC约-0.054，置信区间均含0。',                   # P1 follow-up 1
            'Train IC均值约-0.011、RankIC约-0.020，Validation IC约-0.034、RankIC约-0.054，两分区置信区间均跨0，仅说明']   # deploy-2 run
    for text in live:
        assert any(s == 'valid' for s, _ in S.contradictions(text, rows)), text


def test_correct_or_undecidable_statements_pass():
    rows = S.judgements(PRO)
    ok = ['Validation RankIC约-0.054，HAC区间不跨0，方向为负。',
          'Train区间跨0，证据不足。',
          '2026滚动Test有效174天，RankIC约-0.012，区间跨0。',
          '整体结论为证据不足。',                                          # no interval claim
          'Train区间跨0，而Validation区间不跨0。']                         # both claims in one sentence: not decided here
    for text in ok:
        assert S.contradictions(text, rows) == [], text


def test_missing_intervals_and_unevaluated_test_are_not_judged():
    rows = S.judgements({'partitions': {'train': {'rank_ic_ci_low': None, 'rank_ic_ci_high': None},
                                        'valid': {'rank_ic_ci_low': -0.1, 'rank_ic_ci_high': 0.1}},
                         'test': {'status': 'NOT_EVALUATED'}})
    assert [(s, v) for s, _, _, v in rows] == [('train', 'unavailable'), ('valid', 'crosses')]
    assert '区间不可用' in S.line(rows) and S.contradictions('Train区间不跨0。', rows) == []
