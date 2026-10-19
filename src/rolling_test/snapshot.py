"""Deterministic rolling 2026 snapshots of the six approved daily_update fields.

Version id: rolling_<certified end YYYYMMDD>_<first 12 hex of the six-source fingerprint>. Identical sources reuse the
existing snapshot. The latest trading day is derived from the decoded date axis and its completeness, never from mtime.
A snapshot holds every 2026 observation row plus WARMUP_DAYS earlier rows (2024-2025, the exposed Validation span),
on the fixed baseline security axis; pre-listing cells and the two identity conflicts are masked exactly as in the
reviewed Train/Validation/one-time-Test publications.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

from . import WARMUP_DAYS
from .factors import fingerprint

FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')
VERSION = 'rolling-test-release/1'
IDENTITY_EXCLUSIONS = ('001914.SZ', '302132.SZ')
COMPLETENESS_RATIO = 0.90      # last day kept only if its close coverage >= 90% of the median of the previous 20 days


class SnapshotError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda: src.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def checked_file(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise SnapshotError('PATH_LINK_DENIED')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > maximum:
        raise SnapshotError('FILE_DENIED')
    return path


def version_id(certified_end, source):
    return 'rolling_' + certified_end.replace('-', '') + '_' + fingerprint(source)[:12]


def select_rows(dates, close_counts, *, warmup=WARMUP_DAYS, today=None):
    """dates: sorted YYYYMMDD strings (decoded axis); close_counts: finite close cells per date.

    Returns (row indexes, certified_end YYYY-MM-DD, quality dict). Trailing incomplete days are dropped, not filled."""
    import numpy as np
    dates = list(dates)
    counts = np.asarray(close_counts, dtype=float)
    if dates != sorted(set(dates)) or len(dates) != len(counts):
        raise SnapshotError('DATE_AXIS')
    if today is not None:
        future = [d for d in dates if d > today]
        if future:
            raise SnapshotError('FUTURE_DATES_IN_SOURCE')
    end = len(dates)
    dropped = []
    while end > 21:
        reference = float(np.median(counts[end - 21:end - 1]))
        if reference > 0 and counts[end - 1] >= COMPLETENESS_RATIO * reference:
            break
        dropped.append(dates[end - 1])
        end -= 1
    test = [i for i in range(end) if dates[i] >= '20260101']
    if not test:
        raise SnapshotError('NO_2026_OBSERVATIONS')
    if type(warmup) is not int or warmup < 1:
        raise SnapshotError('WARMUP_BOUND')
    history_start = '20200101' if warmup > WARMUP_DAYS else '20240101'
    before = [i for i in range(end) if history_start <= dates[i] < '20260101'][-warmup:]
    if len(before) < warmup:
        raise SnapshotError('INSUFFICIENT_WARMUP_HISTORY')
    rows = before + test
    last = dates[rows[-1]]
    quality = dict(last_day_close_cells=int(counts[rows[-1]]),
                   reference_median_close_cells=float(np.median(counts[rows[-1] - 20:rows[-1]])),
                   dropped_incomplete_trailing_dates=sorted(dropped), completeness_ratio=COMPLETENESS_RATIO,
                   warmup_rows=len(before), test_rows=len(test))
    return rows, last[:4] + '-' + last[4:6] + '-' + last[6:], quality


def write_panel(target, *, dates, codes, fields, source, certified_end, quality, implementation, approval_ref,
                listing_info, synthetic=False):
    """Validated npy + manifest into a NEW directory (atomic rename by the caller's root step)."""
    import numpy as np
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise SnapshotError('TARGET_EXISTS')
    if set(fields) != set(FIELDS):
        raise SnapshotError('FIELDS')
    shape = (len(dates), len(codes))
    for f, a in fields.items():
        if a.shape != shape or a.dtype != np.float64 or np.isinf(a).any() or (
                ((a < 0) if f in ('volume', 'amount') else (a <= 0)).any()):
            raise SnapshotError('INVALID_ARRAY_' + f)
    o, h, l, c = (fields[k] for k in ('open', 'high', 'low', 'close'))
    with np.errstate(invalid='ignore'):
        bad = (h < o) | (h < c) | (h < l) | (l > o) | (l > c)
    if bad.any():
        raise SnapshotError('OHLC_INCONSISTENT')
    target.mkdir(mode=0o700)
    hashes = {}
    for f in FIELDS:
        path = target / (f + '.npy')
        with path.open('xb') as out:
            np.save(out, fields[f], allow_pickle=False)
        hashes[path.name] = digest(path)
    manifest = dict(version=VERSION, release_id=target.name, status='synthetic' if synthetic else 'PROFILED_EXPLORATORY_ONLY',
                    approval_ref=approval_ref, dates=list(dates), codes=list(codes), certified_end=certified_end,
                    test_start=next(d for d in dates if d >= '20260101'), warmup_rows=sum(d < '20260101' for d in dates),
                    units=dict(prices='CNY/share raw unadjusted', volume='100 shares/lot', amount='1000 CNY'),
                    source=source, source_fingerprint=fingerprint(source), sha256=hashes, quality=quality,
                    listing=listing_info, identity_exclusions=list(IDENTITY_EXCLUSIONS),
                    implementation=implementation, formal_backtest_ready=False, exposure='ROLLING_EXPOSED_TEST')
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False)
    (target / 'manifest.json').write_text(raw, encoding='utf-8')
    return target


def read_snapshot(target, *, expected_manifest_sha256, expected_uid=None, synthetic=False):
    """Evaluator-only reader: fingerprinted manifest and arrays, six-digit research codes, descriptive universe."""
    import numpy as np
    import pandas as pd
    target = Path(target)
    if expected_uid is not None and (not hasattr(os, 'geteuid') or os.geteuid() != expected_uid or expected_uid == 0):
        raise SnapshotError('READER_IDENTITY')
    mpath = checked_file(target / 'manifest.json', 4 * 1024 ** 2)
    if digest(mpath) != expected_manifest_sha256:
        raise SnapshotError('MANIFEST_FINGERPRINT')
    m = json.loads(mpath.read_text(encoding='utf-8'))
    if m['version'] != VERSION or m['release_id'] != target.name or set(m['sha256']) != {f + '.npy' for f in FIELDS}:
        raise SnapshotError('MANIFEST_CONTRACT')
    if (m['status'] == 'synthetic') != synthetic:
        raise SnapshotError('SYNTHETIC_REAL_MIXING_DENIED')
    dates = pd.to_datetime(m['dates'], format='%Y%m%d')
    codes = [c[:6] for c in m['codes']]
    history = int((dates < pd.Timestamp('2026-01-01')).sum())
    if type(m.get('warmup_rows')) is not int or m['warmup_rows'] != history or history < 1:
        raise SnapshotError('HISTORY_SCOPE')
    earliest = '2020-01-01' if history > WARMUP_DAYS else '2024-01-01'
    if (not dates.is_unique or not dates.is_monotonic_increasing or len(set(codes)) != len(codes)
            or len(dates) * len(codes) > 8_000_000 or str(dates.max().date()) != m['certified_end']
            or dates.min() < pd.Timestamp(earliest) or not (dates.year == 2026).any()):
        raise SnapshotError('AXES_OR_SCOPE')
    panels = {}
    for f in FIELDS:
        path = checked_file(target / (f + '.npy'), 160 * 1024 ** 2)
        if digest(path) != m['sha256'][path.name]:
            raise SnapshotError('ARRAY_FINGERPRINT')
        a = np.load(path, mmap_mode='r', allow_pickle=False)
        if a.shape != (len(dates), len(codes)) or a.dtype != np.float64:
            raise SnapshotError('ARRAY_CONTRACT')
        panels[f] = pd.DataFrame(np.array(a), index=dates, columns=codes)
    universe = panels['open'].notna() & panels['close'].notna() & panels['volume'].gt(0)
    return panels, universe, m


def synthetic_snapshot(root, *, seed=7, n_codes=60, end='2026-03-31', drop_last_partial=True):
    """Synthetic engineering snapshot (business days 2024-01-02..end); never mixed with real studies."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    days = pd.bdate_range('2024-01-02', end)
    dates = [d.strftime('%Y%m%d') for d in days]
    codes = [f'{600000 + j:06d}.SH' for j in range(n_codes)]
    close = 10 * np.exp(np.cumsum(rng.normal(0, .02, (len(days), n_codes)), axis=0))
    open_ = close * np.exp(rng.normal(0, .005, close.shape))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, .01, close.shape))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, .01, close.shape))
    volume = rng.uniform(1e3, 1e5, close.shape).round()
    amount = volume * close / 10
    fields = dict(open=open_, high=high, low=low, close=close, volume=volume, amount=amount)
    if drop_last_partial:          # an incomplete last day must be detected and trimmed
        for a in fields.values():
            a[-1, n_codes // 2:] = np.nan
    counts = np.isfinite(fields['close']).sum(axis=1)
    rows, certified_end, quality = select_rows(dates, counts)
    source = {f: dict(bytes=int(a.nbytes), sha256=hashlib.sha256(a.tobytes()).hexdigest()) for f, a in fields.items()}
    target = Path(root) / version_id(certified_end, source)
    return write_panel(target, dates=[dates[i] for i in rows], codes=codes, fields={f: a[rows] for f, a in fields.items()},
                       source=source, certified_end=certified_end, quality=quality, implementation={},
                       approval_ref='synthetic-engineering', listing_info=dict(certified=False, synthetic=True),
                       synthetic=True)
