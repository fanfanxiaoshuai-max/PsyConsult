"""Live localhost acceptance checks. Read the local auth token without displaying it."""
import hashlib,json,sys,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from dotenv import dotenv_values
from core.graph.audit import read,digest,write


def verify():
    env=dotenv_values(ROOT/'agent/.env')
    if env.get('KG_VERSION')!='kg_v2':raise ValueError('Expected preserved kg_v2 selection')
    opener=build_opener(ProxyHandler({}))
    headers={'Authorization':'Bearer '+env.get('API_AUTH_TOKEN',''),'X-User-Id':'acceptance_demo'}
    checks=[]
    def get(path,params=None):
        url='http://127.0.0.1:5000/api/'+path+('?' + urlencode(params) if params else '')
        with opener.open(Request(url,headers=headers),timeout=45) as r:
            assert r.status==200
            return json.load(r)
    stats=get('candidate-graph/stats')
    assert stats['activation_ready'] is False and stats['evidence_review']['expert_approved']==0
    checks.append(dict(case='candidate_unsigned_readonly',passed=True))
    for name in ['抑郁症','双相情感障碍','失眠','帕罗西汀','6A72']:
        hits=get('candidate-graph/search',dict(q=name))
        assert hits['items'],name
        detail=get('candidate-graph/entities/'+hits['items'][0]['id'])
        assert detail['expert_review']=='pending' and detail['activation_ready'] is False
        assert all(r['reasoning_eligible'] is False for r in detail['records'])
        if name=='失眠':assert detail['records'] and all(r['subject_name'] for r in detail['records'])
        checks.append(dict(case='search_and_detail',query=name,matched=hits['total'],records=len(detail['records']),passed=True))
    for status,total in [('all',899),('amended',399),('insufficient_evidence',55),('quarantined',13)]:
        rows=get('candidate-graph/reviews',dict(status=status,limit=1))
        assert rows['total']==total
        checks.append(dict(case='review_filter',status=status,total=total,passed=True))
    assert get('candidate-graph/search',dict(q='40-80mg/d'))['total']==0
    checks.append(dict(case='withdrawn_target_excluded',passed=True))
    packet=get('candidate-graph/expert-packet');assert len(packet['rows'])==899
    assert all(r['expert_decision'] is None for r in packet['rows'])
    checks.append(dict(case='expert_download_unsigned',passed=True,packet_sha256=digest(packet)))
    active=get('knowledge-graph/stats');assert active['version']=='kg_v2'
    checks.append(dict(case='active_graph_preserved',version=active['version'],passed=True))
    old=read(ROOT/'knowledge_sources/v3/receipts/2026-10-20-remainder-03.json')
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in old['active_kg_v2_files'].items())
    checks.append(dict(case='kg_v2_files_unchanged',passed=True))
    with opener.open('http://127.0.0.1:5173/',timeout=15) as r:assert r.status==200 and b'app' in r.read()
    checks.append(dict(case='frontend_http',passed=True))
    result=dict(checked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        scope='localhost_demo_acceptance_not_clinical_certification',
        candidate_url='http://127.0.0.1:5173/#candidate',checks=checks,
        passed=len(checks),failed=0,clinical_expert_approved=False)
    write(ROOT/'docs/CANDIDATE-DEMO-ACCEPTANCE.json',result)
    return result


if __name__=='__main__':
    result=verify();print(json.dumps(dict(passed=result['passed'],failed=result['failed'],clinical_expert_approved=False),ensure_ascii=False))
