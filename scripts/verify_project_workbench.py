"""Read-only live acceptance after the UI publish/activate/rollback walkthrough."""
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from dotenv import dotenv_values
from core.graph.audit import read,write

def verify():
    env=dotenv_values(ROOT/'agent/.env')
    opener=build_opener(ProxyHandler({}))
    headers={'Authorization':'Bearer '+env.get('API_AUTH_TOKEN',''),'X-User-Id':'project_acceptance'}
    checks=[]
    def get(path,params=None):
        url='http://127.0.0.1:5000/api/'+path+('?' + urlencode(params) if params else '')
        with opener.open(Request(url,headers=headers),timeout=45) as r:return json.load(r)
    def passed(case,**details):checks.append(dict(case=case,passed=True,**details))
    status=get('knowledge-workbench/status')
    assert status['total']==899 and status['counts']==dict(approved=787,disabled=44,blocked=68)
    assert status['active'] and any(r['id']==status['active'] for r in status['releases'])
    passed('project_status_and_active_release',counts=status['counts'],active=status['active'])
    for view in ['working','active']:
        for query in ['抑郁症','双相情感障碍','失眠','帕罗西汀','6A72']:
            hits=get('knowledge-workbench/search',dict(q=query,view=view));assert hits['total']>0
            detail=get('knowledge-workbench/entities/'+hits['items'][0]['id'],dict(view=view))
            assert detail['records']
            passed('query_and_detail',view=view,query=query,records=len(detail['records']))
    for state,count in [('approved',787),('blocked',68),('disabled',44)]:
        rows=get('knowledge-workbench/reviews',dict(status=state,limit=1))
        assert rows['total']==count
        passed('project_review_filter',status=state,count=count)
    export=get('knowledge-workbench/export');assert len(export['review_rows'])==899
    assert 'expert_review' not in json.dumps(export) and 'expert_name' not in json.dumps(export)
    passed('project_ledger_export_without_expert_form')
    # Invalid/stale operations must not mutate the live project.
    req=Request('http://127.0.0.1:5000/api/knowledge-workbench/publish',
        data=json.dumps(dict(revision=-1,note='invalid')).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
    try:opener.open(req);raise AssertionError('Expected validation error')
    except HTTPError as e:assert e.code==422
    assert get('knowledge-workbench/status')['revision']==status['revision']
    passed('invalid_mutation_rejected')
    active=get('knowledge-graph/stats');assert active['version']==status['active'] and env.get('KG_VERSION')=='kg_v2'
    receipt=read(ROOT/'knowledge_sources/v3/receipts/2026-10-20-remainder-03.json')
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in receipt['active_kg_v2_files'].items())
    passed('graph_browser_tracks_release_and_baseline_archive_unchanged')
    with opener.open('http://127.0.0.1:5173/',timeout=15) as r:assert r.status==200
    passed('frontend_http')
    result=dict(checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),passed=len(checks),failed=0,
        scope='project_internal_review_and_knowledge_workspace',active=status['active'],checks=checks)
    write(ROOT/'docs/PROJECT-WORKBENCH-ACCEPTANCE.json',result)
    return result

if __name__=='__main__':
    result=verify();print(json.dumps(dict(passed=result['passed'],failed=0),ensure_ascii=False))
