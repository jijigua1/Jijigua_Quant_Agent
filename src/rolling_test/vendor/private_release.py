"""Private Test snapshot adapter. Not registered with the research Agent."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import re
from research_agent.security import Denied
from research_agent.contracts import canonical

FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')
VERSION = 'private-test-release/1'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda: src.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def checked_file(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise Denied('PRIVATE_PATH_LINK_DENIED')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > maximum:
        raise Denied('PRIVATE_FILE_DENIED')
    return path


def publish_panel(target, panel, *, source, listing_dates, certified_end, approval_ref,
                  listing_source_sha256=None, implementation=None):
    """Called only after approval, in quantpub staging; root subsequently seals ownership."""
    import numpy as np
    import pandas as pd
    from release import mask_prelisting, exclude_identity_conflicts, Panel
    from qra_data.validators import Panel as AuditPanel, check_axes, check_ohlc, check_volume_amount, check_listing_bounds
    target = Path(target)
    if target.parent.resolve(strict=True) != target.parent or target.exists() or target.is_symlink():
        raise Denied('PRIVATE_PUBLICATION_TARGET_DENIED')
    dates = pd.to_datetime(panel.dates, format='%Y%m%d')
    test = dates.year == 2026
    if (set(panel.fields) != set(FIELDS) or not test.any() or dates.max() != pd.Timestamp(certified_end)
            or dates.min().year != 2025 or (~test).sum() > 120 or len(dates)*len(panel.codes) > 8_000_000
            or set(source) != set(FIELDS)):
        raise Denied('PRIVATE_PUBLICATION_SCOPE')
    if any(a.shape!=(len(dates),len(panel.codes)) or a.dtype!=np.float64 for a in panel.fields.values()):
        raise Denied('PRIVATE_DTYPE_OR_AXIS')
    if any(np.isinf(a).any() or ((a<0) if f in ('volume','amount') else (a<=0)).any() for f,a in panel.fields.items()):
        raise Denied('PRIVATE_INVALID_PRICE_OR_VOLUME')
    if any(set(s)!={'bytes','sha256'} or type(s['bytes']) is not int or not 0<s['bytes']<=128*1024**2 or
           not re.fullmatch('[0-9a-f]{64}',s['sha256']) for s in source.values()):
        raise Denied('PRIVATE_SOURCE_FINGERPRINT_REQUIRED')
    # Candidate Listdt is conservative masking, never authoritative listing certification.
    masked, count = mask_prelisting(panel, listing_dates)
    conflicts = tuple(c for c in ('001914.SZ', '302132.SZ') if c in panel.codes)
    masked, excluded = exclude_identity_conflicts(masked, conflicts)
    a = AuditPanel(list(masked.dates), list(masked.codes), masked.fields)
    findings = check_axes(a)+check_ohlc(a)+check_volume_amount(a, price_per_unit=10.0)+check_listing_bounds(a, listing_dates, {}, 'close')
    if any(f.severity == 'error' for f in findings):
        raise Denied('PRIVATE_QUALITY_GATE')
    with tempfile.TemporaryDirectory(prefix='.pending-test-', dir=target.parent) as temp:
        stage = Path(temp); hashes = {}
        for field in FIELDS:
            array = masked.fields[field]
            if array.shape != (len(dates),len(panel.codes)) or array.dtype != np.float64:
                raise Denied('PRIVATE_DTYPE_OR_AXIS')
            path = stage/(field+'.npy')
            with path.open('xb') as out:
                np.save(out, array, allow_pickle=False)
            hashes[path.name] = digest(path)
        manifest = dict(version=VERSION,release_id=target.name,status='PROFILED_EXPLORATORY_ONLY',
            approval_ref=approval_ref,dates=list(masked.dates),codes=list(masked.codes),
            test_start=str(dates[test].min().date()),test_end=certified_end,warmup_dates=int((~test).sum()),
            units=dict(prices='CNY/share raw unadjusted',volume='100 shares/lot',amount='1000 CNY'),
            source=source,sha256=hashes,listing_certified=False,prelisting_masked_close_cells=count,
            listing_candidate_sha256=listing_source_sha256,implementation=implementation or {},
            identity_exclusions=list(conflicts),identity_excluded_close_cells=excluded,
            quality_findings=[vars(f) for f in findings],formal_backtest_ready=False)
        (stage/'manifest.json').write_text(canonical(manifest,max_bytes=1024**2),encoding='utf-8')
        os.replace(stage,target)
    return target


def private_reader(target, *, expected_sha256, expected_uid=None):
    """Capability stays exclusively in the independent evaluator, with no request paths."""
    import numpy as np
    import pandas as pd
    target = Path(target)
    if expected_uid is not None and (os.geteuid() != expected_uid or expected_uid == 0):
        raise Denied('PRIVATE_READER_IDENTITY')
    manifest_path = checked_file(target/'manifest.json',1024**2)
    if digest(manifest_path) != expected_sha256:
        raise Denied('PRIVATE_MANIFEST_FINGERPRINT')
    m = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (m['version'] != VERSION or m['release_id'] != target.name or m['status'] != 'PROFILED_EXPLORATORY_ONLY'
            or set(m['sha256']) != {f+'.npy' for f in FIELDS}):
        raise Denied('PRIVATE_MANIFEST_CONTRACT')
    dates = pd.to_datetime(m['dates'],format='%Y%m%d');codes=m['codes']
    if (not dates.is_unique or not dates.is_monotonic_increasing or len(set(codes)) != len(codes)
            or len(dates)*len(codes) > 8_000_000 or dates.max() != pd.Timestamp(m['test_end'])
            or dates.min().year < 2025 or (dates.year < 2026).sum() > 120
            or not (dates.year == 2026).any() or dates.max().year != 2026):
        raise Denied('PRIVATE_AXES_OR_SCOPE')
    panels = {}
    for field in FIELDS:
        path = checked_file(target/(field+'.npy'),128*1024**2)
        if digest(path) != m['sha256'][path.name]:
            raise Denied('PRIVATE_ARRAY_FINGERPRINT')
        arr = np.load(path,mmap_mode='r',allow_pickle=False)
        if arr.shape != (len(dates),len(codes)) or arr.dtype != np.float64:
            raise Denied('PRIVATE_ARRAY_CONTRACT')
        research_codes=[c[:6] for c in codes]
        if len(set(research_codes))!=len(codes):raise Denied('PRIVATE_SECURITY_CODE_COLLISION')
        panels[field] = pd.DataFrame(arr,index=dates,columns=research_codes,copy=False)
    # Same descriptive universe as the deployed Train/Validation reader; not trade permission.
    universe = panels['open'].notna() & panels['close'].notna() & panels['volume'].gt(0)
    return panels,universe,dict(data_kind='independent_test',version=m['release_id'],sha256=expected_sha256)
