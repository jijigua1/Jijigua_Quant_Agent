"""Fit a research Tool result into the JSON contract (C6R4-I2).

Live C6R4-I1 (2026-10-18): after a real 2026 Rolling Test the GH study's read result was 72,241 bytes; the 64 KiB tool
contract rejected it as an unclassified error, so a complete study could no longer be shown. Any paper or report can grow
past the limit (more Test months, long paper definitions, many figures), so the fit is generic:

1. known bulky detail goes first (monthly/annual Test rows, files lists, rationale and paper texts, export details ...);
2. then, generically, the largest remaining container that is not protected.

A dropped object becomes {"omitted": "TOOL_RESULT_SIZE", "bytes": n}; a dropped list becomes []. Types never change, so the
output schema still holds. Protected (never dropped): identity, status and paths, report access, Train/Validation/Test
headline numbers, verdict, annual rows, paper hard stops, parameters, limits. Every drop is listed in
`tool_result_compacted`; nothing is removed from the study directory or the report. If the protected part alone does not
fit, a coded TOOL_RESULT_TOO_LARGE error is raised instead of an unclassified one.
"""
import copy
import json

from .contracts import MAX_JSON_BYTES, ContractError

MARGIN = 4096                       # the ToolResult wrapper, its fingerprint and the model view add a little around it
BUDGET = MAX_JSON_BYTES - MARGIN
OMITTED = 'TOOL_RESULT_SIZE'
NOTE = 'tool_result_compacted'
# dropped first, in this order: detail that the report and the study files keep in full
KNOWN = (
    ('metrics', 'professional', 'test', 'monthly'), ('metrics', 'professional', 'test', 'daily'),
    ('metrics', 'professional', 'test', 'annual'), ('metrics', 'professional', 'files'),
    ('metrics', 'professional', 'definitions'), ('economic_rationale',), ('paper_definition',), ('factor_export',),
    ('figure_paths',), ('implementation_crosscheck',), ('performance',), ('report_consistency',), ('data_partitions',),
    ('formula_rendering',), ('profile',), ('metrics', 'windows'), ('metrics', 'groups'), ('metrics', 'decay'),
    ('metrics', 'predictive'), ('metrics', 'effective_stocks'), ('metrics', 'definitions'),
)
# never dropped (the whole subtree), nor any container that holds one of them
PROTECTED = (
    ('report_access',), ('splits',), ('spec',), ('parameters',), ('paper',), ('papers',), ('evidence',), ('lookahead',),
    ('holdout',), ('test_monthly_label_status',), ('limitations',), ('profiles',), ('resources',), ('comparison',),
    ('invalidation',), ('missing',), ('fields',), ('metadata',), ('null_counts',), ('test_request',), ('rolling_test',),
    ('research_contract',), (NOTE,),
    ('metrics', 'professional', 'annual'), ('metrics', 'professional', 'partitions'), ('metrics', 'professional', 'verdict'),
    ('metrics', 'professional', 'quality'), ('metrics', 'professional', 'test', 'metrics'),
    ('metrics', 'professional', 'test', 'exposure'), ('metrics', 'professional', 'test', 'snapshot'),
    ('metrics', 'professional', 'test', 'maturity'),
)


def size(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _related_to_protected(path):
    return any(path[:len(p)] == p or p[:len(path)] == path for p in PROTECTED)


def _get(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None, None
        parent, value = value, value[key]
    return parent, value


def _containers(value, path=()):
    """Every dict/list below the top level, with its path (dict keys only: list items are never addressed one by one)."""
    if isinstance(value, dict):
        for key in sorted(value):
            child, child_path = value[key], path + (key,)
            if isinstance(child, (dict, list)):
                yield child_path, child
                if isinstance(child, dict):
                    yield from _containers(child, child_path)


def _drop(result, path, dropped):
    parent, value = _get(result, path)
    if parent is None or not isinstance(value, (dict, list)) or _related_to_protected(path):
        return False
    if (isinstance(value, dict) and value.get('omitted') == OMITTED) or value == [] or value == {}:
        return False
    dropped.append({'field': '.'.join(path), 'bytes': size(value)})
    parent[path[-1]] = {'omitted': OMITTED, 'bytes': size(value)} if isinstance(value, dict) else []
    return True


def fit(result, allows_note=True, budget=BUDGET):
    """Return `result` unchanged when it fits; otherwise a smaller deep copy with every drop listed."""
    original = size(result)
    if original <= budget:
        return result
    result, dropped = copy.deepcopy(result), []
    if allows_note:
        result[NOTE] = {'limit_bytes': MAX_JSON_BYTES, 'original_bytes': original, 'omitted': dropped,
                        'full_data': '省略的只是这次工具结果里的明细；研究目录中的报告和 data/ 文件完整保留，没有删除任何文件。'}
    for path in KNOWN:
        if _drop(result, path, dropped) and size(result) <= budget:
            break
    while size(result) > budget:
        candidates = [(size(v), '.'.join(p), p) for p, v in _containers(result)
                      if not _related_to_protected(p) and v not in ([], {}) and not (isinstance(v, dict) and v.get('omitted') == OMITTED)]
        if not candidates:
            break
        candidates.sort(key=lambda c: (-c[0], c[1]))
        if not _drop(result, candidates[0][2], dropped):
            break
    if size(result) > budget:
        raise ContractError('TOOL_RESULT_TOO_LARGE')
    return result
