"""Project scoped records onto their real entities for browsing only."""
import copy
from .audit import digest


def records_with_endpoints(details):
    """Recover old snapshot endpoints from sealed detail membership, never name order.

    Published bytes and their checksums stay intact. New releases include explicit IDs.
    Ambiguous legacy membership is rejected rather than attaching to a namesake.
    """
    entities={d['entity']['id']:d['entity'] for d in details}
    records={};members={}
    for detail in details:
        for record in detail['records']:
            records[record['id']]=copy.deepcopy(record)
            members.setdefault(record['id'],set()).add(detail['entity']['id'])
    for record in records.values():
        for field,name_field in [('subject_id','subject_name'),('related_id','related_name')]:
            name=record.get(name_field)
            if not name:
                record[field]=None
                continue
            uid=record.get(field)
            candidates=[i for i in members[record['id']] if entities[i]['name']==name]
            if uid is None:
                if len(candidates)!=1:raise ValueError('Ambiguous published record endpoint: '+record['id'])
                uid=candidates[0]
            if uid not in candidates:raise ValueError('Published endpoint membership mismatch')
            record[field]=uid
    return list(records.values())


def browser_graph(entities, records, source_list):
    nodes={e['id']:dict(id=e['id'],name=e['name'],label=e['label'],
        aliases=e.get('aliases',[]),legacy_id='',properties={'records':[]},source_ids=[]) for e in entities}
    names={}
    for node in nodes.values():names.setdefault(node['name'],[]).append(node['id'])
    def endpoint(record,key,name_key):
        name=record.get(name_key)
        if not name:return None
        uid=record.get(key)
        if uid is None:
            candidates=names.get(name,[])
            if len(candidates)!=1:raise ValueError('Ambiguous graph endpoint: '+name)
            uid=candidates[0]
        if uid not in nodes or nodes[uid]['name']!=name:raise ValueError('Invalid graph endpoint')
        return uid
    sources={s['id']:dict(copy.deepcopy(s),file='',pointer='',
        review_status='source_checked_by_agent',original=copy.deepcopy(s)) for s in source_list}
    edges={}
    for record in {r['id']:r for r in records}.values():
        subject=endpoint(record,'subject_id','subject_name')
        related=endpoint(record,'related_id','related_name')
        source_ids=sorted({p['source_id'] for p in record['evidence']})
        for uid in {subject,related}-{None}:
            node=nodes[uid]
            node['properties']['records'].append(copy.deepcopy(record))
            node['source_ids']=sorted(set(node['source_ids'])|set(source_ids))
        # A definition or single-entity rule belongs in entity details, not a duplicate node.
        if not related or related==subject:
            continue
        left,right=sorted((subject,related))
        uid='scoped-link:'+digest([left,right])[:24]
        if uid not in edges:
            edges[uid]=dict(id=uid,source=left,target=right,type='HAS_QUALIFIED_ASSERTION',
                properties={'records':[]},source_ids=[],reasoning_eligible=False,project_record=True)
        edge=edges[uid]
        edge['properties']['records'].append(copy.deepcopy(record))
        edge['source_ids']=sorted(set(edge['source_ids'])|set(source_ids))
    return nodes,edges,sources
