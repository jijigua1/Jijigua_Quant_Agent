"""General factor definitions -> isolated Python -> the same three-stage study.

No executable source is accepted through tool arguments. Generated code uses the
existing sandbox, independent synthetic oracle and causality/history checks.
"""
from .contracts import object_schema, validate, fingerprint, ContractError

CONTRACT_SCHEMA = object_schema({
    'formula': {'type':'string','minLength':1,'maxLength':4000,'description':'Only the raw causal factor, one value per input date/stock. No forward labels, standardization, groups, report or export code.'},
    'inputs': {'type':'array','minItems':1,'uniqueItems':True,
               'items':{'enum':['open','high','low','close','volume','amount']}},
    'warmup': {'type':'integer','minimum':1,'description':'Maximum historical row offset on the common published trading-date grid. Never compress each stock to nonmissing observations unless explicitly requested.'},
    'time_semantics': {'type':'string','minLength':1,'maxLength':4000},
    'missing_semantics': {'type':'string','minLength':1,'maxLength':4000},
    'steps': {'type':'array','minItems':1,'maxItems':20,'items':{'type':'string','minLength':1,'maxLength':2000}},
})


def validate_factor_contract(contract, requested_definition=""):
    """Reject evaluation/export instructions masquerading as raw factor code.

    These operations belong to the fixed evaluator. Return actionable tool
    diagnostics before model generation; the workflow repairs the same request.
    """
    import re
    from .security import InvalidParameters
    # Check affirmative instructions, not words inside explicit prohibitions.
    # The model commonly writes "without dropping missing rows"; that is valid.
    clauses=re.split(r'[;；。\n]|(?<=\.)\s+', ' '.join([contract['formula'],*contract['steps'],contract['time_semantics']]))
    affirmative=[c for c in clauses if not re.search(r'\b(?:no|not|never|without)\b|不得|不能|不要|不做|不包含|不压缩|不删除',c,re.I)]
    text=' '.join(affirmative)
    if re.search(r'\blabel(?:s)?\s*(?:\[.*?\])?\s*=|(?:计算|构造|生成).*?标签|(?:生成|输出).*?(?:报告|PKL)',text,re.I):
        raise InvalidParameters([dict(path='$.contract',constraint='RAW_FACTOR_ONLY',
            instruction='contract describes ONLY the raw causal factor on the unchanged input date/stock grid. Forward labels, final standardization, grouping, reports and exports belong to the program via outer parameters. Preserve the original factor formula and missing rules.')])
    if re.search(r'有效交易日序列|有效日序列|(?:compress|drop).*?(?:missing|nan|nonfinite)',text,re.I) and not re.search(r'有效交易日序列|有效日序列|event.time|nonmissing.observation',requested_definition,re.I):
        raise InvalidParameters([dict(path='$.contract.time_semantics',constraint='PUBLISHED_DATE_GRID',
            instruction='Trading-day offsets use the common published date axis and preserve missing rows. Do not redefine the factor on each-stock nonmissing-observation offsets. Explicit event-time research must come from the user request.')])


def study(backend, resource_id, contract, hypothesis, reason, horizon, n_groups,
          standardization, _task_context, factor_name='custom_factor'):
    from .definition_gate import ValidationPassed
    from .paper_tools import RuntimeClient
    from paper_agent.ledger import TaskLedger
    from paper_agent.autonomous_route import build
    validate(contract,CONTRACT_SCHEMA)
    validate_factor_contract(contract, _task_context.get('goal',''))
    import re
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',factor_name):
        raise ContractError('INVALID_FACTOR_NAME')
    # Preflight on actual authorized data BEFORE any generated code or model call.
    definition=dict(input_fields=contract['inputs'],warmup_observations=contract['warmup'],expression=None)
    try:
        backend._study(resource_id,'approved',max(2,contract['warmup']),horizon,n_groups,standardization,
                       dict(_task_context,validate_only=True),definition)
    except ValidationPassed:
        pass
    else:
        raise ContractError('ALGORITHM_PREFLIGHT_DID_NOT_STOP')
    record=backend.catalog.records[resource_id]
    published_fields=set(record['fields']) if record['format']=='published_npy' else {'open','high','low','close','volume'}
    if set(contract['inputs'])-published_fields:
        raise ContractError('ALGORITHM_FIELD_NOT_PUBLISHED')
    if _task_context.get('validate_only'):
        raise ValidationPassed()
    if not _task_context.get('model'):
        raise ContractError('ALGORITHM_MODEL_REQUIRED')
    # User request provenance is explicitly labelled; it is never a paper citation.
    original=_task_context.get('goal','')
    fixed=dict(contract,citations=[dict(passage='USER_REQUEST',quote=original)],unresolved=[],
               provenance=dict(kind='user_requested_factor',request=original))
    _task_context['emit']('ALGORITHM_DEFINITION_FROZEN',dict(contract_sha256=fingerprint(fixed),
                            contract=fixed,horizon=horizon,n_groups=n_groups,standardization=standardization))
    ledger=TaskLedger(backend.artifacts.root/'research_runs'/'.algorithms',_task_context['task_id'],goal=original)
    ledger.write_artifact('definition.json',fixed)
    _task_context['emit']('RESEARCH_STAGE',dict(stage='autonomous_algorithm_design_and_test',status='RUNNING',elapsed_seconds=0))
    try:
        bundle=build({'autonomous_contract':fixed},RuntimeClient(_task_context['model']),ledger)
    except ValueError as exc:
        if str(exc).startswith('INDEPENDENT_REFERENCE_NEEDS_DEFINITION:'):
            from .security import InvalidParameters
            raise InvalidParameters([dict(path='$.contract',constraint='INCOMPLETE_FACTOR_CONTRACT',
                instruction=str(exc)[:1500])]) from exc
        raise ContractError('AUTONOMOUS_ALGORITHM_VALIDATION_FAILED') from exc
    _task_context['emit']('RESEARCH_STAGE',dict(stage='autonomous_algorithm_design_and_test',status='COMPLETED',elapsed_seconds=0))
    # Both expression and custom algorithms enter the existing report/PKL/Test chain.
    return backend.autonomous_study(resource_id,bundle,hypothesis,reason,horizon,n_groups,standardization,
                                    _task_context,factor_name=factor_name)
