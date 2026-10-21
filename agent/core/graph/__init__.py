"""Clinical graph models; optional LLM parser is imported only by its callers."""
from .models import Disease, Symptom, Drug, SideEffect, Treatment, Relation
__all__ = ['Disease', 'Symptom', 'Drug', 'SideEffect', 'Treatment', 'Relation']

from .client import Neo4jClient
from .ingestor import KnowledgeGraphIngestor

def __getattr__(name):
    if name == 'KnowledgeGraphParser':
        from .parser import KnowledgeGraphParser
        return KnowledgeGraphParser
    raise AttributeError(name)
