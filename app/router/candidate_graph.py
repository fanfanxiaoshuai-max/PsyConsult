"""Authenticated read-only preview; no version selection, database writes or chat integration."""
import json
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from app.dependencies.auth import require_chat_identity
from app.router.knowledge_graph import invoke
from core.graph.candidate_preview import preview

router=APIRouter(prefix='/candidate-graph',tags=['Candidate preview'],dependencies=[Depends(require_chat_identity)])

@router.get('/stats')
def stats():return invoke(preview.stats)

@router.get('/search')
def search(q:Annotated[str,Query(min_length=1,max_length=200)],limit:Annotated[int,Query(ge=1,le=50)]=20):
    if not q.strip():raise HTTPException(422,'请输入名称或编码')
    return invoke(preview.search,q,limit)

@router.get('/entities/{uid}')
def detail(uid:str):
    result=invoke(preview.detail,uid)
    if result is None:raise HTTPException(404,'候选实体不存在或已撤销')
    return result

@router.get('/reviews')
def reviews(q:Annotated[str,Query(max_length=200)]='',
            status:Literal['all','amended','source_supported','insufficient_evidence','quarantined','structural_only','withdrawn']='all',
            offset:Annotated[int,Query(ge=0,le=10000)]=0,limit:Annotated[int,Query(ge=1,le=100)]=30):
    return invoke(preview.reviews,q,status,offset,limit)

@router.get('/expert-packet')
def expert_packet():
    packet=invoke(preview.export)
    return Response(json.dumps(packet,ensure_ascii=False),media_type='application/json',
        headers={'Content-Disposition':'attachment; filename="psyconsult-expert-packet.json"','Cache-Control':'no-store'})
