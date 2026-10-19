"""A paper factor on the trusted IR route keeps the full three-stage contract, including the 2026 rolling Test.

The study runs the reviewed executor (no model code), the broker freezes the IR, the independent evaluator recomputes it
on the 2026 snapshot, and the receipt's daily IC is reproduced here from the synthetic market with the literal-recursion
reference evaluator -- a different implementation from both the study and the evaluator code path.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from v1beta_fixtures import TRAIN, build, broker, context

MACD = (r"2 * ( \operatorname{ema}_{12}(C_{i,t}) - \operatorname{ema}_{26}(C_{i,t})"
        r" - \operatorname{ema}_{9}( \operatorname{ema}_{12}(C_{i,t}) - \operatorname{ema}_{26}(C_{i,t}) ) )")


@pytest.fixture
def macd_study(tmp_path):
    from paper_research.factor_ir import parse_formula
    from paper_agent.study_bridge import ir_latex
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    client, b = broker(fx)
    backend.rolling = client
    ir = parse_formula(MACD)["ir"]
    events = []
    result = backend.trusted_ir_study(TRAIN, ir, {"C": "close"}, 'MACD柱（论文因子）', '合成工程验收', 5, 5, 'raw',
                                      context(events=events), factor_name='macd_hist', latex=ir_latex(ir))
    return fx, backend, result, ir


def test_trusted_ir_study_completes_three_stages_with_a_crosscheck(macd_study):
    fx, backend, result, ir = macd_study
    assert result['rolling_test']['status'] == 'COMPLETED'
    test = result['metrics']['professional']['test']
    assert test['status'] == 'COMPLETED' and test['evaluation_type'] == 'ROLLING_EXPOSED_TEST'
    cross = result['implementation_crosscheck']
    assert cross and cross[0]['cells_outside_tolerance'] == 0 and cross[0]['nan_pattern_mismatch'] == 0
    original = Path(result['factor_path']).parents[1]
    definition = json.loads((original / 'code/factor_definition.json').read_text(encoding='utf-8'))
    from research_agent.quant import trusted_ir_sha256
    assert definition['kind'] == 'trusted_ir' and definition['executor_sha256'] == trusted_ir_sha256()
    assert definition['warmup_observations'] == 90 + 31 + 1
    consistency = json.loads((Path(result['report_artifact_path']) / 'data/report_consistency.json').read_text(encoding='utf-8'))
    assert consistency['status'] == 'PASSED'


def test_test_ic_reproduces_with_the_literal_recursion_reference(macd_study):
    from paper_research.factor_ir import evaluate as reference
    fx, backend, result, ir = macd_study
    days, codes, fields = fx['market']
    close, open_, volume = (pd.DataFrame(fields[k], index=days, columns=[c[:6] for c in codes]) for k in ('close', 'open', 'volume'))
    factor = reference(ir, {'close': close}, {'C': 'close'})
    label = open_.shift(-6) / open_.shift(-1) - 1
    universe = open_.notna() & close.notna() & volume.gt(0)
    receipt = json.loads((Path(result['report_artifact_path']) / 'data/test_receipt.json').read_text(encoding='utf-8'))['result']
    rows = {r['date']: r for r in receipt['test']['daily']}
    end = pd.Timestamp(receipt['snapshot']['certified_end'])
    checked = 0
    for d in days[(days >= '2026-01-01') & (days <= end - pd.tseries.offsets.BDay(6))]:
        x, y = factor.loc[d].where(universe.loc[d]), label.loc[d]
        ok = x.notna() & y.notna()
        ic = np.corrcoef(x[ok], y[ok])[0, 1] if ok.sum() >= 10 else None
        got = rows[str(d.date())]['ic']
        assert (ic is None) == (got is None) and (ic is None or abs(ic - got) < 1e-10), (d, ic, got)
        checked += ic is not None
    assert checked > 30


def test_a_changed_executor_is_refused_for_an_existing_study(macd_study, monkeypatch):
    """Stage 2 F (2026-10-15): the gate is the recorded numerical-semantics version, not the executor file bytes; a study is
    recomputed under its own version and still cross-checked against the reference evaluator. An unknown version is refused."""
    fx, backend, result, ir = macd_study
    original = Path(result['factor_path']).parents[1]
    definition = json.loads((original / 'code/factor_definition.json').read_text(encoding='utf-8'))
    from paper_research.factor_ir import IR_SEMANTICS
    from research_agent.security import Denied
    assert definition['ir_semantics'] == IR_SEMANTICS
    with pytest.raises(Denied):
        backend._trusted_ir_compute(dict(definition, ir_semantics='trusted-ir-semantics/99'), {'close': pd.DataFrame({'a': [1.0, 2.0]})})


def test_an_invalid_definition_is_marked_without_changing_history(macd_study, tmp_path):
    """Append-only register + one invalidation revision; earlier files stay byte-identical; no further evaluation."""
    import hashlib
    import runpy
    import sys as _sys
    from research_agent.invalidations import InvalidationError, path as reg_path, records
    fx, backend, result, ir = macd_study
    original = Path(result['factor_path']).parents[1]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in original.rglob('*') if p.is_file()
              and p.name not in ('manifest.json', 'report_versions.json')}
    old_revisions = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(result['report_artifact_path']).rglob('*') if p.is_file()}
    tool = Path(__file__).resolve().parents[1] / 'tools' / 'invalidate_study.py'
    argv = ['invalidate_study.py', '--workspace', str(fx['workspace']), '--study-dir', str(original),
            '--code', 'DEFINITION_LOOKBACK_READ_AS_LAG', '--evidence', '原文：past 1-, 3- and 12-month returns',
            '--evidence', '执行：C[t-21]/C[t-42]-1', '--recorded-by', 'operator-test']
    old_argv, _sys.argv = _sys.argv, argv
    try:
        runpy.run_path(str(tool), run_name='__main__')
        runpy.run_path(str(tool), run_name='__main__')                   # idempotent: no second record or revision
    finally:
        _sys.argv = old_argv
    recs = records(fx['workspace'])
    assert len(recs) == 1 and recs[0]['code'] == 'DEFINITION_LOOKBACK_READ_AS_LAG'
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())          # study files unchanged
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in old_revisions.items())   # earlier revision unchanged
    versions = json.loads((original / 'reports/report_versions.json').read_text(encoding='utf-8'))
    assert versions[-1]['rolling_status'] == 'INVALIDATED' and len(versions) == 3
    html = Path(versions[-1]['html']).read_text(encoding='utf-8')
    assert '研究定义无效' in html and '回看期累计收益被执行成了滞后单期收益' in html
    from research_agent.invalidations import lookup
    from research_agent.report_versions import latest_report
    latest = latest_report(backend.artifacts, original, json.loads((original / 'data/analysis.json').read_text(encoding='utf-8')),
                           backend.rolling)
    assert latest['report_revision'] == 3 and latest['html_path'] == versions[-1]['html']
    assert lookup(fx['workspace'], result['study_id'])['code'] == 'DEFINITION_LOOKBACK_READ_AS_LAG'
    # a tampered register is detected
    lines = reg_path(fx['workspace']).read_text(encoding='utf-8').replace('operator-test', 'someone-else')
    reg_path(fx['workspace']).write_text(lines, encoding='utf-8')
    reg_path(fx['workspace']).write_text(lines + json.dumps({'study_id': 'x', 'prev_sha256': '0' * 64}) + '\n', encoding='utf-8')
    with pytest.raises(InvalidationError):
        records(fx['workspace'])
