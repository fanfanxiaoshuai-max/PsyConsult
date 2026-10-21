from fastapi.testclient import TestClient
from app.app_main import app
from app.app_config.settings import settings
from app.service import knowledge_graph_service as service

client=TestClient(app)
HEADERS={'Authorization':'Bearer test-graph','X-User-Id':'doctor_test'}

def test_graph_auth_and_bounds(monkeypatch):
    monkeypatch.setattr(settings,'api_auth_token','test-graph')
    monkeypatch.setattr(settings,'api_local_user_id','doctor_test')
    assert client.get('/api/knowledge-graph/stats').status_code==401
    assert client.get('/api/knowledge-graph/stats',headers={**HEADERS,'X-User-Id':'../bad'}).status_code==400
    assert client.get('/api/knowledge-graph/search?q=x&limit=999',headers=HEADERS).status_code==422
    assert client.get('/api/knowledge-graph/search?q=%20',headers=HEADERS).status_code==422

def test_search_and_unavailable(monkeypatch):
    monkeypatch.setattr(settings,'api_auth_token','test-graph')
    monkeypatch.setattr(settings,'api_local_user_id','doctor_test')
    monkeypatch.setattr(service,'search',lambda q,limit:dict(version='test',items=[],total=0,truncated=False))
    assert client.get('/api/knowledge-graph/search?q=xyz',headers=HEADERS).json()['items']==[]
    def unavailable(): raise ConnectionError('internal password must not be exposed')
    monkeypatch.setattr(service,'stats',unavailable)
    response=client.get('/api/knowledge-graph/stats',headers=HEADERS)
    assert response.status_code==503
    assert 'password' not in response.text

def test_missing_entity(monkeypatch):
    monkeypatch.setattr(settings,'api_auth_token','test-graph')
    monkeypatch.setattr(settings,'api_local_user_id','doctor_test')
    monkeypatch.setattr(service,'detail',lambda uid:None)
    assert client.get('/api/knowledge-graph/entities/missing',headers=HEADERS).status_code==404


def test_graph_cache_versions_are_separate():
    from app.infra.cache import cache_collection_name
    assert cache_collection_name('legacy')=='qa_semantic_cache'
    assert cache_collection_name('kg_v1')!=cache_collection_name('legacy')
    assert cache_collection_name('kg_v1')!=cache_collection_name('kg_v2')
    assert cache_collection_name('kg_v1')==cache_collection_name('kg_v1')
