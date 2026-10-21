"""Project review transitions, snapshot isolation, durability and API protection."""
import json
import sqlite3
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.candidate_preview import CandidatePreview
from core.graph.project_workbench import ProjectWorkbench,ProjectConflict
from app.app_main import app
from app.router import project_workbench as api
from app.app_config.settings import settings

HEADERS={'Authorization':'Bearer workbench-test','X-User-Id':'project_admin'}

@pytest.fixture(scope='module')
def source():
    store=CandidatePreview(ROOT);store.load();return store

@pytest.fixture
def manager(tmp_path,source):return ProjectWorkbench(source,tmp_path/'workbench.sqlite3')

def test_initial_status_and_original_ledger_preserved(manager):
    s=manager.status()
    assert s['counts']=={'approved':787,'disabled':44,'blocked':68}
    assert s['revision']==0 and s['active'] is None
    original=manager.store.export()
    assert original['summary']['expert_approved']==0
    assert all(r['expert_decision'] is None for r in original['rows'])

def test_review_persists_and_stale_writes_are_rejected(manager):
    item=manager.reviews(status='approved',limit=1)['items'][0]['item_id']
    s=manager.decide(0,'admin',item,'returned','请补充说明')
    assert s['counts']['returned']==1 and s['revision']==1
    assert ProjectWorkbench(manager.store,manager.path).status()==s
    with pytest.raises(ProjectConflict):manager.decide(0,'other',item,'approved','已核对')
    assert manager.status()['revision']==1
    s=manager.decide(1,'admin',item,'approved','已核对')
    assert s['counts']['approved']==787

@pytest.mark.parametrize('status',['blocked','disabled'])
def test_unsubstantiated_and_withdrawn_cannot_be_approved(manager,status):
    item=manager.reviews(status=status,limit=1)['items'][0]['item_id']
    with pytest.raises(ProjectConflict):manager.decide(0,'admin',item,'approved','同意')
    assert manager.status()['revision']==0

def test_publish_activate_query_rollback_and_snapshot_immutability(manager):
    s=manager.publish(0,'admin','首版');first=s['releases'][0]['id']
    assert s['active'] is None and s['releases'][0]['record_count']>0
    with pytest.raises(ProjectConflict):manager.search('失眠',view='active')
    s=manager.activate(1,'admin',first)
    hit=manager.search('失眠',view='active')['items'][0]
    detail=manager.detail(hit['id'],view='active')
    record=detail['records'][0];item=record['audit_item_ids'][0]
    s=manager.decide(2,'admin',item,'returned','修订记录')
    # Working review changes cannot mutate an existing published snapshot.
    assert record in manager.detail(hit['id'],view='active')['records']
    s=manager.publish(3,'admin','退回一项后发布');second=s['releases'][0]['id']
    s=manager.activate(4,'admin',second)
    assert record not in manager.detail(hit['id'],view='active')['records']
    s=manager.rollback(5,'admin');assert s['active']==first
    assert record in manager.detail(hit['id'],view='active')['records']
    s=manager.rollback(6,'admin');assert s['active'] is None
    with pytest.raises(ProjectConflict):manager.rollback(7,'admin')
    assert s['events'][0]['action']=='rollback'

def test_duplicates_and_tampered_snapshot_fail_closed(manager):
    s=manager.publish(0,'admin','首版');uid=s['releases'][0]['id']
    with pytest.raises(ProjectConflict):manager.publish(1,'admin','重复')
    with sqlite3.connect(manager.path) as conn:
        state=json.loads(conn.execute('SELECT payload FROM state').fetchone()[0])
        state['releases'][0]['payload']['approved_item_ids']=[]
        conn.execute('UPDATE state SET payload=?',(json.dumps(state),))
    with pytest.raises(ProjectConflict):manager.activate(1,'admin',uid)

def test_project_export_has_no_expert_signature_fields(manager):
    data=manager.export()
    assert len(data['review_rows'])==899
    assert all('expert_name' not in r and 'project_review' in r for r in data['review_rows'])

def test_routes_auth_validation_transitions_and_errors(monkeypatch,manager):
    monkeypatch.setattr(api,'workbench',manager)
    monkeypatch.setattr(settings,'api_auth_token','workbench-test')
    monkeypatch.setattr(settings,'api_local_user_id','project_admin')
    client=TestClient(app);base='/api/knowledge-workbench'
    assert client.get(base+'/status').status_code==401
    assert client.post(base+'/publish',json={'revision':0,'note':'版本'}).status_code==401
    assert client.post(base+'/publish',headers=HEADERS,json={'revision':0,'note':' '}).status_code==422
    assert client.post(base+'/publish',headers=HEADERS,json={'revision':0,'note':'版本','actor':'spoof'}).status_code==422
    response=client.post(base+'/publish',headers=HEADERS,json={'revision':0,'note':'初始版本'})
    assert response.status_code==200
    s=response.json();assert s['releases'][0]['actor']=='project_admin'
    assert client.post(base+'/publish',headers=HEADERS,json={'revision':0,'note':'旧页面'}).status_code==409
    uid=s['releases'][0]['id']
    assert client.post(base+'/activate',headers=HEADERS,json={'revision':1,'release_id':uid}).status_code==200
    assert client.get(base+'/search',headers=HEADERS,params={'q':'抑郁症','view':'active'}).json()['total']>0
    assert client.get(base+'/reviews?status=blocked',headers=HEADERS).json()['total']==68
    assert client.get(base+'/export',headers=HEADERS).status_code==200
    assert client.post(base+'/rollback',headers=HEADERS,json={'revision':2}).status_code==200
    def fail():raise ValueError('password-secret')
    monkeypatch.setattr(manager,'status',fail)
    r=client.get(base+'/status',headers=HEADERS)
    assert r.status_code==503 and 'password' not in r.text
