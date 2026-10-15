"""ROLLING_EXPOSED_TEST and three-stage reports on synthetic engineering data (not market evidence)."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import v1beta_fixtures as fx_mod
from v1beta_fixtures import REVERSAL, TRAIN, build, broker, context


# ---------------------------------------------------------------- snapshot rules
def test_trailing_incomplete_day_is_trimmed_not_filled():
    from rolling_test.snapshot import select_rows
    days = [d.strftime('%Y%m%d') for d in pd.bdate_range('2024-01-02', '2026-02-27')]
    counts = np.full(len(days), 100)
    counts[-1] = 40                       # the latest day is only partly published
    rows, end, quality = select_rows(days, counts)
    assert end == days[-2][:4] + '-' + days[-2][4:6] + '-' + days[-2][6:]
    assert quality['dropped_incomplete_trailing_dates'] == [days[-1]] and quality['warmup_rows'] == 330
    with pytest.raises(ValueError):
        select_rows(days, counts, today='20260101')            # future rows in the source are refused


def test_snapshot_version_is_content_addressed():
    from rolling_test.snapshot import version_id
    a = {'close': {'bytes': 1, 'sha256': 'a' * 64}}
    b = {'close': {'bytes': 1, 'sha256': 'b' * 64}}
    assert version_id('2026-10-09', a) == version_id('2026-10-09', a) != version_id('2026-10-09', b)
    assert version_id('2026-10-09', a).startswith('rolling_20261009_')


def test_reader_refuses_tampering_and_real_synthetic_mixing(tmp_path):
    from rolling_test.snapshot import SnapshotError, read_snapshot, synthetic_snapshot
    target = synthetic_snapshot(tmp_path)
    sha = hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest()
    panels, universe, m = read_snapshot(target, expected_manifest_sha256=sha, synthetic=True)
    assert m['quality']['dropped_incomplete_trailing_dates'] and panels['close'].index.max() == pd.Timestamp(m['certified_end'])
    with pytest.raises(SnapshotError):
        read_snapshot(target, expected_manifest_sha256=sha, synthetic=False)
    with pytest.raises(SnapshotError):
        read_snapshot(target, expected_manifest_sha256='0' * 64, synthetic=True)


# ---------------------------------------------------------------- full synthetic three-stage study
@pytest.fixture
def three_stage(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    client, b = broker(fx)
    backend.rolling = client
    events = []
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context(events=events))
    return fx, backend, result, events, b


def test_default_rolling_test_produces_a_three_stage_revision(three_stage):
    fx, backend, result, events, _ = three_stage
    assert result['rolling_test']['status'] == 'COMPLETED' and result['report_revision'] == 2
    test = result['metrics']['professional']['test']
    assert test['status'] == 'COMPLETED' and test['evaluation_type'] == 'ROLLING_EXPOSED_TEST'
    assert test['start'] >= '2026-01-01' and Path(result['html_path']).is_file()
    html = Path(result['html_path']).read_text(encoding='utf-8')
    assert 'ROLLING_EXPOSED_TEST' in html and '不是盲测' in html and '2026滚动暴露评价' in html
    revision = Path(result['report_artifact_path'])
    consistency = json.loads((revision / 'data/report_consistency.json').read_text(encoding='utf-8'))
    assert consistency['status'] == 'PASSED', consistency
    # Revision 1 states the pending Test honestly; the original study files are unchanged.
    original = Path(result['factor_path']).parents[1]          # latest_report points artifact_path at the newest revision
    versions = json.loads((original / 'reports/report_versions.json').read_text(encoding='utf-8'))
    assert [v['revision'] for v in versions] == [1, 2] and versions[1]['rolling_status'] == 'COMPLETED'
    assert any(k == 'ROLLING_TEST_OUTCOME' and p['status'] == 'COMPLETED' for k, p in events)


def test_a_long_2026_test_period_fits_the_report_contract(tmp_path):
    """Live 2026-10-13: 185 real Test days made the professional report exceed the 64 KB JSON contract."""
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path, snapshot_end='2026-10-13')
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    assert result['rolling_test']['status'] == 'COMPLETED' and result['report_revision'] == 2
    revision = Path(result['report_artifact_path'])
    test = result['metrics']['professional']['test']
    receipt = json.loads((revision / 'data/test_receipt.json').read_text(encoding='utf-8'))['result']
    assert 'daily' not in test and test['daily_rows'] == len(receipt['test']['daily']) > 150
    assert len(json.dumps(receipt['test']['daily'])) > 40000                     # the rows that broke the inline contract
    from research_agent.report_versions import test_daily
    assert test_daily(revision, test) == receipt['test']['daily']
    assert json.loads((revision / 'data/report_consistency.json').read_text(encoding='utf-8'))['status'] == 'PASSED'
    assert (revision / 'figures/ic_rankic.svg').read_text(encoding='utf-8').count('2026-10') >= 1


def test_a_failed_test_revision_keeps_the_study_and_records_the_failure(tmp_path, monkeypatch):
    """Live 2026-10-13: a revision error turned the whole study into TOOL_EXECUTION_FAILED; Train/Validation were lost."""
    from research_agent import report_versions
    from research_agent.contracts import ContractError
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    real = report_versions.append_rolling_report

    def broken(artifacts, original, outcome):
        if outcome.get('status') == 'COMPLETED':
            raise ContractError('JSON exceeds size limit')
        return real(artifacts, original, outcome)
    monkeypatch.setattr(report_versions, 'append_rolling_report', broken)
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    events = []
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context(events=events))
    assert result['delivery_status'] == 'VERIFIED' and result['splits']['valid']['predictive']['rank_ic']['mean'] is not None
    rt = result['rolling_test']
    assert rt['status'] == 'NOT_EVALUATED' and rt['reason'] == 'FAILED' and rt['report_revision'] == 2
    test = result['metrics']['professional']['test']
    assert test['status'] == 'NOT_EVALUATED' and 'REPORT_REVISION_FAILED' in test['detail']
    assert any(k == 'ROLLING_TEST_OUTCOME' and p['reason'] == 'FAILED' for k, p in events)


def test_static_figures_show_test_or_state_why_not(three_stage):
    """Every static chart of the revision is redrawn with the receipt's Test evidence or says inside the image why it cannot be."""
    fx, backend, result, _, _ = three_stage
    revision = Path(result['report_artifact_path'])
    original = Path(result['factor_path']).parents[1]
    for name in ('ic_rankic', 'ic_distribution', 'group_returns_gross', 'ic_decay', 'factor_distribution', 'factor_autocorrelation'):
        for fmt in ('png', 'svg', 'pdf'):
            new, old = revision / 'figures' / f'{name}.{fmt}', original / 'figures' / f'{name}.{fmt}'
            assert new.is_file() and new.read_bytes() != old.read_bytes(), (name, fmt)       # not the Train/Validation copy
    svg = {n: (revision / 'figures' / f'{n}.svg').read_text(encoding='utf-8') for n in ('ic_rankic', 'group_returns_gross', 'ic_decay')}
    assert all('ROLLING_EXPOSED_TEST' in s and '非盲测' in s for s in svg.values())
    assert 'Test' in svg['group_returns_gross'] and '仅H=5' in svg['ic_decay']
    persistence = (revision / 'figures' / 'factor_autocorrelation.svg').read_text(encoding='utf-8')
    assert '因子持续性' in persistence and '不显示Test持续性' in persistence     # redrawn from stored statistics, Test excluded
    html = Path(result['html_path']).read_text(encoding='utf-8')
    for name in ('ic_distribution', 'group_returns_gross'):
        import base64
        assert base64.b64encode((revision / 'figures' / f'{name}.png').read_bytes()).decode()[:200] in html   # HTML embeds the new image
    assert json.loads((revision / 'data/report_consistency.json').read_text(encoding='utf-8'))['status'] == 'PASSED'


def test_test_statistics_reproduce_independently(three_stage):
    """Daily 2026 IC/RankIC recomputed here with numpy from the synthetic market, not the evaluator code path."""
    fx, backend, result, _, _ = three_stage
    days, codes, fields = fx['market']
    close, open_, volume = (pd.DataFrame(fields[k], index=days, columns=[c[:6] for c in codes]) for k in ('close', 'open', 'volume'))
    factor = -(close / close.shift(5) - 1)
    label = open_.shift(-6) / open_.shift(-1) - 1
    universe = open_.notna() & close.notna() & volume.gt(0)
    receipt = json.loads((Path(result['report_artifact_path']) / 'data/test_receipt.json').read_text(encoding='utf-8'))['result']
    rows = {r['date']: r for r in receipt['test']['daily']}
    end = pd.Timestamp(receipt['snapshot']['certified_end'])
    checked = 0
    for d in days[(days >= '2026-01-01') & (days <= end)]:
        x, y = factor.loc[d].where(universe.loc[d]), label.loc[d]
        ok = x.notna() & y.notna()
        if d > end - pd.tseries.offsets.BDay(6):
            y = y * np.nan                                     # labels beyond the snapshot do not exist
            ok = ok & False
        ic = np.corrcoef(x[ok], y[ok])[0, 1] if ok.sum() >= 10 else None
        got = rows[str(d.date())]['ic']
        assert (ic is None) == (got is None) and (ic is None or abs(ic - got) < 1e-12)
        checked += ic is not None
    assert checked > 30
    immature = receipt['maturity']['immature_signal_dates']
    assert len(immature) == 6 and all(rows[d]['ic'] is None and rows[d]['rank_ic'] is None for d in immature)


def test_same_study_and_snapshot_reuse_the_evaluation(three_stage):
    fx, backend, result, _, _ = three_stage
    original = Path(result['factor_path']).parents[1]
    again = backend.rolling.evaluate(result['study_id'], str(original))
    assert again['status'] == 'COMPLETED' and again['reused'] is True and again['evaluation_id'] == result['rolling_test']['evaluation_id']
    from research_agent.report_versions import append_rolling_report
    same = append_rolling_report(backend.artifacts, original, again)
    assert same['reused'] and same['revision'] == 2


def test_new_trading_days_refresh_a_study_as_a_new_revision(three_stage):
    """Reading a study after new trading days evaluates it on the newer snapshot; revision 2 stays as it was."""
    import hashlib
    from rolling_test.snapshot import select_rows, version_id, write_panel
    from v1beta_fixtures import market
    fx, backend, result, _, b = three_stage
    original = Path(result['factor_path']).parents[1]
    rev2 = sorted(p.name for p in (original.parent).iterdir())
    days, codes, old = market()
    ndays, _, new = market(end='2026-04-30')
    n = len(days)
    fields = {k: np.concatenate([old[k], new[k][n:]]) for k in old}       # history unchanged, new days appended
    keep = ndays >= '2024-01-01'
    d = [x.strftime('%Y%m%d') for x in ndays[keep]]
    f = {k: a[keep] for k, a in fields.items()}
    rows, end, quality = select_rows(d, np.isfinite(f['close']).sum(axis=1))
    src = {k: dict(bytes=int(a.nbytes), sha256=hashlib.sha256(a.tobytes()).hexdigest()) for k, a in fields.items()}
    target = write_panel(fx['snapshot_root'] / version_id(end, src), dates=[d[i] for i in rows], codes=codes,
                         fields={k: a[rows] for k, a in f.items()}, source=src, certified_end=end, quality=quality, implementation={},
                         approval_ref='synthetic', listing_info=dict(certified=False, synthetic=True), synthetic=True)
    b.c['synthetic_snapshot'] = dict(version=target.name, certified_end=end,
                                     manifest_sha256=hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest())
    events = []
    refreshed = backend._refresh_rolling(original, result['study_id'], context(events=events))
    assert refreshed['revision'] == 3 and not refreshed.get('reused')
    assert any(k == 'ROLLING_REFRESH' and p['snapshot'] == target.name and p['certified_end'] > result['rolling_test']['certified_end']
               for k, p in events)
    versions = json.loads((original / 'reports/report_versions.json').read_text(encoding='utf-8'))
    assert [v['revision'] for v in versions] == [1, 2, 3] and versions[1] == json.loads(json.dumps(versions[1]))
    again = backend._refresh_rolling(original, result['study_id'], context())        # same snapshot: reused, no revision 4
    assert again['reused'] and again['revision'] == 3
    assert set(rev2) <= {p.name for p in original.parent.iterdir()}                     # nothing earlier was replaced


def test_a_second_study_of_the_same_definition_reuses_the_evaluation(three_stage):
    """Live 2026-10-13 (second deployment): re-studying the same frozen factor on the same snapshot gave
    REQUEST_FILE_CONFLICT; the evaluation is now reused under a deterministic re-issued receipt for the new study."""
    fx, backend, first, _, b = three_stage
    second = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context(task_id='b' * 32))
    r1, r2 = first['rolling_test'], second['rolling_test']
    assert second['study_id'] != first['study_id']
    assert r2['status'] == 'COMPLETED' and r2['reused'] is True and r2['evaluation_id'] != r1['evaluation_id']
    rec = json.loads((Path(second['report_artifact_path']) / 'data/test_receipt.json').read_text(encoding='utf-8'))['result']
    old = json.loads((Path(first['report_artifact_path']) / 'data/test_receipt.json').read_text(encoding='utf-8'))['result']
    assert rec['reissued_from'] == r1['evaluation_id'] and rec['study_id'] == second['study_id']
    assert rec['test']['metrics'] == old['test']['metrics'] and rec['test']['daily'] == old['test']['daily']   # no new computation
    again = backend.rolling.evaluate(second['study_id'], str(Path(second['factor_path']).parents[1]))
    assert again['status'] == 'COMPLETED' and again['evaluation_id'] == r2['evaluation_id']                      # deterministic
    from research_agent.report_versions import append_rolling_report
    assert append_rolling_report(backend.artifacts, Path(second['factor_path']).parents[1], again)['revision'] == 2


def test_theoretical_group_paths_are_noncompounding_and_reproduce(three_stage):
    fx, backend, result, _, _ = three_stage
    run = Path(result['report_artifact_path'])
    groups = pd.read_csv(run / 'data/group_returns_gross.csv', index_col=0, parse_dates=True)
    paths = pd.read_csv(run / 'data/theoretical_group_paths.csv', index_col=0, parse_dates=True)
    assert (groups.index >= '2026-01-01').any()                       # Test daily groups merged
    sampled = groups.reindex(paths.index)['0'].iloc[::5].dropna()      # same timeline and phase as the chart
    expected = (1 + sampled).prod() - 1
    assert abs(paths['0'].dropna().iloc[-1] - expected) < 1e-12
    naive = groups['0'].sum()                                          # the old overlapping arithmetic sum
    assert abs(naive) > abs(expected) * 2                              # roughly H times larger, as documented
    payload = json.loads((run / 'data/evaluation_chart_payload.json').read_text(encoding='utf-8'))
    chart = next(c for c in payload if c['id'] == 'theoretical_groups')
    assert '互不重叠' in chart['layout']['title'] and '不是账户净值' in chart['layout']['title']


def test_unauthorized_deployment_reports_not_evaluated(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx, authorized=False)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    test = result['metrics']['professional']['test']
    assert test['status'] == 'NOT_EVALUATED' and test['reason'] == 'NOT_AUTHORIZED' and result['report_revision'] == 1
    run = Path(result['factor_path']).parents[1]
    heat = json.loads((run / 'data/evaluation_heatmaps.json').read_text(encoding='utf-8'))
    assert all(v is None for v in heat['rank_ic']['z'][heat['rank_ic']['years'].index(2026)])
    assert json.loads((run / 'data/report_consistency.json').read_text())['status'] == 'PASSED'
    assert not list((tmp_path / 'requests').iterdir())               # nothing was requested


def test_no_broker_means_evaluator_unavailable(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    assert result['metrics']['professional']['test']['reason'] == 'EVALUATOR_UNAVAILABLE'


def test_revised_history_is_detected_and_not_merged(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path, shock_2025=True)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    test = result['metrics']['professional']['test']
    assert test['status'] == 'NOT_EVALUATED' and test['reason'] == 'HISTORY_MISMATCH'
    assert not list((tmp_path / 'receipts').glob('*.json'))


def test_broker_refuses_paths_outside_research_root_and_bad_messages(three_stage, tmp_path):
    fx, backend, result, _, b = three_stage
    out = b.handle({'op': 'evaluate', 'study_id': result['study_id'], 'artifact_path': str(tmp_path)})
    assert out['status'] == 'NOT_EVALUATED' and 'STUDY_OUTSIDE_RESEARCH_ROOT' in out['detail']
    original = str(Path(result['factor_path']).parents[1])
    out = b.handle({'op': 'evaluate', 'study_id': result['study_id'], 'artifact_path': original, 'expression': {}})
    assert out['status'] == 'NOT_EVALUATED' and 'INVALID_REQUEST' in out['detail']
    other = b.handle({'op': 'evaluate', 'study_id': 'b' * 32 + ':' + 'c' * 16, 'artifact_path': original})
    assert 'STUDY_ID_MISMATCH' in other['detail']
    lines = Path(b.c['audit_path']).read_text().splitlines()
    previous = '0' * 64
    for line in lines:                                   # hash-chained audit
        row = json.loads(line)
        sha = row.pop('sha256')
        assert row['previous'] == previous and hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest() == sha
        previous = sha


@pytest.mark.skipif(os.name != 'posix', reason='symlink creation requires POSIX privileges on Windows')
def test_broker_refuses_symlinked_study(three_stage, tmp_path):
    fx, backend, result, _, b = three_stage
    original = Path(result['factor_path']).parents[1]
    link = original.parent / 'linked_study'
    link.symlink_to(original)
    out = b.handle({'op': 'evaluate', 'study_id': result['study_id'], 'artifact_path': str(link)})
    assert out['status'] == 'NOT_EVALUATED' and 'LINK' in out['detail']


def test_evaluator_refuses_changed_definition_and_excess_warmup(three_stage):
    fx, backend, result, _, _ = three_stage
    from rolling_test.evaluator import EvaluationDenied, evaluate
    request = json.loads(next(Path(fx['tmp'] / 'requests').iterdir()).read_text(encoding='utf-8'))
    bad = dict(request, frozen=dict(request['frozen'], horizon=3))
    with pytest.raises(EvaluationDenied):
        evaluate(bad, snapshot_root=fx['snapshot_root'], ledger_path=fx['tmp'] / 'eval' / 'x.sqlite', key=fx_mod.KEY, synthetic=True)
    from rolling_test.factors import fingerprint
    frozen = dict(request['frozen'], warmup=400)
    with pytest.raises(EvaluationDenied):
        evaluate(dict(request, frozen=frozen, definition_sha256=fingerprint(frozen)), snapshot_root=fx['snapshot_root'],
                 ledger_path=fx['tmp'] / 'eval' / 'x.sqlite', key=fx_mod.KEY, synthetic=True)
