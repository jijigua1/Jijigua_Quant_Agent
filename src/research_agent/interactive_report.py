"""Offline Plotly.js presentation of saved deterministic evaluation CSVs."""
import base64
import hashlib
import json
from html import escape
from pathlib import Path
import numpy as np
import pandas as pd
from qrtk_skills.tools import j

PLOTLY_SHA='0a17719a72751704861215da0e5c5cdb3f9a8d50eff5cb84cb6f8b80786682b0'
VERSION='interactive-report/1.1.0'
BLUE='#475f78';AMBER='#c84b31'
COLORS=[[0,'#416787'],[.5,'#f4f4f0'],[1,'#b35340']]


def timeline(series):
    """Keep actual observation dates and explicit gaps; no interpolation or phase reset."""
    dates=list(series.index.strftime('%Y-%m-%d'))
    partitions=['Train' if d<'2024-01-01' else 'Validation' if d<'2026-01-01' else 'Test' for d in dates]
    return dict(x=dates,y=j(series.tolist()),customdata=partitions,connectgaps=False,
                hovertemplate='%{x}<br>%{y:.6f}<br>%{customdata}<extra>%{fullData.name}</extra>')


def partition_layout(result):
    dates=[result['spec']['valid'][0],result['metrics']['professional']['test'].get('start','2026-01-01')]
    return dict(shapes=[dict(type='line',xref='x',x0=d,x1=d,yref='paper',y0=0,y1=1,
                      line=dict(color='#8b99a8',width=1.2,dash='dash')) for d in dates],
                annotations=[dict(x=d,xref='x',y=1,yref='paper',text=label,showarrow=False,
                      xanchor='left',yanchor='bottom',font=dict(size=11,color='#66788a')) for d,label in zip(dates,('Validation','Test'))])


def test_label(test):
    """One wording everywhere: retrospective one-time, rolling exposed, or not evaluated with its reason."""
    if test['status']=='COMPLETED':
        return 'ROLLING_EXPOSED_TEST / 持续曝光' if test['evaluation_type']=='ROLLING_EXPOSED_TEST' else 'RETROSPECTIVE_ONE_TIME / '+str(test['evaluation_type'])
    if test['status']=='NOT_EVALUATED':return 'NOT_EVALUATED / '+test.get('reason','FAILED')
    return test['status']+' / '+test['access']


def stage_rows(result):
    p=result['metrics']['professional'];test=p['test']
    span=test.get('start','—')+' — '+test.get('end','—')
    if test.get('maturity'):
        span+='（成熟标签至 '+str(test['maturity'].get('last_matured_signal_date'))+'）'
    return [['Train','2020—2023','COMPLETED',result['spec']['train'][0]+' — '+result['spec']['train'][1]],
            ['Validation','2024—2025','COMPLETED / EXPOSED',result['spec']['valid'][0]+' — '+result['spec']['valid'][1]],
            ['Test','2026→最新合格日',test_label(test),span if test['status']=='COMPLETED' else test.get('detail','未执行')]]


def noncompounding(groups,horizon):
    """qrtk.cumulative_returns semantics on the full timeline: rows 0,H,2H,... compounded; a missing period is a gap
    (no value plotted) and the path continues from the last level afterwards. Theoretical gross paths, not NAV."""
    sampled=groups.iloc[::horizon]
    out=pd.DataFrame(np.nan,index=groups.index,columns=groups.columns)
    for col in groups.columns:
        level=1.0
        for date,value in sampled[col].items():
            if pd.notna(value):
                level*=1+value;out.loc[date,col]=level-1
    return out


def heatmap_data(monthly, metric):
    years=sorted(int(p[:4]) for p in monthly.period.unique())
    years=sorted(set(years));z=[];text=[];custom=[]
    for year in years:
        values=[];labels=[];info=[]
        for month in range(1,13):
            row=monthly[monthly.period==f'{year:04d}-{month:02d}']
            value=None if row.empty else row.iloc[0][metric+'_mean']
            value=None if value is None or pd.isna(value) else float(value)
            values.append(value);labels.append('N/A' if value is None else f'{value:+.3f}')
            info.append([None,None,'N/A'] if row.empty else [None if str(row.iloc[0].split).startswith(('test / SEALED','test / NOT_')) else int(row.iloc[0][metric+'_n_dates']),
                         None if pd.isna(row.iloc[0].mean_coverage) else float(row.iloc[0].mean_coverage),str(row.iloc[0].split)])
        z.append(values);text.append(labels);custom.append(info)
    finite=[abs(v) for row in z for v in row if v is not None];limit=max(finite,default=.01) or .01
    return dict(years=years,z=z,text=text,custom=custom,limit=limit)


def render_sections(run, result, table, chart,*,progress=None,completed=0,total=8):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    p=result['metrics']['professional'];monthly=pd.read_csv(run/'data/evaluation_monthly.csv',float_precision='round_trip')
    annual=pd.read_csv(run/'data/evaluation_annual.csv',float_precision='round_trip');daily=pd.read_csv(run/'data/evaluation_daily.csv',index_col=0,parse_dates=True,float_precision='round_trip')
    test=p['test'];completed_test=test['status']=='COMPLETED'
    if completed_test and 'test' not in set(daily['split']):
        monthly=pd.concat([monthly[monthly['split']!='test'],pd.DataFrame(test['monthly'])],ignore_index=True)
        annual=pd.concat([annual[annual['split']!='test'],pd.DataFrame(test['annual'])],ignore_index=True)
        from .report_versions import test_daily
        td=pd.DataFrame(test_daily(run,test));td.index=pd.to_datetime(td.pop('date'));td['split']='test'
        test_groups=td[[c for c in td.columns if c in test.get('group_columns',[])]].copy()
        td=td.drop(columns=[c for c in td.columns if c not in ('ic','rank_ic','coverage','split')])
        for m in ('ic','rank_ic'):
            for w in (20,60):td[m+'_rolling'+str(w)]=td[m].rolling(w,min_periods=w).mean()
            td[m+'_cumulative']=td[m].cumsum()
        daily=pd.concat([daily[daily['split']!='test'],td]).sort_index()
        if len(test_groups.columns):
            test_groups.columns=[c[1:] for c in test_groups.columns]
            base=pd.read_csv(run/'data/group_returns_gross.csv',index_col=0,parse_dates=True,float_precision='round_trip')
            pd.concat([base[base.index<test_groups.index.min()],test_groups[base.columns]]).to_csv(run/'data/group_returns_gross.csv')
        annual.to_csv(run/'data/evaluation_annual.csv',index=False)
        monthly.to_csv(run/'data/evaluation_monthly.csv',index=False)
        daily.to_csv(run/'data/evaluation_daily.csv')
    # Stage 3 metric system: every metric from the saved daily rows (Test from the receipt); a sealed 2026 stays a visible N/A row.
    from . import metric_system
    ms=metric_system.compute(run,result)
    n_groups=int(result['spec']['n_groups'])
    heat_years=sorted({int(r['period'][:4]) for r in ms['monthly']}|{2026})
    bundle=Path(__file__).parent/'resources/visuals/plotly-2.32.0.min.js'
    raw=bundle.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PLOTLY_SHA:raise ValueError('PLOTLY_ASSET_HASH_MISMATCH')
    figures=[];charts=[];sections=[]
    heat_payload={};heat_specs=[]
    from .server_plot import configure_chinese_font
    try:cjk=configure_chinese_font().get_name()
    except RuntimeError:cjk=None
    # Chart titles and legends are Chinese: the static PNG/SVG/PDF exports need the same CJK font as the report figures.
    font_rc={'font.family':'sans-serif','font.sans-serif':[cjk,'DejaVu Sans'],'axes.unicode_minus':False,'svg.fonttype':'none','pdf.fonttype':42} if cjk else {}
    labels=[str(y)+(' · Train' if y<=2023 else ' · Validation' if y<=2025 else ' · Test'+(' / '+test.get('reason',test['status']) if not completed_test else ' / rolling' if test['evaluation_type']=='ROLLING_EXPOSED_TEST' else '')) for y in heat_years]
    atlas=[]
    for key,title,kind,fmt in metric_system.heat_metrics(n_groups):
        h=metric_system.heat_grid(ms['monthly'],key,fmt,test,heat_years);lo,hi,mid=metric_system.scale(h,kind)
        name={'rank_ic_mean':'rank_ic_monthly_heatmap','ic_mean':'ic_monthly_heatmap'}.get(key,'heat_'+key+'_monthly')
        if key in ('rank_ic_mean','ic_mean'):heat_payload[key[:-5]]=h|{'limit':hi}
        strong=lambda v,lo=lo,hi=hi,mid=mid:v is not None and (abs(v-mid)>.6*(hi-mid) if mid is not None else v>.6*hi)
        zfmt='%{z:.2%}' if fmt.endswith('%') else '%{z:.0f}' if fmt=='.0f' else '%{z:.6f}'
        trace=dict(type='heatmap',x=list(range(1,13)),y=h['years'],z=h['z'],text=h['text'],customdata=h['custom'],
            hoverongaps=True,colorscale=COLORS if kind!='seq' else [[0,COLORS[1][1]],[1,COLORS[0][1]]],zmin=lo,zmax=hi,
            colorbar=dict(title='值'),hovertemplate='%{y}年%{x}月<br>'+title+': '+zfmt+'<br>有效信号日: %{customdata[0]}<br>覆盖率: %{customdata[1]:.2%}<br>分区: %{customdata[2]}<extra></extra>')
        if mid is not None:trace['zmid']=mid
        layout=dict(title=title+'（按信号日归属月份；每格只用该月有效信号日）',height=max(320,len(h['years'])*40+130),margin=dict(l=174,r=44,t=60,b=56),
            xaxis=dict(title='月份',dtick=1),yaxis=dict(autorange='reversed',dtick=1,tickvals=h['years'],ticktext=labels),
            annotations=[dict(x=x+1,y=h['years'][y],text=h['text'][y][x],showarrow=False,
                font=dict(size=12,color='#89939c' if v is None else 'white' if strong(v) else '#243342'))
                         for y,row in enumerate(h['z']) for x,v in enumerate(row)],
            shapes=[dict(type='line',xref='paper',x0=0,x1=1,yref='y',y0=b,y1=b,line=dict(color=BLUE,width=2)) for b in (2023.5,2025.5)])
        charts.append(dict(id=name,traces=[trace],layout=layout));heat_specs.append((name,title,False))      # interactive only; the atlas is the static copy
        atlas.append((h,title,kind,lo,hi,strong))
    # One static atlas of every heatmap (print view and PDF/SVG download): a study keeps within its 100-file budget.
    with plt.rc_context(font_rc):
        rows_n=(len(atlas)+1)//2;ny=len(heat_years)
        fig,axes=plt.subplots(rows_n,2,figsize=(17,rows_n*(ny*.34+1.5)))
        for ax,(h,title,kind,lo,hi,strong) in zip(axes.ravel(),atlas):
            z=np.array([[np.nan if v is None else v for v in row] for row in h['z']],dtype=float)
            stops=[COLORS[0][1],COLORS[1][1],COLORS[2][1]] if kind!='seq' else [COLORS[1][1],COLORS[0][1]]
            cmap=LinearSegmentedColormap.from_list('research_'+kind,stops);cmap.set_bad('#e6e9ec')
            im=ax.imshow(z,cmap=cmap,vmin=lo,vmax=hi,aspect='auto')
            for y,row in enumerate(h['text']):
                for x,text in enumerate(row):
                    ax.text(x,y,text,ha='center',va='center',color='white' if strong(h['z'][y][x]) else '#243342',fontsize=6.5)
            ax.set_xticks(range(12),[str(m) for m in range(1,13)],fontsize=7)
            ax.set_yticks(range(ny),[str(y)+(' Train' if y<=2023 else ' Valid' if y<=2025 else ' Test') for y in heat_years],fontsize=7)
            boundary=sum(y<=2023 for y in heat_years)-.5
            if -.5<boundary<ny-.5:ax.axhline(boundary,color='#243342',lw=1)
            ax.set_title(title,loc='left',fontsize=9)
            for sp in ax.spines.values():sp.set_visible(False)
            fig.colorbar(im,ax=ax,fraction=.03,pad=.01).ax.tick_params(labelsize=6)
        for ax in axes.ravel()[len(atlas):]:ax.set_visible(False)
        fig.suptitle('月度热力图总览（按信号日归属月份；灰格N/A；'+('2026为Test' if completed_test else '2026 Test未评价')+'）',x=.01,ha='left',fontsize=12)
        fig.tight_layout(rect=(0,0,1,.985))
        for f in ('png','svg','pdf'):fig.savefig(run/'figures'/f'interactive_heat_atlas.{f}',dpi=170,bbox_inches='tight')
        plt.close(fig);figures.append('figures/interactive_heat_atlas.png')
        if progress:progress(completed+len(figures),total,'interactive_heat_atlas')
    (run/'data/evaluation_heatmaps.json').write_text(json.dumps(j(heat_payload),ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    def interactive(name,title,static=None):
        with plt.rc_context(font_rc):
            return _interactive(name,title,static)
    def _interactive(name,title,static=None):
        if static is None:
            import matplotlib.dates as mdates
            spec=next(c for c in charts if c['id']==name);static='interactive_'+name
            fig,ax=plt.subplots(figsize=(10,3.7))
            for trace in spec['traces']:
                x=trace['x'];x=pd.to_datetime(x) if x and isinstance(x[0],str) else x
                style=trace.get('line',{});options={'lw':max(.7,style.get('width',1.4)),'label':trace['name'],'alpha':trace.get('opacity',1)}
                if style.get('color'):options['color']=style['color']
                if style.get('dash')=='dash':options['ls']='--'
                ax.plot(x,np.array(trace['y'],dtype=float),**options)
            if spec['traces'][0]['x'] and isinstance(spec['traces'][0]['x'][0],str):
                locator=mdates.AutoDateLocator(minticks=4,maxticks=8);ax.xaxis.set_major_locator(locator);ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
                for divider in spec['layout'].get('shapes',[]):
                    if divider['type']=='line':ax.axvline(pd.Timestamp(divider['x0']),color='#8b99a8',lw=.9,ls='--')
                for note in spec['layout'].get('annotations',[]):
                    ax.text(pd.Timestamp(note['x']),1.01,note['text'],transform=ax.get_xaxis_transform(),fontsize=9,color='#66788a')
                if spec['layout'].get('xaxis',{}).get('range'):
                    ax.set_xlim(pd.to_datetime(spec['layout']['xaxis']['range']))
            ax.set_title(spec['layout']['title'],loc='left',fontsize=11,pad=12);ax.grid(alpha=.18);ax.axhline(0,color='#89939c',lw=.6)
            ax.legend(frameon=False,ncol=min(5,len(spec['traces'])),fontsize=8,loc='upper left')
            if spec['layout'].get('yaxis',{}).get('tickformat')=='.0%':
                from matplotlib.ticker import PercentFormatter
                ax.yaxis.set_major_formatter(PercentFormatter(1))
            for sp in ax.spines.values():sp.set_visible(False)
            fig.tight_layout()
            for fmt in ('png','svg','pdf'):fig.savefig(run/'figures'/f'{static}.{fmt}',dpi=240,bbox_inches='tight')
            plt.close(fig);figures.append('figures/'+static+'.png')
            if progress:progress(completed+len(figures),total,static)
        controls='<div class="exports"><button data-chart="'+name+'" data-format="png">PNG 高清</button><button data-chart="'+name+'" data-format="svg">SVG</button>'
        if static:
            pdf=base64.b64encode((run/'figures'/f'{static}.pdf').read_bytes()).decode()
            controls+='<a download="'+static+'.pdf" href="data:application/pdf;base64,'+pdf+'">PDF</a>'
        controls+='</div>'
        image=('<img alt="'+escape(title)+'" src="data:image/png;base64,'+base64.b64encode((run/'figures'/f'{static}.png').read_bytes()).decode()+'">') if static else ''
        height=next(c['layout']['height'] for c in charts if c['id']==name)
        return '<div class="interactive-wrap"><h3>'+escape(title)+'</h3><div id="'+name+'" class="interactive-chart" style="height:'+str(height)+'px"></div>'+controls+('<div class="print-chart">'+image+'</div>' if static else '')+'</div>'
    a,amd=table('annual_predictive','逐年预测能力',['年份/分区','IC均值','RankIC均值','RankIC IR','正RankIC','有效日'],
        [[f'{int(r.period)} / {r.split}',r.ic_mean,r.rank_ic_mean,r.rank_ic_ir,r.rank_ic_positive_ratio,r.rank_ic_n_dates] for r in annual.itertuples()]+
        ([] if completed_test else [['2026 / Test · '+test_label(test),None,None,None,None,None]]),['number']*4+['percent','count'])
    ai,aimd=table('annual_ic_detail','逐年IC完整汇总',['年份','IC median','IC std','IC IR','正IC比例','有效日'],
        [[int(r.period),r.ic_median,r.ic_std,r.ic_ir,r.ic_positive_ratio,r.ic_n_dates] for r in annual.itertuples()],['count','number','number','number','percent','count'])
    ar,armd=table('annual_rank_detail','逐年RankIC完整汇总',['年份','RankIC median','RankIC std','RankIC IR','正RankIC比例','有效日'],
        [[int(r.period),r.rank_ic_median,r.rank_ic_std,r.rank_ic_ir,r.rank_ic_positive_ratio,r.rank_ic_n_dates] for r in annual.itertuples()],['count','number','number','number','percent','count'])
    b,bmd=table('annual_uncertainty','年度不确定性与覆盖',['年份','RankIC std','HAC 95%下界','HAC 95%上界','覆盖率','Lag1'],
        [[int(r.period),r.rank_ic_std,r.rank_ic_ci_low,r.rank_ic_ci_high,r.mean_coverage,r.factor_lag1] for r in annual.itertuples()],['count']+['number']*3+['percent','number'])
    c,cmd=table('annual_groups','年度理论分组诊断',['年份','G0−末组均值','毛收益std','单调性','IC正比','有效日'],
        [[int(r.period),r.long_short_mean_gross,r.long_short_std_gross,r.group_monotonicity,r.ic_positive_ratio,r.ic_n_dates] for r in annual.itertuples()],['count','percent','percent','number','percent','count'])
    stage_html,stage_md=table('evaluation_stages','三阶段状态',['分区','规定年份','评价状态','实际数据范围'],stage_rows(result))
    warm=[str(int(r.period)) for r in annual.itertuples() if (pd.isna(r.rank_ic_n_dates) or r.rank_ic_n_dates==0) and int(r.period)<=2025]
    wnote=('<p class="note">'+escape('、'.join(warm)+'年有效评价日为0：该年处于因子暖机期（窗口所需历史不足）或无成熟标签，显示N/A，不补0。')+'</p>') if warm else ''
    m,mmd=table('monthly','逐月完整评价',['月份/分区','IC均值','RankIC均值','有效日','正RankIC','覆盖率'],
        [[r.period+' / '+r.split,r.ic_mean,r.rank_ic_mean,r.rank_ic_n_dates,r.rank_ic_positive_ratio,r.mean_coverage] for r in monthly.itertuples()],['number']*3+['count','percent','percent'])
    # Order required by the stage-3 acceptance: overall -> annual -> every monthly heatmap at once (no switcher) -> G0..G4 detail.
    o_html,a_html,g_html,ms_md=metric_system.tables(ms,table,test,test_label(test))
    heat_html='<h3>三、月度热力图（'+str(len(heat_specs))+'项指标同时展示）</h3><p class="note">月份按信号日归属；灰格为N/A（无有效信号日或Test未评价），不补0。</p>'
    heat_html+=('<div class="explain"><h3>为什么月度没有HAC显著性</h3><ul><li>每个月通常只有约20个有效信号日，'
                '低于本报告HAC统计的既有最低样本（≥60个有效日且≥10×(带宽+1)），而且相邻信号日的H日持有期互相重叠。</li>'
                '<li>因此月度热力图只展示描述统计（均值、IR、胜率、分组收益、单调性、覆盖率、股票数），月度HAC t、p和区间一律为N/A；'
                '不为了凑出显著性而放宽门槛，也不能根据单月颜色或符号判断显著。</li>'
                '<li>需要统计推断时请看“一、总体评价”和“二、逐年评价”的HAC表。</li></ul></div>')
    pdf=base64.b64encode((run/'figures/interactive_heat_atlas.pdf').read_bytes()).decode()
    png=base64.b64encode((run/'figures/interactive_heat_atlas.png').read_bytes()).decode()
    heat_html+=('<div class="exports"><a download="interactive_heat_atlas.pdf" href="data:application/pdf;base64,'+pdf+'">全部热力图 PDF</a></div>'
                '<div class="print-chart"><img alt="月度热力图总览" src="data:image/png;base64,'+png+'"></div>')
    heat_html+=''.join(interactive(name,title,static) for name,title,static in heat_specs)
    legacy='<details><summary>补充：原逐年/逐月表（中位数、HAC区间、旧版分组诊断，CSV同源）</summary>'+a+wnote+ai+ar+b+c+m+'</details>'
    sections.append(('metrics','Factor Metrics · 完整因子评价体系',stage_html+o_html+a_html+wnote+heat_html+g_html+legacy,
        stage_md+'\n\n'+ms_md+'\n\n'+amd+'\n\n'+aimd+'\n\n'+armd+'\n\n'+bmd+'\n\n'+cmd+'\n\n'+mmd))
    dates=list(daily.index.strftime('%Y-%m-%d'));dividers=partition_layout(result)
    for metric in ('ic','rank_ic'):
        traces=[]
        for col,label,width,alpha in [(metric,'逐日值',.6,.4),(metric+'_rolling20','20日滚动均值',1.7,1),(metric+'_rolling60','60日滚动均值',2.1,1)]:
            traces.append(dict(type='scatter',mode='lines',**timeline(daily[col]),name=label,
                line=dict(width=width,color=BLUE if '60' not in col else AMBER),opacity=alpha))
        charts.append(dict(id=metric+'_timeline',traces=traces,layout=dict(title=('IC' if metric=='ic' else 'RankIC')+' · 逐日值与20/60日滚动均值（Train | Validation | Test 连续时间轴）',height=380,
            xaxis=dict(type='date',rangeslider=dict(visible=True,thickness=.09),rangeselector=dict(buttons=[dict(count=1,label='1y',step='year',stepmode='backward'),dict(step='all',label='All')])),
            yaxis=dict(title='截面相关系数',zeroline=True),**dividers)))
    cumulative=[dict(type='scatter',mode='lines',**timeline(daily[m].cumsum()),name=label,line=dict(color=color)) for m,label,color in [('ic','累计IC',BLUE),('rank_ic','累计RankIC',AMBER)]]
    charts.append(dict(id='cumulative_correlation',traces=cumulative,layout=dict(title='累计IC / RankIC（逐日相关系数相加，观察方向是否持续；不是收益或净值）',height=340,
        yaxis=dict(title='相关系数累计和',zeroline=True),**dividers)))
    groups=pd.read_csv(run/'data/group_returns_gross.csv',index_col=0,parse_dates=True,float_precision='round_trip').reindex(daily.index)
    horizon=int(result['parameters']['horizon'])
    group_curves=noncompounding(groups,horizon)
    group_curves.to_csv(run/'data/theoretical_group_paths.csv')
    sampled=group_curves.iloc[::horizon]
    charts.append(dict(id='theoretical_groups',traces=[dict(type='scatter',mode='lines+markers',marker=dict(size=3),**timeline(sampled[col]),
        name='G'+str(col)+('（最高分组）' if str(col)=='0' else '（最低分组）' if str(col)==str(len(groups.columns)-1) else '')) for col in groups.columns],
        layout=dict(title=f'理论分组累计毛收益：每{horizon}个交易日取一个信号日、互不重叠、复利连乘（未扣成本，不是账户净值）',
                    height=380,yaxis=dict(tickformat='.0%',title='累计毛收益'),**dividers)))
    charts.append(dict(id='coverage_timeline',traces=[dict(type='scatter',mode='lines',**timeline(daily.coverage),name='因子覆盖率',line=dict(color=BLUE))],
        layout=dict(title='因子覆盖率：有有限因子值的股票 / 全部发布代码（开头低值为暖机期）',height=300,yaxis=dict(range=[0,1.05],tickformat='.0%'),**dividers)))
    decay=result['metrics']['decay'];decay_traces=[]
    for split,color in [('train',BLUE),('valid',AMBER)]:
        rows=[r for r in decay if r['split']==split]
        for metric in ('ic_mean','rank_ic_mean'):
            decay_traces.append(dict(type='scatter',mode='lines+markers',x=[r['horizon'] for r in rows],y=[r[metric] for r in rows],
                name={'train':'Train','valid':'Validation'}[split]+(' IC' if metric=='ic_mean' else ' RankIC'),line=dict(color=color,dash='dash' if metric=='ic_mean' else 'solid')))
    charts.append(dict(id='interactive_decay',traces=decay_traces,layout=dict(title='预测期衰减：各预测期H单独构造成熟标签（Test只评价冻结的H）',height=330,xaxis=dict(title='预测期H（交易日）'))))
    for c in charts:
        if c['id'] in ('ic_timeline','rank_ic_timeline','cumulative_correlation','coverage_timeline','theoretical_groups'):
            c['layout'].setdefault('xaxis',{}).update(type='date',range=[dates[0],dates[-1]])
    from .report_explain import CHART_NOTES
    trend_notes=[CHART_NOTES[k] for k in ('boundary','ic','immature','cumulative','coverage','decay')]
    explain='<div class="explain"><h3>如何阅读本章图表</h3><ul>'+''.join('<li>'+escape(x)+'</li>' for x in trend_notes)+'</ul></div>'
    sections.append(('trends','Predictive Stability · 时间稳定性',stage_html+explain+interactive('ic_timeline','IC · 日频与20/60日趋势')+
        interactive('rank_ic_timeline','RankIC · 日频与20/60日趋势')+interactive('cumulative_correlation','累计相关（全区间连续展示）')+
        interactive('interactive_decay','多预测期信号衰减')+interactive('coverage_timeline','因子覆盖率')+interactive('theoretical_groups','理论分组非重叠复利毛收益（每H个观察日取一次信号）'),
        '日期轴统一展示全部可见分区，竖线仅划分阶段。累计相关跨分区延续，不是账户净值；缺失或未成熟标签不补值。滚动统计仍按独立分区完整窗口计算。'
        '理论分组曲线采用qrtk已审查定义：每H个观察日取一个信号日（相位0），该日各组等权H日毛收益复利连乘；缺失期断开，下一段从缺口前水平续接；未扣费、非账户NAV。'
        '逐日把重叠H日收益算术相加约放大H倍，本报告不再这样画；原逐日数值仍保存在group_returns_gross.csv。缺少Test逐日分组数据时曲线止于Validation。'))
    rows=p['partitions'].values()
    inf,infmd=table('robust_inference','分区HAC统计推断',['样本/指标','t统计量','p（渐近）','95%下界','95%上界','状态'],
        [[r['split']+' / '+metric,r[metric+'_t_stat'],r[metric+'_p_value'],r[metric+'_ci_low'],r[metric+'_ci_high'],r[metric+'_status']] for r in rows for metric in ('ic','rank_ic')],['number','number','pvalue','number','number','number'])
    sensitivity=pd.read_csv(run/'data/evaluation_sensitivity.csv')
    st,stmd=table('outlier_sensitivity','极端值敏感性（预设诊断）',['样本/指标','原均值','移除极端值后','变化','有效日'],
        [[r.split+' / '+r.metric,r.original_mean,r.no_extreme_mean,r.delta,r.n_dates] for r in sensitivity.itertuples()],['number']*4+['count'])
    sections.append(('robustness','Robustness & Risks · 稳健性',inf+st+'<p class="note">HAC处理重叠标签的序列相关；并非有限样本精确t检验。带宽、缺失网格、最小样本准入和未校正多次试验均见附录。移除异常值只用于敏感性诊断，不自动选择因子。</p>',infmd+'\n\n'+stmd))
    v=p['verdict'];verdict_evidence=[s.replace('HAC区间均不跨0。','Train/Validation HAC区间不跨0；Test区间单独列示。') for s in v['evidence']]
    verdict_html=stage_html+'<p class="lead">'+escape(v['status'])+'</p><ul>'+''.join('<li>'+escape(s)+'</li>' for s in verdict_evidence)+'</ul>'
    test=p['test'];test_note='Test：NOT_RUN / SEALED。未获得真实发布及首次结果解封批准；现有报告不包含2026评价数值。'
    if test['status']=='NOT_EVALUATED':
        test_note='Test：NOT_EVALUATED（'+test.get('reason','FAILED')+'）。'+test.get('detail','')+' 报告不包含任何2026数值，热力图2026行为N/A。'
    if test['status']=='COMPLETED':
        t=test['metrics'];body,md=table('test_comparison','统一分区评价',['分区','IC均值','RankIC均值','RankIC IR','有效日','覆盖率'],
            [[r['split'],r['ic_mean'],r['rank_ic_mean'],r['rank_ic_ir'],r['rank_ic_n_dates'],r['mean_coverage']] for r in [*p['partitions'].values(),t]],['number']*4+['count','percent'])
        for label in ('annual','monthly'):
            tb,tm=table('test_'+label,'Test '+{'annual':'逐年','monthly':'逐月（月份按信号日归属；未成熟信号日不计入）'}[label],['期间','IC均值','RankIC均值','有效日','覆盖率'],
                [[str(r['period']),r['ic_mean'],r['rank_ic_mean'],r['rank_ic_n_dates'],r['mean_coverage']] for r in test[label]],['number']*3+['count','percent'])
            body+=tb;md+='\n\n'+tm
        test_note='Test评估类型：'+str(test['evaluation_type'])+'；曝光记录：'+json.dumps(test['exposure'],ensure_ascii=False)+'。不自动根据结果调参。'
        if test['evaluation_type']=='ROLLING_EXPOSED_TEST':
            mt=test['maturity'];snap=test['snapshot'];imm=mt['immature_signal_dates']
            test_note=('Test为ROLLING_EXPOSED_TEST：2026数据每次更新都会重新曝光，不是独立盲测；由受控评价身份在私有快照 '+snap['version']+
                '（行情截至'+snap['certified_end']+'）上计算，Agent只收到聚合统计。'+
                f"共{mt['observed_dates']}个2026观察日、{mt['matured_signal_dates']}个成熟信号日；最后成熟信号日{mt['last_matured_signal_date']}。"
                +(f"最近{len(imm)}个信号日（{imm[0]} 至 {imm[-1]}）的H={result['parameters']['horizon']}未来开盘标签尚未出现，IC/RankIC为N/A，不补0、不预测。" if imm else '')
                +'不根据Test结果调参或选择因子；定义变化作为新研究登记。')
        for row in result.get('test_monthly_label_status',[]):
            if row['reason']=='ALL_FORWARD_LABELS_UNMATURED':
                test_note+=f" {row['period']}有{row['observed_dates']}个行情观察日、0个成熟标签评价日；H={result['parameters']['horizon']}未来标签未成熟，IC/RankIC为N/A，不是缺失行情。"
        title='Rolling Test · 2026滚动暴露评价' if test['evaluation_type']=='ROLLING_EXPOSED_TEST' else 'Controlled Test · 一次性回顾评价'
        sections.append(('test',title,body+'<p class="note">'+escape(test_note)+'</p>',md+'\n\n'+test_note))
    else:
        sections.append(('test','Test · 2026评价（'+('未评价' if test['status']=='NOT_EVALUATED' else '未运行')+'，无2026数值）',stage_html+'<p class="note">'+escape(test_note)+'</p>',stage_md+'\n\n'+test_note))
    verdict_html+='<p class="note">'+escape(test_note)+'</p>'
    sections.append(('verdict','Research Verdict · 研究判断',verdict_html,v['status']+'\n\n'+'\n'.join('- '+s for s in verdict_evidence)+'\n\n'+test_note))
    payload=json.dumps(j(charts),ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    (run/'data/evaluation_chart_payload.json').write_text(payload,encoding='utf-8')
    js='''<script>'''+raw.decode()+'''</script><script>
const CHARTS='''+payload+''';
const dark=()=>document.documentElement.dataset.theme==='dark';
function palette(){return dark()?{paper_bgcolor:'#192530',plot_bgcolor:'#192530',font:{color:'#dce5ec'},gridcolor:'#3a4958'}:{paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{color:'#243342'},gridcolor:'#e4e9ee'}}
CHARTS.forEach(c=>Plotly.newPlot(c.id,c.traces,Object.assign({margin:{l:66,r:40,t:84,b:60},hovermode:'closest',...palette()},c.layout,{title:{text:c.layout.title,x:.02,y:.98,xanchor:'left',yanchor:'top',font:{size:15}},legend:{orientation:'h',y:1.15,yanchor:'bottom'}}),{responsive:true,displaylogo:false,toImageButtonOptions:{format:'png',scale:3}}));
document.querySelectorAll('[data-chart]').forEach(b=>b.addEventListener('click',()=>Plotly.downloadImage(b.dataset.chart,{format:b.dataset.format,width:1500,height:650,scale:b.dataset.format==='png'?2:1,filename:b.dataset.chart})));
document.getElementById('theme-toggle').addEventListener('click',()=>{document.documentElement.dataset.theme=dark()?'light':'dark';CHARTS.forEach(c=>Plotly.relayout(c.id,palette()));});
</script>'''
    css='''.interactive-wrap{min-width:0;margin:18px 0}.interactive-chart{width:100%;min-height:320px}.exports{display:flex;gap:8px;align-items:center}.exports button,.exports a,#theme-toggle{font:12px system-ui;color:#475f78;background:#f3f6f8;border:1px solid #ccd6de;padding:5px 10px;border-radius:3px;cursor:pointer;text-decoration:none}.print-chart{display:none}html[data-theme=dark] body{background:#101923;color:#dce5ec}html[data-theme=dark] .page{background:#192530;border-color:#3a4958}html[data-theme=dark] h2,html[data-theme=dark] h3{color:#c0d6e7}html[data-theme=dark] th,html[data-theme=dark] pre,html[data-theme=dark] .formula{background:#263541;color:#dce5ec}html[data-theme=dark] td,html[data-theme=dark] th{border-color:#3a4958}html[data-theme=dark] tbody tr:nth-child(even){background:#20303d}@media(max-width:640px){.interactive-wrap{overflow-x:auto}.interactive-chart{min-width:720px}}@media print{.interactive-chart,.exports,#theme-toggle{display:none}.print-chart{display:block}.page{max-width:none}.lead{font-size:14px}details{display:block}}'''
    css+='html[data-theme=dark] nav a,html[data-theme=dark] .note,html[data-theme=dark] .sample-line,html[data-theme=dark] .asset-line,html[data-theme=dark] footer,html[data-theme=dark] figcaption{color:#aec0ce}'
    return dict(sections=sections,figures=figures,javascript=js,css=css,version=VERSION,plotly_sha256=PLOTLY_SHA)
