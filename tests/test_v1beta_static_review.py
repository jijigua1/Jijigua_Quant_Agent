"""Static review of model-generated factor code: R3 false positives fixed, unsafe structures still refused.

The MA candidate below is the real source DeepSeek wrote in live round R3 (2026-10-13) and the reviewer rejected for
UNGUARDED_DIVISION (a guarded name, a non-zero constant) and WINDOW_SHORTER_THAN_DECLARED (a window written as a loop).
These tests only parse source text (ast); no candidate is ever executed here.
"""
import json
from pathlib import Path

from paper_research.candidate import analyze_source

FIX = Path(__file__).parent / 'fixtures_v1beta'
CONTRACT = json.loads((FIX / 'ma_contract.json').read_text(encoding='utf-8'))      # declared max_lag 269, input close
REAL = (FIX / 'ma_candidate_rev2_rejected.py.txt').read_text(encoding='utf-8')


def codes(source, contract=CONTRACT):
    result = analyze_source(source, contract)
    return result, {i['code'] for i in result['issues']}


def body(lines):
    return 'import numpy as np\nimport pandas as pd\n\n\ndef compute(panels):\n' + ''.join('    ' + l + '\n' for l in lines)


def test_the_real_r3_candidate_now_passes_with_the_declared_reach():
    result, found = codes(REAL)
    assert result['passed'] and result['estimated_max_lag'] == 269
    assert not found & {'UNGUARDED_DIVISION', 'WINDOW_SHORTER_THAN_DECLARED', 'HISTORY_BEYOND_DECLARED', 'NEGATIVE_SHIFT'}


def test_the_vectorised_equivalent_also_passes():
    src = body(['close = panels["close"]', 'r = close / close.shift(5).replace(0, np.nan) - 1.0',
                'out = r.shift(5).rolling(260, min_periods=260).mean()', 'return out.replace([np.inf, -np.inf], np.nan)'])
    result, found = codes(src)
    assert result['passed'] and result['estimated_max_lag'] == 269, found


def test_future_reads_through_loops_are_refused():
    for src in (REAL.replace('range(5, 265)', 'range(-5, 255)'),                  # loop starts in the future
                REAL.replace('close.shift(k)', 'close.shift(-k)'),                  # negated loop variable
                body(['close = panels["close"]', 'n = len(close)', 'return close.shift(-n)'])):   # unproven negative shift
        result, found = codes(src)
        assert not result['passed'] and 'NEGATIVE_SHIFT' in found, src


def test_unprovable_or_wrong_windows_still_fail_closed():
    longer = REAL.replace('range(5, 265)', 'range(5, 300)')                     # beyond the declared history
    assert 'HISTORY_BEYOND_DECLARED' in codes(longer)[1]
    unknown = REAL.replace('ks = range(5, 265)', 'ks = range(5, len(close))')   # bound not provable
    assert 'WINDOW_SHORTER_THAN_DECLARED' in codes(unknown)[1] and not codes(unknown)[0]['passed']
    rebound = REAL.replace('        term = num / den - 1.0', '        k = k - 10\n        term = num / den - 1.0')
    assert not codes(rebound)[0]['passed']                                       # loop variable rebound: range not trusted
    shadow = REAL.replace('    ks = range(5, 265)', '    range = lambda a, b: [-1]\n    ks = range(5, 265)')
    assert not codes(shadow)[0]['passed']                                        # a shadowed `range` is not trusted


def test_only_provably_safe_denominators_are_accepted():
    flagged = {
        'literal zero': body(['close = panels["close"]', 'return close / 0']),
        'name bound to zero': body(['close = panels["close"]', 'n = 0', 'return close / n']),
        'name bound twice': body(['close = panels["close"]', 'n = 260.0', 'n = close.shift(1)', 'return close / n']),
        'unguarded series name': body(['close = panels["close"]', 'den = close.shift(1)', 'return close / den']),
    }
    for label, src in flagged.items():
        assert 'UNGUARDED_DIVISION' in codes(src)[1], label
    accepted = body(['close = panels["close"]', 'den = close.shift(1).replace(0, np.nan)', 'n = 2.0',
                     'return (close / den) / n'])
    assert 'UNGUARDED_DIVISION' not in codes(accepted)[1]


def test_other_refusals_are_unchanged():
    for src, code in ((REAL.replace('import numpy as np', 'import os\nimport numpy as np'), 'IMPORT_NOT_ALLOWED'),
                      (REAL.replace('    close = panels["close"]', '    close = panels["close"]\n    open("x")'), 'FORBIDDEN_CALL'),
                      (REAL.replace('    close = panels["close"]', '    close = panels["close"]\n    exec("1")'), 'FORBIDDEN_CALL'),
                      (REAL.replace('panels["close"]', 'panels["volume"]'), 'UNDECLARED_INPUT')):
        result, found = codes(src)
        assert not result['passed'] and code in found, code
