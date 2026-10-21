"""Frozen, exhaustive graph-audit inventory; structural checks never certify medicine."""
import hashlib
import json
import re
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from .normalizer import ROOT

BASELINE_FILES=('entities','relations','sources','resolutions','aliases','review')
AUDIT_VERSION='kg_v3'
TERMINAL={'source_supported','amended','conflicting','insufficient_evidence','unavailable_source','structural_only','quarantined'}
SOURCE_REQUIRED={'source_supported','amended','conflicting'}

def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(dump(value).encode()).hexdigest()
def pointer(term): return str(term).replace('~','~0').replace('/','~1')
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def priority(kind,item,entity=None):
    if kind=='quarantine': return 'P0',2
    if kind=='property':
        key=item['key'].casefold()
        if any(t in key for t in ('dose','range','duration','symptom_count','symptoms','icd','code')): return 'P0',2 if entity['label']=='Drug' else 3
    if kind=='relation':
        rel=item['type']
        if any(t in rel for t in ('CONTRAINDICATED','INTERACT','WASHOUT','DOSE','CONCENTRATION','MONITOR','THERAPEUTIC_RANGE','NEUROTOXIC','NO_SIGNIFICANT','NO_CLINICAL','RISK')): return 'P0',2
        if any(s.startswith('icd11_') for s in item.get('source_ids',[])): return 'P1',3
        return 'P1',4
    if entity and entity['label'] in ('DoseRange','MaxDose','TherapeuticRange','WashoutPeriod','Contraindication','Criterion','Severity'):
        return 'P0',3 if entity['label'] in ('Criterion','Severity') else 2
    if entity and entity['label'] in ('Drug','DrugClass','DrugFormulation'): return 'P1',2
    return 'P1',3

def make_inventory(data):
    entities={e['id']:e for e in data['entities']}
    sources={s['id'] for s in data['sources']}
    items={}
    def add(uid,kind,original,summary,source_ids,entity=None,technical=False,location=None):
        pr,batch=priority(kind,original,entity)
        items[uid]=dict(id=uid,kind=kind,summary=summary,original=original,original_sha256=digest(original),source_ids=source_ids,location=location,priority='P2' if technical else pr,batch=1 if technical else batch,medical_review_required=not technical,structure_checked=True,structural_issues=[])
    for e in data['entities']:
        add('entity:'+e['id'],'entity',e,e['label']+' · '+e['name'],e['source_ids'],e,location=dict(file='baseline/entities.json',entity_id=e['id']))
        for key,value in e['properties'].items():
            # Equality with the existing display name is only a structural fact.
            technical=key in ('name','name_cn') and value==e['name']
            original=dict(entity_id=e['id'],key=key,value=value)
            add('property:'+e['id']+':'+pointer(key),'property',original,e['name']+' / '+key,e['source_ids'],e,technical=technical,location=dict(file='baseline/entities.json',entity_id=e['id'],pointer='/properties/'+pointer(key)))
    for r in data['relations']:
        a=entities.get(r['source'],{}).get('name',r['source']);b=entities.get(r['target'],{}).get('name',r['target'])
        uid='relation:'+r['id']
        add(uid,'relation',r,a+' → '+r['type']+' → '+b,r['source_ids'],location=dict(file='baseline/relations.json',relation_id=r['id']))
        if r['source'] not in entities or r['target'] not in entities: items[uid]['structural_issues'].append('dangling_endpoint')
    for record in data['resolutions']:
        if record['status']!='pending_review': continue
        uid='quarantine:'+record['source_id']
        add(uid,'quarantine',record,record['source_id']+' · '+str(record['original']),[record['source_id']],location=dict(file='baseline/resolutions.json',source_id=record['source_id']))
        items[uid]['structural_issues'].append('unresolved_endpoint_or_type')
    for item in items.values():
        if not item['source_ids'] or not set(item['source_ids'])<=sources:
            item['structural_issues'].append('source_not_in_baseline')
    return items

def freeze(root=ROOT):
    root=Path(root);out=root/'knowledge_sources/v3';out.mkdir(parents=True,exist_ok=True)
    manifest_path=out/'baseline.json'
    if manifest_path.exists() and (out/'inventory.json').exists() and not (out/'reviews.json').exists():
        raise ValueError('Review ledger is missing; refuse to reset completed work')
    if manifest_path.exists():
        manifest=read(manifest_path)
        if manifest['baseline_version']!='kg_v2': raise ValueError('Unexpected baseline')
        for name,expected in manifest['files'].items():
            path=out/'baseline'/name
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError('Frozen baseline changed: '+name)
    else:
        snapshot=out/'baseline';snapshot.mkdir(exist_ok=True)
        files={}
        for name in BASELINE_FILES:
            raw=(root/'mock_data/kg_v2'/(name+'.json')).read_bytes()
            (snapshot/(name+'.json')).write_bytes(raw)
            files[name+'.json']=hashlib.sha256(raw).hexdigest()
        # Source declarations used by the prior 30 claims are also frozen.
        for name in ('catalog','evidence','verification'):
            raw=(root/'knowledge_sources'/(name+'.json')).read_bytes()
            target=name+'-v2.json';(snapshot/target).write_bytes(raw)
            files[target]=hashlib.sha256(raw).hexdigest()
        manifest=dict(version=AUDIT_VERSION,baseline_version='kg_v2',created_at=date.today().isoformat(),files=files)
        write(manifest_path,manifest)
    data={name:read(out/'baseline'/(name+'.json')) for name in BASELINE_FILES}
    inventory=make_inventory(data)
    inventory_path=out/'inventory.json'
    if inventory_path.exists() and read(inventory_path)!=inventory: raise ValueError('Audit inventory differs from frozen baseline')
    if not inventory_path.exists():write(inventory_path,inventory)
    review_path=out/'reviews.json'
    if not review_path.exists():
        reviews={}
        for uid,item in inventory.items():
            technical=not item['medical_review_required']
            reviews[uid]=dict(item_id=uid,status='structural_only' if technical else 'pending_review',reason='原属性与原实体显示名称逐字一致，仅完成仓库结构一致性检查，不证明医学名称或分类正确。' if technical else '已纳入全量台账；医学原文核对尚未完成。',evidence_ids=[],search_attempt_ids=[],expert_review='pending',reviewer='agent' if technical else None,reviewed_at=date.today().isoformat() if technical else None)
        write(review_path,reviews)
    for filename,empty in [('catalog.json',{}),('evidence.json',{}),('search_attempts.json',{}),('findings.json',[])]:
        if not (out/filename).exists(): write(out/filename,empty)
    return inventory

def validate_audit(root=ROOT, *, staged=None):
    root=Path(root);out=root/'knowledge_sources/v3'
    inventory=freeze(root)
    data={name:read(out/(name+'.json')) for name in ('reviews','evidence','catalog','search_attempts')}
    if staged is not None:
        if set(staged)!=set(data): raise ValueError('Staged audit must include every ledger')
        data=staged
    reviews,evidence,catalog,attempts=(data[name] for name in ('reviews','evidence','catalog','search_attempts'))
    if set(reviews)!=set(inventory): raise ValueError('Every frozen item must have exactly one review row')
    verified_raw={}
    for uid,row in reviews.items():
        status=row['status']
        if row['item_id']!=uid or status not in TERMINAL|{'pending_review'}: raise ValueError('Invalid review identity or state: '+uid)
        if not row.get('reason') or row.get('expert_review')!='pending': raise ValueError('Missing reason or unsubstantiated expert approval: '+uid)
        if status=='pending_review':
            if row.get('reviewed_at'): raise ValueError('Pending review must not appear completed: '+uid)
            continue
        if not row.get('reviewed_at') or not row.get('reviewer'): raise ValueError('Missing review audit trail: '+uid)
        if status=='structural_only' and inventory[uid]['medical_review_required']: raise ValueError('Structural result cannot certify medical content: '+uid)
        if status=='amended' and not row.get('proposed_change'):
            raise ValueError('An amendment needs an explicit proposed change: '+uid)
        if status in SOURCE_REQUIRED and not row.get('evidence_ids'): raise ValueError('Medical conclusion needs evidence: '+uid)
        if status in {'insufficient_evidence','unavailable_source','quarantined'} and not row.get('search_attempt_ids') and not row.get('evidence_ids'): raise ValueError('Negative conclusion needs a documented examination: '+uid)
        for aid in row.get('search_attempt_ids',[]):
            if aid not in attempts or uid not in attempts[aid].get('item_ids',[]): raise ValueError('Missing item-specific search attempt: '+uid)
            attempt=attempts[aid]
            if not all(attempt.get(k) for k in ('method','performed_at','queries','result')) or any(sid not in catalog for sid in attempt.get('source_ids',[])): raise ValueError('Incomplete documented examination: '+uid)
        for eid in row.get('evidence_ids',[]):
            claim=evidence.get(eid,{})
            source=catalog.get(claim.get('source_id'),{})
            if uid not in claim.get('item_ids',[]): raise ValueError('Evidence must reference this exact audit item: '+uid)
            if not claim.get('locator') or not claim.get('summary') or not claim.get('conditions') or not claim.get('checked_at') or not claim.get('reviewer'): raise ValueError('Incomplete scoped evidence: '+eid)
            if claim.get('scope') not in ('medical_source_comparison','structural_comparison'): raise ValueError('Unknown comparison scope: '+eid)
            if status in SOURCE_REQUIRED and claim['scope']!='medical_source_comparison': raise ValueError('Structural proof cannot certify medicine: '+uid)
            if not source.get('url','').startswith('https://') or not re.fullmatch('[a-f0-9]{64}',source.get('sha256','')) or not source.get('retrieved_at') or not source.get('region') or source.get('availability')!='available' or source.get('used_for_claims') is not True: raise ValueError('Missing available original source: '+eid)
            if claim.get('source_sha256')!=source['sha256']: raise ValueError('Claim was reviewed against different source bytes: '+eid)
            raw_path=(root/source.get('local_snapshot','')).resolve()
            if not raw_path.is_relative_to(root.resolve()) or not raw_path.is_file(): raise ValueError('Original snapshot missing or outside audit workspace: '+eid)
            seal=(str(raw_path),source['sha256'])
            if seal not in verified_raw:
                raw=raw_path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=source['sha256']: raise ValueError('Original source snapshot changed: '+eid)
                verified_raw[seal]=raw
            raw=verified_raw[seal]
            locator=claim['locator']
            if locator.get('kind')=='html_anchor':
                if source.get('format')!='html' or not locator.get('anchors') or any(('id="'+a+'"').encode() not in raw for a in locator['anchors']): raise ValueError('Original recommendation anchor missing: '+eid)
            elif locator.get('kind')=='pdf_pages':
                if source.get('format')!='pdf' or not locator.get('pages') or any(type(p) is not int or p<1 or p>source.get('pdf_pages',0) for p in locator['pages']): raise ValueError('Invalid PDF page locator: '+eid)
            else: raise ValueError('Unsupported source locator: '+eid)
    return inventory,reviews


def apply_batch(batch_path, root=ROOT):
    """Validate a complete proposed batch before writing; never overwrite earlier work.

    Supporting ledgers are written first and reviews last. Reapplying identical
    content is safe, including recovery after an interrupted supporting-file write.
    """
    root=Path(root);out=root/'knowledge_sources/v3'
    inventory,_=validate_audit(root)
    batch=read(batch_path)
    if not batch.get('id') or not batch.get('reviews'): raise ValueError('Empty or unnamed batch')
    data={name:read(out/(name+'.json')) for name in ('reviews','evidence','catalog','search_attempts')}
    for name in ('evidence','search_attempts'):
        for key,value in batch.get(name,{}).items():
            if key in data[name] and data[name][key]!=value: raise ValueError('Conflicting batch evidence: '+key)
            data[name][key]=value
    for uid,row in batch['reviews'].items():
        if uid not in inventory or row.get('original_sha256')!=inventory[uid]['original_sha256']:
            raise ValueError('Batch original does not match frozen item: '+uid)
        if row.get('batch_id')!=batch['id'] or row.get('status') not in TERMINAL-{'structural_only'}:
            raise ValueError('Invalid batch review: '+uid)
        existing=data['reviews'][uid]
        if existing['status']!='pending_review' and existing!=row:
            raise ValueError('Refuse to overwrite completed review: '+uid)
        data['reviews'][uid]=row
    for claim in batch.get('evidence',{}).values():
        sid=claim['source_id']
        if sid not in data['catalog']: raise ValueError('Unknown source: '+sid)
        data['catalog'][sid]['used_for_claims']=True
    validate_audit(root,staged=data)
    for name in ('catalog','evidence','search_attempts','reviews'):
        write(out/(name+'.json'),data[name])
    return report(root)

def report(root=ROOT):
    root=Path(root);out=root/'knowledge_sources/v3';inventory,reviews=validate_audit(root)
    data=read(out/'baseline/relations.json')
    result=dict(implementation_stage='inventory_and_initial_source_comparison',candidate_version=AUDIT_VERSION,baseline_version='kg_v2',updated_at=date.today().isoformat(),total=len(inventory),counts_by_kind=dict(Counter(i['kind'] for i in inventory.values())),counts_by_status=dict(Counter(r['status'] for r in reviews.values())),counts_by_priority=dict(Counter(i['priority'] for i in inventory.values())),counts_by_batch=dict(Counter(i['batch'] for i in inventory.values())),pending_by_priority=dict(Counter(inventory[uid]['priority'] for uid,r in reviews.items() if r['status']=='pending_review')),inventory_complete=True,structural_examination_count=len(inventory),structural_issue_items=sum(bool(i['structural_issues']) for i in inventory.values()),medical_review_required=sum(i['medical_review_required'] for i in inventory.values()),medical_review_completed=sum(i['medical_review_required'] and reviews[uid]['status']!='pending_review' for uid,i in inventory.items()),source_supported_count=sum(r['status']=='source_supported' for r in reviews.values()),clinical_expert_reviewed=0,prior_v2_checked_relations=sum(e.get('reasoning_eligible') is True for e in data),full_medical_review_complete=all(r['status']!='pending_review' for r in reviews.values()),activation_ready=False)
    outcomes=Counter(r['status'] for r in reviews.values())
    all_adjudicated=outcomes['pending_review']==0
    result.update(
        implementation_stage='source_comparison_complete_with_open_findings' if all_adjudicated else 'source_comparison_in_progress',
        all_items_adjudicated=all_adjudicated,
        full_medical_verification_complete=False,
        unresolved_medical_items=sum(outcomes[s] for s in ('insufficient_evidence','unavailable_source','quarantined','conflicting')),
        candidate_amendments_not_applied=outcomes['amended'],
        completion_definition='All frozen items have a scoped review outcome; this does not mean all claims are supported, amendments applied, or clinically expert approved.',
    )
    write(out/'progress.json',result)
    findings_path=out/'findings.json'
    findings=[f for f in read(findings_path) if f.get('category')=='structural'] if findings_path.exists() else []
    for uid,row in reviews.items():
        if row['status'] not in {'amended','insufficient_evidence','conflicting'}: continue
        finding=dict(id=('AMEND-' if row['status']=='amended' else 'REVIEW-')+uid,category='medical_source_comparison',status='candidate_only',review_status=row['status'],item_id=uid,summary=inventory[uid]['summary'],reason=row['reason'],evidence_ids=row.get('evidence_ids',[]),expert_review='pending')
        for key in ('proposed_change','candidate_disposition','search_attempt_ids'):
            if row.get(key):finding[key]=row[key]
        findings.append(finding)
    write(findings_path,findings)
    for batch in range(1,5):
        write(out/('batch-'+str(batch)+'.json'),[uid for uid,i in inventory.items() if i['batch']==batch])
    return result
