"""Apply an explicit, source-bound offline audit batch without activating a graph."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from core.graph.audit import apply_batch

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch',type=Path)
    args=parser.parse_args()
    print(json.dumps(apply_batch(args.batch),ensure_ascii=False,indent=2))
