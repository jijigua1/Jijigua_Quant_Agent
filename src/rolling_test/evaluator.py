"""Rolling 2026 evaluator. Runs as quanteval (real) or in-process (synthetic engineering tests).

Input : a broker-written request (frozen definition fixed from the study's own files, snapshot version + manifest SHA,
        Validation dates for the history check). No paths from the Agent, no tuning parameters.
Output: an HMAC-signed receipt with aggregates only: daily IC / RankIC / coverage / valid pairs / equal-weight group mean
        forward gross returns / G0-last, partition-annual-monthly statistics, label maturity, warm-up overlap digest.
        Never prices, per-stock factors or per-stock labels.
Ledger: (definition_sha256, snapshot version, contract) is unique; a repeat returns the stored signed receipt.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from . import CONTRACT, EVALUATION_TYPE, MAX_WARMUP, PROTOCOL
from .factors import KINDS, compute, fingerprint

REQUEST_KEYS = {'protocol', 'contract', 'study_id', 'frozen', 'definition_sha256', 'snapshot', 'overlap_dates', 'synthetic'}


class EvaluationDenied(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sign(key, result):
    return hmac.new(key, _canonical(result).encode('utf-8'), hashlib.sha256).hexdigest()


def verify(key, receipt):
    if set(receipt) != {'result', 'signature'}:
        return False
    return hmac.compare_digest(sign(key, receipt['result']), receipt['signature'])


def _check(request):
    import re
    if set(request) != REQUEST_KEYS or request['protocol'] != PROTOCOL or request['contract'] != CONTRACT:
        raise EvaluationDenied('REQUEST_CONTRACT')
    f = request['frozen']
    if f.get('kind') not in KINDS or fingerprint(f) != request['definition_sha256']:
        raise EvaluationDenied('FROZEN_DEFINITION_MISMATCH')
    if f['lag'] != 1 or f['direction'] != 1 or not 1 <= f['horizon'] <= 10 or not 2 <= f['n_groups'] <= 5:
        raise EvaluationDenied('FROZEN_PARAMETERS_OUT_OF_CONTRACT')
    if not 1 <= int(f['warmup']) <= MAX_WARMUP:
        raise EvaluationDenied('WARMUP_EXCEEDS_SNAPSHOT_HISTORY')
    if not re.fullmatch(r'[0-9a-f]{32}:[0-9a-f]{16}', request['study_id']):
        raise EvaluationDenied('STUDY_ID')
    s = request['snapshot']
    if set(s) != {'version', 'manifest_sha256'} or not re.fullmatch(r'rolling_\d{8}_[0-9a-f]{12}', s['version']):
        raise EvaluationDenied('SNAPSHOT_REFERENCE')
    if not isinstance(request['overlap_dates'], list) or len(request['overlap_dates']) > 80:
        raise EvaluationDenied('OVERLAP_DATES')


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        with self._db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS evaluations (evaluation_id TEXT PRIMARY KEY, definition_sha256 TEXT,'
                             ' snapshot TEXT, contract TEXT, study_id TEXT, status TEXT, receipt TEXT, created REAL,'
                             ' UNIQUE(definition_sha256, snapshot, contract));'
                             'CREATE TABLE IF NOT EXISTS audit (at REAL, event TEXT, payload TEXT);')

    def _db(self):
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def audit(self, event, payload):
        with self._db() as db:
            db.execute('INSERT INTO audit VALUES (?,?,?)', (time.time(), event, _canonical(payload)))

    def find(self, sha, snapshot):
        with self._db() as db:
            row = db.execute('SELECT receipt FROM evaluations WHERE definition_sha256=? AND snapshot=? AND contract=?'
                             ' AND status=?', (sha, snapshot, CONTRACT, 'COMPLETED')).fetchone()
        return json.loads(row[0]) if row else None

    def store(self, receipt):
        r = receipt['result']
        with self._db() as db:
            db.execute('INSERT INTO evaluations VALUES (?,?,?,?,?,?,?,?)', (r['evaluation_id'], r['definition_sha256'],
                       r['snapshot']['version'], CONTRACT, r['study_id'], 'COMPLETED', _canonical(receipt), time.time()))


def _monotonic(row):
    import numpy as np
    import pandas as pd
    v = row.to_numpy(dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 2 or np.ptp(v[ok]) == 0:
        return np.nan
    return -np.corrcoef(np.arange(len(v))[ok], pd.Series(v[ok]).rank().to_numpy())[0, 1]


def evaluate(request, *, snapshot_root, ledger_path, key, expected_uid=None, synthetic=False, created_at=None):
    """Return (receipt, reused). Raises EvaluationDenied for contract failures (recorded)."""
    import numpy as np
    import pandas as pd
    import qrtk
    from research_agent.factor_evaluation import _period
    from qrtk_skills.tools import j
    from .snapshot import read_snapshot
    if len(key) < 32:
        raise EvaluationDenied('KEY_LENGTH')
    _check(request)
    if bool(request['synthetic']) != bool(synthetic):
        raise EvaluationDenied('SYNTHETIC_REAL_MIXING_DENIED')
    # Real data always needs the separate evaluator identity; synthetic data checks it too whenever one is configured.
    if (not synthetic or expected_uid is not None) and (expected_uid is None or not hasattr(os, 'geteuid')
                                                        or os.geteuid() != expected_uid or expected_uid == 0):
        raise EvaluationDenied('EVALUATOR_IDENTITY')
    ledger = Ledger(ledger_path)
    snap = request['snapshot']
    cached = ledger.find(request['definition_sha256'], snap['version'])
    if cached is not None:
        if cached['result']['study_id'] != request['study_id']:
            # The same frozen definition was already evaluated on this snapshot for another study: no new Test computation
            # or exposure. The statistics are re-issued for this study under a deterministic id naming the evaluation they
            # come from, so asking again yields the identical receipt (and no new report revision).
            first = cached['result']
            reissue = hashlib.sha256((first['evaluation_id'] + '|' + request['study_id']).encode('utf-8')).hexdigest()[:32]
            result = dict(first, study_id=request['study_id'], evaluation_id=reissue, reissued_from=first['evaluation_id'],
                          test=dict(first['test'], exposure=dict(first['test']['exposure'], evaluation_id=reissue)))
            cached = dict(result=result, signature=sign(key, result))
        ledger.audit('REUSED', dict(evaluation_id=cached['result']['evaluation_id'], study_id=request['study_id'],
                                    reissued_from=cached['result'].get('reissued_from')))
        return cached, True
    started = time.monotonic()
    panels, universe, manifest = read_snapshot(Path(snapshot_root) / snap['version'],
                                               expected_manifest_sha256=snap['manifest_sha256'],
                                               expected_uid=expected_uid, synthetic=synthetic)
    frozen = request['frozen']
    factor = compute(frozen, panels)
    h, groups_n = frozen['horizon'], frozen['n_groups']
    values = qrtk.evaluate_factor(factor, panels['open'], direction=1, horizon=h, lag=1, n_groups=groups_n,
                                  universe=universe, min_obs=10)
    all_dates = list(factor.index)
    test_dates = factor.index[factor.index >= pd.Timestamp('2026-01-01')]
    position = {d: i for i, d in enumerate(all_dates)}
    matured = pd.Series([position[d] + 1 + h <= len(all_dates) - 1 for d in test_dates], index=test_dates)
    gr = values['group_returns'].reindex(test_dates)
    daily = pd.DataFrame(dict(ic=values['ic'].reindex(test_dates), rank_ic=values['rank_ic'].reindex(test_dates),
                              coverage=factor.loc[test_dates].notna().mean(axis=1),
                              n_pairs=(values['valid'] & values['forward_returns'].notna()).sum(axis=1).reindex(test_dates).astype(float),
                              long_short_gross=values['long_short'].reindex(test_dates),
                              group_monotonicity=gr.apply(_monotonic, axis=1),
                              factor_lag1=qrtk.cross_sectional_corr(factor.where(universe), factor.where(universe).shift(1), min_obs=10).reindex(test_dates),
                              rank_lag1=values['rank_autocorr'].reindex(test_dates), split='test'), index=test_dates)
    daily.loc[daily[['ic', 'rank_ic']].isna().all(axis=1), 'n_pairs'] = np.nan
    # Unmatured labels stay missing; they are never filled or predicted.
    if (daily.loc[~matured, ['ic', 'rank_ic']].notna()).any().any():
        raise EvaluationDenied('UNMATURED_LABEL_PRODUCED_A_VALUE')
    period = _period(daily, h, 'test', 'test')
    annual = [_period(g, h, int(y), 'test') for y, g in daily.groupby(daily.index.year)]
    monthly = [_period(g, h, str(p), 'test') for p, g in daily.groupby(daily.index.to_period('M'))]
    last_matured = test_dates[matured.to_numpy()][-1] if matured.any() else None
    maturity = dict(observed_dates=len(test_dates), matured_signal_dates=int(matured.sum()),
                    last_observation=str(test_dates[-1].date()),
                    last_matured_signal_date=None if last_matured is None else str(last_matured.date()),
                    immature_signal_dates=[str(d.date()) for d in test_dates[~matured.to_numpy()]],
                    rule=f'signal T matures when open[T+1+{h}] is observed in the snapshot (lag 1, H={h})')
    overlap = []
    from . import code_weights
    weights = code_weights(list(factor.columns))
    for day in request['overlap_dates']:
        ts = pd.Timestamp(day)
        if ts not in factor.index or ts >= pd.Timestamp('2026-01-01'):
            overlap.append(dict(date=day, count=None))
            continue
        row = factor.loc[ts].to_numpy(dtype=float)
        ok = np.isfinite(row)
        overlap.append(dict(date=day, count=int(ok.sum()), sum=float(row[ok].sum()), sum_sq=float((row[ok] ** 2).sum()),
                            proj=[float(weights[i][ok] @ row[ok]) for i in range(len(weights))],
                            proj_scale=float(np.abs(row[ok]).sum())))
    group_columns = [f'G{g}' for g in range(groups_n)]
    rows = []
    for d, v in daily.iterrows():
        row = dict(date=str(d.date()), matured=bool(matured[d]), ic=v.ic, rank_ic=v.rank_ic, coverage=v.coverage,
                   n_pairs=v.n_pairs, long_short_gross=v.long_short_gross)
        row.update({c: gr.loc[d, g] for c, g in zip(group_columns, gr.columns)})
        rows.append(row)
    evaluation_id = uuid.uuid4().hex
    result = j(dict(protocol=PROTOCOL, contract=CONTRACT, evaluation_id=evaluation_id, evaluation_type=EVALUATION_TYPE,
        study_id=request['study_id'], definition=frozen, definition_sha256=request['definition_sha256'],
        synthetic=bool(synthetic), snapshot=dict(version=snap['version'], manifest_sha256=snap['manifest_sha256'],
            certified_end=manifest['certified_end'], source_fingerprint=manifest['source_fingerprint'],
            quality=manifest['quality'], status=manifest['status']),
        test=dict(status='COMPLETED', access='CONTROLLED_EVALUATOR', evaluation_type=EVALUATION_TYPE,
            exposure=dict(kind='continuously exposed rolling evaluation; not a blind test',
                          evaluation_id=evaluation_id, snapshot=snap['version']),
            start=str(test_dates[0].date()), end=str(test_dates[-1].date()),
            metrics=period, annual=annual, monthly=monthly, daily=rows, group_columns=group_columns,
            group_definition='equal-weight mean of overlapping H-day raw open-to-open forward gross returns per signal date; G0 = highest factor'),
        maturity=maturity, overlap=overlap, raw_data_returned=False, formal_backtest_ready=False,
        compute_seconds=round(time.monotonic() - started, 3), created_at=created_at or time.strftime('%Y-%m-%dT%H:%M:%S%z')))
    receipt = dict(result=result, signature=sign(key, result))
    if len(_canonical(receipt).encode()) > 480 * 1024:
        raise EvaluationDenied('RECEIPT_TOO_LARGE')
    ledger.store(receipt)
    ledger.audit('EVALUATED', dict(evaluation_id=evaluation_id, study_id=request['study_id'],
                                   definition_sha256=request['definition_sha256'], snapshot=snap['version']))
    return receipt, False


def main(argv=None):
    """quanteval entry: evaluator.py <host_config.json> <request.json>; prints the receipt path."""
    import resource
    import sys
    args = argv or sys.argv[1:]
    if len(args) != 2:
        raise SystemExit('host config and request required')
    config = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    request = json.loads(Path(args[1]).read_text(encoding='utf-8'))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 ** 3,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 ** 2,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    key = Path(config['key_path']).read_bytes()
    receipt, reused = evaluate(request, snapshot_root=config['snapshot_root'], ledger_path=config['ledger_path'], key=key,
                               expected_uid=config['evaluator_uid'], synthetic=config.get('synthetic', False))
    os.umask(0o022)
    out = Path(config['outbox']) / (receipt['result']['evaluation_id'] + '.json')
    if not out.exists():
        with out.open('x', encoding='utf-8') as fh:
            fh.write(_canonical(receipt))
    print(json.dumps(dict(receipt=str(out), reused=reused, evaluation_id=receipt['result']['evaluation_id'])))


if __name__ == '__main__':
    main()
