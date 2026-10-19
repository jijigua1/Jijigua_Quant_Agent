"""Planner regressions found in the live v1.0 Beta acceptance (2026-10-13); offline, no model call.

S1: a weekly paper's window repair counted trading days and was converted again by 5 rows/period (250 -> 1250 days);
    the decision text showed 249 while the code ran 1249; the sample gate fired only after code approval.
S2: a Chinese factor name for an English factor crashed the plan.  S3: straddle returns were offered as stock returns.
"""
import copy
import json
import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).parent / 'fixtures_v1beta'
if not (FIX/'live_model_outputs.json').is_file():
    pytest.skip('Private model replay omitted',allow_module_level=True)
LIVE = json.loads((FIX / 'live_model_outputs.json').read_text(encoding='utf-8'))
REPAIRED = r"ILLIQ_{i,t} = \operatorname{mean}_{k=0}^{249}(\frac{|R_{i,t-k}|}{VOLD_{i,t-k}})"
PROFILE = {'fields': ['open', 'high', 'low', 'close', 'volume', 'amount'], 'train_rows_estimate': 1001,
           'status': 'PROFILED_EXPLORATORY_ONLY', 'adjustment': 'none (raw unadjusted market prices)',
           'units': {'volume': 'lots (100 shares)', 'amount': 'thousand CNY'},
           'splits': {'train': ['2020-01-02', '2023-12-29'], 'valid': ['2024-01-02', '2025-12-31'], 'test': ['2026-01-01', '2026-12-31']},
           'holdout': '2026 evaluated only by the controlled rolling evaluator (aggregates)',
           'certification': {'source': 'synthetic-test', 'level': 'PROFILED_EXPLORATORY_ONLY', 'fields': [],
                             'certified': {'adjusted_prices': False, 'listing_status': False, 'trading_status': False}}}


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    from paper_agent.evidence import PaperEvidence
    root = tmp_path_factory.mktemp('papers')
    shutil.copyfile(FIX / 'amihud2002.pdf', root / 'amihud2002.pdf')
    return PaperEvidence.build(root / 'amihud2002.pdf', cache_dir=root / 'cache', allowed_roots=[root])


def make_plan(evidence, *, freq=None, unit='trading_day', meaning=None, factor=None, profile=PROFILE, pdf_weekly=None):
    from paper_agent.planner import plan
    from paper_agent.understanding import verify
    if pdf_weekly if pdf_weekly is not None else bool(freq):     # the PDF's own data statement (parser), as for the MA paper
        evidence = copy.copy(evidence)
        evidence.spec = copy.deepcopy(evidence.spec)
        evidence.spec['A_supported']['frequency'] = [{'value': 'weekly returns are used in the main study', 'evidence': []}]
    raw = json.loads(LIVE['amihud_understanding'])
    fac = raw['factors'][0]
    fac['formula_latex'] = REPAIRED
    if freq:
        fac['frequency']['value'] = freq
    if meaning:
        next(s for s in fac['symbols'] if s['symbol'] == 'R')['meaning'] = meaning
    u = verify(raw, evidence)
    u['formula_repairs'] = [{'factor': 'ILLIQ', 'error': 'UNSUPPORTED_WINDOW_BOUNDS: _{d = 1}^{D _ { i , y }}', 'repaired': REPAIRED,
                             'note': {'choice': '250-trading-day window', 'reason': 'integer window'}, 'window_unit': unit,
                             'parses_after_repair': True}]
    return plan(evidence, u, copy.deepcopy(profile), factor=factor)[0]


def codes(p):
    return {h['code'] for h in p['hard_stops']}


@pytest.mark.usefixtures("amihud_250_carrier")
def test_daily_plan_question_comes_first_and_states_the_real_lookback(evidence):
    from paper_agent.planner import decision_text
    p = make_plan(evidence)
    assert p['status'] == 'AWAITING_USER_DECISION' and p['warmup_rows'] in (250, 251) and p['choices']['horizon']['n'] == 1
    first, second = decision_text(p).splitlines()[:2]
    assert first.startswith('该论文需要使用') and first.endswith('是否继续？') and f"约{p['warmup_rows']}个交易日" in first and '未复权价格' in first
    assert second.startswith('实际执行（按交易日行计）：') and str(p['warmup_rows']) in second


@pytest.mark.usefixtures("amihud_250_carrier")
def test_trading_day_repair_of_a_weekly_paper_is_not_converted_twice(evidence):
    daily, weekly = make_plan(evidence), make_plan(evidence, freq='weekly (main empirical study)')
    assert weekly['warmup_rows'] == daily['warmup_rows'] < 300                  # was 5x (1250 rows) before the fix
    assert 'time_unit_rows' not in weekly['choices'] and weekly['choices']['horizon']['n'] == 5
    assert any(s['item'] == 'frequency' and 'restated in trading days' in s['ours'] for s in weekly['substitutions'])


@pytest.mark.usefixtures("amihud_250_carrier")
def test_paper_period_window_is_converted_and_an_unfittable_lookback_stops_before_any_gate(evidence):
    p = make_plan(evidence, freq='weekly', unit='paper_period')
    assert p['status'] == 'BLOCKED' and 'LOOKBACK_EXCEEDS_SAMPLE' in codes(p)   # 250 weeks of history > Train
    small = make_plan(evidence, profile=dict(PROFILE, train_rows_estimate=200))  # daily too: 251 rows > a 200-row Train
    assert 'LOOKBACK_EXCEEDS_SAMPLE' in codes(small)


@pytest.mark.usefixtures("amihud_250_carrier")
def test_frequency_text_follows_what_the_task_executes(evidence):
    p = make_plan(evidence, freq='weekly', unit='paper_period', pdf_weekly=False, profile=dict(PROFILE, train_rows_estimate=5000))
    assert 'time_unit_rows' not in p['choices'] and p['warmup_rows'] < 300      # the PDF reads daily: nothing scaled ...
    assert [s['ours'] for s in p['substitutions'] if s['item'] == 'frequency'] == [
        "the paper's data statement reads daily: lags and windows run on daily rows unchanged, factor evaluated every day"]


@pytest.mark.usefixtures("amihud_250_carrier")
def test_unstated_window_unit_on_a_non_daily_paper_blocks(evidence):
    p = make_plan(evidence, freq='weekly', unit=None)
    assert p['status'] == 'BLOCKED' and 'WINDOW_UNIT_AMBIGUOUS' in codes(p)
    assert make_plan(evidence, unit=None)['status'] == 'AWAITING_USER_DECISION'  # daily: unit cannot be ambiguous


@pytest.mark.usefixtures("amihud_250_carrier")
def test_other_instruments_are_never_substituted_by_stock_prices(evidence):
    p = make_plan(evidence, meaning='Monthly return of a one-month at-the-money straddle held to expiration')
    assert p['status'] == 'BLOCKED' and 'INSTRUMENT_NOT_AVAILABLE' in codes(p)


def test_a_translated_factor_name_maps_to_the_papers_only_factor(evidence):
    p = make_plan(evidence, factor='非流动性指标')
    assert p['factor'] == 'ILLIQ' and any('mapped to the paper' in n for n in p['notes'])


def test_library_partial_match_and_continue_resolve_one_paper(tmp_path):
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    for name in ('amihud2002.pdf', 'gh4-paper.pdf'):
        target = lib.root / 'incoming' / ('up-' + name)
        shutil.copyfile(FIX / name, target)
        lib.import_pdf(target, name)
    amihud, gh = sorted(lib.entries(), key=lambda r: r['name'])
    hit = lib.resolve('Hwang 动量 momentum investing')                          # mixed language: best partial match
    assert hit['status'] == 'FOUND' and hit['paper']['sha256'] == gh['sha256']
    lib.touch(amihud['sha256'])
    cont = lib.resolve('继续刚刚中断的论文研究')
    assert cont['status'] == 'FOUND' and cont['paper']['sha256'] == amihud['sha256'] and cont['basis'] == 'most recently researched'
    assert lib.resolve('刚上传的')['paper']['sha256'] == lib.entries()[-1]['sha256']   # 'just uploaded' still means upload order


def test_known_failures_explain_themselves():
    from research_agent.conversation import FAILURE_TEXT
    assert '回看' in FAILURE_TEXT['INSUFFICIENT_RESEARCH_SAMPLE'] and '没有计算' in FAILURE_TEXT['INSUFFICIENT_RESEARCH_SAMPLE']
    assert all('Train' in FAILURE_TEXT[c] for c in ('ARTIFACT_DIRECTORY_UNAVAILABLE', 'STUDY_NOT_IN_SESSION'))


def test_staging_fault_injection_corrupts_one_reply_and_ask_json_recovers(tmp_path, monkeypatch):
    """The pre-release switch breaks only the first paper reply of a process; production never sets it."""
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ask_json
    from research_agent.llm import ModelResponse, Usage
    from research_agent.paper_tools import RuntimeClient
    monkeypatch.setenv('QRA_TEST_CORRUPT_JSON_ONCE', '1')
    monkeypatch.setattr(RuntimeClient, '_fault_used', False)
    calls = []

    def model_call(request):
        calls.append(request)
        return ModelResponse('{"formula_latex": "m = x"}', usage=Usage(1, 1, 2), request_id='r', actual_model='double')
    ledger = TaskLedger(tmp_path, 'f' * 32, goal='t', budget=dict(model_calls=5, total_tokens=10 ** 6, wall_seconds=10 ** 6,
                                                                  design_revisions=2, orchestration_turns=0))
    client = RuntimeClient(model_call)
    obj, _ = ask_json(client, ledger, purpose='formula_repair', system='s', user='u', schema={'type': 'object'})
    assert obj == {'formula_latex': 'm = x'} and len(calls) == 2                    # corrupted once, repaired once
    raws = sorted((tmp_path / 'tasks').rglob('formula_repair_*.json'))
    assert json.loads(raws[0].read_text(encoding='utf-8'))['raw_output'] == '{"formula_latex": "m = x"'
    ask_json(client, ledger, purpose='formula_repair', system='s', user='u', schema={'type': 'object'})
    assert len(calls) == 3                                                            # later replies untouched


def test_production_layout_never_gets_fault_injection():
    import importlib.util
    pytest.importorskip('grp')                                                        # the root launcher is POSIX-only
    spec = importlib.util.spec_from_file_location('launcher_v1', Path(__file__).parents[1] / 'deploy/launcher_v1.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    base = dict(agent_home='/h', test_fault_injection=True)
    assert 'QRA_TEST_CORRUPT_JSON_ONCE' not in launcher.environment(dict(base, root='/opt/jijigua-quant-agent/v1beta'))
    assert launcher.environment(dict(base, root='/opt/jijigua-quant-agent/v1rc'))['QRA_TEST_CORRUPT_JSON_ONCE'] == '1'
    assert 'QRA_TEST_CORRUPT_JSON_ONCE' not in launcher.environment(dict(agent_home='/h', root='/opt/jijigua-quant-agent/v1rc'))


def test_malformed_model_json_is_repaired_once_and_the_raw_reply_is_kept(tmp_path):
    """Live R2: two understanding replies failed the runtime JSON check and were discarded; ask_json now repairs them."""
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ask_json
    from research_agent.llm import ModelResponse, Usage
    from research_agent.paper_tools import JSON_RULE, RuntimeClient
    replies = iter([r'{"formula_latex": "m = \operatorname{mean}_{k=0}^{249}(X)"}',        # \o: invalid JSON escape
                    r'{"formula_latex": "m = \\operatorname{mean}_{k=0}^{249}(X)"}'])
    seen = []

    def model_call(request):
        seen.append(request)
        return ModelResponse(next(replies), usage=Usage(10, 20, 30), request_id='r%d' % len(seen), actual_model='double')
    ledger = TaskLedger(tmp_path, 'k' * 32, goal='t', budget=dict(model_calls=5, total_tokens=10 ** 6, wall_seconds=10 ** 6,
                                                                  design_revisions=2, orchestration_turns=0))
    obj, _ = ask_json(RuntimeClient(model_call), ledger, purpose='formula_repair', system='s', user='u',
                      schema={'type': 'object', 'required': ['formula_latex']})
    assert obj['formula_latex'] == r'm = \operatorname{mean}_{k=0}^{249}(X)' and len(seen) == 2
    assert all(r.output_schema is None and r.messages[-1].content == JSON_RULE for r in seen)    # no blind runtime retry
    assert 'invalid JSON' in seen[1].messages[-2].content                                          # the model was told why
    raws = sorted((tmp_path / 'tasks').rglob('formula_repair_*.json'))
    assert len(raws) == 2 and r'\operatorname' in json.loads(raws[0].read_text(encoding='utf-8'))['raw_output']
