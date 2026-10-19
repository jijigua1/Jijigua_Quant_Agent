"""Canonical research definitions, their registry and reuse (2026-10-16). Synthetic panels and real staging evidence;
no model call is made except through the scripted test providers."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from paper_agent.canonical import canonical_ir, classify, definition, factor_key, sha  # noqa: E402
from paper_agent.definitions import DefinitionRegistry, RegistryError  # noqa: E402
from paper_research.factor_ir import parse_formula  # noqa: E402

GH = r"F = \frac{P_{i,t}}{\max_{0 \le k \le 251} P_{i,t-k}}"


def plan_of(latex, field="close", *, horizon=10, rows=21, lag=0, asset="EQUITY_STOCK_COMPATIBLE", consent=False, route="trusted_ir",
            factor="52-week high measure", kinds=("frequency_conversion",)):
    ir = parse_formula(latex)["ir"]
    return {"factor": factor, "status": "AWAITING_USER_DECISION", "route": route, "ir_execution_json": ir, "ir_execution": latex,
            "symbol_map": {"P": {"field": field, "adjustment": "none"}, "H": {"field": "high", "adjustment": "none"}},
            "choices": {"time_unit_rows": {"rows": rows}, "label_lag": 1, "horizon": {"n": horizon}},
            "assets": {"decision": asset}, "asset_consent_required": consent, "paper_frequency": "monthly",
            "substitutions": [{"kind": k, "item": k} for k in kinds], "hard_stops": [], "definition_sha256": "x"}


def task_of(lag=0):
    return {"factor": {"symbols": [], "timing": {"common_lag_removed": lag}, "definition_evidence": []}}


def canon(latex, *, params=(), **kw):
    p = plan_of(latex, **{k: v for k, v in kw.items() if k != "lag"})
    u = {"factors": [{"name": p["factor"], "parameters": list(params)}]}
    rec, digest = definition(p, task_of(kw.get("lag", 0)), u, paper={"sha256": "a" * 64, "name": "gh.pdf", "version": 1})
    return rec


# ------------------------------------------------------------------ identity: wording never changes the SHA
def test_wording_symbol_names_and_disclosure_lines_do_not_change_the_definition():
    a = canon(GH, factor="52-week high measure (ratio of current price to 52-week high)", kinds=("formula_restatement",))
    b = canon(GH.replace("P_", "Q_").replace("P_{", "Q_{"), factor="nearness to the 52-week high", kinds=("price_basis",))
    b2 = canon(r"G = \frac{Q_{i,t}}{\max_{0 \le j \le 251} Q_{i,t-j}}", factor="FHH")
    for x in (b, b2):
        x_plan_fields = x["math"]
    assert a["definition_sha256"] == canon(GH, factor="FHH")["definition_sha256"]
    # symbol names map to fields; a different symbol letter with the same field mapping is the same definition
    p = plan_of(r"G = \frac{Q_{i,t}}{\max_{0 \le j \le 251} Q_{i,t-j}}")
    p["symbol_map"] = {"Q": {"field": "close", "adjustment": "none"}}
    rec, _ = definition(p, task_of(), {"factors": [{"name": p["factor"], "parameters": []}]},
                        paper={"sha256": "a" * 64, "name": "gh.pdf", "version": 1})
    assert rec["definition_sha256"] == a["definition_sha256"]


def test_equivalent_expressions_are_class_a_and_real_differences_are_class_c():
    base = canon(r"F = \frac{1}{21} \sum_{k=0}^{20} (P_{i,t-k} - P_{i,t-k-21})")
    commuted = canon(r"F = \frac{1}{21} \sum_{k=0}^{20} (-P_{i,t-k-21} + P_{i,t-k})")
    scaled = canon(r"F = \frac{\sum_{k=0}^{20} (P_{i,t-k} - P_{i,t-k-21})}{21}")
    assert classify(base, scaled) == "A_EQUIVALENT"                    # different SHA, the same numbers
    assert classify(base, commuted) in ("SAME", "A_EQUIVALENT")
    gh = canon(GH)
    assert classify(gh, canon(GH.replace("251", "252"))) == "C_SEMANTIC"        # 252 vs 253 prices
    assert classify(gh, canon(GH.replace("251", "272"))) == "C_SEMANTIC"        # 12 vs 13 months
    assert classify(gh, canon(GH, field="high")) == "C_SEMANTIC"                # closing vs intraday high series
    assert classify(gh, canon(r"F = \frac{P_{i,t-21}}{\max_{0 \le k \le 251} P_{i,t-21-k}}")) == "C_SEMANTIC"  # one month stale
    assert classify(gh, canon(GH, consent=True, asset="ASSET_CLASS_NOT_AVAILABLE")) == "C_SEMANTIC"   # another asset contract
    assert classify(gh, canon(GH, horizon=5)) == "C_SEMANTIC"                   # another label
    assert classify(gh, None) == "D_ENGINEERING"


def test_user_parameters_and_semantics_versions_are_part_of_the_identity():
    rsi = r"F = \operatorname{mean}_{k=0}^{13}(\max(P_{i,t-k} - P_{i,t-k-1}, 0))"
    x14 = canon(rsi, params=[{"symbol": "X", "value": 14, "status": "USER"}])
    x14b = canon(rsi, params=[{"symbol": "N", "value": 14, "status": "USER"}])
    x20 = canon(rsi.replace("13", "19"), params=[{"symbol": "X", "value": 20, "status": "USER"}])
    assert x14["definition_sha256"] == x14b["definition_sha256"]              # the symbol letter is wording
    assert x14["definition_sha256"] != x20["definition_sha256"]
    paper_14 = canon(rsi, params=[{"symbol": "X", "value": 14, "status": "PAPER"}])
    assert paper_14["definition_sha256"] != x14["definition_sha256"]          # a user choice is a different contract
    p = plan_of(GH)
    u = {"factors": [{"name": p["factor"], "parameters": []}]}
    v1, _ = definition(p, task_of(), u, paper={"sha256": "a" * 64, "name": "x", "version": 1}, semantics="trusted-ir-semantics/1")
    v2, _ = definition(p, task_of(), u, paper={"sha256": "a" * 64, "name": "x", "version": 1})
    assert v1["definition_sha256"] != v2["definition_sha256"]


def test_macd_parameters_and_numbered_factors():
    macd = r"F = \operatorname{ema}_{12}(P_{i,t}) - \operatorname{ema}_{26}(P_{i,t})"
    assert canon(macd)["definition_sha256"] != canon(macd.replace("26", "35"))["definition_sha256"]
    assert factor_key("Alpha#12", "研究101 Formulaic Alphas那篇论文里的Alpha#12") == "alpha#12"
    assert factor_key("Alpha#1", "Alpha#1") == "alpha#1" != factor_key("Alpha#101", "Alpha#101")


def test_canonical_ir_ignores_variable_names_and_time_labels():
    a = canonical_ir(parse_formula(r"F = \operatorname{mean}_{k=0}^{19}(P_{i,t-k})")["ir"], {"P": "close"})
    b = canonical_ir(parse_formula(r"F = \operatorname{mean}_{j=0}^{19}(C_{i,t-j})")["ir"], {"C": "close"})
    assert sha(a) == sha(b)


# ------------------------------------------------------------------ registry: approval scope, freezing, reuse, invalidation
def registry_with(tmp_path, rec, status="AWAITING_USER_DECISION", params=None, session="s1"):
    reg = DefinitionRegistry(tmp_path)
    reg.propose(rec, plan_status=status, user_params=params or {}, session_id=session,
                sources={"understanding": {}, "plan": {}, "task": {}})
    return reg


def test_an_approval_belongs_to_one_definition_and_its_scope(tmp_path):
    gh = canon(GH)
    reg = registry_with(tmp_path, gh)
    sha_ = gh["definition_sha256"]
    assert reg.get(sha_)["status"] == "APPROVAL_REQUIRED" and not reg.approved(sha_)
    with pytest.raises(RegistryError):
        reg.freeze(sha_, needs_approval=True)                                  # never executed without the decision
    reg.approve(sha_, session_id="s1", task_id="t", substitutions=[], asset_phrase=False)
    assert reg.approved(sha_) and not reg.approved(sha_, asset_consent_required=True)   # no asset phrase was given
    other = canon(GH.replace("251", "272"))
    reg.propose(other, plan_status="AWAITING_USER_DECISION", user_params={}, session_id="s2")
    assert not reg.approved(other["definition_sha256"])                         # an approval never moves to another SHA
    reg.freeze(sha_, needs_approval=True)
    reg.executed(sha_, {"study_id": "s", "execution_sha256": "e"})
    assert reg.get(sha_)["status"] == "EXECUTED" and reg.verify_chain()


def test_reuse_needs_the_same_paper_factor_and_this_sessions_values(tmp_path):
    x14 = canon(r"F = \operatorname{mean}_{k=0}^{13}(P_{i,t-k})", params=[{"symbol": "X", "value": 14, "status": "USER"}])
    x14["display"]["factor"] = "Relative Strength Index (RSI)"
    reg = registry_with(tmp_path, x14, params={"X": 14})
    s = x14["definition_sha256"]
    reg.approve(s, session_id="s1", task_id="t", substitutions=[], asset_phrase=False)
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="RSI", user_params={"X": 14})["definition_sha256"] == s
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="RSI", user_params={}) is None        # no X typed now
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="RSI", user_params={"X": 20}) is None
    assert reg.reusable(paper_sha256="b" * 64, requested_factor="RSI", user_params={"X": 14}) is None
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="MACD", user_params={"X": 14}) is None


def test_numbered_factors_never_reuse_another_number(tmp_path):
    a12 = canon(r"F = P_{i,t} - P_{i,t-1}", factor="Alpha#12")
    a12["factor_key"] = "alpha#12"
    reg = registry_with(tmp_path, a12, status="READY")
    reg.freeze(a12["definition_sha256"], needs_approval=False)
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="Alpha#12", user_params={})
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="Alpha#1", user_params={}) is None
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="Alpha#101", user_params={}) is None


def test_invalidated_and_superseded_definitions_are_never_reused(tmp_path):
    gh = canon(GH)
    reg = registry_with(tmp_path, gh, status="READY")
    s = gh["definition_sha256"]
    reg.freeze(s, needs_approval=False)
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="", user_params={})
    reg.invalidate(s, code="DEFINITION_SEMANTICS_WRONG", reason="test", evidence=["x"], recorded_by="qa")
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="", user_params={}) is None
    with pytest.raises(RegistryError):
        reg.freeze(s, needs_approval=False)
    with pytest.raises(RegistryError):
        reg.approve(s, session_id="s", task_id="t", substitutions=[], asset_phrase=False)
    other = canon(GH.replace("P_{", "P_{")) if False else canon(GH, horizon=5)
    reg.propose(other, plan_status="READY", user_params={}, session_id="s")
    reg.freeze(other["definition_sha256"], needs_approval=False)
    reg.supersede(other["definition_sha256"], "c" * 64, "program changed")
    assert reg.reusable(paper_sha256="a" * 64, requested_factor="", user_params={}) is None
    assert reg.get(other["definition_sha256"])["superseded_by"]["definition_sha256"] == "c" * 64
    lines = (tmp_path / "definitions" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["payload"]["x"] = 1
    lines[1] = json.dumps(tampered)
    (tmp_path / "definitions" / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        reg.verify_chain()


# ------------------------------------------------------------------ end to end: a new session reuses the frozen definition
from test_v1beta_papers import FIX, PaperProvider, decision, patched_rolling, stage  # noqa: E402,F401
from v1beta_fixtures import broker, build  # noqa: E402


@pytest.mark.usefixtures("amihud_250_carrier")
def test_a_new_session_reuses_the_frozen_definition_without_reading_again(tmp_path, patched_rolling):
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    first = PaperProvider([decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=first, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    done = app.turn('同意，按这个口径探索性研究。')
    assert '研究定义：' in done and '（已冻结）' in done
    second = PaperProvider([decision('skill', skill_id='paper_research', goal=goal)])
    second.queues['understanding'] = []                                   # any new reading would fail this test
    app2 = build_chat(tmp_path / 'state2', provider=second, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    assert app2.session_id != app.session_id
    out = app2.turn('研究我刚上传的论文。')
    assert '复用此前已确认并冻结的定义' in out and '回复“同意”' not in out
    regs = list((tmp_path / 'papers' / 'tasks').glob('*/definitions/events.jsonl'))
    kinds = [json.loads(l)['kind'] for l in regs[0].read_text(encoding='utf-8').splitlines()]
    assert kinds.count('APPROVED') == 1 and 'FROZEN' in kinds and kinds.count('EXECUTED') == 2


# ------------------------------------------------------------------ acceptance 1: every computing parameter is in the SHA
def test_no_collision_between_different_parameters_whatever_their_source():
    rsi = lambda n: rf"F = \operatorname{{mean}}_{{k=0}}^{{{n - 1}}}(\max(P_{{i,t-k}} - P_{{i,t-k-1}}, 0))"
    for src in ("PAPER", "USER"):
        a = canon(rsi(14), params=[{"symbol": "X", "value": 14, "status": src}])
        b = canon(rsi(20), params=[{"symbol": "X", "value": 20, "status": src}])
        assert a["definition_sha256"] != b["definition_sha256"] and classify(a, b) == "C_SEMANTIC"
    ema = lambda n: rf"F = \operatorname{{ema}}_{{{n}}}(P_{{i,t}})"
    e12, e26 = canon(ema(12)), canon(ema(26))
    assert e12["definition_sha256"] != e26["definition_sha256"] and classify(e12, e26) == "C_SEMANTIC"
    w = e12["math"]["windows"][0]
    assert w["op"] == "ema" and w["n"] == 12 and w["window"] and w["init"]       # span, truncation window and seed are hashed
    changed = copy.deepcopy(e12)
    changed["math"]["formula_ir"]["args"][0]["init"] = "mean"
    assert sha(changed["math"]) != e12["definition_sha256"]
    assert canon(GH)["math"]["conventions"] == "canonical-conventions/1"        # the system-default version is hashed


# ------------------------------------------------------------------ acceptance 3: approval scope never widens
def test_an_asset_substitution_approval_does_not_carry_to_another_contract(tmp_path):
    idx = canon(GH, consent=True, asset="ASSET_CLASS_NOT_AVAILABLE")
    reg = registry_with(tmp_path, idx)
    reg.approve(idx["definition_sha256"], session_id="s1", task_id="t", substitutions=[{"kind": "asset_substitution"}],
                asset_phrase=True)
    assert reg.approved(idx["definition_sha256"], asset_consent_required=True)
    other = canon(GH.replace("251", "125"), consent=True, asset="ASSET_CLASS_NOT_AVAILABLE")     # another research contract
    reg.propose(other, plan_status="AWAITING_USER_DECISION", user_params={}, session_id="s2")
    assert not reg.approved(other["definition_sha256"], asset_consent_required=True)
    plain = canon(GH)                                                            # the same formula without the substitution
    reg.propose(plain, plan_status="AWAITING_USER_DECISION", user_params={}, session_id="s2")
    assert not reg.approved(plain["definition_sha256"])


# ------------------------------------------------------------------ acceptance 4: state machine, chain, idempotency
def test_proposals_and_repeated_executions_are_idempotent_and_chained(tmp_path):
    gh = canon(GH)
    reg = registry_with(tmp_path, gh, status="READY")
    s = gh["definition_sha256"]
    reg.propose(gh, plan_status="READY", user_params={}, session_id="s1")          # same session again: no new event
    reg.propose(gh, plan_status="READY", user_params={}, session_id="s2")          # another session: recorded, not duplicated
    assert reg.get(s)["proposed_in_sessions"] == ["s1", "s2"]
    reg.freeze(s, needs_approval=False)
    reg.freeze(s, needs_approval=False)                                             # freezing twice changes nothing
    reg.executed(s, {"study_id": "a", "execution_sha256": "e1"})
    reg.executed(s, {"study_id": "a", "execution_sha256": "e1"})                    # a re-run is recorded, the status stays
    rec = reg.get(s)
    assert rec["status"] == "EXECUTED" and len(rec["executions"]) == 2
    kinds = [json.loads(l)["kind"] for l in (tmp_path / "definitions/events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds == ["PROPOSED", "FROZEN", "EXECUTED", "EXECUTED"] and reg.verify_chain()


# ------------------------------------------------------------------ acceptance 5: JSON repair never changes text
def test_json_repair_only_moves_brackets_and_otherwise_fails_explicitly(tmp_path):
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ModelFailure, ScriptedClient, _bracket_repair, ask_json
    if not (Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_ready_replies.json').is_file():
        pytest.skip('Historical live model replies omitted from public release')
    live = json.loads((Path(__file__).parent / 'fixtures_v1beta' / 'live_20261015_ready_replies.json').read_text(encoding='utf-8'))
    raw = [r['raw_output'] for r in live['20261016_142232/D09'] if r['purpose'] == 'paper_understanding'][0]
    obj, fixes = _bracket_repair(raw)
    assert fixes == ['remove } at 1609']
    f = obj['factors'][0]
    assert f['formula_latex'] == r"FHH_{i,t} = \frac{P_{i,t-1}}{high_{i,t-1}}" and \
        f['formula_citations'][0]['quote'] == r"stocks are ranked based on \frac{P_{i,t-1}}{high_{i,t-1}}"
    assert _bracket_repair('{"formula": "a, "quote": "b"}') is None                # would need to change a string
    ledger = TaskLedger(tmp_path, goal='j', budget=dict(model_calls=5, total_tokens=10 ** 6, wall_seconds=10 ** 6,
                                                       design_revisions=1, orchestration_turns=0))
    bad = '{"formula": "a, "quote": "b"}'
    with pytest.raises(ModelFailure) as e:
        ask_json(ScriptedClient({'x': [bad, bad, bad]}), ledger, purpose='x', system='s', user='u',
                 schema={'type': 'object', 'required': ['formula']})
    assert 'SCHEMA_INVALID' in e.value.code


# ------------------------------------------------------------------ acceptance 8: one SHA means the same numbers
def test_readings_sharing_a_sha_compute_identical_numbers():
    """The 38 real readings: within every canonical SHA group, each pair is re-evaluated on the reference evaluator."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import tempfile
    import replay_canonical as R
    from paper_agent.canonical import equivalent
    data = json.loads(R.FIXTURE.read_text(encoding='utf-8'))
    groups = {}
    with tempfile.TemporaryDirectory() as td:
        for i, key in enumerate(sorted(data)):
            r = R.replay(key, data[key], Path(td) / str(i))
            if r.get('record') and r['status'] != 'BLOCKED':
                groups.setdefault(r['definition_sha256'], []).append(r['record']['math']['formula_ir'])
    checked = 0
    for irs in groups.values():
        for other in irs[1:]:
            cmp = equivalent(irs[0], other)
            assert cmp and cmp['agree'] and cmp['max_abs_diff'] == 0.0
            checked += 1
    # D02, D03u, D09 and two D04 definitions: the 10-17 run-1 reading named gold as futures (asset consent required),
    # a real contract difference (class C) with the same formula -- kept apart, never merged
    assert len(groups) == 5 and checked >= 30


@pytest.mark.usefixtures("amihud_250_carrier")
def test_the_study_and_its_report_revision_name_the_frozen_definition(tmp_path, patched_rolling):
    """Acceptance 6: registry execution -> study directory -> paper definition record -> report revision, one SHA."""
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    app = build_chat(tmp_path / 'state', provider=PaperProvider([decision('skill', skill_id='paper_research', goal=goal),
                                                                 decision(consent='accept')]),
                     profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    app.turn('同意，按这个口径探索性研究。')
    rec_path = next((tmp_path / 'papers' / 'tasks').glob('*/definitions/*.json'))
    rec = json.loads(rec_path.read_text(encoding='utf-8'))
    run = Path(rec['executions'][0]['artifact_path'])
    record = json.loads((run / 'code/paper_definition.json').read_text(encoding='utf-8'))
    assert record['canonical_definition_sha256'] == rec['definition_sha256']
    versions = json.loads((run / 'reports/report_versions.json').read_text(encoding='utf-8'))
    revision = Path(versions[-1]['html']).parents[1]
    assert json.loads((revision / 'code/paper_definition.json').read_text(encoding='utf-8'))['canonical_definition_sha256'] == rec['definition_sha256']


# ------------------------------------------------------------------ acceptance 3: an older program's approval is not carried over
@pytest.mark.usefixtures("amihud_250_carrier")
def test_a_legacy_plan_approval_does_not_authorize_the_new_definition(tmp_path, patched_rolling):
    """candidate4 and earlier stored 'accepted_plan_sha256' in the task ledger. After an upgrade that approval must not
    stand in for a registry approval: the user is asked again, nothing is executed and no definition is frozen."""
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    app = build_chat(tmp_path / 'state', provider=PaperProvider([decision('skill', skill_id='paper_research', goal=goal)]),
                     profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    asked = app.turn('研究我刚上传的论文。')
    assert '回复“同意”' in asked
    task = next((tmp_path / 'papers' / 'tasks').glob('*/state.json'))
    state = json.loads(task.read_text(encoding='utf-8'))
    events = task.parent / 'definitions' / 'events.jsonl'
    plan_sha = json.loads(next(task.parent.glob('definitions/*[0-9a-f].json')).read_text(encoding='utf-8'))['plan_sha256']
    state['accepted_plan_sha256'] = plan_sha                               # what the old program wrote on '同意'
    task.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    app2 = build_chat(tmp_path / 'state2', provider=PaperProvider([decision('skill', skill_id='paper_research', goal=goal)]),
                      profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    again = app2.turn('研究我刚上传的论文。')
    assert '回复“同意”' in again and '复用此前已确认' not in again
    kinds = [json.loads(l)['kind'] for l in events.read_text(encoding='utf-8').splitlines()]
    assert not {'APPROVED', 'FROZEN', 'EXECUTED'} & set(kinds)


# ------------------------------------------------------------------ live J1 2026-10-17 09:51: no approval without a definition
@pytest.mark.usefixtures("amihud_250_carrier")
def test_a_model_proposal_around_paper_research_never_becomes_an_approval_entry(tmp_path, patched_rolling):
    """The router answered “X=14” with action=propose. The generic gate held the paper tool and offered “同意” for a
    call with no executable definition (“冻结计划 ” with an empty plan SHA), and the confirmed run then read the parameter
    values from the word “同意”. Paper research is self-gated: the request runs as this turn's own, so the paper tool's
    own gate shows the exact definition, and no generic proposal is stored."""
    from research_agent.app import build_chat
    from research_agent.contracts import canonical as dumps
    from research_agent.llm import ModelResponse
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    propose = ModelResponse(dumps(dict(action='propose', reply='论文口径不可得，拟按用户参数研究。', skill_id='paper_research',
                                       research_goal=goal, reason='测试', consent='',
                                       definition_change='阻断：论文口径定义不可得，无法按用户指定参数计算；不提供替代计算。')))
    app = build_chat(tmp_path / 'state', provider=PaperProvider([propose]), profile='development',
                     resources_manifest=fx['manifest'], research_config=fx['config'])
    out = app.turn('研究我刚上传的论文。')
    import sqlite3
    with sqlite3.connect(tmp_path / 'state' / 'research.sqlite3') as db:
        events = [dict(kind=k, payload=json.loads(p)) for k, p in db.execute('select kind, payload from events order by sequence')]
    kinds = [e.get('kind') for e in events]
    assert 'DEFINITION_PROPOSAL_SELF_GATED' in kinds and 'DEFINITION_PROPOSAL_TASK' not in kinds
    assert '冻结计划 ' not in out and '受阻原因与拟议改变：阻断' not in out
    # the paper tool's own gate asked, with the program-rendered formula and its canonical definition
    assert '回复“同意”' in out and '实际执行' in out
    held = [e for e in events if e.get('kind') == 'DEFINITION_CHANGE_PROPOSED']
    assert held and all((h.get('payload') or {}).get('tool') == 'qrtk_paper_research' and
                        (h['payload'].get('arguments') or {}).get('plan_sha256') for h in held)


def test_staging_not_authorized_is_not_described_as_production():
    from research_agent.report_versions import ROLLING_REASONS
    text = ROLLING_REASONS['NOT_AUTHORIZED']
    assert '生产环境尚未授权' not in text and '本环境' in text and '未读取或计算任何2026数据' in text


# ------------------------------------------------------------------ live A/B 2026-10-17 and offline probes on real readings
def _replay(key, params, focus=None):
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import replay_canonical as rc
    rows = json.loads(rc.FIXTURE.read_text(encoding='utf-8'))[key]
    name, case_focus, _ = rc.CASES[key.split('/')[1].split('#')[0]]
    rc.CASES['PROBE'] = (name, focus if focus is not None else case_focus, params)
    with tempfile.TemporaryDirectory() as tmp:
        return rc.replay(key.split('/')[0] + '/PROBE', rows, Path(tmp))


def test_a_derived_symbol_without_definition_is_never_its_data_field():
    """Real reading (A/B 10-17 D03u run 1): RS 'average rises / average drops', kind derived, data_field close, no
    derivation. It was admitted as RSI = 100 - 100/(1 + close[t]); now it is not admitted."""
    r = _replay('20261017_094123/D03u', {'X': 14})
    assert r['status'] != 'AWAITING_USER_DECISION' or 'close' not in json.dumps(r['record']['math']['formula_ir'])
    assert r['status'] in ('BLOCKED', 'NEEDS_NEW_MODEL_CALL')      # the investigation round is asked for RS's definition


def test_a_typed_value_that_names_no_parameter_blocks_instead_of_being_ignored():
    r = _replay('20261015_140339/D02', {'N': 8})
    assert r['status'] == 'BLOCKED' and 'USER_PARAMETER_NOT_IN_DEFINITION' in r['hard_stops']


def test_user_values_over_paper_values_give_their_own_definition_and_say_so():
    base, over = _replay('20261015_140339/D02', None), _replay('20261015_140339/D02', {'N_fast': 8, 'N_slow': 17})
    assert over['status'] == 'AWAITING_USER_DECISION' and over['definition_sha256'] != base['definition_sha256']
    assert 'ema[N=8,' in over['executed'] and 'ema[N=17,' in over['executed']
    shown = json.dumps(over['record']['substitutions'], ensure_ascii=False)
    assert '原文取值' in shown and 'N_fast=12' in shown and '用户指定' in shown and '原文没有给出该数值' not in shown


def test_rsi_14_and_20_from_real_readings_never_share_a_definition():
    a, b = _replay('20261017_094123/D03u#r2', {'X': 14}), _replay('20261017_094123/D03u#r2', {'X': 20})
    assert a['status'] == b['status'] == 'AWAITING_USER_DECISION'
    assert a['definition_sha256'] != b['definition_sha256'] and 'k=0..13' in a['executed'] and 'k=0..19' in b['executed']


# ------------------------------------------------------------------ the three modes: first reading / frozen reuse / re-read
@pytest.mark.usefixtures("amihud_250_carrier")
def test_a_user_requested_reread_reads_afresh_and_says_which_definition_it_gave(tmp_path, patched_rolling):
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    first = PaperProvider([decision('skill', skill_id='paper_research', goal=goal), decision(consent='accept')])
    app = build_chat(tmp_path / 'state', provider=first, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    assert '（已冻结）' in app.turn('同意，按这个口径探索性研究。')
    again = PaperProvider([decision('skill', skill_id='paper_research', goal=goal)])
    app2 = build_chat(tmp_path / 'state2', provider=again, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    out = app2.turn('重新阅读我刚上传的论文，再研究一次。')
    assert again.queues['understanding'] == []                              # a fresh model reading was made
    assert '应你的要求重新阅读论文' in out and '复用此前已确认' not in out
    ledger = next((tmp_path / 'papers' / 'tasks').glob('*/events.jsonl'))
    kinds = [json.loads(l)['kind'] for l in ledger.read_text(encoding='utf-8').splitlines()]
    assert 'USER_REREAD_REQUESTED' in kinds and kinds.count('DEFINITION_REUSED') == 0


def test_ema_initialisation_is_part_of_the_definition():
    """Same paper, different research convention (seed = first value vs SMA of the first N): never merged into one SHA."""
    from paper_research.factor_ir import fields_used
    ir = parse_formula(r"\operatorname{ema}_{12}(close_{t}) - \operatorname{ema}_{26}(close_{t})")["ir"]
    other = copy.deepcopy(ir)
    for node in other["args"]:
        node["init"] = "sma"
    a, b = (canonical_ir(x, {f: f for f in fields_used(x)}) for x in (ir, other))
    assert sha(a) != sha(b)
    assert classify({"definition_sha256": sha(a), "math": {"formula_ir": a}},
                    {"definition_sha256": sha(b), "math": {"formula_ir": b}}) != "SAME"


# ------------------------------------------------------------------ 2026-10-17: the user edits the proposed definition
class EditingProvider(PaperProvider):
    """PaperProvider plus scripted answers of the definition-edit reader (the user's words -> a patch)."""
    def __init__(self, decisions, edits):
        super().__init__(decisions)
        self.queues['edit'] = list(edits)

    def complete(self, request):
        from research_agent.contracts import canonical as dumps
        from research_agent.llm import ModelResponse
        if paper_call(request) and 'You update ONE quantitative factor definition' in request.messages[0].content:
            self.calls.append(request)
            return ModelResponse(dumps(self.queues['edit'].pop(0)))
        return super().complete(request)


from test_v1beta_papers import paper_call  # noqa: E402


@pytest.mark.usefixtures("amihud_250_carrier")
@pytest.mark.parametrize('edited_horizon',[5,120])
def test_versions_edit_undo_and_only_the_confirmed_version_runs(tmp_path, patched_rolling,edited_horizon):
    """v1 (paper) -> v2 horizon 5 -> v3 new formula -> undo (v2 again) -> "同意" runs exactly v2: an edit is never consent,
    each version has its own definition SHA, the paper's definition stays beside it and the run uses the user's horizon."""
    import sqlite3
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    illiq = r"\operatorname{mean}_{k=0}^{20}(\frac{|\frac{close_{t-k}}{close_{t-k-1}} - 1|}{amount_{t-k}})"
    edits = [dict(intent='edit', formula_latex='', horizon_days=edited_horizon, changes_cn=f'预测期改为{edited_horizon}个交易日'),
             dict(intent='edit', formula_latex=illiq, changes_cn='改为21日窗口的简单收益非流动性'),
             dict(intent='undo')]
    skill = decision('skill', skill_id='paper_research', goal=goal)
    app = build_chat(tmp_path / 'state', provider=EditingProvider([skill, skill, skill, skill, decision(consent='accept')], edits),
                     profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])

    def held():
        with sqlite3.connect(tmp_path / 'state' / 'research.sqlite3') as db:
            return [json.loads(p) for (p,) in db.execute("select payload from events where kind='DEFINITION_CHANGE_PROPOSED' order by sequence")][-1]

    v1 = app.turn('研究我刚上传的论文。')
    assert '回复“同意”' in v1 and '用户定制定义' not in v1
    sha1 = held()['arguments']['plan_sha256']
    v2 = app.turn(f'预测期改成{edited_horizon}天，其他不变。')
    assert '用户定制定义 v2' in v2 and f'预测期 {edited_horizon}' in v2 and '已冻结' not in v2      # an edit is shown, never run
    assert '用户定制定义需要使用' in v2 and '该论文需要使用' not in v2
    sha2 = held()['arguments']['plan_sha256']
    v3 = app.turn('公式改成过去21日简单收益绝对值除以成交额的均值。')
    assert '用户定制定义 v3' in v3 and 'amount' in v3
    sha3 = held()['arguments']['plan_sha256']
    back = app.turn('撤销刚才的修改。')
    assert held()['arguments']['plan_sha256'] == sha2 and len({sha1, sha2, sha3}) == 3 and '用户定制定义 v2' in back
    done = app.turn('同意')
    assert '（已冻结）' in done
    regs = next((tmp_path / 'papers' / 'tasks').glob('*/definitions'))
    executed = [json.loads(f.read_text(encoding='utf-8')) for f in regs.glob('*[0-9a-f].json')]
    ran = [r for r in executed if r.get('executions')]
    assert len(ran) == 1 and ran[0]['user_version']['n'] == 2 and ran[0]['executions'][0]['horizon'] == edited_horizon
    assert ran[0]['math']['time']['horizon'] == edited_horizon


def _reading(key, params=None):
    """Evidence and the verified real reading of a fixture key (no model call), as the planner gets them."""
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import replay_canonical as rc
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ScriptedClient
    from paper_agent.understanding import understand
    from test_v1beta_semantics import load as load_paper
    rows = json.loads(rc.FIXTURE.read_text(encoding='utf-8'))[key]
    name, focus, _ = rc.CASES[key.split('/')[1].split('#')[0]]
    ev, _ = load_paper(name)
    script = {p: [r['raw_output'] for r in rows if r['purpose'] == p] for p in
              ('paper_understanding', 'formula_repair', 'independent_reading', 'paper_investigation')}
    script['paper_understanding'] = script['paper_understanding'][-1:]
    ledger = TaskLedger(Path(tempfile.mkdtemp()), goal=key, budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                                       design_revisions=2, orchestration_turns=0))
    u = understand(ev, ScriptedClient(script), ledger, focus=focus, user_params=params)
    pick = next(f['name'] for f in u['factors'] if not focus or focus.lower() in f['name'].lower())
    return ev, u, pick, rc.PAPERS[name]


def test_user_versions_on_real_readings_change_exactly_what_was_asked():
    from paper_agent import user_edit
    from paper_agent.planner import plan as make_plan
    from test_v1beta_semantics import PROFILE

    def version(key, latex='', horizon=None, params=None):
        ev, u, pick, paper = _reading(key, params)
        base, task, _ = make_plan(ev, u, PROFILE, factor=pick)
        uu = user_edit.apply(u, pick, dict(formula_latex=latex, horizon_days=horizon, changes_cn='测试'), 2)
        p, t, _ = make_plan(ev, uu, PROFILE, factor=pick)
        _, s0 = definition(base, task, u, paper={'sha256': paper, 'name': pick, 'version': 1}, requested_factor=pick)
        rec, s1 = definition(p, t, uu, paper={'sha256': paper, 'name': pick, 'version': 1}, requested_factor=pick)
        return base, p, rec, s0, s1

    macd = r"\operatorname{ema}_{%s}(close_{t}) - \operatorname{ema}_{%s}(close_{t})"
    base, p, rec, s0, s1 = version('20261015_140339/D02', macd % (8, 17))
    assert p['status'] == 'AWAITING_USER_DECISION' and s1 != s0 and 'N=8,' in p['ir_execution'] and 'N=17,' in p['ir_execution']
    shown = json.dumps(p['substitutions'], ensure_ascii=False)
    assert '用户定制定义 v2（不是论文复现）' in shown and '论文定义' in shown
    _, fast, _, _, s_fast = version('20261015_140339/D02', macd % (8, 26))              # only the fast EMA changes
    assert 'N=8,' in fast['ir_execution'] and 'N=26,' in fast['ir_execution'] and 'close' in fast['ir_execution'] and s_fast not in (s0, s1)
    _, seeded, _, _, s_seed = version('20261015_140339/D02', r"\operatorname{ema}_{12,sma}(close_{t}) - \operatorname{ema}_{26}(close_{t})")
    assert 'init=sma' in seeded['ir_execution'] and s_seed not in (s0, s1, s_fast)
    _, five, rec5, _, s5 = version('20261015_140339/D02', horizon=5)                      # horizon only: same formula
    assert five['ir_execution'] == base['ir_execution'] and rec5['math']['time']['horizon'] == 5 and s5 != s0
    rsi = (r"100 - \frac{100}{1 + \frac{\operatorname{rma}_{14}(\max(close_{t} - close_{t-1}, 0))}"
           r"{\operatorname{rma}_{14}(\max(close_{t-1} - close_{t}, 0))}}")
    _, wilder, _, _, _ = version('20261017_094123/D03u#r2', rsi, params={'X': 14})
    assert wilder['status'] == 'AWAITING_USER_DECISION' and 'alpha=0.0714286' in wilder['ir_execution']
    _, high, _, s_gh0, s_high = version('20261016_142232/D09', r"\frac{close_{t}}{\max_{k=0}^{251} high_{t-k}}")
    assert high['status'] == 'AWAITING_USER_DECISION' and 'high[t-k]' in high['ir_execution'] and s_high != s_gh0
    blocked, filled, _, _, _ = version('20261016_142232/D03', rsi)                        # blocked (no X): the user supplies it all
    assert blocked['status'] == 'BLOCKED' and filled['status'] == 'AWAITING_USER_DECISION'
    _, future, _, _, _ = version('20261015_140339/D02', r"close_{t+1} - close_{t}")
    _, vwap, _, _, _ = version('20261015_140339/D02', r"vwap_{t} - close_{t}")
    assert future['status'] == vwap['status'] == 'BLOCKED'
    assert any(h['code'] == 'FIELD_NOT_AVAILABLE' for h in vwap['hard_stops'])


def test_a_users_version_is_never_reused_by_another_session(tmp_path):
    rec = canon(r"\frac{P_{i,t}}{\max_{k=0}^{251} P_{i,t-k}}")
    digest = rec["definition_sha256"]
    reg = DefinitionRegistry(tmp_path)
    reg.propose(dict(rec, user_version={'n': 2, 'id': 'x'}), plan_status='AWAITING_USER_DECISION', user_params={}, session_id='s1')
    reg.approve(digest, session_id='s1', task_id='t1', substitutions=[], asset_phrase=False)
    reg.freeze(digest, needs_approval=True)
    assert reg.reusable(paper_sha256=rec['math']['paper_sha256'], requested_factor='', user_params={}) is None


@pytest.mark.usefixtures("amihud_250_carrier")
def test_after_a_frozen_reuse_the_next_message_edits_and_an_unsupported_edit_is_blocked(tmp_path, patched_rolling):
    """Session 2's first request reuses the frozen definition; its next message is read as an edit (v2, not reuse);
    an edit the daily panel cannot express (weekly bars) is blocked and said, never run in daily rows."""
    from research_agent.app import build_chat
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    skill = decision('skill', skill_id='paper_research', goal=goal)
    app = build_chat(tmp_path / 'state', provider=PaperProvider([skill, decision(consent='accept')]), profile='development',
                     resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    assert '（已冻结）' in app.turn('同意')
    second = EditingProvider([skill, skill, skill], [dict(intent='edit', horizon_days=5, changes_cn='预测期改为5个交易日'),
                                                     dict(intent='unsupported', changes_cn='改用周频数据')])
    second.queues['understanding'] = []
    app2 = build_chat(tmp_path / 'state2', provider=second, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    assert '复用此前已确认并冻结的定义' in app2.turn('研究我刚上传的论文。')
    edited = app2.turn('预测期改成5天。')
    assert '用户定制定义 v2' in edited and '复用此前已确认' not in edited
    weekly = app2.turn('改用周频数据。')
    assert 'USER_EDIT_NOT_SUPPORTED' in weekly and '周频' in weekly


# ------------------------------------------------------------------ K3 live 2026-10-17 13:56 (session ffb20037)
class DeclaringProvider(EditingProvider):
    """As live K3: the workflow's planning model declares a definition change for the edit turn."""
    def complete(self, request):
        from research_agent.contracts import canonical as dumps
        from research_agent.llm import ModelResponse, Role
        props = (request.output_schema or {}).get('properties', {})
        if 'definition_change' in props and 'research_goal' not in props and not any(x.role == Role.TOOL for x in request.messages):
            self.calls.append(request)
            return ModelResponse(dumps(dict(action='continue', hypothesis='论文因子', change_reason='用户修改',
                                            summary='按用户修改研究。', definition_change='预测期改为5天，需用户确认')))
        return super().complete(request)


@pytest.mark.usefixtures("amihud_250_carrier")
def test_k3_an_edit_reaches_the_paper_tool_and_only_the_shown_version_runs(tmp_path, patched_rolling):
    import sqlite3
    from research_agent.app import build_chat
    from research_agent.contracts import canonical as dumps
    from research_agent.llm import ModelResponse
    from research_agent.paper_library import PaperLibrary
    goal = '研究我刚上传的论文，提取里面的因子并做完整研究'
    fx = build(tmp_path)
    patched_rolling['client'], _ = broker(fx)
    lib = PaperLibrary(tmp_path / 'papers')
    lib.import_pdf(stage(lib, FIX / 'amihud2002.pdf'), 'Amihud_2002.pdf')
    skill = decision('skill', skill_id='paper_research', goal=goal)
    propose = ModelResponse(dumps(dict(action='propose', reply='', skill_id='paper_research', research_goal=goal + '，预测期改成5天',
                                       reason='用户修改', consent='', definition_change='预测期改为5天')))
    prov = DeclaringProvider([skill, propose, decision(consent='accept'), skill],
                             [dict(intent='edit', horizon_days=5, formula_latex=None, changes_cn='预测期改为5个交易日'), dict(intent='undo')])
    app = build_chat(tmp_path / 'state', provider=prov, profile='development', resources_manifest=fx['manifest'], research_config=fx['config'])
    app.turn('研究我刚上传的论文。')
    prov.factor = 'ILLIQ 预测期5天'          # K3 rerun: the model words the factor argument differently every turn
    v2 = app.turn('预测期改成5天，其他不变。')
    with sqlite3.connect(tmp_path / 'state' / 'research.sqlite3') as db:
        held = [json.loads(p) for (p,) in db.execute("select payload from events where kind='DEFINITION_CHANGE_PROPOSED' order by sequence")][-1]
    assert held['arguments'].get('plan_sha256') and '冻结计划 ' not in v2 and '用户定制定义 v2' in v2
    assert '（已冻结）' in app.turn('同意 执行吧')
    regs = next((tmp_path / 'papers' / 'tasks').glob('*/definitions'))
    ran = [r for r in (json.loads(f.read_text(encoding='utf-8')) for f in regs.glob('*[0-9a-f].json')) if r.get('executions')]
    assert len(ran) == 1 and ran[0]['executions'][0]['horizon'] == 5 and ran[0]['math']['time']['horizon'] == 5
    back = app.turn('撤销刚才的修改。')                   # after a run: the restored version is shown, never run unasked
    assert '回复“同意”' in back and '（已冻结）' not in back
    assert sum(len(r.get('executions') or []) for r in (json.loads(f.read_text(encoding='utf-8')) for f in regs.glob('*[0-9a-f].json'))) == 1


def test_k3_real_rsi_completion_with_null_horizon_and_an_auxiliary_definition():
    from paper_agent import user_edit
    from paper_agent.planner import plan as make_plan
    from test_v1beta_semantics import PROFILE
    real = {"intent": "edit", "horizon_days": None, "changes_cn": "将RS定义为14日平均涨幅与平均跌幅之比，并用Wilder平滑（rma_14）计算。",
            "formula_latex": r"RSI_{i,t} = 100 - \frac{100}{1 + RS_{i,t}},\quad RS_{i,t} = \frac{\operatorname{rma}_{14}(\max(close_{t} - close_{t-1}, 0))}"
                             r"{\operatorname{rma}_{14}(\max(close_{t-1} - close_{t}, 0))}"}
    from paper_agent.model import _validate
    assert not _validate(real, user_edit.SCHEMA)                          # the K3 reply passes the contract now
    ev, u, pick, _ = _reading('20261016_142232/D03')                      # RSI blocked: X not given
    p, _, _ = make_plan(ev, user_edit.apply(u, pick, dict(real, horizon_days=None), 2), PROFILE, factor=pick)
    assert p['status'] == 'AWAITING_USER_DECISION' and 'Wilder N=14' in p['ir_execution']


def test_round_c_a_printed_conditional_is_never_admitted_as_a_rewrite(tmp_path):
    """Round C E01 (2026-10-17): Alpha#23 '((sum(high,20)/20) < high) ? -delta(high,2) : 0' was admitted as
    sign(high - mean20)*(-delta(high,2)) -- +delta where the paper has 0 -- after the second reading was asked to re-express
    the conditional in a grammar that has none. The three real replies, replayed: blocked, nothing to approve."""
    import gzip
    from paper_agent.evidence import PaperEvidence
    from paper_agent.ledger import TaskLedger
    from paper_agent.model import ScriptedClient
    from paper_agent.planner import plan as make_plan
    from paper_agent.understanding import understand
    from test_v1beta_semantics import PROFILE
    if not Path(Path(__file__).parent / 'fixtures_v1beta' / 'papers' / 'alpha101.json.gz').is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    d = json.load(gzip.open(Path(__file__).parent / 'fixtures_v1beta' / 'papers' / 'alpha101.json.gz', 'rt', encoding='utf-8'))
    ev = PaperEvidence(d['doc'], d['spec'], d['passages'])
    script = {p: [r['raw_output'] for r in d['replies'] if r['purpose'] == p] for p in ('paper_understanding', 'independent_reading')}
    ledger = TaskLedger(tmp_path, goal='alpha23', budget=dict(model_calls=40, total_tokens=2_000_000, wall_seconds=10 ** 7,
                                                               design_revisions=2, orchestration_turns=0))
    u = understand(ev, ScriptedClient(script), ledger, focus='Alpha#23')
    p, _, _ = make_plan(ev, u, PROFILE, factor='Alpha#23')
    assert p['status'] == 'BLOCKED' and 'CONDITIONAL_NOT_REPRESENTABLE' in {h['code'] for h in p['hard_stops']}
