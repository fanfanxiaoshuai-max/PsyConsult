"""Read-only, integrity-checked candidate preview, deliberately independent of GraphRepository."""
import copy
from pathlib import Path
from threading import RLock
from .audit import ROOT,read,digest
from .expert_review import build_packet,source_title
from .remediation import validate_candidate

ALIASES={'抑郁症':'抑郁障碍','双相情感障碍':'双相障碍'}


class CandidatePreview:
    def __init__(self,root=ROOT):
        self.root=Path(root);self._lock=RLock();self._data=None;self._packet=None;self._paths=[];self._stamp=None

    def _fingerprint(self):
        return [(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in self._paths]

    def load(self):
        with self._lock:
            if self._data is not None and self._stamp==self._fingerprint():return self._data,self._packet
            b=self.root/'knowledge_sources/v3'
            self._data=None;self._packet=None
            candidate=read(self.root/'mock_data/kg_v3_candidate/candidate.json')
            validate_candidate(candidate,self.root)
            packet=read(b/'expert/packet.json');expected=build_packet(self.root)
            expected['generated_on']=packet['generated_on']
            if digest(packet)!=digest(expected):raise ValueError('Expert packet stale or modified')
            paths=[self.root/'mock_data/kg_v3_candidate/candidate.json',b/'expert/packet.json',b/'expert/sources.json',b/'search_attempts.json']
            paths.extend(b/name for name in candidate['input_sha256'])
            paths.extend((b/'baseline').glob('*.json'))
            for catalog_path in [b/'catalog.json',b/'remediation/sources.json',b/'expert/sources.json']:
                for s in read(catalog_path).values():
                    if s.get('local_snapshot'):
                        path=(self.root/s['local_snapshot']).resolve()
                        if not path.is_relative_to(self.root.resolve()):raise ValueError('Source outside workspace')
                        if path.exists():paths.append(path)
            self._paths=sorted(set(paths));self._stamp=self._fingerprint()
            self._data=candidate;self._packet=packet
            return candidate,packet

    def stats(self):
        data,packet=self.load()
        return dict(version=data['version'],summary=data['summary'],evidence_review=packet['summary'],
            notice='候选预览 · 临床专家未审核 · 不进入聊天推理',
            activation_ready=False,read_only=True,expert_review='pending')

    def search(self,query,limit=20):
        data,_=self.load();q=ALIASES.get(query.strip(),query.strip()).casefold()
        items=[]
        for n in data['entities']:
            if n.get('withdrawn'):continue
            terms=[n['name']]+[c['code'] for c in n.get('codings',[])]
            if any(q in t.casefold() for t in terms):
                items.append(dict(id=n['id'],name=n['name'],label=n['label'],expert_review='pending'))
        items.sort(key=lambda n:(n['name'].casefold()!=q,n['name'],n['id']))
        return dict(items=items[:limit],total=len(items),truncated=len(items)>limit,version=data['version'])

    def detail(self,uid):
        data,packet=self.load()
        entity=next((e for e in data['entities'] if e['id']==uid and not e.get('withdrawn')),None)
        if entity is None:return None
        records=[]
        names={e['id']:e['name'] for e in data['entities']}
        catalog=read(self.root/'knowledge_sources/v3/catalog.json')
        for a in data['structured']['qualified_assertions']:
            if a['subject_id']==uid or (a.get('related_concept') or {}).get('entity_id')==uid:
                proof_view=[dict(p,source_title=source_title(p['source_id'],catalog[p['source_id']])) for p in a['provenance']]
                records.append(dict(id=a['id'],kind='qualified_assertion',title=a['provenance'][0]['audited_finding'],
                    subject_id=a['subject_id'],related_id=(a.get('related_concept') or {}).get('entity_id'),
                    subject_name=names[a['subject_id']],related_name=names.get((a.get('related_concept') or {}).get('entity_id','')),
                    predicate=a['predicate'],context=a['context'],evidence=proof_view,
                    audit_item_ids=a['audit_item_ids'],expert_review='pending',reasoning_eligible=False))
        for r in data['structured']['clinical_records']:
            if r['subject_id']==uid or any(p.get(k)==uid for p in r['parameters'] for k in ('from_entity','to_entity')) or uid in [r['context'].get('inhibitor_id'),r['context'].get('affected_id')]:
                s=catalog[r['source_id']]
                records.append(dict(id=r['id'],kind=r['kind'],title=r['evidence']['summary'],
                    subject_id=r['subject_id'],related_id=None,subject_name=names[r['subject_id']],related_name=None,
                    predicate='HAS_SCOPED_RULE',context=dict(r['context'],parameters=r['parameters'],constraints=r['constraints']),
                    evidence=[dict(source_id=r['source_id'],source_title=source_title(r['source_id'],s),
                        region=s['region'],edition=s.get('label_revision',s.get('edition')),sha256=s['sha256'],
                        locator=r['evidence']['locator'],scope_conditions=r['scope']['conditions'])],
                    audit_item_ids=r['evidence']['item_ids'],expert_review='pending',reasoning_eligible=False))
        source_index={sid:dict(id=sid,title=source_title(sid,s),url=s['url'],
            region=s['region'],edition=s.get('label_revision',s.get('edition')),sha256=s.get('sha256'))
            for sid,s in catalog.items() if s.get('url','').startswith('https://')}
        used={p['source_id'] for r in records for p in r['evidence']}
        # Each original item stays available in the separate review queue; never treat old payloads as new facts.
        queue=[r for r in packet['rows'] if (r['kind']=='entity' and r['original'].get('id')==uid) or
               (r['kind']=='property' and r['original'].get('entity_id')==uid) or
               (r['kind']=='relation' and uid in (r['original'].get('source'),r['original'].get('target')))]
        return dict(entity={k:entity[k] for k in ('id','name','label','codings','related_categories','course_definition') if k in entity},
            records=records,sources=[source_index[sid] for sid in sorted(used)],
            review_item_ids=[r['item_id'] for r in queue],review_counts=dict(
                insufficient=sum(r['original_status']=='insufficient_evidence' for r in queue),
                withdrawn=sum((r.get('candidate_change') or {}).get('after','missing') is None for r in queue)),
            version=data['version'],expert_review='pending',activation_ready=False)

    def reviews(self,q='',status='all',offset=0,limit=30):
        _,packet=self.load();needle=q.strip().casefold()
        rows=[]
        for row in packet['rows']:
            withdrawn=(row.get('candidate_change') or {}).get('after','missing') is None
            if status=='withdrawn' and not withdrawn:continue
            if status not in {'all','withdrawn'} and row['original_status']!=status:continue
            if needle and needle not in (row['summary']+' '+row['item_id']).casefold():continue
            rows.append(row)
        return dict(items=copy.deepcopy(rows[offset:offset+limit]),total=len(rows),offset=offset,limit=limit)

    def export(self):return copy.deepcopy(self.load()[1])


preview=CandidatePreview()
