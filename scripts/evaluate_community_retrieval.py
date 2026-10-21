"""Measure source coverage, not medical correctness. No model or vector API calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.public_support import retrieve,knowledge_version,METHOD

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--k',type=int,default=3);p.add_argument('--suite',choices=['legacy','reviewed','paraphrase'],default='legacy');args=p.parse_args()
    if args.k<1:p.error('k must be positive')
    name={'legacy':'community_retrieval.jsonl','reviewed':'community_retrieval_reviewed.jsonl','paraphrase':'community_retrieval_paraphrase.jsonl'}[args.suite]
    cases_path=ROOT/'evals'/name;raw=cases_path.read_bytes()
    cases=[json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    rows=[];behavior=[]
    for case in cases:
        if case.get('evaluation_kind')=='behavior' or case['case_id']=='KB034':behavior.append(case);continue
        error=None
        try:results=retrieve(case['query'],args.k)
        except Exception as exc:results=[];error=type(exc).__name__
        found={s['id'] for row in results for s in row['sources']};expected=set(case['expected_source_ids']);matched=expected&found
        rows.append(dict(case_id=case['case_id'],query=case['query'],expected=sorted(expected),matched=sorted(matched),missing=sorted(expected-found),
                         any_hit=(bool(matched) if expected else not results) and error is None,complete_hit=(expected<=found if expected else not results) and error is None,coverage=(len(matched)/len(expected) if expected else int(not results)) if error is None else 0,
                         error=error,results=results))
    count=len(rows)
    report=dict(knowledge_version=knowledge_version(),retrieval_method=METHOD,suite=args.suite,k=args.k,cases=count,
                testset_sha256=hashlib.sha256(raw).hexdigest(),any_source_recall=sum(r['any_hit'] for r in rows)/count,
                complete_source_hit_rate=sum(r['complete_hit'] for r in rows)/count,macro_source_coverage=sum(r['coverage'] for r in rows)/count,
                errors=sum(r['error'] is not None for r in rows),behavior_cases_excluded=behavior,
                note='Legacy expectations are unchanged; reviewed suite changes are recorded separately. Query errors count as misses. No-source queries count as correct only when retrieval is empty. Source coverage does not prove medical or answer correctness.',rows=rows)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','behavior_cases_excluded')},ensure_ascii=False))
    return 0 if all(r['complete_hit'] for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
