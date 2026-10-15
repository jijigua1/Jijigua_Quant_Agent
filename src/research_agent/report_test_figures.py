"""Static report figures for a ROLLING_EXPOSED_TEST revision.

A revision copies the study's static figures, which cover Train/Validation only. Charts whose Test evidence is in the
verified receipt (daily IC/RankIC, daily group forward returns, Test IC at the frozen horizon) are redrawn on one continuous
axis with both split boundaries. Charts whose Test evidence the Agent may not see (Test-period factor values) keep their
Train/Validation content and state that inside the image. Nothing is estimated, filled or extrapolated.
"""
from pathlib import Path

TEST = '#3a7d44'
NO_TEST_VALUES = {
    'factor_distribution': 'Test期因子值只由独立评价器计算，不发放给Agent；本图只覆盖 Train / Validation。',
}
PERSISTENCE_NOTE = 'Test期因子值不发放给Agent，因此不显示Test持续性；本图只覆盖 Train / Validation（由已存的稳定性统计重绘）。'


def render(run, result):
    """Redraw / annotate static figures of a completed rolling revision; returns the figure names written."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.dates as mdates
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from matplotlib.ticker import PercentFormatter
    from .research_report import AMBER, BLUE, GREY
    from .server_plot import configure_chinese_font
    run = Path(run)
    p = result['metrics']['professional']
    test = p['test']
    if test.get('status') != 'COMPLETED':
        return []
    spec, h = result['spec'], result['spec']['horizon']
    from .report_versions import test_daily
    daily = pd.DataFrame(test_daily(run, test))
    daily['date'] = pd.to_datetime(daily['date'])
    daily = daily.set_index('date').sort_index()
    for c in daily.columns:
        if c != 'matured':
            daily[c] = pd.to_numeric(daily[c], errors='coerce')    # receipt nulls (immature labels) stay NaN
    daily['split'] = 'test'
    immature = len(test['maturity'].get('immature_signal_dates', []))
    footer = (f"Train {spec['train'][0]}–{spec['train'][1]} · Validation {spec['valid'][0]}–{spec['valid'][1]} · "
              f"Test {test['start']}–{test['end']}\nTest = ROLLING_EXPOSED_TEST（持续曝光，非盲测）· 快照截至 "
              f"{test['snapshot']['certified_end']} · {immature}个未成熟信号日显示为N/A")
    written = []
    try:
        font_name = configure_chinese_font().get_name()
    except RuntimeError:
        font_name = 'DejaVu Sans'
    style = {'font.family': 'sans-serif', 'font.sans-serif': [font_name, 'DejaVu Sans'], 'font.size': 10.5,
             'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#bcc5ce', 'axes.linewidth': .6,
             'axes.unicode_minus': False, 'svg.fonttype': 'none', 'pdf.fonttype': 42, 'legend.frameon': False}
    splits = [('train', BLUE, 'Train'), ('valid', AMBER, 'Validation'), ('test', TEST, 'Test')]

    def save(fig, name, title, ylabel, dates=False, note=None):
        ax = fig.axes[0]
        ax.set_title(title, loc='left', fontsize=12, pad=45)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', color='#475f78', lw=.6, ls='--', alpha=.25)
        ax.set_axisbelow(True)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, ncol=2 if len(handles) == 4 else 3, loc='lower left', bbox_to_anchor=(0, 1.02), fontsize=9)
        if dates:
            loc = mdates.AutoDateLocator(minticks=3, maxticks=7)
            ax.xaxis.set_major_locator(loc)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
            ax.axvspan(pd.Timestamp(spec['valid'][0]), pd.Timestamp(spec['valid'][1]), color=AMBER, alpha=.055)
            ax.axvspan(pd.Timestamp(test['start']), pd.Timestamp(test['end']), color=TEST, alpha=.06)
            for date, label in ((spec['valid'][0], 'Validation'), (test['start'], 'Test')):
                ax.axvline(pd.Timestamp(date), color=GREY, ls='--', lw=.7)
                ax.text(pd.Timestamp(date), 1.01, label, transform=ax.get_xaxis_transform(), fontsize=8, color=GREY)
        fig.text(.13, .075, footer, fontsize=8, color=GREY, va='bottom', linespacing=1.4)
        if note:
            fig.text(.13, .02, note, fontsize=8, color=GREY)
        fig.subplots_adjust(left=.13, right=.98, bottom=.3, top=.74)
        for fmt in ('png', 'svg', 'pdf'):
            fig.savefig(run / 'figures' / f'{name}.{fmt}', dpi=300, metadata={'Creator': 'Research Agent'} if fmt == 'pdf' else None)
        plt.close(fig)
        written.append(name)

    with plt.rc_context(style):
        # 1. predictive power over the continuous Train | Validation | Test axis (immature tail stays a gap)
        hist = pd.read_csv(run / 'data/ic_rankic.csv', index_col=0, parse_dates=True)
        frame = pd.concat([hist[['ic', 'rank_ic', 'split']], daily[['ic', 'rank_ic', 'split']]]).sort_index()
        fig, ax = plt.subplots(figsize=(7.8, 3.4))
        for col, color, label in (('ic', BLUE, 'IC'), ('rank_ic', AMBER, 'RankIC')):
            ax.plot(frame.index, frame[col], color=color, lw=.7, alpha=.35, label=label)
            roll = frame.groupby('split')[col].transform(lambda x: x.rolling(5, min_periods=5).mean())
            ax.plot(frame.index, roll, color=color, lw=1.5, label=label + ' · 5日均值')
        ax.axhline(0, color=GREY, lw=.7)
        save(fig, 'ic_rankic', '预测能力随时间变化 · Train / Validation / Test', '截面相关系数', True)

        # 2. distribution of daily IC / RankIC per stage
        fig, ax = plt.subplots(figsize=(7.8, 3.4))
        bins = np.linspace(-1, 1, 21)
        for split, color, label in splits:
            part = frame[frame['split'] == split]
            r, i = part['rank_ic'].dropna(), part['ic'].dropna()
            if len(r):
                ax.hist(r, bins=bins, histtype='step', lw=1.5, color=color, density=True, label=f'{label} RankIC · n={len(r)}')
            if len(i):
                ax.hist(i, bins=bins, histtype='step', lw=1, ls='--', color=color, density=True, label=f'{label} IC · n={len(i)}')
        ax.set_xlabel('逐日截面相关系数（各阶段分别归一化为密度）')
        save(fig, 'ic_distribution', 'IC / RankIC 逐日分布 · Train / Validation / Test', '密度')

        # 3. the G0–G4 chart is drawn by report_explain.group_figure when the revision is rendered (same code as revision 1)

        # 4. decay: Train / Validation curves; Test is evaluated only at the frozen horizon H
        decay = pd.DataFrame(result['metrics']['decay'])
        fig, ax = plt.subplots(figsize=(7.8, 3.4))
        for split, color, label in splits[:2]:
            t = decay[decay['split'] == split]
            ax.plot(t.horizon, t.rank_ic_mean, marker='o', ms=4, color=color, label=label + ' RankIC')
            ax.plot(t.horizon, t.ic_mean, marker='s', ms=3, color=color, ls='--', alpha=.7, label=label + ' IC')
        m = test['metrics']
        if m.get('rank_ic_mean') is not None:
            ax.plot([h], [m['rank_ic_mean']], marker='*', ms=11, color=TEST, ls='none', label=f'Test RankIC（仅H={h}）')
        if m.get('ic_mean') is not None:
            ax.plot([h], [m['ic_mean']], marker='D', ms=5, color=TEST, ls='none', label=f'Test IC（仅H={h}）')
        ax.axhline(0, color=GREY, lw=.7)
        ax.set_xticks(sorted(decay.horizon.unique()))
        ax.set_xlabel('预测期H（交易日）')
        save(fig, 'ic_decay', '预测期衰减 · 标签按阶段边界剔除', 'IC / RankIC 均值',
             note=f'Test：受控评价器只计算冻结的预测期 H={h}，其他预测期未评价。')

        # 4b. persistence: redrawn from the stored Train/Validation stability statistics (no factor matrix is read)
        stability = pd.DataFrame(result['metrics'].get('stability', []))
        if len(stability):
            fig, ax = plt.subplots(figsize=(7.8, 3.4))
            for split, color, label in splits[:2]:
                t = stability[stability['split'] == split]
                ax.plot(t.lag, t.correlation, marker='o', ms=4, color=color, label=label + ' · 数值相关')
                ax.plot(t.lag, t.rank_correlation, marker='s', ms=3, ls='--', color=color, alpha=.65, label=label + ' · 排序相关')
            ax.axhline(0, color=GREY, lw=.7)
            ax.set_xticks(sorted(stability.lag.unique()))
            ax.set_xlabel('滞后期（交易日）· 因子自身的跨日相关，不是未来收益自相关')
            save(fig, 'factor_autocorrelation', '因子持续性 · 相邻两日共同股票', '平均相关系数', note=PERSISTENCE_NOTE)

        # 5. charts without releasable Test values: original image kept, the reason written into the figure itself
        for name, note in NO_TEST_VALUES.items():
            src = run / 'figures' / f'{name}.png'
            if not src.exists():
                continue
            image = mpimg.imread(src)
            height, width = image.shape[:2]
            band = .45 / (height / 300 + .45)                  # a separate strip under the unchanged original image
            fig = plt.figure(figsize=(width / 300, height / 300 + .45))
            ax = fig.add_axes([0, band, 1, 1 - band])
            ax.imshow(image)
            ax.axis('off')
            fig.text(.12, band / 2, note, fontsize=8, color=GREY, va='center')
            for fmt in ('png', 'svg', 'pdf'):
                fig.savefig(run / 'figures' / f'{name}.{fmt}', dpi=300, metadata={'Creator': 'Research Agent'} if fmt == 'pdf' else None)
            plt.close(fig)
            written.append(name)
    return written
