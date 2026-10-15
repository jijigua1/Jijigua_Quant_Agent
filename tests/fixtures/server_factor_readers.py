"""Original public contract probe, not the historical third-party consumer implementation.

Only call with a fresh trusted export created in the same test. Never expose as a Tool.
"""
import pandas as pd

def norm_index(frame):
    out=frame.copy()
    out.index=pd.to_datetime(out.index).strftime('%Y%m%d')
    out.columns=pd.Index([str(code).split('.')[0].zfill(6) for code in out.columns],name=frame.columns.name)
    assert out.index.is_unique and out.columns.is_unique
    return out.sort_index()

def load_and_pivot_factors(factor_path):
    values=pd.read_pickle(factor_path)  # trusted fresh writer output from the calling test only
    if not values: raise ValueError('empty factor dictionary')
    template=next(iter(values.values()))
    assert all(x.index.equals(template.index) and x.columns.equals(template.columns) for x in values.values())
    return {str(day):pd.DataFrame({name:frame.loc[day].astype('float32') for name,frame in values.items()})
            for day in template.index}
