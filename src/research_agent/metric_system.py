"""Stage 3 (2026-10-15): the complete factor metric system, computed from the saved daily rows only.

One daily table per study: Train / Validation from data/evaluation_daily.csv + data/group_returns_gross.csv (written by the
reviewed qrtk evaluation), Test from the rolling receipt's daily rows (data/test_receipt.json, aggregate statistics computed by
the controlled evaluator). Nothing here reads factor values, prices or 2026 market data, and nothing changes the evaluator's
signed receipt: every number below is a deterministic function of those rows.

Per period (partition, calendar year, calendar month of the signal date):
  IC / RankIC        mean, sample std (ddof=1), IR = mean/std (not annualised), win rate = share of valid days > 0,
                     Bartlett Newey-West HAC SE / t / two-sided asymptotic p / 95% CI (the existing factor-evaluation contract:
                     >= 60 dates and >= 10*(bandwidth+1), complete finite grid after trimming edge gaps; otherwise N/A)
  sample             valid days (finite RankIC), mean stocks per valid day (factor and label both present), mean coverage
  groups             G0..G{n-1} daily equal-weight H-day open-to-open gross forward returns (G0 = highest factor): mean, std, HAC t;
                     G0-G{n-1} spread: mean, std, win rate, HAC SE / t / p / CI
  monotonicity       daily -Spearman(group index, group return) averaged; and the same statistic on the period's group means
  strategy metrics   N/A until an accepted continuous strategy return series exists (none does): no annual return, Sharpe,
                     drawdown or turnover is derived from overlapping theoretical group labels.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = 'metric-system/1'
STRATEGY_NA = 'N/A：尚无经过验收的连续策略收益序列'
STRATEGY_METRICS = ('年化收益', '年化波动', '夏普比率', '最大回撤', '换手率')
SPLIT_CN = {'train': 'Train', 'valid': 'Validation', 'test': 'Test'}


def _finite(values):
    v = np.asarray(values, dtype=float)
    return v[np.isfinite(v)]


def _monotonic(v):
    """-Spearman(group index, group value): +1 when G0 > G1 > ... (higher score, higher return). Same rule as the evaluator."""
    v = np.asarray(v, dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 2 or np.ptp(v[ok]) == 0:
        return None
    return float(-np.corrcoef(np.arange(len(v))[ok], pd.Series(v[ok]).rank().to_numpy())[0, 1])


def hac_reason(r):
    """Why a HAC result is N/A, in the report's words (the gate itself is the existing factor-evaluation contract)."""
    if r['status'] == 'approximate':
        return ''
    if r['status'] == 'insufficient':
        n, lags = r.get('n_valid') or 0, r.get('lags') or 0
        need = max(60, 10 * (lags + 1))
        if r.get('n', 0) and r.get('n_valid', 0) < r.get('n', 0):
            return f'序列内部有缺失日（{r["n"] - r["n_valid"]}天），HAC要求连续完整网格，不补值'
        return f'有效日{n}天，少于要求的{need}天（≥60且≥10×(带宽{lags}+1)）'
    return '长期方差不可用（序列近似常数）'


def _describe(values, horizon, *, hac=True):
    from .factor_evaluation import inference
    x = np.asarray(values, dtype=float)
    v = _finite(x)
    std = float(v.std(ddof=1)) if len(v) > 1 else None
    out = dict(mean=float(v.mean()) if len(v) else None, std=std,
               ir=float(v.mean() / std) if std is not None and std > 0 else None,
               win_rate=float((v > 0).mean()) if len(v) else None, n=int(len(v)))
    if hac:
        r = inference(x, horizon)
        out.update(hac_status=r['status'], hac_reason=hac_reason(r), se=r['se'], t=r['t_stat'], p=r['p_value'], ci_low=r['ci_low'], ci_high=r['ci_high'],
                   lags=r['lags'])
    return out


def daily_table(run, result):
    """Train/Validation and (when the rolling Test completed) Test daily rows in one frame; Test rows come from the receipt."""
    run = Path(run)
    n = int(result['spec']['n_groups'])
    cols = ['G%d' % g for g in range(n)]
    daily = pd.read_csv(run / 'data/evaluation_daily.csv', index_col=0, parse_dates=True, float_precision='round_trip')
    daily = daily[daily['split'].isin(['train', 'valid'])]
    groups = pd.read_csv(run / 'data/group_returns_gross.csv', index_col=0, parse_dates=True, float_precision='round_trip')
    groups = groups.reindex(daily.index)
    out = pd.DataFrame({'split': daily['split'], 'ic': daily['ic'], 'rank_ic': daily['rank_ic'], 'coverage': daily['coverage'],
                        'n_pairs': daily['n_pairs']}, index=daily.index)
    for g in range(n):
        out['G%d' % g] = groups[str(g)].to_numpy(dtype=float)
    out['matured'] = True
    test = result['metrics']['professional']['test']
    if test['status'] == 'COMPLETED':
        from .report_versions import test_daily
        td = pd.DataFrame(test_daily(run, test))
        td.index = pd.to_datetime(td.pop('date'))
        part = pd.DataFrame(index=td.index)
        part['split'] = 'test'
        for c in ['ic', 'rank_ic', 'coverage', 'n_pairs', *cols]:
            part[c] = pd.to_numeric(td[c], errors='coerce') if c in td else np.nan
        part['matured'] = td['matured'].astype(bool) if 'matured' in td else True
        out = pd.concat([out, part]).sort_index()
    out['spread'] = out[cols[0]] - out[cols[-1]]
    out['monotonicity'] = [_monotonic(r) if r is not None else None for r in out[cols].to_numpy(dtype=float)]
    out['monotonicity'] = out['monotonicity'].astype(float)
    return out


def period(rows, horizon, n, name, split, *, hac=True):
    cols = ['G%d' % g for g in range(n)]
    rank_ok = np.isfinite(rows['rank_ic'].to_numpy(dtype=float))
    out = dict(period=name, split=split, observed_dates=int(len(rows)), valid_days=int(rank_ok.sum()),
               mean_stocks=float(rows['n_pairs'][rank_ok].mean()) if rank_ok.any() else None,
               mean_coverage=float(rows['coverage'].mean()) if rows['coverage'].notna().any() else None)
    for m in ('ic', 'rank_ic'):
        out.update({m + '_' + k: v for k, v in _describe(rows[m], horizon, hac=hac).items()})
    for c in cols:
        d = _describe(rows[c], horizon, hac=hac)
        out.update({c + '_mean': d['mean'], c + '_std': d['std'], c + '_n': d['n']})
        if hac:
            out[c + '_t'] = d['t']
    out.update({'spread_' + k: v for k, v in _describe(rows['spread'], horizon, hac=hac).items()})
    out['monotonicity'] = float(rows['monotonicity'].mean()) if rows['monotonicity'].notna().any() else None
    means = [out[c + '_mean'] for c in cols]
    out['monotonicity_of_means'] = _monotonic([np.nan if v is None else v for v in means]) if None not in means else None
    out['strategy'] = STRATEGY_NA
    return out


def compute(run, result):
    """Overall (per partition), annual and monthly rows; one file, data/metric_system.json (the study keeps its file budget)."""
    run = Path(run)
    h, n = int(result['spec']['horizon']), int(result['spec']['n_groups'])
    daily = daily_table(run, result)
    test = result['metrics']['professional']['test']
    overall = [period(g, h, n, s, s) for s, g in daily.groupby('split', sort=False)]
    order = {'train': 0, 'valid': 1, 'test': 2}
    overall.sort(key=lambda r: order[r['split']])
    annual = [period(g, h, n, int(y), str(g['split'].iloc[0])) for y, g in daily.groupby(daily.index.year)]
    # A calendar month never mixes partitions (boundaries are 2024-01-01 and 2026-01-01); monthly HAC is not asserted (< 60 days).
    monthly = [period(g, h, n, str(p), str(g['split'].iloc[0]), hac=False) for p, g in daily.groupby(daily.index.to_period('M'))]
    from qrtk_skills.tools import j
    summary = j(dict(version=VERSION, horizon=h, n_groups=n, test_status=test['status'], test_reason=test.get('reason'),
                     strategy=dict(status='N/A', text=STRATEGY_NA, metrics=list(STRATEGY_METRICS)),
                     overall=overall, annual=annual, monthly=monthly,
                     definitions=dict(
                         ir='mean / sample std (ddof=1), not annualised', win_rate='share of valid days with value > 0',
                         hac='Bartlett Newey-West, bandwidth max(H-1, floor(4*(n/100)^(2/9))); >=60 and >=10*(bandwidth+1) dates; '
                             'complete finite grid after trimming edge gaps; asymptotic normal; no multiple-testing adjustment',
                         monthly='descriptive only; no monthly HAC or significance', valid_days='dates with a finite RankIC',
                         mean_stocks='mean over valid days of stocks with both a factor value and a matured label',
                         groups=f'G0 = highest factor; {n} equal-count groups per signal date; equal-weight H-day open-to-open gross '
                                'forward return; overlapping labels; not tradable returns',
                         spread=f'daily G0 - G{n - 1}, theoretical gross difference, not a long-short strategy return',
                         monotonicity='daily -Spearman(group index, group return), averaged; monotonicity_of_means uses the period means',
                         test='rolling exposed Test rows from the controlled evaluator receipt; unmatured signal dates are N/A, never 0')))
    (run / 'data/metric_system.json').write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    return summary


# ---------------------------------------------------------------------------------------------------------- heatmaps
def heat_metrics(n):
    """(key, title, kind, value format). kind: div = centred at 0, win = centred at 50%, seq = sequential from 0."""
    last = 'G%d' % (n - 1)
    return [('rank_ic_mean', 'RankIC 月度均值', 'div', '+.3f'), ('ic_mean', 'IC 月度均值', 'div', '+.3f'),
            ('rank_ic_ir', 'RankIC IR（月内均值/标准差，未年化）', 'div', '+.2f'), ('ic_ir', 'IC IR（月内均值/标准差，未年化）', 'div', '+.2f'),
            ('rank_ic_win_rate', 'RankIC 胜率（月内RankIC>0的有效日占比）', 'win', '.0%'),
            ('ic_win_rate', 'IC 胜率（月内IC>0的有效日占比）', 'win', '.0%'),
            ('spread_mean', f'G0−{last} 月度均值（理论毛收益差）', 'div', '+.2%'),
            ('G0_mean', 'G0（最高分组）月度均值毛收益', 'div', '+.2%'), (last + '_mean', f'{last}（最低分组）月度均值毛收益', 'div', '+.2%'),
            ('monotonicity', '分组单调性（日度−Spearman均值）', 'div', '+.2f'),
            ('mean_coverage', '因子覆盖率（月均）', 'seq', '.0%'), ('mean_stocks', '平均有效股票数（因子与成熟标签均存在）', 'seq', '.0f')]


def _fmt(value, f):
    return 'N/A' if value is None else format(value, f)


def heat_grid(monthly, key, fmt, test, years):
    rows = {r['period']: r for r in monthly}
    z, text, custom = [], [], []
    for year in years:
        zr, tr, cr = [], [], []
        for month in range(1, 13):
            r = rows.get(f'{year:04d}-{month:02d}')
            v = None if r is None or r.get(key) is None or (isinstance(r.get(key), float) and math.isnan(r[key])) else float(r[key])
            zr.append(v)
            tr.append(_fmt(v, fmt))
            cr.append([None, None, 'N/A'] if r is None else [r['valid_days'], r['mean_coverage'], SPLIT_CN.get(r['split'], r['split'])])
        z.append(zr), text.append(tr), custom.append(cr)
    return dict(years=years, z=z, text=text, custom=custom)


def scale(grid, kind):
    finite = [v for row in grid['z'] for v in row if v is not None]
    if kind == 'win':
        d = max([abs(v - .5) for v in finite], default=.05) or .05
        return .5 - d, .5 + d, .5
    if kind == 'seq':
        top = max(finite, default=1.0) or 1.0
        return 0.0, top, None
    d = max([abs(v) for v in finite], default=.01) or .01
    return -d, d, 0.0


# ---------------------------------------------------------------------------------------------------------- tables
def _label(r):
    return f"{r['period']} / {SPLIT_CN.get(r['split'], r['split'])}"


def tables(ms, table, test, test_text):
    """HTML/Markdown in the required order: overall -> annual (heatmaps are inserted by the caller) and the group detail."""
    n = ms['n_groups']
    last = 'G%d' % (n - 1)
    gcols = ['G%d' % g for g in range(n)]
    overall = {r['split']: r for r in ms['overall']}
    parts = ['train', 'valid', 'test']
    name = {'train': 'Train', 'valid': 'Validation', 'test': 'Test' if test['status'] == 'COMPLETED' else 'Test · ' + test_text}
    o = [overall.get(s, {}) for s in parts]
    h1, m1 = table('metric_overall_predictive', '总体 · IC / RankIC（逐分区）',
                   ['分区', 'IC均值', 'IC std', 'IC IR', 'IC胜率', 'RankIC均值', 'RankIC std', 'RankIC IR', 'RankIC胜率'],
                   [[name[s], r.get('ic_mean'), r.get('ic_std'), r.get('ic_ir'), r.get('ic_win_rate'), r.get('rank_ic_mean'),
                     r.get('rank_ic_std'), r.get('rank_ic_ir'), r.get('rank_ic_win_rate')] for s, r in zip(parts, o)],
                   ['number'] * 4 + ['percent'] + ['number'] * 3 + ['percent'])
    hac_rows = []
    for s, r in zip(parts, o):
        for key, label in (('ic', 'IC'), ('rank_ic', 'RankIC'), ('spread', f'G0−{last}')):
            hac_rows.append([name[s] + ' / ' + label, r.get(key + '_mean'), r.get(key + '_se'), r.get(key + '_t'), r.get(key + '_p'),
                             r.get(key + '_ci_low'), r.get(key + '_ci_high'), r.get(key + '_hac_status', 'N/A'), r.get(key + '_n')])
    h2, m2 = table('metric_overall_hac', '总体 · HAC统计推断（Newey-West，渐近正态；G0−'+last+'行的均值与区间为收益率小数）',
                   ['分区 / 序列', '均值', 'HAC SE', 't', 'p（双侧）', '95%下界', '95%上界', '状态', '有效日'], hac_rows,
                   ['number'] * 4 + ['pvalue', 'number', 'number', 'number', 'count'])
    h3, m3 = table('metric_overall_sample', '总体 · 样本与分组',
                   ['分区', '有效日', '平均股票数', '覆盖率', *gcols, f'G0−{last}', f'G0−{last}胜率', '单调性（日均）', '单调性（组均值）'],
                   [[name[s], r.get('valid_days'), r.get('mean_stocks'), r.get('mean_coverage'), *[r.get(c + '_mean') for c in gcols],
                     r.get('spread_mean'), r.get('spread_win_rate'), r.get('monotonicity'), r.get('monotonicity_of_means')] for s, r in zip(parts, o)],
                   ['number', 'count', 'number', 'percent'] + ['percent'] * (n + 2) + ['number', 'number'])
    h4, m4 = table('metric_strategy', '策略指标', ['指标', 'Train', 'Validation', 'Test'],
                   [[k, STRATEGY_NA, STRATEGY_NA, STRATEGY_NA] for k in STRATEGY_METRICS])
    annual = list(ms['annual'])
    if test['status'] != 'COMPLETED' and not any(r['split'] == 'test' for r in annual):
        annual.append(dict(period=2026, split='test'))
    alabel = lambda r: _label(r) if r['split'] != 'test' or test['status'] == 'COMPLETED' else f"{r['period']} / {name['test']}"
    h5, m5 = table('metric_annual', '逐年 · 预测能力与样本',
                   ['年份 / 分区', 'IC均值', 'IC IR', 'IC胜率', 'RankIC均值', 'RankIC IR', 'RankIC胜率', 'RankIC HAC t', 'RankIC 95%下界',
                    'RankIC 95%上界', '有效日', '平均股票数', '覆盖率'],
                   [[alabel(r), r.get('ic_mean'), r.get('ic_ir'), r.get('ic_win_rate'), r.get('rank_ic_mean'), r.get('rank_ic_ir'),
                     r.get('rank_ic_win_rate'), r.get('rank_ic_t'), r.get('rank_ic_ci_low'), r.get('rank_ic_ci_high'), r.get('valid_days'),
                     r.get('mean_stocks'), r.get('mean_coverage')] for r in annual],
                   ['number'] * 3 + ['percent'] + ['number'] * 2 + ['percent'] + ['number'] * 3 + ['count', 'number', 'percent'])
    hac_rows = []
    for r in annual:
        for key, label in (('ic', 'IC'), ('rank_ic', 'RankIC'), ('spread', f'G0−{last}')):
            na = r.get(key + '_hac_status') != 'approximate'
            hac_rows.append([alabel(r) + ' / ' + label, r.get(key + '_mean'), r.get(key + '_t'), r.get(key + '_p'), r.get(key + '_ci_low'),
                             r.get(key + '_ci_high'), r.get(key + '_n'),
                             ('N/A：' + (r.get(key + '_hac_reason') or '本年未评价')) if na else '可用（渐近近似）'])
    h5b, m5b = table('metric_annual_hac', f'逐年 · HAC统计推断（IC、RankIC、G0−{last}；Newey-West，渐近正态）',
                     ['年份 / 分区 / 序列', '均值', 'HAC t', 'p（双侧）', '95%下界', '95%上界', '有效日', '状态'], hac_rows,
                     ['number'] * 3 + ['pvalue', 'number', 'number', 'count', 'number'])
    h6, m6 = table('metric_groups_annual', f'逐年 · G0–{last} 分组明细（G0为最高分组）',
                   ['年份 / 分区', *gcols, f'G0−{last}', f'G0−{last} HAC t', '95%下界', '95%上界', f'G0−{last}胜率', '单调性（日均）', '有效日'],
                   [[alabel(r), *[r.get(c + '_mean') for c in gcols], r.get('spread_mean'), r.get('spread_t'), r.get('spread_ci_low'),
                     r.get('spread_ci_high'), r.get('spread_win_rate'), r.get('monotonicity'), r.get('spread_n')] for r in annual],
                   ['number'] + ['percent'] * (n + 1) + ['number', 'percent', 'percent', 'percent', 'number', 'count'])
    h7, m7 = table('metric_groups_monthly', f'逐月 · G0–{last} 分组明细（描述统计，不做月度显著性）',
                   ['月份 / 分区', *gcols, f'G0−{last}', f'G0−{last}胜率', '单调性（日均）', '有效日'],
                   [[_label(r), *[r.get(c + '_mean') for c in gcols], r.get('spread_mean'), r.get('spread_win_rate'), r.get('monotonicity'),
                     r.get('spread_n')] for r in ms['monthly']],
                   ['number'] + ['percent'] * (n + 2) + ['number', 'count'])
    note = ('<p class="note">IR = 均值/样本标准差（未年化）；胜率 = 有效日中数值&gt;0的占比；HAC为Bartlett Newey-West，样本不足60个有效日或网格内部有缺口时为N/A，'
            '不补值；月度只做描述统计。G0为当日因子值最高的一组，分组收益为重叠的H日开盘到开盘理论毛收益，不是账户收益。'
            '策略指标（年化收益、夏普、回撤、换手）需要经过验收的连续策略收益序列，当前没有，因此全部显示N/A，不用理论分组收益代替。</p>')
    overall_html = '<h3>一、总体评价</h3>' + h1 + h2 + h3 + h4 + note
    annual_html = ('<h3>二、逐年评价</h3>' + h5 + h5b +
                   f'<p class="note">G0−{last}行的均值与区间为收益率小数。N/A 表示该年不满足既有 HAC 合同（≥60 个有效日且 ≥10×(带宽+1)，'
                   '序列内部无缺口），程序不补值、不放宽门槛，也不给出显著性。</p>')
    group_html = '<h3>四、G0–' + last + ' 分组明细</h3>' + h6 + '<details open><summary>逐月分组明细（' + str(len(ms['monthly'])) + '个月）</summary>' + h7 + '</details>'
    md = '\n\n'.join([m1, m2, m3, m4, m5, m5b, m6, m7])
    return overall_html, annual_html, group_html, md
