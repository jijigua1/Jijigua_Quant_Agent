"""Stage 2 (2026 rolling Test delivery, 2026-10-15): read vs refresh, refresh transparency, newest-revision access,
report recovery from an issued receipt, and the program-stated 2026 access rules. Synthetic engineering data only."""
import json
from pathlib import Path

import pytest

from v1beta_fixtures import REVERSAL, TRAIN, build, broker, context


@pytest.fixture
def study(tmp_path):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    client, b = broker(fx)
    backend.rolling = client
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    return fx, backend, result, b


def readable(backend, result):
    """The session check of read_study is covered elsewhere (test_quant_integration); here the study is in the session."""
    original = Path(result['factor_path']).parents[1]
    evidence = {k: result[k] for k in ('resource_id', 'analysis_sha256', 'report_path', 'report_status') if k in result}
    evidence.update(artifact_path=str(original), resource_id=TRAIN)
    if 'analysis_sha256' not in evidence:
        import hashlib
        evidence['analysis_sha256'] = hashlib.sha256((original / 'data/analysis.json').read_bytes()).hexdigest()
    evidence.setdefault('report_path', str(original / 'reports/report.md'))
    evidence.setdefault('report_status', 'COMPLETED')
    backend.artifacts.locate = lambda study_id, ctx: (original, evidence)
    return original


class Spy:
    """Counts evaluator requests made through the client."""
    def __init__(self, client):
        self.client, self.calls = client, 0
        self.available, self.receipt_dir = client.available, client.receipt_dir

    def status(self):
        return self.client.status()

    def evaluate(self, *a):
        self.calls += 1
        return self.client.evaluate(*a)

    def load_receipt(self, *a):
        return self.client.load_receipt(*a)


def evaluations(fx):
    import sqlite3
    db = sqlite3.connect(next(Path(fx['tmp']).glob('eval/*.sqlite*')))
    return db.execute('select count(*) from evaluations').fetchone()[0]


def test_reading_a_study_has_no_side_effect_unless_a_refresh_is_asked(study):
    """Production audit P1: qrtk_read_study evaluated, published and wrote reports although the user only read."""
    fx, backend, result, _ = study
    original = readable(backend, result)
    before = sorted(p.name for p in original.parent.iterdir())
    backend.rolling = spy = Spy(backend.rolling)
    out = backend.read_study(TRAIN, result['study_id'], context())
    assert spy.calls == 0 and sorted(p.name for p in original.parent.iterdir()) == before
    a = out['report_access']
    assert a['refresh'] == {'requested': False, 'status': 'NOT_REQUESTED'} and a['shown_revision'] == 2
    assert a['test_status'] == 'COMPLETED' and a['data_cutoff'] and a['receipt_evaluation_id']
    from research_agent.report_versions import report_access_text
    text = report_access_text(a)
    assert '只读查询' in text and '刷新2026' in text and '第 2 版' in text
    again = backend.read_study(TRAIN, result['study_id'], context(), refresh=True)      # same snapshot: reuse, no revision
    assert spy.calls == 1 and again['report_access']['refresh']['status'] == 'REUSED_NO_CHANGE'


def test_a_failed_refresh_says_so_and_keeps_showing_the_last_success(study, monkeypatch):
    """Production audit P2: a failed refresh returned the old report silently."""
    fx, backend, result, _ = study
    readable(backend, result)

    class Down(Spy):
        def evaluate(self, *a):
            raise OSError('broker gone')
    backend.rolling = Down(backend.rolling)
    out = backend.read_study(TRAIN, result['study_id'], context(), refresh=True)
    a = out['report_access']
    assert a['refresh']['status'] == 'FAILED' and a['refresh']['category'] == 'EVALUATOR_ERROR'
    assert out['metrics']['professional']['test']['status'] == 'COMPLETED' and a['shown_revision'] == 2
    from research_agent.report_versions import report_access_text
    text = report_access_text(a)
    assert '最新一次刷新未成功' in text and '不是本次刷新的结果' in text


def test_a_receipt_whose_report_failed_is_finished_without_a_new_evaluation(tmp_path, monkeypatch):
    """Production audit P1 (GH 20:14): a receipt was issued but the report never followed. The receipt id is recorded and a
    refresh builds the report from that receipt; the evaluator ledger gains no row and a repeat is idempotent."""
    from research_agent import report_versions
    from research_agent.contracts import ContractError
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    real = report_versions.append_rolling_report
    state = {'broken': True}

    def flaky(artifacts, original, outcome):
        if outcome.get('status') == 'COMPLETED' and state['broken']:
            raise ContractError('JSON exceeds size limit')
        return real(artifacts, original, outcome)
    monkeypatch.setattr(report_versions, 'append_rolling_report', flaky)
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    original = readable(backend, result)
    versions = json.loads((original / 'reports/report_versions.json').read_text(encoding='utf-8'))
    eid = result['rolling_test']['evaluation_id']
    assert versions[-1]['rolling_status'] == 'FAILED' and versions[-1]['receipt_evaluation_id'] == eid
    read = backend.read_study(TRAIN, result['study_id'], context())
    assert read['report_access']['pending_receipt'] == eid and '不会重新评价' in report_versions.report_access_text(read['report_access'])
    rows = evaluations(fx)
    state['broken'] = False
    events = []
    out = backend.read_study(TRAIN, result['study_id'], context(events=events), refresh=True)
    a = out['report_access']
    assert a['recovered']['status'] == 'COMPLETED' and a['recovered']['evaluation_id'] == eid
    assert out['metrics']['professional']['test']['status'] == 'COMPLETED' and a['pending_receipt'] is None
    assert evaluations(fx) == rows                                         # no new evaluation, only the report
    revision = Path(out['report_artifact_path'])
    assert json.loads((revision / 'manifest.json').read_text(encoding='utf-8'))['new_evaluation'] is False
    again = backend.read_study(TRAIN, result['study_id'], context(), refresh=True)
    n = len(json.loads((original / 'reports/report_versions.json').read_text(encoding='utf-8')))
    assert again['report_access']['recovered'] is None and n == 3          # idempotent: no further revision


def test_the_original_study_directory_points_to_the_newest_report(study):
    """Production audit: browsing 20-19-52 (revision 1, Test PENDING) did not lead to 20-21-04 (revision 2)."""
    fx, backend, result, _ = study
    original = Path(result['factor_path']).parents[1]
    page = (original / 'reports/LATEST_REPORT.html').read_text(encoding='utf-8')
    assert '最新报告：第 2 版' in page and result['html_path'] in page and '第 1 版（原始研究）' in page
    manifest = json.loads((original / 'manifest.json').read_text(encoding='utf-8'))
    assert any(f['path'] == 'reports/LATEST_REPORT.html' for f in manifest['files'])


def test_a_failed_later_attempt_does_not_hide_an_earlier_success(study):
    fx, backend, result, _ = study
    original = Path(result['factor_path']).parents[1]
    from research_agent.report_versions import append_rolling_report, latest_report
    append_rolling_report(backend.artifacts, original, dict(status='NOT_EVALUATED', reason='FAILED', detail='EVALUATOR_ERROR'))
    out = latest_report(backend.artifacts, original, json.loads((original / 'data/analysis.json').read_text(encoding='utf-8')))
    assert out['report_revision'] == 2 and out['metrics']['professional']['test']['status'] == 'COMPLETED'


@pytest.mark.parametrize('status,state,phrase', [
    ({'status': 'OK', 'authorized': True, 'synthetic': False, 'contract': 'rolling-test-contract/1'}, 'ROLLING_AUTHORIZED', '已经授权并自动执行'),
    ({'status': 'OK', 'authorized': False, 'synthetic': False}, 'ROLLING_NOT_AUTHORIZED', '不代表正式生产环境没有部署'),
    (None, 'EVALUATOR_UNAVAILABLE', '没有连接2026滚动评价器')])
def test_2026_access_is_stated_by_the_program(status, state, phrase):
    """Production audit P1: ordinary replies said the rolling Test 'still needs approval' while it was authorized."""
    from research_agent.test_access import describe
    d = describe(status)
    assert d['state'] == state and phrase in d['text']
    assert '原始行情和未来标签任何时候都不能由Agent读取' in d['text'] and '一次性独立测试' in d['text'] and 'UNSUPPORTED_STUDY' in d['text']


def test_a_study_from_another_session_is_explained_without_widening_access():
    """Production audit P2: a new session could not find an earlier session's report. The answer explains how to reach it;
    the session check itself is unchanged (covered by test_quant_integration)."""
    from research_agent.conversation import FAILURE_TEXT
    for code in ('STUDY_NOT_IN_SESSION', 'ARTIFACT_DIRECTORY_UNAVAILABLE', 'STUDY_NOT_IN_LEDGER'):
        text = FAILURE_TEXT[code]
        assert '/session' in text and 'quant-agent chat --resume' in text and 'reports/LATEST_REPORT.html' in text
        assert '权限设计' in text and '管理员' in text


def test_a_new_study_still_triggers_the_rolling_evaluation_automatically(tmp_path):
    """refresh=False only governs reading; finishing a NEW study still runs the controlled 2026 evaluation once."""
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    client, _ = broker(fx)
    backend.rolling = spy = Spy(client)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    assert spy.calls == 1 and result['rolling_test']['status'] == 'COMPLETED' and result['report_revision'] == 2
    assert evaluations(fx) == 1


def test_recovering_a_report_never_rewrites_or_resigns_a_receipt(tmp_path, monkeypatch):
    import hashlib
    from research_agent import report_versions
    from research_agent.contracts import ContractError
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    real, state = report_versions.append_rolling_report, {'broken': True}

    def flaky(artifacts, original, outcome):
        if outcome.get('status') == 'COMPLETED' and state['broken']:
            raise ContractError('JSON exceeds size limit')
        return real(artifacts, original, outcome)
    monkeypatch.setattr(report_versions, 'append_rolling_report', flaky)
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling, _ = broker(fx)
    result = backend.expression_study(TRAIN, REVERSAL, '短期反转', '合成工程验收', 5, 5, 'raw', context())
    readable(backend, result)
    digest = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(fx['tmp']).glob('receipts/*.json')}
    before = digest()
    assert before
    state['broken'] = False
    backend.read_study(TRAIN, result['study_id'], context(), refresh=True)
    assert digest() == before                                                  # same files, same bytes, same signatures
