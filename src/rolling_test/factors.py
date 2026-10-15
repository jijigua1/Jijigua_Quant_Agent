"""Frozen definitions read from a completed study, and their trusted re-computation inside the evaluator.

The broker derives the definition from the study's own files (never from the Agent's request). The evaluator computes
it with reviewed code only: the production DSL, the fixed builders, or the trusted Factor-IR executor. A human-approved,
model-written implementation is NOT executed here; its study already proved cell-by-cell equality with the same IR.
"""
import hashlib
import json

KINDS = ('fixed', 'expression', 'ir')


def fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def frozen_from_study(analysis, definition):
    """Return the frozen evaluation definition, or raise ValueError(code)."""
    params = analysis['parameters']
    if analysis.get('delivery_status') != 'VERIFIED':
        raise ValueError('STUDY_NOT_VERIFIED')
    if analysis.get('mode') != 'real_data' and analysis.get('mode') != 'synthetic':
        raise ValueError('STUDY_MODE_UNKNOWN')
    common = dict(horizon=int(params['horizon']), n_groups=int(params['n_groups']),
                  standardization=params['standardization'], lag=1, direction=1)
    if not 1 <= common['horizon'] <= 10 or not 2 <= common['n_groups'] <= 5 or common['standardization'] not in ('raw', 'zscore'):
        raise ValueError('STUDY_PARAMETERS_OUT_OF_CONTRACT')
    if definition.get('kind') == 'approved_implementation':
        if not isinstance(definition.get('ir'), dict) or not isinstance(definition.get('symbols'), dict):
            raise ValueError('APPROVED_DEFINITION_WITHOUT_TRUSTED_IR')
        spec = dict(kind='ir', ir=definition['ir'], symbols=definition['symbols'],
                    warmup=int(definition['warmup_observations']),
                    implementation_sha256=definition['source_sha256'])
    elif definition.get('kind') == 'trusted_ir':
        # The study itself ran the reviewed IR executor (no model code); the evaluator recomputes the same frozen IR.
        if not isinstance(definition.get('ir'), dict) or not isinstance(definition.get('symbols'), dict):
            raise ValueError('TRUSTED_IR_DEFINITION_INCOMPLETE')
        spec = dict(kind='ir', ir=definition['ir'], symbols=definition['symbols'],
                    warmup=int(definition['warmup_observations']),
                    implementation_sha256=definition['executor_sha256'])
        if definition.get('ir_semantics'):
            # recorded only when present, so every definition frozen before versioning keeps its SHA and its receipts
            spec['ir_semantics'] = definition['ir_semantics']
    elif definition.get('expression') is not None:
        spec = dict(kind='expression', expression=definition['expression'],
                    warmup=int(params.get('lookback') or definition.get('warmup_observations') or 2))
    elif params.get('factor_id') in ('reversal', 'volume_stall'):
        spec = dict(kind='fixed', factor_id=params['factor_id'], lookback=int(params['lookback']),
                    warmup=int(params['lookback']) + 1)
    else:
        raise ValueError('UNSUPPORTED_FACTOR_DEFINITION')
    frozen = dict(spec, **common)
    return dict(definition=frozen, definition_sha256=fingerprint(frozen), study_id=analysis['study_id'],
                study_definition_sha256=analysis.get('definition_sha256'), train_validation_data_sha256=analysis['data_sha256'],
                synthetic=analysis['mode'] == 'synthetic')


def compute(frozen, panels):
    """Evaluator side. Reviewed implementations only; output aligned to the panel axis, ±inf -> NaN."""
    import numpy as np
    d = frozen
    if d['kind'] == 'fixed':
        # The reviewed builder applies its own standardization, exactly as in the study.
        from research_agent.quant_factors import build_factor
        out = build_factor(d['factor_id'], panels['close'], panels['volume'], d['lookback'], d['standardization'])
        return out.astype(float).replace([np.inf, -np.inf], np.nan)
    if d['kind'] == 'expression':
        from research_agent.factor_expression import FIELDS, compute as dsl
        out = dsl(d['expression'], {k: v for k, v in panels.items() if k in FIELDS}, max_cells=8_000_000)
    elif d['kind'] == 'ir':
        from paper_agent.trusted_ir import evaluate
        from paper_research.factor_ir import IRError, semantics_of
        if set(d['symbols'].values()) - set(panels):
            raise ValueError('IR_FIELD_NOT_IN_SNAPSHOT')
        try:
            semantics = semantics_of(d)       # the study's own numerical semantics (version 1 when not recorded)
        except IRError:
            raise ValueError('UNSUPPORTED_IR_SEMANTICS') from None
        out = evaluate(d['ir'], panels, d['symbols'], semantics=semantics)
    else:
        raise ValueError('UNKNOWN_KIND')
    out = out.astype(float).replace([np.inf, -np.inf], np.nan)
    if d['standardization'] == 'zscore':
        out = out.sub(out.mean(axis=1), axis=0).div(out.std(axis=1, ddof=1).replace(0, np.nan), axis=0)
    ref = panels['close']
    if not out.index.equals(ref.index) or list(out.columns) != list(ref.columns):
        raise ValueError('FACTOR_AXIS_CONTRACT')
    return out
