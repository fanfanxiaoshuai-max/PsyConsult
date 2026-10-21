"""Initialize/check the frozen full-graph audit. Does not activate or modify the database."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import report
if __name__=='__main__': print(json.dumps(report(ROOT),ensure_ascii=False,indent=2))
