"""quantagent-run regression of v1.0 Beta against verified baselines (read-only for production artifacts).

1. Production five-day reversal, latest revision (r4): read through the v1 report path; compare partition statistics
   with the accepted values; prove the production study and revision files are byte-identical before/after.
2. Alpha#53 (Phase 4, independently verified): recompute Train/Validation with the v1 pipeline on the real published
   releases (no model call; DSL expression from the Phase 4 study) and compare every metric with the Phase 4 run.
No 2026 data is read; the isolated broker is not attached (status EVALUATOR_UNAVAILABLE is expected).
"""
import hashlib
import json
import sys
import time
from pathlib import Path

R = Path('/opt/jijigua-quant-agent/v1beta')
sys.path[:0] = [str(R / 'src'), str(R / 'src/rolling_test/vendor')]
PROD_RUNS = Path('/srv/jijigua-quant-agent/research_runs')
REVERSAL = PROD_RUNS / '2026-10-13/01-33-21_reversal_5d'
ACCEPTED_R4 = {'train': (0.020367376934, 0.026380421612, 959), 'valid': (0.043337659475, 0.046300839332, 479),
               'test': (-0.000863362188, 0.004014245450, 177)}
ALPHA53 = Path('/srv/jijigua-quant-agent/claude_p4/research_runs/2026-10-13/01-04-45_alpha_53')


def tree_digest(root):
    files = sorted(p for p in root.rglob('*') if p.is_file())
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    out = {}
    from research_agent.artifacts import ResearchArtifacts
    from research_agent.report_versions import latest_report
    versions = json.loads((REVERSAL / 'reports/report_versions.json').read_text(encoding='utf-8'))
    revision_dirs = [Path(v['artifact_path']) for v in versions if v.get('artifact_path')]
    before = {str(d): tree_digest(d) for d in [REVERSAL] + revision_dirs}
    artifacts = ResearchArtifacts('/srv/jijigua-quant-agent')
    analysis = json.loads((REVERSAL / 'data/analysis.json').read_text(encoding='utf-8'))
    latest = latest_report(artifacts, REVERSAL, analysis)
    p = latest['metrics']['professional']
    got = {'train': p['partitions']['train'], 'valid': p['partitions']['valid'], 'test': p['test']['metrics']}
    rows = {}
    for split, (ic, ric, n) in ACCEPTED_R4.items():
        g = got[split]
        rows[split] = dict(ic=g['ic_mean'], rank_ic=g['rank_ic_mean'], n=g['rank_ic_n_dates'],
                           match=abs(g['ic_mean'] - ic) < 1e-12 and abs(g['rank_ic_mean'] - ric) < 1e-12 and g['rank_ic_n_dates'] == n)
    after = {str(d): tree_digest(d) for d in [REVERSAL] + revision_dirs}
    out['production_reversal_r4'] = dict(revision=latest['report_revision'], test_type=p['test']['evaluation_type'], partitions=rows,
                                         files_checked=sum(len(v) for v in before.values()), unchanged=before == after)
    # Alpha#53 recomputation with the v1 study pipeline (real published releases; no model; no broker).
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    work = Path('/srv/jijigua-quant-agent/v1beta/regression') / time.strftime('%Y%m%d_%H%M%S')
    (work / 'research_runs').mkdir(parents=True)
    research = json.loads((R / 'config/research.json').read_text(encoding='utf-8')) | {'workspace': str(work)}
    research.pop('paper_root', None)
    (work / 'research.json').write_text(json.dumps(research), encoding='utf-8')
    backend = QuantBackend(ResourceCatalog(R / 'config/resources.json'), work / 'research.json')
    definition = json.loads((ALPHA53 / 'code/factor_definition.json').read_text(encoding='utf-8'))
    events = []

    class Store:
        path = 'regression'
    ctx = dict(task_id='e' * 32, session_id='r' * 32, goal='v1 regression Alpha#53', store=Store(), core_code_sha256='0' * 64,
               provider={'provider': 'none'}, emit=lambda k, v: events.append(k), deadline=time.monotonic() + 1800,
               authorized_resources=('gpushare:train2020_2023', 'gpushare:validation2024_2025'), hypothesis='regression', change_reason='regression')
    started = time.monotonic()
    result = backend.expression_study('gpushare:train2020_2023', definition['expression'], 'regression', 'regression', 1, 5, 'raw', ctx)
    seconds = time.monotonic() - started
    import csv
    old = {(r['split'], r['metric']): r for r in csv.DictReader((ALPHA53 / 'data/factor_metrics.csv').open(encoding='utf-8'))}
    new = {(r['split'], r['metric']): r for r in csv.DictReader((Path(result['factor_path']).parents[1] / 'data/factor_metrics.csv').open(encoding='utf-8'))}
    diffs = {f'{s}/{m}': max(abs(float(old[(s, m)][k]) - float(new[(s, m)][k])) for k in ('mean', 'std', 'icir', 'positive_ratio', 'n_dates'))
             for s, m in old}
    import numpy as np
    import pandas as pd
    a = pd.read_pickle(ALPHA53 / 'data/factor_plain.pkl')
    b = pd.read_pickle(Path(result['factor_path']).parent / 'factor_plain.pkl')
    same = a.shape == b.shape and np.allclose(a.to_numpy(float), b.to_numpy(float), rtol=0, atol=0, equal_nan=True)
    out['alpha53_v1_recompute'] = dict(metric_max_abs_diff=diffs, factor_matrix_identical=bool(same), seconds=round(seconds, 1),
                                       test=result['metrics']['professional']['test']['reason'],
                                       rationale=result['economic_rationale']['status'],
                                       consistency=json.loads((Path(result['factor_path']).parents[1] / 'data/report_consistency.json').read_text())['status'])
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
