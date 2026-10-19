"""Causal, bounded expression DAGs. No source code, eval, paths or callbacks."""
import math

from .contracts import ContractError, fingerprint, object_schema, validate

VERSION = '1.0.0'
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')
UNARY = {'neg', 'abs', 'cs_rank', 'cs_zscore'}
WINDOW = {'delay', 'diff', 'returns', 'rolling_mean', 'rolling_std', 'rolling_rank'}
BINARY = {'add', 'sub', 'mul', 'div', 'min', 'max', 'rolling_corr'}
OPS = ('field', 'constant', *sorted(UNARY | WINDOW | BINARY))
NODE = object_schema({'op': {'enum': list(OPS)}, 'field': {'enum': list(FIELDS)},
    'value': {'type': 'number', 'minimum': -1e6, 'maximum': 1e6},
    'window': {'type': 'integer', 'minimum': 1},
    'args': {'type': 'array', 'maxItems': 2, 'items': {'type':'integer','minimum':0,'maximum':39}}}, required=['op'])
SCHEMA = object_schema({'nodes':{'type':'array','minItems':1,'maxItems':40,'items':NODE},
    'output':{'type':'integer','minimum':0,'maximum':39}})


def inspect(expression):
    validate(expression, SCHEMA)
    fields = set()
    histories=[];depths=[];formulas=[];units=[]
    for i,node in enumerate(expression['nodes']):
        op = node['op']
        keys = {'op'}
        arity = 0
        if op == 'field':
            keys.add('field'); fields.add(node.get('field'))
        elif op == 'constant':
            keys.add('value')
            if type(node.get('value')) not in (int, float) or not math.isfinite(node['value']):
                raise ContractError('finite constant required')
        else:
            keys.add('args'); arity = 2 if op in BINARY else 1
            if op in WINDOW or op == 'rolling_corr':
                keys.add('window')
        if set(node) != keys or len(node.get('args', [])) != arity:
            raise ContractError('expression operator arguments invalid')
        if 'window' in keys and (type(node.get('window')) is not int or node['window'] < 1):
            raise ContractError('window must be a positive historical offset')
        if op in {'rolling_std', 'rolling_corr'} and node['window'] < 2:
            raise ContractError('dispersion requires window >= 2')
        args=node.get('args',[])
        if any(type(x) is not int or not 0<=x<i for x in args):
            raise ContractError('expression edges must reference earlier nodes')
        depth=max((depths[x] for x in args),default=0)+1
        if depth>8:raise ContractError('expression depth budget exceeded')
        history = max((histories[x] for x in args), default=0)
        history += node.get('window', 0) - (1 if op.startswith('rolling_') else 0)
        if op=='field':unit=(0,1) if node['field']=='volume' else (1,1) if node['field']=='amount' else (1,0)
        elif op=='constant':unit=(0,0)
        elif op in {'returns','cs_rank','cs_zscore','rolling_rank','rolling_corr'}:unit=(0,0)
        elif op in {'mul','div'}:
            sign=1 if op=='mul' else -1;unit=tuple(a+sign*b for a,b in zip(units[args[0]],units[args[1]]))
        elif op in {'add','sub','min','max'}:
            a,b=(units[x] for x in args)
            zero=[expression['nodes'][x]['op']=='constant' and expression['nodes'][x]['value']==0 for x in args]
            if a!=b and not any(zero):raise ContractError('incompatible expression units')
            unit=b if zero[0] else a
        else:unit=units[args[0]]
        units.append(unit)
        histories.append(history);depths.append(depth)
        formulas.append(node['field'] if op=='field' else str(node['value']) if op=='constant' else
            op+'('+','.join([formulas[x] for x in args]+([str(node['window'])] if 'window' in node else []))+')')
    output=expression['output']
    if output!=len(expression['nodes'])-1:
        raise ContractError('expression output must be final node')
    reachable={output}
    for i in range(output,-1,-1):
        if i in reachable:reachable.update(expression['nodes'][i].get('args',[]))
    if len(reachable)!=len(expression['nodes']):raise ContractError('unused expression nodes denied')
    if not fields:
        raise ContractError('a factor must depend on observed data')
    return dict(operator_version=VERSION, expression=expression, expression_sha256=fingerprint(expression),
        input_fields=sorted(fields), nodes=len(histories), warmup_observations=histories[output],formula=formulas[output],
        output_units={'price_power':units[output][0],'volume_power':units[output][1]},
        available_time='T close after all required input observations; historical publication time requires data contract',
        zero_denominator='NaN', rolling_min_periods='full window', rank_ties='average', std_ddof=1)


def compute(expression, panels, *, max_cells=100000):
    import numpy as np
    import pandas as pd
    definition = inspect(expression)
    anchor = panels['close']
    if not 1 <= max_cells <= 8_000_000 or anchor.size > max_cells or any(not panels[f].index.equals(anchor.index) or
        not panels[f].columns.equals(anchor.columns) for f in definition['input_fields']):
        raise ContractError('expression input axes/size invalid')
    results=[]
    uses=[0]*len(expression['nodes'])
    for node in expression['nodes']:
        for arg in node.get('args',[]): uses[arg]+=1
    def run(node):
        op = node['op']
        if op == 'field': return panels[node['field']]
        if op == 'constant': return anchor * 0 + node['value']
        a = results[node['args'][0]]; w = node.get('window')
        if op == 'neg': return -a
        if op == 'abs': return a.abs()
        if op == 'delay': return a.shift(w)
        if op == 'diff': return a - a.shift(w)
        if op == 'returns': return a / a.shift(w).replace(0, np.nan) - 1
        if op == 'cs_rank': return a.rank(axis=1, method='average', pct=True)
        if op == 'cs_zscore': return a.sub(a.mean(axis=1), axis=0).div(a.std(axis=1, ddof=1).replace(0, np.nan), axis=0)
        if op == 'rolling_mean': return a.rolling(w, min_periods=w).mean()
        if op == 'rolling_std': return a.rolling(w, min_periods=w).std(ddof=1)
        if op == 'rolling_rank':
            return a.rolling(w, min_periods=w).rank(method='average',pct=True)
        b = results[node['args'][1]]
        if op == 'add': return a + b
        if op == 'sub': return a - b
        if op == 'mul': return a * b
        if op == 'div': return a / b.replace(0, np.nan)
        if op == 'min': return np.minimum(a, b)
        if op == 'max': return np.maximum(a, b)
        if op == 'rolling_corr': return a.rolling(w, min_periods=w).corr(b)
        raise ContractError('unregistered expression operator')
    for node in expression['nodes']:
        results.append(run(node).replace([np.inf, -np.inf], np.nan))
        for arg in node.get('args',[]):
            uses[arg]-=1
            if uses[arg]==0: results[arg]=None
    return results[expression['output']]
