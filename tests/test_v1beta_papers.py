"""Paper library, upload validation, and the natural-language paper research flow with decision and code approval gates.

The model is scripted (real deepseek-flash outputs recorded in Phase 4 for understanding; operator-written candidate code);
data are synthetic. This is engineering evidence of the gates and plumbing, not market evidence."""
import base64
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from research_agent.app import build_chat
from research_agent.contracts import canonical
from research_agent.llm import ModelResponse, Role, ToolCall
from research_agent.providers.mock import MockProvider
from v1beta_fixtures import broker, build

FIX = Path(__file__).parent / 'fixtures_v1beta'
if not (FIX / 'live_model_outputs.json').is_file():
    pytest.skip('Private paper/model replay omitted from public repository', allow_module_level=True)
LIVE = json.loads((FIX / 'live_model_outputs.json').read_text(encoding='utf-8'))
OPERATOR_ILLIQ = '''import numpy as np
import pandas as pd


def compute(panels):
    close = panels["close"]
    amount = panels["amount"]
    ret = close / close.shift(1).replace(0, np.nan) - 1
    ratio = (ret.abs() / amount.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    out = ratio.rolling(250, min_periods=250).mean()
    return out.replace([np.inf, -np.inf], np.nan)
'''
GOOD_REPAIR = {"formula_latex": r"ILLIQ_{i,t} = \operatorname{mean}_{k=0}^{249}(\frac{|R_{i,t-k}|}{VOLD_{i,t-k}})",
               "replication_note": {"choice": "250-trading-day trailing average instead of the calendar-year average",
                                    "reason": "integer window; 250 trading days is the nominal length of one year"}}
RATIONALE = dict(intuition=dict(measures='单位成交额引起的平均绝对价格变动（价格冲击）', high_value_means='流动性差', low_value_means='流动性好'),
    mechanisms=[dict(name='非流动性溢价', category='liquidity_premium', source='literature', literature='Amihud and Mendelson (1986)',
                     explanation='投资者为持有交易成本更高的资产要求补偿。', citations=[])],
    narrative=['成交稀薄时价格冲击大', 'ILLIQ升高', '投资者要求更高预期收益作为补偿', '高ILLIQ股票未来收益更高'],
    expected_direction='positive', direction_reason='流动性补偿。', conditions='市场整体流动性正常时。',
    data_implications='A股日频250日窗口替代年度平均；成交额为千元人民币，比例常数不影响秩相关。',
    alternative_explanations=['小市值效应'], failure_regimes=['流动性危机中高ILLIQ股票先受冲击'],
    next_tests=['控制市值后检验'], mechanism_clarity='tentative')
DESIGN = {'design': {'summary': 'operator reference ILLIQ', 'missing_dsl_capabilities': ['amount field'], 'algorithm_steps': ['mean'],
                     'window_semantics': '250 rows', 'nan_policy': 'propagate'}, 'source': OPERATOR_ILLIQ}


# ---------------------------------------------------------------- library
@pytest.fixture
def library(tmp_path):
    from research_agent.paper_library import PaperLibrary
    return PaperLibrary(tmp_path / 'papers')


def stage(library, source, data=None):
    target = library.root / 'incoming' / ('up-' + os.urandom(4).hex())
    if data is not None:
        target.write_bytes(data)
    else:
        shutil.copyfile(source, target)
    return target


def test_import_dedupe_versions_and_discovery(library):
    a = library.import_pdf(stage(library, FIX / 'amihud2002.pdf'), 'D:\\Papers\\Amihud 2002 非流动性.pdf')
    assert a['duplicate'] is False and a['pages'] > 10 and a['name'] == 'Amihud 2002 非流动性.pdf' and a['version'] == 1
    again = library.import_pdf(stage(library, FIX / 'amihud2002.pdf'), 'other name.pdf')
    assert again['duplicate'] is True and len(library.entries()) == 1           # same bytes, stored once
    time.sleep(1.1)
    b = library.import_pdf(stage(library, FIX / 'gh4-paper.pdf'), 'Amihud 2002 非流动性.pdf')
    assert b['version'] == 2 and b['sha256'] != a['sha256']                    # same name, new bytes: new version
    assert library.resolve('刚上传的')['paper']['sha256'] == b['sha256']
    assert library.resolve('')['paper']['sha256'] == b['sha256']
    assert library.resolve(a['sha256'][:10])['paper']['sha256'] == a['sha256']
    amb = library.resolve('Amihud')
    assert amb['status'] == 'AMBIGUOUS' and len(amb['candidates']) == 2 and 'sha256' not in amb['candidates'][0]
    assert library.resolve('nonexistent paper xyz')['status'] == 'NOT_FOUND'
    gh = library.resolve('读取George和Hwang那篇论文')                         # authors live on page one, not in the file name
    assert gh['status'] == 'FOUND' and gh['paper']['sha256'] == b['sha256']
    assert library.resolve('52-week high 那篇')['paper']['sha256'] == b['sha256']
    assert sorted(p.name for p in (library.root / 'files').iterdir()) == sorted([a['sha256'] + '.pdf', b['sha256'] + '.pdf'])
    assert not list((library.root / 'incoming').iterdir())                       # no half-finished files


@pytest.mark.parametrize('payload,code', [(b'', 'PDF_EMPTY'), (b'hello world, not a pdf', 'NOT_A_PDF'),
                                          (b'%PDF-1.4\n' + b'garbage' * 200, 'PDF_UNREADABLE')])
def test_bad_files_are_refused_and_removed(library, payload, code):
    from research_agent.paper_library import PaperError
    with pytest.raises(PaperError) as exc:
        library.import_pdf(stage(library, None, payload), 'x.pdf')
    assert exc.value.code == code and not list((library.root / 'incoming').iterdir()) and library.entries() == []


def test_encrypted_and_oversized_pdfs(library, monkeypatch):
    import fitz
    from research_agent import paper_library
    doc = fitz.open(str(FIX / 'gh4-paper.pdf'))
    encrypted = library.root / 'incoming' / 'enc'
    doc.save(str(encrypted), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='u', owner_pw='o')
    with pytest.raises(paper_library.PaperError) as exc:
        library.import_pdf(encrypted, 'enc.pdf')
    assert exc.value.code == 'PDF_ENCRYPTED'
    monkeypatch.setattr(paper_library, 'MAX_BYTES', 1000)
    with pytest.raises(paper_library.PaperError) as exc:
        library.import_pdf(stage(library, FIX / 'gh4-paper.pdf'), 'big.pdf')
    assert exc.value.code == 'PDF_TOO_LARGE'


def test_traversal_names_and_paths_are_neutralised(library, tmp_path):
    from research_agent.paper_library import PaperError, safe_name
    assert safe_name('../../etc/passwd.pdf') == 'passwd.pdf' and safe_name('a\x00b\u202e.pdf') == 'ab.pdf'
    outside = tmp_path / 'outside.pdf'
    shutil.copyfile(FIX / 'gh4-paper.pdf', outside)
    with pytest.raises(PaperError):
        library.import_pdf(outside, 'x.pdf')                                     # only the trusted incoming directory
    if os.name == 'posix':
        link = library.root / 'incoming' / 'link'
        link.symlink_to(outside)
        with pytest.raises(PaperError):
            library.import_pdf(link, 'x.pdf')


# ---------------------------------------------------------------- natural-language flow with both gates
class PaperProvider(MockProvider):
    transport = type('LiveDouble', (), {'is_live': True})()   # test double reports live so the rationale path runs

    def __init__(self, decisions, factor=''):
        super().__init__()
        self.decisions = iter(decisions)
        self.queues = {'understanding': [LIVE['amihud_understanding']], 'repair': [LIVE['amihud_repair_1'], canonical(GOOD_REPAIR)],
                       'rationale': [canonical(RATIONALE)], 'design': [canonical(DESIGN)]}
        self.calls = []
        self.factor = factor

    def complete(self, request):
        self.calls.append(request)
        schema = request.output_schema or {}
        if 'research_goal' in schema.get('properties', {}):
            return next(self.decisions)
        if request.tools:
            names = {t.name for t in request.tools}
            if 'qrtk_paper_research' in names:
                return ModelResponse(tool_calls=(ToolCall('paper%d' % len(self.calls), 'qrtk_paper_research',
                                                          {'paper': '刚上传的', 'factor': self.factor}),))
            return ModelResponse(tool_calls=(ToolCall('list%d' % len(self.calls), 'paper_list', {}),))
        if paper_call(request) and 'You update ONE quantitative factor definition' in request.messages[0].content:
            return ModelResponse(canonical({'intent': 'none'}))   # the edit reader: this double's users never edit
        if schema == {'type': 'object'} or paper_call(request):
            system = request.messages[0].content
            text = request.messages[-2 if paper_call(request) else -1].content    # skip the trailing JSON rule
            if 'Write its formula at observation date t' in text:
                # independent second reading of the unreadable printed ILLIQ formula: the same definition, written afresh
                live = json.loads(LIVE['amihud_understanding'])
                return ModelResponse(canonical({"formula_latex": GOOD_REPAIR["formula_latex"], "parameters": [],
                                                "symbols": live["factors"][0]["symbols"]}))
            kind = ('rationale' if '实证资产定价研究员' in system else 'design' if 'implementing one quantitative factor' in system
                    else 'repair' if 'does not parse' in text else 'understanding')
            return ModelResponse(self.queues[kind].pop(0))
        done = any(x.role == Role.TOOL for x in request.messages)
        return ModelResponse(canonical(dict(action='complete' if done else 'continue', hypothesis='论文因子', change_reason='论文研究',
                                            summary='论文因子的探索性研究结果。', definition_change='')))


def paper_call(request):
    """paper_agent calls reach the runtime without a schema; ask_json parses them and the JSON rule ends the request."""
    from research_agent.paper_tools import JSON_RULE
    return not request.tools and not request.output_schema and request.messages[-1].content == JSON_RULE


def decision(action='reply', reply='', skill_id='', goal='', consent=''):
    return ModelResponse(canonical(dict(action=action, reply=reply, skill_id=skill_id, research_goal=goal, reason='测试',
                                        definition_change='', consent=consent)))


def research_chat(tmp_path, decisions, *, upload=True):
    fx = build(tmp_path)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    if upload:
        lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = PaperProvider(decisions)
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    import research_agent.quant as quant
    client, _ = broker(fx)
    return app, provider, fx, lib, client


def studies(fx):
    return [p for p in (fx['workspace'] / 'research_runs').rglob('manifest.json')]


@pytest.fixture
def patched_rolling(monkeypatch):
    holder = {}
    from research_agent import rolling_client

    def from_env(cls):
        return holder.get('client') or cls()
    monkeypatch.setattr(rolling_client.RollingClient, 'from_environment', classmethod(from_env))
    return holder


@pytest.fixture
def model_code_route(monkeypatch):
    """Since 2026-10-14 an IR-expressible paper factor runs on the reviewed trusted IR executor (no model code). The code
    approval machinery stays for algorithms the IR cannot express; these tests force that route to keep it covered."""
    import paper_agent.planner as planner
    from paper_agent.ledger import sha256_obj
    real = planner.plan

    def forced(*a, **k):
        p, task, spec = real(*a, **k)
        if p['route'] == 'trusted_ir':
            p['route'] = 'new_algorithm'
            p['definition_sha256'] = sha256_obj({x: p[x] for x in ('factor', 'mode', 'route', 'ir_execution', 'symbol_map', 'choices')})
        return p, task, spec
    monkeypatch.setattr(planner, 'plan', forced)


@pytest.mark.usefixtures("amihud_250_carrier")
def test_upload_then_one_sentence_research_runs_on_the_trusted_executor(tmp_path, patched_rolling):
    """One definition gate; no model-written code exists or runs; the executor is checked against the reference evaluator."""
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    decisions = [decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept')]
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = PaperProvider(decisions)
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    first = app.turn('研究我刚上传的论文。')
    assert '回复“同意”' in first and '250' in first and '时间轴说明' in first and not studies(fx)
    second = app.turn('同意，按这个口径探索性研究。')
    assert 'Test（2026滚动暴露评价' in second and '论文：Amihud_2002.pdf' in second and 'def compute' not in second
    assert not (tmp_path / 'papers/approved_code/approvals').exists() or not list((tmp_path / 'papers/approved_code/approvals').iterdir())
    task_id = app.store.session_turns(app.session_id)[-1]['research_task_id']
    data = next(e['result']['data'] for e in app.store.load(task_id).experiments if e['tool'] == 'qrtk_paper_research')
    assert data['paper']['route'] == 'trusted_ir' and data['metrics']['professional']['test']['evaluation_type'] == 'ROLLING_EXPOSED_TEST'
    cross = data['implementation_crosscheck']
    assert cross and all(c['checked_against'].startswith('factor_ir.evaluate') and c['cells_outside_tolerance'] == 0
                         and c['nan_pattern_mismatch'] == 0 and c['non_nan_cells'] > 0 for c in cross)
    pd_rec = data['paper_definition']
    assert pd_rec['executed']['timeline'] and pd_rec['asset']['decision'] == 'EQUITY_STOCK_COMPATIBLE'
    html = Path(data['html_path']).read_text(encoding='utf-8')
    assert '论文定义核验' in html and '核验清单' in html and '执行器×参考求值器逐格核对' in html
    assert json.loads((Path(data['report_artifact_path']) / 'data/report_consistency.json').read_text())['status'] == 'PASSED'


@pytest.mark.usefixtures("amihud_250_carrier")
def test_upload_then_one_sentence_research_with_both_gates(tmp_path, patched_rolling, model_code_route):
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    decisions = [decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept'), decision(consent='accept')]
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = PaperProvider(decisions)
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    first = app.turn('研究我刚上传的论文。')
    assert '回复“同意”' in first and '250' in first and not studies(fx)            # substitutions shown, nothing computed
    second = app.turn('同意，按这个口径探索性研究。')
    assert '回复“同意”即批准运行这一份代码' in second and 'def compute(panels)' in second and not studies(fx)
    assert '代码指纹' in second and '不是操作系统沙箱' in second
    session = app.store.session(app.session_id)
    pending = session['pending_code_approval']
    third = app.turn('同意')
    assert 'Test（2026滚动暴露评价' in third and '论文：Amihud_2002.pdf' in third and '经你批准的新算法' in third
    approval = json.loads(next((tmp_path / 'papers/approved_code/approvals').iterdir()).read_text())
    assert approval['channel'] == 'chat_user_turn' and approval['user_words'] == '同意' and approval['source_sha256'] == pending['source_sha256']
    entry = json.loads(next((tmp_path / 'papers/approved_code/entries').iterdir()).read_text())
    assert entry['status'] == 'TRUSTED_REGISTERED' and all(t['passed'] for t in entry['tests'])
    # The user never typed an ID, SHA, tool or skill name.
    assert not any(x in t for t in ('研究我刚上传的论文。', '同意，按这个口径探索性研究。', '同意') for x in ('sha', 'SHA', 'APPROVE', 'qrtk_'))
    # Report: three stages, economic rationale, consistency.
    task_id = app.store.session_turns(app.session_id)[-1]['research_task_id']
    data = next(e['result']['data'] for e in app.store.load(task_id).experiments if e['tool'] == 'qrtk_paper_research')
    assert data['metrics']['professional']['test']['evaluation_type'] == 'ROLLING_EXPOSED_TEST'
    assert data['economic_rationale']['status'] == 'CHECKED' and data['paper']['route'] == 'new_algorithm'
    assert data['implementation_crosscheck'] and all(c['cells_outside_tolerance'] == 0 and c['nan_pattern_mismatch'] == 0 for c in data['implementation_crosscheck'])
    assert json.loads((Path(data['report_artifact_path']) / 'data/report_consistency.json').read_text())['status'] == 'PASSED'
    # Re-reading the same paper reuses the cached understanding: no new understanding call (1 reading + 2 formula repairs
    # + 1 independent second reading of the unreadable printed ILLIQ formula, all made once).
    assert len([c for c in provider.calls if paper_call(c) and 'careful quantitative-finance research reader' in c.messages[0].content]) == 4


@pytest.mark.usefixtures("amihud_250_carrier")
def test_rejection_unclear_ambiguity_and_expiry_never_execute(tmp_path, patched_rolling, model_code_route):
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    goal = '研究我刚上传的论文'
    provider = PaperProvider([decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept'),
                              decision(consent='accept'), decision(consent='accept'), decision(consent='reject')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    app.turn('同意')
    assert app.store.session(app.session_id)['pending_code_approval']
    unclear = app.turn('这段代码看起来还行吧')            # the model says accept, the user's words are not explicit
    assert '尚未运行新代码' in unclear and not studies(fx)
    session = app.store.session(app.session_id)
    session['pending_code_approval']['expires_at'] = time.time() - 1
    app.store.save_session(session)
    expired = app.turn('同意')
    assert not studies(fx) and app.store.session(app.session_id)['pending_code_approval'] is None
    assert not list((tmp_path / 'papers/approved_code/approvals').iterdir())
    refused = app.turn('拒绝')
    assert not studies(fx) and not list((tmp_path / 'papers/approved_code/approvals').iterdir())


@pytest.mark.usefixtures("amihud_250_carrier")
def test_rejecting_the_code_records_a_block(tmp_path, patched_rolling, model_code_route):
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    provider = PaperProvider([decision('skill', skill_id='paper_research', goal='研究我刚上传的论文'), decision(consent='accept'),
                              decision(consent='reject')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    app.turn('同意')
    answer = app.turn('拒绝，不要运行这段代码')
    assert '已拒绝运行这段新代码' in answer and not studies(fx)
    events = [e['kind'] for t in app.store.session_turns(app.session_id) for e in app.store.events(t['route_task_id'])]
    assert 'CODE_APPROVAL_REJECTED' in events


def test_ambiguous_open_objects_authorize_nothing(tmp_path, patched_rolling):
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    provider = PaperProvider([decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    session = app.store.session(app.session_id)
    session['pending_definition'] = dict(id='p' * 32, change='x', description='y', tool='qrtk_paper_research', arguments={}, definition_sha256='0' * 64)
    session['pending_code_approval'] = dict(id='c' * 32, what='x', source_sha256='a' * 64, expires_at=time.time() + 600)
    app.store.save_session(session)
    answer = app.turn('同意')
    assert '无法确定对象' in answer and not studies(fx)


@pytest.mark.parametrize("words", ['同意', '同意，按这个口径探索性研究。', '可以，用股票吧', '好的继续'])
def test_an_asset_substitution_is_not_unlocked_by_ordinary_consent(tmp_path, patched_rolling, words):
    """Futures/options -> A-share stocks needs the user's exact phrase; '同意' or paraphrases run nothing."""
    from paper_agent.planner import ASSET_PHRASE
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    provider = PaperProvider([decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    session = app.store.session(app.session_id)
    session['pending_definition'] = dict(id='p' * 32, change='资产替代', description='期货 -> A股', tool='qrtk_paper_research', arguments={},
                                         definition_sha256='0' * 64, skill_id='paper_research', research_goal='研究AQR论文',
                                         required_phrase=ASSET_PHRASE)
    app.store.save_session(session)
    answer = app.turn(words)
    assert ASSET_PHRASE in answer and '尚未执行' in answer and not studies(fx)
    assert app.store.session(app.session_id)['pending_definition'] is not None          # still waiting, nothing confirmed


def test_the_exact_asset_phrase_confirms_even_when_the_model_reads_no_consent(tmp_path):
    import sqlite3
    from paper_agent.planner import ASSET_PHRASE
    fx = build(tmp_path)
    app = build_chat(tmp_path / 'state', provider=PaperProvider([decision(consent='')]), profile='development',
                     resources_manifest=fx['manifest'], research_config=fx['config'])
    session = app.store.session(app.session_id)
    session['pending_definition'] = dict(id='p' * 32, change='资产替代', description='期货 -> A股', tool='qrtk_paper_research', arguments={},
                                         definition_sha256='0' * 64, skill_id='paper_research', research_goal='研究AQR论文',
                                         required_phrase=ASSET_PHRASE)
    app.store.save_session(session)
    app.turn(ASSET_PHRASE)
    kinds = [k for k, in sqlite3.connect(str(tmp_path / 'state' / 'research.sqlite3')).execute(
        "select kind from events where kind like 'DEFINITION%'")]
    assert kinds == ['DEFINITION_CHANGE_CONFIRMED'] and app.store.session(app.session_id)['pending_definition'] is None


def test_changed_code_is_not_covered_by_an_old_approval(tmp_path):
    from paper_agent.registry import TrustedRegistry
    reg = TrustedRegistry(tmp_path / 'reg', channels=('chat_user_turn',))
    assert reg.registered('a' * 64) is None                                      # approvals are per exact SHA


def test_list_and_ambiguous_paper_requests_answer_without_model_reading(tmp_path, patched_rolling):
    fx = build(tmp_path)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    provider = PaperProvider([decision('skill', skill_id='paper_research', goal='研究我刚上传的论文')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')                                              # empty library
    assert not any(paper_call(c) or (c.output_schema or {}) == {'type': 'object'} for c in provider.calls)
    task_id = app.store.session_turns(app.session_id)[-1]['research_task_id']
    data = next(e['result']['data'] for e in app.store.load(task_id).experiments if e['tool'] == 'qrtk_paper_research')
    assert data['paper_status'] == 'NO_PAPERS'
    assert app.store.load(task_id).status == 'COMPLETED'                       # a catalog answer is an accepted result


def test_cli_paper_import_and_list(tmp_path):
    from research_agent.cli import main
    fx = build(tmp_path)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    incoming = stage(lib, FIX / 'gh4-paper.pdf')
    name = base64.urlsafe_b64encode('52周高点 George & Hwang.pdf'.encode()).decode().rstrip('=')
    assert main(['--research-config', str(fx['config']), 'paper-import', str(incoming), name]) == 0
    assert lib.entries()[0]['name'] == '52周高点 George & Hwang.pdf'
    assert main(['--research-config', str(fx['config']), 'paper-list']) == 0


def test_template_placeholders_and_stamps_are_not_paper_titles():
    """Live 2026-10-13 uploads showed 'Paper Title (use style: paper title)', an arXiv stamp and a bare '研究报告' as titles."""
    from research_agent.paper_library import TITLE_ARTEFACT
    for artefact in ('Paper Title (use style: paper title)', 'arXiv:cond-mat/0212641v1  [cond-mat.stat-mech]  31 Dec 2002',
                     '研究报告', 'Microsoft Word - draft.docx', 'PII: S1386-4181(01)00024-6'):
        assert TITLE_ARTEFACT.search(artefact), artefact
    for title in ('Detailed study of a moving average trading rule', 'Option Momentum', '华泰证券研究报告：量化月报',
                  'A comparative study of the MACD-base trading'):
        assert not TITLE_ARTEFACT.search(title), title


def test_blocked_papers_explain_their_hard_stops_in_chinese():
    """Live Q1/Q2: the model said it had no details of a block; the program now writes the reason itself."""
    from research_agent.paper_tools import blocked_text
    text = blocked_text(dict(name='2206.12282 MACD strategies.pdf', factor='MACD', factors=['MACD', 'RSI'],
                             hard_stops=[dict(code='FIELD_NOT_AVAILABLE', symbol='EMA', detail="needs None; published fields ['close']"),
                                         dict(code='FORMULA_NOT_ESTABLISHED', symbol=None, detail='no verified formula'),
                                         dict(code='ADMISSION_FIELDS', detail='x')]))
    assert 'FIELD_NOT_AVAILABLE（EMA）' in text and '已发布：开高低收、成交量、成交额' in text and '数据准入检查未通过' in text
    assert '论文中还识别到：RSI' in text and '没有执行任何计算' in text


def test_a_title_match_beats_a_body_text_match_and_ambiguity_lists_candidates(tmp_path):
    """Live Q4: 'moving average' tied the MA paper (title) with the MACD paper (page-one text); no candidates were shown."""
    from research_agent.paper_library import PaperLibrary
    from research_agent.paper_tools import candidates_text
    lib = PaperLibrary(tmp_path / 'papers')
    base = dict(version=1, pages=30, status='REGISTERED', bytes=1)
    rows = [dict(base, sha256='a' * 64, name='ferreira_silva_yen_2019_ma_rule.pdf', title='Detailed study of a moving average trading rule',
                 heading='Detailed study of a moving average trading rule', uploaded_at='2026-10-13T14:58:21+08:00'),
            dict(base, sha256='b' * 64, name='2206.12282 MACD strategies.pdf', title='A comparative study of the MACD-base trading',
                 heading='A comparative study of the MACD-based trading: Moving Average Convergence Divergence', uploaded_at='2026-10-13T23:15:16+08:00')]
    lib._save(rows)
    hit = lib.resolve('moving average（移动平均）那篇论文')
    assert hit['status'] == 'FOUND' and hit['paper']['sha256'] == 'a' * 64
    both = lib.resolve('study trading')                                       # equal title matches: still ambiguous
    assert both['status'] == 'AMBIGUOUS' and len(both['candidates']) == 2
    text = candidates_text('AMBIGUOUS', both['candidates'])
    assert 'ferreira_silva_yen_2019_ma_rule.pdf' in text and '2206.12282 MACD strategies.pdf' in text and '请说出' in text


@pytest.mark.usefixtures("amihud_250_carrier")
def test_a_lost_review_request_is_reported_and_rebuilt_without_running_code(tmp_path, patched_rolling, model_code_route):
    """Live Q5: a cached candidate had no registry request (copied paper ledger); approval failed and was mislabelled as
    failed known-truth tests. Now the failure is named, and the next research turn rebuilds the request (fresh static review)."""
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    from research_agent.paper_library import PaperLibrary
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    goal = '研究我刚上传的论文'
    provider = PaperProvider([decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept'),
                              decision(consent='accept'), decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept'),
                              decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=provider, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    assert '回复“同意”即批准运行这一份代码' in app.turn('同意')
    reg = tmp_path / 'papers/approved_code'
    for sub in ('requests', 'sources'):
        for p in (reg / sub).iterdir():
            p.unlink()
    lost = app.turn('同意')
    assert '审核登记表中没有这份代码的有效审核请求' in lost and '真值测试未通过' not in lost and not studies(fx)
    again = app.turn('研究我刚上传的论文。')          # a later request in the session: the definition is shown first
    assert '回复“同意”' in again and not studies(fx)
    again = app.turn('同意')
    assert '回复“同意”即批准运行这一份代码' in again and len(list((reg / 'requests').iterdir())) == 1
    done = app.turn('同意')
    assert '经你批准的新算法' in done and studies(fx)
    entry = json.loads(next((reg / 'entries').iterdir()).read_text())
    assert entry['status'] == 'TRUSTED_REGISTERED' and all(t['passed'] for t in entry['tests'])
