"""Final publication prerequisites. This does not replace the owner's disclosure approval."""
import json
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    blocked=[]
    if not (ROOT/'LICENSE').is_file(): blocked.append('OWNER_LICENSE_NOT_SELECTED')
    review=ROOT/'provenance/RIGHTS_REVIEW.json'
    if not review.is_file():
        blocked.append('RIGHTS_REVIEW_MISSING')
    else:
        data=json.loads(review.read_text(encoding='utf-8'))
        blocked += [x['id'] for x in data['items'] if x['status'] not in ('CLEARED','EXCLUDED','INSTALL_SEPARATELY')]
    security=ROOT/'provenance/DEPENDENCY_SECURITY_CURRENT.json'
    if not security.is_file():
        blocked.append('DEPENDENCY_SECURITY_UNVERIFIED')
    else:
        check=json.loads(security.read_text(encoding='utf-8'))
        if check['status']!='PASS':blocked.append('DEPENDENCY_SECURITY_BLOCKED')
        if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha for p,sha in check.get('lock_sha256',{}).items()):
            blocked.append('DEPENDENCY_LOCK_CHANGED_AFTER_SCAN')
    print(json.dumps({'status':'BLOCKED' if blocked else 'TECHNICAL_PREREQUISITES_PASSED',
                      'blocked':blocked,'human_disclosure_approval_still_required':True},indent=2))
    return int(bool(blocked))

if __name__=='__main__':sys.exit(main())
