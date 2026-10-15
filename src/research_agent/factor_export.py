"""Fixed protocol-4 factor exports. Unknown/external pickle is never loaded."""
import hashlib,os,pickle,re,uuid,json,io,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from .security import Denied
from .artifacts import check_directory,ResearchArtifacts
from . import __version__

VERSION='server-panel-v1'

class ExportFailed(RuntimeError):
    pass

def panel(frame, *, max_cells=100000):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex):raise ValueError('dated DataFrame required')
    if not 1<=max_cells<=8_000_000 or frame.empty or frame.size>max_cells or frame.index.tz is not None or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError('factor date/size contract invalid')
    if not frame.index.equals(frame.index.normalize()):raise ValueError('daily date required')
    codes=list(frame.columns)
    if not all(isinstance(c,str) and re.fullmatch(r'\d{6}',c) for c in codes) or len(set(codes))!=len(codes):raise ValueError('six-digit unique stock codes required')
    if not all(pd.api.types.is_numeric_dtype(t) for t in frame.dtypes):raise ValueError('numeric factor required')
    x=pd.DataFrame(np.array(frame.to_numpy(),dtype='float64',order='C',copy=True),
        index=pd.Index(list(frame.index.strftime('%Y%m%d')),name='date'),columns=pd.Index(codes,name='Code'))
    if np.isinf(x.to_numpy()).any():raise ValueError('infinite factor value refused')
    x.values[np.isnan(x.values)]=np.nan  # Canonical NaN payload survives CSV-based verification.
    return x

def _atomic(path,raw):
    check_directory(path.parent)
    if path.exists() or path.is_symlink():raise Denied('FACTOR_EXPORT_ALREADY_EXISTS')
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def server_panel(frame,synthetic=False,*,published_codes=None):
    x=panel(frame,max_cells=8_000_000 if published_codes is not None else 100000)
    if published_codes is not None:
        if len(published_codes)!=len(x.columns) or any(not re.fullmatch(r'\d{6}\.(SH|SZ)',c) for c in published_codes) or list(x.columns)!=[c[:6] for c in published_codes]:
            raise Denied('PUBLISHED_FACTOR_CODE_AXIS_MISMATCH')
        x.columns=pd.Index(published_codes,name='Code')
        return x
    if synthetic:return x
    p=Path(__file__).parent/'resources/factor_format.json'
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848':raise Denied('FACTOR_FORMAT_FINGERPRINT_MISMATCH')
    mapping=json.loads(raw)['codes']
    if any(c not in mapping for c in x.columns):raise ValueError('server stock suffix not verified for this resource')
    x.columns=pd.Index([mapping[c] for c in x.columns],name='Code')
    return x

def _serialize(obj,compressed=False):
    raw=pickle.dumps(obj,protocol=4)
    if not compressed:return raw
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
        item=zipfile.ZipInfo('factor.pkl',date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;z.writestr(item,raw)
    return buf.getvalue()

def verify(path,expected,*,max_bytes=2*1024*1024):
    """Trust comes from byte equality to this process's fixed writer, not a supplied hash."""
    check_directory(path.parent)
    if not 1<=max_bytes<=80*1024*1024 or path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>max_bytes:raise Denied('FACTOR_FILE_DENIED')
    raw=path.read_bytes();safe=_serialize(expected,path.name.endswith('.zip'))
    if raw!=safe:raise Denied('UNTRUSTED_FACTOR_PICKLE')
    # Only our freshly serialized numeric panel/dictionary can reach this load.
    if path.name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:raw=z.read('factor.pkl')
    obj=pickle.loads(raw)
    if isinstance(expected,dict):
        if type(obj) is not dict or list(obj)!=list(expected):raise ValueError('factor dictionary mismatch')
        for k in expected:pd.testing.assert_frame_equal(obj[k],expected[k],check_exact=True)
    else:pd.testing.assert_frame_equal(obj,expected,check_exact=True)
    return obj

def export(run,frame,definition,provenance,*,published_codes=None):
    synthetic=provenance.get('mode')=='synthetic';x=server_panel(frame,synthetic,published_codes=published_codes);plain=panel(frame,max_cells=8_000_000 if published_codes is not None else 100000);name=provenance['parameters']['factor_id']
    if not re.fullmatch('[a-z_]{1,40}',name):raise ValueError('fixed factor name required')
    records=[]
    for file,obj,format_id in [('factor.pkl',x,'synthetic-panel-v1' if synthetic else VERSION),
                              ('factor.pkl.zip',x,'server-panel-zip-v1'),
                              ('factor_plain.pkl',plain,'plain-code-panel-v1'),('factor_dict.pkl',{name:x},'perry-dict-v1')]:
        p=run/'data'/file;_atomic(p,_serialize(obj,file.endswith('.zip')));verify(p,obj,max_bytes=80*1024*1024 if published_codes is not None else 2*1024*1024)
        records.append(dict(path=str(p),format=format_id,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    meta=dict(status='VERIFIED',format_version='synthetic-panel-v1' if synthetic else VERSION,protocol=4,writer_version='1.0.0',core_version=__version__,writer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),pandas_version=pd.__version__,numpy_version=np.__version__,
        shape=list(x.shape),index_type='Index[str YYYYMMDD]',column_type='Index[str six-digit code + observed exchange suffix]' if not synthetic else 'synthetic bare six-digit codes',multiindex=False,
        index_name=x.index.name,columns_name=x.columns.name,dtype='float64',date_start=x.index[0],date_end=x.index[-1],
        codes=list(x.columns),nan_cells=int(x.isna().sum().sum()),inf_cells=0,direction=1,definition=definition,
        axis_mapping_sha256=hashlib.sha256((Path(__file__).parent/'resources/factor_format.json').read_bytes()).hexdigest(),
        data_sha256=provenance['data_sha256'],available_time=provenance['research_contract']['available_time'],
        scope='train+validation factor values only; no future labels/test performance/account data',
        downstream='single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification',files=records)
    if published_codes is not None:
        meta.update(axis_mapping_sha256=hashlib.sha256(json.dumps(published_codes,separators=(',',':')).encode()).hexdigest(),
                    data_partitions=provenance['data_partitions'])
    ResearchArtifacts.write_json(run/'data/factor_metadata.json',meta,max_bytes=1024*1024)
    if published_codes is not None:
        meta={k:v for k,v in meta.items() if k!='codes'} | {'code_count':len(x.columns)}
    return dict(factor_path=str(run/'data/factor.pkl'),factor_metadata_path=str(run/'data/factor_metadata.json'),factor_export=meta,delivery_status='VERIFIED')
