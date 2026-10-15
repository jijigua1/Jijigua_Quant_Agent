"""Stage 1 fixes from the live A/B of 2026-10-15 14:03 (src 322ca59a, reader /5). The real DeepSeek replies of the two
nondeterministic cases are replayed offline on the real staging evidence of the same papers (SHA-identical fixtures)."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_v1beta_semantics import PROFILE, load  # noqa: E402

from paper_agent.ledger import TaskLedger  # noqa: E402
from paper_agent.model import ScriptedClient  # noqa: E402
from paper_agent.planner import plan  # noqa: E402
from paper_agent.understanding import understand  # noqa: E402
from paper_research.factor_ir import parse_formula  # noqa: E402
from paper_research.task import _common_lag  # noqa: E402

_live_path = Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_stage1_replies.json'
LIVE = json.loads(_live_path.read_text(encoding='utf-8')) if _live_path.is_file() else {}
pytestmark = pytest.mark.skipif(not LIVE, reason='Private model replay omitted; not claimed passed')


def replay(name, case, tmp_path, user_params=None):
    ev, _ = load(name)
    raw = [r['raw_output'] for r in LIVE[case]['replies'] if r['purpose'] == 'paper_understanding'][-1]
    f = json.loads(raw)['factors'][0]
    agree = [{'formula_latex': f.get('formula_latex'), 'parameters': f.get('parameters') or [], 'symbols': f.get('symbols') or []}] * 3
    client = ScriptedClient({'paper_understanding': [raw], 'formula_repair': [], 'paper_investigation': [],
                             'independent_reading': agree})
    ledger = TaskLedger(tmp_path, goal=case, budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                         design_revisions=2, orchestration_turns=0))
    return ev, understand(ev, client, ledger, user_params=user_params)


def test_a_formation_lag_inside_a_window_is_the_same_dating_convention():
    lag = lambda latex: _common_lag(parse_formula(latex)['ir'])
    assert lag(r'FHH_{i,t} = \frac{P_{i,t-1}}{\max_{0 \le k \le 11} P_{i,t-1-k}}') == 1      # live D09 run 1
    assert lag(r'FHH_{i,t} = \frac{P_{i,t-1}}{high_{i,t-1}}') == 1                            # live D09 run 2 (already right)
    assert lag(r'MOM_{i,t} = \operatorname{mean}_{k=2}^{12} (r_{i,t-k})') == 0                 # a single skipped window keeps its skip
    assert lag(r'MOM_{i,t} = \frac{P_{i,t-1}}{P_{i,t-12}} - 1') == 0                           # different lags: nothing is re-dated
    assert lag(r'X = \operatorname{ema}_{12}(close_{i,t-1})') == 0                            # recursive smoothing is never re-dated


def test_live_d09_run1_reading_now_executes_the_current_52_week_ratio(tmp_path):
    """The reply that executed P[t-21] / max(P[t-k-21]) on 14:03 must give the same factor as run 2: P[t] / max(P[t-k])."""
    ev, u = replay('gh', 'D09_run1', tmp_path)
    f = u['factors'][0]
    p, _, _ = plan(ev, u, PROFILE, factor=f['name'])
    executed = p['execution']['readable'] if isinstance(p.get('execution'), dict) else str(p.get('execution'))
    text = json.dumps(p, ensure_ascii=False)
    assert 'P[t-21]' not in text and 'P[t-k-21]' not in text, executed
    assert 'ts_max_{k=0..251}(P[t-k])' in text and '(P[t] / ' in text


def test_live_d03u_run2_reading_with_the_users_x_is_admitted_on_the_factors_own_days_quote(tmp_path):
    """Run 2's reader left frequency "unstated"; the RSI definition it cites says "X days" (verified verbatim)."""
    ev, u = replay('ti1110', 'D03u_run2', tmp_path, user_params={'X': 14})      # the live request carried X=14
    f = u['factors'][0]
    p, task, _ = plan(ev, u, PROFILE, factor=f['name'])
    stops = {h['code'] for h in p['hard_stops']}
    assert 'ADMISSION_SEMANTICS' not in stops, p['hard_stops']
    assert p['status'] == 'AWAITING_USER_DECISION'
    freq = task['data_schema']['frequency'][0]
    assert freq['value'].startswith('daily') and "factor's own definition, verified verbatim" in freq['value']
    assert 'X days' in freq['evidence'][0]['quote'] and freq['evidence'][0]['location']['page'] == 2


def test_without_a_days_quote_the_frequency_is_still_not_guessed(tmp_path):
    ev, _ = load('ti1110')
    f = json.loads([r['raw_output'] for r in LIVE['D03u_run2']['replies']][-1])['factors'][0]
    f['verbal_definition']['citations'] = [c for c in f['verbal_definition']['citations'] if 'day' not in c['quote']]
    f['formula_citations'] = [c for c in f.get('formula_citations') or [] if 'day' not in c['quote']]
    for prm in f['parameters']:
        prm['citations'] = [c for c in prm['citations'] if 'days' not in c['quote'] and 'day' not in c['quote']]
    raw = json.dumps({**json.loads([r['raw_output'] for r in LIVE['D03u_run2']['replies']][-1]), 'factors': [f]})
    client = ScriptedClient({'paper_understanding': [raw], 'formula_repair': [], 'paper_investigation': [],
                             'independent_reading': [{'formula_latex': f.get('formula_latex'), 'parameters': f['parameters'],
                                                      'symbols': f.get('symbols') or []}] * 3})
    ledger = TaskLedger(tmp_path / 'b', goal='x', budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                             design_revisions=2, orchestration_turns=0))
    u2 = understand(ev, client, ledger, user_params={'X': 14})
    p, _, _ = plan(ev, u2, PROFILE, factor=u2['factors'][0]['name'])
    assert p['status'] == 'BLOCKED'                               # no quote naming the unit: still blocked, never guessed
