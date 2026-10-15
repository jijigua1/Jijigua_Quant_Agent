"""Operator-side independent check of one real ROLLING_EXPOSED_TEST receipt (run as root on the server; read-only).

Recomputes the 52-week-high factor and the daily Test IC / RankIC with plain numpy/pandas from the private snapshot arrays
(np.load, allow_pickle=False) instead of the evaluator code path, then compares them with the signed receipt. Acceptance
evidence only: nothing here feeds research or parameter choice. Usage: verify_rolling_real.py <registered receipt.json>
"""
import hashlib
import hmac
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROLL = Path('/srv/jijigua-quant-agent/v1beta_rolling')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def pearson(x, y):
    x, y = x - x.mean(), y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else None


def main(path):
    receipt = json.loads(Path(path).read_text(encoding='utf-8'))
    body = {k: receipt[k] for k in ('result', 'signature')}
    key = (ROLL / 'rolling.key').read_bytes()
    ok_sig = hmac.compare_digest(hmac.new(key, canonical(body['result']).encode(), hashlib.sha256).hexdigest(), body['signature'])
    r = body['result']
    snap = ROLL / 'snapshots' / r['snapshot']['version']
    manifest_raw = (snap / 'manifest.json').read_bytes()
    m = json.loads(manifest_raw)
    ok_manifest = hashlib.sha256(manifest_raw).hexdigest() == r['snapshot']['manifest_sha256']
    ok_arrays = all(hashlib.sha256((snap / f).read_bytes()).hexdigest() == s for f, s in m['sha256'].items())
    dates = pd.to_datetime(m['dates'], format='%Y%m%d')
    codes = [c[:6] for c in m['codes']]
    load = lambda f: pd.DataFrame(np.load(snap / f'{f}.npy', allow_pickle=False), index=dates, columns=codes)
    close, open_, volume = load('close'), load('open'), load('volume')
    frozen = r['definition']
    h = frozen['horizon']
    print('frozen definition:', json.dumps({k: frozen[k] for k in frozen if k not in ('ir',)}, ensure_ascii=False)[:400])
    print('frozen IR:', json.dumps(frozen.get('ir'), ensure_ascii=False)[:300])
    factor = close / close.rolling(252, min_periods=252).max()          # P[t] / max_{k=0..251} P[t-k]
    factor = factor.replace([np.inf, -np.inf], np.nan)
    universe = open_.notna() & close.notna() & volume.gt(0)
    label = open_.shift(-(1 + h)) / open_.shift(-1) - 1
    rows = {x['date']: x for x in r['test']['daily']}
    test_dates = dates[dates >= '2026-01-01']
    worst, compared, immature_ok = 0.0, 0, True
    for d in test_dates:
        x, y = factor.loc[d].where(universe.loc[d]), label.loc[d]
        ok = (x.notna() & y.notna()).to_numpy()
        got = rows[str(d.date())]
        if not got['matured']:
            immature_ok &= got['ic'] is None and got['rank_ic'] is None
            continue
        if ok.sum() < 10:
            immature_ok &= got['ic'] is None
            continue
        xv, yv = x.to_numpy()[ok], y.to_numpy()[ok]
        ic = pearson(xv, yv)
        ric = pearson(pd.Series(xv).rank().to_numpy(), pd.Series(yv).rank().to_numpy())
        for mine, theirs in ((ic, got['ic']), (ric, got['rank_ic'])):
            worst = max(worst, abs(mine - theirs)) if theirs is not None else float('inf')
        compared += 1
    daily = pd.DataFrame(r['test']['daily'])
    means = dict(ic=pd.to_numeric(daily['ic']).mean(), rank_ic=pd.to_numeric(daily['rank_ic']).mean())
    met = r['test']['metrics']
    ledger = sqlite3.connect(f"file:{ROLL / 'eval/ledger.sqlite'}?mode=ro", uri=True)
    tables = [t for (t,) in ledger.execute("select name from sqlite_master where type='table'")]
    audit = [json.loads(l) for l in (ROLL / 'audit/broker.jsonl').read_text(encoding='utf-8').splitlines()]
    chain = all(a['previous'] == b['sha256'] for b, a in zip(audit, audit[1:]))
    out = dict(signature_valid=ok_sig, manifest_fingerprint=ok_manifest, array_fingerprints=ok_arrays,
               snapshot=r['snapshot']['version'], certified_end=r['snapshot']['certified_end'], snapshot_status=m['status'],
               evaluation_type=r['evaluation_type'], test_range=[r['test']['start'], r['test']['end']],
               matured_dates_compared=compared, max_abs_diff_daily_ic_rankic=worst, immature_are_null=immature_ok,
               immature_dates=r['maturity']['immature_signal_dates'], maturity_rule=r['maturity']['rule'],
               receipt_ic_mean=met.get('ic_mean'), recomputed_ic_mean=means['ic'],
               receipt_rank_ic_mean=met.get('rank_ic_mean'), recomputed_rank_ic_mean=means['rank_ic'],
               rank_ic_n_dates=met.get('rank_ic_n_dates'), ledger_tables=tables, audit_events=len(audit), audit_chain_valid=chain,
               raw_data_returned=r['raw_data_returned'])
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    good = ok_sig and ok_manifest and ok_arrays and immature_ok and chain and compared > 30 and worst < 1e-9
    print('INDEPENDENT_CHECK', 'PASSED' if good else 'FAILED')


if __name__ == '__main__':
    main(sys.argv[1])
