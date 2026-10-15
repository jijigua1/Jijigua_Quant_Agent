"""quantagent side of the OS-level rolling self-test: synthetic releases, one study, broker over the inherited socket."""
import json
import socket
import sys
from pathlib import Path

R = Path('/opt/jijigua-quant-agent/v1beta')
sys.path[:0] = [str(R / 'src'), str(R / 'src/rolling_test/vendor'), str(R / 'tests')]


def main(ws, fd, receipts):
    import os
    import v1beta_fixtures as fx_mod
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    from research_agent.rolling_client import RollingClient
    ws = Path(ws)
    (ws / 'fx').mkdir()
    fx = fx_mod.build(ws / 'fx')
    backend = QuantBackend(ResourceCatalog(fx['manifest']), fx['config'])
    backend.rolling = RollingClient(socket.socket(fileno=int(fd)), receipts)
    out = dict(uid=os.geteuid(), groups=os.getgroups(), status=backend.rolling.status())
    try:
        r = backend.expression_study(fx_mod.TRAIN, fx_mod.REVERSAL, '短期反转（系统自检）', '合成工程验收', 5, 5, 'raw', fx_mod.context())
        t = r['metrics']['professional']['test']
        consistency = json.loads((Path(r['report_artifact_path']) / 'data/report_consistency.json').read_text())
        out.update(rolling=r['rolling_test'], test_status=t['status'], evaluation_type=t.get('evaluation_type'),
                   test_rank_ic=t.get('metrics', {}).get('rank_ic_mean'), immature=len(t.get('maturity', {}).get('immature_signal_dates', [])),
                   report_revision=r['report_revision'], consistency=consistency['status'], html=r['html_path'])
        again = backend.rolling.evaluate(r['study_id'], r['artifact_path'])
        out['repeat'] = dict(status=again['status'], reused=again.get('reused'), same_id=again.get('evaluation_id') == r['rolling_test']['evaluation_id'])
    except Exception as exc:  # noqa: BLE001 - recorded in the self-test summary
        import traceback
        out['error'] = traceback.format_exc()[-1500:]
    (ws / 'result.json').write_text(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main(*sys.argv[1:])
