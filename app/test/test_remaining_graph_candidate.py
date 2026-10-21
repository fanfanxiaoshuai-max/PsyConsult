"""Exact remaining denominator, real materialized changes and clinically meaningful boundaries."""
import copy
import sys
from collections import Counter
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read,digest
from core.graph.remediation import build_candidate,validate_candidate
from core.graph.remaining_candidate import validate_remaining_batch
from core.graph.structured_candidate import inspect_candidate


@pytest.fixture(scope='module')
def data():return build_candidate(ROOT)


@pytest.fixture(scope='module')
def args():
    b=ROOT/'knowledge_sources/v3'
    return dict(batch=read(b/'remediation/structured-batch-02.json'),
        first=read(b/'remediation/structured-batch-01.json'),
        inventory=read(b/'inventory.json'),reviews=read(b/'reviews.json'),
        evidence=read(b/'evidence.json'),catalog=read(b/'catalog.json'))


def facts(data,gid):return [f for f in data['structured']['qualified_assertions'] if f['policy_id']==gid]


def test_remaining_is_exact_349_with_no_overlap_or_default_disposition(data,args):
    batch=args['batch'];expected={u for u,r in args['reviews'].items() if r['status']=='amended'}
    assert set(batch['operations']).isdisjoint(args['first']['operations'])
    assert set(batch['operations'])|set(args['first']['operations'])==expected
    assert len(batch['operations'])==349
    assert Counter(op['edit']['kind'] for op in batch['operations'].values())=={
        'withdraw_original_assertion':33,'materialize_qualified_assertion':316}
    assert len(data['structured']['changes'])==399
    assert data['summary']['remaining_structured_items']==0
    assert len({op['policy_id'] for op in batch['operations'].values()})==147
    assert all(d['implementation_status']=='structured_applied_candidate' and d['structured_result']
               for d in data['replacement_drafts'])


def test_every_replacement_exists_as_a_fact_and_every_withdrawal_is_explicit(data,args):
    second=data['structured']['batches'][1]
    fact_index={f['id']:f for f in second['qualified_assertions']}
    assert len(fact_index)==268
    for uid,op in args['batch']['operations'].items():
        result=second['changes'][uid]
        if op['edit']['disposition']=='withdraw':
            assert result['after'] is None and result['replacement_value'] is None
            assert result['reason_code'] and result['followup_required']
        else:
            assert result['assertion_ids']
            for fid in result['assertion_ids']:
                assert uid in fact_index[fid]['audit_item_ids']
    assert set(u for f in fact_index.values() for u in f['audit_item_ids'])=={
        u for u,op in args['batch']['operations'].items() if op['edit']['disposition']=='qualify'}


def test_original_evidence_is_bound_to_each_deduplicated_fact(data,args):
    for fact in data['structured']['qualified_assertions']:
        assert fact['provenance'] and fact['context']
        for p in fact['provenance']:
            proof=args['evidence'][p['evidence_id']]
            assert set(fact['audit_item_ids']).issubset(proof['item_ids'])
            assert p['sha256']==args['catalog'][p['source_id']]['sha256']
            assert p['locator']==proof['locator']
        assert fact['reasoning_eligible'] is False and fact['expert_review']=='pending'
        assert fact['diagnostic_sufficiency'] is False and fact['category_inheritance'] is False


def test_no_legacy_causes_first_line_or_exclusion_rules_in_materialized_graph(data):
    graph=data['structured']['graph'];ids={n['id'] for n in graph['nodes']}
    assert len(ids)==len(graph['nodes'])==406
    assert len(graph['edges'])==304
    assert all(e[k] in ids for e in graph['edges'] for k in ('source','target'))
    assert {e['type'] for e in graph['edges']}=={'HAS_EXAMPLE','HAS_COURSE_SPECIFIER','HAS_SCOPED_RULE','HAS_QUALIFIED_ASSERTION'}
    assert all(e['reasoning_eligible'] is False for e in graph['edges'])
    assert all(n['reasoning_eligible'] is False for n in graph['nodes'])
    for node in data['entities']:
        if node.get('withdrawn'):assert node['id'] not in ids


def test_retired_targets_and_count_nodes_do_not_match_current_preview(data):
    for q in ['40-80mg/d','150-300mg/d','核心症状≥2条','中重度抑郁']:
        result=inspect_candidate(data,q)
        assert result['matched_entities']==[]
    for gid in ['WHO-DEPRESSION-THRESHOLD-AND-SEVERITY','NICE-DEPRESSION-FIRSTLINE-SCOPE']:
        for fact in facts(data,gid):
            subject=next(e for e in data['entities'] if e['id']==fact['subject_id'])
            assert not subject.get('withdrawn')
            assert subject['name'] in {'抑郁发作','抑郁障碍'}


def test_depression_threshold_and_causal_exclusions_are_qualified(data):
    for fact in facts(data,'WHO-DEPRESSION-THRESHOLD-AND-SEVERITY'):
        ctx=fact['context']
        assert (ctx['symptoms_total_min'],ctx['affective_cluster_min'],ctx['duration_weeks_min'])==(5,1,2)
        assert ctx['requires_complete_function_and_exclusion_assessment'] is True
        assert ctx['legacy_core_additional_count_table'] is False
    for gid in ['B03-DEP-CAUSAL-EXCLUSIONS','B03-SCHIZ-CAUSAL-EXCLUSION']:
        assert all(f['context']['causal_attribution_required'] and
                   f['context']['comorbidity_or_use_history_alone_excludes'] is False for f in facts(data,gid))
    assert all(f['context']['fixed_two_month_minimum'] is None for f in facts(data,'B03-RECURRENT-INTERVAL'))


def test_directional_washout_is_not_a_universal_fourteen_days(data):
    for gid,expected in [('B03-VEN-MAOI',('venlafaxine',7,'day')),
                         ('B03-FLU-MAOI',('fluoxetine',5,'week'))]:
        f=facts(data,gid)[0];directions=f['context']['directions']
        reverse=next(d for d in directions if d['from_drug']==expected[0])
        assert (reverse['minimum'],reverse['unit'])==expected[1:]
        incoming=next(d for d in directions if d['to_drug']==expected[0])
        assert (incoming['minimum'],incoming['unit'])==(14,'day')


def test_lai_route_correction_is_explicit_and_product_bound(data):
    f=facts(data,'B03-OLA-LAI')[0]
    assert f['context']['route']=='deep_intramuscular_gluteal'
    assert f['context']['post_injection_observation_hours_min']==3
    assert f['context']['equivalent_to_short_acting_injection'] is False
    assert f['provenance'][0]['source_id']=='us_olanzapine_lai'
    assert f['provenance'][0]['locator']['pages']==[1]
    assert f['context']['scope_correction']


def test_drug_identity_and_risk_labels_do_not_inherit_licensing_or_causality(data):
    val=facts(data,'B03-VAL-ID')
    assert any(f['context'].get('precise_generic_name')=='Sodium valproate' for f in val)
    for gid in ['B03-FV-ADVERSE','B03-ARI-ADVERSE','B03-LAM-ADVERSE','B03-CLO-CARDIAC']:
        assert all(f['predicate']=='HAS_REPORTED_ADVERSE_EVENT' and
                   f['context']['individual_causation_established'] is False for f in facts(data,gid))
    assert all(f['context']['research_only'] for f in facts(data,'B03-DBS-ROLE'))
    assert all(f['context']['research_only'] for f in facts(data,'B03-RTMS-ROLE'))
    renal=facts(data,'B03-LI-SEVERE-RENAL')[0]['context']
    assert renal['action']=='not_recommended' and renal['threshold']==dict(operator='lt',value=30,unit='mL/min')
    assert renal['implies_safe_use'] is False


def test_dose_profiles_distinguish_indications_and_studied_versus_recommended(data):
    ven=facts(data,'B03-VEN-DOSE')[0]['context']
    panic=next(p for p in ven['dose_profiles'] if p.get('indication')=='PD')
    assert panic['initial']==37.5 and panic['increment_interval_days_min']==7
    assert ven['SAD']['recommended']==75 and ven['SAD']['higher_dose_additional_benefit_established'] is False
    dul=facts(data,'B03-DUL-DOSE')[0]['context']
    assert next(p for p in dul['dose_profiles'] if p.get('indication')=='MDD')['initial_range']==[40,60]
    assert dul['studied_dose_is_universal_target'] is False
    ris=facts(data,'B03-RIS-DOSE')[0]['context']
    adult=next(p for p in ris['dose_profiles'] if p.get('indication')=='schizophrenia' and p['population']=='adult')
    assert adult['recommended_range']==[4,8] and adult['efficacy_studied_range']==[4,16]
    assert adult['above_6mg_twice_daily_generally_not_recommended'] is True
    assert ris['efficacy_studied_range_is_universal_recommended_max'] is False


def test_candidate_and_original_batch_receipt_are_consistent(data,args):
    saved=read(ROOT/'mock_data/kg_v3_candidate/candidate.json')
    assert digest(saved)==digest(data)
    assert validate_candidate(saved,ROOT)['clinical_amendments_approved']==0
    old=read(ROOT/'knowledge_sources/v3/remediation/structured-receipt-01.json')
    assert old['batch_sha256']==digest(args['first'])
    new=read(ROOT/'knowledge_sources/v3/remediation/structured-receipt-02.json')
    assert new['batch_sha256']==digest(args['batch']) and len(new['operations'])==349
    assert new['candidate_sha256']==digest(saved)


@pytest.mark.parametrize('corruption',['missing_item','old_batch_overlap','wrong_review','wrong_proof',
    'fake_approval','empty_context','unjustified_withdrawal_value','causal_exclusion','deterministic_adverse_event',
    'missing_washout_direction','lai_oral','nonfinite_value','negative_dose','reversed_dose_range'])
def test_bad_remaining_edits_fail_closed(args,corruption):
    modified=copy.deepcopy(args);batch=modified['batch'];ops=batch['operations'];uid=next(iter(ops))
    def pick(gid):return next(op for op in ops.values() if op['policy_id']==gid)
    if corruption=='missing_item':ops.pop(uid)
    elif corruption=='old_batch_overlap':
        op=next(iter(modified['first']['operations'].values()));ops[op['item_id']]=op
    elif corruption=='wrong_review':ops[uid]['review_sha256']='0'*64
    elif corruption=='wrong_proof':ops[uid]['evidence_ids']=['B03-DBS-ROLE']
    elif corruption=='fake_approval':batch['expert_review']='approved'
    elif corruption=='empty_context':ops[uid]['edit']['context']={}
    elif corruption=='unjustified_withdrawal_value':pick('B03-FLU-TARGET')['edit']['context']['replacement_value']=80
    elif corruption=='causal_exclusion':pick('B03-DEP-CAUSAL-EXCLUSIONS')['edit']['context']['causal_attribution_required']=False
    elif corruption=='deterministic_adverse_event':pick('B03-CLO-CARDIAC')['edit']['context']['individual_causation_established']=True
    elif corruption=='missing_washout_direction':pick('B03-VEN-MAOI')['edit']['context']['directions'].pop()
    elif corruption=='lai_oral':pick('B03-OLA-LAI')['edit']['context']['route']='oral'
    elif corruption=='nonfinite_value':ops[uid]['edit']['context']['fake_number']=float('nan')
    elif corruption=='negative_dose':pick('B03-VEN-DOSE')['edit']['context']['dose_profiles'][0]['initial']=-75
    else:pick('B03-DUL-DOSE')['edit']['context']['dose_profiles'][0]['initial_range']=[60,40]
    with pytest.raises(ValueError):validate_remaining_batch(**modified)
