"""Group-return (G0–G4) figure, statistics and wording derived from the evaluation code, plus chart explanations.

Every sentence about grouping states what qrtk.factor_eval and historical_evaluation actually do (checked 2026-10-13):
- each signal date t: stocks with a finite factor value inside the universe of t (open and close present, volume > 0);
- ranked by the factor (direction +1, descending, ties broken by column order), cut into n equal-count groups;
  G0 holds the highest scores. Groups are rebuilt every date; no membership is carried between dates or stages;
- label open[t+1+H] / open[t+1] − 1 on raw (unadjusted) prices; equal weight inside a group; members without a label
  are left out of that date's average; no costs, slippage, limits or account constraints;
- a stage keeps only signal dates whose label exit date is inside the stage (no label crosses a stage boundary);
- a bar = arithmetic mean over the stage's dates of the daily group means (overlapping H-day labels; not compounded);
- G0−G(n−1) = mean of the daily differences (a theoretical gross spread, not a long-short account).
"""
from html import escape

import numpy as np
import pandas as pd

STAGES = (('train', 'Train'), ('valid', 'Validation'), ('test', 'Test'))


def _hac(values, horizon):
    from .research_metrics import hac_mean
    x = np.asarray(values, dtype=float)
    finite = np.flatnonzero(np.isfinite(x))
    if not len(finite):
        return dict(status='insufficient', ci_low=None, ci_high=None, n=0)
    return hac_mean(x[finite[0]:finite[-1] + 1], horizon)


def group_stats(run, result):
    """Per stage: group means, G0−last spread with HAC 95% interval, monotonicity, dates and mean group size."""
    from .report_versions import test_daily
    from pathlib import Path
    run = Path(run)
    h, n = result['spec']['horizon'], result['spec']['n_groups']
    p = result['metrics'].get('professional') or {}
    daily = pd.read_csv(run / 'data/evaluation_daily.csv', index_col=0, parse_dates=True)
    out = {}
    for key, label in STAGES[:2]:
        tg = result['splits'][key]['theoretical_groups']
        part = (p.get('partitions') or {}).get(key) or {}
        ls = daily.loc[daily['split'] == key, 'long_short_gross'] if 'long_short_gross' in daily else pd.Series(dtype=float)
        hac = _hac(ls.to_numpy(), h)
        out[key] = dict(label=label, means=[tg['mean_group_return_gross'].get(str(g)) for g in range(n)],
                        spread=tg['long_short_mean_gross'], ci=(hac.get('ci_low'), hac.get('ci_high')), ci_status=hac['status'],
                        monotonic=tg['monotonicity'].get('pooled'), strict=tg['monotonicity'].get('strictly_monotone'),
                        n_dates=tg['monotonicity'].get('n_dates'), stocks=part.get('mean_stocks'),
                        rank_ic=result['splits'][key]['predictive']['rank_ic']['mean'],
                        rank_ci=(part.get('rank_ic_ci_low'), part.get('rank_ic_ci_high')))
    test = p.get('test') or {}
    if test.get('status') == 'COMPLETED' and test.get('group_columns'):
        # receipts signed before group returns were returned (independent-evaluator/1.0.x, production 10-13) have no
        # group columns: no Test row here; the Test IC/RankIC still come from the receipt (candidate6 rehearsal: KeyError)
        rows = pd.DataFrame(test_daily(run, test))
        cols = test['group_columns']
        for c in cols + ['long_short_gross']:
            rows[c] = pd.to_numeric(rows[c], errors='coerce')
        means = [None if rows[c].dropna().empty else float(rows[c].dropna().mean()) for c in cols]
        matured = rows[rows['matured']] if 'matured' in rows else rows
        hac = _hac(matured['long_short_gross'].to_numpy(), h)
        m = test['metrics']
        valid_means = [v for v in means if v is not None]
        mono = None
        if len(valid_means) == n:
            r = pd.Series(means).rank().to_numpy()
            mono = float(-np.corrcoef(np.arange(n), r)[0, 1]) if np.ptp(r) > 0 else None
        out['test'] = dict(label='Test', means=means, spread=float(matured['long_short_gross'].mean()) if matured['long_short_gross'].notna().any() else None,
                           ci=(hac.get('ci_low'), hac.get('ci_high')), ci_status=hac['status'], monotonic=mono,
                           strict=None if mono is None else abs(mono) == 1.0, n_dates=int(matured['long_short_gross'].notna().sum()),
                           stocks=m.get('mean_stocks'), rank_ic=m.get('rank_ic_mean'), rank_ci=(m.get('rank_ic_ci_low'), m.get('rank_ic_ci_high')))
    return out


def group_labels(n):
    """Equal-count groups from the highest score (G0) to the lowest (G{n-1})."""
    edges = [round(100 * k / n) for k in range(n + 1)]
    names = []
    for g in range(n):
        if g == 0:
            names.append(f'G0\n最高（前{edges[1]}%）')
        elif g == n - 1:
            names.append(f'G{g}\n最低（后{100 - edges[g]}%）')
        else:
            names.append(f'G{g}\n{edges[g]}–{edges[g + 1]}%')
    return names


def group_figure(run, result, stats):
    """Bar chart of the stages present in `stats` (2 before the rolling Test, 3 after); png/svg/pdf."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    from pathlib import Path
    from .research_report import AMBER, BLUE, GREY
    from .server_plot import configure_chinese_font
    run = Path(run)
    h, n = result['spec']['horizon'], result['spec']['n_groups']
    colors = {'train': BLUE, 'valid': AMBER, 'test': '#3a7d44'}
    try:
        font = configure_chinese_font().get_name()
    except RuntimeError:
        font = 'DejaVu Sans'
    stages = [k for k, _ in STAGES if k in stats]
    width = 0.8 / len(stages)
    with plt.rc_context({'font.family': 'sans-serif', 'font.sans-serif': [font, 'DejaVu Sans'], 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42, 'legend.frameon': False}):
        fig, ax = plt.subplots(figsize=(8.2, 4.0))
        x = np.arange(n)
        for i, key in enumerate(stages):
            s = stats[key]
            vals = [np.nan if v is None else v for v in s['means']]
            bars = ax.bar(x + (i - (len(stages) - 1) / 2) * width, vals, width * 0.95, color=colors[key], alpha=.88,
                          label=f"{s['label']}（{s['n_dates']}个有效信号日）")
            for b, v in zip(bars, vals):
                if np.isfinite(v):
                    ax.annotate(f'{v:.2%}', (b.get_x() + b.get_width() / 2, v), xytext=(0, 3 if v >= 0 else -9),
                                textcoords='offset points', ha='center', fontsize=6.5)
        ax.margins(y=.16)                             # room for the value labels above and below the bars
        ax.axhline(0, color=GREY, lw=.7)
        ax.set_xticks(x, group_labels(n), fontsize=9)
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=2))
        ax.set_ylabel(f'未来{h}个交易日平均毛收益')
        ax.set_title(f'理论分组毛收益：每日按因子值动态五分组（G0最高），组内等权，持有{h}日，跨日算术平均', loc='left', fontsize=10.5, pad=34)
        ax.legend(ncol=len(stages), loc='lower left', bbox_to_anchor=(0, 1.0), fontsize=8.5)
        ax.grid(axis='y', color='#475f78', lw=.5, ls='--', alpha=.22)
        note = (f'收益 = open[t+1+{h}] / open[t+1] − 1（未复权，未扣费、滑点和交易限制）；相邻信号日持有期重叠，不是可交易组合或账户净值。')
        if 'test' in stats:
            t = result['metrics']['professional']['test']
            note += (f"\nTest = ROLLING_EXPOSED_TEST（持续曝光，非盲测 / not blind），快照截至{t['snapshot']['certified_end']}，"
                     f"未成熟信号日{len(t['maturity'].get('immature_signal_dates', []))}个不计入。")
        fig.text(.08, .015, note, fontsize=7, color=GREY, linespacing=1.4)
        fig.subplots_adjust(left=.1, right=.98, bottom=.27 if 'test' in stats else .23, top=.80)
        for fmt in ('png', 'svg', 'pdf'):
            fig.savefig(run / 'figures' / f'group_returns_gross.{fmt}', dpi=300, metadata={'Creator': 'Research Agent'} if fmt == 'pdf' else None)
        plt.close(fig)


def _pp(x):
    return 'N/A' if x is None or not np.isfinite(x) else f'{x * 100:+.2f}个百分点'


def _ci_text(ci):
    lo, hi = ci
    if lo is None or hi is None:
        return '区间不可用（序列不完整或样本不足，未计算）'
    side = '跨0' if lo <= 0 <= hi else ('不跨0（为正）' if lo > 0 else '不跨0（为负）')
    return f'HAC 95%区间 [{lo * 100:+.2f}, {hi * 100:+.2f}] 个百分点，{side}'


def group_analysis(result, stats):
    """Deterministic natural-language reading of the groups against the frozen ex-ante direction."""
    n, h = result['spec']['n_groups'], result['spec']['horizon']
    last = f'G{n - 1}'
    r = result.get('economic_rationale') or {}
    expected = {'positive': 1, 'negative': -1}.get(r.get('expected_direction')) if r.get('status') == 'CHECKED' else None
    lines = []
    if expected == 1:
        lines.append(f'事前（结果计算前冻结）预期：因子值越高未来收益越高，即G0应高于{last}，组间大致由高到低递减。')
    elif expected == -1:
        lines.append(f'事前（结果计算前冻结）预期：因子值越高未来收益越低，即G0应低于{last}。')
    else:
        lines.append('没有冻结的事前方向，以下只描述观察到的组间关系，不判断是否支持某一机制。')
    for key, label in STAGES:
        s = stats.get(key)
        if not s:
            continue
        sp = s['spread']
        order = ('严格单调' if s['strict'] else '大致单调' if s['monotonic'] is not None and abs(s['monotonic']) >= 0.7 else '无明显单调')
        mono_dir = '' if s['monotonic'] is None else ('（组越靠前收益越高）' if s['monotonic'] > 0 else '（组越靠后收益越高，与G0最高分反向）')
        ric = 'N/A' if s['rank_ic'] is None else f"{s['rank_ic']:+.4f}"
        text = (f"{label}：G0−{last} = {_pp(sp)}（{h}日理论毛收益之差，{s['n_dates']}个有效信号日），{_ci_text(s['ci'])}；"
                f"组间{order}{mono_dir}；RankIC {ric}。")
        if expected is not None and sp is not None and np.isfinite(sp):
            agree = np.sign(sp) == expected
            lo, hi = s['ci']
            decided = lo is not None and hi is not None and not (lo <= 0 <= hi)
            if agree and decided:
                text += '与事前方向一致，且组间差统计上可与0区分。'
            elif agree:
                text += '方向与事前一致，但组间差的区间跨0，属于观察结果，证据不足。'
            elif decided:
                text += '方向与事前相反，且区间不跨0：该阶段不支持事前假设。'
            else:
                text += '方向与事前相反，但区间跨0，只是观察结果，不能据此断言因子失效。'
        rc = s['rank_ci']
        if rc and rc[0] is not None and sp is not None and s['rank_ic'] is not None and np.sign(sp) != np.sign(s['rank_ic']):
            text += '注意：组间差与RankIC符号不同，说明收益差主要来自少数组或极端值，排序关系并不稳定。'
        lines.append(text)
    if 'test' in stats:
        m = [v for v in stats['test']['means'] if v is not None]
        if m and all(v < 0 for v in m):
            lines.append('Test期间各组平均收益均为负，反映的是这段时间A股整体（未复权、毛收益）的走势；判断因子要看组间相对差和排序关系，而不是各组绝对收益是否为正。')
    paper = result.get('paper')
    if paper and paper.get('substitutions'):
        lines.append('本研究是基于A股未复权日频数据的探索性替代，与论文原文的样本、频率与组合规则不同（差异见研究定义）；'
                     '方向与论文不一致不构成对原论文结论的检验或推翻。')
    return lines


def group_section(run, result, table, chart):
    """HTML + Markdown for the 分组表现 section: chart, method, statistics table, deterministic reading."""
    stats = group_stats(run, result)
    group_figure(run, result, stats)                 # one chart for every report revision: 2 stages, or 3 with the rolling Test
    n, h = result['spec']['n_groups'], result['spec']['horizon']
    method = [
        f'分组依据：每个信号日t，取当日在股票池内（开盘价、收盘价存在且成交量>0）且因子值有限的全部股票，按当日因子值从高到低排序，切成{n}个股票数相等的组；'
        f'G0为当日得分最高的约{100 // n}%，依次到G{n - 1}为最低的约{100 // n}%；并列值按代码列顺序确定先后，当日有效股票少于{n}只则不分组。',
        '时间逻辑：每天用当日因子值重新分组，不沿用前一日或前一阶段的成员；Train、Validation、Test使用同一冻结公式与同一分组规则，Validation期间的组成员不会被带入2026 Test。',
        f'每根柱子：该阶段所有有效信号日上，组内股票“未来{h}日开盘到开盘收益”（open[t+1+{h}] / open[t+1] − 1，T日收盘出信号、T+1开盘进入）的等权平均，再对日期取算术平均；'
        '没有未来收益（停牌、退市或标签未成熟）的股票不计入当日平均。',
        f'口径限制：未复权价格；未扣手续费、滑点、冲击成本；未处理涨跌停、停牌等可交易性约束；相邻信号日的{h}日持有期互相重叠，柱子不是复合收益，'
        '也不是可执行组合或账户净值。各阶段只保留卖出日仍在该阶段内的标签，不跨阶段边界。',
        f'G0−G{n - 1}：逐日组间差的算术平均，是理论毛收益差，不是真实多空策略收益；区间为逐日序列的HAC（Newey-West）95%近似区间，只作描述，不做多重检验校正。',
    ]
    size = {k: (None if s['stocks'] is None else s['stocks'] / n) for k, s in stats.items()}
    rows = []
    for key, label in STAGES:
        s = stats.get(key)
        if s:
            rows.append([label, *s['means'], s['spread'], ('N/A' if s['ci'][0] is None else f"[{s['ci'][0]:+.2%}, {s['ci'][1]:+.2%}]"),
                         s['monotonic'], ('N/A' if size[key] is None else f'{size[key]:.1f}'), s['n_dates']])
    headers = ['阶段', *[f'G{g}' for g in range(n)], f'G0−G{n - 1}', 'HAC 95%区间', '单调性¹', '平均每组股票数', '有效信号日']
    t, tmd = table('group_summary', f'分组未来{h}日平均毛收益与组间差', headers, rows,
                   ['number'] + ['percent'] * (n + 1) + ['number', 'number', 'number', 'count'])
    analysis = group_analysis(result, stats)
    html = (chart('group_returns_gross', f'每日按当日因子值动态{n}等分（G0最高），组内等权，未来{h}日开盘到开盘毛收益，跨日算术平均；未扣费、非账户净值。')
            + '<div class="explain"><h3>这张图怎么读</h3><ul>' + ''.join('<li>' + escape(x) + '</li>' for x in method) + '</ul></div>'
            + t + '<p class="note">¹ 单调性 = −Spearman(组序号, 组平均收益)：+1表示G0到末组严格递减（高分组收益更高），−1表示严格递增（低分组收益更高）。</p>'
            + '<h3>分组结果解读（程序依据数值生成）</h3>' + ''.join('<p>' + escape(x) + '</p>' for x in analysis))
    md = '\n'.join('- ' + x for x in method) + '\n\n' + tmd + '\n\n' + '\n\n'.join(analysis)
    return html, md, stats


CHART_NOTES = {
    'ic': 'IC为每个信号日当日因子值与未来收益的截面Pearson相关；RankIC用排名（Spearman），对极端值更稳健。'
          '均值为正表示因子值高的股票未来收益平均更高；单日波动很大，应看均值、区间与稳定性。',
    'hac': 'HAC 95%区间对重叠持有期造成的自相关做Newey-West修正；区间跨0表示当前样本未提供明确证据，不等于证明无效；'
           '区间不跨0也只说明统计上可与0区分，不代表可交易或存在因果关系。',
    'cumulative': '理论累计曲线每隔H个信号日取一次、互不重叠、复利连乘的组收益路径，Train→Validation→Test连续累乘（Test段从Validation末端水平接续），'
                  '阶段边界处被剔除的跨界标签显示为断点；用来观察相对走势，未扣成本、不考虑可交易性，不是账户净值。',
    'coverage': '覆盖率 = 当日有有限因子值的股票数 / 股票池股票数；开头的低覆盖来自暖机期（因子需要足够历史），不是数据缺失被填补。',
    'decay': '衰减图对每个预测期H分别构造成熟标签并按阶段边界截断，观察预测力随持有期的变化；2026 Test只评价冻结的预测期H。',
    'boundary': '虚线标出Validation（2024-01-02起）与Test（2026起）的边界；Train/Validation为已曝光的研究样本，'
                'Test为2026滚动暴露评价：每次有新交易日都会重新计算，持续曝光，不是严格盲测。',
    'immature': '最近H+1个信号日的未来收益尚未在数据快照中出现（标签未成熟），显示为N/A；不补0、不预测，等新交易日到来后自动更新。',
    'limits': '所有结果基于未复权行情、未认证的历史股票池和毛收益；不构成可交易结论，正式账户回测仍未准入。',
}


def methodology_html():
    items = [('IC / RankIC', CHART_NOTES['ic']), ('HAC置信区间与显著性', CHART_NOTES['hac']), ('理论累计曲线与净值', CHART_NOTES['cumulative']),
             ('因子覆盖率与有效样本', CHART_NOTES['coverage']), ('预测期衰减', CHART_NOTES['decay']), ('阶段边界与2026滚动暴露', CHART_NOTES['boundary']),
             ('未成熟标签 N/A', CHART_NOTES['immature']), ('可交易性限制', CHART_NOTES['limits'])]
    body = ''.join('<dt>' + escape(k) + '</dt><dd>' + escape(v) + '</dd>' for k, v in items)
    md = '\n'.join(f'- **{k}**：{v}' for k, v in items)
    return '<details class="method"><summary>方法说明（指标定义、统计口径与限制，点击展开）</summary><dl>' + body + '</dl></details>', md


# Render-time Chinese wording of the stored English limitation strings (stored results are unchanged; unknown text is shown as is).
LIMIT_CN = {
    'PROFILED_EXPLORATORY_ONLY; not backtest approved': '数据仅为探索性画像级别（PROFILED_EXPLORATORY_ONLY），未获正式回测准入。',
    'raw prices may distort returns across corporate actions': '使用未复权价格：除权除息、拆并股等公司行为会扭曲收益。',
    'listing dates and historical universe PIT unverified': '上市日期与历史股票池未做时点（PIT）认证，可能存在幸存者偏差。',
    'observed calendar, trade status and delisting valuations uncertified': '交易日历、交易状态与退市估值未经认证。',
    'IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores':
        'IC针对所述原始因子计算；方向+1在结果前固定；G0为因子值最高组。',
    'group returns are gross, equal weight, missing labels excluded; not account returns':
        '分组收益为等权毛收益，缺失标签剔除；不是账户收益。',
    'no industry/size neutralisation or multiple-testing adjustment; HAC inference has explicit sample admission':
        '未做行业/市值中性化，未做多重检验校正；HAC推断有明确的最小样本准入。',
    'positive observed volume is sample eligibility, not permission to buy/sell':
        '成交量>0只表示进入样本，不代表当日可以买入或卖出。',
    'all parameter changes after seeing validation are exploratory; no certified out-of-sample performance':
        '看到Validation后的任何参数修改都属于探索性研究；没有经认证的样本外表现。',
    'Train2020-2023 and Validation2024-2025 are separate hash-checked published partitions; 2026 unavailable to ordinary research resources; approved evaluator statistics are separate':
        'Train 2020–2023 与 Validation 2024–2025 为分别校验哈希的发布分区；2026行情不向普通研究资源开放，Test统计只由受控评价器单独计算。',
    'Train2020-2023 and Validation2024-2025 are separate hash-checked published partitions; 2026 unavailable':
        'Train 2020–2023 与 Validation 2024–2025 为分别校验哈希的发布分区；2026行情不向普通研究资源开放。',
    'Validation warm-up uses permitted Train history; Train labels crossing boundary purged, Validation tail not filled from 2026':
        'Validation暖机使用允许的Train历史；跨越边界的Train标签被剔除，Validation尾部不使用2026数据补齐。',
    'listing dates are unverified; published candidate prelisting mask does not certify a historical PIT stock universe':
        '上市日期未核实；发布的上市前掩码不能证明历史时点股票池。',
    'no embargo gap requested: chronological factor diagnostics only, no supervised train-label fit; lag+H boundary purge applied':
        '未设置禁区间隔：仅做按时间顺序的因子诊断，没有用Train标签拟合模型；已按lag+H剔除跨界标签。',
    'volume is lots (100 shares), amount thousand CNY; price-relative label is not corporate-action-adjusted total return':
        '成交量单位为手（100股），成交额单位为千元；价格比值标签不是经公司行为调整的总收益。',
    'test is sealed; no independent test claim': 'Test已封存；不作独立测试结论。',
}
UNSUPPORTED_CN = {
    'industry/size neutralisation': '行业/市值中性化',
    'existing-factor correlation without authorized reference': '与已有因子的相关性（缺少授权的参考因子库）',
    'true independent OOS': '真正独立的样本外检验',
    'tradable NAV, Sharpe, drawdown, costs': '可交易净值、夏普、回撤与交易成本',
}


def limitation_cn(text):
    """Chinese wording for a stored limitation string; patterns with numbers are matched, unknown text is returned as is."""
    import re
    if text in LIMIT_CN:
        return LIMIT_CN[text]
    m = re.fullmatch(r'labels overlap \(h=(\d+)\)[:;]? ICIR not annualised;?\s*(effective independent dates ~ n/\d+)?', text)
    if m:
        return (f'相邻信号日的{m.group(1)}日持有期标签相互重叠；ICIR未年化'
                + (f'；有效独立样本约为 n/{m.group(1)}' if m.group(2) else '') + '。')
    m = re.fullmatch(r'(.+): insufficient valid dates', text)
    if m:
        return f'{m.group(1)}：有效评价日不足。'
    return text


def limits_html(limits, unsupported):
    """Limits chapter: known limitations in Chinese, then what the system does not yet support (next steps)."""
    known = list(dict.fromkeys(limitation_cn(x) for x in limits))
    todo = [UNSUPPORTED_CN.get(x, x) for x in dict.fromkeys(unsupported)]
    html = '<h3>已知局限</h3><ul>' + ''.join('<li>' + escape(x) + '</li>' for x in known) + '</ul>'
    md = '\n'.join('- ' + x for x in known)
    if todo:
        html += '<h3>尚未支持（下一步）</h3><ul>' + ''.join('<li>' + escape(x) + '</li>' for x in todo) + '</ul>'
        md += '\n\n尚未支持（下一步）：\n' + '\n'.join('- ' + x for x in todo)
    return html, md


STATUS_CN = {"PASSED": "通过", "FAILED": "未通过", "NOT_VERIFIED": "未核验", "SUBSTITUTED": "已替代（非忠实）", "NOT_APPLICABLE": "不适用"}
KIND_CN = {"asset_substitution": "资产替代", "data_object": "数据对象", "parameter_choice": "参数选择", "interpretation": "含义解释",
           "recursion_truncation": "递归截断", "derived_input": "派生输入", "unadjusted_prices": "未复权价格", "frequency_conversion": "频率换算",
           "evaluation_method": "评价方法", "formula_restatement": "公式重述", "price_basis": "价格口径", "window_approximation": "窗口近似"}


SOURCE_CN = {"ai_misreading": "AI 理解错误", "extraction_error": "PDF/公式提取错误", "unsupported_notation": "程序暂不支持的记法",
             "paper_ambiguity": "论文本身存在歧义或未写明", "data_mismatch": "研究对象与现有数据不匹配", "free_parameter": "需要用户选择的自由参数"}
PARSE_CN = {"PARSED":"已解析为受控公式", "ALGORITHM": "算法步骤（非闭式公式）", "PARAMETER_UNBOUND": "参数待用户确定",
            "PROGRAM_PARSE_INCOMPLETE": "程序解析未完成", "NO_FORMULA": "没有公式"}
PARAM_CN = {"PAPER": "原文给出（已逐字核验）", "USER": "用户指定", "UNVERIFIED": "模型给出但原文找不到", "UNSTATED": "原文未给出"}
TOOL_CN = {"search": "检索", "read": "读段落", "page": "读整页（含原始文本层）"}


def reconciliation_html(rec, table):
    """AI reading x program analysis: what each side read, the conflicts and their sources, the reader's investigation."""
    html = "<h3>AI 解读与程序核对</h3>"
    md = "### AI 解读与程序核对\n\n"
    ai, prog = rec.get("ai_initial") or {}, rec.get("program_parse") or {}
    rows = [["AI 首次解读", ai.get("formula") or ("算法步骤" if ai.get("algorithm") else "无"), str(ai.get("status") or "")],
            ["程序解析", prog.get("written") or "", PARSE_CN.get(prog.get("status"), str(prog.get("status")))],
            ["参数绑定后", prog.get("bound") or "", "按核验通过的参数取值代入" if prog.get("bound") != prog.get("written") else "无需代入"],
            ["最终执行", (rec.get("final") or {}).get("formula") or "", str((rec.get("final") or {}).get("status") or "")]]
    if prog.get("layout_formula"):
        lf = prog["layout_formula"]
        rows.insert(2, ["PDF 版面重建公式", lf.get("latex") or "", f"p{lf.get('page')}（程序独立重建）"])
    t, tmd = table("paper_reconcile", "两条路径的读取结果", ["来源", "公式", "状态"], rows, ["number"] * 3)
    html, md = html + t, md + tmd + "\n\n"
    if rec.get("parameters"):
        t, tmd = table("paper_parameters", "参数（只采用原文逐字核验或用户指定的数值）", ["参数", "含义", "取值", "依据", "原文测试过的取值", "原文出处"],
                       [[p["symbol"], p.get("meaning") or "", "" if p.get("value") is None else p["value"], PARAM_CN.get(p["status"], p["status"]),
                         "、".join(str(v) for v in p.get("paper_values") or []) or "—",
                         "；".join(f"p{c.get('page')}“{c.get('quote', '')[:60]}”" for c in p.get("citations") or []) or "无"]
                        for p in rec["parameters"]], ["number"] * 6)
        html, md = html + t, md + tmd + "\n\n"
    if rec.get("conflicts"):
        t, tmd = table("paper_conflicts", "分歧与来源判断", ["问题", "符号", "是否阻断", "来源判断", "判断依据", "说明"],
                       [[c["code"], c.get("symbol") or "", "阻断" if c.get("blocking") else "需确认/提示", c.get("source_cn") or "",
                         "AI 主张经程序核实" if c.get("source_basis") == "reader_claim_verified" else "程序规则", c.get("detail") or ""]
                        for c in rec["conflicts"]], ["number"] * 6)
        html, md = html + t, md + tmd + "\n\n"
    for r in rec.get("investigations") or []:
        reqs = "；".join(TOOL_CN.get(q.get("tool"), str(q.get("tool"))) + (f"“{q['query']}”" if q.get("query") else "")
                        + (f" 第{q['pages'][0]}页" if q.get("pages") else "") for q in r.get("requests") or []) or "未调用工具"
        line = (f"第{(r.get('attempt') or 0) + 1}次调查（{r.get('rounds')} 轮模型调用）：{reqs}。"
                f"问题 {','.join(r.get('conflicts_before') or [])} → {','.join(r.get('conflicts_after') or []) or '已解决'}；"
                f"公式 {r.get('formula_before')} → {r.get('formula_after')}")
        html += '<p class="note">' + escape(line) + "</p>"
        md += "- " + line + "\n"
        for f in r.get("findings") or []:
            fl = (f"AI 判断 {f.get('issue')}{('（' + str(f['symbol']) + '）') if f.get('symbol') else ''} 来源为“"
                  f"{SOURCE_CN.get(f.get('source'), f.get('source'))}”：{f.get('explanation')}；程序{'采纳' if f.get('accepted') else '未采纳'}（{f.get('why')}）")
            html += '<p class="note">' + escape(fl) + "</p>"
            md += "  - " + fl + "\n"
        if r.get("page_images"):
            pi = "、".join(f"{x['name']}（sha256 {x['sha256'][:12]}）" for x in r["page_images"])
            html += '<p class="note">' + escape("供人工复核的页面截图：" + pi) + "</p>"
            md += "  - 供人工复核的页面截图：" + pi + "\n"
    if rec.get("user_parameters"):
        u = "、".join(f"{k}={v}" for k, v in rec["user_parameters"].items())
        html += '<p class="note">' + escape("用户确认/指定的参数：" + u) + "</p>"
        md += "用户确认/指定的参数：" + u + "\n\n"
    if rec.get("uncertainties"):
        html += "<p class=\"note\">仍存在的不确定性：</p><ul>" + "".join("<li>" + escape(x) + "</li>" for x in rec["uncertainties"]) + "</ul>"
        md += "仍存在的不确定性：\n" + "\n".join("- " + x for x in rec["uncertainties"]) + "\n\n"
    html += '<p class="note">' + escape(rec.get("boundary") or "") + "</p>"
    md += (rec.get("boundary") or "") + "\n\n"
    return html, md


def paper_definition_section(result, table):
    """Paper -> structured definition -> executed formula, as checked before computation; invalid or non-faithful studies
    are flagged at the top (validity comes from the append-only invalidation registry, never from editing the record)."""
    d = result.get("paper_definition")
    inv = result.get("invalidation")
    if not d and not inv:
        return None
    html, md = "", ""
    if inv:
        msg = ("研究定义无效：" + inv.get("reason_cn", "") + "。本报告的统计结果不能作为该论文因子的研究结论；"
               "原始成果按审计要求保留，未删除或改写。")
        html += '<div class="banner invalid">' + escape(msg) + "</div>"
        md += "> **" + msg + "**\n\n"
        for e in inv.get("evidence") or []:
            html += '<p class="note">' + escape("证据：" + str(e)[:300]) + "</p>"
            md += "- 证据：" + str(e)[:300] + "\n"
        html += '<p class="note">' + escape(f"登记：{inv.get('recorded_by')} · {inv.get('recorded_at')} · {inv.get('code')}") + "</p>"
    if not d:
        return html, md
    if not d.get("faithful"):
        kinds = {s["kind"] for s in d.get("substitutions", [])}
        msg = ("非忠实复现：研究资产已从“" + (d["asset"].get("summary_cn") or "原论文资产") + "”替换为A股个股，"
               "结果不能代表原论文，原论文的结论不可沿用。" if d["asset"].get("substituted") else
               "探索性替代研究：以下差异经用户确认后执行，不称为论文复现。")
        html += '<div class="banner ' + ("invalid" if d["asset"].get("substituted") else "explore") + '">' + escape(msg) + "</div>"
        md += "> " + msg + "\n\n"
    p = d["paper_text"]
    html += "<h3>原论文定义与证据</h3><p>" + escape(str(p.get("verbal") or "")) + "</p>"
    md += "### 原论文定义与证据\n\n" + str(p.get("verbal") or "") + "\n\n"
    for c in (p.get("verbal_citations") or []) + (p.get("formula_citations") or []):
        line = f"p{c.get('page')} {c.get('passage')}：“{c.get('quote')}”"
        html += '<p class="note">' + escape(line) + "</p>"
        md += "- " + line + "\n"
    html += '<p class="note">模型对原文公式的结构化重述（' + escape(str(p.get("formula_status"))) + "）：" + escape(p.get("formula_latex") or "") + "</p>"
    rows = [[s["symbol"], s.get("kind") or "", s.get("field") or "", s.get("meaning") or "",
             "；".join(f"p{c.get('page')}“{c.get('quote')[:60]}”" for c in s.get("citations") or []) or "无"] for s in d["symbols"]]
    t, tmd = table("paper_symbols", "符号表（每个符号均需原文定义）", ["符号", "类型", "映射字段", "含义", "原文出处"], rows, ["number"] * 5)
    html += t
    md += "\n" + tmd + "\n"
    e = d["executed"]
    html += "<h3>实际执行公式（按交易日行）</h3><p class=\"formula\">" + escape(e["formula"] or "") + "</p>"
    html += "<p class=\"note\">需要 " + escape(str(e["warmup_rows"])) + " 个交易日历史。</p><ul>" + \
        "".join("<li>" + escape(x) + "</li>" for x in e.get("timeline") or []) + "</ul>"
    md += "### 实际执行公式\n\n" + (e["formula"] or "") + "\n\n" + "\n".join("- " + x for x in e.get("timeline") or []) + "\n\n"
    if e.get("worked_examples"):
        t, tmd = table("paper_examples", "定义→执行数值核对（构造价格路径）", ["符号", "回看行", "跳过行", "收益口径", "按声明手算", "执行公式", "结论"],
                       [[x["symbol"], x["n_rows"], x["skip_rows"], {"log": "对数", "simple": "简单"}[x["compounding"]],
                         f"{x['declared_value']:.8f}", f"{x['executed_value']:.8f}", "一致" if x["match"] else "不一致"] for x in e["worked_examples"]],
                       ["number", "count", "count", "number", "number", "number", "number"])
        html += t
        md += tmd + "\n\n"
    if d.get("substitutions"):
        t, tmd = table("paper_differences", "原论文与本次研究的全部差异（用户已确认）", ["类别", "项目", "原论文", "本次研究"],
                       [[KIND_CN.get(s["kind"], s["kind"]), s["item"], s["paper"], s["ours"]] for s in d["substitutions"]], ["number"] * 4)
        html += t
        md += tmd + "\n\n"
    cross = result.get("implementation_crosscheck") or []
    checks = list(d.get("checks") or [])
    if cross:
        c0 = cross[0]
        checks.append({"name": "执行器×参考求值器逐格核对", "status": "PASSED" if not (c0.get("nan_pattern_mismatch") or c0.get("cells_outside_tolerance")) else "FAILED",
                       "detail": f"{c0.get('rows')}行×{c0.get('cols')}列，非空单元格 {c0.get('non_nan_cells')}，超差 {c0.get('cells_outside_tolerance')}，"
                                 f"缺失模式不一致 {c0.get('nan_pattern_mismatch')}"})
    t, tmd = table("paper_checks", "核验清单（计算任何结果之前完成）", ["检查", "结论", "说明"],
                   [[c["name"], STATUS_CN.get(c["status"], c["status"]), c["detail"]] for c in checks], ["number"] * 3)
    html += t
    md += tmd + "\n\n"
    rec = d.get("reconciliation")
    if rec:
        h, m = reconciliation_html(rec, table)
        html += h
        md += m
    elif d.get("semantic_repairs"):
        line = "；".join(f"第{r['attempt'] + 1}次重读：{','.join(r['conflicts_before'])} → {','.join(r['conflicts_after']) or '已解决'}"
                        for r in d["semantic_repairs"])
        html += '<p class="note">' + escape("语义纠错重读记录：" + line) + "</p>"
        md += "语义纠错重读记录：" + line + "\n\n"
    html += ('<p class="note">核验边界：程序能确认引文逐字存在、时间下标与回看/滞后用法一致、数值有出处、执行公式与声明一致；'
             '不能证明模型对原文经济含义的理解完全正确，也不能核对文本层缺失的公式图像。</p>')
    return html, md
