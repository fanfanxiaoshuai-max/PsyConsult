"""Verify active graph over HTTP after backend restart, without printing credentials."""
import json
import sys
from pathlib import Path
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.infra.cache import COLLECTION_NAME

if __name__=='__main__':
    expected=sys.argv[1]
    values=dotenv_values(ROOT/'agent/.env')
    headers={'X-User-Id':'kg_activation_check','Authorization':'Bearer '+(values.get('API_AUTH_TOKEN') or '')}
    with httpx.Client(base_url='http://127.0.0.1:5000/api/knowledge-graph',headers=headers,trust_env=False,timeout=15) as client:
        stats=client.get('/stats'); stats.raise_for_status(); stats=stats.json()
        assert stats['version']==expected
        assert stats['entities']==(230 if expected=='kg_v2' else 214)
        assert stats['relations']==(423 if expected=='legacy' else 406 if expected=='kg_v2' else 376)
        result=client.get('/search',params={'q':'Sertraline'});result.raise_for_status()
        entity=result.json()['items'][0]
        assert entity['legacy_id']=='舍曲林'
        detail=client.get('/entities/'+entity['id']); detail.raise_for_status()
        neighbors=client.get('/entities/'+entity['id']+'/neighbors',params={'relation_type':'INTERACTS_WITH' if expected=='kg_v2' else 'HAS_SIDE_EFFECT'})
        neighbors.raise_for_status()
        assert neighbors.json()['edges']
        assert all(r['type']==('INTERACTS_WITH' if expected=='kg_v2' else 'HAS_SIDE_EFFECT') for r in neighbors.json()['edges'])
        if expected!='legacy': assert detail.json()['sources'] and neighbors.json()['sources']
    evidence=ROOT/'docs/KNOWLEDGE-GRAPH-ACTIVATION.json'
    data=json.loads(evidence.read_text(encoding='utf-8')) if evidence.exists() else {}
    data[expected]=dict(http_checked=True,entities=stats['entities'],relations=stats['relations'],search=True,detail=True,filtered_neighbors=True,cache_collection=COLLECTION_NAME)
    evidence.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('HTTP active graph verified:',expected,'cache:',COLLECTION_NAME)
