"""Approved Skill validators. A Skill cannot supply executable validator code."""

import re

from .contracts import ContractError, validate
from .tools import DATA_HASH

class EvidenceRequired(ContractError):
    pass


def _mock_research(plan, experiments):
    factors = [x for x in experiments if x["tool"] == "compute_mock_factor"]
    windows = {x["parameters"].get("lookback") for x in factors}
    if not {3, 5}.issubset(windows):
        raise ContractError("Mock acceptance requires windows 3 and 5")
    if any(x["result"]["data"].get("data_sha256") != DATA_HASH or
           x["result"]["data"].get("mode") != "synthetic" for x in factors):
        raise ContractError("Mock evidence has invalid provenance")
    return {"mode": "synthetic", "summary": plan["summary"], "factor_experiments": len(factors)}


def _data_query(plan, experiments):
    evidence = [x["result"]["data"] for x in experiments if x["tool"] in {"describe_resource", "read_data_slice"}]
    if not evidence or any(x.get("mode") not in {"real_data", "synthetic"} or not x.get("data_sha256") for x in evidence):
        raise ContractError("data query requires validated descriptive evidence")
    return {"mode": "real_data" if any(x["mode"] == "real_data" for x in evidence) else "synthetic",
            "summary": plan["summary"], "resource_ids": sorted({x["resource_id"] for x in evidence}),
            "analysis_scope": "data_description"}


PAPER_STUDY_GOAL = re.compile(r'研究|提取|因子|复现|定义|factor|study|replicat', re.I)


def _quant_research(plan, experiments, *, skill_id, goal=''):
    if skill_id=='paper_research':
        # A requested paper study needs this task's own paper tool result: a listing, or an earlier turn's result about
        # another paper, is not evidence (live J1/J6: "already blocked" was claimed for a paper that was never read).
        listing_only = re.search(r'列出|列表|有哪些|哪些论文|上传了什么|\blist', goal or '', re.I)
        if PAPER_STUDY_GOAL.search(goal or '') and not listing_only and not any(x['tool']=='qrtk_paper_research' for x in experiments):
            raise EvidenceRequired('PAPER_STUDY_NOT_CALLED')
        # Library listings, unresolved/ambiguous paper references and BLOCKED readings are honest catalog answers.
        listing=[x['result']['data'] for x in experiments if x['tool'] in ('paper_list','qrtk_paper_research') and x['result']['data'].get('mode')=='catalog']
        if listing and not any(x['tool']=='qrtk_paper_research' and x['result']['data'].get('mode')!='catalog' for x in experiments):
            return {'mode':'catalog','summary':plan['summary'],'analysis_scope':listing[-1]['analysis_scope'],'resource_ids':[]}
    evidence=[x['result']['data'] for x in experiments if x['tool'].startswith('qrtk_') and x['result']['data'].get('mode')!='catalog']
    catalogs=[x['result']['data'] for x in experiments if x['tool']=='list_research_resources']
    if not evidence and skill_id=='data_research' and catalogs:
        return {'mode':'catalog','summary':plan['summary'],'analysis_scope':'resource_catalog',
            'resource_ids':sorted({r['id'] for r in catalogs[-1]['resources']})}
    if not evidence:
        raise EvidenceRequired('Skill needs an authorized qrtk computation, readiness check or verified study read')
    if any(x.get('mode') not in {'real_data','synthetic'} or not x.get('data_sha256') for x in evidence):
        raise ContractError('quant acceptance requires actual computation or readiness evidence')
    studies=[x for x in evidence if x.get('study_id')]
    if any(x.get('delivery_status')!='VERIFIED' for x in studies if 'factor_export' in x or x.get('implementation_version') in ('0.3.0','0.4.0')):
        raise ContractError('new factor delivery requires verified PKL')
    if any(x.get('splits',{}).get('test')!='sealed' or x.get('formal_backtest_ready') is not False for x in studies):
        raise ContractError('unapproved test reveal or market claim')
    result={'mode':evidence[-1]['mode'],'summary':plan['summary'],
            'analysis_scope':evidence[-1]['analysis_scope'],'resource_ids':sorted({x['resource_id'] for x in evidence})}
    if studies:
        result['study_id']=studies[-1]['study_id'];result['artifact_path']=studies[-1]['artifact_path']
        result['report_path']=studies[-1]['report_path']
    return result

VALIDATORS = {"mock_research_v1": _mock_research, "data_query_v1": _data_query, 'quant_research_v1':_quant_research}


def accept_result(skill, plan, experiments, goal=''):
    validator = VALIDATORS.get(skill.validator_id)
    if validator is None:
        raise ContractError("unregistered Skill validator")
    result = validator(plan, experiments, skill_id=skill.id, goal=goal) if skill.validator_id=='quant_research_v1' else validator(plan, experiments)
    validate(result, skill.output_schema)
    return result
