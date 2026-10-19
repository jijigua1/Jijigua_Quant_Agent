"""A paper factor OUTSIDE the trusted grammar (a 60-day running maximum drawdown is path dependent): the reviewed pair route.

Mechanism test with scripted model replies (the real-paper check is part of the live acceptance): the understanding states
an algorithm with verified quotes (Amihud's own definition text), the plan asks for a definition decision that says the
2026 Test cannot be evaluated, two independently written implementations are reviewed together, they must agree after
approval, the study cross-checks a column sample against reference(), and the rolling Test is honestly NOT_EVALUATED.
"""
import json
from pathlib import Path

import pytest

from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ModelResponse
from test_v1beta_papers import FIX, LIVE, RATIONALE, PaperProvider, decision, paper_call, stage, studies
from v1beta_fixtures import broker, build

COMPUTE = '''import numpy as np
import pandas as pd


def compute(panels):
    p = panels["close"].astype(float)
    vals = [p.shift(k) for k in range(59, -1, -1)]
    peak = vals[0]
    worst = vals[0] * 0.0
    for v in vals[1:]:
        peak = np.maximum(peak, v)
        worst = np.minimum(worst, v / peak.replace(0, np.nan) - 1.0)
    valid = p.notna().astype(float).rolling(60, min_periods=60).sum().eq(60)
    return worst.where(valid).replace([np.inf, -np.inf], np.nan)
'''
REFERENCE = '''import numpy as np
import pandas as pd


def reference(panels):
    p = panels["close"]
    out = pd.DataFrame(np.nan, index=p.index, columns=p.columns)
    n = 60
    for j, c in enumerate(p.columns):
        x = p[c].to_numpy(dtype=float)
        for t in range(n - 1, len(x)):
            w = x[t - n + 1:t + 1]
            if not np.isfinite(w).all():
                continue
            peak = w[0]
            worst = 0.0
            for v in w:
                peak = max(peak, v)
                worst = min(worst, v / peak - 1.0) if peak != 0 else np.nan
            out.iloc[t, j] = worst
    return out
'''


def algorithm_understanding():
    u = json.loads(LIVE['amihud_understanding'])
    f = u['factors'][0]
    f.update(name='60-day maximum drawdown', formula_latex='', formula_status='algorithm',
             algorithm={'steps': ['for each stock and day t take the last 60 daily closing prices (t-59..t)',
                                  'walk forward through the window keeping the running maximum price',
                                  'the factor is the most negative value of price / running maximum - 1 inside the window'],
                        'inputs': ['R'], 'lookback': {'n': 60, 'unit': 'trading_day'},
                        'citations': f['verbal_definition']['citations'][:1]})
    for s in f['symbols']:
        if s['symbol'] == 'R':
            s.update(kind='raw_field', data_field='returns')
    u['factors'] = [f]
    return canonical(u)


class AlgorithmProvider(PaperProvider):
    def __init__(self, decisions):
        super().__init__(decisions)
        self.queues = {'understanding': [algorithm_understanding()], 'repair': [], 'rationale': [canonical(RATIONALE)],
                       'design': [canonical({'design': {'summary': 'vectorised running drawdown', 'missing_dsl_capabilities': ['path dependence'],
                                                        'algorithm_steps': ['running max'], 'window_semantics': '60 rows', 'nan_policy': 'propagate'},
                                             'source': COMPUTE})],
                       'reference': [canonical({'source': REFERENCE, 'notes': 'literal loops'})]}

    def complete(self, request):
        if (request.output_schema == {'type': 'object'} or paper_call(request)) and 'REFERENCE implementation' in request.messages[0].content:
            self.calls.append(request)
            return ModelResponse(self.queues['reference'].pop(0))
        return super().complete(request)


@pytest.fixture
def patched_rolling(monkeypatch):
    holder = {}
    from research_agent import rolling_client
    monkeypatch.setattr(rolling_client.RollingClient, 'from_environment', classmethod(lambda cls: holder.get('client') or cls()))
    return holder


@pytest.fixture(autouse=True)
def legacy_reviewed_pair_compatibility(monkeypatch):
    # These I4 fixtures exercise the retained reviewed-pair fallback, including
    # archived code approvals. I5 defaults to autonomous_python, covered by the
    # calendar and path-dependent cases in test_autonomous_cli_pipeline.py.
    from paper_agent import autonomous_route
    monkeypatch.setattr(autonomous_route, 'eligible', lambda plan: False)


def test_a_path_dependent_paper_factor_runs_as_a_reviewed_pair_and_is_honest_about_test(tmp_path, patched_rolling):
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = AlgorithmProvider([decision('skill', skill_id='paper_research', goal='研究我刚上传的论文'),
                                  decision(consent='accept'), decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    first = app.turn('研究我刚上传的论文。')
    assert '算法步骤' in first and '2026 Test' in first and '不可评价' in first and not studies(fx)
    second = app.turn('同意')
    assert '回复“同意”即批准运行这一份代码' in second and 'def compute(panels)' in second and 'def reference(panels)' in second
    assert '另一次模型调用写成' in second and not studies(fx)
    third = app.turn('同意')
    assert 'Test（2026）：未评价' in third and '不运行模型代码' in third
    entry = json.loads(next((tmp_path / 'papers/approved_code/entries').iterdir()).read_text())
    names = [t['name'] for t in entry['tests']]
    assert entry['status'] == 'TRUSTED_REGISTERED' and all(t['passed'] for t in entry['tests'])
    assert {'agreement_seed20261014', 'agreement_seed20261014_no_lookahead', 'agreement_seed20261014_set_nan',
            'agreement_seed20261014_set_zero'} <= set(names)
    task_id = app.store.session_turns(app.session_id)[-1]['research_task_id']
    data = next(e['result']['data'] for e in app.store.load(task_id).experiments if e['tool'] == 'qrtk_paper_research')
    cross = data['implementation_crosscheck']
    assert cross and cross[0]['checked_against'].startswith('approved reference()') and cross[0]['cells_outside_tolerance'] == 0
    assert cross[0]['nan_pattern_mismatch'] == 0 and cross[0]['non_nan_cells'] > 0
    assert data['paper']['route'] == 'algorithm'
    test = data['metrics']['professional']['test']
    assert test['status'] == 'NOT_EVALUATED' and test['reason'] == 'UNSUPPORTED_STUDY' and '不运行模型代码' in test['detail']


@pytest.mark.parametrize("wrong,why", [
    (COMPUTE.replace("range(59, -1, -1)", "range(58, -1, -1)"), "window one day short"),
    (COMPUTE.replace("v / peak.replace(0, np.nan) - 1.0", "v / peak - 1.0"), "harmless rewrite"),
])
def test_a_wrong_vectorised_implementation_is_rejected_after_approval(tmp_path, patched_rolling, wrong, why):
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = AlgorithmProvider([decision('skill', skill_id='paper_research', goal='研究我刚上传的论文'),
                                  decision(consent='accept'), decision(consent='accept')])
    provider.queues['design'][0] = canonical({'design': {'summary': why, 'missing_dsl_capabilities': [], 'algorithm_steps': [],
                                                         'window_semantics': '', 'nan_policy': ''}, 'source': wrong})
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    app.turn('同意')
    third = app.turn('同意')
    entries = list((tmp_path / 'papers/approved_code/entries').iterdir())
    entry = json.loads(entries[0].read_text())
    if why == "harmless rewrite":                     # an equivalent rewrite still agrees: no false rejection
        assert entry['status'] == 'TRUSTED_REGISTERED' and studies(fx)
    else:
        assert entry['status'] == 'REJECTED_AFTER_TESTS' and not studies(fx) and '真值测试' in third
        assert not all(t['passed'] for t in entry['tests'])
