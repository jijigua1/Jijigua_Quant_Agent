"""Stage 1 fixes from the live A/B of 2026-10-15 14:03 (src 322ca59a, reader /5). The real DeepSeek replies of the two
nondeterministic cases are replayed offline on the real staging evidence of the same papers (SHA-identical fixtures)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_v1beta_semantics import PROFILE, load  # noqa: E402

from paper_agent.ledger import TaskLedger  # noqa: E402
from paper_agent.model import ScriptedClient  # noqa: E402
from paper_agent.planner import plan  # noqa: E402
from paper_agent.understanding import understand  # noqa: E402
from paper_research.factor_ir import parse_formula  # noqa: E402
from paper_research.task import _common_lag  # noqa: E402

LIVE = json.loads((Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_stage1_replies.json').read_text(encoding='utf-8'))


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


def test_live_alpha101_falls_back_to_the_trusted_ir_executor_without_candidate_permission():
    """J6 14:33: the DSL validator rejects (high-low)+0.001 on units; the trusted-IR route then refused itself."""
    import copy
    import gzip
    import pytest
    from paper_research.candidate import contract_from_task
    from paper_research.errors import PaperError
    if not Path(Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_alpha101_task.json.gz').is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    task = json.load(gzip.open(Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_alpha101_task.json.gz', 'rt', encoding='utf-8'))
    assert task['dsl']['status'] == 'expressible' and not task['admission']['permissions']['may_generate_candidate']
    with pytest.raises(PaperError):
        contract_from_task(task)                                  # model-code candidates keep the stricter permission
    c = contract_from_task(task, trusted_ir=True)
    assert sorted(i['field'] for i in c['inputs']) == ['close', 'high', 'low', 'open']
    blocked = copy.deepcopy(task)
    blocked['admission']['gates']['semantics']['blocking_items'] = ['factor selection']
    with pytest.raises(PaperError):
        contract_from_task(blocked, trusted_ir=True)              # an unresolved definition is never computed


def test_a_derivation_written_with_published_field_names_maps_them(tmp_path):
    """J3 Huatai: A = close_t / close_{t-12} - 1 was reported as "needs ['close'] ... not mapped to published fields"."""
    sys.path.insert(0, str(Path(__file__).parent))
    from test_v1beta_reconcile import cite, factor, reading
    from paper_agent.understanding import verify
    ev, _ = load('huatai')
    q = next(p for p in ev.passages if len(p['text']) > 40 and ev.verify_quote(p['id'], p['text'][10:30]))
    c = cite(ev, q['id'], q['text'][10:30])
    syms = [{"symbol": "A", "meaning": "12-period price change", "kind": "derived", "data_field": None,
             "derivation_latex": r"A_{i,t} = \frac{close_{i,t}}{close_{i,t-12}} - 1", "citations": [c]}]
    f = factor(ev, 'price momentum signal', r"S_{i,t} = \operatorname{sign}(A_{i,t})", syms, cits=[c])
    u = verify(reading(f), ev)
    p, _, _ = plan(ev, u, PROFILE, factor=u['factors'][0]['name'])
    undefined = [h for h in p['hard_stops'] if h['code'] == 'SYMBOL_UNDEFINED' and 'close' in h.get('detail', '')]
    assert not undefined, undefined


READY = json.loads((Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_ready_replies.json').read_text(encoding='utf-8'))
# this file's checks are about the four 10-15/16 runs; later runs in the same fixture are replayed by test_v1beta_canonical
READY = {k: v for k, v in READY.items() if not k.startswith('20261017')}
PAPER = {'D02': 'macd', 'D03': 'ti1110', 'D03u': 'ti1110', 'D04': 'condmat', 'D09': 'gh'}
FACTOR = {'D02': 'MACD', 'D03': 'RSI', 'D03u': 'RSI', 'D04': 'CMI', 'D09': None}


def replay_live(key, tmp_path, investigate=()):
    case = key.split('/')[1].split('#')[0]
    ev, _ = load(PAPER[case])
    rows = READY[key]
    script = {p: [r['raw_output'] for r in rows if r['purpose'] == p] for p in
              ('paper_understanding', 'formula_repair', 'independent_reading', 'paper_investigation')}
    script['paper_understanding'] = script['paper_understanding'][-1:]
    script['paper_investigation'] = script['paper_investigation'] + [json.dumps(x) for x in investigate]
    ledger = TaskLedger(tmp_path, goal=key, budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                        design_revisions=2, orchestration_turns=0))
    u = understand(ev, ScriptedClient(script), ledger, focus=FACTOR[case] or '',
                   user_params={'X': 14} if case == 'D03u' else None)
    name = next((f['name'] for f in u['factors'] if FACTOR[case] and FACTOR[case].lower() in f['name'].lower()), u['factors'][0]['name'])
    return ev, u, name


EXPECTED = {'D02': r'^\(ema\[N=12, [^]]*\]\(close\[t\]\) - ema\[N=26, [^]]*\]\(close\[t\]\)\)$',
            'D03u': r'ts_mean_\{k=0\.\.13\}',
            'D04': r'^\(\(1 / 21\) \* ts_sum_\{k=0\.\.20\}\(\(y\[t-k\] - y\[t-k-21\]\)\)\)$',
            'D09': r'^\(P\[t\] / ts_max_\{k=0\.\.251\}\(P\[t-k\]\)\)$'}


def test_every_real_reading_of_four_live_runs_gives_one_canonical_definition_per_case(tmp_path):
    """38 real DeepSeek readings (four live runs, 10-15/16), replayed through the current program with a model that repeats
    its own reading when asked again: per case, every admitted reading has the SAME canonical definition SHA and executes
    the expected formula; the 13-month reading is caught; RSI without X is blocked every time."""
    import re
    from paper_agent.canonical import definition
    by_case, caught = {}, []
    for i, key in enumerate(sorted(READY)):
        case = key.split('/')[1].split('#')[0]
        rows = READY[key]
        f0 = json.loads([r['raw_output'] for r in rows if r['purpose'] == 'paper_understanding'][-1]) if not             key.endswith('20261016_142232/D09') else None
        insist = [{'action': 'answer', 'factor': f0['factors'][0]}] * 2 if f0 else []
        try:
            ev, u, name = replay_live(key, tmp_path / str(i), investigate=insist)
        except Exception as e:                                        # noqa: BLE001
            by_case.setdefault(case, []).append((key, 'NEEDS_MODEL', str(e)[:80]))
            continue
        f = next(x for x in u['factors'] if x['name'] == name)
        p, task, _ = plan(ev, u, PROFILE, factor=name)
        if p['status'] == 'BLOCKED':
            codes_ = sorted({h['code'] for h in p['hard_stops']})
            by_case.setdefault(case, []).append((key, 'BLOCKED', codes_))
            if 'WINDOW_LENGTH_CONTRADICTS_PAPER' in codes_:
                caught.append(key)
            continue
        _, sha = definition(p, task, u, paper={'sha256': PAPER[case], 'name': PAPER[case], 'version': 1},
                            requested_factor=FACTOR[case] or '')
        assert re.search(EXPECTED[case], p['ir_execution'] or ''), (key, p['ir_execution'])
        by_case.setdefault(case, []).append((key, 'ADMITTED', sha))
    for case in ('D02', 'D03u', 'D04', 'D09'):
        shas = {x[2] for x in by_case[case] if x[1] == 'ADMITTED'}
        assert len(shas) == 1, (case, by_case[case])
    assert all(x[1] == 'BLOCKED' and x[2] == ['FREE_PARAMETER_UNBOUND'] for x in by_case['D03'])
    assert caught == ['20261015_215348/D09']
    blocked = {x[0]: x[2] for c in by_case.values() for x in c if x[1] in ('BLOCKED', 'NEEDS_MODEL')}
    assert set(blocked) <= {'20261015_215348/D09', '20261016_142232/D04#r2'} | {k for k in blocked if '/D03' in k and '/D03u' not in k}


def test_a_plan_made_by_another_program_is_never_reused(tmp_path, monkeypatch):
    """Live recheck J1 22:00: RSI with X=14 was blocked again by a plan cached under the old program (A/B passed 3/3)."""
    import research_agent.paper_tools as pt
    import paper_agent.planner as planner
    ev, u = replay('ti1110', 'D03u_run2', tmp_path, user_params={'X': 14})
    ledger = TaskLedger(tmp_path / 'l', goal='x', budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                             design_revisions=2, orchestration_turns=0))
    pipe = pt.PaperPipeline.__new__(pt.PaperPipeline)
    pipe.backend = type('B', (), {'paper_data_profile': staticmethod(lambda: PROFILE)})()
    calls = []
    real = planner.plan
    monkeypatch.setattr(planner, 'plan', lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    monkeypatch.setattr(pt, '_PROGRAM', 'a' * 64)
    first = pipe._plan(ledger, ev, u, 'RSI')
    again = pipe._plan(ledger, ev, u, 'RSI')
    assert len(calls) == 1 and again['basis_sha256'] == first['basis_sha256']          # same program: cached
    monkeypatch.setattr(pt, '_PROGRAM', 'b' * 64)
    third = pipe._plan(ledger, ev, u, 'RSI')
    assert len(calls) == 2 and third['basis_sha256'] != first['basis_sha256']          # another program: planned again


def test_a_value_typed_in_another_session_never_binds_the_papers_free_parameter(tmp_path):
    """Live J1 23:25: "研究…RSI因子。" without X was proposed as RSI(14) because X=14 was typed in an earlier session."""
    from paper_agent.understanding import reverify
    ev, u = replay('ti1110', 'D03u_run2', tmp_path, user_params={'X': 14})       # session A typed X=14
    assert next(p for p in u['factors'][0]['parameters'] if p['symbol'] == 'X')['status'] == 'USER'
    fresh = reverify(u, ev, {})                                                    # session B typed nothing
    assert fresh['user_parameters'] == {}
    f = fresh['factors'][0]
    assert any(c['code'] == 'FREE_PARAMETER_UNBOUND' and c['blocking'] for c in f['conflicts'])
    p, _, _ = plan(ev, fresh, PROFILE, factor=f['name'])
    assert p['status'] == 'BLOCKED' and 'FREE_PARAMETER_UNBOUND' in {h['code'] for h in p['hard_stops']}
    again = reverify(fresh, ev, {'X': 20})                                         # session C types its own value
    assert next(p for p in again['factors'][0]['parameters'] if p['symbol'] == 'X')['value'] == 20
