"""Legacy fresh-install bootstrap. Existing deployments must use the reviewed release transaction.

Layout (all new paths; existing identities only, no group or ACL change):
  /opt/jijigua-quant-agent/v1beta            root:root 0755 code + venv (not writable by any Agent identity)
  /opt/jijigua-quant-agent/v1beta/deploy/host.json, rolling/broker.json   root 0600
  /var/lib/jijigua-quant-agent/v1beta                quantagent 0700: research_runs, state, papers, home
  /var/lib/jijigua-quant-agent/v1beta_staging        root 0700: scp landing zone for quant-paper
  /var/lib/jijigua-quant-agent/v1beta_rolling        root 0755
      snapshots   root:quanteval 0750     requests root:quanteval 0750     receipts root:quantagent 0750
      staging     quantpub 0700           eval     quanteval 0700 (ledger, outbox)   audit root 0700
      evaluator.json, rolling.key root:quanteval 0440
Real 2026 rolling evaluation stays authorized=false here until the operator approves production.
"""
import grp
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import sys

import argparse

_args = argparse.ArgumentParser(description='configure one v1 deployment (default: the v1beta production layout)')
_args.add_argument('--name', default='v1beta', choices=('v1beta', 'v1rc'), help='v1rc = isolated pre-release staging copy')
_args.add_argument('--venv', default=None, help='python venv to run (default: <root>/.venv); staging reuses the read-only v1beta venv')
_args.add_argument('--test-fault-injection', action='store_true', help='staging only: corrupt one model JSON reply per process')
ARGS = _args.parse_args()
R = Path('/opt/jijigua-quant-agent') / ARGS.name
W = Path('/var/lib/jijigua-quant-agent') / ARGS.name
S = Path('/var/lib/jijigua-quant-agent') / (ARGS.name + '_staging')
RR = Path('/var/lib/jijigua-quant-agent') / (ARGS.name + '_rolling')
VENV = Path(ARGS.venv) if ARGS.venv else R / '.venv'
PROD = Path('/opt/jijigua-quant-agent/research_agent')
if ARGS.test_fault_injection and ARGS.name == 'v1beta':
    raise SystemExit('fault injection is never configured for the production layout')


def ids(user, group=None):
    return pwd.getpwnam(user).pw_uid, grp.getgrnam(group or user).gr_gid


def directory(path, uid, gid, mode):
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise SystemExit('refusing link ' + str(path))
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def write(path, value, uid, gid, mode):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, bytes) else '', encoding='utf-8')
    os.chown(temp, uid, gid)
    os.chmod(temp, mode)
    os.replace(temp, path)


def main():
    if os.geteuid() != 0:
        raise SystemExit('root required')
    if (R / 'deploy/host.json').exists():
        raise SystemExit('Existing deployment: use release_tool; bootstrap refuses to replace its configuration')
    agent, agent_g = ids('quantagent')
    evaluator, evaluator_g = ids('quanteval')
    publisher, publisher_g = ids('quantpub')
    root = (0, 0)
    directory(W, agent, agent_g, 0o700)
    for sub in ('research_runs', 'state', 'papers', 'home', 'home/matplotlib'):
        directory(W / sub, agent, agent_g, 0o700)
    directory(S, *root, 0o700)
    directory(RR, *root, 0o755)
    directory(RR / 'snapshots', 0, evaluator_g, 0o750)
    directory(RR / 'requests', 0, evaluator_g, 0o750)
    directory(RR / 'receipts', 0, agent_g, 0o750)
    directory(RR / 'staging', publisher, publisher_g, 0o700)
    directory(RR / 'eval', evaluator, evaluator_g, 0o700)
    directory(RR / 'eval' / 'outbox', evaluator, evaluator_g, 0o755)
    directory(RR / 'eval' / 'mpl', evaluator, evaluator_g, 0o700)
    directory(RR / 'audit', *root, 0o700)
    directory(R / 'deploy' / 'rolling', *root, 0o700)
    key = RR / 'rolling.key'
    if not key.exists():
        with key.open('xb') as out:
            out.write(secrets.token_bytes(32))
    os.chown(key, 0, evaluator_g)
    os.chmod(key, 0o440)
    write(RR / 'evaluator.json', dict(key_path=str(key), snapshot_root=str(RR / 'snapshots'), ledger_path=str(RR / 'eval/ledger.sqlite'),
                                      evaluator_uid=evaluator, outbox=str(RR / 'eval/outbox'), synthetic=False), 0, evaluator_g, 0o440)
    # Research configuration: the same published Train/Validation releases as production, read-only.
    resources = json.loads((PROD / 'config/resources.json').read_text(encoding='utf-8'))
    resources['resources'] = [r for r in resources['resources'] if r['id'] in ('gpushare:train2020_2023', 'gpushare:validation2024_2025')]
    research = json.loads((PROD / 'config/research.json').read_text(encoding='utf-8'))
    research = dict(research, workspace=str(W), paper_root=str(W / 'papers'), require_rolling_test=True,
                    resources={k: v for k, v in research['resources'].items() if k in ('gpushare:train2020_2023', 'gpushare:validation2024_2025')})
    (R / 'config').mkdir(exist_ok=True)
    write(R / 'config/resources.json', resources, 0, 0, 0o644)
    write(R / 'config/research.json', research, 0, 0, 0o644)
    baseline = next(r for r in resources['resources'] if r['id'] == 'gpushare:train2020_2023')['path']
    broker = dict(synthetic=False, authorized=False, research_root=str(W / 'research_runs'), agent_uid=agent, agent_group='quantagent',
                  snapshot_root=str(RR / 'snapshots'), staging_root=str(RR / 'staging'), request_dir=str(RR / 'requests'),
                  receipt_dir=str(RR / 'receipts'), audit_path=str(RR / 'audit/broker.jsonl'), key_path=str(key),
                  source_root='/srv/quant-market/daily_update', baseline_manifest=baseline, listing_candidate=True,
                  approval_ref='NOT_YET_APPROVED', evaluator_config=str(RR / 'evaluator.json'),
                  evaluator=dict(user='quanteval', python=str(VENV / 'bin/python'), code_path=[str(R / 'src'), str(R / 'src/rolling_test/vendor')],
                                 cwd=str(RR / 'eval'), mpl_dir=str(RR / 'eval/mpl'), outbox=str(RR / 'eval/outbox'), timeout=300))
    write(R / 'deploy/rolling/broker.json', broker, 0, 0, 0o600)
    host = dict(root=str(R), agent_python=str(VENV / 'bin/python'), runner=str(R / 'deploy/run_v1.py'), state_dir=str(W / 'state'),
                agent_home=str(W / 'home'), resources_manifest=str(R / 'config/resources.json'), research_config=str(R / 'config/research.json'),
                paper_staging=str(S), rolling=dict(receipt_dir=str(RR / 'receipts'), broker_code=str(R / 'src'),
                runtime_python=str(VENV / 'bin/python'), config=str(R / 'deploy/rolling/broker.json')))
    if ARGS.test_fault_injection:
        host['test_fault_injection'] = True
    write(R / 'deploy/host.json', host, 0, 0, 0o600)
    print(json.dumps(dict(configured=True, rolling_authorized=broker['authorized'], workspace=str(W), staging=str(S), rolling=str(RR))))


if __name__ == '__main__':
    main()
