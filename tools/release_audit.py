"""Offline public-release checks. Findings contain locations, never matched secrets."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '__pycache__', '.pytest_cache', 'build', 'dist', 'demo_output'}
RULES = {
    'api-secret': rb'\bsk-[A-Za-z0-9_-]{16,}',
    'github-secret': rb'\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}',
    'private-key': rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'private-host': rb'i-\d+\.gpushare\.com',
    'private-home': rb'(?i)(?:[CD]:[/\\]+Users[/\\]+(?:Kevin|KEVINW)|[CD]:[/\\]+GeorgeResearch|[CD]:[/\\]+ResearchAgent|/home/' + b'research_' + rb'wty|/hy-tmp/' + b'research_' + rb'wty)',
    'bearer-value': rb'(?i)authorization[\x20\x22\x27:=]+bearer[\x20]+[A-Za-z0-9._-]{16,}',
}
FORBIDDEN_SUFFIXES = {'.pkl','.pickle','.npy','.npz','.parquet','.pdf','.whl','.zip','.tgz','.gz','.sqlite','.db','.pem','.key','.dpapi','.ipynb'}
LARGE_ARTIFACTS = {'docs/examples/synthetic_report.html':15_000_000}  # one self-contained synthetic report with inline Plotly/images

def inspect_bytes(name, data):
    findings=[]
    for label, pattern in RULES.items():
        for match in re.finditer(pattern, data):
            findings.append({'file':name, 'line':data[:match.start()].count(b'\n')+1,'rule':label})
    if len(data)>LARGE_ARTIFACTS.get(name,5_000_000):
        findings.append({'file':name,'rule':'large-file'})
    if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
        findings.append({'file':name,'rule':'private-or-binary-artifact'})
    return findings

def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not SKIP.intersection(p.relative_to(ROOT).parts)
                  and not any(part.endswith('.egg-info') for part in p.relative_to(ROOT).parts))

def audit(history=False):
    findings=[]; rows=[]; links=[]; syntax=[]
    for p in files():
        rel=p.relative_to(ROOT).as_posix()
        if p.is_symlink() or p.stat().st_nlink != 1:
            findings.append({'file':rel,'rule':'linked-file'})
            continue
        data=p.read_bytes()
        findings.extend(inspect_bytes(rel,data))
        rows.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if p.suffix=='.py':
            try: ast.parse(data,filename=rel)
            except (SyntaxError,UnicodeError): syntax.append(rel)
        if p.suffix=='.md':
            for raw in re.findall(r'(?<!!)\[[^\]]*\]\(([^\s)]+)\)',data.decode('utf-8-sig')):
                if re.match(r'^[a-zA-Z][\w+.-]*:',raw) or raw.startswith('#'):
                    continue
                target=unquote(raw.split('#')[0]).strip('<>')
                if target and not (p.parent/target).exists(): links.append({'file':rel,'target':target})
    commits=0
    if history:
        result=subprocess.run(['git','rev-list','--all'],cwd=ROOT,capture_output=True,text=True)
        if result.returncode:
            findings.append({'file':'.git','rule':'history-unavailable'})
        else:
            for commit in result.stdout.splitlines():
                commits+=1
                listing=subprocess.check_output(['git','ls-tree','-rz',commit],cwd=ROOT)
                for row in listing.split(b'\0'):
                    if not row: continue
                    meta,name=row.split(b'\t',1);kind=meta.split()[1]
                    if kind!=b'blob': continue
                    obj=meta.split()[2].decode()
                    data=subprocess.check_output(['git','cat-file','blob',obj],cwd=ROOT)
                    findings.extend({**x,'commit':commit} for x in inspect_bytes(name.decode(),data))
    return {'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'findings':findings,'broken_links':links,
            'syntax_failures':syntax,'history_commits_checked':commits,'inventory':rows,
            'status':'PASS' if not findings and not links and not syntax else 'FAIL',
            'limitations':['Pattern scanning is not a proof of absence; manual provenance and licence review are required.']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--history',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=audit(args.history)
    if args.output: args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={k:v for k,v in result.items() if k!='inventory'}
    print(json.dumps(summary,ensure_ascii=False,indent=2));return int(result['status']!='PASS')

if __name__=='__main__': raise SystemExit(main())
