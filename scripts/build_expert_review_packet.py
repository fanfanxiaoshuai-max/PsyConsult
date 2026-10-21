import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.expert_review import write_packet
if __name__=='__main__':print(json.dumps(write_packet(ROOT),ensure_ascii=False,indent=2))
