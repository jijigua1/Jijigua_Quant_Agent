"""Synthetic engineering fixtures for v1.0 Beta: published Train/Validation releases, a rolling 2026 snapshot built from the
same synthetic market, and an in-process broker on a socketpair. Synthetic results never enter real reports."""
import hashlib
import json
import os
import socket
import threading
from pathlib import Path

import sys

import numpy as np
import pandas as pd

_VENDOR = str(Path(__file__).resolve().parents[1] / 'src' / 'rolling_test' / 'vendor')
if _VENDOR not in sys.path:
    sys.path.append(_VENDOR)   # reviewed qra_data validators used by the production publisher

TRAIN = 'synthetic:train2020_2023'
VALID = 'synthetic:validation2024_2025'
KEY = b'k' * 32


def market(seed=11, n_codes=40, end='2026-03-31', shock_2025=False):
    """Business days 2020-01-02..end; weak short-term reversal so the 5-day reversal factor has a positive IC."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range('2020-01-02', end)
    days = days[np.arange(len(days)) % 15 != 7]   # synthetic holidays keep each split below 1000 sessions
    n = len(days)
    noise = rng.normal(0, .02, (n, n_codes))
    r = np.zeros_like(noise)
    for t in range(n):
        past = r[max(0, t - 5):t].sum(axis=0)
        r[t] = -0.06 * past + noise[t]
    close = 10 * np.exp(np.cumsum(r, axis=0))
    if shock_2025:   # a revised history: Validation-period prices differ from the published release
        close[(days >= '2025-12-10') & (days <= '2025-12-12')] *= 1.03   # a revised print inside the overlap window
    open_ = close * np.exp(rng.normal(0, .004, close.shape))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, .01, close.shape))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, .01, close.shape))
    volume = rng.uniform(1e3, 1e5, close.shape).round()
    amount = volume * close / 10
    codes = [f'{600000 + j:06d}.SH' for j in range(n_codes)]
    return days, codes, dict(open=open_, high=high, low=low, close=close, volume=volume, amount=amount)


def build(tmp_path, *, shock_2025=False, paper_root=True, snapshot_end=None, snapshot_warmup=330):
    from research_agent.published_release import Panel, publish
    days, codes, fields = market()
    releases = tmp_path / 'releases'
    releases.mkdir()
    records = []
    for split, (lo, hi), rid in (('train', ('2020-01-01', '2023-12-31'), TRAIN), ('validation', ('2024-01-01', '2025-12-31'), VALID)):
        keep = (days >= lo) & (days <= hi)
        panel = Panel(tuple(d.strftime('%Y%m%d') for d in days[keep]), tuple(codes), {f: a[keep].copy() for f, a in fields.items()})
        source = {'files': {f: {'sha256': hashlib.sha256(a.tobytes()).hexdigest()} for f, a in fields.items()}}
        target = publish(releases, split, 'baseline_synth_v1', panel, source=source, listing_dates={c: '20000101' for c in codes})
        manifest = target / 'manifest.json'
        records.append(dict(id=rid, path=str(manifest), format='published_npy', source='synthetic engineering market',
                            approval_ref='synthetic', data_kind='synthetic', frequency='daily', timezone='Asia/Shanghai',
                            start_date=str(days[keep][0].date()), end_date=str(days[keep][-1].date()), date_column='date',
                            fields={'date': 'date', 'code': 'string', **{f: 'float' for f in fields}},
                            adjustment='none: raw unadjusted market prices', available_time='synthetic',
                            sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), partition=split,
                            release_id='baseline_synth_v1', access_status='PROFILED_EXPLORATORY_ONLY'))
    (tmp_path / 'resources.json').write_text(json.dumps(dict(version='1', withheld_from='2026-01-01', resources=records)), encoding='utf-8')
    workspace = tmp_path / 'workspace'
    (workspace / 'research_runs').mkdir(parents=True)
    contract = dict(adjustment='none', volume_unit='lots', calendar='observed_union', available_time='synthetic T-close',
                    corporate_actions='not_modelled', universe='synthetic fixed axis', limits=['synthetic engineering data'],
                    research_use='exploratory_raw_price')
    config = dict(version='1', workspace=str(workspace), resources={TRAIN: contract, VALID: contract},
                  validation_pairs={TRAIN: VALID})
    if paper_root:
        config['paper_root'] = str(tmp_path / 'papers')
    (tmp_path / 'research.json').write_text(json.dumps(config), encoding='utf-8')
    # Rolling snapshot from the same (or a revised) synthetic market.
    from rolling_test.snapshot import select_rows, version_id, write_panel
    sdays, scodes, sfields = market(shock_2025=shock_2025)
    if snapshot_end:   # a longer 2026: the same history with later sessions appended (as new trading days arrive)
        ldays, _, longer = market(end=snapshot_end)
        sfields = {k: np.concatenate([a, longer[k][len(sdays):]]) for k, a in sfields.items()}
        sdays = ldays
    keep = sdays >= ('2020-01-01' if snapshot_warmup > 330 else '2024-01-01')
    d = [x.strftime('%Y%m%d') for x in sdays[keep]]
    f = {k: a[keep].copy() for k, a in sfields.items()}
    rows, end, quality = select_rows(d, np.isfinite(f['close']).sum(axis=1),warmup=snapshot_warmup)
    src = {k: dict(bytes=int(a.nbytes), sha256=hashlib.sha256(a.tobytes()).hexdigest()) for k, a in sfields.items()}
    snaps = tmp_path / 'rolling_private'
    snaps.mkdir()
    target = write_panel(snaps / version_id(end, src), dates=[d[i] for i in rows], codes=scodes, fields={k: a[rows] for k, a in f.items()},
                         source=src, certified_end=end, quality=quality, implementation={}, approval_ref='synthetic',
                         listing_info=dict(certified=False, synthetic=True), synthetic=True)
    snap = dict(version=target.name, manifest_sha256=hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(), certified_end=end)
    return dict(manifest=tmp_path / 'resources.json', config=tmp_path / 'research.json', workspace=workspace,
                snapshot=snap, snapshot_root=snaps, tmp=tmp_path, market=(days, codes, fields))


def broker(fx, *, authorized=True):
    """In-process synthetic broker on a socketpair; returns (RollingClient, Broker)."""
    from research_agent.rolling_client import RollingClient
    from rolling_test.broker import Broker, serve
    from rolling_test.evaluator import evaluate
    tmp = fx['tmp']
    for name in ('requests', 'receipts', 'eval'):
        (tmp / name).mkdir(exist_ok=True)
    (tmp / 'rolling.key').write_bytes(KEY)
    config = dict(synthetic=True, authorized=authorized, research_root=str(fx['workspace'] / 'research_runs'),
                  synthetic_snapshot=fx['snapshot'], snapshot_root=str(fx['snapshot_root']), request_dir=str(tmp / 'requests'),
                  receipt_dir=str(tmp / 'receipts'), audit_path=str(tmp / 'broker_audit.jsonl'), key_path=str(tmp / 'rolling.key'),
                  approval_ref='synthetic')

    def runner(request_path):
        request = json.loads(Path(request_path).read_text(encoding='utf-8'))
        return evaluate(request, snapshot_root=fx['snapshot_root'], ledger_path=tmp / 'eval' / 'ledger.sqlite', key=KEY, synthetic=True)
    b = Broker(config, runner=runner)
    if os.name != 'posix':
        # Windows socketpair is a loopback TCP connection, forbidden by the offline test guard; keep the JSON round trip.
        class DirectClient(RollingClient):
            def _call(self, request):
                from rolling_test.protocol import MAX_REQUEST, ProtocolError
                raw = json.dumps(request, ensure_ascii=False, sort_keys=True)
                if len(raw.encode()) > MAX_REQUEST:
                    raise ProtocolError('MESSAGE_TOO_LARGE')
                return json.loads(json.dumps(b.handle(json.loads(raw))))
        return DirectClient(object(), tmp / 'receipts', require_foreign_owner=False), b
    agent, parent = socket.socketpair()   # AF_UNIX on Linux: the real inherited-FD transport
    threading.Thread(target=serve, args=(parent, b), daemon=True).start()
    return RollingClient(agent, tmp / 'receipts', require_foreign_owner=False), b   # in-process broker: same uid


def context(task_id='a' * 32, events=None):
    import time as _time
    events = events if events is not None else []

    class Store:
        path = 'synthetic-ledger'
    return dict(task_id=task_id, session_id='s' * 32, goal='合成三阶段研究', store=Store(), core_code_sha256='0' * 64,
                provider={'provider': 'mock'}, emit=lambda kind, payload: events.append((kind, payload)),
                deadline=_time.monotonic() + 1800, authorized_resources=(TRAIN, VALID), hypothesis='短期反转',
                change_reason='合成工程验收')


REVERSAL = {'nodes': [{'op': 'field', 'field': 'close'}, {'op': 'returns', 'args': [0], 'window': 5}, {'op': 'neg', 'args': [1]}], 'output': 2}
