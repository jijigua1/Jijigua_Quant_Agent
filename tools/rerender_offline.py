"""Offline re-render of an existing study with the current report code (QA only; 2026-10-15).

Copies the statistics and static figures an operator re-render is allowed to use (the same filter as a report revision:
data/*.csv except factor values and input slices, non-interactive figures, the frozen definition and, when present, the
Test receipt) from <source> into a NEW directory <out>, re-renders the report there and runs the consistency checks. The
source study is only read, nothing is evaluated and no 2026 data is read: Test numbers come from the existing receipt.

    python tools/rerender_offline.py <source study or revision dir> <new output dir>
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path


def main(argv=None):
    argv = argv or sys.argv[1:]
    source, out = Path(argv[0]), Path(argv[1])
    if out.exists():
        raise SystemExit(f'output exists: {out}')
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    entries = {f['path']: f for f in manifest['files']}
    keep = lambda name: ((name.startswith('data/') and name.endswith('.csv') and name not in ('data/factor_values.csv', 'data/input_slice.csv'))
                         or (name.startswith('figures/') and not Path(name).name.startswith(('interactive_', 'rank_ic_monthly_', 'ic_monthly_')))
                         or name in ('code/factor_definition.json', 'code/economic_rationale.json', 'code/paper_definition.json',
                                     'code/factor_formula.tex', 'data/test_receipt.json', 'data/analysis.json'))
    for sub in ('data', 'figures', 'code', 'reports'):
        (out / sub).mkdir(parents=True)
    copied = 0
    for name, f in entries.items():
        if not keep(name):
            continue
        raw = (source / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != f['sha256']:
            raise SystemExit(f'source fingerprint mismatch: {name}')
        (out / name).write_bytes(raw)
        copied += 1
    result = json.loads((out / 'data/analysis.json').read_text(encoding='utf-8'))
    definition = json.loads((out / 'code/factor_definition.json').read_text(encoding='utf-8'))
    from research_agent.research_report import render
    from research_agent.report_consistency import check
    render(out, result, None, {}, manifest.get('goal', '离线重渲染'), definition.get('hypothesis', '冻结研究定义'), definition)
    report = check(out, result)
    files = sum(1 for p in out.rglob('*') if p.is_file())
    print(json.dumps(dict(source=str(source), out=str(out), copied=copied, files_after=files, consistency=report['status'],
                          failed=[c for c in report['checks'] if not c['passed']],
                          test=result['metrics']['professional']['test']['status']), ensure_ascii=False, indent=1))
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    sys.exit(main())
