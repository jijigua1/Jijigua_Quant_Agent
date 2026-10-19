"""Frozen Python algorithm identity shared by research and the isolated evaluator."""
import hashlib
import json
from pathlib import Path

VERSION = 'isolated-python/1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def engine_sha():
    root = Path(__file__).parent
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                   for name in ('algorithm_bundle.py', 'isolated_execution.py', 'isolated_worker.py')})


def validate(bundle):
    required = {'version', 'source', 'source_sha256', 'contract', 'contract_sha256', 'engine_sha256', 'validation'}
    if set(bundle) != required or bundle['version'] != VERSION:
        raise ValueError('ALGORITHM_BUNDLE_CONTRACT')
    src = bundle['source']
    if not isinstance(src, str) or not 1 <= len(src.encode()) <= 64000:
        raise ValueError('ALGORITHM_SOURCE_SIZE')
    if hashlib.sha256(src.encode()).hexdigest() != bundle['source_sha256']:
        raise ValueError('ALGORITHM_SOURCE_CHANGED')
    contract = bundle['contract']
    if digest(contract) != bundle['contract_sha256'] or engine_sha() != bundle['engine_sha256']:
        raise ValueError('ALGORITHM_CONTRACT_OR_ENGINE_CHANGED')
    if not isinstance(contract.get('inputs'), list) or not contract['inputs'] or set(contract['inputs']) - {'open','high','low','close','volume','amount'}:
        raise ValueError('ALGORITHM_INPUT_FIELDS')
    if type(contract.get('warmup')) is not int or contract['warmup'] < 1:
        raise ValueError('ALGORITHM_HISTORY_BOUND')
    evidence = bundle['validation']
    if not evidence.get('passed') or evidence.get('source_sha256') != bundle['source_sha256'] or not evidence.get('checks'):
        raise ValueError('ALGORITHM_VALIDATION_MISSING')
    return contract


def compute(bundle, panels):
    from .isolated_execution import execute
    contract = validate(bundle)
    if set(contract['inputs']) - set(panels):
        raise ValueError('ALGORITHM_FIELD_NOT_PUBLISHED')
    return execute(bundle['source'], {k: panels[k] for k in contract['inputs']},
                   source_sha256=bundle['source_sha256'], timeout=120,
                   memory_bytes=8*1024**3, output_bytes=256*1024**2)
