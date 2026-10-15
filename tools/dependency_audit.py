"""Check public pinned dependency metadata with OSV. Never sends project data or secrets."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LOCKS=('requirements.lock','requirements-research.lock','requirements-paper.lock','pyproject.toml')

def pins(text):
    return re.findall(r'(?<![A-Za-z0-9_-])([A-Za-z0-9_-]+)==([0-9][A-Za-z0-9.+-]*)',text)

def request_payload():
    pairs=sorted(set(pair for name in LOCKS for pair in pins((ROOT/name).read_text(encoding='utf-8'))))
    queries=[{'package':{'name':name,'ecosystem':'PyPI'},'version':version} for name,version in pairs]
    queries.append({'package':{'name':'plotly.js','ecosystem':'npm'},'version':'2.32.0'})
    return {'queries':queries}

def check(payload,send):
    result=send(payload)
    if len(result.get('results',[]))!=len(payload['queries']):raise ValueError('invalid OSV result count')
    findings=[]
    for query,item in zip(payload['queries'],result['results']):
        for vulnerability in item.get('vulns',[]):
            findings.append({'package':query['package'],'version':query['version'],'id':vulnerability['id']})
    return {'status':'PASS' if not findings else 'BLOCKED','findings':findings,'packages':len(payload['queries'])}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'provenance/DEPENDENCY_SECURITY_CURRENT.json')
    args=p.parse_args()
    def send(payload):
        req=urllib.request.Request('https://api.osv.dev/v1/querybatch',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
    try:
        record=check(request_payload(),send)
    except (OSError,ValueError,KeyError):
        record={'status':'UNVERIFIED','findings':[],'reason':'OSV query failed; absence of findings is not a pass'}
    record.update(checked_at_utc=datetime.now(timezone.utc).isoformat(),database='OSV',
                  lock_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in LOCKS},
                  limits='Exact package/version advisory match only; no native/transitive reachability certification')
    args.output.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps(record,indent=2));return int(record['status']!='PASS')

if __name__=='__main__':raise SystemExit(main())
