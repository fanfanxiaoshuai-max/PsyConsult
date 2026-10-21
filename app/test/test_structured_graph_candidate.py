"""Semantics of the first materialized candidate batch, independently of draft prose."""
import copy
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read, digest
from core.graph.remediation import build_candidate
from core.graph.structured_candidate import validate_structured_batch, inspect_candidate


@pytest.fixture(scope='module')
def data():return build_candidate(ROOT)


@pytest.fixture(scope='module')
def inputs():
    base=ROOT/'knowledge_sources/v3'
    return dict(batch=read(base/'remediation/structured-batch-01.json'),
        inventory=read(base/'inventory.json'),reviews=read(base/'reviews.json'),
        evidence=read(base/'evidence.json'),catalog=read(base/'catalog.json'))


def test_applied_batch_has_no_dangling_edges_or_duplicate_clinical_records(data):
    summary=data['summary']; structured=data['structured']
    assert summary['structured_items_applied']==399
    assert summary['remaining_structured_items']==0
    assert summary['structured_drafts']==0  # The previous 12 prose/dict drafts have actual edits now.
    assert len(structured['clinical_records'])==15
    graph=structured['graph'];ids=[n['id'] for n in graph['nodes']]
    assert len(ids)==len(set(ids))
    assert len(structured['batches'][0]['graph']['edges'])==36
    assert all(e[k] in ids for e in graph['edges'] for k in ('source','target'))
    assert all(n['reasoning_eligible'] is False for n in graph['nodes'])
    assert all(e['reasoning_eligible'] is False for e in graph['edges'])
    assert graph['activation_ready'] is False
    assert len([d for d in data['replacement_drafts'] if d['implementation_status']=='structured_applied_candidate'])==399
    assert digest(read(ROOT/'mock_data/kg_v3_candidate/structured-graph.json'))==digest(graph)


def test_symptom_hierarchy_has_examples_without_reversing_endpoints(data,inputs):
    modified=[e for e in data['relations'] if e.get('structured_item_id') and e['type']=='HAS_EXAMPLE']
    assert len(modified)==18
    for edge in modified:
        original=inputs['inventory']['relation:'+edge['id']]['original']
        assert (edge['source'],edge['target'])==(original['source'],original['target'])
        assert original['type']=='SUBTYPE_OF'
        assert edge['diagnostic_sufficiency'] is False
    result=inspect_candidate(data,'幻听')
    assert result['relations'] and all(r['type']=='HAS_EXAMPLE' for r in result['relations'])


def test_course_nodes_and_qualification_relationships_preserve_real_requirements(data):
    nodes={e['name']:e for e in data['entities'] if e['label']=='CourseSpecifier'}
    assert set(nodes)=={'首次发作','多次发作','持续型'}
    assert nodes['多次发作']['course_definition']['between_episode_remission_months_min']==3
    continuous=nodes['持续型']['course_definition']
    assert continuous['when_applied_to_first_episode']==dict(duration_years_min=1,replaces='first_episode_specifier')
    assert 'duration_years_min' not in continuous  # One year is conditional, not a universal course rule.
    links=[e for e in data['relations'] if e.get('structured_item_id') and e['type']=='HAS_COURSE_SPECIFIER']
    assert len(links)==3
    assert all(e['target'] in {n['id'] for n in nodes.values()} for e in links)


def test_corrected_code_is_searchable_and_retired_code_is_not_a_matching_alias(data):
    result=inspect_candidate(data,'6A72')
    assert [n['name'] for n in result['matched_entities']]==['恶劣心境']
    coding=result['matched_entities'][0]['codings'][0]
    assert (coding['system'],coding['edition'],coding['code'])==('ICD-11','WHO CDDR 2024','6A72')
    assert inspect_candidate(data,'6A73')['totals']['entities']==0
    assert 'legacy_id' not in result['nodes'][0] and 'properties' not in result['nodes'][0]


def test_retirement_does_not_guess_replacement_codes(data):
    nodes={n['id']:n for n in data['entities']}
    for uid in ['property:408bf2d0bb58d9adb050102d:icd10','property:845ae0c616b381a617eeb5d4:icd10']:
        result=data['structured']['changes'][uid]
        assert result['after'] is None and result['followup_required'] is True
        assert 'icd10' not in nodes[result['entity_id']]['properties']
        assert not nodes[result['entity_id']].get('codings')
    dep=nodes['06b62e6a29f4d2e83f762bd2']
    assert {m['code'] for m in dep['related_categories']}=={'F32','F33'}
    assert all(m['equivalent_to_umbrella'] is False for m in dep['related_categories'])
    assert not dep.get('codings')


def test_lithium_scopes_are_separate_and_starting_dose_is_not_concentration(data):
    result=inspect_candidate(data,'锂盐')
    records=result['clinical_records']
    assert len(records)==4
    targets={(r['scope']['region'],p['unit'],p['lower'],p['upper']) for r in records for p in r['parameters']}
    assert targets=={('US','mEq/L',.8,1.2),('US','mEq/L',.8,1.0),
                     ('UK','mmol/L',.6,.8),('UK','mmol/L',.8,1.0)}
    assert all(r['context']['sampling_hours_after_dose']==12 for r in records if r['scope']['region']=='US')
    retired=data['structured']['changes']['property:72d56d56d60120f29a185b86:dose_start']
    assert retired['after'] is None


def test_indication_and_regimen_change_initial_dose_instead_of_global_value(data):
    records=inspect_candidate(data,'奥氮平')['clinical_records']
    doses={(r['context']['indication'],r['context']['regimen']):r['parameters'][0]['value'] for r in records}
    assert doses[('mania','monotherapy')]==15
    assert doses[('mania','combination')]==10
    assert all(r['scope']['region']=='CN' for r in records)
    flu=inspect_candidate(data,'氟西汀')['clinical_records']
    assert len(flu)==4
    assert all(p.get('value')!=80 for r in flu for p in r['parameters'])
    assert any(r['context'].get('co_treatment')=='psychotherapy' for r in flu)


def test_washout_direction_and_cyp_management_do_not_become_generic_contraindications(data):
    record=next(r for r in data['structured']['clinical_records'] if r['kind']=='washout')
    a,b=record['parameters']
    assert (a['from_entity'],a['to_entity'])==(b['to_entity'],b['from_entity'])
    assert a['minimum']==b['minimum']==14
    interaction=next(r for r in data['structured']['clinical_records'] if r['kind']=='interaction_management')
    assert interaction['context']['affected_id']==interaction['subject_id']
    assert interaction['context']['inhibitor_id']!=interaction['subject_id']
    assert interaction['scope']['region']=='US'
    assert interaction['parameters'][0]['denominator']==3
    assert not interaction.get('contraindicated')


@pytest.mark.parametrize('corruption',['wrong_review','wrong_code','unit_swap','missing_population','missing_sample_time',
    'unbound_proof','missing_washout_direction','negative_value','expert_approval','zero_denominator'])
def test_invalid_edits_fail_closed(inputs,corruption):
    modified=copy.deepcopy(inputs)
    batch=modified['batch'];ops=batch['operations']
    uid=next(iter(ops))
    records=[r for op in ops.values() for r in op['edit'].get('records',[])]
    if corruption=='wrong_review':ops[uid]['review_sha256']='0'*64
    elif corruption=='wrong_code':
        next(op for op in ops.values() if op['edit']['kind']=='replace_code_assignment')['edit']['code']='6A73'
    elif corruption=='unit_swap':
        next(r for r in records if r['source_id']=='us_lithium_dailymed')['parameters'][0]['unit']='mmol/L'
    elif corruption=='missing_population':records[0]['context'].pop('population')
    elif corruption=='missing_sample_time':
        next(r for r in records if r['source_id']=='us_lithium_dailymed')['context'].pop('sampling_hours_after_dose')
    elif corruption=='unbound_proof':records[0]['evidence_id']='B03-SCHIZ-EXAMPLE-DIRECTION'
    elif corruption=='missing_washout_direction':
        next(r for r in records if r['kind']=='washout')['parameters'][0].pop('to_entity')
    elif corruption=='negative_value':records[0]['parameters'][0]['value']=-50
    elif corruption=='expert_approval':batch['expert_review']='approved'
    else:next(r for r in records if r['kind']=='interaction_management')['parameters'][0]['denominator']=0
    with pytest.raises(ValueError):validate_structured_batch(**modified)
