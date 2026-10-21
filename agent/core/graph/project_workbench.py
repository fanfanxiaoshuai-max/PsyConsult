"""Persistent project review and immutable releases for the knowledge workspace."""
import copy
import json
import sqlite3
from contextlib import closing
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .audit import ROOT, digest
from .candidate_preview import preview

LABELS={'approved':'审核通过','returned':'退回修改','disabled':'已停用','blocked':'依据不足 / 隔离'}


def project_view(value):
    """Present project fields without legacy expert-form metadata; archives stay untouched."""
    if isinstance(value,dict):
        return {k:project_view(v) for k,v in value.items() if not k.startswith('expert_') and k!='medical_review_required'}
    if isinstance(value,list):return [project_view(v) for v in value]
    return value


class ProjectConflict(ValueError):
    pass


class ProjectWorkbench:
    def __init__(self, store=preview, path=None):
        self.store=store
        self.path=Path(path or ROOT/'logs/knowledge-workbench.sqlite3')

    def _connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(self.path,timeout=30)
        conn.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
        return conn

    def _read(self,conn):
        row=conn.execute('SELECT payload FROM state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else dict(revision=0,decisions={},releases=[],active=None,activation_history=[],events=[])

    def _rows(self,state):
        data,packet=self.store.load(); key=digest(data)
        decisions=state['decisions'].get(key,{})
        rows=[]
        for original in packet['rows']:
            row=project_view(original)
            withdrawn=(row.get('candidate_change') or {}).get('after','missing') is None
            eligible=row['original_status'] in {'source_supported','amended','structural_only'} and not withdrawn
            status='disabled' if withdrawn else 'approved' if eligible else 'blocked'
            decision=decisions.get(row['item_id'])
            if decision:status=decision['status']
            row['project_review']=dict(status=status,label=LABELS[status],eligible=eligible,
                note=(decision or {}).get('note','基于已完成的来源核对和数据校验纳入项目内部审核。' if eligible else '保留原处置，不纳入发布内容。'),
                updated_at=(decision or {}).get('at'),actor=(decision or {}).get('actor','project_validation'))
            rows.append(row)
        return key,rows

    def status(self):
        from config import get_settings
        with closing(self._connect()) as c:state=self._read(c)
        key,rows=self._rows(state)
        return dict(revision=state['revision'],working_sha256=key,counts=dict(Counter(r['project_review']['status'] for r in rows)),
            total=len(rows),active=state['active'],releases=[{k:v for k,v in r.items() if k!='payload'} for r in reversed(state['releases'])],
            events=list(reversed(state['events'][-30:])),scope='knowledge_workspace_and_chat',
            chat_version=state['active'] or get_settings().kg_version)

    def reviews(self,q='',status='all',offset=0,limit=20):
        with closing(self._connect()) as c:state=self._read(c)
        _,rows=self._rows(state)
        rows=[r for r in rows if (status=='all' or r['project_review']['status']==status or r['original_status']==status)
              and (not q.strip() or q.strip().casefold() in (r['summary']+' '+r['item_id']).casefold())]
        return dict(items=rows[offset:offset+limit],total=len(rows))

    def _mutate(self,revision,actor,action,fn):
        conn=self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE');state=self._read(conn)
            if state['revision']!=revision:raise ProjectConflict('页面已过期，请重新加载后再操作。')
            key,rows=self._rows(state)
            at=datetime.now(timezone.utc).isoformat()
            target=fn(state,key,rows,at)
            state['revision']+=1
            state['events'].append(dict(action=action,actor=actor,at=at,target=target))
            conn.execute('INSERT OR REPLACE INTO state VALUES (1,?)',(json.dumps(state,ensure_ascii=False),))
            conn.commit()
        finally:conn.close()
        return self.status()

    def decide(self,revision,actor,item_id,status,note):
        if status not in {'approved','returned','disabled'}:raise ProjectConflict('无效的审核状态。')
        def apply(state,key,rows,at):
            row=next((r for r in rows if r['item_id']==item_id),None)
            if row is None:raise ProjectConflict('条目不存在。')
            if status=='approved' and not row['project_review']['eligible']:raise ProjectConflict('依据不足、隔离或已撤销条目不能批准，请先补齐来源并重新构建。')
            state['decisions'].setdefault(key,{})[item_id]=dict(status=status,note=note,actor=actor,at=at)
            return item_id
        return self._mutate(revision,actor,'review_'+status,apply)

    def publish(self,revision,actor,note):
        def apply(state,key,rows,at):
            if len(state['releases'])>=100:raise ProjectConflict('版本数量已达上限。')
            approved={r['item_id'] for r in rows if r['project_review']['status']=='approved'}
            decisions_hash=digest({r['item_id']:r['project_review']['status'] for r in rows})
            if any(r['source_sha256']==key and r['decisions_sha256']==decisions_hash for r in state['releases']):
                raise ProjectConflict('相同内容已经发布，无需重复发布。')
            data,_=self.store.load();details=[]
            approved_ids={e['id'] for e in data['entities'] if 'entity:'+e['id'] in approved and not e.get('withdrawn')}
            for entity in data['entities']:
                if entity.get('withdrawn'):continue
                detail=project_view(self.store.detail(entity['id']))
                detail['records']=[r for r in detail['records'] if r['audit_item_ids'] and set(r['audit_item_ids'])<=approved
                    and r['subject_id'] in approved_ids and (not r.get('related_id') or r['related_id'] in approved_ids)]
                # Returning/disabling the entity itself also removes it from published search.
                if 'entity:'+entity['id'] not in approved:continue
                if detail['records']:details.append(detail)
            if not details:raise ProjectConflict('没有可发布的知识记录。')
            uid='project-'+uuid4().hex[:12]
            payload=dict(entities=details,approved_item_ids=sorted(approved))
            state['releases'].append(dict(id=uid,name='知识版本 '+str(len(state['releases'])+1),created_at=at,actor=actor,note=note,
                source_sha256=key,decisions_sha256=decisions_hash,payload_sha256=digest(payload),
                entity_count=len(details),record_count=len({r['id'] for d in details for r in d['records']}),payload=payload))
            return uid
        return self._mutate(revision,actor,'publish',apply)

    def activate(self,revision,actor,release_id):
        def apply(state,key,rows,at):
            release=next((r for r in state['releases'] if r['id']==release_id),None)
            if release is None or digest(release['payload'])!=release['payload_sha256']:raise ProjectConflict('版本不存在或完整性校验失败。')
            if state['active']==release_id:raise ProjectConflict('该版本已经启用。')
            if release['source_sha256']!=key:raise ProjectConflict('来源数据已经变化，请重新发布。')
            from .snapshot_repository import SnapshotRepository
            SnapshotRepository(release)
            state['activation_history'].append(state['active']);state['active']=release_id
            return release_id
        return self._mutate(revision,actor,'activate',apply)

    def rollback(self,revision,actor):
        def apply(state,key,rows,at):
            if not state['activation_history']:raise ProjectConflict('没有可回退的启用记录。')
            previous=state['activation_history'].pop()
            if previous:
                release=next(r for r in state['releases'] if r['id']==previous)
                if digest(release['payload'])!=release['payload_sha256']:raise ProjectConflict('历史版本完整性校验失败。')
                from .snapshot_repository import SnapshotRepository
                SnapshotRepository(release)
            state['active']=previous
            return previous or 'working'
        return self._mutate(revision,actor,'rollback',apply)

    def export(self):
        result=self.status();result['review_rows']=self.reviews(limit=10000)['items']
        return result

    def _active(self):
        self.store.load()
        with closing(self._connect()) as c:state=self._read(c)
        release=next((r for r in state['releases'] if r['id']==state['active']),None)
        if release is None:raise ProjectConflict('尚未启用发布版本，请先发布并启用。')
        if digest(release['payload'])!=release['payload_sha256']:raise ProjectConflict('版本完整性校验失败。')
        return release

    def selected_release(self):
        """Return a validated active snapshot, or explicit baseline selection."""
        with closing(self._connect()) as c:state=self._read(c)
        if state['active'] is None:return None
        return self.published_release(state['active'])

    def published_release(self,uid):
        data,_=self.store.load()
        with closing(self._connect()) as c:state=self._read(c)
        release=next((r for r in state['releases'] if r['id']==uid),None)
        if release is None or release['source_sha256']!=digest(data):raise ProjectConflict('已发布版本缺失或来源已变化，请检查版本记录。')
        from .snapshot_repository import SnapshotRepository
        SnapshotRepository(release)
        return release

    def search(self,q,limit=20,view='working'):
        if view=='working':return self.store.search(q,limit)
        from .candidate_preview import ALIASES
        release=self._active();term=ALIASES.get(q.strip(),q.strip()).casefold()
        items=[d['entity'] for d in release['payload']['entities'] if any(term in s.casefold() for s in [d['entity']['name']]+[x['code'] for x in d['entity'].get('codings',[])])]
        items.sort(key=lambda n:(n['name'].casefold()!=term,n['name'],n['id']))
        return dict(items=items[:limit],total=len(items),truncated=len(items)>limit,version=release['id'])

    def detail(self,uid,view='working'):
        from .browser_projection import browser_graph,records_with_endpoints
        if view=='working':
            detail=project_view(self.store.detail(uid))
            data,_=self.store.load()
            entities=[e for e in data['entities'] if not e.get('withdrawn')]
        else:
            release=self._active()
            detail=next((copy.deepcopy(d) for d in release['payload']['entities'] if d['entity']['id']==uid),None)
            entities=[d['entity'] for d in release['payload']['entities']]
            if detail is not None:
                records={r['id']:r for r in records_with_endpoints(release['payload']['entities'])}
                detail['records']=[records[r['id']] for r in detail['records']]
        if detail is None:return None
        nodes,edges,_=browser_graph(entities,detail['records'],detail['sources'])
        wanted={uid}|{e[k] for e in edges.values() for k in ('source','target')}
        detail['browser_graph']=dict(nodes=[nodes[i] for i in sorted(wanted)],edges=list(edges.values()))
        return detail


workbench=ProjectWorkbench()
