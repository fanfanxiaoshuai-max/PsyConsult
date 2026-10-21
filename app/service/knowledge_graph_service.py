from core.graph.runtime_version import resolve_binding
from core.graph.retriever import rank_entities

def search(query, limit):
    repo=resolve_binding().repository
    items=rank_entities(query, repo.entities())
    return dict(version=repo.version, items=items[:limit], total=len(items), truncated=len(items)>limit)

def detail(uid):
    return resolve_binding().repository.detail(uid)

def neighbors(uid, limit, relation_type=None, include_unreviewed=False):
    return resolve_binding().repository.neighbors([uid], limit=limit, relation_type=relation_type, include_unreviewed=include_unreviewed)

def stats():
    return resolve_binding().repository.stats()
