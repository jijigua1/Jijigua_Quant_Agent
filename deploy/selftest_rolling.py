"""Root-run OS-level self-test of ROLLING_EXPOSED_TEST on SYNTHETIC data with the real identities (no 2026 market data).

root pinned FDs -> quantpub static decode/publish -> root seal; quantagent study -> root broker -> quanteval evaluation
-> root receipt registry -> quantagent report revision; plus negative permission probes. Prints one JSON summary.
"""
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys
import tempfile
import time

R = Path('/opt/jijigua-quant-agent/v1beta')
sys.path[:0] = [str(R / 'src'), str(R / 'src/rolling_test/vendor'), str(R / 'tests')]
PY = str(R / '.venv/bin/python')


def ids(name):
    return pwd.getpwnam(name).pw_uid, grp.getgrnam(name).gr_gid


def mkdir(path, uid, gid, mode):
    path.mkdir(parents=True, exist_ok=False)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def probe(user, code):
    """Run a tiny Python statement as `user`; returns 'DENIED' on PermissionError, 'ALLOWED' otherwise."""
    program = 'import sys\ntry:\n ' + code + '\n print("ALLOWED")\nexcept PermissionError:\n print("DENIED")'
    out = subprocess.run(['/usr/sbin/runuser', '-u', user, '--', PY, '-I', '-c', program], capture_output=True, text=True, timeout=60)
    return out.stdout.strip() or out.stderr.strip()[-200:]


def main():
    import pandas as pd
    import v1beta_fixtures as fx_mod
    from rolling_test.broker import Broker, serve
    from rolling_test.publish import publish, source_spec
    stamp = time.strftime('%Y%m%d_%H%M%S')
    agent, agent_g = ids('quantagent')
    evaluator, evaluator_g = ids('quanteval')
    publisher, publisher_g = ids('quantpub')
    base = Path('/var/lib/jijigua-quant-agent/v1beta_rolling/selftest') / stamp
    base.parent.mkdir(exist_ok=True)
    os.chmod(base.parent, 0o755)
    mkdir(base, 0, 0, 0o755)
    for name, uid, gid, mode in (('snapshots', 0, evaluator_g, 0o750), ('requests', 0, evaluator_g, 0o750),
                                 ('receipts', 0, agent_g, 0o750), ('staging', publisher, publisher_g, 0o700),
                                 ('eval', evaluator, evaluator_g, 0o700), ('audit', 0, 0, 0o700)):
        mkdir(base / name, uid, gid, mode)
    mkdir(base / 'eval/outbox', evaluator, evaluator_g, 0o755)
    mkdir(base / 'eval/mpl', evaluator, evaluator_g, 0o700)
    key = base / 'rolling.key'
    key.write_bytes(os.urandom(32))
    os.chown(key, 0, evaluator_g)
    os.chmod(key, 0o440)
    # 1. synthetic daily_update-like source (pandas pickles), root-private.
    source_root = Path(tempfile.mkdtemp(prefix='qra-v1-synth-'))
    days, codes, fields = fx_mod.market()
    keep = days >= '2024-01-01'
    index = [d.strftime('%Y%m%d') for d in days[keep]]
    for f, a in fields.items():
        pd.DataFrame(a[keep], index=index, columns=codes).to_pickle(source_root / (f + '.pkl'))
    source, _ = source_spec(source_root)
    started = time.monotonic()
    row = publish(source_root=source_root, private_root=base / 'snapshots', staging_root=base / 'staging', expected_codes=codes,
                  approval_ref='selftest-synthetic', implementation={}, today='20261013', source=source, synthetic=True)
    publish_seconds = time.monotonic() - started
    again = publish(source_root=source_root, private_root=base / 'snapshots', staging_root=base / 'staging', expected_codes=codes,
                    approval_ref='selftest-synthetic', implementation={}, today='20261013', source=source, synthetic=True)
    snapshot = dict(version=row['version'], manifest_sha256=row['manifest_sha256'], certified_end=row['certified_end'])
    (base / 'evaluator.json').write_text(json.dumps(dict(key_path=str(key), snapshot_root=str(base / 'snapshots'),
        ledger_path=str(base / 'eval/ledger.sqlite'), evaluator_uid=evaluator, outbox=str(base / 'eval/outbox'), synthetic=True)))
    os.chown(base / 'evaluator.json', 0, evaluator_g)
    os.chmod(base / 'evaluator.json', 0o440)
    # 2. quantagent workspace with synthetic published Train/Validation releases.
    ws = Path('/var/lib/jijigua-quant-agent/v1beta/selftest') / stamp
    (ws.parent).mkdir(exist_ok=True)
    os.chown(ws.parent, agent, agent_g)
    os.chmod(ws.parent, 0o700)
    mkdir(ws, agent, agent_g, 0o700)
    config = dict(synthetic=True, enforce_identity=True, authorized=True, research_root=str(ws / 'fx/workspace/research_runs'),
                  agent_uid=agent, agent_group='quantagent', synthetic_snapshot=snapshot, snapshot_root=str(base / 'snapshots'),
                  request_dir=str(base / 'requests'), receipt_dir=str(base / 'receipts'), audit_path=str(base / 'audit/broker.jsonl'),
                  key_path=str(key), approval_ref='selftest-synthetic', evaluator_config=str(base / 'evaluator.json'),
                  synthetic_overlap_dates=[d[:4] + '-' + d[4:6] + '-' + d[6:] for d in index],
                  evaluator=dict(user='quanteval', python=PY, code_path=[str(R / 'src'), str(R / 'src/rolling_test/vendor')],
                                 cwd=str(base / 'eval'), mpl_dir=str(base / 'eval/mpl'), outbox=str(base / 'eval/outbox'), timeout=300))
    parent, child = socket.socketpair()
    pid = os.fork()
    if pid == 0:
        parent.close()
        os.set_inheritable(child.fileno(), True)
        os.setgroups([])
        os.setgid(agent_g)
        os.setuid(agent)
        os.execve(PY, [PY, '-I', str(R / 'deploy/selftest_agent.py'), str(ws), str(child.fileno()), str(base / 'receipts')],
                  {'PATH': '/usr/bin:/bin', 'HOME': str(ws), 'MPLCONFIGDIR': str(ws), 'OPENBLAS_NUM_THREADS': '1', 'LANG': 'C.UTF-8'})
    child.close()
    serve(parent, Broker(config))
    _, status = os.waitpid(pid, 0)
    result = json.loads((ws / 'result.json').read_text()) if (ws / 'result.json').exists() else {'error': 'agent produced no result'}
    receipts = list((base / 'receipts').glob('*.json'))
    audit = [json.loads(x) for x in (base / 'audit/broker.jsonl').read_text().splitlines()]
    previous, chain = '0' * 64, True
    for rowa in audit:
        sha = rowa.pop('sha256')
        chain &= rowa['previous'] == previous and hashlib.sha256(json.dumps(rowa, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest() == sha
        previous = sha
    snapshot_dir = base / 'snapshots' / snapshot['version']
    summary = dict(stamp=stamp, agent_exit=status, publish=dict(version=row['version'], reused_on_repeat=again['reused'],
        seconds=round(publish_seconds, 1), owner=[os.stat(snapshot_dir).st_uid, os.stat(snapshot_dir).st_gid, oct(os.stat(snapshot_dir).st_mode & 0o777)],
        status=json.loads((snapshot_dir / 'manifest.json').read_text())['status'], dropped_incomplete=row['dropped_incomplete']),
        agent=result, receipts=[dict(name=p.name, uid=p.stat().st_uid, gid=p.stat().st_gid, mode=oct(p.stat().st_mode & 0o777)) for p in receipts],
        audit_events=[a['event'] for a in audit], audit_chain_valid=chain,
        probes=dict(quantagent_reads_snapshot=probe('quantagent', f'open({str(snapshot_dir / "close.npy")!r},"rb").read(1)'),
                    quantagent_reads_key=probe('quantagent', f'open({str(key)!r},"rb").read(1)'),
                    quantagent_reads_ledger=probe('quantagent', f'open({str(base / "eval/ledger.sqlite")!r},"rb").read(1)'),
                    quanteval_writes_receipts=probe('quanteval', f'open({str(base / "receipts/x.json")!r},"w").write("x")'),
                    quantpub_reads_snapshot=probe('quantpub', f'open({str(snapshot_dir / "close.npy")!r},"rb").read(1)'),
                    quanteval_reads_snapshot=probe('quanteval', f'open({str(snapshot_dir / "close.npy")!r},"rb").read(1)')))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
