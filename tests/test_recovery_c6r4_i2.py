"""C6R4-I2: research Tool results that outgrow the 64 KiB JSON contract (live C6R4-I1 acceptance, 2026-10-18).

After a real 2026 Rolling Test the GH study's read result was 68,513 bytes (canonical JSON; 72,241 with spaces); validate() raised an unclassified
ContractError and the Agent could not show a complete study ("刷新" and "报告在哪里" both failed). The fixture below is
that exact read result (statistics only, no market data). The fit is generic: known bulky detail first, then the
largest unprotected container, types preserved, every drop listed, a coded error if the protected part cannot fit.
"""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent import result_fit
from research_agent.contracts import ContractError, MAX_JSON_BYTES, validate
from research_agent.evidence import summary
from research_agent.result_fit import BUDGET, NOTE, OMITTED, fit, size
from v1beta_fixtures import TRAIN, build

LIVE = Path(__file__).parent / 'fixtures_v1beta' / 'c6r4i1_live_gh_read_result.json.gz'
KEPT = ('report_access', 'splits', 'spec', 'parameters', 'test_monthly_label_status', 'limitations', 'report_path',
        'html_path', 'study_id', 'research_status', 'final_report_ready', 'resource_id', 'mode', 'report_revision')


def live():
    if not Path(LIVE).is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    value = json.loads(gzip.open(LIVE, 'rt', encoding='utf-8').read())
    assert value['resource_id'] == 'gpushare:train2020_2023'
    value['resource_id'] = TRAIN          # the offline backend's schema lists its synthetic resource ids only
    return value


@pytest.fixture(scope='module')
def read_schema(tmp_path_factory):
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path_factory.mktemp('i2'))
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    return backend, backend.registry()._tools['qrtk_read_study'].output_schema


def test_the_live_read_result_failed_the_contract_and_now_fits_with_its_headline(read_schema):
    _, schema = read_schema
    if not Path(LIVE).is_file():
        pytest.skip("Private recorded evidence fixture omitted from public repository")
    assert size(json.loads(gzip.open(LIVE, 'rt', encoding='utf-8').read())) == 68513    # as read live
    original = live()
    assert size(original) > MAX_JSON_BYTES
    with pytest.raises(ContractError, match='JSON exceeds size limit'):        # the C6R4-I1 failure, reproduced
        validate(original, schema)
    fitted = fit(original)
    assert size(fitted) <= BUDGET
    validate(fitted, schema)
    for key in KEPT:
        assert fitted[key] == original[key], key
    p, q = fitted['metrics']['professional'], original['metrics']['professional']
    for key in ('partitions', 'verdict', 'annual', 'quality'):
        assert p[key] == q[key], key
    assert p['test']['metrics'] == q['test']['metrics'] and p['test']['status'] == 'COMPLETED'
    note = fitted[NOTE]
    assert note['original_bytes'] == size(original) and note['omitted'][0]['field'] == 'metrics.professional.test.monthly'
    assert p['test']['monthly'] == []                                          # a list stays a list
    assert original['metrics']['professional']['test']['monthly'], 'the input is never modified'
    view = summary(fitted)                                                     # what the model sees still has the Test
    assert view[NOTE]['omitted'][0]['field'] == 'metrics.professional.test.monthly'
    test = view['current_report']['test']
    assert test['status'] == 'COMPLETED' and round(test['metrics']['rank_ic_mean'], 4) == -0.0096
    assert view['current_report']['partitions']['valid']['rank_ic_mean'] == q['partitions']['valid']['rank_ic_mean']


def test_through_the_tool_registry_the_read_is_delivered(read_schema, monkeypatch):
    backend, _ = read_schema
    from research_agent import tools
    from research_agent.llm import ToolCall
    monkeypatch.setattr(tools, 'authorize', lambda *a, **k: None)             # authorization is covered elsewhere
    monkeypatch.setattr(backend, 'read_study', lambda **k: live())
    registry = backend.registry()
    grant = SimpleNamespace(task_id='a' * 32, resources=(TRAIN,))
    out = registry.execute(ToolCall('c1', 'qrtk_read_study', {'resource_id': TRAIN, 'study_id': 'a' * 32 + ':' + 'b' * 16}),
                           policy=SimpleNamespace(resources=(TRAIN,)), grant=grant, skill=None,
                           task_context={'task_id': 'a' * 32})
    assert out['status'] == 'ok' and out['data'][NOTE]['omitted']
    assert size(out) <= MAX_JSON_BYTES


def test_small_results_are_returned_unchanged():
    small = {'mode': 'real_data', 'metrics': {'x': list(range(10))}}
    assert fit(small) is small and NOTE not in small


def test_an_unknown_bulky_field_is_dropped_generically_largest_first():
    value = {'mode': 'real_data', 'report_path': '/r.md', 'limitations': ['a'] * 5,
             'metrics': {'professional': {'annual': [{'period': '2025', 'split': 'valid'}], 'partitions': {'valid': {}},
                                          'verdict': {'status': 'X'}, 'test': {'status': 'COMPLETED', 'metrics': {}}},
                         'new_diagnostic': {'rows': ['z' * 100] * 60}},
             'another_new_block': {'rows': ['y' * 100] * 30}, 'tiny': {'k': 1}}
    fitted = fit(value, budget=size(value) - 3000)
    assert fitted['metrics']['new_diagnostic'] == {'omitted': OMITTED, 'bytes': size(value['metrics']['new_diagnostic'])}
    assert fitted['another_new_block'] == value['another_new_block'] and fitted['tiny'] == value['tiny']
    assert fitted['limitations'] == value['limitations'] and fitted['metrics']['professional'] == value['metrics']['professional']
    assert [d['field'] for d in fitted[NOTE]['omitted']] == ['metrics.new_diagnostic']


def test_when_the_protected_part_alone_is_too_large_the_error_is_coded():
    value = {'mode': 'real_data', 'limitations': ['限制说明' * 50] * 400}
    with pytest.raises(ContractError) as exc:
        fit(value)
    assert str(exc.value) == 'TOOL_RESULT_TOO_LARGE'
    import re
    assert re.fullmatch(r'[A-Z][A-Z0-9_]{2,60}', str(exc.value))              # the workflow passes coded errors to the user


def test_a_note_is_never_added_where_the_schema_has_no_place_for_it():
    value = {'mode': 'real_data', 'economic_rationale': {'text': 'x' * 70000}}
    fitted = fit(value, allows_note=False)
    assert NOTE not in fitted and fitted['economic_rationale']['omitted'] == OMITTED


def test_every_quant_tool_schema_has_the_note_field(read_schema):
    backend, _ = read_schema
    registry = backend.registry()
    for name, tool in registry._tools.items():
        if tool.kind == 'quant_compute':
            assert NOTE in tool.output_schema['properties'], name


def test_study_json_files_over_64k_are_written_and_read_and_1mib_still_guards(tmp_path):
    """A study's own analysis/manifest were capped at 64 KiB (the live GH analysis was already 52 KiB before Test)."""
    import hashlib
    from research_agent.artifacts import ResearchArtifacts, STUDY_JSON_MAX_BYTES
    from research_agent.security import Denied
    run = tmp_path / 'run'
    (run / 'data').mkdir(parents=True)
    big = {'paper_definition': {'text': '论文定义' * 30000}}                     # ~360 KB of UTF-8
    ResearchArtifacts.write_json(run / 'data/analysis.json', big)
    raw = (run / 'data/analysis.json').read_bytes()
    assert len(raw) > MAX_JSON_BYTES
    assert ResearchArtifacts.read_analysis(run, {'analysis_sha256': hashlib.sha256(raw).hexdigest()}) == big
    huge = tmp_path / 'huge'
    (huge / 'data').mkdir(parents=True)
    with pytest.raises(ContractError):
        ResearchArtifacts.write_json(huge / 'data/analysis.json', {'x': 'y' * (STUDY_JSON_MAX_BYTES + 1)})
    (huge / 'data/analysis.json').write_bytes(b'{"x":"' + b'y' * (STUDY_JSON_MAX_BYTES + 1) + b'"}')
    with pytest.raises(Denied, match='ARTIFACT_FILE_DENIED'):
        ResearchArtifacts.read_analysis(huge, {'analysis_sha256': '0' * 64})


def test_compaction_accounts_for_its_own_note_before_stopping():
    from copy import deepcopy
    value={'parameters':{'definition':'x'*1400}, 'metrics':{'professional':{
        'test':{'monthly':['m'*2000]}, 'files':{'file':'f'*700}}}}
    after=deepcopy(value);after['metrics']['professional']['test']['monthly']=[]
    budget=size(after)+50
    fitted=fit(value,budget=budget)
    assert size(fitted)<=budget
    assert fitted['parameters']==value['parameters']
    assert len(fitted[NOTE]['omitted'])>=2
    assert value['metrics']['professional']['test']['monthly']
