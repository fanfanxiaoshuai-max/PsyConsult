"""Synthetic final-answer grounding checks after removing unsupported prompt examples."""
import json,sys,time,uuid
from pathlib import Path
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
v=dotenv_values(ROOT/'agent/.env')
headers={'X-User-Id':'kg_v2_grounding_'+uuid.uuid4().hex[:8],'Authorization':'Bearer '+(v.get('API_AUTH_TOKEN') or '')}
queries=[
 '仅做教学药物资料审查：成人帕罗西汀与舍曲林联用有什么风险？请查询知识图谱，说明是否有已核对的直接药物对证据，并给出资料出处。',
 '教学药物资料核对：氟西汀与锂盐联用的风险及监测是什么？另请查询氟西汀与MAOI双向换药间隔，说明资料适用条件和原文出处。'
]
report=dict(version='kg_v2',synthetic_only=True,prompt_updated=True,report_mode='evidence_fields',answers=[])
with httpx.Client(trust_env=False,timeout=httpx.Timeout(300,connect=10)) as c:
 for query in queries:
  print('Checking grounded answer...',flush=True);events=[];start=time.monotonic()
  with c.stream('POST','http://127.0.0.1:5000/api/chat',headers=headers,json={'query':query,'session_id':'v2_grounding_'+uuid.uuid4().hex}) as r:
   r.raise_for_status()
   for line in r.iter_lines():
    if line.startswith('data: '): events.append(json.loads(line[6:]))
  assert events[-1].get('done') and any(e.get('agent')=='drug_interaction' for e in events)
  text=''.join(e.get('content','') for e in events if 'status' not in e)
  assert text.strip()
  report['answers'].append(dict(query=query,answer=text,seconds=round(time.monotonic()-start,2),tools=[e.get('content') for e in events if e.get('status')=='agent_tool_call']))
  print('SSE report received:',len(text),'characters',flush=True)
first,second=[a['answer'] for a in report['answers']]
assert 'P05' in first and '未在当前图谱找到已核对的直接证据' in first
assert 'F01' in second and 'F04' in second and '至少14天' in second and '至少5周' in second and '升高和降低' in second
assert '礼来医学网' in second and '#page=22' in second
assert all('每3' not in a['answer'] and '每月' not in a['answer'] for a in report['answers'])
report['acceptance']=dict(no_invented_monitoring_frequency=True,directional_washout_preserved=True,bidirectional_lithium_change_preserved=True,unverified_direct_pair_not_asserted=True,source_links_and_publishers_preserved=True)
(ROOT/'docs/KNOWLEDGE-GRAPH-KG_V2-GROUNDING.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
