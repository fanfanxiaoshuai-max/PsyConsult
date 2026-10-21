"""Explicit first structural amendments; no extraction of prescriptions from prose."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
from core.graph.audit import read, write, digest


def prepare(root=ROOT):
    base = root / 'knowledge_sources/v3'
    inventory, reviews = read(base/'inventory.json'), read(base/'reviews.json')
    operations = {}
    course_definitions={
        'd592d6d2f064492b3c8b07d1':dict(course='first_episode',previous_schizophrenia_or_schizoaffective_episodes=0,
            requires_complete_diagnostic_criteria=True,remission_status_assessed_separately=True),
        'fed09d8c290dbd563081baf1':dict(course='multiple_episodes',qualifying_episodes_min=2,
            qualifying_disorders=['schizophrenia','schizoaffective_disorder'],
            current_or_most_recent_episode='schizophrenia',between_episode_remission_months_min=3,
            remission_states=['partial','full'],requires_complete_diagnostic_criteria=True),
        '21d79055466331363ac01b98':dict(course='continuous',
            full_criteria_met_for_almost_entire_course=True,subthreshold_periods='very_brief_relative_to_overall_course',
            when_applied_to_first_episode=dict(duration_years_min=1,replaces='first_episode_specifier'),
            remission_status_assessed_separately=True),
    }

    def put(uid, edit):
        row = reviews[uid]
        assert row['status'] == 'amended' and uid not in operations
        operations[uid] = dict(item_id=uid, original_sha256=inventory[uid]['original_sha256'],
            review_sha256=digest(row), evidence_ids=row['evidence_ids'], edit=edit)

    # These clinical examples retain parent -> example direction, changing the predicate.
    for uid, row in reviews.items():
        if row['status'] != 'amended': continue
        proof = row['evidence_ids'][0]
        if proof == 'B03-SCHIZ-EXAMPLE-DIRECTION':
            put(uid, dict(kind='replace_relation_type', expected_type='SUBTYPE_OF',
                          type='HAS_EXAMPLE', diagnostic_sufficiency=False))
        elif proof == 'B03-SCHIZ-COURSE-SPECIFIERS':
            if inventory[uid]['kind'] == 'entity':
                put(uid, dict(kind='replace_entity_role', expected_label='ClinicalSubtype',
                              label='CourseSpecifier', disease_id='557312cc1a8ce5f7bb725e2d',
                              definition=course_definitions[inventory[uid]['original']['id']]))
            else:
                put(uid, dict(kind='replace_relation_type', expected_type='HAS_SUBTYPE',
                              type='HAS_COURSE_SPECIFIER', diagnostic_sufficiency=False))

    # Removal is an explicit finished data edit; it does not invent an alternative code.
    removed_codes = {
        'WHO-MANIC-CODE-SCOPE': 'disorder_code_assigned_to_episode',
        'WHO-HYPOMANIC-CODE-SCOPE': 'disorder_code_assigned_to_episode',
        'B03-MANIA-CODE': 'requires_current_episode_and_psychotic_status',
        'B03-THYROID-CODE': 'unspecified_category_assigned_to_umbrella',
        'B03-LIPID-CODE': 'requires_lipid_subtype',
        'B03-SEROTONIN-CODE': 'wrong_equivalence',
        'B03-HYPERTENSION-CODE': 'essential_hypertension_is_not_control_status',
        'B03-HEPATIC-CODE': 'wrong_equivalence',
        'B03-RENAL-CODE': 'drug_threshold_is_not_ckd_stage',
        'B03-GI-BLEED-CODE': 'requires_bleeding_site_or_unspecified_status',
    }
    for uid, row in reviews.items():
        if row['status'] != 'amended' or inventory[uid]['kind'] != 'property':continue
        prop=inventory[uid]['original']; proof=row['evidence_ids'][0]
        if proof in removed_codes:
            put(uid, dict(kind='remove_code_assignment', key=prop['key'], code=prop['value'],
                          reason_code=removed_codes[proof], replacement_code=None))
        elif proof == 'WHO-DYSTHYMIA-CODE':
            put(uid, dict(kind='replace_code_assignment', key=prop['key'], old_code='6A73',
                          code='6A72', system='ICD-11', edition='WHO CDDR 2024',
                          concept='Dysthymic disorder'))
        elif proof in {'B03-ICD10-DEP', 'B03-ANXIETY-CODES'}:
            mappings = ([dict(code='F32', concept='Depressive episode'),
                         dict(code='F33', concept='Recurrent depressive disorder')]
                        if proof=='B03-ICD10-DEP' else
                        [dict(code='F40', concept='Phobic anxiety disorders'),
                         dict(code='F41', concept='Other anxiety disorders')])
            put(uid, dict(kind='replace_with_related_categories', key=prop['key'],
                          system='ICD-10', edition='WHO ICD-10 2019', mappings=mappings,
                          equivalent_to_umbrella=False, exhaustive=False))

    def quantity(value, unit, role):
        return dict(value=value, unit=unit, role=role)

    def rule(key, subject, kind, source_id, evidence_id, context, parameters, constraints):
        return dict(key=key, subject_id=subject, kind=kind, source_id=source_id,
                    evidence_id=evidence_id, context=context, parameters=parameters,
                    constraints=constraints)

    ser='04f8787e935c61048f6af186'; flu='fcc7bf9f26197edd8426900f'
    ola='fbe4ed72827477d0ae8cfb0f'; li='72d56d56d60120f29a185b86'
    cloz=next(i['original']['id'] for i in inventory.values()
              if i['kind']=='entity' and i['original']['name']=='氯氮平')
    fv=next(i['original']['id'] for i in inventory.values()
            if i['kind']=='entity' and i['original']['name']=='氟伏沙明')
    maoi=next(i['original']['id'] for i in inventory.values()
              if i['kind']=='entity' and i['original']['name']=='单胺氧化酶抑制剂')
    shared=['仅原文所列制剂及版本', '需临床人员结合完整标签及个体情况复核', '不生成个人处方']
    templates={}
    templates['B02-SER-START']=[rule('sertraline-adult-initial-cn',ser,'dose','cn_sertraline_viatris',
        'B02-SER-START',dict(population='adult', indications=['depression','OCD'],phase='initial'),
        [quantity(50,'mg/day','initial_dose'),quantity(7,'day','minimum_titration_interval')],shared)]
    templates['B02-FLU-MAX']=[]
    for indication,condition in [('depression','20mg/day疗效不足；最初3–4周评估调整'),
                                 ('OCD','20mg/day治疗2周后仍无明显疗效')]:
        templates['B02-FLU-MAX'].append(rule('fluoxetine-'+indication+'-cn',flu,'dose',
            'cn_fluoxetine_lilly','B02-FLU-MAX',dict(population='adult',indication=indication,
            phase='dose_adjustment', prerequisite=condition),
            [quantity(20,'mg/day','recommended_dose'),quantity(60,'mg/day','maximum_after_titration')],shared))
    templates['B02-FLU-MAX'].extend([
        rule('fluoxetine-bulimia-cn',flu,'dose','cn_fluoxetine_lilly','B02-FLU-MAX',
             dict(population='adult',indication='bulimia',co_treatment='psychotherapy'),
             [quantity(60,'mg/day','recommended_dose')],shared),
        rule('fluoxetine-elderly-cn',flu,'dose','cn_fluoxetine_lilly','B02-FLU-MAX',
             dict(population='elderly',phase='dose_adjustment'),
             [quantity(40,'mg/day','usual_upper_dose'),quantity(60,'mg/day','maximum_recommended_dose')],
             shared+['谨慎增加剂量；不能把最高量等同于通常推荐量'])])
    templates['B02-OLA-START']=[]
    for indication,regimen,dose in [('schizophrenia','monotherapy',10),('mania','monotherapy',15),
                                    ('mania','combination',10),('bipolar_recurrence_prevention','label_qualified',10)]:
        templates['B02-OLA-START'].append(rule('olanzapine-'+indication+'-'+regimen+'-cn',ola,'dose',
            'cn_olanzapine_hansoh','B02-OLA-START',dict(population='adult',indication=indication,
            regimen=regimen,phase='initial'),[quantity(dose,'mg/day','initial_dose')],shared+
            (['预防复发应保留既往躁狂治疗有效等标签条件'] if 'prevention' in indication else [])))
    templates['B03-LI-RANGE']=[]
    for phase,low,high in [('acute_manic_or_mixed',0.8,1.2),('maintenance',0.8,1.0)]:
        templates['B03-LI-RANGE'].append(rule('lithium-'+phase+'-us',li,'concentration_target',
            'us_lithium_dailymed','B03-LI-RANGE',dict(population='adult_over_30kg',
            indication='bipolar_I',phase=phase, sampling_hours_after_dose=12),
            [dict(lower=low,upper=high,unit='mEq/L',role='serum_target')],
            shared+['血浓度不能单独判断疗效或毒性', '不与英国指南单位及阶段范围自动合并']))
    nice=[]
    for key,low,high,context in [('first_time',0.6,0.8,dict(population='adult',scenario='first_lithium_treatment')),
                              ('trial_higher',0.8,1.0,dict(population='adult',scenario='relapse_while_taking_lithium_or_impairing_subthreshold_symptoms',trial_duration_months_min=6))]:
        nice.append(rule('lithium-'+key+'-uk',li,'concentration_target','nice_cg185',
            'B03-LI-NICE-CONCENTRATION',context,
            [dict(lower=low,upper=high,unit='mmol/L',role='plasma_target')],
            ['仅NICE CG185相应条件', '不转换或并入美国产品目标范围', '不生成个人处方']))
    templates['B02-SER-MAOI']=[rule('sertraline-maoi-washout-cn',ser,'washout',
        'cn_sertraline_viatris','B02-SER-MAOI',dict(population='label_defined',
        prohibited_combination=True),[dict(from_entity=maoi,to_entity=ser,minimum=14,unit='day'),
                                    dict(from_entity=ser,to_entity=maoi,minimum=14,unit='day')],
        shared+['仅MAOI与舍曲林间换药；不扩展到其他药物'])]
    templates['B02-CLO-FLUVOX']=[rule('fluvoxamine-clozapine-management-us',cloz,
        'interaction_management','us_clozapine_mylan','B02-CLO-FLUVOX',
        dict(population='label_defined',inhibitor_id=fv,affected_id=cloz,
             mechanism='strong_CYP1A2_inhibition',exposure_direction='may_increase'),
        [dict(value=1,denominator=3,unit='fraction_of_original_dose',role='label_dose_adjustment')],
        shared+['仅美国标签中的强CYP1A2抑制剂合用条件', '非无条件绝对禁忌', '不得自行按比例调药'])]
    for uid,row in reviews.items():
        if row['status']!='amended':continue
        proof=row['evidence_ids'][0]
        if proof not in templates:continue
        if uid=='property:'+li+':dose_start':
            put(uid,dict(kind='retire_unqualified_dose',key='dose_start',replacement_value=None,
                         followup='需要另行确认具体制剂起始量；浓度范围不能替代剂量'))
            continue
        records=list(templates[proof])
        if proof=='B03-LI-RANGE': records=records+nice
        put(uid,dict(kind='replace_with_scoped_records',records=records))
    result=dict(id='structured-01',version='kg_v3_candidate',expert_review='pending',
                reasoning_eligible=False,operations=operations)
    write(base/'remediation/structured-batch-01.json',result)
    return result


if __name__=='__main__':
    from collections import Counter
    batch=prepare()
    print(len(batch['operations']),dict(Counter(x['edit']['kind'] for x in batch['operations'].values())))
