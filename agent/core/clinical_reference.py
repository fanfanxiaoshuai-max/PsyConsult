"""Small, source-checked corrections for legacy RAG documents. No clinical output rewriting."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ANXIETY_SOURCE=ROOT/'mock_data/icd11_anxiety.md'


def anxiety_reference(query: str) -> str:
    if any(term in query.casefold() for term in ('焦虑','心慌','心悸','紧张','担忧','惊恐','社交恐','压力','应激','适应障碍','6b00','6b01','6b04','6b43','gad')):
        return '【来源：WHO ICD-11 CDDR 2024；本地原文核对摘要】\n'+ANXIETY_SOURCE.read_text(encoding='utf-8')
    return ''


def current_document(source: str, original: str) -> str:
    # Existing embeddings can still point at pre-correction chunks. Read the checked source
    # instead of returning stale text or deleting the shared Milvus collection.
    if source=='icd11_anxiety.md':return ANXIETY_SOURCE.read_text(encoding='utf-8')
    return original
