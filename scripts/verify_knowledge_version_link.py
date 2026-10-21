"""Live A/B/A acceptance using synthetic questions; restores the starting active release."""
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from dotenv import dotenv_values
from core.graph.audit import digest,write

def verify():
    env=dotenv_values(ROOT/'agent/.env');opener=build_opener(ProxyHandler({}))
    run_id=uuid4().hex[:12];user='version_acceptance_'+run_id
    headers={'Authorization':'Bearer '+env.get('API_AUTH_TOKEN',''),'X-User-Id':user,'Content-Type':'application/json'}
    def request(path,body=None):
        req=Request('http://127.0.0.1:5000/api/'+path,headers=headers,
            data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None)
        with opener.open(req,timeout=180) as response:return response.read().decode()
    def get(path):return json.loads(request(path))
    def change(action,**kwargs):
        state=get('knowledge-workbench/status')
        return json.loads(request('knowledge-workbench/'+action,dict(revision=state['revision'],**kwargs)))
    checks=[];turns=[]
    def passed(case,**kwargs):checks.append(dict(case=case,passed=True,**kwargs))
    initial=get('knowledge-workbench/status');a=initial['active'];assert a,'Enable the initial release first'
    hits=get('knowledge-workbench/search?'+urlencode(dict(q='帕罗西汀',view='active')))
    detail=get('knowledge-workbench/entities/'+hits['items'][0]['id']+'?view=active')
    record=detail['records'][0];item=record['audit_item_ids'][0]
    exported=get('knowledge-workbench/export')
    original=next(r['project_review'] for r in exported['review_rows'] if r['item_id']==item)
    assert original['status']=='approved'
    query='仅做药物资料审查，不要鉴别诊断或治疗方案。帕罗西汀相关的不良反应和适用条件有哪些？'
    # Different scoped records can legitimately share an audited summary; compare immutable IDs.
    marker=record['id']
    def chat(label,version,expect_cache):
        events=[json.loads(line[6:]) for line in request('chat',dict(query=query,session_id='link_'+run_id+'_'+label)).splitlines() if line.startswith('data: ')]
        assert events[-1].get('done') and not any(e.get('error') or e.get('failed') for e in events),events[-1]
        assert all(e.get('knowledge_version')==version for e in events)
        hit=any(e.get('cache_hit') for e in events);assert hit==expect_cache,(label,hit)
        answer=''.join(e.get('content','') for e in events if e.get('agent') and not e.get('status'))
        turns.append(dict(label=label,knowledge_version=version,cache_hit=hit,answer=answer))
        passed('live_chat_'+label,version=version,cache_hit=hit)
        return answer
    modified=False;b=None
    try:
        answer=chat('A',a,False);assert marker in answer
        chat('A_cache',a,True)
        change('review',item_id=item,status='returned',note='版本联动验收：暂时排除一条记录以验证差异，结束后恢复')
        modified=True
        try:state=change('publish',note='版本联动验收 B：单条记录差异')
        except HTTPError as error:
            if error.code!=409:raise
            exported=get('knowledge-workbench/export')
            key=digest({r['item_id']:r['project_review']['status'] for r in exported['review_rows']})
            state=get('knowledge-workbench/status')
            b=next(r['id'] for r in state['releases'] if r['decisions_sha256']==key and r['source_sha256']==state['working_sha256'])
        if b is None:b=state['releases'][0]['id']
        change('activate',release_id=b)
        assert get('knowledge-graph/stats')['version']==b
        passed('browser_tracks_B',version=b)
        answer=chat('B',b,False);assert marker not in answer
        passed('B_omits_returned_record',record_id=record['id'])
        change('rollback')
        assert get('knowledge-workbench/status')['active']==a
        answer=chat('A_restored',a,True);assert marker in answer
        passed('rollback_restores_A_record',record_id=record['id'])
    finally:
        if modified:change('review',item_id=item,status=original['status'],note=original['note'])
        state=get('knowledge-workbench/status')
        if state['active']!=a:change('activate',release_id=a)
    assert get('knowledge-graph/stats')['version']==a
    passed('starting_release_restored',version=a)
    result=dict(checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),scope='synthetic_live_chat_version_link',
        passed=len(checks),failed=0,release_a=a,release_b=b,checks=checks,turns=turns)
    write(ROOT/'docs/KNOWLEDGE-VERSION-LINK-ACCEPTANCE.json',result)
    return result

if __name__=='__main__':
    result=verify();print(json.dumps({k:v for k,v in result.items() if k in {'passed','failed','release_a','release_b'}},ensure_ascii=False))
