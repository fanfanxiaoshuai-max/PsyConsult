"""Version-bound deterministic graph retrieval for all agents."""
from langchain_core.tools import tool

@tool
def query_knowledge_graph(query: str) -> str:
    """
    查询精神科临床知识图谱。
    当需要查询疾病-症状关联、药物-副作用关系、药物相互作用、治疗方案-药物关系等结构化医学知识时，使用此工具。
    输入参数 query 必须是明确的自然语言查询句子。
    """
    from core.graph.runtime_version import current_repository
    from core.graph.retriever import retrieve,format_result
    try:
        repository=current_repository()
        return format_result(retrieve(repository,query))
    except Exception:
        return '知识版本或图谱检索不可用；未切换到其他版本，请检查当前发布版本。'
