"""Version-aware drug report from the scoped knowledge graph."""
import asyncio
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer

from core.workflow.state import AgentState
from tools.graph_tool import query_knowledge_graph


class DrugReviewAgentNode:
    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        writer = get_stream_writer()
        writer({"agent": "drug_interaction", "event": "start"})

        from core.graph.runtime_version import current_repository
        repository = current_repository()
        if repository.version == "kg_v2" or getattr(repository, "is_snapshot", False):
            from core.graph.evidence_report import render_chat_review
            from core.graph.retriever import rank_entities

            messages = list(state["messages"])
            human_index = next(
                (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
                None,
            )
            query = str(messages[human_index].content) if human_index is not None else ""
            try:
                entities = await asyncio.to_thread(repository.entities)

                def has_drug(value):
                    return any(e["label"] == "Drug" for e in rank_entities(value, entities))

                if not has_drug(query):
                    previous = messages[:human_index] if human_index is not None else []
                    candidate = next(
                        (str(m.content) for m in reversed(previous)
                         if isinstance(m, HumanMessage) and has_drug(str(m.content))),
                        None,
                    )
                    if candidate:
                        query += "\n" + candidate
                if sum(e["label"] == "Drug" for e in rank_entities(query, entities)) >= 2:
                    query += " 联用相互作用"
                writer({"agent": "drug_interaction", "event": "tool_call", "tool": "query_knowledge_graph"})
                payload = await asyncio.to_thread(query_knowledge_graph.invoke, {"query": query})
            except Exception:
                payload = ""
            writer({"agent": "drug_interaction", "event": "tool_done"})
            content = render_chat_review(payload)
        else:
            content = "## 药物资料审查\n\n当前知识版本未提供可用于药物审查的已核对记录。"

        for offset in range(0, len(content), 120):
            writer({"agent": "drug_interaction", "chunk": content[offset:offset + 120]})
        return {"messages": [AIMessage(content=content)], "next_agent": ""}
