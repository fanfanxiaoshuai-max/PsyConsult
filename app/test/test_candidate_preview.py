"""Local preview must remain authenticated, read-only, traceable, and separate from inference."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from app.app_main import app
from app.app_config.settings import settings
from app.router import candidate_graph
from core.graph.audit import read,digest
from core.graph.candidate_preview import CandidatePreview
from core.graph.expert_review import build_packet

HEADERS={'Authorization':'Bearer preview-test','X-User-Id':'expert_demo'}
client=TestClient(app)


@pytest.fixture(scope='module')
def store():return CandidatePreview(ROOT)


@pytest.fixture(autouse=True)
def auth(monkeypatch,store):
    monkeypatch.setattr(settings,'api_auth_token','preview-test')
    monkeypatch.setattr(settings,'api_local_user_id','expert_demo')
    monkeypatch.setattr(candidate_graph,'preview',store)


def test_preview_auth_and_query_bounds():
    assert client.get('/api/candidate-graph/stats').status_code==401
    assert client.get('/api/candidate-graph/stats',headers={**HEADERS,'X-User-Id':'../bad'}).status_code==400
    for path in ['/search?q=%20','/search?q=x&limit=1000','/reviews?status=approved','/reviews?offset=-1']:
        assert client.get('/api/candidate-graph'+path,headers=HEADERS).status_code==422


@pytest.mark.parametrize('name',['抑郁症','双相情感障碍','失眠','帕罗西汀','6A72'])
def test_expected_searches_match_and_detail_is_pending(name):
    response=client.get('/api/candidate-graph/search',params={'q':name},headers=HEADERS)
    assert response.status_code==200 and response.json()['total']>0
    uid=response.json()['items'][0]['id']
    detail=client.get('/api/candidate-graph/entities/'+uid,headers=HEADERS).json()
    assert detail['activation_ready'] is False and detail['expert_review']=='pending'
    if name=='失眠':assert detail['records']  # Adverse-event target lookup, not only subject lookup.
    assert all(r['reasoning_eligible'] is False for r in detail['records'])


def test_withdrawn_entity_excluded_and_review_still_accessible():
    retired='da424821bf328794aa43279d'
    assert client.get('/api/candidate-graph/entities/'+retired,headers=HEADERS).status_code==404
    assert client.get('/api/candidate-graph/search',params={'q':'40-80mg/d'},headers=HEADERS).json()['total']==0
    queue=client.get('/api/candidate-graph/reviews',params={'q':'40-80mg/d','status':'withdrawn'},headers=HEADERS).json()
    assert queue['total']>0 and all(r['candidate_change']['after'] is None for r in queue['items'])


@pytest.mark.parametrize('status,total',[('all',899),('amended',399),('insufficient_evidence',55),('quarantined',13)])
def test_review_counts_and_pagination(status,total):
    response=client.get('/api/candidate-graph/reviews',params={'status':status,'limit':2},headers=HEADERS)
    assert response.status_code==200
    data=response.json();assert data['total']==total and len(data['items'])==2
    page=client.get('/api/candidate-graph/reviews',params={'status':status,'offset':2,'limit':2},headers=HEADERS).json()
    assert {r['item_id'] for r in data['items']}.isdisjoint(r['item_id'] for r in page['items'])


def test_expert_packet_is_unsigned_complete_and_downloadable():
    response=client.get('/api/candidate-graph/expert-packet',headers=HEADERS)
    assert response.status_code==200 and 'attachment' in response.headers['Content-Disposition']
    data=response.json()
    assert len(data['rows'])==899 and data['summary']['expert_approved']==0
    assert data['summary']['clinical_certification'] is False
    assert sum(r['medical_review_required'] for r in data['rows'])==838
    assert all(r['expert_decision'] is None and r['expert_name'] is None for r in data['rows'])
    assert 'local_snapshot' not in str(data['supplemental_sources'])
    assert client.post('/api/candidate-graph/expert-packet',headers=HEADERS,json={'approved':True}).status_code==405


def test_preview_does_not_use_repository_or_mutate_activation(monkeypatch,store):
    from core.graph.repository import GraphRepository
    monkeypatch.setattr(GraphRepository,'entities',lambda *a:pytest.fail('Preview must not read live graph'))
    stats=store.stats()
    assert stats['activation_ready'] is False and stats['read_only'] is True
    assert stats['evidence_review']['amended_items_rechecked']==399
    assert stats['evidence_review']['open_items_reexamined']==68


def test_fail_closed_without_internal_error_leak(monkeypatch):
    def fail():raise ValueError('secret-path-and-password')
    monkeypatch.setattr(candidate_graph.preview,'stats',fail)
    response=client.get('/api/candidate-graph/stats',headers=HEADERS)
    assert response.status_code==503 and 'password' not in response.text and 'secret-path' not in response.text


def test_cache_invalidation_does_not_serve_previous_candidate(tmp_path,store):
    data,packet=store.load()
    watched=tmp_path/'changed.json';watched.write_text('{}')
    isolated=CandidatePreview(tmp_path)
    isolated._data=data;isolated._packet=packet;isolated._paths=[watched];isolated._stamp=isolated._fingerprint()
    assert isolated.load()[0] is data
    watched.write_text('{"changed": true}')
    with pytest.raises(FileNotFoundError):isolated.load()
    assert isolated._data is None


def test_rechecked_packet_matches_sealed_candidate_and_preserves_open_verdicts():
    packet=build_packet(ROOT)
    sealed=read(ROOT/'knowledge_sources/v3/expert/packet.json')
    # Generation date is metadata; all sealed content and review outcomes must still match.
    packet['generated_on']=sealed['generated_on']
    assert digest(packet)==digest(sealed)
    open_rows=[r for r in packet['rows'] if r['original_status'] in {'insufficient_evidence','quarantined'}]
    assert len(open_rows)==68
    assert all(r['supplemental_review']['original_claim_enabled'] is False for r in open_rows)
    val=next(r for r in open_rows if r['item_id']=='relation:7efcc9ce0710295737b50093')
    assert val['supplemental_review']['outcome']=='case_report_signal_only'
    assert len(val['supplemental_review']['additional_source_ids'])==2
    quet=next(r for r in open_rows if r['item_id']=='relation:0e7ad968542880407cddfb87')
    assert quet['supplemental_review']['outcome']=='confounded_case_report_only'
