"""Authenticated project workflow; activation affects only knowledge workspace snapshots."""
import json
import logging
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,Field,ConfigDict
from app.dependencies.auth import require_chat_identity,require_reviewer_identity,require_admin_identity
from core.graph.project_workbench import workbench,ProjectConflict

router=APIRouter(prefix='/knowledge-workbench',tags=['Knowledge workbench'],dependencies=[Depends(require_chat_identity)])
Reviewer=Annotated[str,Depends(require_reviewer_identity)]
Admin=Annotated[str,Depends(require_admin_identity)]

def run(fn,*args):
    def execute():
        try:return fn(*args)
        except ProjectConflict as e:raise HTTPException(409,str(e)) from None
    # Keep intentional client errors; sanitize internal filesystem/database errors.
    try:return execute()
    except HTTPException:raise
    except Exception:
        logging.getLogger('clinical_cds.chat').exception('Knowledge workbench request failed')
        raise HTTPException(503,'知识工作区暂时不可用，请稍后重试。') from None

class Change(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    revision:int=Field(ge=0)

class Review(Change):
    item_id:str=Field(min_length=1,max_length=200)
    status:Literal['approved','returned','disabled']
    note:str=Field(min_length=1,max_length=1000)

class Publish(Change):
    note:str=Field(min_length=1,max_length=1000)

class Activate(Change):
    release_id:str=Field(pattern=r'^project-[0-9a-f]{12}$')

@router.get('/status')
def status():return run(workbench.status)

@router.get('/reviews')
def reviews(q:Annotated[str,Query(max_length=200)]='',status:Literal['all','approved','returned','disabled','blocked','amended','source_supported','insufficient_evidence','quarantined','structural_only']='all',offset:Annotated[int,Query(ge=0,le=10000)]=0,limit:Annotated[int,Query(ge=1,le=100)]=20):
    return run(workbench.reviews,q,status,offset,limit)

@router.post('/review')
def review(body:Review,actor:Reviewer):return run(workbench.decide,body.revision,actor,body.item_id,body.status,body.note)

@router.post('/publish')
def publish(body:Publish,actor:Admin):return run(workbench.publish,body.revision,actor,body.note)

@router.post('/activate')
def activate(body:Activate,actor:Admin):return run(workbench.activate,body.revision,actor,body.release_id)

@router.post('/rollback')
def rollback(body:Change,actor:Admin):return run(workbench.rollback,body.revision,actor)

@router.get('/export')
def export():return Response(json.dumps(run(workbench.export),ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="project-review.json"','Cache-Control':'no-store'})

@router.get('/search')
def search(q:Annotated[str,Query(min_length=1,max_length=200)],view:Literal['working','active']='working'):
    if not q.strip():raise HTTPException(422,'请输入名称或编码')
    return run(workbench.search,q,20,view)

@router.get('/entities/{uid}')
def detail(uid:str,view:Literal['working','active']='working'):
    result=run(workbench.detail,uid,view)
    if result is None:raise HTTPException(404,'实体不存在')
    return result
