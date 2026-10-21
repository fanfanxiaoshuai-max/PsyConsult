"""Regression gates for scoped v2 evidence and exclusion of unverified claims."""
import copy
import json
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.evidence_dataset import normalize_v2
from core.graph.validator import validate
from core.graph.repository import GraphRepository
from core.graph.retriever import retrieve,format_result

@pytest.fixture
def data(): return normalize_v2()

def test_evidence_coverage_and_directional_conditions(data):
    report=validate(data)
    assert report['source_checked_relations']==30
    assert report['cn_records']==24 and report['us_supplement_records']==6
    checked=[e['evidence'] for e in data['relations'] if e['reasoning_eligible']]
    assert all(sum(e['drug']==d for e in checked)==6 for d in ['舍曲林','帕罗西汀','氟西汀','奥氮平','锂盐'])
    records={e['id']:e for e in checked}
    assert records['F01']['washout_days']=={'maoi_to_drug':14,'drug_to_maoi':35}
    assert records['S01']['washout_days']=={'maoi_to_drug':14,'drug_to_maoi':14}
    assert records['F04']['concentration_directions']==['increase','decrease']
    assert all(e['expert_review']=='pending' for e in checked)
    assert all(e['region']=='US' and '非缓释' in e['formulation'] for e in checked if e['id'].startswith('L'))

@pytest.mark.parametrize('field',['conditions','population','pages','region','formulation','label_revision'])
def test_missing_scope_fails_closed(data,field):
    edge=next(e for e in data['relations'] if e['reasoning_eligible'])
    edge['evidence'].pop(field)
    with pytest.raises(ValueError): validate(data)

@pytest.mark.parametrize('field,value',[('sha256','bad'),('url','javascript:alert(1)'),('used_for_claims',False),('pages',[999]),('catalog_id','other')])
def test_invalid_proof_fails_closed(data,field,value):
    source=next(s for s in data['sources'] if s['id'].startswith('evidence:'))
    source[field]=value
    with pytest.raises(ValueError): validate(data)

class MemoryRepository(GraphRepository):
    def __init__(self,data): self.version='kg_v2';self.data=data
    def entities(self): return self.data['entities']
    def sources(self,ids): return [s for s in self.data['sources'] if s['id'] in ids]
    def _read(self,query,**params):
        return [{'payload':json.dumps(e)} for e in self.data['relations'] if e['source'] in params['ids'] or e['target'] in params['ids']]

def test_unverified_edge_and_properties_excluded_from_agent(data):
    repo=MemoryRepository(data)
    result=retrieve(repo,'帕罗西汀和舍曲林合用相互作用')
    assert result['edges']==[]
    assert result['class_context']['edges']
    assert all('properties' not in e for e in result['nodes']+result['candidates'])
    assert all(e['reasoning_eligible'] for e in result['class_context']['edges'])
    text=format_result(result)
    assert 'https://' in text and '临床专家' in text and '2022-05-25' in text
    assert any(r['status']=='unsupported_absolute_contraindication' for r in data['review'])

def test_browse_toggle_and_no_invented_pair(data):
    repo=MemoryRepository(data)
    drug=next(e for e in data['entities'] if e['name']=='舍曲林' and e['label']=='Drug')
    safe=repo.neighbors([drug['id']])
    all_edges=repo.neighbors([drug['id']],include_unreviewed=True,limit=100)
    assert len(safe['edges'])==6
    assert len(all_edges['edges'])>6
    assert all(e['reasoning_eligible'] for e in safe['edges'])
    result=retrieve(repo,'氟西汀和锂盐合用相互作用')
    assert len(result['edges'])==1
    assert result['edges'][0]['evidence']['id']=='F04'


def test_old_dataset_unchanged(data):
    from core.graph.normalizer import normalize
    old=normalize()
    assert len(old['relations'])==376
    assert not any('reasoning_eligible' in e for e in old['relations'])
    assert {e['id'] for e in old['relations']} <= {e['id'] for e in data['relations']}

def test_report_preserves_conditions_without_invented_monitoring(data):
    from core.graph.evidence_report import render_evidence_report
    result=retrieve(MemoryRepository(data),'氟西汀与锂盐合用及MAOI换药相互作用')
    report=render_evidence_report(format_result(result))
    assert '升高和降低' in report and '至少5周' in report and '至少14天' in report
    assert '每3' not in report and '每月' not in report
    assert '2025-02-05' in report and '#page=22' in report
    assert '美国标签为补充资料' in report and '临床专家审核待完成' in report

@pytest.mark.parametrize('payload',['unavailable','[]','null','{}'])
def test_report_unavailable_never_claims_safety(payload):
    from core.graph.evidence_report import render_evidence_report
    report=render_evidence_report(payload)
    assert '暂时不可用' in report and '不能据此判断安全' in report


def test_report_class_context_not_converted_into_pair_contraindication(data):
    from core.graph.evidence_report import render_evidence_report
    result=retrieve(MemoryRepository(data),'帕罗西汀与舍曲林合用相互作用')
    report=render_evidence_report(format_result(result))
    assert '未在当前图谱找到已核对的直接证据' in report
    assert '不构成对所讨论药物对的直接禁忌确认' in report
    assert '帕罗西汀 → 舍曲林' not in report
    assert '程序代理' in report and '医院' in report

def test_report_us_evidence_retains_region_and_formulation(data):
    from core.graph.evidence_report import render_evidence_report
    result=retrieve(MemoryRepository(data),'锂盐和NSAIDs相互作用')
    report=render_evidence_report(format_result(result))
    assert '美国标签补充（不代表中国批准范围）' in report
    assert '非缓释制剂' in report and '2026-08' in report and '#page=12' in report

def test_v2_drug_node_generates_from_evidence_without_model(monkeypatch,data):
    from types import SimpleNamespace
    import config
    import core.graph.repository as repository
    import agents.drug_review_agent as module
    from langchain_core.messages import HumanMessage
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(kg_version='kg_v2'))
    monkeypatch.setattr(repository,'GraphRepository',lambda:MemoryRepository(data))
    from core.graph import runtime_version
    monkeypatch.setattr(runtime_version,'current_repository',lambda:MemoryRepository(data))
    events=[]
    monkeypatch.setattr(module,'get_stream_writer',lambda:events.append)
    queries=[]
    def invoke(args):
        queries.append(args['query'])
        return format_result(retrieve(MemoryRepository(data),args['query']))
    monkeypatch.setattr(module,'query_knowledge_graph',SimpleNamespace(invoke=invoke))
    node=module.DrugReviewAgentNode.__new__(module.DrugReviewAgentNode)
    import asyncio
    result=asyncio.run(node({'messages':[HumanMessage(content='氟西汀和锂盐合用及MAOI换药')]}))
    answer=result['messages'][0].content
    assert '至少5周' in answer and '升高和降低' in answer
    assert '每3' not in answer and len(queries)==1
    assert ''.join(e.get('chunk','') for e in events)==answer

def test_evidence_json_pointers_and_publisher_survive_agent_format(data):
    raw=json.loads((ROOT/'knowledge_sources/evidence.json').read_text(encoding='utf-8'))
    for source in data['sources']:
        if source['id'].startswith('evidence:'):
            assert raw[source['pointer'].removeprefix('/')]==source['original']
    from core.graph.evidence_report import render_evidence_report
    result=retrieve(MemoryRepository(data),'氟西汀和锂盐合用相互作用')
    assert '礼来医学网' in render_evidence_report(format_result(result))

@pytest.mark.parametrize('query,canonical', [('抑郁症','抑郁障碍'),('双相情感障碍','双相障碍')])
def test_common_disease_names_match_without_merging_subtypes(data,query,canonical):
    from core.graph.retriever import rank_entities
    before=copy.deepcopy(data['entities'])
    matches=rank_entities(query,data['entities'])
    assert matches and all(e['name']==canonical for e in matches)
    assert any(e['label']=='Disease' for e in matches)
    assert {e['id'] for e in matches}=={e['id'] for e in data['entities'] if e['name']==canonical and e['label'] in ('Disease','DifferentialDiagnosis')}
    assert data['entities']==before
    result=retrieve(MemoryRepository(data),query)
    assert any(e['name']==canonical for e in result['candidates'])
    assert not any(e.get('reasoning_eligible') is False for e in result['edges'])
