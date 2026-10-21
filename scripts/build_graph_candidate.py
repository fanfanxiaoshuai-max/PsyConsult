"""Build the offline remediation candidate; never import or activate it."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from core.graph.remediation import write_candidate

if __name__ == '__main__':
    print(json.dumps(write_candidate(ROOT), ensure_ascii=False, indent=2))
