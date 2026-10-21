"""Patient facts, medical consistency and draft isolation regressions."""
import asyncio
import json
from types import SimpleNamespace
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'agent'))

import pytest
from langchain_core.messages import AIMessage,AIMessageChunk,HumanMessage,SystemMessage,ToolMessage

from core.clinical_consistency import (checked_answer,ConsistencyCheckFailed,
    patient_statements,natural_prose,hard_findings,apply_edits,Edit)


def state(query='患者最近3周压力大，心慌，入睡困难。'):
    return {'messages':[HumanMessage(query)],'user_messages':[HumanMessage(query)]}


class Reviewer:
    def __init__(self,*decisions):self.decisions=list(decisions);self.inputs=[]
    async def ainvoke(self,messages):
        self.inputs.append(json.loads(messages[-1].content))
        result=self.decisions.pop(0)
        if isinstance(result,Exception):raise result
        if 'revised_answer' in result:
            result=dict(result)
            revised=result.pop('revised_answer')
            result['edits']=[{'quote':self.inputs[-1]['draft'],'replacement':revised}] if revised else []
        return SimpleNamespace(content=json.dumps(result,ensure_ascii=False))


def test_original_patient_facts_exclude_model_answers_and_mixed_summary():
    s={'messages':[SystemMessage('已排除甲亢'),AIMessage('已确诊GAD'),HumanMessage('心慌3周')]}
    assert patient_statements(s)==['心慌3周']
    s['user_messages']=[HumanMessage('更正：病程是3天，不是3周')]
    assert patient_statements(s)==['更正：病程是3天，不是3周']


def test_sentence_patch_preserves_every_untouched_part():
    candidate='## 症状清单\n心慌、入睡困难。\n## 鉴别诊断\n已排除甲亢。其他内容保持原样。'
    result=apply_edits(candidate,[Edit(quote='已排除甲亢。',replacement='尚未提供甲功结果，甲状腺原因待排查。')])
    assert result==candidate.replace('已排除甲亢。','尚未提供甲功结果，甲状腺原因待排查。')


def test_fixed_line_ids_preserve_other_lines_and_original_newlines():
    assert apply_edits('标题\r\n错误句。\r\n其余正确句。',
        [Edit(line_id=1,replacement='修正句。')])=='标题\r\n修正句。\r\n其余正确句。'


@pytest.mark.parametrize('edits',[
    [Edit(line_id=9,replacement='越界')],
    [Edit(line_id=0,replacement='不允许\n扩写新段落')],
    [Edit(line_id=0,replacement='A'),Edit(line_id=0,replacement='B')],
])
def test_invalid_line_edits_cannot_modify_draft(edits):
    with pytest.raises(ConsistencyCheckFailed):apply_edits('原句。',edits)


@pytest.mark.parametrize('candidate,edits',[
    ('原文',[Edit(quote='不存在的引用',replacement='不能应用')]),
    ('相同。相同。',[Edit(quote='相同。',replacement='歧义')]),
    ('心慌失眠，病程3周。',[Edit(quote='心慌失眠',replacement='A'),Edit(quote='失眠，病程',replacement='B')]),
    ('原文',[Edit(quote='原文',replacement='')]),
])
def test_ambiguous_overlapping_or_empty_patches_fail_closed(candidate,edits):
    with pytest.raises(ConsistencyCheckFailed):apply_edits(candidate,edits)


def test_unchanged_consistent_prose_is_not_rewritten():
    draft='## 症状清单\n病程3周，心慌、入睡困难。\n## 鉴别诊断\n应激相关反应待评估；需询问具体应激源及发生时间。'
    reviewer=Reviewer({'issues':[],'revised_answer':None})
    assert asyncio.run(checked_answer(reviewer,draft,state()))==draft
    assert reviewer.inputs[0]['patient_statements']==['患者最近3周压力大，心慌，入睡困难。']
    assert '至少持续数月' in reviewer.inputs[0]['references']


def test_provider_echoing_identical_line_on_confirmation_is_harmless():
    text='病程3周，应激源日期仍需明确。'
    reviewer=Reviewer({'issues':[],'edits':[{'line_id':0,'replacement':text}]})
    assert asyncio.run(checked_answer(reviewer,text,state()))==text


def test_confirmation_without_issues_does_not_apply_unsolicited_style_edits():
    good='尚需核实应激源发生日期。'
    reviewer=Reviewer({'issues':['把日期当作已知'],'edits':[{'line_id':0,'replacement':good}]},
                      {'issues':[],'edits':[{'line_id':0,'replacement':'更长的文风改写不应发布'}]})
    assert asyncio.run(checked_answer(reviewer,'已经符合时间条件。',state()))==good


def test_later_followup_keeps_reference_from_original_case():
    s=state();s['user_messages'] += [HumanMessage('继续补问') for _ in range(15)]
    reviewer=Reviewer({'issues':[],'edits':[]})
    asyncio.run(checked_answer(reviewer,'请补充症状频率与功能影响。',s))
    assert '至少持续数月' in reviewer.inputs[0]['references']
    assert reviewer.inputs[0]['patient_statements'][0]=='患者最近3周压力大，心慌，入睡困难。'


def test_bad_time_assumption_is_revised_then_rule_checked():
    corrected='病程3周；具体应激事件及发生日期未提供，需补问，暂不能确认起病时间条件。'
    reviewer=Reviewer({'issues':['把症状时长当作应激源日期'],'revised_answer':corrected},
                      {'issues':[],'revised_answer':None})
    result=asyncio.run(checked_answer(reviewer,'已符合应激源后一个月内起病。尚需明确应激源日期。',state()))
    assert result==corrected and len(reviewer.inputs)==1
    assert hard_findings(result,patient_statements(state()))==[]


def test_unresolved_rewrite_is_not_released():
    reviewer=Reviewer({'issues':['缺少病史'],'revised_answer':'仍然说已确诊。'},
                      {'issues':['修正后仍矛盾'],'revised_answer':None})
    with pytest.raises(ConsistencyCheckFailed):asyncio.run(checked_answer(reviewer,'草稿',state()))


def test_remaining_rule_violation_gets_only_one_targeted_repair():
    reviewer=Reviewer({'issues':['没有检查资料'],'edits':[{'line_id':0,'replacement':'患者已确诊GAD。'}]},
                      {'issues':['无确诊资料'],'edits':[{'line_id':0,'replacement':'诊断条件尚待核实。'}]})
    result=asyncio.run(checked_answer(reviewer,'已排除甲亢。',state()))
    assert result=='诊断条件尚待核实。' and len(reviewer.inputs)==2
    assert reviewer.inputs[1]['required_corrections']


def test_product_scope_does_not_support_blanket_approval_claims():
    assert hard_findings('中国尚无SSRI或SNRI明确获批GAD适应症。',['请介绍药物'])
    assert hard_findings('具体地区和产品的适应症需按对应说明书核对。',['请介绍药物'])==[]
    assert hard_findings('文拉法辛的GAD适应症仅获美国FDA批准，中国说明书未明确标注。',['请介绍药物'])
    assert hard_findings('帕罗西汀在中国说明书列有惊恐障碍，GAD属超说明书用药。',['请介绍药物'])
    assert hard_findings('本轮所见具体产品的中国说明书尚未明确GAD范围，需结合产品核对。',['请介绍药物'])==[]


def test_unreported_context_pattern_is_not_a_patient_fact():
    assert hard_findings('支持线索：紧张、心悸、失眠，且呈非情境特异性。',['患者长时间紧张心慌失眠'])
    assert hard_findings('支持线索：若症状呈非情境特异性，需进一步评估。',['患者长时间紧张心慌失眠'])==[]


def test_failed_review_cannot_fall_back_to_original_draft():
    reviewer=Reviewer(ConnectionError('private provider output'))
    with pytest.raises(ConsistencyCheckFailed,match='unavailable'):
        asyncio.run(checked_answer(reviewer,'未经核对的诊断草稿',state()))


def test_deterministic_gate_rejects_false_approval_of_invented_exclusion():
    reviewer=Reviewer({'issues':[],'revised_answer':None})
    with pytest.raises(ConsistencyCheckFailed):
        asyncio.run(checked_answer(reviewer,'已排除甲亢及心律失常。',state()))
    assert reviewer.inputs[0]['required_corrections']


@pytest.mark.parametrize('draft',['需排除甲亢。','尚未排除甲亢。','是否已排除甲亢？','不能认为已排除甲亢。'])
def test_gate_does_not_confuse_unknown_or_question_with_completed_exclusion(draft):
    assert hard_findings(draft,patient_statements(state()))==[]


def test_supplied_negative_exam_is_preserved_without_becoming_all_clear():
    query='患者心慌3周；医生已做心电图，本次未见心律失常，甲功尚未检查。'
    draft='本次心电图未见心律失常，甲状腺原因仍需评估。'
    reviewer=Reviewer({'issues':[],'revised_answer':None})
    assert asyncio.run(checked_answer(reviewer,draft,state(query)))==draft


def test_explicit_user_reported_diagnosis_is_not_reclassified_as_unknown():
    query='患者已确诊抑郁症，请解释一般治疗路径。'
    draft='用户提供的信息是患者已确诊抑郁症；治疗仍需结合病史、严重度和具体资料。'
    reviewer=Reviewer({'issues':[],'revised_answer':None})
    assert asyncio.run(checked_answer(reviewer,draft,state(query)))==draft


@pytest.mark.parametrize('query,expected',[
    ('请分析','广泛性焦虑障碍（GAD）；需继续评估。'),
    ('请给ICD-11编码','广泛性焦虑障碍（GAD，ICD-11 6B00）；需继续评估。'),
    ('6B00是什么意思','广泛性焦虑障碍（GAD，ICD-11 6B00）；需继续评估。'),
])
def test_optional_coding_is_a_display_choice_not_a_clinical_number_rewrite(query,expected):
    assert natural_prose('广泛性焦虑障碍（GAD，ICD-11 6B00）；需继续评估。',query)==expected
    assert '50 mg/日' in natural_prose('原资料为50 mg/日、4–6周；不是个体处方。','请说明')
    assert '5HT2' in natural_prose('5HT2受体属于药理资料。','请解释药理机制')


def test_hiding_an_optional_code_keeps_the_classification_subject():
    assert natural_prose('病程未明确；ICD-11 6B00要求至少数月。','请分析')=='病程未明确；ICD-11要求至少数月。'


def test_asking_for_icd11_criteria_is_not_asking_for_codes():
    assert natural_prose('广泛性焦虑障碍（ICD-11 6B00）待评估。','请按ICD11说明鉴别方向')=='广泛性焦虑障碍待评估。'


def test_correcting_a_wrong_code_does_not_trigger_the_wrong_code_gate():
    assert hard_findings('适应障碍不是6B44，其编码为6B43。',['请核对编码'])==[]


def test_gate_catches_the_previously_accepted_followup_contradiction():
    draft='病程符合适应障碍的时间窗口（应激源后1个月内起病），但尚未确认应激源性质与发生日期。'
    assert hard_findings(draft,['最近3周压力大'])
    assert hard_findings('需明确应激源发生日期，当前不能确认是否符合应激源后一个月内起病。',['最近3周压力大'])==[]
    assert hard_findings('ICD-11广泛性焦虑障碍不设固定时长下限。',['心慌3周'])
    assert hard_findings('广泛性焦虑障碍不是固定6个月门槛，但至少数月仍是必要特征。',['心慌3周'])==[]


def test_diagnostic_classification_is_not_a_drug_recommendation_source():
    assert hard_findings('SSRIs为ICD-11及中国指南推荐的一线药物。',['请介绍治疗'])
    assert hard_findings('ICD-11推荐SSRIs作为一线药物。',['请介绍治疗'])
    assert hard_findings('可按ICD-11诊断要求评估，治疗方案另按实际指南核对。',['请介绍治疗'])==[]


def test_missing_lookup_does_not_prove_absence_from_classification():
    assert hard_findings('ICD-11中未单独编码入睡困难。',['失眠3周'])
    assert hard_findings('失眠是睡眠症状，其编码本次未核对。',['失眠3周'])==[]


def test_unquantified_duration_is_not_a_confirmed_negative_criterion():
    assert hard_findings('本例尚未满足至少数月的必要特征。',['患者长时间紧张心慌失眠'])
    assert hard_findings('本例尚未满足至少数月的必要特征。',['患者紧张心慌3周'])==[]
    assert hard_findings('病程未量化，尚未确认是否满足该项要求。',['患者长时间紧张心慌失眠'])==[]


@pytest.mark.parametrize('module_name,stage',[
    ('agents.diagnosis_agent','differential_diagnosis'),
    ('agents.treatment_agent','treatment_recommend'),
])
def test_agent_stream_and_checkpoint_contain_only_checked_answer(monkeypatch,module_name,stage):
    import importlib
    module=importlib.import_module(module_name)
    events=[]
    monkeypatch.setattr(module,'get_stream_writer',lambda:events.append)
    class Inner:
        async def astream(self,*args,**kwargs):
            yield AIMessageChunk(content='UNSAFE_DRAFT'),{}
            yield ToolMessage(content='检索资料',tool_call_id='call',name='query_vector_db'),{}
    async def check(llm,draft,s,tools,node):
        assert draft=='UNSAFE_DRAFT'
        assert not any('chunk' in e for e in events)
        assert tools[0]['content']=='检索资料'
        return '最终核对后的自然回答'
    monkeypatch.setattr(module,'checked_answer',check)
    cls=module.DiagnosisAgentNode if stage=='differential_diagnosis' else module.TreatmentAgentNode
    node=cls.__new__(cls);node.inner_agent=Inner();node.llm=object()
    result=asyncio.run(node(state()))
    assert ''.join(e.get('chunk','') for e in events)=='最终核对后的自然回答'
    assert result['messages'][0].content=='最终核对后的自然回答'
    assert any(e.get('event')=='consistency_check' for e in events)


def test_agent_failure_never_streams_unsafe_draft(monkeypatch):
    import agents.diagnosis_agent as module
    events=[]
    monkeypatch.setattr(module,'get_stream_writer',lambda:events.append)
    class Inner:
        async def astream(self,*args,**kwargs):yield AIMessageChunk(content='UNSAFE_DRAFT'),{}
    async def check(*args):raise ConsistencyCheckFailed('unresolved')
    monkeypatch.setattr(module,'checked_answer',check)
    node=module.DiagnosisAgentNode.__new__(module.DiagnosisAgentNode)
    node.inner_agent=Inner();node.llm=object()
    with pytest.raises(ConsistencyCheckFailed):asyncio.run(node(state()))
    assert not any(e.get('chunk') for e in events)


def test_blocked_draft_never_enters_sse_cache_or_checkpoint(monkeypatch):
    from app.service import chat_service
    from core.graph import runtime_version
    from core.workflow.graph_manager import AgentGraphManager
    from langgraph.checkpoint.memory import InMemorySaver
    from agents.diagnosis_agent import DiagnosisAgentNode
    async def route(s):return {'next_agent':'differential_diagnosis','metadata':{'diagnosis_only':True}}
    class Inner:
        async def astream(self,*args,**kwargs):yield AIMessageChunk(content='UNSAFE_DRAFT 已排除甲亢。'),{}
    node=DiagnosisAgentNode.__new__(DiagnosisAgentNode)
    node.inner_agent=Inner();node.llm=Reviewer({'issues':[],'revised_answer':None})
    manager=AgentGraphManager.__new__(AgentGraphManager)
    manager.orchestrator=SimpleNamespace(route=route);manager.diagnosis_node=node
    manager.drug_review_node=manager.treatment_node=manager._summary_llm=None
    saver=InMemorySaver();graph=manager.build_graph(checkpointer=saver)
    class Cache:
        available=True
        writes=[]
        async def for_knowledge(self,key):return self
        async def get_cache(self,*args):return None
        async def set_cache(self,*args,**kwargs):self.writes.append(args)
    cache=Cache()
    binding=runtime_version.KnowledgeBinding('synthetic','synthetic','test-only',object())
    monkeypatch.setattr(runtime_version,'resolve_binding',lambda:binding)
    monkeypatch.setattr(runtime_version,'binding_from_metadata',lambda meta:binding)
    monkeypatch.setattr(chat_service,'graph',graph);monkeypatch.setattr(chat_service,'checkpointer',saver)
    monkeypatch.setattr(chat_service,'semantic_cache',cache);monkeypatch.setattr(chat_service,'memory',None)
    async def exercise():
        events=[json.loads(e[6:]) async for e in chat_service.stream_chat('患者心慌失眠3周','user','case')]
        snapshot=await graph.aget_state(chat_service.session_config('user','case'))
        return events,snapshot.values
    events,values=asyncio.run(exercise())
    assert events[-1]['done'] and events[-1]['failed']
    assert not cache.writes
    assert not any(isinstance(m,AIMessage) for m in values['messages'])
    assert 'UNSAFE_DRAFT' not in json.dumps(events)
    assert any(e.get('status')=='clinical_consistency_check' for e in events)


def test_anxiety_treatment_search_keeps_treatment_documents(monkeypatch):
    from tools import vector_tool
    calls=[]
    def search(query,k):
        calls.append(query)
        return [(SimpleNamespace(metadata={'source':'china_guidelines.md'},page_content='这是需要保留的治疗资料'),0.1)]
    monkeypatch.setattr(vector_tool,'_get_milvus_store',lambda:SimpleNamespace(similarity_search_with_score=search))
    result=vector_tool.query_vector_db.invoke({'query':'广泛性焦虑障碍一线治疗'})
    assert calls and '这是需要保留的治疗资料' in result and '至少持续数月' in result


def test_checked_stage_boundary_has_same_spacing_in_sse_and_cache(monkeypatch):
    from app.service import chat_service
    from core.graph import runtime_version
    binding=runtime_version.KnowledgeBinding('synthetic','synthetic','stage-spacing',object())
    monkeypatch.setattr(runtime_version,'resolve_binding',lambda:binding)
    class Graph:
        async def astream(self,*args,**kwargs):
            yield 'custom',{'agent':'differential_diagnosis','chunk':'## 症状清单\n三周。'}
            yield 'custom',{'agent':'treatment_recommend','chunk':'## 治疗建议\n待评估。'}
    class Cache:
        available=True
        saved=None
        async def for_knowledge(self,key):return self
        async def get_cache(self,*args):return None
        async def set_cache(self,query,answer,**kwargs):self.saved=answer
    cache=Cache()
    monkeypatch.setattr(chat_service,'graph',Graph());monkeypatch.setattr(chat_service,'checkpointer',None)
    monkeypatch.setattr(chat_service,'memory',None);monkeypatch.setattr(chat_service,'semantic_cache',cache)
    async def run():return [json.loads(e[6:]) async for e in chat_service.stream_chat('心慌失眠3周','user','case')]
    events=asyncio.run(run())
    visible=''.join(e.get('content','') for e in events if e.get('agent') and not e.get('status'))
    assert visible==cache.saved=='## 症状清单\n三周。\n\n## 治疗建议\n待评估。'
