"""Operator-only authenticated Test merge. Never a model Tool or data reader."""
import hashlib
import hmac
import json
import os
from pathlib import Path
from .contracts import canonical,validate
from .security import Denied


def append_test_report(artifacts, original, receipt, approval_key):
    from .research_report import render
    import pandas as pd
    original=artifacts.checked_run(original)
    m=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    entries={f['path']:f for f in m['files']}
    def checked(name):
        p=original/name
        if name not in entries or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>512*1024*1024:
            raise Denied('REPORT_SOURCE_DENIED')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entries[name]['sha256']:raise Denied('REPORT_SOURCE_FINGERPRINT')
        return raw
    if len(approval_key)<32 or set(receipt)!={'result','signature'}:raise Denied('TEST_RECEIPT_REQUIRED')
    raw=canonical(receipt['result'],max_bytes=65536)
    sig=hmac.new(approval_key,raw.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig,receipt['signature']):raise Denied('TEST_RECEIPT_SIGNATURE')
    test=receipt['result'];result=json.loads(checked('data/analysis.json'))
    definition=json.loads(checked('code/factor_definition.json'));frozen=test['frozen_definition']
    from .independent_evaluator import freeze
    if (test['status']!='COMPLETED' or freeze(frozen)['definition_sha256']!=test['definition_sha256'] or
        test['research_study_id']!=result['study_id'] or frozen['research_study_id']!=result['study_id'] or
        frozen['approved_train_validation_fingerprint']!=result['data_sha256'] or
        frozen['code_sha256']!=m['code_sha256']):raise Denied('TEST_RECEIPT_STUDY_MISMATCH')
    if test['synthetic']!=(result['mode']=='synthetic'):raise Denied('SYNTHETIC_TEST_REAL_REPORT_DENIED')
    expression=definition.get('expression')
    if expression is None and result['parameters']['factor_id']=='reversal':
        expression=dict(nodes=[dict(op='field',field='close'),dict(op='returns',args=[0],window=result['parameters']['lookback']),dict(op='neg',args=[1])],output=2)
    if expression is None:raise Denied('TEST_FACTOR_DEFINITION_UNSUPPORTED')
    params=result['parameters']
    if (frozen['expression']!=expression or frozen['horizon']!=params['horizon'] or
        frozen['n_groups']!=params['n_groups'] or frozen['standardization']!=params['standardization']):
        raise Denied('TEST_FROZEN_PARAMETERS_MISMATCH')
    index=original/'reports/report_versions.json'
    versions=json.loads(checked('reports/report_versions.json')) if index.exists() else [dict(revision=1,html=str(original/'reports/report.html'),markdown=str(original/'reports/report.md'))]
    if any(v.get('evaluation_id')==test['evaluation_id'] for v in versions):raise Denied('TEST_RECEIPT_ALREADY_MERGED')
    p=result['metrics']['professional'];p['test']=test['test'];p['report_revision']=len(versions)+1
    schema=json.loads((Path(__file__).parent/'resources/factor_report.schema.json').read_text())
    validate(p,schema)
    claim=original/'reports'/('test_receipt_'+test['evaluation_id']+'.claim')
    try:
        with claim.open('x',encoding='utf-8') as out:out.write(hashlib.sha256(raw.encode()).hexdigest())
    except FileExistsError:raise Denied('TEST_RECEIPT_ALREADY_MERGED') from None
    # Keep Train/Validation conclusions and append actual Test evidence, never select new parameters.
    from .research_report import number
    t=p['test']['metrics'];p['verdict']['evidence'].append(
        f"Test ({test['evaluation_type']})：IC {number(t['ic_mean'])} / RankIC {number(t['rank_ic_mean'])}，有效日 {t['rank_ic_n_dates']}；曝光已登记。")
    a=p['partitions']['valid']['rank_ic_mean']
    if t['rank_ic_mean'] is None or t['rank_ic_n_dates']<60:p['verdict']['status']='NEEDS_MORE_EVIDENCE'
    elif a is not None and a*t['rank_ic_mean']<=0:p['verdict']['status']='UNSTABLE'
    archive_id,run=artifacts.create_revision(original,p['report_revision'])
    # Copy only bounded statistical inputs. PKL/data matrices remain immutable in the original study.
    for name in entries:
        if name.startswith('data/') and name.endswith('.csv') and name not in ('data/factor_values.csv','data/input_slice.csv'):
            if entries[name]['bytes']>8*1024*1024:raise Denied('REPORT_STATISTICS_BUDGET')
            (run/name).write_bytes(checked(name))
    (run/'code/factor_definition.json').write_bytes(checked('code/factor_definition.json'))
    artifacts.write_json(run/'data/evaluation_summary.json',p)
    artifacts.write_json(run/'data/test_receipt.json',test)
    import io
    factor=pd.read_csv(io.BytesIO(checked('data/factor_values.csv')),index_col=0,parse_dates=True,float_precision='round_trip')
    result.update(render(run,result,factor,{},m.get('goal','统一三阶段因子报告'),definition.get('hypothesis','冻结因子独立评价'),definition))
    result['factor_path']=str(original/'data/factor.pkl');result['artifact_path']=str(original)
    artifacts.write_json(run/'data/analysis.json',result,max_bytes=1024*1024)
    vm=dict(task_id=m['task_id'],run_id=archive_id.split(':')[1],study_id=result['study_id'],
        report_revision=p['report_revision'],evaluation_id=test['evaluation_id'],source_study=str(original),
        source_manifest_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
        frozen_definition_sha256=test['definition_sha256'],test_data_sha256=test['data_sha256'],
        code_sha256=m['code_sha256'],artifact_budget_bytes=m.get('artifact_budget_bytes',20*1024*1024),
        task_status='RUNNING',test_exposure=test['test']['exposure'],files=[])
    artifacts.write_json(run/'manifest.json',vm);artifacts.update_manifest(run,dict(task_status='COMPLETED',files=artifacts.inventory(run)))
    versions.append(dict(revision=p['report_revision'],evaluation_id=test['evaluation_id'],study_id=result['study_id'],
        artifact_path=str(run),html=result['html_path'],markdown=result['report_path'],
        manifest_sha256=hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest()))
    temp=index.with_suffix('.'+test['evaluation_id']+'.tmp')
    with temp.open('x',encoding='utf-8') as out:out.write(canonical(versions))
    os.replace(temp,index)
    artifacts.update_manifest(original,dict(report_revision=p['report_revision'],files=artifacts.inventory(original)))
    return versions[-1]


ROLLING_REASONS = {'NOT_AUTHORIZED': '本环境（例如预发布环境）未获授权使用2026滚动评价通道；这不代表正式生产环境没有部署滚动Test。未读取或计算任何2026数据。',
    'EVALUATOR_UNAVAILABLE': '本进程没有连接受控评价代理（例如离线/测试环境），未计算2026结果。',
    'NO_TEST_DATA': '尚无合格的2026行情快照。', 'NO_MATURE_LABELS': '2026行情存在，但H期未来标签尚未成熟。',
    'HISTORY_MISMATCH': '评价器在Validation重叠日重算的因子与研究存档不一致，结果未合并。',
    'FAILED': '受控评价失败，失败已登记且不自动重试。', 'UNSUPPORTED_STUDY': '该研究定义暂不支持受控重算。',
    'PENDING': '已冻结研究定义，滚动2026评价将作为下一报告版本生成。'}


TEST_DAILY_SOURCE='data/test_receipt.json'


def test_daily(run, test):
    """Daily Test rows of a revision: inline (older revisions) or from its receipt copy, checked against the report."""
    if 'daily' in test:return test['daily']
    if test.get('daily_source')!=TEST_DAILY_SOURCE:raise Denied('TEST_DAILY_SOURCE')
    path=Path(run)/TEST_DAILY_SOURCE
    if path.is_symlink() or path.stat().st_size>16*1024*1024:raise Denied('TEST_DAILY_SOURCE')
    result=json.loads(path.read_text(encoding='utf-8'))['result']
    rows=result['test']['daily']
    if result['evaluation_id']!=(test.get('exposure') or {}).get('evaluation_id') or len(rows)!=test.get('daily_rows'):
        raise Denied('TEST_DAILY_MISMATCH')
    return rows


def append_rolling_report(artifacts, original, outcome):
    """Agent-side revision for ROLLING_EXPOSED_TEST. The receipt was verified against the root-owned registry by the
    caller (RollingClient); this function never computes Test statistics. A status-only revision records a refusal."""
    from .research_report import render
    original=artifacts.checked_run(original)
    m=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    entries={f['path']:f for f in m['files']}
    def checked(name,limit=512*1024*1024):
        p=original/name
        if name not in entries or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>limit:
            raise Denied('REPORT_SOURCE_DENIED')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entries[name]['sha256']:raise Denied('REPORT_SOURCE_FINGERPRINT')
        return raw
    result=json.loads(checked('data/analysis.json'))
    definition=json.loads(checked('code/factor_definition.json'))
    index=original/'reports/report_versions.json'
    versions=json.loads(checked('reports/report_versions.json'))
    completed=outcome.get('status')=='COMPLETED'
    if completed:
        receipt=outcome['receipt'];r=receipt['result']
        if r['study_id']!=result['study_id'] or r['evaluation_type']!='ROLLING_EXPOSED_TEST':
            raise Denied('ROLLING_RECEIPT_STUDY_MISMATCH')
        if r['synthetic']!=(result['mode']=='synthetic'):raise Denied('SYNTHETIC_TEST_REAL_REPORT_DENIED')
        same=next((v for v in versions if v.get('evaluation_id')==r['evaluation_id']),None)
        if same:return same|{'reused':True}
        t=r['test']
        test=dict(status='COMPLETED',access='CONTROLLED_EVALUATOR',evaluation_type='ROLLING_EXPOSED_TEST',
            exposure=t['exposure'],start=t['start'],end=t['end'],metrics=t['metrics'],annual=t['annual'],monthly=t['monthly'],
            daily_rows=len(t['daily']),daily_source=TEST_DAILY_SOURCE,
            group_columns=t['group_columns'],group_definition=t['group_definition'],maturity=r['maturity'],
            snapshot={k:r['snapshot'][k] for k in ('version','certified_end','manifest_sha256','status')},
            receipt_sha256=receipt['registry_sha256'])
    else:
        reason=outcome.get('reason') if outcome.get('reason') in ROLLING_REASONS else 'FAILED'
        last=versions[-1]
        if last.get('rolling_status')==reason and last.get('receipt_evaluation_id')==outcome.get('receipt_evaluation_id'):
            return last|{'reused':True}
        detail=str(outcome.get('detail') or '')
        if 'APPROVED_DEFINITION_WITHOUT_TRUSTED_IR' in detail:
            detail='该因子由经你审核的模型算法计算（超出可信IR算子范围）；独立评价器不运行模型代码，因此2026 Test无法由受控评价器计算。'
        test=dict(status='NOT_EVALUATED',access='SEALED',evaluation_type=None,exposure=None,reason=reason,
                  detail=(ROLLING_REASONS[reason]+(' '+detail if detail else ''))[:400])
        if outcome.get('receipt_evaluation_id'):
            test['receipt_evaluation_id']=outcome['receipt_evaluation_id']   # Test computed, report failed: recoverable
    p=result['metrics']['professional'];p['test']=test;p['report_revision']=len(versions)+1
    schema=json.loads((Path(__file__).parent/'resources/factor_report.schema.json').read_text())
    validate(p,schema)
    if completed:
        # Daily Test rows grow with every trading day; they stay in the receipt copy and are validated row by row.
        row_schema=schema['properties']['test']['properties']['daily']['items']
        for row in r['test']['daily']:validate(row,row_schema)
    from .research_report import number
    if completed:
        t=test['metrics']
        p['verdict']['evidence'].append(
            f"Test（滚动暴露评价，快照截至{test['snapshot']['certified_end']}）：IC {number(t['ic_mean'])} / RankIC {number(t['rank_ic_mean'])}，"
            f"有效日 {t['rank_ic_n_dates']}；持续曝光，不是盲测。")
        a=p['partitions']['valid']['rank_ic_mean']
        if t['rank_ic_mean'] is None or t['rank_ic_n_dates']<60:p['verdict']['status']='NEEDS_MORE_EVIDENCE'
        elif a is not None and a*t['rank_ic_mean']<=0:p['verdict']['status']='UNSTABLE'
    archive_id,run=artifacts.create_revision(original,p['report_revision'])
    for name in entries:
        if name.startswith('data/') and name.endswith('.csv') and name not in ('data/factor_values.csv','data/input_slice.csv'):
            if entries[name]['bytes']>16*1024*1024:raise Denied('REPORT_STATISTICS_BUDGET')
            (run/name).write_bytes(checked(name))
        elif name.startswith('figures/') and not Path(name).name.startswith(('interactive_','rank_ic_monthly_','ic_monthly_')):
            (run/name).write_bytes(checked(name,32*1024*1024))
    (run/'code/factor_definition.json').write_bytes(checked('code/factor_definition.json'))
    if 'code/economic_rationale.json' in entries:
        (run/'code/economic_rationale.json').write_bytes(checked('code/economic_rationale.json'))
    if 'code/paper_definition.json' in entries:      # the paper-check section and the canonical definition SHA travel with every revision
        (run/'code/paper_definition.json').write_bytes(checked('code/paper_definition.json'))
    if (original/'code/factor_formula.tex').exists() and 'code/factor_formula.tex' in entries:
        (run/'code/factor_formula.tex').write_bytes(checked('code/factor_formula.tex'))
    artifacts.write_json(run/'data/evaluation_summary.json',p)
    if completed:artifacts.write_json(run/'data/test_receipt.json',outcome['receipt'],max_bytes=1024*1024)
    if completed:
        # Static charts copied from revision 1 cover Train/Validation; redraw them with the receipt's Test evidence or state why not.
        from .report_test_figures import render as test_figures
        test_figures(run,result)
    result.update(render(run,result,None,{},m.get('goal','统一三阶段因子报告'),definition.get('hypothesis','冻结研究定义'),definition))
    result['factor_path']=str(original/'data/factor.pkl');result['artifact_path']=str(original)
    from .report_consistency import check as consistency
    result['report_consistency']=consistency(run,result)
    artifacts.write_json(run/'data/analysis.json',result,max_bytes=2*1024*1024)
    vm=dict(task_id=m['task_id'],run_id=archive_id.split(':')[1],study_id=result['study_id'],
        report_revision=p['report_revision'],evaluation_id=test.get('exposure',{}).get('evaluation_id') if completed else None,
        rolling_status='COMPLETED' if completed else test['reason'],source_study=str(original),
        source_manifest_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
        code_sha256=m['code_sha256'],artifact_budget_bytes=m.get('artifact_budget_bytes',20*1024*1024),
        task_status='RUNNING',test_exposure=test.get('exposure'),new_evaluation=completed and not outcome.get('reused'),files=[])
    if test.get('receipt_evaluation_id'):vm['receipt_evaluation_id']=test['receipt_evaluation_id']
    artifacts.write_json(run/'manifest.json',vm);artifacts.update_manifest(run,dict(task_status='COMPLETED',files=artifacts.inventory(run)))
    versions.append(dict(revision=p['report_revision'],evaluation_id=vm['evaluation_id'],rolling_status=vm['rolling_status'],
        study_id=result['study_id'],artifact_path=str(run),html=result['html_path'],markdown=result['report_path'],
        manifest_sha256=hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest(),
        **({'receipt_evaluation_id':vm['receipt_evaluation_id']} if vm.get('receipt_evaluation_id') else {}),
        **({'certified_end':test['snapshot']['certified_end']} if completed else {})))
    temp=index.with_suffix('.r'+str(p['report_revision'])+'.tmp')
    with temp.open('x',encoding='utf-8') as out:out.write(canonical(versions))
    os.replace(temp,index)
    write_latest_pointer(original,versions)
    artifacts.update_manifest(original,dict(report_revision=p['report_revision'],files=artifacts.inventory(original)))
    return versions[-1]|{'reused':False}


LATEST_POINTER = 'reports/LATEST_REPORT.html'


def write_latest_pointer(original, versions):
    """A small page in the ORIGINAL study directory naming every report revision and the newest successful one, so
    browsing the first run no longer leaves the user on revision 1 (production audit: 20-19-52 vs 20-21-04)."""
    from html import escape
    best=next((v for v in reversed(versions) if v.get('rolling_status') in ('COMPLETED','INVALIDATED')),versions[-1])
    rows=''.join(f"<tr><td>{v['revision']}</td><td>{escape(str(v.get('rolling_status') or '原始研究'))}</td>"
                 f"<td>{escape(str(v.get('certified_end') or ''))}</td><td><a href='file://{escape(v['html'])}'>{escape(v['html'])}</a></td></tr>"
                 for v in versions)
    page=("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>最新报告</title><body style='font-family:sans-serif'>"
          f"<h2>本研究的最新报告：第 {best['revision']} 版</h2><p><a href='file://{escape(best['html'])}'>{escape(best['html'])}</a></p>"
          "<p>本目录是第 1 版（原始研究）。后续版本在各自的目录中，历史版本保留不改。</p>"
          f"<table border='1' cellpadding='4'><tr><th>版本</th><th>2026状态</th><th>2026数据截至</th><th>报告</th></tr>{rows}</table></body></html>")
    temp=original/'reports/.LATEST_REPORT.tmp'
    temp.write_text(page,encoding='utf-8')
    os.replace(temp,original/LATEST_POINTER)


def pending_receipts(original):
    """Receipt ids recorded by failed report revisions and never turned into a COMPLETED revision."""
    index=original/'reports/report_versions.json'
    if not index.exists():return []
    versions=json.loads(index.read_text(encoding='utf-8'))
    done={v.get('evaluation_id') for v in versions if v.get('rolling_status')=='COMPLETED'}
    return [v['receipt_evaluation_id'] for v in versions if v.get('receipt_evaluation_id') and v['receipt_evaluation_id'] not in done][-1:]


def report_access(original, out, refresh, recovered, evaluator=False):
    """What the user is looking at (program-written): original and newest revisions, 2026 evidence, data cutoff, the
    outcome of a requested refresh, and a pending receipt waiting for its report."""
    index=original/'reports/report_versions.json'
    versions=json.loads(index.read_text(encoding='utf-8')) if index.exists() else [dict(revision=1,rolling_status=None)]
    shown=out.get('report_revision',1)
    last=versions[-1]
    completed=[v for v in versions if v.get('rolling_status')=='COMPLETED']
    test=(out.get('metrics') or {}).get('professional',{}).get('test') or {}
    return dict(original_revision=1,shown_revision=shown,latest_attempt_revision=last.get('revision'),
                latest_attempt_status=last.get('rolling_status'),
                latest_completed_revision=completed[-1]['revision'] if completed else None,
                test_status=test.get('status'),test_reason=test.get('reason'),
                receipt_evaluation_id=(test.get('exposure') or {}).get('evaluation_id'),
                data_cutoff=(test.get('snapshot') or {}).get('certified_end'),
                pending_receipt=(pending_receipts(original) or [None])[-1],
                refresh=refresh,recovered=recovered,evaluator_connected=bool(evaluator),
                versions=[{k:v.get(k) for k in ('revision','rolling_status','certified_end','evaluation_id')} for v in versions][-6:])


REFRESH_CN = {'NOT_AUTHORIZED': '本环境未授权2026滚动评价', 'EVALUATOR_UNAVAILABLE': '本会话没有连接2026评价器（请用 quant-agent chat 启动的会话查询）',
              'UNSUPPORTED_STUDY': '该研究定义不在评价器可重算范围内', 'HISTORY_MISMATCH': '评价器重算的暖机期因子与研究不一致，结果未采用',
              'REPORT_FAILED': '2026已计算、回执已登记，但报告生成失败；再次刷新会用同一回执补完报告，不会重新评价',
              'EVALUATOR_ERROR': '评价器出错', 'SKIPPED_INVALID_DEFINITION': '研究定义已登记为无效，不再评价'}


def report_access_text(a):
    """Program-written lines: which report revision is shown, its 2026 evidence and the outcome of a requested refresh."""
    lines = [f"报告版本：当前展示第 {a['shown_revision']} 版（共 {len(a.get('versions') or [1])} 个版本，第 1 版为原始研究；历史版本保留不改）。"]
    if a.get('test_status') == 'COMPLETED':
        lines.append(f"2026滚动Test：已有结果，数据截至 {a.get('data_cutoff')}，回执 {str(a.get('receipt_evaluation_id'))[:12]}。")
    elif a.get('pending_receipt'):
        lines.append(f"2026滚动Test：评价器已计算（回执 {a['pending_receipt'][:12]}），但报告尚未生成；说“刷新2026”会用这张回执补完报告，不会重新评价。")
    else:
        lines.append(f"2026滚动Test：{a.get('test_reason') or '暂无结果'}。")
    r = a.get('refresh') or {}
    st = r.get('status')
    if st == 'NOT_REQUESTED':
        lines.append("本次为只读查询，没有请求评价器；如需更新到最新行情，请说“刷新2026”。")
    elif st == 'NEW_REVISION':
        lines.append(f"已刷新：生成第 {r.get('revision')} 版，2026数据截至 {r.get('certified_end')}。")
    elif st == 'REUSED_NO_CHANGE':
        lines.append("已检查：最新快照的结果已有回执，沿用，没有新的评价，也没有新版本。")
    elif st:
        lines.append(f"最新一次刷新未成功（{REFRESH_CN.get(r.get('category') or st, r.get('category') or st)}"
                     + (f"；明细：{r.get('detail')}" if r.get('detail') else '') + f"）。当前展示的是第 {a['shown_revision']} 版"
                     + (f"，2026数据截至 {a.get('data_cutoff')}" if a.get('data_cutoff') else '') + "，不是本次刷新的结果。")
    rec = a.get('recovered') or {}
    if rec.get('status') == 'COMPLETED':
        lines.append(f"已用既有回执 {str(rec.get('evaluation_id'))[:12]} 补完报告（第 {rec.get('revision')} 版），没有重新评价。")
    elif rec.get('status') == 'FAILED':
        lines.append(f"用既有回执 {str(rec.get('evaluation_id'))[:12]} 补完报告未成功（{rec.get('detail')}），回执仍保留。")
    if a.get('latest_attempt_revision') and a['latest_attempt_revision'] != a['shown_revision'] \
            and a.get('latest_attempt_status') not in (None, 'COMPLETED', 'INVALIDATED'):
        lines.append(f"注意：第 {a['latest_attempt_revision']} 版是一次未成功的尝试（{a['latest_attempt_status']}），当前展示的是最近一次成功的第 {a['shown_revision']} 版。")
    return '\n'.join(lines)


def latest_report(artifacts, original, result, rolling=None):
    """Read an authenticated revision index; historical no-index studies remain valid. A 2026 rolling Test result is shown
    only when its receipt equals the copy in the trusted registry of `rolling` (the process's RollingClient)."""
    index=original/'reports/report_versions.json'
    if not index.exists():return result
    manifest=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    item=next(x for x in manifest['files'] if x['path']=='reports/report_versions.json')
    if index.is_symlink() or index.stat().st_nlink!=1 or hashlib.sha256(index.read_bytes()).hexdigest()!=item['sha256']:
        raise Denied('REPORT_INDEX_FINGERPRINT')
    versions=json.loads(index.read_text(encoding='utf-8'))
    if len(versions)==1:return result
    v=versions[-1]
    if v.get('rolling_status') not in ('COMPLETED','INVALIDATED'):
        # a failed or status-only attempt after a successful revision: keep showing the success, state the failure
        v=next((x for x in reversed(versions) if x.get('rolling_status') in ('COMPLETED','INVALIDATED')),v)
        if v.get('revision')==1:return result
    run=artifacts.checked_run(v['artifact_path']);path=run/'manifest.json'
    if path.is_symlink() or path.stat().st_nlink!=1 or hashlib.sha256(path.read_bytes()).hexdigest()!=v['manifest_sha256']:raise Denied('REPORT_REVISION_FINGERPRINT')
    vm=json.loads(path.read_text(encoding='utf-8'))
    if vm['study_id']!=result['study_id']:raise Denied('REPORT_REVISION_STUDY')
    record=next(f for f in vm['files'] if f['path']=='data/analysis.json')
    analysis=run/'data/analysis.json'
    if analysis.is_symlink() or analysis.stat().st_nlink!=1 or analysis.stat().st_size>1024*1024 or hashlib.sha256(analysis.read_bytes()).hexdigest()!=record['sha256']:raise Denied('REPORT_ANALYSIS_FINGERPRINT')
    updated=json.loads(analysis.read_text(encoding='utf-8'))
    test=updated['metrics']['professional']['test'];months=[]
    receipt_record=next((f for f in vm['files'] if f['path']=='data/test_receipt.json'),None)
    if test['status']=='COMPLETED' and not receipt_record:
        raise Denied('REPORT_RECEIPT_REQUIRED')
    if test['status']=='COMPLETED' and receipt_record:
        receipt_path=run/'data/test_receipt.json'
        if (receipt_path.is_symlink() or receipt_path.stat().st_nlink!=1 or receipt_path.stat().st_size>128*1024
            or hashlib.sha256(receipt_path.read_bytes()).hexdigest()!=receipt_record['sha256']):
            raise Denied('REPORT_RECEIPT_FINGERPRINT')
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        signed=receipt.get('result',receipt)
        if test.get('evaluation_type')=='ROLLING_EXPOSED_TEST' and signed.get('evaluation_type')!='ROLLING_EXPOSED_TEST':
            raise Denied('REPORT_RECEIPT_TYPE_MISMATCH')
        if signed.get('evaluation_type')=='ROLLING_EXPOSED_TEST':
            # The study directory is written by the research process itself, so its receipt bytes, manifest and index
            # prove only that they agree with each other. A rolling Test is authentic only when it equals the broker's
            # registry copy, read through the process's trusted RollingClient (fixed directory, broker-owned single-link
            # file). No registry configured, an id outside the broker's syntax, or any mismatch: not shown (fail closed;
            # C6 skipped the check without QRA_ROLLING_RECEIPTS and built the path from an unchecked id -- C9 audit).
            from .rolling_client import EVALUATION_ID
            eid=signed.get('evaluation_id')
            if not isinstance(eid,str) or not EVALUATION_ID.fullmatch(eid):raise Denied('REPORT_RECEIPT_ID')
            if eid!=v['evaluation_id'] or signed['study_id']!=result['study_id']:
                raise Denied('REPORT_RECEIPT_STUDY')
            if rolling is None or getattr(rolling,'receipt_dir',None) is None:raise Denied('REPORT_RECEIPT_UNVERIFIED')
            try:
                stored=rolling.load_receipt(Path(rolling.receipt_dir)/(eid+'.json'),result['study_id'])
            except (OSError,ValueError,KeyError):
                raise Denied('REPORT_RECEIPT_NOT_REGISTERED') from None
            if {k:stored[k] for k in ('result','signature')}!={k:receipt.get(k) for k in ('result','signature')}:
                raise Denied('REPORT_RECEIPT_NOT_REGISTERED')
            # Local manifests are research-writable. Bind every exposed Test field,
            # not just the receipt bytes, to the registry's authenticated result.
            if not all(k in signed for k in ('test','maturity','snapshot')) or not all(k in signed['test'] for k in (
                    'exposure','start','end','metrics','annual','monthly','daily','group_columns','group_definition')):
                raise Denied('REPORT_RECEIPT_METRICS_MISMATCH')
            t=signed['test']
            expected=dict(status='COMPLETED',access='CONTROLLED_EVALUATOR',evaluation_type='ROLLING_EXPOSED_TEST',
                exposure=t['exposure'],start=t['start'],end=t['end'],metrics=t['metrics'],annual=t['annual'],monthly=t['monthly'],
                daily_rows=len(t['daily']),daily_source=TEST_DAILY_SOURCE,
                group_columns=t['group_columns'],group_definition=t['group_definition'],maturity=signed['maturity'],
                snapshot={k:signed['snapshot'][k] for k in ('version','certified_end','manifest_sha256','status')},
                receipt_sha256=stored['registry_sha256'])
            if 'daily' in test:
                # Older authenticated revisions stored the same daily rows
                # inline. Admit that representation without weakening any value
                # comparison or requiring another historical evaluation.
                for key in ('daily_rows','daily_source'):
                    if key not in test:expected.pop(key)
            if {k:v for k,v in test.items() if k!='daily'}!=expected or ('daily' in test and test['daily']!=t['daily']):
                raise Denied('REPORT_RECEIPT_METRICS_MISMATCH')
            immature=list(signed['maturity']['immature_signal_dates'])
        else:
            # A research-writable evaluation_type must never select a weaker
            # verification path. Legacy files remain on disk, but an unverifiable
            # one-shot receipt is not certified 2026 evidence (no automatic rerun).
            raise Denied('REPORT_LEGACY_TEST_UNVERIFIED')
        for row in test.get('monthly',[]):
            n=row['observed_dates'];missing=sum(d.startswith(str(row['period'])) for d in immature)
            months.append(dict(period=row['period'],observed_dates=n,effective_dates=row['rank_ic_n_dates'],
                unmatured_labels=missing,reason='ALL_FORWARD_LABELS_UNMATURED' if n>0 and n==missing else
                'AVAILABLE' if row['rank_ic_n_dates']>0 else 'INSUFFICIENT_VALID_PAIRS'))
    test.pop('daily',None)  # Aggregate series remain in authenticated files, never model context.
    return result|{'html_path':v['html'],'report_path':v['markdown'],'artifact_path':str(run),'report_artifact_path':str(run),
        'report_revision':v['revision'],'report_manifest_sha256':v['manifest_sha256'],
        'test_monthly_label_status':months,'figure_paths':updated['figure_paths'],'metrics':updated['metrics']}


def render_published_revision(artifacts, original, rolling=None):
    """Operator-only render of authenticated public aggregates. Never updates the latest pointer."""
    from .research_report import render
    original=artifacts.checked_run(original)
    root_manifest=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    index=original/'reports/report_versions.json'
    index_record=next(x for x in root_manifest['files'] if x['path']=='reports/report_versions.json')
    if index.is_symlink() or index.stat().st_nlink!=1 or hashlib.sha256(index.read_bytes()).hexdigest()!=index_record['sha256']:
        raise Denied('REPORT_INDEX_FINGERPRINT')
    rows=json.loads(index.read_text(encoding='utf-8'))
    source=artifacts.checked_run(rows[-1]['artifact_path'])
    source_manifest=source/'manifest.json'
    if source_manifest.is_symlink() or source_manifest.stat().st_nlink!=1:raise Denied('REPORT_SOURCE_DENIED')
    raw=source_manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=rows[-1]['manifest_sha256']:raise Denied('REPORT_REVISION_FINGERPRINT')
    m=json.loads(raw);revision=rows[-1]['revision']+1
    if m['study_id']!=rows[-1]['study_id']:raise Denied('REPORT_REVISION_STUDY')
    allowed={}
    for entry in m['files']:
        name=entry['path'];rel=Path(name)
        if (rel.is_absolute() or '..' in rel.parts):raise Denied('REPORT_SOURCE_DENIED')
        if (name.startswith('data/') and rel.suffix in ('.csv','.json') and rel.name not in ('factor_values.csv','input_slice.csv','evaluation_chart_payload.json','evaluation_heatmaps.json','report_tables.json')
            or name.startswith('figures/') and rel.suffix in ('.png','.svg','.pdf')
            or name.startswith('code/') and rel.name=='factor_definition.json'):
            p=source/rel
            if p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>8*1024**2:raise Denied('REPORT_SOURCE_DENIED')
            data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise Denied('REPORT_SOURCE_FINGERPRINT')
            allowed[name]=data
    result=json.loads(allowed['data/analysis.json']);definition=json.loads(allowed['code/factor_definition.json'])
    result['test_monthly_label_status']=latest_report(artifacts,original,result,rolling)['test_monthly_label_status']
    result['metrics']['professional']['report_revision']=revision
    archive_id,run=artifacts.create_revision(original,revision)
    for name,data in allowed.items():
        if name not in ('data/analysis.json','data/evaluation_summary.json'):(run/name).write_bytes(data)
    presentation=render(run,result,None,{},root_manifest.get('goal','统一因子报告'),definition.get('hypothesis','冻结研究定义'),definition)
    result.update(presentation);result['artifact_path']=str(original)
    artifacts.write_json(run/'data/analysis.json',result,max_bytes=1024**2)
    artifacts.write_json(run/'data/evaluation_summary.json',result['metrics']['professional'])
    current=m|dict(run_id=archive_id.split(':')[1],report_revision=revision,
        source_revision_path=str(source),source_manifest_sha256=hashlib.sha256(raw).hexdigest(),
        source_study=str(original),report_only_revision=True,new_evaluation=False,
        root_manifest_before_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
        renderer_source_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('report_versions.py','research_report.py','interactive_report.py','factor_math.py')},files=[])
    artifacts.write_json(run/'manifest.json',current)
    artifacts.update_manifest(run,dict(files=artifacts.inventory(run)))
    return dict(revision=revision,study_id=result['study_id'],evaluation_id=m['evaluation_id'],artifact_path=str(run),
        html=presentation['html_path'],markdown=presentation['report_path'],
        manifest_sha256=hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest(),
        source_manifest_sha256=hashlib.sha256(raw).hexdigest(),latest_pointer_updated=False,new_evaluation=False)


def append_invalidation_report(artifacts, original, record):
    """Operator revision for a study whose definition was found wrong: the newest revision's numbers, files and receipt
    are copied unchanged, the report opens with the invalidation notice, and the index gains one row. Nothing earlier
    is modified; the record itself lives in the append-only invalidation register."""
    from .research_report import render
    original=artifacts.checked_run(original)
    m=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
    own={f['path']:f for f in m['files']}
    index=original/'reports/report_versions.json'
    if index.is_symlink() or index.stat().st_nlink!=1 or hashlib.sha256(index.read_bytes()).hexdigest()!=own['reports/report_versions.json']['sha256']:
        raise Denied('REPORT_INDEX_FINGERPRINT')
    versions=json.loads(index.read_text(encoding='utf-8'))
    last=versions[-1]
    if last.get('rolling_status')=='INVALIDATED':return last|{'reused':True}
    source=original
    if len(versions)>1:
        source=artifacts.checked_run(last['artifact_path'])
        if hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()!=last['manifest_sha256']:raise Denied('REPORT_REVISION_FINGERPRINT')
    entries={f['path']:f for f in json.loads((source/'manifest.json').read_text(encoding='utf-8'))['files']}
    def checked(name,limit=64*1024*1024):
        p=source/name
        if name not in entries or p.is_symlink() or p.stat().st_nlink!=1 or p.stat().st_size>limit:raise Denied('REPORT_SOURCE_DENIED')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entries[name]['sha256']:raise Denied('REPORT_SOURCE_FINGERPRINT')
        return raw
    result=json.loads(checked('data/analysis.json'))
    if record['study_id']!=result['study_id']:raise Denied('INVALIDATION_STUDY_MISMATCH')
    definition=json.loads(checked('code/factor_definition.json'))
    result['invalidation']={k:record[k] for k in ('code','reason_cn','evidence','recorded_by','recorded_at')}
    p=result['metrics']['professional'];p['report_revision']=len(versions)+1
    p['verdict']['evidence'].insert(0,'研究定义无效：'+record['reason_cn']+'；统计仅作历史记录。')
    archive_id,run=artifacts.create_revision(original,p['report_revision'])
    for name in entries:
        keep=(name.startswith('data/') and name.endswith('.csv') and name not in ('data/factor_values.csv','data/input_slice.csv')) or \
            (name.startswith('figures/') and not Path(name).name.startswith(('interactive_','rank_ic_monthly_','ic_monthly_'))) or \
            name in ('code/factor_definition.json','code/economic_rationale.json','code/paper_definition.json','code/factor_formula.tex',
                     'data/test_receipt.json')
        if keep:
            (run/name).parent.mkdir(parents=True,exist_ok=True)
            (run/name).write_bytes(checked(name))
    artifacts.write_json(run/'data/evaluation_summary.json',p)
    result.update(render(run,result,None,{},m.get('goal','研究报告'),definition.get('hypothesis','冻结研究定义'),definition))
    result['factor_path']=str(original/'data/factor.pkl');result['artifact_path']=str(original)
    from .report_consistency import check as consistency
    result['report_consistency']=consistency(run,result)
    artifacts.write_json(run/'data/analysis.json',result,max_bytes=2*1024*1024)
    vm=dict(task_id=m['task_id'],run_id=archive_id.split(':')[1],study_id=result['study_id'],report_revision=p['report_revision'],
        evaluation_id=last.get('evaluation_id'),rolling_status='INVALIDATED',source_study=str(original),
        source_manifest_sha256=hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
        code_sha256=m['code_sha256'],artifact_budget_bytes=m.get('artifact_budget_bytes',20*1024*1024),
        task_status='RUNNING',invalidation=result['invalidation'],new_evaluation=False,files=[])
    artifacts.write_json(run/'manifest.json',vm);artifacts.update_manifest(run,dict(task_status='COMPLETED',files=artifacts.inventory(run)))
    versions.append(dict(revision=p['report_revision'],evaluation_id=vm['evaluation_id'],rolling_status='INVALIDATED',
        study_id=result['study_id'],artifact_path=str(run),html=result['html_path'],markdown=result['report_path'],
        manifest_sha256=hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest()))
    temp=index.with_suffix('.r'+str(p['report_revision'])+'.tmp')
    with temp.open('x',encoding='utf-8') as out:out.write(canonical(versions))
    os.replace(temp,index)
    artifacts.update_manifest(original,dict(report_revision=p['report_revision'],files=artifacts.inventory(original)))
    return versions[-1]|{'reused':False}
