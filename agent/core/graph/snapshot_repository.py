"""Read scoped published records without converting them into unconditional edges."""
import copy
from .audit import digest
from .retriever import rank_entities,infer_group
from .browser_projection import browser_graph,records_with_endpoints


class SnapshotRepository:
    is_snapshot=True

    def __init__(self,release):
        payload=release['payload']
        if digest(payload)!=release['payload_sha256']:raise ValueError('Release checksum mismatch')
        self.version=release['id'];self.label=release['name'];self.sha256=release['payload_sha256']
        self._details=copy.deepcopy(payload['entities'])
        approved=set(payload['approved_item_ids']);ids=set();records={}
        for d in self._details:
            e=d['entity']
            if e['id'] in ids or 'entity:'+e['id'] not in approved:raise ValueError('Unapproved or duplicate entity')
            ids.add(e['id'])
            sources={s['id']:s for s in d['sources']}
            for r in d['records']:
                if not r['audit_item_ids'] or not set(r['audit_item_ids'])<=approved:raise ValueError('Unapproved record')
                if not r['context'] or not r['evidence'] or not r['title']:raise ValueError('Unscoped record')
                if r['id'] in records and records[r['id']]!=r:raise ValueError('Conflicting record copies')
                records[r['id']]=r
                for p in r['evidence']:
                    source=sources.get(p['source_id'])
                    if not source or not source['url'].startswith('https://') or not p.get('locator') or not p.get('sha256'):
                        raise ValueError('Record provenance missing')
        names={d['entity']['name'] for d in self._details}
        if not records or any(r['subject_name'] not in names or (r.get('related_name') and r['related_name'] not in names) for r in records.values()):
            raise ValueError('Published record endpoint absent')
        self._browser_records=records_with_endpoints(self._details)

    def entities(self):
        entities=[]
        for d in self._details:
            e=d['entity'];aliases=[c['code'] for c in e.get('codings',[])]
            if e['name']=='抑郁障碍':aliases.append('抑郁症')
            if e['name']=='双相障碍':aliases.append('双相情感障碍')
            entities.append(dict(id=e['id'],name=e['name'],label=e['label'],aliases=aliases))
        return entities

    def _browser_graph(self):
        return browser_graph(self.entities(),self._browser_records,
            [s for d in self._details for s in d['sources']])

    def detail(self,uid):
        nodes,_,sources=self._browser_graph();node=nodes.get(uid)
        return dict(version=self.version,entity=node,sources=[sources[s] for s in node['source_ids']]) if node else None

    def neighbors(self,ids,limit=40,relation_type=None,include_unreviewed=False,**kwargs):
        nodes,edges,sources=self._browser_graph()
        records=[e for e in edges.values() if (e['source'] in ids or e['target'] in ids) and (not relation_type or e['type']==relation_type)]
        records.sort(key=lambda e:e['id']);selected=records[:limit]
        wanted=set(ids)|{e[k] for e in selected for k in ('source','target')}
        used={s for uid in wanted if uid in nodes for s in nodes[uid]['source_ids']}
        return dict(version=self.version,nodes=[nodes[i] for i in sorted(wanted) if i in nodes],edges=selected,
            sources=[sources[i] for i in sorted(used)],total=len(records),truncated=len(records)>limit,
            message='同一实体仅显示一次；点击连线查看全部关联记录，点击实体查看自身知识。')

    def stats(self):
        nodes,edges,_=self._browser_graph()
        return dict(version=self.version,entities=len(self._details),relations=len(edges),relation_types=['HAS_QUALIFIED_ASSERTION'],
            knowledge_records=len({r['id'] for d in self._details for r in d['records']}),
            pending=[],evidence_notice='知识浏览与问答使用同一发布版本；记录保留适用条件。')

    def retrieve(self,query,limit=20):
        ranked=rank_entities(query,self.entities())
        explicit=[e for e in ranked if any(len(s)>=2 and s.casefold() in query.casefold() for s in [e['name']]+e['aliases'])]
        chosen=(explicit or ranked[:5])[:12];chosen_ids={e['id'] for e in chosen}
        drug_names={e['name'] for e in chosen if e['label']=='Drug'}
        pair=len(drug_names)>=2 and infer_group(query)=='interactions'
        records={};sources={}
        for d in self._details:
            if d['entity']['id'] not in chosen_ids:continue
            for s in d['sources']:sources[s['id']]=s
            for r in d['records']:records[r['id']]=r
        records=sorted(records.values(),key=lambda r:r['id'])
        direct=[];context=[]
        for r in records:
            item=copy.deepcopy(r)
            # Runtime eligibility is for this published copy, never written into frozen data.
            item.pop('expert_review',None);item['project_review']='approved';item['reasoning_eligible']=True
            if pair and not (r['subject_name'] in drug_names and r.get('related_name') in drug_names):context.append(item)
            else:direct.append(item)
        total=len(direct)+len(context)
        direct=direct[:limit];context=context[:max(0,limit-len(direct))]
        used={p['source_id'] for r in direct+context for p in r['evidence']}
        return dict(version=self.version,version_name=self.label,payload_sha256=self.sha256,candidates=chosen,nodes=chosen,edges=[],
            records=direct,context_records=context,sources=[sources[sid] for sid in sorted(used)],
            total=total,truncated=total>limit,pair_query=pair,
            message='仅使用当前发布快照中的带条件记录；未收录不表示不存在风险。',
            evidence_notice='保留原文定位、适用范围、数值方向与不确定性；单药或类别资料不是所问药物对的直接证据。')
