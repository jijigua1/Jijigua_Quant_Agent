"""Evidence-first financial reports over reviewed numerical artifacts."""
import base64,json
from html import escape
from pathlib import Path
import numpy as np
import pandas as pd
from . import __version__

VERSION='3.1.0'
# Adapted from GeorgeResearch/core_backtest/plotting.py, plot_final_result.
BLUE='#475f78';AMBER='#c84b31';GREY='#8a929a'

def number(x,unit='number'):
    if x is None or isinstance(x,(float,np.floating)) and not np.isfinite(x):return 'N/A'
    if isinstance(x,(bool,np.bool_)):return '是' if x else '否'
    if isinstance(x,str):return x
    if unit=='pvalue':return '<numeric precision' if x==0 else f'{x:.3g}'
    return f'{x:.2%}' if unit=='percent' else f'{x:.0f}' if unit=='count' else f'{x:.4f}'

def _clause(text):
    """Model text as a clause: trailing sentence/list punctuation removed so joins never print '。；' or '。。'."""
    return str(text).strip().rstrip('。；;，,.、 ').strip()

def _after(text,*leads):
    """Drop a lead phrase the model already wrote (e.g. '该因子衡量：该因子衡量…', '高因子值意味着因子值高意味着…')."""
    t=str(text).strip()
    for lead in leads:
        if t.startswith(lead):return t[len(lead):].lstrip('：: ')
    return t

def avg_count(x):
    """An average stock count reads as one decimal (3897.0353 -> 3897.0)."""
    return None if x is None or isinstance(x,(float,np.floating)) and not np.isfinite(x) else f'{x:.1f}'

def _merged_notes(notes):
    """One fact-check note per mechanism: '标为作者观点…已改标为Agent假设' already covers '涉及作者观点…已在正文标注'."""
    import re
    relabelled={m.group(1) for n in notes for m in [re.match(r'机制“(.+?)”标为作者观点但原文引用未能核对',n)] if m}
    return [n for n in notes if not any(n.startswith('机制“'+k+'”的表述涉及作者观点') for k in relabelled)]

def economic_section(result,table):
    """Economic Rationale (ex-ante, frozen before results) + deterministic ex-ante vs evidence comparison."""
    from .economic_rationale import STATUS_TEXT, compare, verdict_text
    r=result.get('economic_rationale');p=result['metrics'].get('professional')
    html='<h3>Economic Rationale · 经济逻辑与作用机制</h3>';md='### Economic Rationale · 经济逻辑与作用机制\n\n'
    if not r or r.get('status')!='CHECKED':
        msg='经济逻辑分析不可用（'+str((r or {}).get('reason','未生成'))+'）；本报告只提供统计证据，不补写事后解释。'
        return html+'<p class="note">'+escape(msg)+'</p>',md+msg
    direction={'positive':'正相关（因子值越高，预期未来收益越高）','negative':'负相关（因子值越高，预期未来收益越低）','unclear':'无法事前判断'}[r['expected_direction']]
    clarity={'clear':'机制较明确','tentative':'机制为待检验假设','unclear':'经济机制尚不明确'}[r['mechanism_clarity']]
    i=r['intuition'];paras=[]
    measures=_clause(_after(i['measures'],'该因子衡量'))
    paras.append(('经济直觉',(measures if measures.startswith(('该因子','本因子')) else '该因子衡量'+measures)+'。高因子值意味着'+_clause(_after(i['high_value_means'],'高因子值意味着','因子值高意味着','因子值越高意味着'))
        +'；低因子值意味着'+_clause(_after(i['low_value_means'],'低因子值意味着','因子值低意味着','因子值越低意味着'))+'。'))
    for m in r['mechanisms']:
        cite=''.join('（'+c['passage']+(', p'+str(c['page']) if c.get('page') else '')+'：“'+c['quote']+'”）' for c in m['citations'])
        lit=('（'+m['literature']+'）' if m['literature'] else '')
        paras.append(('潜在收益来源 · '+m['name'],m['explanation']+lit+cite+' ['+m['source_label']+']'))
    paras.append(('作用路径',' → '.join(_clause(x) for x in r['narrative'])+'。以上为待检验机制链，统计相关不构成因果证明。'))
    paras.append(('事前预期方向','在计算任何结果之前冻结：'+direction+'。'+_clause(r['direction_reason'])+'。'
        +('适用条件：'+_clause(r['conditions'])+'。' if r['conditions'] else '')+'机制判断：'+clarity+'。'+(_clause(r['ex_ante_note'])+'。' if r.get('ex_ante_note') else '')))
    if r['data_implications']:paras.append(('研究口径对经济含义的影响',r['data_implications']))
    lim='；'.join(_clause(x) for x in r['alternative_explanations']+r['failure_regimes']+r['deployment_limits'] if _clause(x))
    paras.append(('经济解释的局限','替代解释与可能失效的市场状态：'+lim+'。'))
    for title,text in paras:
        html+='<p><strong>'+escape(title)+'。</strong>'+escape(text)+'</p>';md+='**'+title+'。** '+text+'\n\n'
    if r['check_notes']:
        note='事实校验记录：'+' '.join(_merged_notes(r['check_notes']))
        html+='<p class="note">'+escape(note)+'</p>';md+=note+'\n\n'
    if p:
        rows=compare(r,p,result['splits'])
        t,tmd=table('economic_evidence','经济假设与实证证据对照',['阶段','事前方向','RankIC均值','HAC 95%区间','G0−末组','对照结论'],
            [[x['stage'],{1:'正',-1:'负',None:'未定'}[x['expected']],x.get('rank_ic'),
              None if not x.get('ci') else '['+(f"{x['ci'][0]:+.4f}" if x['ci'][0] is not None else 'N/A')+', '+(f"{x['ci'][1]:+.4f}" if x['ci'][1] is not None else 'N/A')+']',
              x.get('long_short'),STATUS_TEXT[x['status']]] for x in rows],['number','number','number','number','percent','number'])
        summary=verdict_text(r,rows)
        nxt='下一步检验：'+'；'.join(_clause(x) for x in r['next_tests'])+'。' if r['next_tests'] else ''
        html+=t+'<p>'+escape(summary)+'</p>'+('<p class="note">'+escape(nxt)+'</p>' if nxt else '')
        md+=tmd+'\n\n'+summary+('\n\n'+nxt if nxt else '')
    return html,md


def render(run,result,factor,series,goal,hypothesis,definition,progress=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import PercentFormatter
    from .server_plot import configure_chinese_font,annotate_group_returns
    try:font=configure_chinese_font();font_name=font.get_name();cjk=True
    except RuntimeError:font_name='DejaVu Sans';cjk=False
    metrics=result['metrics'];data=pd.read_csv(run/'data/ic_rankic.csv',index_col=0,parse_dates=True)
    values=factor.loc[:result['spec']['valid'][1]] if factor is not None else None;figures=[];tables=[];sections=[]
    if factor is not None:
        predictive=data[['ic','rank_ic']].notna().any().any()
        available={'ic_rankic':predictive,'ic_distribution':predictive,'factor_coverage':bool(values.size),
            'factor_distribution':np.isfinite(values.to_numpy()).any(),'group_returns_gross':any(r['mean_return_gross'] is not None for r in metrics['groups']),
            'ic_decay':any(r['rank_ic_mean'] is not None for r in metrics['decay']),
            'factor_autocorrelation':any(r['correlation'] is not None or r['rank_correlation'] is not None for r in metrics['stability']),
            'experiment_comparison':bool(result.get('comparison')) and any(result['splits'][s]['predictive']['rank_ic']['mean'] is not None or result['comparison']['parent_statistics'][s]['rank_ic']['mean'] is not None for s in ('train','valid'))}
        total_figures=sum(bool(x) for x in available.values())+(7 if metrics.get('professional') else 0)
        # Final notebook palette, dashed grids, frameless legends and percentage axes
        # are reused without executing its account engine.
        with plt.rc_context({'font.family':'sans-serif','font.sans-serif':[font_name,'DejaVu Sans'],'font.size':10.5,
            'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#bcc5ce','axes.linewidth':.6,
            'axes.unicode_minus':False,'svg.fonttype':'none','pdf.fonttype':42,'legend.frameon':False}):
            def save(fig,name,title,ylabel,dates=False):
                if not available[name]:plt.close(fig);return
                ax=fig.axes[0];ax.set_title(title,loc='left',fontsize=12,pad=45);ax.set_ylabel(ylabel)
                ax.grid(axis='y',color='#475f78',lw=.6,ls='--',alpha=.25);ax.set_axisbelow(True)
                if name=='group_returns_gross':ax.grid(False)  # Keep grid strokes clear of percentage annotations.
                handles,labels=ax.get_legend_handles_labels()
                if handles:ax.legend(handles,labels,ncol=2,loc='lower left',bbox_to_anchor=(0,1.02),fontsize=9.5)
                if dates:
                    loc=mdates.AutoDateLocator(minticks=3,maxticks=6);ax.xaxis.set_major_locator(loc);ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
                    ax.axvspan(pd.Timestamp(result['spec']['valid'][0]),pd.Timestamp(result['spec']['valid'][1]),color=AMBER,alpha=.055)
                    for date,label in [(result['spec']['valid'][0],'Validation'),
                        (metrics.get('professional',{}).get('test',{}).get('start','2026-01-01'),'Test')]:
                        ax.axvline(pd.Timestamp(date),color=GREY,ls='--',lw=.7)
                        ax.text(pd.Timestamp(date),1.01,label,transform=ax.get_xaxis_transform(),fontsize=8,color=GREY)
                fig.text(.13,.015,f"Train / Validation · {result['spec']['train'][0]} – {result['spec']['valid'][1]} · 探索性研究",fontsize=8,color=GREY)
                fig.subplots_adjust(left=.13,right=.98,bottom=.22,top=.74);fig.canvas.draw()
                for fmt in ('png','svg','pdf'):fig.savefig(run/'figures'/f'{name}.{fmt}',dpi=300,metadata={'Creator':'Research Agent'} if fmt=='pdf' else None)
                plt.close(fig);figures.append(f'figures/{name}.png')
                if progress:progress(len(figures),total_figures,name)
            def figure():return plt.subplots(figsize=(7.2,3.3))
            fig,ax=figure();plot=data.reindex(values.index)
            for col,color,label in [('ic',BLUE,'IC'),('rank_ic',AMBER,'RankIC')]:
                ax.plot(plot.index,plot[col],color=color,lw=.8,alpha=.4,label=label)
                roll=data.groupby('split')[col].transform(lambda x:x.rolling(5,min_periods=5).mean()).reindex(values.index)
                ax.plot(roll.index,roll,color=color,lw=1.6,label=label+' · 5日均值')
            ax.axhline(0,color=GREY,lw=.7);save(fig,'ic_rankic','预测能力随时间变化 · Train / Validation','截面相关系数',True)
            fig,ax=figure()
            for col,color,label in [('ic',BLUE,'IC'),('rank_ic',AMBER,'RankIC')]:
                v=data[col].dropna();ax.hist(v,bins=np.linspace(-1,1,21),histtype='step',lw=1.5,color=color,label=f'{label} · n={len(v)}')
            ax.set_xlabel('逐日截面相关系数');save(fig,'ic_distribution','IC / RankIC 逐日分布','信号日数')
            fig,ax=figure();n=result['spec']['n_groups'];x=np.arange(n)
            for offset,split,color,label in [(-.18,'train',BLUE,'Train'),(.18,'valid',AMBER,'Validation')]:
                means=result['splits'][split]['theoretical_groups']['mean_group_return_gross']
                group_values=[np.nan if means.get(str(i)) is None else means[str(i)] for i in range(n)]
                bars=ax.bar(x+offset,group_values,.34,label=label,color=color,alpha=.88)
                annotate_group_returns(ax,bars,group_values)
            ax.margins(y=.22)
            ax.axhline(0,color=GREY,lw=.7);ax.set_xticks(x,[f'G{i}' for i in range(n)]);ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.set_xlabel('G0 = 因子值最高组 · 毛收益、组内等权 · 不是账户净值')
            save(fig,'group_returns_gross',f"未来{result['spec']['horizon']}个交易日理论分组毛收益",'毛收益')
            coverage=values.notna().mean(axis=1);coverage.to_csv(run/'data/factor_coverage.csv')
            fig,ax=figure();ax.plot(coverage.index,coverage,color=BLUE,lw=1.5);ax.fill_between(coverage.index,0,coverage.values,color=BLUE,alpha=.08)
            ax.set_ylim(0,1.05);ax.yaxis.set_major_formatter(PercentFormatter(1));save(fig,'factor_coverage','因子覆盖率 · 保留暖机期','有限值 / 股票池',True)
            finite=values.to_numpy().ravel();finite=finite[np.isfinite(finite)]
            fig,ax=figure();ax.hist(finite,bins=35,color=BLUE,alpha=.78,rwidth=.93)
            ax.set_xlabel('因子值 · 全部有限值，未截尾');save(fig,'factor_distribution',f'因子值分布 · n={len(finite):,}','观测数')
            decay=pd.DataFrame(metrics['decay']);fig,ax=figure()
            for split,color,label in [('train',BLUE,'Train'),('valid',AMBER,'Validation')]:
                t=decay[decay['split']==split];ax.plot(t.horizon,t.rank_ic_mean,marker='o',ms=4,color=color,label=label+' RankIC')
                ax.plot(t.horizon,t.ic_mean,marker='s',ms=3,color=color,ls='--',alpha=.7,label=label+' IC')
            ax.axhline(0,color=GREY,lw=.7);ax.set_xticks(sorted(decay.horizon.unique()));ax.set_xlabel('预测期H（交易日）')
            save(fig,'ic_decay','预测期衰减 · 标签按阶段边界剔除','IC / RankIC 均值')
            stability=pd.DataFrame(metrics['stability']);fig,ax=figure()
            for split,color,label in [('train',BLUE,'Train'),('valid',AMBER,'Validation')]:
                t=stability[stability['split']==split];ax.plot(t.lag,t.correlation,marker='o',ms=4,color=color,label=label+' · 数值相关')
                ax.plot(t.lag,t.rank_correlation,marker='s',ms=3,ls='--',color=color,alpha=.65,label=label+' · 排序相关')
            ax.axhline(0,color=GREY,lw=.7);ax.set_xticks([1,5,10]);ax.set_xlabel('滞后期（交易日）· 因子自身的跨日相关，不是未来收益自相关')
            save(fig,'factor_autocorrelation','因子持续性 · 相邻两日共同股票','平均相关系数')
            if result.get('comparison'):
                c=result['comparison'];before=[c['parent_statistics'][s]['rank_ic']['mean'] for s in ('train','valid')]
                after=[result['splits'][s]['predictive']['rank_ic']['mean'] for s in ('train','valid')]
                pd.DataFrame({'split':['train','valid'],'parent_rank_ic':before,'current_rank_ic':after,
                    'parent_n':[c['parent_statistics'][s]['rank_ic']['n_dates'] for s in ('train','valid')],
                    'current_n':[result['splits'][s]['predictive']['rank_ic']['n_dates'] for s in ('train','valid')]}).to_csv(run/'data/experiment_comparison.csv',index=False)
                fig,ax=figure();xs=np.arange(2)
                ax.bar(xs-.18,[np.nan if v is None else v for v in before],.34,color=GREY,label='上一版本')
                ax.bar(xs+.18,[np.nan if v is None else v for v in after],.34,color=BLUE,label='当前版本');ax.set_xticks(xs,['Train','Validation']);ax.axhline(0,color=GREY,lw=.7)
                ax.set_xlabel('同一数据与预测期 · 暖机期变化可能改变样本数')
                save(fig,'experiment_comparison','参数对比 · 探索性','RankIC均值')
    else:
        # Operator re-render: reuse verified published base figures; never read a factor/price matrix.
        figures=['figures/'+p.name for p in (run/'figures').glob('*.png') if not p.name.startswith(('interactive_','rank_ic_monthly_','ic_monthly_'))]
        total_figures=len(figures)+7
    def table(key,title,headers,rows,units=None):
        from qrtk_skills.tools import j
        rows=j(rows)
        units=units or ['number']*len(headers);shown=[[number(v,units[i]) for i,v in enumerate(row)] for row in rows]
        tables.append(dict(id=key,title=title,headers=headers,values=rows,formatted=shown,units=units))
        md='| '+' | '.join(headers)+' |\n|'+'---|'*len(headers)+'\n'+'\n'.join('| '+' | '.join(row)+' |' for row in shown)
        html='<div class="metrics-table"><table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'
        html+=''.join('<tr>'+''.join('<td'+(' class="numeric"' if i else '')+'>'+escape(v)+'</td>' for i,v in enumerate(row))+'</tr>' for row in shown)+'</tbody></table></div>'
        return '<h3>'+escape(title)+'</h3>'+html,'### '+title+'\n\n'+md
    def chart(name,caption):
        f='figures/'+name+'.png'
        if f not in figures:return '<p class="note">'+escape(name)+'：N/A，缺少有效数值，未生成图表。</p>'
        return '<figure><img alt="'+escape(caption)+'" src="data:image/png;base64,'+base64.b64encode((run/f).read_bytes()).decode()+'"><figcaption>'+escape(caption)+'</figcaption></figure>'
    def section(key,title,body,md):sections.append((key,title,body,md))
    professional=metrics.get('professional');test=professional['test'] if professional else None
    test_rows=[]
    if test:
        from .interactive_report import test_label
        test_rows=[['Test / '+test_label(test),m,*([test['metrics'][m+'_'+k] for k in ('mean','std','ir','n_dates')] if test['status']=='COMPLETED' else [None]*4)] for m in ('ic','rank_ic')]
    core,coremd=table('core','Train / Validation / Test · 核心指标',['样本','指标','均值','标准差','IR¹','有效日'],[[r['split'],r['metric'],r['mean'],r['std'],r['icir'],r['n_dates']] for r in metrics['predictive']]+test_rows,['number']*5+['count'])
    extra,extramd=table('sample','中位数、方向与有效股票',['样本','指标','中位数','正值比例','平均股票数','有效日'],
        [[r['split'],r['metric'],professional['partitions'][r['split']][r['metric']+'_median'] if professional else None,r['positive_ratio'],avg_count(r['mean_stocks']),r['n_dates']] for r in metrics['predictive']],['number','number','number','percent','number','count'])
    ri={s:result['splits'][s]['predictive']['rank_ic'] for s in ('train','valid')}
    conclusion='有效相关样本不足，尚无法判断方向一致性。' if metrics['direction_consistent'] is None else '训练与验证的因子方向一致。' if metrics['direction_consistent'] else '训练与验证方向不一致，稳定性尚不足。'
    conclusion+='训练/验证均值 RankIC 为 '+number(ri['train']['mean'])+' / '+number(ri['valid']['mean'])+'。'
    conclusion+=('有效日期有限，当前仅支持探索性描述，不能确认预测效力。' if min(r['n_dates'] for r in ri.values())<60 else '需结合重叠标签、诊断与独立验证判断；相关性不构成因果证据。')
    window='预热'+str(definition['warmup_observations'])+'观察日' if 'expression' in definition else str(result['parameters']['lookback'])+'日'
    contract=result['research_contract'];title='因子研究 · '+result.get('factor_name',result['parameters']['factor_id'])+' / '+window
    meta=f"{result['resource_id']} · {result['spec']['train'][0]}—{result['spec']['valid'][1]} · {result['n_codes']}只 · 复权={contract['adjustment']}"
    meta+=' · 创建 '+result.get('created_at','历史研究时间未登记')[:19].replace('T',' ')+'（上海时间）'
    persisted=Path(result.get('factor_path',run/'data/factor.pkl'))
    stability_summary=' / '.join(r['split']+' Lag1 '+number(r['correlation']) for r in metrics['stability'] if r['lag']==1)
    assets='<p class="asset-line">PKL 已验证 · '+escape(stability_summary)+'<br>因子文件：'+escape(str(persisted))+'<br>成果目录：'+escape(str(run))+'</p>'
    professional=metrics.get('professional')
    if professional and min(r['n_dates'] for r in ri.values()) > 0:
        conclusion=professional['verdict']['status']+' · '+' '.join(professional['verdict']['evidence'][:2])
        if professional['test']['status']=='COMPLETED':
            tm=professional['test']['metrics']
            conclusion=professional['verdict']['status']+' · '
            kind=('2026滚动暴露评价（行情截至'+professional['test']['snapshot']['certified_end']+'，持续曝光，非盲测）'
                  if professional['test']['evaluation_type']=='ROLLING_EXPOSED_TEST' else '获批的回顾性2026 Test')
            conclusion+=('已完成'+kind+'：RankIC '+number(tm['rank_ic_mean'])+
                '，HAC 95%区间 ['+number(tm.get('rank_ic_ci_low'))+', '+number(tm.get('rank_ic_ci_high'))+
                ']；不能据此认定预测能力已获证明，正式账户回测仍BLOCKED。')
        elif professional['test']['status']=='NOT_EVALUATED':
            conclusion+=' Test（2026）未评价：'+professional['test'].get('reason','FAILED')+'。'
    stages,stagesmd=('','')
    if professional:
        from .interactive_report import stage_rows
        stages,stagesmd=table('stages','统一三阶段研究',['分区','年份','状态','实际数据范围'],stage_rows(result))
    section('summary','研究摘要','<p class="lead">'+escape(conclusion)+'</p><p class="sample-line">'+escape(meta)+'</p>'+stages+core+assets,conclusion+'\n\n'+meta+'\n\n'+stagesmd+'\n\n'+coremd+'\n\nPKL：'+str(persisted))
    from .factor_math import render as render_math
    math=render_math(definition,result['parameters']['standardization'])
    result['formula_rendering']={k:v for k,v in math.items() if k!='html'}
    (run/'code/factor_formula.tex').write_text(math['latex']+'\n',encoding='utf-8')
    variables='C/O/H/L为收盘/开盘/最高/最低价，V为成交量，t为当前观察日，i为股票。Delay为历史偏移；Mean/Std/RankTS/CorrTS包含当日的完整历史窗口（Std: ddof=1）；RankCS为横截面百分位平均秩，ZCS为当日横截面样本标准化。固定放量滞涨的成交量均值使用前L日、不含当日。'
    econ_html,econ_md=economic_section(result,table)
    from .report_explain import paper_definition_section
    paper_part=paper_definition_section(result,table)
    if paper_part:section('paper','论文定义核验',*paper_part)
    section('definition','因子定义与经济假设','<div class="formula">'+math['html']+'</div><p>'+escape(hypothesis)+'</p><p class="note">'+variables+'</p><p class="note">按T收盘信号约束计算，历史可获得时间仍未验证；方向+1预先固定。历史偏移、完整窗口暖机；零分母/缺失不填0。标签 open[T+1+H]/open[T+1]−1（观察日期）。</p>'+econ_html,'$$\n'+math['latex']+'\n$$\n\n'+hypothesis+'\n\n'+variables+'\n\n'+econ_md)
    infer,infermd=table('inference','统计推断准入',['样本','指标','状态','输入日','有效日','HAC滞后'],[[r['split'],r['metric'],r['status'],r['n'],r.get('n_valid',next(x['n_dates'] for x in metrics['predictive'] if x['split']==r['split'] and x['metric']==r['metric'])),r['lags']] for r in metrics['inference']],['number','number','number','count','count','count'])
    cirows=[[r['split'],r['metric'],r['se'],r['ci_low'],r['ci_high']] for r in metrics['inference'] if r['status']=='approximate']
    ci,cimd=table('ci','HAC均值95%区间',['样本','指标','标准误','下界','上界'],cirows) if cirows else ('','')
    dt,dtmd=table('decay','预测期衰减',['样本','H','IC均值','RankIC均值','有效日'],[[r['split'],r['horizon'],r['ic_mean'],r['rank_ic_mean'],r['n_dates']] for r in metrics['decay']],['number','count','number','number','count'])
    from .report_explain import CHART_NOTES,group_section,methodology_html
    pred_note='<div class="explain"><ul><li>'+escape(CHART_NOTES['ic'])+'</li><li>'+escape(CHART_NOTES['hac'])+'</li></ul></div>'
    section('prediction','预测能力',pred_note+extra+'<div class="chart-grid">'+chart('ic_distribution','重叠未来标签；分布不代表独立样本。')+chart('ic_decay','每个预测期单独构造成熟标签，按分段边界剔除。')+'</div>'+dt+infer+ci+'<p class="note">¹ IR为均值/样本标准差，未年化。HAC只对足够长且完整的有限序列启用；不输出显著性星号。</p>',extramd+'\n\n'+dtmd+'\n\n'+infermd+'\n\n'+cimd)
    st,stmd=table('stability','因子值与排序自相关',['样本','Lag','值相关','秩相关','有效日','平均共同股票'],[[r['split'],r['lag'],r['correlation'],r['rank_correlation'],r['n_dates'],avg_count(r['mean_pairs'])] for r in metrics['stability']],['number','count','number','number','count','number'])
    win,winmd=table('windows','时间窗口稳定性',['样本','指标','子窗口','均值','标准差','有效日'],[[r['split'],r['metric'],r['window'],r['mean'],r['std'],r['n_dates']] for r in metrics['windows']],['number']*5+['count'])
    d=metrics['distribution'];qt,qtmd=table('quality','分布与数据质量',['指标','值','口径'],[
        ['覆盖率',number(d['coverage'],'percent'),'完整可见矩形含暖机'],['缺失率',number(d['missing_rate'],'percent'),'NaN保留'],
        ['有效因子值',number(d['finite_cells'],'count'),'训练+验证有限数值'],['均值 / 标准差',number(d['mean'])+' / '+number(d['std']),'合并观测、ddof=1'],
        ['偏度 / 超额峰度',number(d['skew'])+' / '+number(d['excess_kurtosis']),'无偏估计，小样本可N/A'],
        ['异常值比例',number(d['extreme_eligible_ratio'],'percent'),'逐日稳健z>5，MAD=0不评估'],
        ['最长连续缺失',number(d['longest_missing_observations'],'count'),'观察日，含暖机'],
        ['P01 / P50 / P99',' / '.join(number(d['quantiles'][k]) for k in ('0.01','0.5','0.99')),'无尾部修剪']])
    section('diagnostics','稳定性与分布诊断','<p class="note">'+escape(CHART_NOTES['coverage'])+'</p>'+chart('factor_autocorrelation','共同可观测股票横截面相关，再按日期均值；不是未来收益自相关。')+st+win+'<div class="chart-grid">'+chart('factor_coverage','保留暖机及缺失。')+chart('factor_distribution','全部有限值，不隐藏极端值。')+'</div>'+qt,stmd+'\n\n'+winmd+'\n\n'+qtmd)
    gt,gtmd=table('groups','分组未来毛收益',['样本','组别','均值','标准差','有效日'],[[r['split'],r['group'],r['mean_return_gross'],r['std_return_gross'],r['n_dates']] for r in metrics['groups']],['number','number','percent','percent','count'])
    mt,mtmd=table('monotonicity','单调性',['样本','G0−末组毛收益','单调性²','有效日'],[[s,result['splits'][s]['theoretical_groups']['long_short_mean_gross'],result['splits'][s]['theoretical_groups']['monotonicity']['pooled'],result['splits'][s]['theoretical_groups']['monotonicity']['n_dates']] for s in ('train','valid')],['number','percent','number','count'])
    if professional and (run/'data/evaluation_daily.csv').exists():
        # Source-derived method text, dynamic-group statistics with HAC intervals, Chinese chart and deterministic reading.
        ghtml,gmd,_=group_section(run,result,table,chart)
        turnover='<p class="note">Top组排序换手代理均值 '+number(metrics['rank_turnover_proxy_mean'],'percent')+'；不是组合换手或交易成本。</p>'
        section('groups','分组表现',ghtml+'<details><summary>逐组收益标准差与原始单调性表</summary>'+gt+mt+'</details>'+turnover,gmd+'\n\n'+gtmd+'\n\n'+mtmd)
    else:
        section('groups','分组表现',chart('group_returns_gross','G0最高分；等权、未扣费，不是可交易账户收益。')+gt+mt+'<p class="note">² −Spearman(组序号,分组均值)，高分组收益更高为正。Top组排序换手代理均值 '+number(metrics['rank_turnover_proxy_mean'],'percent')+'；不是组合换手/成本。</p>',gtmd+'\n\n'+mtmd)
    if result.get('comparison'):
        c=result['comparison'];rows=[]
        for s in ('train','valid'):
            old=c['parent_statistics'][s]['rank_ic'];cur=ri[s];rows.append([s,old['mean'],cur['mean'],c['rank_ic_delta'][s],old['n_dates'],cur['n_dates']])
        ct,ctmd=table('comparison','父子实验',['样本','父RankIC','本次RankIC','差值','父有效日','本次有效日'],rows,['number']*4+['count','count'])
        pt,ptmd=table('parameters','参数变化',['参数','父实验','本次'],[[k,str(c['parent_parameters'].get(k,'N/A')),str(result['parameters'].get(k,'N/A'))] for k in ('factor_id','lookback','horizon','n_groups','standardization')])
        section('comparison','实验对比',chart('experiment_comparison','验证后调整参数仍是探索性；暖机改变样本数。')+ct+pt,ctmd+'\n\n'+ptmd)
    extended=None
    if professional:
        from .interactive_report import render_sections
        extended=render_sections(run,result,table,chart,progress=progress,completed=len(figures),total=total_figures)
        sections.extend(extended['sections']);figures.extend(extended['figures'])
        # Static coverage and its embedded image share the same three-stage aggregate trace.
        old=base64.b64encode((run/'figures/factor_coverage.png').read_bytes()).decode() if (run/'figures/factor_coverage.png').exists() else None
        if old:
            for fmt in ('png','svg','pdf'):
                (run/'figures'/('factor_coverage.'+fmt)).write_bytes((run/'figures'/('interactive_coverage_timeline.'+fmt)).read_bytes())
            new=base64.b64encode((run/'figures/factor_coverage.png').read_bytes()).decode()
            sections=[(k,t,b.replace(old,new),m) for k,t,b,m in sections]
    split_note='Train/Validation为独立发布研究分区；2026未开放为普通Agent行情资源，只由受控评价身份计算聚合统计（滚动评价持续曝光，不是盲测）。Validation已曝光，不是独立盲测。' if result.get('data_partitions') else 'test=sealed 只隐藏统计，不是全系统盲测。'
    limits=['探索性研究 / 证据不足；正式回测 BLOCKED，无账户图表。',split_note,*[x.replace('2026 unavailable','2026 unavailable to ordinary research resources; approved evaluator statistics are separate') for x in result['limitations']]]
    mhtml,mmd=methodology_html()
    section('method','方法说明',mhtml,mmd)
    from .report_explain import limits_html
    lhtml,lmd=limits_html(limits,metrics['unsupported'])
    section('limits','局限与下一步',lhtml,lmd)
    appendix=dict(goal=goal,parameters=result['parameters'],data_contract=contract,data_sha256=result['data_sha256'],spec=result['spec'],spec_fingerprint=result['spec_fingerprint'],implementation={'core_version':__version__,'tool_version':result['implementation_version'],'source_sha256':result['implementation_sha256'],'report_version':VERSION},factor_export=result['factor_export'],metric_definitions=metrics['definitions'],reproduce='python code/reproduce.py',font={'primary':font_name,'latin_fallback':'DejaVu Sans'},cjk_font_available=cjk)
    appendix['formula_rendering']=result['formula_rendering']
    if result.get('data_partitions'):appendix['data_partitions']=result['data_partitions']
    appendix['plot_source']={'entry':'backtest.ipynb last cell -> core_backtest.api.run_final_notebook -> core_backtest.plotting.plot_final_result','plot_sha256':'d2b5a374e66d426eb33363dd5441709a25915ef884893ffdcd2a9bbddfe8dd52','reused':'palette, group percentage annotations, dashed y-grid, zero line, frameless legends, percentage formatter; independent factor layout','account_engine_executed':False}
    apptext=json.dumps(appendix,ensure_ascii=False,indent=2)
    section('appendix','技术附录','<details><summary>公式、合同、PKL元数据、指纹与复现入口</summary><pre>'+escape(apptext)+'</pre></details>','```json\n'+apptext+'\n```')
    if extended:
        appendix['professional_evaluation']=professional
        appendix['interactive_report']={k:v for k,v in extended.items() if k in ('version','plotly_sha256')}
        apptext=json.dumps(appendix,ensure_ascii=False,indent=2)
        sections[-1]=('appendix','技术附录','<details><summary>完整统计合同、HAC参数、PKL指纹与复现入口</summary><pre>'+escape(apptext)+'</pre></details>','```json\n'+apptext+'\n```')
        order=['summary','paper','definition','metrics','prediction','trends','diagnostics','groups','comparison','robustness','test','verdict','limits','method','appendix']
        sections.sort(key=lambda s:order.index(s[0]))
    (run/'data/report_tables.json').write_text(json.dumps(tables,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    css='''*{box-sizing:border-box}body{margin:0;background:#f2f5f7;color:#243342;font:14px/1.65 system-ui,"Microsoft YaHei","Noto Sans CJK SC",sans-serif}.page{max-width:1120px;margin:32px auto;background:white;padding:36px 42px;border:1px solid #e0e6eb}header{border-bottom:2px solid #1d5578;padding-bottom:18px}.eyebrow{font-size:11px;letter-spacing:2px;color:#627b8d}h1{font-size:27px;line-height:1.3;margin:10px 0}h2{font-size:19px;color:#204e6b;border-bottom:1px solid #e5ebef;padding-bottom:8px;margin-top:28px}h3{font-size:13px;margin:18px 0 7px}.badge{font-size:11px;color:#846229;background:#f6f1e7;padding:4px 8px}.lead{font-size:17px;line-height:1.7;margin-top:18px}.sample-line,.note,figcaption{color:#637383;font-size:12px}.formula{padding:12px 16px;border-left:3px solid #1769aa;background:#f4f7fa;font:13px/1.6 ui-monospace,monospace;overflow-wrap:anywhere}nav{display:flex;gap:14px;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid #e5ebef}nav a{font-size:12px;color:#46667e;text-decoration:none}.metrics-table{overflow-x:auto;margin:8px 0 14px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;min-width:470px}th{text-align:right;color:#607183;font-weight:500;font-size:11px;background:#f3f6f8}th:first-child,td:first-child{text-align:left}td,th{padding:7px 10px;border-bottom:1px solid #e5ebef;white-space:nowrap}td{font-size:12px}.numeric{text-align:right}tbody tr:nth-child(even){background:#fafcfd}figure{margin:18px 0}img{display:block;width:100%;height:auto}figcaption{margin:5px 12px}.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.chart-grid figure{min-width:0}pre{background:#f4f7fa;white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;font-size:11px}p,li{overflow-wrap:anywhere}details{border:1px solid #e0e6eb;padding:12px}summary{cursor:pointer;color:#46667e}footer{font-size:11px;color:#7a8792;border-top:1px solid #e5ebef;padding-top:14px;margin-top:28px}@media(max-width:760px){.page{margin:0;padding:20px 16px;border:0}.chart-grid{grid-template-columns:1fr}h1{font-size:23px}.lead{font-size:15px}}@media print{body{background:white}.page{border:0;padding:0}nav{display:none}figure,table{break-inside:avoid}}'''
    css+=' .formula{overflow-x:auto;max-width:100%;padding:20px 16px}.math-svg{width:auto;height:46px;max-width:none}.asset-line{font-size:12px;color:#637383}'
    css+=' .banner{padding:10px 14px;margin:8px 0 14px;font-weight:600;border-radius:3px}.banner.invalid{background:#fbeaea;border-left:4px solid #b3261e;color:#7d1a14}.banner.explore{background:#fff6e5;border-left:4px solid #c27c0e;color:#6b4508}html[data-theme=dark] .banner.invalid{background:#3a1f1f;color:#f4c7c3}html[data-theme=dark] .banner.explore{background:#3a2f1a;color:#f3dcae}'
    css+=' .explain{background:#f6f9fb;border-left:3px solid #8fb3cc;padding:6px 14px;margin:10px 0 14px;font-size:12.5px}.explain ul{margin:6px 0;padding-left:18px}.explain li{margin:3px 0}.explain h3{margin:6px 0 2px}.method dl{margin:10px 0}.method dt{font-weight:600;margin-top:10px}.method dd{margin:2px 0 0 0;color:#40525f}'
    if extended:css+=extended['css']
    html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' · 因子研究报告</title><style>'+css+'</style></head><body><main class="page"><header><div class="eyebrow">QUANTITATIVE RESEARCH / FACTOR NOTE</div><h1>'+escape(title)+'</h1><span class="badge">探索性研究 / 证据不足</span></header><nav>'
    html+=''.join('<a href="#'+k+'">'+escape(t)+'</a>' for k,t,_,_ in sections)+('<button id="theme-toggle">浅色 / 深色</button>' if extended else '')+'</nav>'
    html+=''.join('<section id="'+k+'">'+('<h2>'+escape(t)+'</h2>' if k!='summary' else '')+body+'</section>' for k,t,body,_ in sections)
    html+='<footer>可信程序数值 · PKL验证成功 · 非独立盲测 · /hy-tmp临时存储请备份 · SSH断开不保证继续</footer></main>'+ (extended['javascript'] if extended else '')+'</body></html>'
    (run/'reports/report.html').write_text(html,encoding='utf-8')
    md='# '+title+'\n\n状态：incomplete / exploratory；PKL已验证，正式回测未准入。\n\n'+'\n\n'.join('## '+t+'\n\n'+m for _,t,_,m in sections)
    md+='\n\n## 图表\n\n'+'\n\n'.join('!['+Path(f).stem+'](../'+f+')' for f in figures)
    (run/'reports/report.md').write_text(md,encoding='utf-8')
    if professional and professional['report_revision']==1:
        version=dict(revision=1,study_id=result['study_id'],html=str(run/'reports/report.html'),markdown=str(run/'reports/report.md'),
            html_sha256=__import__('hashlib').sha256(html.encode()).hexdigest())
        with (run/'reports/report_versions.json').open('x',encoding='utf-8') as f:json.dump([version],f,ensure_ascii=False)
    return dict(report_path=str(run/'reports/report.md'),html_path=str(run/'reports/report.html'),figure_paths=[str(run/f) for f in figures],report_status='incomplete')
