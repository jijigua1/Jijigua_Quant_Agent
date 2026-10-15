"""Deterministic report consistency checks over the files a report was rendered from. No model, no recomputation of
factors; every check compares two saved artifacts. Result: data/report_consistency.json (status PASSED/FAILED)."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

TOL = 1e-12


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(b)))


def check(run, result):
    run = Path(run)
    p = result['metrics']['professional']
    test = p['test']
    completed = test['status'] == 'COMPLETED'
    checks = []

    def record(name, passed, detail=''):
        checks.append(dict(name=name, passed=bool(passed), detail=str(detail)[:300]))

    tables = {t['id']: t for t in json.loads((run / 'data/report_tables.json').read_text(encoding='utf-8'))}
    core = tables.get('core')
    ok, detail = core is not None, 'core table missing'
    if core:
        for row in core['values']:
            split, metric, mean = row[0], row[1], row[2]
            if split in ('train', 'valid'):
                want = next(r['mean'] for r in result['metrics']['predictive'] if r['split'] == split and r['metric'] == metric)
            else:
                want = test['metrics'][metric + '_mean'] if completed else None
            if not _close(mean, want):
                ok, detail = False, f'{split}/{metric}: table {mean} vs metrics {want}'
                break
    record('summary_matches_metrics', ok, detail)

    monthly = pd.read_csv(run / 'data/evaluation_monthly.csv', float_precision='round_trip')
    heat = json.loads((run / 'data/evaluation_heatmaps.json').read_text(encoding='utf-8'))
    ok, detail = True, ''
    for metric in ('rank_ic', 'ic'):
        h = heat[metric]
        for y, year in enumerate(h['years']):
            for m in range(12):
                value = h['z'][y][m]
                row = monthly[monthly.period == f'{year:04d}-{m + 1:02d}']
                want = None if row.empty or pd.isna(row.iloc[0][metric + '_mean']) else float(row.iloc[0][metric + '_mean'])
                if year == 2026 and not completed:
                    want = None
                if not _close(value, want):
                    ok, detail = False, f'{metric} {year}-{m + 1:02d}: heatmap {value} vs csv {want}'
    record('heatmap_matches_monthly_csv', ok, detail)

    daily = pd.read_csv(run / 'data/evaluation_daily.csv', index_col=0, parse_dates=True, float_precision='round_trip')
    test_rows = daily[daily.index >= pd.Timestamp('2026-01-01')]
    if completed:
        receipt_path = run / 'data/test_receipt.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
        result_part = (receipt or {}).get('result', receipt or {})
        same = receipt is not None and result_part.get('evaluation_id') == (test.get('exposure') or {}).get('evaluation_id')
        record('test_status_matches_receipt', same, 'receipt missing or evaluation id differs' if not same else '')
        end = test.get('snapshot', {}).get('certified_end', test.get('end'))
        record('test_dates_within_snapshot', test_rows.index.max() <= pd.Timestamp(end) if len(test_rows) else False,
               f'last test row {test_rows.index.max()} vs certified end {end}')
        if test.get('maturity'):
            immature = set(test['maturity']['immature_signal_dates'])
            from .report_versions import test_daily
            bad = [r['date'] for r in test_daily(run, test) if r['date'] in immature and (r['ic'] is not None or r['rank_ic'] is not None)]
            record('immature_labels_are_na', not bad and len(immature) + test['maturity']['matured_signal_dates'] == test['maturity']['observed_dates'],
                   bad[:3])
    else:
        record('no_test_values_without_evaluation', test_rows[['ic', 'rank_ic']].isna().all().all() if len(test_rows) else True,
               'Test values present although status is ' + test['status'])

    payload = json.loads((run / 'data/evaluation_chart_payload.json').read_text(encoding='utf-8'))
    charts = {c['id']: c for c in payload}
    boundaries = ok = True
    detail = ''
    for name in ('ic_timeline', 'rank_ic_timeline', 'cumulative_correlation', 'coverage_timeline', 'theoretical_groups'):
        c = charts.get(name)
        if c is None:
            ok, detail = False, name + ' missing'
            continue
        lines = [s['x0'] for s in c['layout'].get('shapes', []) if s.get('type') == 'line']
        if len(lines) != 2:
            boundaries, detail = False, name + ': expected 2 phase boundaries, got ' + str(len(lines))
        if completed and name in ('ic_timeline', 'cumulative_correlation', 'coverage_timeline'):
            xs = [x for t in c['traces'] for x, y in zip(t['x'], t['y']) if y is not None and x >= '2026-01-01']
            if not xs:
                ok, detail = False, name + ': completed Test has no 2026 points'
    record('phase_boundaries_present', boundaries, detail)
    record('test_shown_on_timelines', ok, detail)

    groups_path = run / 'data/theoretical_group_paths.csv'
    if groups_path.exists():
        from .interactive_report import noncompounding
        groups = pd.read_csv(run / 'data/group_returns_gross.csv', index_col=0, parse_dates=True, float_precision='round_trip')
        paths = pd.read_csv(groups_path, index_col=0, parse_dates=True, float_precision='round_trip')
        again = noncompounding(groups.reindex(paths.index), int(result['parameters']['horizon']))
        same = np.allclose(again.to_numpy(float), paths.to_numpy(float), rtol=1e-12, atol=1e-15, equal_nan=True)
        record('group_paths_reproduce', same, '' if same else 'theoretical paths differ from group_returns_gross.csv')

    ms_path = run / 'data/metric_system.json'
    if ms_path.exists():
        from .metric_system import STRATEGY_NA
        ms = json.loads(ms_path.read_text(encoding='utf-8'))
        rows = {r['split']: r for r in ms['overall']}
        ok, detail = True, ''
        refs = [('train', p['partitions']['train']), ('valid', p['partitions']['valid'])]
        if completed:
            refs.append(('test', test['metrics']))
        for split, ref in refs:
            for key, want in (('ic_mean', ref['ic_mean']), ('rank_ic_mean', ref['rank_ic_mean']), ('valid_days', ref['rank_ic_n_dates'])):
                if split not in rows or not _close(rows[split].get(key), want):
                    ok, detail = False, f'{split}/{key}: metric system {rows.get(split, {}).get(key)} vs evaluation {want}'
        record('metric_system_matches_partitions', ok and (completed or 'test' not in rows), detail or ('test row without evaluation' if not ok else ''))
        month = {r['period']: r for r in ms['monthly']}
        heat = [c for c in charts.values() if c['traces'] and c['traces'][0].get('type') == 'heatmap']
        ok, detail = len(heat) >= 9, f'{len(heat)} monthly heatmaps'
        keys = {'rank_ic_monthly_heatmap': 'rank_ic_mean', 'ic_monthly_heatmap': 'ic_mean'}
        for c in heat:
            key = keys.get(c['id']) or c['id'][len('heat_'):-len('_monthly')]
            t = c['traces'][0]
            for y, zrow in zip(t['y'], t['z']):
                for m, v in enumerate(zrow, 1):
                    r = month.get(f'{y:04d}-{m:02d}')
                    want = None if r is None else r.get(key)
                    if not _close(v, want):
                        ok, detail = False, f'{c["id"]} {y}-{m:02d}: heatmap {v} vs metric_monthly {want}'
        record('all_monthly_heatmaps_match_metric_system', ok, detail)
        strategy = tables.get('metric_strategy')
        record('strategy_metrics_na_without_accepted_series',
               strategy is not None and all(v == STRATEGY_NA for row in strategy['values'] for v in row[1:]), 'strategy table')

    verdict = p['verdict']['status']
    parts = p['partitions']
    crosses = [s for s in ('train', 'valid') if parts[s]['rank_ic_ci_low'] is None or parts[s]['rank_ic_ci_low'] <= 0 <= parts[s]['rank_ic_ci_high']]
    ok = not (verdict == 'PROMISING_EXPLORATORY' and crosses)
    if completed and verdict == 'PROMISING_EXPLORATORY' and (test['metrics']['rank_ic_n_dates'] or 0) < 60:
        ok = False
    record('verdict_matches_evidence', ok, f'verdict {verdict}; CI crosses 0 in {crosses}')
    record('report_revision_recorded', p.get('report_revision', 1) >= 1)

    report = dict(version='report-consistency/1', status='PASSED' if all(c['passed'] for c in checks) else 'FAILED', checks=checks)
    (run / 'data/report_consistency.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
