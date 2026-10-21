"""Fetch explicitly catalogued v3 originals without modifying existing source declarations."""
import hashlib,json,sys,re
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read,write

def fetch(ids=None):
    path=ROOT/'knowledge_sources/v3/catalog.json';catalog=read(path)
    output=ROOT/'.tools/knowledge_sources/v3';output.mkdir(parents=True,exist_ok=True)
    for sid,s in catalog.items():
        if ids and sid not in ids: continue
        if not re.fullmatch(r'[A-Za-z0-9_-]+',sid): raise ValueError('Invalid source ID')
        file=output/(sid+('.pdf' if s['format']=='pdf' else '.html'))
        try:
            if not file.exists():
                with urlopen(Request(s['url'],headers={'User-Agent':'Mozilla/5.0'}),timeout=40) as response:
                    raw=response.read(20_000_001)
                if len(raw)>20_000_000 or (s['format']=='pdf' and not raw.startswith(b'%PDF')): raise ValueError('Unexpected source bytes')
                file.write_bytes(raw)
            actual=hashlib.sha256(file.read_bytes()).hexdigest()
            if s.get('sha256') and s['sha256']!=actual: raise ValueError('Original changed; create a new source record')
            s.setdefault('retrieved_at',date.today().isoformat())
            s.update(sha256=actual,last_local_integrity_check=date.today().isoformat(),local_snapshot=str(file.relative_to(ROOT)).replace('\\','/'),availability='available')
            s.pop('error',None)
            print(sid,'available',len(file.read_bytes()),flush=True)
        except Exception as exc:
            s.update(availability='unavailable',error=type(exc).__name__)
            print(sid,'unavailable',type(exc).__name__,flush=True)
        write(path,catalog)

if __name__=='__main__': fetch(sys.argv[1:] or None)
