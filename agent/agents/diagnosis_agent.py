"""Clinical assessment and differential diagnosis agent."""
from typing import Any, Dict

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.prebuilt import create_react_agent

from config import get_settings
from core.graph.runtime_version import knowledge_prompt
from core.workflow.state import AgentState
from core.clinical_consistency import checked_answer
from tools.graph_tool import query_knowledge_graph
from tools.synonym_tool import query_synonyms
from tools.vector_tool import query_vector_db


class DiagnosisAgentNode:
    def __init__(self):
        self.llm = ChatOpenAI(**get_settings().get_model_config(), temperature=0.1)
        self.inner_agent = create_react_agent(
            self.llm, [query_synonyms, query_knowledge_graph, query_vector_db]
        )

    def _build_system_prompt(self, memory_context: str, query: str = '') -> str:
        from core.clinical_reference import anxiety_reference
        checked_reference=anxiety_reference(query)
        memory_block = f"\n## 历史对话 / 用户偏好\n{memory_context}" if memory_context else ""
        return f"""你是精神科临床诊断辅助 Agent。结合用户原话和检索资料，完成症状梳理与鉴别诊断。

工作流程：
1. 必要时用 query_synonyms 将口语表达映射为标准术语。
2. 用 query_knowledge_graph 查询相关疾病、症状和鉴别线索。
3. 用 query_vector_db 检索相关 ICD-11 诊断标准资料。

正文只用以下两个标题，保持简洁：
## 症状清单
列出用户实际描述的症状、原话和关键缺失信息。

## 鉴别诊断
只列最相关的两个方向，简要说明支持线索、尚缺条件和需要排除的情况。

约束：
- 先遵守本轮提问的范围；如果只要求复述病程或提出补问，就直接完成这项任务，不必套用症状清单和鉴别诊断模板。
- 诊断体系必须分清：WHO《ICD-11 CDDR》(2024)，6B00 广泛性焦虑障碍要求症状至少持续数月、更多日子存在症状；不能写成 ICD-11 必须满6个月或凑足3项附加症状。DSM-5-TR 的6个月条件不能移植到 ICD-11。病程、功能损害和排除条件不足时只列鉴别方向。
- 症状编码仅在检索原文明确对应时使用；不凭记忆给“心慌”“紧张”附加编码。诊断标准无法核对时说明待确认，不补造阈值。
- 未查到编码只代表本次未核对，不能断言ICD-11没有该编码。用户已提供的病程（如3周）须如实保留，不再列为缺失，也不当作已持续数月；仅对确实未知的信息补问。
- “长时间”尚未量化时，不知道是否达到数月；不得写成患者已确定不满足该病程要求。区分未确认与已不满足。
- 默认用疾病和症状名称表达，不主动附加ICD编码；用户明确要求编码时才返回检索原文中已核对的代码。
- 未提供的检查结果或排除结论不能补造：“需排除甲亢、心律失常”不等于“已排除甲亢、心律失常”。只有用户明确提供已完成的检查或排除结论，才可如实转述。
- 不编造用户未提供的症状、量表作答或已确诊结论；缺少完整作答时不估算 PHQ-9 总分。
- 对图谱中没有的记录说明覆盖不足，不把其他资料说成当前图谱版本的内容。
- 标明使用的指南或资料名称即可，不附证据编号、原文定位、逐条来源详情或长篇记录清单。
- 不增加“本轮知识版本”“任务已完成”“未执行”或工具调用过程等说明；版本已由页面单独显示。
- 最多调用 2 次工具，然后完成回答。
{knowledge_prompt()}{memory_block}
{checked_reference}"""

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        writer = get_stream_writer()
        writer({"agent": "differential_diagnosis", "event": "start"})
        query=next((str(m.content) for m in reversed(state['messages']) if isinstance(m,HumanMessage)),'')
        messages = [SystemMessage(content=self._build_system_prompt(state.get("memory_context", ""),query))] + list(state["messages"])
        full_content = ""
        tool_results = []
        async for msg, _ in self.inner_agent.astream({"messages": messages}, stream_mode="messages"):
            if isinstance(msg, AIMessageChunk):
                if msg.content:
                    full_content += msg.content
                elif getattr(msg, "tool_calls", None):
                    for call in msg.tool_calls:
                        writer({"agent": "differential_diagnosis", "event": "tool_call", "tool": call.get("name", "")})
            elif isinstance(msg, ToolMessage):
                tool_results.append({'tool':msg.name,'content':msg.content})
                writer({"agent": "differential_diagnosis", "event": "tool_done"})
        writer({'agent':'differential_diagnosis','event':'consistency_check'})
        full_content=await checked_answer(self.llm,full_content,state,tool_results,'diagnosis')
        for offset in range(0,len(full_content),120):
            writer({'agent':'differential_diagnosis','chunk':full_content[offset:offset+120]})
        return {"messages": [AIMessage(content=full_content)]}
