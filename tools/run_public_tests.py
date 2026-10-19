"""Run the complete public suite in deterministic, disjoint CI partitions.

Windows font embedding makes one full-suite job exceed its wall-clock limit.
The two partitions cover every test module; they do not alter tests or assertions.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def partition(root=ROOT):
    files = sorted((root / 'tests').rglob('test_*.py'))
    reports = [p for p in files if p.name.startswith('test_v1beta')]
    core = [p for p in files if p not in reports]
    if not core or not reports or set(core) & set(reports) or set(core + reports) != set(files):
        raise ValueError('INCOMPLETE_TEST_PARTITION')
    return dict(all=files, core=core, reports=reports)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shard', choices=('all', 'core', 'reports'), default='all')
    parser.add_argument('--verify-partition', action='store_true')
    args = parser.parse_args()
    parts = partition()
    if args.verify_partition:
        print(json.dumps(dict(status='PASS', modules={k: len(v) for k, v in parts.items()},
                              overlap=0, omitted=0)))
        return 0
    import pytest
    return pytest.main([str(p) for p in parts[args.shard]] +
                       ['-q', '-p', 'no:cacheprovider', '--durations=10'])


if __name__ == '__main__':
    sys.exit(main())
