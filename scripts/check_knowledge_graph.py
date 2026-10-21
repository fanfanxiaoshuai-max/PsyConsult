"""Integration gate for dataset isolation, idempotence, provenance and retrieval."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
sys.path.insert(0,str(ROOT))
from core.graph.repository import GraphRepository
from core.graph.retriever import retrieve, rank_entities
from scripts.build_knowledge_graph import build
from app.test.test_knowledge_graph_data import CASES

def check(reimport=True):
    report={'synthetic_queries_only': True}
    repo=GraphRepository('kg_v1')
    print('Checking dataset stats...',flush=True)
    first=repo.stats()
    if reimport:
        print('Checking repeat import...',flush=True)
        build()
        assert repo.stats()==first
    if reimport:
        report['idempotent_import']=True
    elif (ROOT/'docs/KNOWLEDGE-GRAPH-VERIFICATION.json').exists():
        previous=json.loads((ROOT/'docs/KNOWLEDGE-GRAPH-VERIFICATION.json').read_text(encoding='utf-8'))
        report['idempotent_import']=previous.get('idempotent_import',False) if previous.get('digest')==first['digest'] else False
    print('Checking fixed retrieval cases...',flush=True)
    entities=repo.entities()
    report['cases']=[]
    for q,name,label in CASES:
        matches=rank_entities(q,entities)
        assert any(e['legacy_id']==name and e['label']==label for e in matches),q
        report['cases'].append({'query':q,'expected_name':name,'expected_label':label,'passed':True})
    report['relation_checks']=[]
    for q in ['舍曲林有哪些副作用','抑郁发作有什么症状','舍曲林与帕罗西汀合用']:
        result=retrieve(repo,q)
        assert result['edges'],q
        assert result['sources']
        assert all(e['source_ids'] for e in result['edges'])
        report['relation_checks'].append(dict(query=q,edges=len(result['edges']),sources=len(result['sources']),passed=True))
    print('Checking legacy isolation...',flush=True)
    legacy=GraphRepository('legacy').stats()
    assert legacy['entities']==214 and legacy['relations']==423
    report.update(legacy_preserved=True,entities=first['entities'],relations=first['relations'],pending=len(first['pending']),digest=first['digest'])
    (ROOT/'docs/KNOWLEDGE-GRAPH-VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Graph integration checks passed.',flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skip-reimport',action='store_true')
    check(not p.parse_args().skip_reimport)
