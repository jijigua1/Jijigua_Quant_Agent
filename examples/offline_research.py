"""Reproducible synthetic Train/Validation report, PKL and figures. No API or server."""
import argparse
import json
import hashlib
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('demo_output'))
    args=parser.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)  # no silent overwrite of earlier runs
    from v1beta_fixtures import REVERSAL, TRAIN, build, context
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    started=time.monotonic()
    fx=build(out)
    backend=QuantBackend(ResourceCatalog(fx['manifest']),fx['config'])
    # No rolling broker is attached. Test stays NOT_RUN/NOT_EVALUATED, not a real 2026 claim.
    from research_agent.contracts import fingerprint
    ctx=context()
    core=ROOT/'src/research_agent'
    ctx['core_code_sha256']=fingerprint({p.relative_to(core).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in sorted(core.rglob('*.py'))})
    result=backend.expression_study(TRAIN,REVERSAL,'Synthetic reversal engineering example','offline reproducibility',5,5,'raw',ctx)
    run=Path(result.get('report_artifact_path') or Path(result['factor_path']).parents[1])
    record={'data_kind':'synthetic','seconds':round(time.monotonic()-started,3),'result':result,
            'html':str(run/'reports/report.html'),'factor_pkl':result['factor_path']}
    (out/'demo_result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='result'},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
