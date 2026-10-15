"""Two reviewed causal builders. No model-generated expression or executable code."""
import numpy as np

def build_factor(factor_id, close, volume, lookback, standardization):
    ret = close / close.shift(lookback) - 1
    if factor_id == 'reversal':
        factor = -ret
    elif factor_id == 'volume_stall':
        baseline = volume.shift(1).rolling(lookback,min_periods=lookback).mean()
        ratio = volume / baseline.where(baseline > 0)
        # Fixed smooth stall weight, not a threshold selected using future returns.
        factor = (ratio - 1).clip(lower=0) * np.exp(-ret.abs() / .02)
    else:
        raise ValueError('unreviewed factor')
    factor = factor.where(np.isfinite(factor))
    if standardization == 'zscore':
        factor = factor.sub(factor.mean(axis=1),axis=0).div(factor.std(axis=1,ddof=1).replace(0,np.nan),axis=0)
    elif standardization != 'raw':
        raise ValueError('unreviewed normalization')
    return factor
