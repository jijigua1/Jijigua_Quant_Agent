"""Independent numeric check of the stage-3 metric system of one study revision (2026-10-15).

Recomputes every overall / annual / monthly metric from the saved daily rows with its own code (numpy/pandas only; nothing is
imported from research_agent) and compares it with data/metric_system.json, data/report_tables.json and the
heatmap payload of the rendered report. Read-only; prints a JSON verdict.

    python tools/numcheck_metrics.py <revision or study dir> [--tol 1e-12]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

Z95 = 1.95996398454


def rankdata(v):
    """Average ranks 1..n with ties sharing their mean rank (own implementation; no scipy on the server)."""
    v = np.asarray(v, dtype=float)
    order = np.argsort(v, kind='mergesort')
    s = v[order]
    ranks = np.empty(len(v))
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def hac(x, h):
    """Bartlett Newey-West mean SE on the series with structural edge gaps trimmed; None when the contract is not met."""
    x = np.asarray(x, dtype=float)
    fin = np.flatnonzero(np.isfinite(x))
    if not len(fin):
        return None
    x = x[fin[0]:fin[-1] + 1]
    lags = max(h - 1, int(4 * (len(x) / 100) ** (2 / 9)))
    if len(x) < max(60, 10 * (lags + 1)) or not np.isfinite(x).all():
        return None
    n = len(x)
    e = x - x.mean()
    var = e @ e / n
    for k in range(1, lags + 1):
        var += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    if var <= 0:
        return None
    se = math.sqrt(var / n)
    t = x.mean() / se
    return dict(se=se, t=t, p=math.erfc(abs(t) / math.sqrt(2)), ci_low=x.mean() - Z95 * se, ci_high=x.mean() + Z95 * se)


def mono(v):
    v = np.asarray(v, dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 2 or v[ok].max() == v[ok].min():
        return None
    a, b = np.arange(len(v))[ok].astype(float), rankdata(v[ok])
    a, b = a - a.mean(), b - b.mean()
    return float(-(a @ b) / math.sqrt((a @ a) * (b @ b)))


def stats(x, h, with_hac=True):
    x = np.asarray(x, dtype=float)
    v = x[np.isfinite(x)]
    out = dict(mean=v.mean() if len(v) else None, n=len(v), win_rate=(v > 0).mean() if len(v) else None)
    out['std'] = float(np.sqrt(((v - v.mean()) ** 2).sum() / (len(v) - 1))) if len(v) > 1 else None
    out['ir'] = out['mean'] / out['std'] if out['std'] else None
    if with_hac:
        r = hac(x, h) or {}
        out.update(se=r.get('se'), t=r.get('t'), p=r.get('p'), ci_low=r.get('ci_low'), ci_high=r.get('ci_high'))
    return out


def load(run, h, n):
    cfg = json.loads((run / 'data/metric_system.json').read_text(encoding='utf-8'))
    d = pd.read_csv(run / 'data/evaluation_daily.csv', index_col=0, parse_dates=True, float_precision='round_trip')
    d = d[d['split'].isin(['train', 'valid'])]
    g = pd.read_csv(run / 'data/group_returns_gross.csv', index_col=0, parse_dates=True, float_precision='round_trip').reindex(d.index)
    rows = pd.DataFrame({'split': d['split'], 'ic': d['ic'], 'rank_ic': d['rank_ic'], 'coverage': d['coverage'], 'n_pairs': d['n_pairs']})
    for k in range(n):
        rows['G%d' % k] = g[str(k)].astype(float)
    receipt = run / 'data/test_receipt.json'
    if cfg['test_status'] == 'COMPLETED':
        r = json.loads(receipt.read_text(encoding='utf-8'))
        t = pd.DataFrame((r.get('result') or r)['test']['daily'])
        t.index = pd.to_datetime(t.pop('date'))
        t = t.reindex(columns=['ic', 'rank_ic', 'coverage', 'n_pairs', *['G%d' % k for k in range(n)]]).astype(float)
        t.insert(0, 'split', 'test')
        rows = pd.concat([rows, t]).sort_index()
    rows['spread'] = rows['G0'] - rows['G%d' % (n - 1)]
    rows['monotonicity'] = [mono(r) for r in rows[['G%d' % k for k in range(n)]].to_numpy(dtype=float)]
    return cfg, rows


def expect(rows, h, n, with_hac):
    rank_ok = np.isfinite(rows['rank_ic'].to_numpy(dtype=float))
    e = dict(observed_dates=len(rows), valid_days=int(rank_ok.sum()),
             mean_stocks=rows['n_pairs'][rank_ok].mean() if rank_ok.any() else None,
             mean_coverage=rows['coverage'].mean() if rows['coverage'].notna().any() else None)
    for m in ('ic', 'rank_ic', 'spread'):
        s = stats(rows[m], h, with_hac)
        for k, v in s.items():
            e[m + '_' + k] = v
    for k in range(n):
        s = stats(rows['G%d' % k], h, with_hac)
        e.update({'G%d_mean' % k: s['mean'], 'G%d_std' % k: s['std'], 'G%d_n' % k: s['n']})
        if with_hac:
            e['G%d_t' % k] = s['t']
    m = rows['monotonicity'].astype(float)
    e['monotonicity'] = m.mean() if m.notna().any() else None
    means = [e['G%d_mean' % k] for k in range(n)]
    e['monotonicity_of_means'] = mono(means) if None not in means else None
    return e


def same(a, b, tol):
    na = a is None or (isinstance(a, float) and math.isnan(a))
    nb = b is None or (isinstance(b, float) and math.isnan(b))
    if na or nb:
        return na and nb
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('--tol', type=float, default=1e-12)
    a = ap.parse_args(argv)
    run = Path(a.run)
    cfg = json.loads((run / 'data/metric_system.json').read_text(encoding='utf-8'))
    h, n = cfg['horizon'], cfg['n_groups']
    cfg, rows = load(run, h, n)
    bad, checked = [], 0
    groups = {'overall': [(s, g) for s, g in rows.groupby('split', sort=False)],
              'annual': [(int(y), g) for y, g in rows.groupby(rows.index.year)],
              'monthly': [(str(p), g) for p, g in rows.groupby(rows.index.to_period('M'))]}
    for level, parts in groups.items():
        got = {str(r['period']): r for r in cfg[level]}
        if set(got) != {str(k) for k, _ in parts}:
            bad.append(dict(level=level, issue='periods differ', got=sorted(got), want=sorted(str(k) for k, _ in parts)))
            continue
        for key, g in parts:
            want = expect(g, h, n, level != 'monthly')
            for field, value in want.items():
                checked += 1
                row = got[str(key)]
                if field not in row or not same(row[field], value, a.tol):
                    bad.append(dict(level=level, period=str(key), field=field, got=row.get(field), want=value))
    # rendered tables carry the same raw numbers
    tables = {t['id']: t for t in json.loads((run / 'data/report_tables.json').read_text(encoding='utf-8'))}
    ann = {str(r['period']): r for r in cfg['annual']}
    for row in tables['metric_annual']['values']:
        year = str(row[0]).split(' / ')[0]
        if year in ann:
            r = ann[year]
            for v, field in zip(row[1:], ['ic_mean', 'ic_ir', 'ic_win_rate', 'rank_ic_mean', 'rank_ic_ir', 'rank_ic_win_rate', 'rank_ic_t',
                                          'rank_ic_ci_low', 'rank_ic_ci_high', 'valid_days', 'mean_stocks', 'mean_coverage']):
                checked += 1
                if not same(v, r.get(field), a.tol):
                    bad.append(dict(level='table metric_annual', period=year, field=field, got=v, want=r.get(field)))
    hac_fields = ['mean', 't', 'p', 'ci_low', 'ci_high', 'n']
    for row in tables['metric_annual_hac']['values']:
        year, _, series = str(row[0]).partition(' / ')
        key = {'IC': 'ic', 'RankIC': 'rank_ic'}.get(series.rsplit(' / ', 1)[-1], 'spread')
        r = ann.get(year.split(' / ')[0])
        if r is None:
            continue
        for v, field in zip(row[1:7], hac_fields):
            checked += 1
            if not same(v, r.get(key + '_' + field), a.tol):
                bad.append(dict(level='table metric_annual_hac', period=year, field=key + '_' + field, got=v, want=r.get(key + '_' + field)))
    payload = json.loads((run / 'data/evaluation_chart_payload.json').read_text(encoding='utf-8'))
    month = {r['period']: r for r in cfg['monthly']}
    heat = [c for c in payload if c['id'].endswith('_monthly_heatmap') or c['id'].endswith('_monthly')]
    keys = {'rank_ic_monthly_heatmap': 'rank_ic_mean', 'ic_monthly_heatmap': 'ic_mean'}
    for c in heat:
        key = keys.get(c['id']) or c['id'][len('heat_'):-len('_monthly')]
        t = c['traces'][0]
        for y, zrow in zip(t['y'], t['z']):
            for mth, v in enumerate(zrow, 1):
                r = month.get(f'{y:04d}-{mth:02d}')
                want = None if r is None else r.get(key)
                checked += 1
                if not same(v, want, a.tol):
                    bad.append(dict(level='heatmap', chart=c['id'], cell=f'{y}-{mth:02d}', got=v, want=want))
    print(json.dumps(dict(run=str(run), status='PASSED' if not bad else 'FAILED', values_checked=checked, heatmaps=len(heat),
                          mismatches=bad[:30], n_mismatches=len(bad)), ensure_ascii=False, indent=2, default=float))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
