"""Paper -> explicit user-reviewed contract -> isolated Python implementation.

Capability gaps may propose a new executable contract; mathematical contradictions,
unknown parameters, missing input data and invalid citations never disappear.
"""
import copy
import json

from .ledger import sha256_obj
from .model import ask_json

CAPABILITY = {'CALENDAR_WINDOW_UNSUPPORTED', 'CONDITIONAL_NOT_REPRESENTABLE', 'FORMULA_UNPARSEABLE'}
RECONSTRUCTION = {'FORMULA_RECONSTRUCTION_UNVERIFIED'}

CONTRACT_SCHEMA = {'type':'object','additionalProperties':False,
    'required':['formula','inputs','warmup','time_semantics','missing_semantics','steps','citations','unresolved'],
    'properties':{'formula':{'type':'string','minLength':1,'maxLength':4000},
        'inputs':{'type':'array','minItems':1,'maxItems':6,'uniqueItems':True,'items':{'type':'string'}},
        'warmup':{'type':'integer','minimum':1},
        'time_semantics':{'type':'string','minLength':1,'maxLength':4000},
        'missing_semantics':{'type':'string','minLength':1,'maxLength':4000},
        'steps':{'type':'array','minItems':1,'maxItems':20,'items':{'type':'string'}},
        'citations':{'type':'array','minItems':1,'items':{'type':'object','required':['passage','quote'],
            'properties':{'passage':{'type':'string'},'quote':{'type':'string'}},'additionalProperties':False}},
        'unresolved':{'type':'array','items':{'type':'string'}}}}

SYSTEM = '''Read the supplied original paper evidence. Propose one explicit computational
contract for the selected factor, NOT code. No fixed operator menu applies: Python
algorithms will implement the user-confirmed contract. Preserve calendar periods,
conditions, units, missing counts, and the original mathematical definition. The
earlier formula reconstruction is unverified, not authoritative. Cite exact supplied
passages. Never guess data, minimum observations, timing, parameters or definitions.
Put every unresolved choice in unresolved; no execution follows those choices.
State exactly when a value becomes available (a full year's value is unavailable
before year end), and the finite history bound in daily rows, including publication
lag and carrying values forward when the paper requires it. The bound is a maximum
history requirement, NOT permission to replace calendar intervals by a fixed window.
Missing/zero-denominator handling must follow the paper or remain unresolved.
Use only the published fields and actual units in the data profile. Return the
specified JSON. inputs must contain exact published field identifiers (for example
close and amount), never descriptions or units. Put descriptions in steps.
user_request records the user's requested computational choices, not paper evidence
and not execution approval. Apply explicit choices such as raw prices, local currency,
or previous-year timing as disclosed exploratory substitutions; do not claim the
paper specified them. Keep choices not supplied by the paper or user unresolved. unresolved contains ONLY
computational choices still requiring an answer. If user_request explicitly resolves
a choice, document its exploratory provenance in steps, NOT in unresolved. Differences
from a paper-faithful replication are disclosures, not missing choices for this
explicit exploratory contract. Use only passage IDs present in passages; copy short
quotes verbatim from their text. Never cite from memory or invent a passage ID.
A previous full calendar-year value carried through the following year can require
roughly two years of input history; warmup must cover the oldest required row.
Do not claim trusted IR certification or approval.'''


def eligible(plan):
    codes = {x['code'] for x in plan.get('hard_stops') or []}
    return plan.get('route') == 'algorithm' or (plan.get('status') == 'BLOCKED' and
            bool(codes & CAPABILITY) and codes <= CAPABILITY | RECONSTRUCTION)


def verbatim_repair_options(evidence, bad_citations):
    """Offer contiguous source spans, never normalize away mathematical symbols."""
    import difflib
    options=[]
    for cite in bad_citations:
        passage=cite.get('passage')
        if passage not in evidence.by_id:
            continue
        source=evidence.by_id[passage]['text'];quote=cite.get('quote','')
        blocks=difflib.SequenceMatcher(None,quote,source,autojunk=False).get_matching_blocks()
        spans=sorted((source[b.b:b.b+b.size] for b in blocks if b.size>=20),key=len,reverse=True)
        options.extend(dict(passage=passage,quote=span[:180]) for span in spans[:3])
    return options


def propose(plan, understanding, evidence, profile, client, ledger, *, user_request=''):
    if not eligible(plan) or client is None:
        return plan
    factor = next(f for f in understanding['factors'] if f['name'] == plan['factor'])
    basis = sha256_obj(dict(plan=plan, factor=factor, profile=profile, user_request=user_request, route='autonomous/2'))
    cached = ledger.read_artifact(f'autonomous_plans/{basis}.json')
    if cached:
        return cached
    cites = list((factor.get('formula') or {}).get('citations') or [])
    cites += list((factor.get('verbal_definition') or {}).get('citations') or [])
    cites += list((factor.get('algorithm') or {}).get('citations') or [])
    for item in factor.get('symbols') or []:
        cites.extend(item.get('citations') or [])
    # Factor evidence also occurs in window, timing and sample-condition objects.
    # Every quoted factor passage visible to the model must have its source text.
    def citation_ids(value):
        if isinstance(value, dict):
            if isinstance(value.get('passage'), str):
                yield value['passage']
            for child in value.values():
                yield from citation_ids(child)
        elif isinstance(value, list):
            for child in value:
                yield from citation_ids(child)
    ids = set(citation_ids(factor)) | ({c.get('passage') for c in cites} - {None})
    # Include nearby context: a denominator or sample condition often follows
    # the formula's paragraph. The model must not see only a convenient quote.
    import re
    for passage in list(ids):
        match=re.fullmatch(r'P(\d+)',passage)
        if match:
            ids.update(f'P{i:04d}' for i in range(max(0,int(match[1])-2),int(match[1])+4))
    passages = [{'id':i,'text':evidence.by_id[i]['text']} for i in sorted(ids) if i in evidence.by_id]
    if not passages:
        return plan
    prompt = json.dumps(dict(factor=factor, passages=passages, profile=profile, user_request=user_request), ensure_ascii=False)
    if len(prompt.encode()) > 48000:
        return plan
    from .model import ModelFailure
    schema = copy.deepcopy(CONTRACT_SCHEMA)
    schema['properties']['inputs']['items']['enum'] = list(profile['fields'])
    schema['properties']['citations']['items']['properties']['passage']['enum'] = [p['id'] for p in passages]
    def blocked(code, detail):
        result=copy.deepcopy(plan)
        result['status']='BLOCKED'
        result['original_hard_stops']=list(plan.get('hard_stops') or [])
        result['hard_stops']=[dict(code=code,detail=detail)]
        return result
    from .understanding import _cites
    choices_reviewed = False
    for evidence_attempt in range(2):
        try:
            contract, _ = ask_json(client, ledger, purpose='autonomous_contract',
                system=SYSTEM + '\nReturn this exact JSON schema (not the input factor object). Keep quotes short.\n' + json.dumps(schema,ensure_ascii=False),
                user=prompt, schema=schema, max_tokens=6000, repair=1)
        except ModelFailure as exc:
            return blocked('AUTONOMOUS_CONTRACT_MODEL_FAILED',str(exc)[:300])
        if contract['unresolved'] and not choices_reviewed:
            choices_reviewed = True
            try:
                contract, _ = ask_json(client, ledger, purpose='autonomous_choices_review',
                    system=SYSTEM + '\nReview unresolved choices for THIS requested run only. Keep genuinely missing computational choices unresolved. Explicit user choices take precedence over paper-replication defaults. A possible future paper-faithful run, optional additional factor, or reinstating a filter explicitly excluded by the user is not a missing choice for this run. Do not invent a missing parameter or infer consent. Preserve verified citations and return the complete contract.\n' + json.dumps(schema,ensure_ascii=False),
                    user=json.dumps(dict(user_request=user_request,contract=contract,passages=passages,profile=profile),ensure_ascii=False),
                    schema=schema,max_tokens=6000,repair=1)
            except ModelFailure as exc:
                return blocked('AUTONOMOUS_CONTRACT_MODEL_FAILED',str(exc)[:300])
        good, bad = _cites(evidence, contract['citations'])
        invalid_ids = [c['passage'] for c in contract['citations'] if c['passage'] not in ids]
        invalid_fields = sorted(set(contract['inputs']) - set(profile['fields']))
        if good and not bad and not invalid_ids and not invalid_fields:
            break
        if evidence_attempt:
            return blocked('AUTONOMOUS_CONTRACT_EVIDENCE_INVALID',
                           '自主算法定义的引文或输入字段在一次纠正后仍未通过核验；没有执行代码。')
        prompt = json.dumps(dict(factor=factor,passages=passages,profile=profile,user_request=user_request,
            previous_contract=contract,verbatim_quote_options=verbatim_repair_options(evidence,bad),validation_errors=dict(nonverbatim_citations=bad,
                unavailable_passage_ids=invalid_ids,invalid_fields=invalid_fields),
            correction='Return the complete corrected contract. Preserve computational choices. For invalid quotes, select a relevant verbatim_quote_options entry or copy an exact contiguous supplied source span. The options are literal source substrings, not corrected mathematical expressions. Never repeat a rejected quote, paraphrase it, or reconstruct math typography. Preserve the definition; this is evidence repair, not approval.'),ensure_ascii=False)
    if profile.get('train_rows_estimate') and contract['warmup'] >= profile['train_rows_estimate']:
        return blocked('LOOKBACK_EXCEEDS_SAMPLE',f"requires {contract['warmup']} historical rows; published Train contains {profile['train_rows_estimate']} rows")
    if contract['unresolved']:
        result=copy.deepcopy(plan)
        result['notes']=list(result.get('notes') or [])+contract['unresolved']
        result['original_hard_stops']=list(plan.get('hard_stops') or [])
        result['hard_stops']=[dict(code='ALGORITHM_DEFINITION_REQUIRED',detail='；'.join(contract['unresolved']))]
        result['status']='BLOCKED'
        return result
    result=copy.deepcopy(plan)
    result.update(status='AWAITING_USER_DECISION', route='autonomous_python',
                  original_hard_stops=plan.get('hard_stops',[]), hard_stops=[],
                  autonomous_contract=contract, ir_execution_json=None, dsl=None,
                  ir_execution=contract['formula'], inputs=contract['inputs'], warmup_rows=contract['warmup'],
                  symbol_map={f:{'field':f} for f in contract['inputs']},
                  timeline=[contract['time_semantics'],contract['missing_semantics']],worked_examples=[])
    if not result.get('choices'):
        result['choices']=dict(label_lag=1,horizon=dict(n=1,unit='trading_day'),splits=profile['splits'])
        result['notes']=list(result.get('notes') or [])+['预测期采用明确展示的系统默认1个交易日；确认后才执行。']
    result['substitutions']=[s for s in result.get('substitutions',[]) if s['kind'] not in ('test_not_evaluable','algorithm_route')]+[
        dict(item='自主编程',kind='autonomous_python',paper='原定义与原阻断证据保留',
             ours='你确认上述具体定义后，由模型编写、隔离测试和修正 Python；不认证为可信IR。冻结同一代码贯穿Train、Validation、2026。')]
    result['definition_sha256']=sha256_obj(dict(contract=contract, choices=result['choices'], original=plan['definition_sha256']))
    ledger.write_artifact(f'autonomous_plans/{basis}.json',result)
    return result


def build(plan, client, ledger):
    """Independent reference gets only the confirmed definition, never compute code.

    The reference is model authored and explicitly recorded as such. Agreement
    is supporting numerical evidence, not a general mathematical proof.
    """
    import numpy as np
    import pandas as pd
    from .autonomous_algorithm import develop, source_sha, SCHEMA
    from .isolated_execution import execute
    from .algorithm_bundle import VERSION, digest, engine_sha, validate
    contract=plan['autonomous_contract']
    key=digest(contract)
    old=ledger.read_artifact(f'autonomous_algorithms/{key}.bundle.json')
    if old and any(x.get('performance_only') and x.get('fixture')=='market_scale_synthetic_performance' for x in old.get('validation',{}).get('checks',[])):
        validate(old)
        return old
    fixtures=[]
    rows=max(800,contract['warmup']+100)
    for seed in (451,593,829):
        rng=np.random.default_rng(seed)
        dates=pd.bdate_range('2019-07-01',periods=rows)
        price=np.exp(np.cumsum(rng.normal(0,.02,(rows,4)),axis=0))*20
        arrays={f:price.copy() for f in ('open','high','low','close')}
        arrays['high']=price*1.05; arrays['low']=price*.95
        arrays['volume']=rng.uniform(100,10000,(rows,4))
        arrays['amount']=price*arrays['volume']
        if seed==593:
            for value in arrays.values():value[::17,1]=np.nan
        if seed==829:
            arrays['volume'][::19,2]=0; arrays['amount'][::19,2]=0
        panels={f:pd.DataFrame(arrays[f],index=dates,columns=['A','B','C','D']) for f in contract['inputs']}
        expected=None
        fixtures.append(dict(name=f'independent_seed_{seed}',data_class='synthetic',panels=panels,expected=expected,
            oracle_basis='pending independent reference',prefix_cutoffs=[rows-20,rows-1],history_bound=contract['warmup']))
    from .isolated_execution import IsolationError
    feedback=''
    for reference_attempt in range(3):
        ref,_=ask_json(client,ledger,purpose='autonomous_reference',system='''Write an independent,
literal reference implementation of the user-confirmed paper definition. Do not optimize.
Always return all three fields: source, explanation, unresolved (an empty list if fully specified). Define compute(panels) returning a DataFrame.
Use numpy/pandas and ordinary Python; no files, network, subprocess, external state.
Only input fields named by the contract. Observe its exact availability and missing
rules. Never use future rows. If an assumption is missing return unresolved.
No implementation being tested is provided; derive from the contract and citations.''' + '\nRequired JSON schema:\n' + json.dumps(SCHEMA),
        user=json.dumps(contract,ensure_ascii=False)+feedback,schema=SCHEMA,max_tokens=8192,repair=1)
        if ref['unresolved']:
            raise ValueError('INDEPENDENT_REFERENCE_NEEDS_DEFINITION: '+';'.join(ref['unresolved']))
        ledger.write_artifact(f'autonomous_algorithms/{key}.reference.py.txt',ref['source'],kind='text')
        try:
            for fixture in fixtures:
                fixture['expected']=execute(ref['source'],fixture['panels'],source_sha256=source_sha(ref['source']),timeout=120)
                fixture['oracle_basis']='independent model reference '+source_sha(ref['source'])
            break
        except IsolationError as exc:
            ledger.event('INDEPENDENT_REFERENCE_REPAIR',dict(attempt=reference_attempt+1,code=str(exc)[:4096]))
            if reference_attempt==2:
                raise ValueError('INDEPENDENT_REFERENCE_EXECUTION_FAILED') from exc
            feedback='\nPrevious independent reference (no candidate implementation supplied):\n'+ref['source']+'\nSynthetic sandbox diagnostic DATA; repair execution only, keep contract unchanged:\n'+str(exc)[:4096]
    # Detect slow per-cell Python before exposing a full market panel. The
    # performance fixture has no numerical-oracle claim; the three independent
    # reference fixtures above still establish numerical and temporal checks.
    seed_panels=fixtures[0]['panels']
    performance_rows=max(1455,rows);performance_columns=5427
    performance_dates=pd.bdate_range('2019-07-01',periods=performance_rows)
    wide={f:pd.DataFrame(np.resize(frame.to_numpy(),(performance_rows,performance_columns)),index=performance_dates,
                        columns=[f'S{i:04d}' for i in range(performance_columns)]) for f,frame in seed_panels.items()}
    fixtures.append(dict(name='market_scale_synthetic_performance',data_class='synthetic',panels=wide,
                         performance_only=True,timeout=30,oracle_basis='resource check only; independent numeric fixtures checked separately'))
    result=develop(contract,fixtures,client,ledger,confirmed_contract_sha256=sha256_obj(contract))
    if result['status']!='SYNTHETIC_VALIDATED':
        raise ValueError('AUTONOMOUS_ALGORITHM_'+result['status'])
    bundle=dict(version=VERSION,source=result['source'],source_sha256=result['source_sha256'],
                contract=contract,contract_sha256=key,engine_sha256=engine_sha(),validation=result['history'][-1]['validation'])
    validate(bundle)
    ledger.write_artifact(f'autonomous_algorithms/{key}.bundle.json',bundle)
    return bundle
