"""Parse the original synthetic note without a model, network or copyrighted PDF."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main():
    from paper_research.document import ingest_document
    from paper_research.extract import extract_research_spec
    from paper_research.spec import validate_research_spec, export_research_spec
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('demo_output/paper_run_01'))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    doc=ingest_document(ROOT/'examples/synthetic_factor_note.md',allowed_roots=[ROOT/'examples'])
    spec=extract_research_spec(doc);validation=validate_research_spec(spec,doc)
    assert validation['valid'],validation
    export_research_spec(spec,args.output)
    (args.output/'document.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'data_kind':'synthetic original note','validation':validation,'research_claim':'not_reproduced',
                      'output':str(args.output.resolve())},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
