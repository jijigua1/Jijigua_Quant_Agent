"""Stage 3 (2026-10-15): the complete factor metric system and its report order. Synthetic engineering data only; the numbers
here are not market evidence."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from v1beta_fixtures import REVERSAL, TRAIN, build, broker, context

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


@pytest.fixture(scope='module')
def studies(tmp_path_factory):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    out = {}
    for name, authorized in (('rolling', True), ('sealed', False)):
        fx = build(tmp_path_factory.mktemp(name))
        backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
        backend.rolling, _ = broker(fx, authorized=authorized)
        result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
        out[name] = (result, Path(result.get('report_artifact_path') or Path(result['factor_path']).parents[1]))
    return out


def numcheck(run):
    import importlib.util
    spec = importlib.util.spec_from_file_location('numcheck_metrics', TOOLS / 'numcheck_metrics.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main([str(run)])


def test_the_html_follows_overall_annual_heatmaps_groups_and_shows_every_heatmap(studies):
    result, run = studies['rolling']
    assert result['metrics']['professional']['test']['status'] == 'COMPLETED'
    html = (run / 'reports/report.html').read_text(encoding='utf-8')
    marks = [html.index(s) for s in ('一、总体评价', '二、逐年评价', '三、月度热力图', '四、G0–G4 分组明细')]
    assert marks == sorted(marks)
    payload = json.loads((run / 'data/evaluation_chart_payload.json').read_text(encoding='utf-8'))
    heat = [c for c in payload if c['traces'][0]['type'] == 'heatmap']
    assert len(heat) >= 9 and all('id="' + c['id'] + '"' in html for c in heat)    # all rendered at once
    assert '<select' not in html                                                       # no metric switcher
    assert all(c['traces'][0]['y'][-1] == 2026 for c in heat)
    tables = {t['id'] for t in json.loads((run / 'data/report_tables.json').read_text(encoding='utf-8'))}
    assert {'metric_overall_predictive', 'metric_overall_hac', 'metric_overall_sample', 'metric_strategy', 'metric_annual',
            'metric_groups_annual', 'metric_groups_monthly'} <= tables
    assert json.loads((run / 'data/report_consistency.json').read_text(encoding='utf-8'))['status'] == 'PASSED'


def test_every_metric_is_reproduced_by_independent_code(studies):
    for name in ('rolling', 'sealed'):
        assert numcheck(studies[name][1]) == 0, name


def test_the_overall_rows_agree_with_the_existing_partition_and_test_statistics(studies):
    result, run = studies['rolling']
    ms = json.loads((run / 'data/metric_system.json').read_text(encoding='utf-8'))
    p = result['metrics']['professional']
    rows = {r['split']: r for r in ms['overall']}
    for split, ref in [('train', p['partitions']['train']), ('valid', p['partitions']['valid']), ('test', p['test']['metrics'])]:
        for m in ('ic', 'rank_ic'):
            assert rows[split][m + '_mean'] == pytest.approx(ref[m + '_mean'], rel=1e-12, abs=1e-15)
            assert rows[split][m + '_n'] == ref[m + '_n_dates']
        assert rows[split]['valid_days'] == ref['rank_ic_n_dates']


def test_without_an_evaluated_test_2026_is_na_everywhere_and_strategy_metrics_are_na(studies):
    from research_agent.metric_system import STRATEGY_NA
    result, run = studies['sealed']
    assert result['metrics']['professional']['test']['status'] == 'NOT_EVALUATED'
    ms = json.loads((run / 'data/metric_system.json').read_text(encoding='utf-8'))
    assert {r['split'] for r in ms['overall']} == {'train', 'valid'} and not [r for r in ms['monthly'] if r['period'] >= '2026']
    payload = json.loads((run / 'data/evaluation_chart_payload.json').read_text(encoding='utf-8'))
    for c in (c for c in payload if c['traces'][0]['type'] == 'heatmap'):
        t = c['traces'][0]
        assert all(v is None for v in t['z'][t['y'].index(2026)]), c['id']
    html = (run / 'reports/report.html').read_text(encoding='utf-8')
    assert html.count(STRATEGY_NA) >= 15 and 'NOT_AUTHORIZED' in html
    strategy = next(t for t in json.loads((run / 'data/report_tables.json').read_text(encoding='utf-8')) if t['id'] == 'metric_strategy')
    assert all(v == STRATEGY_NA for row in strategy['values'] for v in row[1:])


def test_period_rules_win_rate_hac_gate_monotonicity_and_g0_is_highest():
    from research_agent.metric_system import period
    idx = pd.bdate_range('2021-01-04', periods=80)
    rng = np.random.default_rng(5)
    rows = pd.DataFrame({'split': 'train', 'ic': rng.normal(.02, .1, 80), 'rank_ic': rng.normal(.03, .1, 80),
                         'coverage': .9, 'n_pairs': 100.0}, index=idx)
    for g in range(5):
        rows['G%d' % g] = .01 * (4 - g) + rng.normal(0, .001, 80)          # G0 highest by construction
    rows.loc[idx[10], 'rank_ic'] = np.nan
    rows['spread'] = rows['G0'] - rows['G4']
    from research_agent.metric_system import _monotonic
    rows['monotonicity'] = [_monotonic(r) for r in rows[['G%d' % g for g in range(5)]].to_numpy()]
    full = period(rows, 1, 5, 'x', 'train')
    v = rows['rank_ic'].dropna()
    assert full['rank_ic_win_rate'] == pytest.approx((v > 0).mean()) and full['valid_days'] == 79
    assert full['rank_ic_hac_status'] == 'insufficient' and full['rank_ic_t'] is None      # interior gap: no HAC, not filled
    assert full['ic_hac_status'] == 'approximate' and full['ic_t'] == pytest.approx(full['ic_mean'] / full['ic_se'])
    assert full['monotonicity'] == pytest.approx(1.0) and full['monotonicity_of_means'] == pytest.approx(1.0)
    assert full['G0_mean'] > full['G4_mean'] and full['spread_mean'] == pytest.approx(full['G0_mean'] - full['G4_mean'])
    short = period(rows.iloc[:30], 1, 5, 'm', 'train', hac=False)
    assert 'rank_ic_t' not in short and short['strategy'].startswith('N/A')


def test_annual_hac_covers_ic_rankic_and_the_spread_and_names_the_reason_for_na(studies):
    result, run = studies['rolling']
    table = next(t for t in json.loads((run / 'data/report_tables.json').read_text(encoding='utf-8')) if t['id'] == 'metric_annual_hac')
    series = {str(r[0]).rsplit(' / ', 1)[-1] for r in table['values']}
    assert series == {'IC', 'RankIC', 'G0−G4'}
    years = {str(r[0]).split(' / ')[0] for r in table['values']}
    assert len(table['values']) == 3 * len(years)
    for row in table['values']:
        status = row[-1]
        if status.startswith('N/A'):
            assert row[2] is None and row[4] is None and ('少于要求' in status or '缺失' in status or '未评价' in status), row
        else:
            assert row[2] is not None and row[4] is not None
    html = (run / 'reports/report.html').read_text(encoding='utf-8')
    assert '为什么月度没有HAC显著性' in html and '月度HAC t、p和区间一律为N/A' in html
    ms = json.loads((run / 'data/metric_system.json').read_text(encoding='utf-8'))
    assert all('rank_ic_t' not in m for m in ms['monthly'])                   # no monthly HAC is computed at all
