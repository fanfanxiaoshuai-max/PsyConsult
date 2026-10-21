"""Guideline-backed treatment recommendation agent."""
from typing import Any, Dict

from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.prebuilt import create_react_agent

from config import get_settings
from core.graph.runtime_version import knowledge_prompt
from core.workflow.state import AgentState
from core.clinical_consistency import checked_answer
from tools.graph_tool import query_knowledge_graph
from tools.vector_tool import query_vector_db


class TreatmentAgentNode:
    def __init__(self):
        self.llm = ChatOpenAI(**get_settings().get_model_config(), temperature=0.1)
        self.inner_agent = create_react_agent(self.llm, [query_vector_db, query_knowledge_graph])

    def _build_system_prompt(self, memory_context: str) -> str:
        memory_block = f"\n## 历史对话 / 用户偏好\n{memory_context}" if memory_context else ""
        return f"""你是精神科治疗建议辅助 Agent。阅读本轮诊断分析和用户提问，结合检索到的指南与当前知识图谱给出简洁建议。

先用 query_vector_db 检索相关指南，再用 query_knowledge_graph 核对药物或治疗关系。最多调用 2 次工具。

按需要使用以下结构，不适用的部分可省略：
## 治疗建议
### 一线方案
### 其他选择
### 非药物治疗
### 注意事项

约束：
- ICD-11用于分类和诊断，不能称“ICD-11推荐某一线药物”；治疗建议只归属实际检索到的治疗资料，来源不明确时不虚构指南名或推荐等级。
- 一般治疗信息须保留条件，但不把合理的条件句误写成患者已确诊；心理支持与一般非药物措施也不应一律限定为全部检查和正式确诊后才能开始。
- 原资料中的“通常”“例如”“可考虑”保留其限定，不改写成绝对必要条件。
- 未量化“长时间”时只能说病程条件未确认，不能断言病程不够；未确诊GAD也不能推导所有焦虑症状一律不得用药，只能暂不替本例确定具体药物方案。
- 只补充治疗方面的新信息，不重复上一阶段的症状清单、鉴别诊断或对同一追问的回答。
- 诊断条件依所注明的体系；WHO ICD-11 CDDR (2024) 对6B00使用至少持续数月，不把DSM的6个月与附加症状数量条件称为ICD-11标准。
- 药物和具体参数应来自检索结果；保留记录中的人群、地区、适用条件及不确定性，不能自行补全剂量或适应证。
- 来源只需简短注明指南或记录名称，不附证据编号、原文定位、逐条来源详情或长篇记录清单。
- 资料不足时直说，不把鉴别方向当作已确诊疾病或给出个人处方。
- 不输出知识版本、任务完成情况或工具调用过程；版本已由页面单独显示。
{knowledge_prompt()}{memory_block}"""

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        writer = get_stream_writer()
        writer({"agent": "treatment_recommend", "event": "start"})
        messages = [SystemMessage(content=self._build_system_prompt(state.get("memory_context", "")))] + list(state["messages"])
        full_content = ""
        tool_results = []
        async for msg, _ in self.inner_agent.astream({"messages": messages}, stream_mode="messages"):
            if isinstance(msg, AIMessageChunk):
                if msg.content:
                    full_content += msg.content
                elif getattr(msg, "tool_calls", None):
                    for call in msg.tool_calls:
                        writer({"agent": "treatment_recommend", "event": "tool_call", "tool": call.get("name", "")})
            elif isinstance(msg, ToolMessage):
                tool_results.append({'tool':msg.name,'content':msg.content})
                writer({"agent": "treatment_recommend", "event": "tool_done"})
        writer({'agent':'treatment_recommend','event':'consistency_check'})
        full_content=await checked_answer(self.llm,full_content,state,tool_results,'treatment')
        for offset in range(0,len(full_content),120):
            writer({'agent':'treatment_recommend','chunk':full_content[offset:offset+120]})
        return {"messages": [AIMessage(content=full_content)]}
