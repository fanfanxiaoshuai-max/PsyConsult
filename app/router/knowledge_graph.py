import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies.auth import require_chat_identity
from app.schemas.knowledge_graph import GraphSearch, GraphNeighborhood
from app.service import knowledge_graph_service as service

logger=logging.getLogger('clinical_cds.chat')
router=APIRouter(prefix='/knowledge-graph', tags=['Knowledge graph'], dependencies=[Depends(require_chat_identity)])

def invoke(fn, *args):
    try:
        return fn(*args)
    except Exception:
        logger.exception('Knowledge graph request failed')
        raise HTTPException(503, '知识图谱暂时不可用，请稍后重试。') from None

@router.get('/search', response_model=GraphSearch)
def search(q: Annotated[str, Query(min_length=1,max_length=200)], limit: Annotated[int, Query(ge=1,le=50)]=20):
    if not q.strip():
        raise HTTPException(422, '请输入实体名称')
    return invoke(service.search, q.strip(), limit)

@router.get('/stats')
def stats():
    return invoke(service.stats)

@router.get('/entities/{uid}')
def detail(uid: str):
    result=invoke(service.detail, uid)
    if result is None:
        raise HTTPException(404, '实体不存在')
    return result

@router.get('/entities/{uid}/neighbors', response_model=GraphNeighborhood)
def neighbors(uid: str, limit: Annotated[int, Query(ge=1,le=100)]=40,
              relation_type: Annotated[str | None, Query(max_length=100)]=None,
              include_unreviewed: bool=False):
    if invoke(service.detail, uid) is None:
        raise HTTPException(404, '实体不存在')
    return invoke(service.neighbors, uid, limit, relation_type, include_unreviewed)
