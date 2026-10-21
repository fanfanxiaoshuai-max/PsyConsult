"""Guard the exhaustive review denominator and clinically material scope limits."""
import json
from pathlib import Path
from collections import Counter

BASE=Path(__file__).resolve().parents[2]/'knowledge_sources/v3'

def read(name):return json.loads((BASE/name).read_text(encoding='utf-8-sig'))

def test_remainder_is_exactly_the_frozen_unreviewed_scope():
    inventory=read('inventory.json');rows=read('reviews.json')
    second=read('batches/2026-10-20-medication-02.json')
    remainder=read('batches/2026-10-20-remainder-03.json')
    initial={uid for uid,row in rows.items() if inventory[uid]['medical_review_required'] and row['reviewed_at']=='2026-10-19'}
    expected={uid for uid,item in inventory.items() if item['medical_review_required']}-initial-set(second['reviews'])
    assert len(initial)==37 and len(expected)==746
    assert set(remainder['reviews'])==expected
    assert set(remainder['reviews']).isdisjoint(second['reviews'])
    for uid,row in remainder['reviews'].items():
        assert row['original_sha256']==inventory[uid]['original_sha256']
        assert row['expert_review']=='pending'
        assert row['evidence_ids']

def test_all_quarantined_originals_remain_quarantined():
    inventory=read('inventory.json');batch=read('batches/2026-10-20-remainder-03.json')
    ids={uid for uid,item in inventory.items() if item['kind']=='quarantine'}
    assert len(ids)==13
    for uid in ids:
        row=batch['reviews'][uid]
        assert row['status']=='quarantined'
        assert row['search_attempt_ids'] and row['candidate_disposition']

def test_negative_reviews_have_exact_item_specific_examinations():
    batch=read('batches/2026-10-20-remainder-03.json')
    for uid,row in batch['reviews'].items():
        if row['status'] not in ('insufficient_evidence','quarantined'):continue
        assert row['candidate_disposition']
        for aid in row['search_attempt_ids']:
            attempt=batch['search_attempts'][aid]
            assert attempt['item_ids']==[uid]
            assert attempt['source_ids'] and attempt['result'] and attempt['queries']

def test_cross_region_and_experimental_limits_are_preserved():
    batch=read('batches/2026-10-20-remainder-03.json');proof=batch['evidence']
    assert '研究' in proof['B03-DBS-ROLE']['summary']
    assert '研究' in proof['B03-RTMS-ROLE']['summary']
    assert '体外' in proof['B03-LAM-SER']['summary']
    assert 'T43.6' in proof['B03-SEROTONIN-CODE']['summary']
    assert 'K76.0' in proof['B03-HEPATIC-CODE']['summary']
    assert '7天' in proof['B03-VEN-MAOI']['summary']
    assert 'PHARMACOKINETIC_PROPS' in proof['B03-VAL-RANGE']['locator']['anchors']
    linked=[r for r in batch['reviews'].values() if 'B03-LI-RANGE' in r['evidence_ids']]
    assert all('B03-LI-NICE-CONCENTRATION' in r['evidence_ids'] for r in linked if ':dose_start' not in r['item_id'])
    assert 'US' in proof['B03-LI-NICE-CONCENTRATION']['conditions'] or '美国' in proof['B03-LI-NICE-CONCENTRATION']['conditions']

def test_excluded_wrong_topic_source_is_not_used():
    batch=read('batches/2026-10-20-remainder-03.json');catalog=read('catalog.json')
    assert not catalog['nice_dbs_ocd']['used_for_claims']
    assert all(p['source_id']!='nice_dbs_ocd' for p in batch['evidence'].values())
    assert batch['evidence']['B03-DBS-ROLE']['source_id']=='nice_dbs_ocd_htg577'

def test_full_review_does_not_claim_all_content_is_verified_or_deployed():
    result=read('progress.json');rows=read('reviews.json')
    assert result['total']==len(rows)==899
    assert result['all_items_adjudicated']
    assert result['counts_by_status'].get('pending_review',0)==0
    assert not result['full_medical_verification_complete']
    assert not result['activation_ready'] and result['clinical_expert_reviewed']==0
    assert result['unresolved_medical_items']>0 and result['candidate_amendments_not_applied']>0
    assert Counter(row['status'] for row in rows.values())==result['counts_by_status']
