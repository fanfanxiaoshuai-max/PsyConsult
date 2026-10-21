"""Search the offline structured candidate, without enabling it in the running app."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read
from core.graph.remediation import validate_candidate
from core.graph.structured_candidate import inspect_candidate

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('query');p.add_argument('--limit',type=int,default=20)
    args=p.parse_args()
    if not 1<=args.limit<=100:p.error('--limit must be between 1 and 100')
    data=read(ROOT/'mock_data/kg_v3_candidate/candidate.json')
    validate_candidate(data,ROOT)
    print(json.dumps(inspect_candidate(data,args.query,args.limit),ensure_ascii=False,indent=2))
