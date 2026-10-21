import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'agent'))
from core.graph.normalizer import normalize
from core.graph.validator import validate
from core.graph.retriever import rank_entities, retrieve, matches_group

@pytest.fixture(scope='module')
def dataset():
    return normalize()

def test_complete_and_deterministic(dataset):
    assert dataset == normalize()
    report=validate(dataset)
    assert report['entities']==214
    assert report['relations']==376
    unresolved=[r for r in dataset['resolutions'] if r['kind']=='unresolved_edge']
    assert len(unresolved)==13
    assert all(r['source_id'] in {s['id'] for s in dataset['sources']} for r in unresolved)

def test_dangling_and_missing_provenance_rejected(dataset):
    broken=copy.deepcopy(dataset)
    broken['relations'][0]['target']='nonexistent'
    broken['entities'][0]['source_ids']=[]
    with pytest.raises(ValueError, match='Dangling'):
        validate(broken)

CASES=[
 ('舍曲林','舍曲林','Drug'),('舍曲林有哪些副作用','舍曲林','Drug'),
 ('Sertraline','舍曲林','Drug'),('sertraline side effects','舍曲林','Drug'),
 ('帕罗西汀','帕罗西汀','Drug'),('Paroxetine','帕罗西汀','Drug'),
 ('氟西汀','氟西汀','Drug'),('Fluoxetine','氟西汀','Drug'),
 ('奥氮平','奥氮平','Drug'),('Olanzapine','奥氮平','Drug'),
 ('锂盐','锂盐','Drug'),('Lithium','锂盐','Drug'),
 ('精神分裂症','精神分裂症','Disease'),('精神分裂症','精神分裂症','DifferentialDiagnosis'),
 ('双相障碍','双相障碍','Disease'),('双相障碍','双相障碍','DifferentialDiagnosis'),
 ('抑郁发作有什么症状','抑郁发作','Disease'),('失眠','失眠','Symptom'),
 ('患者睡不着怎么办','失眠','Symptom'),('睡不好','失眠','Symptom'),
 ('舍曲林与帕罗西汀合用','舍曲林','Drug'),('舍曲林与帕罗西汀合用','帕罗西汀','Drug'),
]
@pytest.mark.parametrize('query,name,label',CASES)
def test_query_candidates(dataset,query,name,label):
    rows=rank_entities(query,dataset['entities'])
    assert any(e['legacy_id']==name and e['label']==label for e in rows)
    if query in ('Sertraline','舍曲林'):
        assert rows[0]['legacy_id']=='舍曲林'

def test_unknown_and_cypher_input_do_not_become_commands(dataset):
    for q in ('完全不存在的实体XYZ987','\" MATCH (n) DETACH DELETE n //'):
        assert rank_entities(q,dataset['entities'])==[]

def test_pair_filter_and_group_before_limit(dataset):
    class MemoryRepository:
        version='test'
        def entities(self): return dataset['entities']
        def neighbors(self,ids,group='all',limit=40,pair_ids=None):
            edges=[r for r in dataset['relations'] if (r['source'] in ids or r['target'] in ids) and matches_group(r['type'],group)]
            if pair_ids: edges=[r for r in edges if r['source'] in pair_ids and r['target'] in pair_ids]
            return dict(edges=edges[:limit],truncated=len(edges)>limit)
    result=retrieve(MemoryRepository(),'舍曲林与帕罗西汀合用',limit=1)
    assert result['edges']
    candidates={e['id'] for e in result['candidates'] if e['label']=='Drug'}
    assert all(e['source'] in candidates and e['target'] in candidates for e in result['edges'])
