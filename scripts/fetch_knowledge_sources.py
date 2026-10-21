"""Fetch only the catalogued public documents; verify PDF bytes, retain local hashes."""
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]

def fetch():
    path=ROOT/'knowledge_sources/catalog.json'
    catalog=json.loads(path.read_text(encoding='utf-8'))
    out=ROOT/'.tools/knowledge_sources';out.mkdir(parents=True,exist_ok=True)
    for source in catalog:
        if source.get('availability')=='unavailable_404':
            continue
        file=out/(source['id']+'.pdf')
        if not file.exists():
            request=Request(source['url'],headers={'User-Agent':'Mozilla/5.0'})
            with urlopen(request,timeout=45) as response:
                data=response.read(20_000_001)
            if not data.startswith(b'%PDF') or len(data)>20_000_000:
                raise ValueError('Not an acceptable PDF: '+source['id'])
            file.write_bytes(data)
        digest=hashlib.sha256(file.read_bytes()).hexdigest()
        if source.get('sha256') and source['sha256']!=digest:
            raise ValueError('Source changed; review a new catalog version: '+source['id'])
        source.setdefault('sha256',digest)
        source.setdefault('retrieved_at',date.today().isoformat())
        source.setdefault('local_snapshot','.tools/knowledge_sources/'+file.name)
        path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(source['id'],len(file.read_bytes()),digest,flush=True)
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': fetch()
