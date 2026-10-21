"""Live read-only API, retrieval and immutable-import acceptance for kg_v2."""
import json,sys
from pathlib import Path
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'));sys.path.insert(0,str(ROOT))
from core.graph.repository import GraphRepository,close_graph_connections
from core.graph.retriever import retrieve,format_result
from scripts.build_knowledge_graph import build

def main():
    report=dict(version='kg_v2',synthetic_only=True)
    first=build(version='kg_v2'); second=build(version='kg_v2')
    assert first['digest']==second['digest']
    assert GraphRepository('kg_v1').stats()['relations']==376
    assert GraphRepository('legacy').stats()['relations']==423
    repo=GraphRepository('kg_v2')
    drugs=['舍曲林','帕罗西汀','氟西汀','奥氮平','锂盐']
    report['counts']={k:first[k] for k in ('entities','relations','sources','source_checked_relations','cn_records','us_supplement_records','digest')}
    report['drugs']={}
    for drug in drugs:
        uid=next(e['id'] for e in repo.entities() if e['label']=='Drug' and e['name']==drug)
        r=repo.neighbors([uid],limit=100)
        owned=[e for e in r['edges'] if e['source']==uid]
        assert len(owned)==6
        assert all(e['reasoning_eligible'] for e in r['edges'])
        report['drugs'][drug]=dict(owned_records=len(owned),incident_records=len(r['edges']))
    result=retrieve(repo,'帕罗西汀和舍曲林合用相互作用')
    assert not result['edges'] and result['class_context']['edges']
    assert '专家审核' in format_result(result)
    v=dotenv_values(ROOT/'agent/.env')
    headers={'X-User-Id':'kg_v2_acceptance','Authorization':'Bearer '+(v.get('API_AUTH_TOKEN') or '')}
    with httpx.Client(base_url='http://127.0.0.1:5000/api/knowledge-graph',headers=headers,trust_env=False,timeout=20) as c:
        stats=c.get('/stats');stats.raise_for_status();assert stats.json()['version']=='kg_v2'
        r=c.get('/search',params={'q':'Sertraline'});r.raise_for_status();uid=r.json()['items'][0]['id']
        safe=c.get('/entities/'+uid+'/neighbors');safe.raise_for_status()
        old=c.get('/entities/'+uid+'/neighbors',params={'include_unreviewed':'true'});old.raise_for_status()
        assert len(safe.json()['edges'])==6 and len(old.json()['edges'])>6
        assert all(s['title'] and s['pages'] and s['sha256'] for s in safe.json()['sources'])
        assert c.post('/stats').status_code==405
        report['http']=dict(version=True,search=True,source_proof=True,default_checked_only=True,explicit_legacy_toggle=True,read_only=True)
    report.update(idempotent=True,old_versions_preserved=True,unverified_absolute_contraindication_excluded=True)
    (ROOT/'docs/KNOWLEDGE-GRAPH-KG_V2-VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    close_graph_connections();print('kg_v2 API, evidence retrieval, import idempotence and old versions: passed')

if __name__=='__main__': main()
