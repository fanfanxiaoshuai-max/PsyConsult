"""The full audit cannot hide records or confuse structural and medical review."""
import copy,hashlib,json,shutil,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import freeze,validate_audit,report,read,write,apply_batch

@pytest.fixture
def audit_root(tmp_path):
    for folder,names in [('mock_data/kg_v2',['entities','relations','sources','resolutions','aliases','review']),('knowledge_sources',['catalog','evidence','verification'])]:
        target=tmp_path/folder;target.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copyfile(ROOT/folder/(name+'.json'),target/(name+'.json'))
    freeze(tmp_path)
    return tmp_path

def test_all_baseline_objects_are_accounted_for(audit_root):
    r=report(audit_root)
    assert r['total']==899 and r['counts_by_kind']=={'entity':230,'property':250,'relation':406,'quarantine':13}
    assert r['counts_by_status']=={'pending_review':838,'structural_only':61}
    assert r['medical_review_completed']==0 and r['clinical_expert_reviewed']==0
    assert r['prior_v2_checked_relations']==30 and not r['full_medical_review_complete'] and not r['activation_ready']
    inv=read(audit_root/'knowledge_sources/v3/inventory.json')
    assert all(i['structure_checked'] for i in inv.values())
    assert sum(bool(i['structural_issues']) for i in inv.values())==13

def test_rerun_preserves_review_and_frozen_denominator(audit_root):
    p=audit_root/'knowledge_sources/v3/reviews.json';rows=read(p);uid=next(iter(rows));rows[uid]['reason']='Still waiting for original source';write(p,rows)
    assert freeze(audit_root)==read(audit_root/'knowledge_sources/v3/inventory.json')
    assert read(p)[uid]['reason']=='Still waiting for original source'
    # Live data may evolve; the sealed audit baseline cannot silently shrink.
    write(audit_root/'mock_data/kg_v2/relations.json',[])
    assert report(audit_root)['counts_by_kind']['relation']==406

@pytest.mark.parametrize('target',['inventory','baseline'])
def test_changed_inventory_or_baseline_is_rejected(audit_root,target):
    p=audit_root/('knowledge_sources/v3/inventory.json' if target=='inventory' else 'knowledge_sources/v3/baseline/entities.json')
    value=read(p)
    if isinstance(value,dict):value.pop(next(iter(value)))
    else:value.pop()
    write(p,value)
    with pytest.raises(ValueError):report(audit_root)

@pytest.mark.parametrize('change',['missing','structure_as_medicine','invented_expert','false_completion_date','no_evidence'])
def test_false_completion_is_rejected(audit_root,change):
    p=audit_root/'knowledge_sources/v3/reviews.json';rows=read(p);uid=next(k for k,v in rows.items() if v['status']=='pending_review')
    if change=='missing':rows.pop(uid)
    elif change=='structure_as_medicine':rows[uid].update(status='structural_only',reviewer='agent',reviewed_at='2026-10-19')
    elif change=='invented_expert':rows[uid]['expert_review']='approved'
    elif change=='false_completion_date':rows[uid]['reviewed_at']='2026-10-19'
    else:rows[uid].update(status='source_supported',reviewer='agent',reviewed_at='2026-10-19')
    write(p,rows)
    with pytest.raises(ValueError):validate_audit(audit_root)


def attach_test_proof(root):
    base=root/'knowledge_sources/v3';rows=read(base/'reviews.json');uid=next(k for k,v in rows.items() if v['status']=='pending_review')
    file=root/'.tools/test-source.html';file.parent.mkdir();file.write_text('<article id="rec-1">Test only original</article>',encoding='utf-8')
    sha=hashlib.sha256(file.read_bytes()).hexdigest()
    write(base/'catalog.json',{'source':dict(id='source',url='https://example.org/source',region='UK',format='html',sha256=sha,local_snapshot='.tools/test-source.html',retrieved_at='2026-10-19',availability='available',used_for_claims=True)})
    write(base/'evidence.json',{'E1':dict(id='E1',source_id='source',source_sha256=sha,item_ids=[uid],locator=dict(kind='html_anchor',anchors=['rec-1']),summary='Synthetic proof only',conditions='Test fixture',checked_at='2026-10-19',reviewer='agent',scope='medical_source_comparison')})
    rows[uid].update(status='source_supported',reviewer='agent',reviewed_at='2026-10-19',evidence_ids=['E1']);write(base/'reviews.json',rows)
    return uid


def test_exact_item_and_source_proof_are_required(audit_root):
    attach_test_proof(audit_root)
    assert report(audit_root)['source_supported_count']==1

@pytest.mark.parametrize('mutation',['unavailable','wrong_hash','wrong_anchor','not_used','wrong_item','structural_proof','changed_bytes','amendment_without_proposal'])
def test_invalid_source_or_amendment_fails_closed(audit_root,mutation):
    uid=attach_test_proof(audit_root);base=audit_root/'knowledge_sources/v3'
    c=read(base/'catalog.json');e=read(base/'evidence.json');rows=read(base/'reviews.json')
    if mutation=='unavailable':c['source']['availability']='unavailable'
    elif mutation=='wrong_hash':e['E1']['source_sha256']='0'*64
    elif mutation=='wrong_anchor':e['E1']['locator']['anchors']=['not-present']
    elif mutation=='not_used':c['source']['used_for_claims']=False
    elif mutation=='wrong_item':e['E1']['item_ids']=[]
    elif mutation=='structural_proof':e['E1']['scope']='structural_comparison'
    elif mutation=='changed_bytes':(audit_root/'.tools/test-source.html').write_text('changed',encoding='utf-8')
    else:rows[uid]['status']='amended'
    write(base/'catalog.json',c);write(base/'evidence.json',e);write(base/'reviews.json',rows)
    with pytest.raises(ValueError):validate_audit(audit_root)


def test_cannot_call_missing_evidence_without_recording_attempt(audit_root):
    base=audit_root/'knowledge_sources/v3';rows=read(base/'reviews.json');uid=next(k for k,v in rows.items() if v['status']=='pending_review')
    rows[uid].update(status='insufficient_evidence',reviewer='agent',reviewed_at='2026-10-19');write(base/'reviews.json',rows)
    with pytest.raises(ValueError):validate_audit(audit_root)
    rows[uid]['search_attempt_ids']=['attempt'];write(base/'reviews.json',rows)
    write(base/'search_attempts.json',{'attempt':dict(item_ids=[uid],method='document_search',performed_at='2026-10-19',queries=['exact synthetic claim'],result='not supported in the examined source',source_ids=[])})
    assert report(audit_root)['medical_review_completed']==1

def test_missing_ledger_must_not_silently_reset_completed_work(audit_root):
    (audit_root/'knowledge_sources/v3/reviews.json').unlink()
    with pytest.raises(ValueError,match='refuse to reset'):freeze(audit_root)


def proposed_test_batch(root):
    prior=attach_test_proof(root);base=root/'knowledge_sources/v3'
    inv=read(base/'inventory.json');rows=read(base/'reviews.json')
    uid=next(k for k,v in rows.items() if v['status']=='pending_review')
    claim=copy.deepcopy(read(base/'evidence.json')['E1'])
    claim.update(id='E2',item_ids=[uid])
    row=dict(item_id=uid,original_sha256=inv[uid]['original_sha256'],batch_id='test-batch',status='source_supported',reason='Synthetic comparison',evidence_ids=['E2'],search_attempt_ids=[],expert_review='pending',reviewer='agent',reviewed_at='2026-10-20')
    batch=dict(id='test-batch',reviews={uid:row},evidence={'E2':claim})
    file=root/'batch.json';write(file,batch)
    return file,batch,uid,prior


def test_batch_is_idempotent_and_preserves_prior_reviews(audit_root):
    file,batch,uid,prior=proposed_test_batch(audit_root)
    base=audit_root/'knowledge_sources/v3';before=read(base/'reviews.json')[prior]
    first=apply_batch(file,audit_root)
    assert first['medical_review_completed']==2
    assert apply_batch(file,audit_root)==first
    assert read(base/'reviews.json')[prior]==before


@pytest.mark.parametrize('mutation',['wrong_original','invented_expert','bad_proof','missing_proof','overwrite_prior'])
def test_invalid_batch_does_not_write_any_ledger(audit_root,mutation):
    file,batch,uid,prior=proposed_test_batch(audit_root)
    base=audit_root/'knowledge_sources/v3'
    paths=[base/(name+'.json') for name in ('reviews','evidence','catalog','search_attempts')]
    before=[p.read_bytes() for p in paths]
    if mutation=='wrong_original':batch['reviews'][uid]['original_sha256']='0'*64
    elif mutation=='invented_expert':batch['reviews'][uid]['expert_review']='approved'
    elif mutation=='bad_proof':batch['evidence']['E2']['source_sha256']='0'*64
    elif mutation=='missing_proof':batch['reviews'][uid]['evidence_ids']=[]
    else:
        row=batch['reviews'].pop(uid)
        row.update(item_id=prior,original_sha256=read(base/'inventory.json')[prior]['original_sha256'])
        batch['reviews'][prior]=row
    write(file,batch)
    with pytest.raises(ValueError):apply_batch(file,audit_root)
    assert [p.read_bytes() for p in paths]==before


def test_medication_batch_preserves_scope_and_inadequate_evidence():
    batch=read(ROOT/'knowledge_sources/v3/batches/2026-10-20-medication-02.json')
    rows=batch['reviews'];evidence=batch['evidence']
    assert len(rows)==55
    assert sum(r['status']=='source_supported' for r in rows.values())==30
    assert sum(r['status']=='insufficient_evidence' for r in rows.values())==5
    assert all(r['expert_review']=='pending' for r in rows.values())
    dose=rows['property:fcc7bf9f26197edd8426900f:dose_max']['proposed_change']['replacement']
    assert 'not an endorsed maximum' in dose['over_80mg_statement']
    assert 'elderly' in dose and 'under_18_CN' in dose
    washout=rows['relation:72eab889786efdf949c885cd']['proposed_change']['replacement']
    assert washout['maoi_to_sertraline_days_min']==14
    assert washout['sertraline_to_maoi_days_min']==14
    assert '升高和降低' in evidence['B02-RECHECK-F04']['summary']
    assert '每个药物' in evidence['B02-RECHECK-L06']['conditions']
    assert rows['relation:2c2faf6fabc3a899f8f98956']['status']=='insufficient_evidence'
