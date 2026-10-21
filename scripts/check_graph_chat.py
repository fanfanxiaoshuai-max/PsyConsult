"""Live synthetic three-route regression after graph upgrade; calls the configured model API."""
import json
import sys
import uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.check_e2e import collect
from app.app_config.settings import settings
from app.infra.cache import COLLECTION_NAME

if __name__=='__main__':
    run=uuid.uuid4().hex[:8]
    user='kg_verify_'+run
    cases=[
      ('教学虚构病例：成年人近三周情绪低落、兴趣下降和早醒，无既往躁狂史。请做简短鉴别诊断，并查询知识图谱提供来源。','differential_diagnosis'),
      ('仅讨论教学病例的治疗：已明确抑郁发作，请检索图谱简述分级治疗原则。','treatment_recommend'),
      ('仅做教学药物风险审查：请查询图谱，说明舍曲林与帕罗西汀的相互作用，并标注资料是否已核实。','drug_interaction'),
    ]
    report=dict(version=settings.kg_version,cache_collection=COLLECTION_NAME,synthetic_cases_only=True,turns=[])
    with httpx.Client(trust_env=False,timeout=httpx.Timeout(300,connect=10)) as client:
        for i,(query,expected) in enumerate(cases):
            print('Checking route:',expected,flush=True)
            result=collect(client,query,user,'kg_session_'+run+'_'+str(i))
            assert expected in result['nodes']
            assert not result['cache_hit']
            report['turns'].append(result)
        print('Checking upgraded-version cache...',flush=True)
        hit=collect(client,cases[-1][0],user,'kg_cache_'+run)
        assert hit['cache_hit']
        report['cache_hit']=hit
    (ROOT/('docs/KNOWLEDGE-GRAPH-'+settings.kg_version.upper()+'-CHAT-VERIFICATION.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Three routes and versioned cache passed.',flush=True)
