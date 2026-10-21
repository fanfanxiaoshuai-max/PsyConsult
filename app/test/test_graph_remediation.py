"""Candidate coverage, provenance, uncertainty and release boundaries."""
import copy
import importlib.util
import sys
from collections import Counter
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read, digest
from core.graph.remediation import build_candidate, validate_candidate, source_receipts
from core.graph.repository import GraphRepository
from core.graph.release import require_released_version


@pytest.fixture(scope='module')
def candidate():
    return build_candidate(ROOT)


def test_frozen_scope_and_all_amendments_have_real_safety_actions(candidate):
    assert len(candidate['actions'])==899
    amendments=[a for a in candidate['actions'].values() if a['status']=='amended']
    assert Counter(a['action'] for a in amendments)=={
        'remove_original_property':106,'disable_original_relation':230,'restrict_entity_to_display':63}
    assert len(candidate['replacement_drafts'])==399
    assert len(candidate['quarantine'])==13
    for row in candidate['replacement_drafts']:
        assert row['proposed_change'] and row['evidence']
        assert row['expert_review']=='pending' and row['reasoning_eligible'] is False


def test_no_retired_properties_or_aliases_leak_into_candidate(candidate):
    entities={e['id']:e for e in candidate['entities']}
    inventory=read(ROOT/'knowledge_sources/v3/inventory.json')
    for uid,action in candidate['actions'].items():
        if action['status'] in {'amended','insufficient_evidence'} and inventory[uid]['kind']=='property':
            original=inventory[uid]['original']
            assert original['key'] not in entities[original['entity_id']]['properties']
    assert all(e['aliases']==[] and e['reasoning_eligible'] is False for e in entities.values())
    assert len(candidate['relations'])==406
    assert all(e['reasoning_eligible'] is False and not e['properties'] for e in candidate['relations'])


def test_supplement_covers_all_55_without_promoting_original_claims(candidate):
    rows=[a['supplement'] for a in candidate['actions'].values() if 'supplement' in a]
    assert len(rows)==55
    assert Counter(r['outcome'] for r in rows)==dict(scoped_replacement_available=37,
        original_claim_not_established=7,conflicting_evidence=2,still_open=9)
    assert all(r['expert_review']=='pending' and r['original_claim_enabled'] is False for r in rows)
    assert len(candidate['source_receipts'])==21
    assert sum(r['locator']['kind']=='pubmed_article_abstract' for r in candidate['source_receipts'].values())==15
    assert all(r['locator'].get('full_article_reviewed') is False for r in candidate['source_receipts'].values()
               if r['locator']['kind']=='pubmed_article_abstract')


def test_conflicting_and_reverse_direction_studies_do_not_approve_edges(candidate):
    actions=candidate['actions']
    for rid in ['38ef2afd8538ed94fd34d365','f9c67439fdf6541170c3c2e8']:
        row=actions['relation:'+rid]['supplement']
        assert row['outcome']=='conflicting_evidence'
        assert set(row['source_ids'])=={'pmid_9627209','pmid_22426846'}
    reverse=actions['relation:31364b5c7c0d250d37ddae99']['supplement']
    assert '不能证明反向' in reverse['conclusion']
    assert '不能证明' in actions['relation:5a944495f091b0debadf876b']['supplement']['conclusion']


def test_generated_candidate_matches_current_sealed_inputs(candidate):
    saved=read(ROOT/'mock_data/kg_v3_candidate/candidate.json')
    assert digest(saved)==digest(candidate)
    assert validate_candidate(saved,ROOT)['activation_ready'] is False


def test_active_v2_files_remain_identical_to_pre_remediation_receipt():
    import hashlib
    receipt=read(ROOT/'knowledge_sources/v3/receipts/2026-10-20-remainder-03.json')
    for name,expected in receipt['active_kg_v2_files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected


@pytest.mark.parametrize('mutation',['eligibility','missing_action','expert','proposal'])
def test_candidate_tampering_rejected(candidate,mutation):
    changed=copy.deepcopy(candidate)
    if mutation=='eligibility':changed['relations'][0]['reasoning_eligible']=True
    elif mutation=='missing_action':changed['actions'].pop(next(iter(changed['actions'])))
    elif mutation=='expert':changed['replacement_drafts'][0]['expert_review']='approved'
    else:changed['replacement_drafts'][0]['proposed_change']={}
    with pytest.raises(ValueError,match='Candidate differs'):validate_candidate(changed,ROOT)


def test_changed_or_outside_source_cannot_validate():
    sources=read(ROOT/'knowledge_sources/v3/remediation/sources.json')
    first=next(iter(sources))
    sources[first]['sha256']='0'*64
    with pytest.raises(ValueError,match='hash mismatch'):source_receipts(ROOT,sources)
    sources[first]['local_snapshot']='../outside.xml'
    with pytest.raises(ValueError,match='outside cache'):source_receipts(ROOT,sources)


@pytest.mark.parametrize('version',['kg_v3','kg_v3_candidate','unknown'])
def test_candidate_and_unknown_version_fail_before_database_read(version,monkeypatch):
    repo=GraphRepository(version)
    monkeypatch.setattr(repo,'_read',lambda *a,**k:pytest.fail('Candidate must not query database'))
    with pytest.raises(ValueError,match='尚未发布'):repo.entities()
    with pytest.raises(ValueError,match='尚未发布'):require_released_version(version)


def test_selector_refuses_candidate_before_reading_env_or_database():
    spec=importlib.util.spec_from_file_location('select_version_under_test',ROOT/'scripts/select_graph_version.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(ValueError,match='尚未发布'):module.select('kg_v3_candidate')
