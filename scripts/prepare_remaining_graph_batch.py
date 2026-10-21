"""Explicit semantic policies for the exact 349 remaining amendments.

Policies are hand specified against the sealed reviews. No default conversion,
numeric extraction from prose, or automatic clinical approval is permitted.
"""
import copy
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read,write,digest


def policies():
    out={}
    def P(tag,predicate,*,role=None,withdraw=False,**context):
        assert tag not in out
        out[tag]=dict(predicate=predicate,entity_role=role,disposition='withdraw' if withdraw else 'qualify',context=context)
    P('B03-DEP-UMBRELLA','DEFINES_DIAGNOSTIC_GROUP',role='DiagnosticGroup',
      preferred_english='Depressive disorders',equivalent_to_MDD=False,
      members=['single_episode_depressive_disorder','recurrent_depressive_disorder','dysthymic_disorder'],members_exhaustive=False)
    P('B03-PSYCHOTIC-DIFFERENTIAL','REQUIRES_TEMPORAL_DIFFERENTIAL',
      assess=['psychosis_within_mood_episode','psychosis_outside_mood_episode','schizoaffective_criteria'],name_match_exclusion=False)
    P('B03-SEVERITY-BINS','RETIRES_HISTORICAL_GROUPING',withdraw=True,
      reason='overlapping_historical_severity_bins',equivalent_to_NICE_groups=False,replacement_value=None)
    P('B03-PSYCHOTIC-SPECIFIER','HAS_PSYCHOTIC_SPECIFIER',role='EpisodeSpecifier',
      requires=['specific_mood_disorder','current_episode','severity'],implies_schizophrenia=False)
    P('B03-RESISTANCE-ID','REQUIRES_TREATMENT_RESPONSE_REVIEW',role='TreatmentResponseContext',
      prerequisites=['review_diagnosis','adherence','adequate_dose_and_duration','previous_response'],
      decisions=['switch','augmentation'],shared_decision=True,independent_disease_subtype=False)
    P('B03-CBT-OCD','CONSIDERS_COMBINED_CBT_ERP_AND_SSRI',population='adult',disorder='OCD',
      prerequisite='inadequate_response_to_adequate_SSRI_or_CBT_ERP',multidisciplinary_review=True,
      intervention='CBT_including_ERP',quarantined_endpoints_restored=False)
    P('B03-RELAXATION','HAS_PROTOCOL_DEFINED_PSYCHOLOGICAL_OPTION',role='ProtocolDefinedTreatment',
      population='adult',disorder='GAD',protocol='applied_relaxation',intensity='high',generic_relaxation_equivalent=False)
    P('B03-MINDFULNESS-ID','DEFINES_PROTOCOL_SPECIFIC_INTERVENTION',role='InterventionFamily',
      example='mindfulness_based_cognitive_therapy',goal='depression_relapse_prevention',all_mindfulness_equivalent=False)
    P('B03-OCD-INITIAL-SSRI','HAS_INITIAL_PHARMACOLOGICAL_OPTION',population='adult',disorder='OCD',
      prerequisite='pharmacotherapy_selected',alternative='CBT_including_ERP',
      selection_factors=['functional_impairment','preference'],automatic_first_line_for_all=False)
    P('B02-SER-MAX','HAS_SCOPED_DOSE_LIMIT',population='adult',indications=['depression','OCD'],
      maximum=dict(value=200,unit='mg/day'),prerequisite='50mg_response_inadequate_and_tolerated',titration_interval_days_min=7)
    P('B03-PAR-DOSE','HAS_INDICATION_SPECIFIC_DOSING',population='adult',
      depression=dict(initial=20,maximum=50,unit='mg/day'),
      separate_paths=['OCD','panic','social_anxiety','elderly','hepatic_or_renal_impairment'],universal_dose=False)
    P('B02-FLU-START','HAS_SCOPED_RECOMMENDED_DOSE',population=['adult','elderly'],
      indications=['depression','OCD'],recommended=dict(value=20,unit='mg/day'),
      separate_paths=['bulimia','elderly_titration','hepatic_impairment'],universal_initial_dose=False)
    P('B03-VEN-DOSE','HAS_INDICATION_SPECIFIC_DOSING',population='adult',formulation='extended_release_capsule',
      distinguish=['MDD','GAD','SAD','PD','hepatic_adjustment','renal_adjustment'],
      SAD=dict(recommended=75,unit='mg/day',higher_dose_additional_benefit_established=False),
      dose_profiles=[
        dict(indications=['MDD','GAD'],population='adult',initial=75,unit='mg/day',
             optional_adaptation_initial=37.5,adaptation_days=[4,7],maximum=225,
             increment_max=75,increment_interval_days_min=4,response_and_tolerability_required=True),
        dict(indication='PD',population='adult',initial=37.5,initial_duration_days=7,unit='mg/day',
             maximum_approximate=225,increment_max=75,increment_interval_days_min=7)],
      hepatic_reduction_percent=dict(mild_or_moderate=50,severe_or_cirrhosis_min=50),
      renal_reduction_percent=dict(mild_or_moderate=[25,50],severe_or_haemodialysis_min=50),
      individual_clearance_variability_review=True,universal_75_initial_225_max=False)
    P('B03-DUL-DOSE','HAS_INDICATION_SPECIFIC_DOSING',formulation='delayed_release_capsule',
      distinguish=['MDD','GAD','diabetic_peripheral_neuropathic_pain','age'],
      additional_benefit_above_60mg_not_established_in_relevant_label_contexts=True,
      dose_profiles=[
        dict(indication='MDD',population='adult',initial_range=[40,60],unit='mg/day',
             optional_adaptation_initial=30,adaptation_days=7,effective_studied_dose=120,
             additional_benefit_above_60_established=False),
        dict(indication='GAD',population='adult_under_65',initial=60,unit='mg/day',
             optional_adaptation_initial=30,adaptation_days=7,increment=30,studied_dose=120,
             additional_benefit_above_60_established=False),
        dict(indication='GAD',population='geriatric',initial=30,unit='mg/day',initial_duration_weeks=2,
             target=60,increment=30,maximum_studied=120),
        dict(indication='GAD',population='age_7_to_17',initial=30,unit='mg/day',initial_duration_weeks=2,
             recommended_range=[30,60],increment=30,maximum_studied=120),
        dict(indication='diabetic_peripheral_neuropathic_pain',population='adult',recommended=60,unit='mg/day',
             lower_start_if_tolerability_concern=True,additional_benefit_above_60_established=False)],
      avoid_in=['chronic_liver_disease','cirrhosis','GFR_below_30_mL_per_min'],
      universal_30_60_initial_120_max=False,studied_dose_is_universal_target=False)
    P('B02-OLA-MAX','HAS_SCOPED_DOSE_LIMIT',population='adult',
      indications=['schizophrenia','mania','bipolar_recurrence_prevention'],
      adjustment_range=dict(lower=5,upper=20,unit='mg/day'),clinical_reassessment_required=True,all_formulations_equivalent=False)
    P('B03-RIS-DOSE','HAS_INDICATION_SPECIFIC_DOSING',
      distinguish=['adult_schizophrenia','bipolar_mania','adolescent','hepatic_or_renal_impairment','once_or_twice_daily'],
      six_mg_is_universal_maximum=False,above_6mg_twice_daily_regimen_concerns=['efficacy_limit','EPS'],
      dose_profiles=[
        dict(indication='schizophrenia',population='adult',initial=2,unit='mg/day',recommended_range=[4,8],
             efficacy_studied_range=[4,16],increment_range=[1,2],increment_interval_hours_min=24,
             above_6mg_twice_daily_generally_not_recommended=True,safety_above_16mg_studied=False),
        dict(indication='schizophrenia',population='adolescent',initial=0.5,unit='mg/day',target=3,
             increment_range=[0.5,1],increment_interval_hours_min=24,efficacy_studied_range=[1,6],
             additional_benefit_above_3_established=False,above_6mg_studied=False),
        dict(indication='bipolar_mania',population='adult',initial_range=[2,3],unit='mg/day',
             increment=1,increment_interval_hours_min=24,efficacy_studied_range=[1,6],above_6mg_studied=False),
        dict(indication='bipolar_mania',population='pediatric',initial=0.5,unit='mg/day',
             increment_range=[0.5,1],increment_interval_hours_min=24,target_range=[1,2.5],efficacy_studied_range=[1,6]),
        dict(population='adult_severe_renal_or_hepatic_impairment',initial_per_dose=0.5,unit='mg',doses_per_day=2,
             increases_above_1_5mg_twice_daily_interval_days_min=7)],
      efficacy_studied_range_is_universal_recommended_max=False)
    P('B03-LI-ID','HAS_PRODUCT_SPECIFIC_CLINICAL_ROLE',role='DrugFamily',
      active_component='lithium',evidence_formulation='ordinary_lithium_carbonate_tablet_or_capsule',
      disorder='bipolar_I',all_salts_or_formulations_inherit=False)
    P('B03-VAL-ID','HAS_PRECISE_DRUG_IDENTITY',role='DrugIdentity',
      precise_generic_name='Sodium valproate',broader_related_name='Valproate',
      pharmacological_category='antiepileptic',equivalent_to_divalproex_or_semisodium=False)
    P('B03-VAL-MOOD-CLASS','HAS_STAGE_SPECIFIC_CLINICAL_ROLE',
      clinical_role='mood_stabilisation_in_selected_bipolar_regimens',
      distinguish=['salt','formulation','region','licensed_vs_off_label'],
      all_category_members_inherit=False,reproductive_safety_review_required=True)
    P('B03-VAL-START','RETIRES_UNQUALIFIED_STARTING_DOSE',withdraw=True,
      reason='unqualified_500_750mg_not_supported_by_selected_product',
      reference_scope='UK_Epilim_200mg_epilepsy',replacement_value=None,Chinese_bipolar_dose_inferred=False)
    P('B03-VAL-RANGE','HAS_CONTEXT_DEPENDENT_CONCENTRATION',
      source_range=dict(lower=40,upper=100,unit='mg/L'),product='UK_Epilim_200mg_enteric_tablet',
      dependent_on=['sampling_time','co_medication','total_vs_free_concentration','indication'],unit_conversion_performed=False)
    P('B03-LAM-MOOD-CLASS','HAS_STAGE_SPECIFIC_CLINICAL_ROLE',disorder='bipolar_I',stage='maintenance',
      acute_mania_or_mixed_efficacy_established=False,all_mood_stabiliser_effects_inherit=False)
    P('B03-OLA-LAI','HAS_FORMULATION_SPECIFIC_REQUIREMENTS',role='DrugFormulation',
      product='ZYPREXA RELPREVV',route='deep_intramuscular_gluteal',formulation='extended_release_injectable_suspension',
      post_injection_observation_hours_min=3,certified_setting_and_emergency_services=True,
      equivalent_to_short_acting_injection=False,scope_correction='原审核条件误用了口服模板；以所绑定原文第1页长效肌注制剂为准')
    P('B03-CLOMI-SECOND','HAS_CONDITIONAL_SUBSEQUENT_OPTION',population='adult',disorder='OCD',
      any_prerequisite=['adequate_SSRI_ineffective','SSRI_not_tolerated','informed_preference','previous_good_response'],fixed_second_step=False)
    P('B03-OCD-GOAL','HAS_MULTIDIMENSIONAL_TREATMENT_GOAL',role='OutcomeGoal',disorder='OCD',
      dimensions=['obsession_and_compulsion_time','distress','function'],time_alone_defines_cure=False,individualised=True)
    P('B03-OCD-12W','HAS_TREATMENT_SPECIFIC_REVIEW_POINT',role='TreatmentReviewPoint',population='adult',disorder='OCD',
      review_weeks=12,regimens=['SSRI','combined_treatment_as_guideline_specifies'],
      CBT_ERP_hours_assessed_separately=True,early_safety_or_response_review_delayed=False,universal_minimum_duration=False)
    P('B03-OCD-MAINT','HAS_RESPONSE_CONDITIONAL_CONTINUATION',role='ContinuationTreatmentContext',
      disorder='OCD',prerequisite='effective_SSRI_treatment',continuation_months_min=12,
      remission_and_relapse_review_required=True,universal_one_to_two_year_threshold=False)
    for tag in ['B03-SER-TARGET-NODES','B03-FLU-TARGET','B03-FV-TARGET']:
        P(tag,'RETIRES_UNSUPPORTED_FIXED_TARGET',withdraw=True,
          reason='fixed_target_not_established_for_all_label_patients',replacement_value=None,
          raw_value_retained_only_in_audit=True,universal_target_created=False)
    P('B03-SER-MAX-NODES','HAS_PRODUCT_BOUND_DOSE_LIMIT',role='ProductBoundDoseLimit',
      drug='sertraline',population='adult',maximum=dict(value=200,unit='mg/day'),
      response_and_tolerability_review=True,titration_interval_days_min=7,shared_numeric_node_for_other_drugs=False)
    P('B03-ERP-FIRST','HAS_SEVERITY_AND_PREFERENCE_DEPENDENT_OPTION',population='adult',disorder='OCD',
      protocol='CBT_including_ERP',selection_factors=['functional_impairment','preference','treatment_intensity'],
      children_and_family_path_separate=True,unconditional_first_line=False)
    P('B03-DBS-ROLE','HAS_RESEARCH_ONLY_PROCEDURE',population='adult',disorder='chronic_severe_treatment_resistant_OCD',
      procedure='DBS',research_only=True,experienced_centre=True,multidisciplinary_assessment=True,routine_recommendation=False)
    P('B03-RTMS-ROLE','HAS_RESEARCH_ONLY_PROCEDURE',disorder='OCD',procedure='rTMS',research_only=True,
      efficacy_evidence='inadequate_in_selected_NICE_guidance',other_disorders_or_device_approvals_inherit=False)
    depression=dict(symptoms_total_min=5,affective_cluster_min=1,duration_weeks_min=2,
      concurrent=True,frequency='most_of_day_nearly_every_day',change_from_typical_functioning=True,
      requires_complete_function_and_exclusion_assessment=True,diagnostic_sufficiency=False)
    P('B03-DEP-EPISODE-ID','DEFINES_EPISODE_NOT_DISORDER',role='MoodEpisode',
      equivalent_to_single_episode_disorder_code_6A70=False,**depression)
    P('B03-DEP-SYMPTOM-DURATION','HAS_EPISODE_LEVEL_DURATION_CONDITION',symptom_alone_sufficient=False,**depression)
    P('B03-DEP-WEIGHT','HAS_QUALITATIVE_SIGNIFICANT_CHANGE_REQUIREMENT',
      dimension='appetite_or_weight',significance='clinical',fixed_five_percent_one_month_threshold=None,
      system='WHO_CDDR_2024',other_diagnostic_systems_evaluated=False)
    P('B03-DEP-SEVERITY-ID','DEFINES_SEVERITY_SPECIFIER',role='SeveritySpecifier',
      dimensions=['symptom_number','symptom_intensity','functional_impairment','psychotic_symptoms'],legacy_core_additional_count_table=False)
    P('WHO-DEPRESSION-THRESHOLD-AND-SEVERITY','REQUIRES_INTEGRATED_EPISODE_ASSESSMENT',
      subject_override='抑郁发作',
      severity_dimensions=['symptom_number','symptom_intensity','functional_impairment'],
      legacy_core_additional_count_table=False,**depression)
    P('B03-DEP-FUNCTION','HAS_FUNCTIONAL_ASSESSMENT_DIMENSION',role='FunctionalAssessmentDimension',
      domains=['personal','family','social','educational','occupational','other_important'],
      combine_with=['symptom_number','symptom_intensity'],function_alone_determines_severity=False)
    for tag in ['B03-DEP-PSYCHOTIC','WHO-PSYCHOSIS-SEVERITY']:
        P(tag,'HAS_SEVERITY_BOUND_PSYCHOTIC_SPECIFIER',
          psychosis_allowed_in=['moderate','severe'],psychosis_in_mild=False,severity_assessment_required=True)
    P('B03-DEP-OLD-CRITERIA','RETIRES_LEGACY_SYMPTOM_COUNT',withdraw=True,
      reason='legacy_core_additional_count_not_CDDR_2024_rule',replacement_value=None,automatic_diagnosis=False)
    for tag,disorder in [('B03-DEP-CAUSAL-EXCLUSIONS','depressive_episode'),('B03-SCHIZ-CAUSAL-EXCLUSION','schizophrenia')]:
        P(tag,'HAS_CAUSAL_ATTRIBUTION_EXCLUSION',role='CausalExclusionContext',disorder=disorder,
          causes_to_assess=['substance','medication','other_medical_condition'],
          causal_attribution_required=True,comorbidity_or_use_history_alone_excludes=False)
    P('B03-DEP-BIPOLAR-DIFF','HAS_DISORDER_CLASSIFICATION_DIFFERENTIAL',
      classify=['single_episode_depressive_disorder','recurrent_depressive_disorder'],
      assess_history=['mania','hypomania','mixed_episode'],bipolar_depressive_episode_excluded=False)
    P('B03-DEP-PSYCHOSIS-DIFF','REQUIRES_TEMPORAL_DIFFERENTIAL',
      assess=['mood_episode_timing','psychosis_outside_mood_episode','schizoaffective_criteria'],name_match_exclusion=False)
    P('B03-RECURRENT-INTERVAL','HAS_QUALITATIVE_INTEREPISODE_INTERVAL',role='InterepisodeInterval',
      interval='several_months',between_episodes='no_significant_mood_disturbance',fixed_two_month_minimum=None,
      dysthymia_superimposed_episode_exception=True)
    P('B03-DYSTHYMIA-COURSE','HAS_AGE_AND_COURSE_BOUND_REQUIREMENT',role='CourseRequirement',
      usual_adult_duration_years_min=2,initial_two_years='no_full_depressive_episode',
      prolonged_symptom_free_intervals=False,children_may_have_shorter_initial_course=True,
      later_superimposed_depressive_episodes_possible=True,always_mild_or_never_episode=False)
    P('B03-CATATONIA-ROLE','HAS_PSYCHOMOTOR_DOMAIN',role='PsychomotorPresentation',
      separate_from_gross_disorganisation=True,full_syndrome_requires_separate_assessment=True,
      associated_diagnosis_when_full_syndrome='6A40',single_sign_equals_syndrome=False)
    P('B03-BIPOLAR-MANIA-DIFF','REQUIRES_TEMPORAL_DIFFERENTIAL',
      assess=['psychosis_outside_manic_or_mixed_episode','schizoaffective_criteria'],mood_dominance_alone_sufficient=False)
    P('B03-MEDICATION-PSYCHOSIS','REQUIRES_MEDICATION_CAUSAL_ASSESSMENT',role='MedicationInducedDifferentialContext',
      assess=['known_drug_effect','temporal_relation','other_causes'],withdrawal_response_alone_sufficient=False)
    P('B03-MANIA-CODE','DEFINES_EPISODE_NOT_FIXED_CODE',role='MoodEpisode',
      current_phase='mania',bipolar_course_required=True,psychotic_status_assessed=True,unconditional_F31_1=False)
    P('B03-OTHER-SSRI-ID','DEFINES_RELATIVE_DRUG_SET',role='RelativeDrugClass',
      base_class='SSRI',exclude_current_drug=True,is_single_drug=False,implies_contraindication=False)
    P('B03-CYP2D6-ROLE','HAS_ENZYME_INHIBITION_MECHANISM',role='PharmacologicalMechanism',
      enzyme='CYP2D6',action='inhibition',substrates_assessed_separately=True,mechanism_is_drug_substrate=False)
    P('B03-HYPERTENSION-ID','DEFINES_CONTROL_STATUS',role='ClinicalControlStatus',
      disease='hypertension',control='uncontrolled',etiology_and_code_separate=True)
    P('B03-PK-EFFECT-NODES','RETIRES_UNBOUND_PHARMACOKINETIC_EFFECT',withdraw=True,
      reason='affected_drug_and_trigger_not_bound',replacement_value=None,self_causation=False)
    P('B03-ANTICOAG-EFFECT','HAS_UNCERTAIN_CLINICAL_SIGNIFICANCE_OBSERVATION',role='ClinicalObservation',
      observation='small_prothrombin_time_change',clinical_significance='uncertain',
      action='monitor_when_starting_or_stopping_sertraline',deterministic_potentiation=False)
    P('B03-LIVER-MONITOR','HAS_RISK_BASED_MONITORING_PLAN',role='MonitoringPlan',
      phase=['baseline','early_treatment'],early_months=6,
      dimensions=['liver_function','clinical_symptoms','hepatic_synthesis_or_coagulation'],normal_enzymes_exclude_injury=False)
    P('B03-WASHOUT14-NODE','HAS_DIRECTIONAL_WASHOUT_REQUIREMENT',role='DrugBoundWashoutContext',
      directions=[dict(from_drug='MAOI',to_drug='sertraline',minimum=14,unit='day'),
                  dict(from_drug='sertraline',to_drug='MAOI',minimum=14,unit='day')],universal_washout=False)
    P('B03-WASHOUT5W-NODE','HAS_DIRECTIONAL_WASHOUT_REQUIREMENT',role='DrugBoundWashoutContext',
      directions=[dict(from_drug='fluoxetine',to_drug='MAOI',minimum=5,unit='week'),
                  dict(from_drug='MAOI',to_drug='fluoxetine',minimum=14,unit='day')],other_switches_assessed_separately=True)
    P('B03-LOW-ELECTROLYTE-ROLE','HAS_AVOID_USE_QT_RISK_CONTEXT',role='QTRiskCondition',
      risks=['hypokalaemia','hypomagnesaemia'],action=['avoid_use_in_label_context','correct_risk','monitor'],
      formal_contraindication_in_all_regions=False)
    P('B03-ARI-MECHANISM','HAS_POSSIBLE_RECEPTOR_MECHANISM',role='PharmacologicalMechanism',
      partial_agonism=['D2','5_HT1A'],antagonism=['5_HT2A'],clinical_mechanism_fully_established=False)
    P('B03-TRS-ID','REQUIRES_ADEQUATE_SEQUENTIAL_TREATMENT_REVIEW',role='TreatmentResponseContext',
      different_antipsychotics_min=2,adequate_dose_and_duration=True,
      includes_non_clozapine_second_generation=True,review=['diagnosis','adherence','other_causes'],any_two_exposures_sufficient=False)
    P('B03-DEP-SWITCH','HAS_SHARED_DECISION_SUBSEQUENT_STRATEGY',prerequisites=['review_nonresponse','previous_treatment','preference'],
      specialist_participation=True,review_licensing_and_adverse_burden=True,automatic_on_resistant_label=False)
    P('B03-MANIA-MOOD-FIRST','HAS_PREVIOUS_TREATMENT_DEPENDENT_SEQUENCE',disorder='mania_or_hypomania',
      population='adult_not_already_on_antipsychotic_or_mood_stabiliser',
      initial_named_antipsychotic_option=True,lithium_or_valproate_based_on_response=True,all_mood_stabilisers_first_line=False)
    P('B03-LAI-MAINT','HAS_PREFERENCE_OR_ADHERENCE_DEPENDENT_OPTION',stage='maintenance',
      any_context=['patient_preference','avoid_covert_nonadherence'],shared_decision=True,specific_formulation=True,mandatory_for_all=False)
    P('B03-PANIC-SNRI','HAS_CONDITIONAL_SUBSEQUENT_OPTION',disorder='panic',
      prerequisites=['SSRI_unsuitable_or_ineffective','adequate_previous_trial','licensed_specific_drug','risk_and_preference_review'],all_SNRIs_fixed_second_line=False)
    P('B03-BIPOLAR-QUE','HAS_STAGE_SPECIFIC_TREATMENT_OPTION',population='adult',
      disorder='moderate_or_severe_bipolar_depression',drug='quetiapine',
      depends_on=['existing_lithium','previous_treatment','monotherapy_or_add_on'],all_depression_first_choice=False)
    P('NICE-DEPRESSION-FIRSTLINE-SCOPE','HAS_PREFERENCE_BOUND_INITIAL_OPTION',disorder='less_severe_depression',
      subject_override='抑郁障碍',historical_severity_bin_equated=False,
      antidepressant_routinely_first_line=False,informed_preference_exception=True,Chinese_source_comparison_complete=False)
    P('B03-ATYPICAL-BIPOLAR','HAS_PHASE_AND_DRUG_SPECIFIC_OPTION',
      phases=['mania','bipolar_depression','maintenance'],specific_drug_required=True,all_class_members_inherit=False)
    P('B03-PREGABALIN-GAD','HAS_INTOLERANCE_DEPENDENT_OPTION',disorder='GAD',
      prerequisite='SSRI_or_SNRI_not_tolerated',review=['dependence','pregnancy','other_risks'],automatic_second_step=False)
    P('B03-PANIC-SSRI','HAS_LICENSED_INITIAL_DRUG_OPTION',disorder='panic',
      licensed_specific_SSRI=True,review=['age','previous_response','risk','preference'],all_SSRIs_inherit=False)
    P('B03-DEP-CLASS-FIRST','HAS_SEVERITY_AND_PREFERENCE_DEPENDENT_OPTION',disorder='depression',
      subject_override='抑郁障碍',historical_severity_bin_equated=False,
      selection_factors=['severity','preference','previous_response'],include_psychological_and_combined_options=True,fixed_class_order=False)
    P('B03-PANIC-CLOMI','HAS_CONDITIONAL_OFF_LABEL_OPTION',disorder='panic',population='adult',
      any_prerequisite=['SSRI_unsuitable','no_improvement_after_12_weeks_SSRI'],pharmacotherapy_still_appropriate=True,
      off_label_in_guideline_context=True,TCA_overdose_risk_review=True)
    P('NICE-LITHIUM-MAINTENANCE','HAS_GUIDELINE_LONG_TERM_FIRST_LINE_OPTION',disorder='bipolar',stage='long_term',
      drug='lithium',all_lithium_salts_doses_inherit=False)
    P('B03-DEP-ANTIPSYCH-FIRST','RETIRES_UNIVERSAL_ANTIPSYCHOTIC_FIRST_LINE',withdraw=True,
      reason='no_general_depression_antipsychotic_monotherapy_first_line',replacement_value=None,
      requires_separate_psychotic_depression_or_specialist_augmentation_context=True)
    P('B03-GAD-DRUG-ORDER','HAS_RESPONSE_DEPENDENT_DRUG_SEQUENCE',disorder='GAD',
      prerequisite='pharmacotherapy_selected',initial='consider_SSRI',
      if_sertraline_ineffective='consider_other_SSRI_or_SNRI',licensing_risk_preference_review=True,all_classes_equal_first_line=False)
    P('B03-GAD-BENZO','HAS_SHORT_TERM_CRISIS_ONLY_OPTION',disorder='GAD',context='crisis',duration='short_term',routine_or_long_term=False)
    P('B03-ANTIDEP-CLASS-TREATS','HAS_CATEGORY_LEVEL_OPTION',disorder='depression',
      specific_drug_population_and_licence_required=True,all_class_members_inherit=False)
    P('B03-MANIA-ATYPICAL','HAS_NAMED_INITIAL_ANTIPSYCHOTIC_OPTION',population='adult_not_already_on_relevant_treatment',
      disorder='mania_or_hypomania',options=['haloperidol','olanzapine','quetiapine','risperidone'],all_atypicals_inherit=False)
    P('B03-ANXIETY-CHILDREN','HAS_DIAGNOSTIC_CATEGORY_MEMBER',
      parent='anxiety_or_fear_related_disorders',single_disease_mutually_exclusive_subtype=False)
    P('B03-SCHIZ-ANTIPSYCHOTIC','HAS_SHARED_DECISION_COMBINED_CARE_OPTION',disorder='schizophrenia',
      components=['oral_antipsychotic','psychological_intervention'],
      selection_factors=['preference','previous_response','adverse_risk'],all_second_generation_preferred_over_first=False)
    P('B03-ECT-DEP','HAS_SEVERITY_AND_URGENCY_DEPENDENT_OPTION',disorder='severe_depression',
      any_context=['informed_preference','rapid_response_needed','other_treatments_unsuccessful'],
      informed_consent_and_risk_assessment=True,fixed_second_line=False)
    P('B03-ERP-SUPERIORITY','RETIRES_UNQUALIFIED_COMPARATIVE_SUPERIORITY',withdraw=True,
      reason='comparison_requires_matched_population_intervention_intensity_and_outcome',replacement_value=None,universal_superiority_or_equivalence=False)
    P('B03-VEN-GAD-EVIDENCE','HAS_LABEL_DEFINED_INDICATION',population='adult',indication='GAD',
      formulation='extended_release_capsule',evidence_grade=None,grading_framework_not_supplied=True)
    P('B03-DEP-ANTIPSYCH-SECOND','HAS_SPECIALIST_COMBINATION_OPTION',disorder='depression',
      with_antidepressant=True,any_context=['previous_nonresponse','psychotic_symptoms'],specialist_review=True,universal_second_line=False)
    P('B03-BIPOLAR-BASE','HAS_PHASE_AND_DRUG_SPECIFIC_OPTION',stage='bipolar_depression',
      assess=['specific_drug','previous_regimen','existing_lithium','serum_lithium_if_relevant'],all_mood_stabilisers_universal_base=False)
    P('B03-LAM-PROPHYLAXIS','HAS_LABEL_DEFINED_MAINTENANCE_ROLE',subject_override='拉莫三嗪',
      population='adult',disorder='bipolar_I',stage='maintenance',outcome='delay_recurrence',current_acute_episode_efficacy_inferred=False)
    P('B03-SCHIZ-DEP-DIFF','REQUIRES_TEMPORAL_DIFFERENTIAL',
      assess=['psychosis_outside_mood_episode','psychotic_depression','schizoaffective_context'],name_match_exclusion=False)
    for tag in ['B03-CLO-CARDIAC','B03-FV-ADVERSE','B03-ARI-ADVERSE','B03-LAM-ADVERSE',
                'B03-QUE-ADVERSE','B03-CLO-SEIZURE','B03-CLO-WEIGHT-ADVERSE','B03-CLO-AGRANULOCYTOSIS']:
        P(tag,'HAS_REPORTED_ADVERSE_EVENT',event_certainty='reported_or_possible',
          individual_causation_established=False,frequency_comparison_across_trials=False,
          risk_contexts=({'B03-CLO-CARDIAC':['cardiac_assessment','rechallenge_restrictions'],
            'B03-LAM-ADVERSE':['titration','co_medications','serious_rash_separate_from_benign_rash'],
            'B03-QUE-ADVERSE':['initiation','titration','falls'],
            'B03-CLO-SEIZURE':['dose','titration','previous_seizure_risk'],
            'B03-CLO-AGRANULOCYTOSIS':['ANC_monitoring','severe_neutropenia_not_same_as_all_leukopenia']}.get(tag,['label_population','clinical_monitoring'])))
    P('B02-CLO-SER','HAS_DIRECTIONAL_EXPOSURE_RISK',influencing_drug='sertraline',affected_drug='clozapine',
      exposure_direction='may_increase',fixed_multiplier=None,monitoring_required=True)
    P('B03-VAL-PCOS','HAS_REPORTED_REPRODUCTIVE_ADVERSE_EVENT',
      distinguish=['polycystic_ovary_morphology','PCOS_diagnosis'],weight_related_risk_context=True,
      individual_causation_established=False,uniform_incidence=None)
    P('B03-VEN-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',population='adult',
      allowed_indications=['MDD','GAD','SAD'],formulation='extended_release_capsule',other_region_or_formulation_inherits=False)
    P('B03-LI-OLA','HAS_SEPARATE_SOURCE_INTERACTION_OBSERVATIONS',
      CN_olanzapine='no_interaction_shown_in_specified_study',US_lithium='antipsychotic_class_neurotoxicity_warning',
      class_warning_is_pair_specific_trial=False,global_no_interaction=False)
    P('B03-SER-QUE-DEPRESSION','RETIRES_CLASS_TO_PAIR_EFFICACY_INFERENCE',withdraw=True,
      reason='class_augmentation_guidance_not_direct_universal_sertraline_quetiapine_pair_evidence',replacement_value=None,
      specialist_combination_may_be_considered_separately=True)
    P('B03-VAL-BIPOLAR','HAS_SALT_AND_PHASE_SPECIFIC_GUIDELINE_OPTION',phases=['mania','maintenance'],
      depends_on=['previous_response','reproductive_safety','salt','licensing'],UK_semisodium_not_all_sodium_products=True)
    for tag in ['B03-LI-SELF-CONCENTRATION','B03-RIS-SELF-CONCENTRATION','B03-OLA-SELF-CONCENTRATION']:
        P(tag,'RETIRES_SELF_CAUSAL_EXPOSURE_EDGE',withdraw=True,
          reason='missing_specific_trigger_and_affected_drug_context',replacement_value=None,self_causal_alert=False)
    P('B03-LI-HYPONATREMIA','HAS_LABEL_WARNING_RISK_CONTEXT',risk='hyponatraemia_related_lithium_toxicity',
      medical_management_required=True,all_hyponatraemia_formal_contraindication=False)
    P('B03-PAR-INDICATIONS','HAS_PRODUCT_SPECIFIC_USE_CONTEXT',
      directly_described_uses=['depression','OCD','panic','social_phobia'],
      GAD_appears_in_safety_studies=True,GAD_licensed_indication_established_by_this_source=False)
    P('B03-LAM-VAL-INTERACTION','HAS_DIRECTIONAL_EXPOSURE_AND_RASH_RISK',
      influencing_drug='valproate',affected_drug='lamotrigine',mechanism='reduced_metabolism',
      exposure_direction='may_increase',serious_rash_risk=True,titration_and_monitoring_required=True,fixed_individual_multiplier=None)
    P('B02-SER-LI','HAS_DISTINCT_PK_AND_PD_OBSERVATIONS',population='healthy_volunteers',
      lithium_PK='not_significantly_changed_in_study',tremor='increased',all_risks_absent=False)
    P('B02-PAR-TCA','HAS_SUBSTRATE_DEPENDENT_EXPOSURE_RISK',influencing_drug='paroxetine',
      mechanism='CYP2D6_inhibition',affected_class='some_tricyclic_antidepressants',
      specific_substrate_required=True,monitoring_and_adjustment_review=True,all_TCA_same_effect=False)
    P('B03-VEN-HYPERTENSION','HAS_PRETREATMENT_CONTROL_AND_MONITORING_REQUIREMENT',
      control_existing_hypertension_before_treatment=True,monitor_blood_pressure=True,formal_section_4_contraindication=False)
    P('B03-SER-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',population='label_defined',
      allowed_indications=['depression','OCD'],product='CN_Zoloft_ordinary_tablet',all_ages_and_doses_inherit=False)
    P('B03-DUL-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',formulation='delayed_release_capsule',
      allowed_indications=['GAD','diabetic_peripheral_neuropathic_pain','adult_MDD'],age_paths_separate=True,other_pain_indications_inferred=False)
    P('B03-LAM-ACUTE-DEPRESSION','HAS_GUIDELINE_OFF_LABEL_OPTION',population='adult',
      indication='selected_moderate_or_severe_bipolar_depression',
      guideline_region='UK',US_label_acute_efficacy_established=False,licensing_and_guideline_equated=False)
    P('B03-CLO-TRS','HAS_ADEQUATE_TREATMENT_DEPENDENT_OPTION',disorder='schizophrenia',
      sequential_different_antipsychotics_min=2,adequate_dose_and_duration=True,
      includes_non_clozapine_second_generation=True,diagnosis_and_adherence_review=True)
    P('B03-FLU-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',
      allowed_indications=['depression','OCD','bulimia'],bulimia_co_treatment='psychotherapy',all_indications_same_dose_or_duration=False)
    P('B03-ANTIPSYCH-REGIMEN','HAS_REGIMEN_REVIEW_REQUIREMENT',routine_polypharmacy='avoid',
      exceptions=['short_term_switching','selected_specialist_clozapine_augmentation'],
      pair_specific_PK_effect_established=False,global_no_indication_claim=False)
    P('B03-RIS-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',
      allowed_indications=['schizophrenia','bipolar_I_acute_manic_or_mixed_episode'],
      age_and_mono_or_adjunct_paths_separate=True,all_bipolar_phases_inherit=False)
    P('B03-QUE-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',formulation='ordinary_tablet',
      allowed_indications=['schizophrenia','bipolar_mania','bipolar_depression'],
      age_and_mono_or_adjunct_paths_separate=True,extended_release_equivalent=False)
    P('B03-LI-QUE-INTERACTION','HAS_SEPARATE_PK_AND_SAFETY_CONTEXTS',
      specific_study_lithium_steady_state_PK='unchanged',some_combination_indications_exist=True,
      separate_lithium_antipsychotic_class_warning=True,pair_risk_quantified_by_class_warning=False,all_risks_absent=False)
    P('B02-FLUVOX-MAOI','HAS_LABEL_CONTRAINDICATION_AND_DIRECTIONAL_WASHOUT',
      concomitant_psychiatric_MAOI='contraindicated',directions=[
      dict(from_drug='MAOI',to_drug='fluvoxamine',minimum=14,unit='day'),
      dict(from_drug='fluvoxamine',to_drug='MAOI',minimum=14,unit='day')],
      linezolid_and_IV_methylene_blue_separate=True)
    P('B02-FLUVOX-TIZ','HAS_LABEL_DEFINED_CONTRAINDICATION',
      combination=['fluvoxamine','tizanidine'],mechanism='CYP1A2_inhibition',risks=['increased_exposure','blood_pressure_effect'])
    P('B03-ARI-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',
      allowed_indications=['schizophrenia','bipolar_I_acute_manic_or_mixed_episode'],
      age_and_adjunct_paths_separate=True,acute_bipolar_depression_inferred=False)
    P('B03-VEN-MAOI','HAS_LABEL_CONTRAINDICATION_AND_DIRECTIONAL_WASHOUT',
      concomitant_psychiatric_MAOI='contraindicated',directions=[
      dict(from_drug='MAOI',to_drug='venlafaxine',minimum=14,unit='day'),
      dict(from_drug='venlafaxine',to_drug='MAOI',minimum=7,unit='day')],
      linezolid_and_IV_methylene_blue_separate=True)
    P('B03-LI-QUE-MANIA','HAS_LABEL_DEFINED_ADJUNCT_INDICATION',
      formulation='ordinary_quetiapine_tablet',indication='bipolar_I_acute_mania',adjunct_to='lithium',label_population_and_monitoring_required=True)
    P('B03-FLU-MAOI','HAS_LABEL_CONTRAINDICATION_AND_DIRECTIONAL_WASHOUT',
      concomitant_MAOI='contraindicated',directions=[
      dict(from_drug='MAOI',to_drug='fluoxetine',minimum=14,unit='day'),
      dict(from_drug='fluoxetine',to_drug='MAOI',minimum=5,unit='week')])
    P('B03-LI-MAINTENANCE','HAS_LABEL_DEFINED_MAINTENANCE_ROLE',
      indication='bipolar_I',formulation='ordinary_lithium_carbonate_tablet_or_capsule',age_paths_separate=True,extended_release_dosing_inferred=False)
    P('B03-LI-NEURO-RISK','HAS_TOXICITY_AND_COMBINATION_RISK_CONTEXT',
      assess=['lithium_toxicity','antipsychotic_coadministration','clinical_manifestations'],individual_toxicity_automatically_diagnosed=False)
    P('B03-LAM-MAINTENANCE','HAS_LABEL_DEFINED_MAINTENANCE_ROLE',population='adult',indication='bipolar_I',
      prerequisite='after_standard_acute_treatment',outcome='delay_mood_episode',acute_mania_efficacy_inferred=False)
    P('B02-SER-WARFARIN','HAS_MONITORING_RELEVANT_OBSERVATION',
      observation='small_prothrombin_time_increase',clinical_significance='uncertain',monitor_when=['start_sertraline','stop_sertraline'])
    P('B03-LI-DEP-AUGMENT','HAS_SPECIALIST_AUGMENTATION_OPTION',disorder='depression',
      prerequisite='previous_inadequate_response',shared_decision=True,adverse_burden_acceptance_and_monitoring=True,automatic_on_resistant_label=False)
    P('B03-OLA-INDICATIONS','HAS_LABEL_DEFINED_INDICATION',population='adult',
      allowed_indications=['schizophrenia','moderate_or_severe_mania','bipolar_recurrence_prevention_after_effective_mania_treatment'],
      acute_bipolar_depression_inferred=False)
    P('B02-PAR-MAOI','HAS_PRODUCT_BOUND_CONTRAINDICATION',combination=['paroxetine','MAOI'],
      concomitant_use='prohibited',unknown_directional_washout_not_invented=True)
    P('B03-CLO-LI','HAS_REPORTED_NMS_AND_COMBINATION_WARNING',
      event='neuroleptic_malignant_syndrome',reported_with=['clozapine_alone','clozapine_with_CNS_drugs_including_lithium'],
      pair_relative_risk_quantified=False,individual_event_certain=False)
    P('B03-DUL-LIVER','HAS_AVOID_USE_LIVER_RISK_CONTEXT',
      avoid_in=['chronic_liver_disease','cirrhosis'],liver_injury_warning=True,all_liver_test_abnormalities_formal_contraindication=False)
    P('B03-QUE-DEP-AUGMENT','HAS_SPECIALIST_AUGMENTATION_OPTION',
      prerequisite='previous_inadequate_antidepressant_response',with_antidepressant=True,
      specific_product_and_licensing_review=True,ordinary_and_extended_release_licences_equated=False)
    P('B03-VEN-SEROTONERGIC','HAS_SEROTONERGIC_COADMINISTRATION_RISK',
      risk='serotonin_syndrome',monitoring_required=True,MAOI_contraindication_separate=True,all_serotonergic_pairs_absolutely_contraindicated=False)
    P('B03-ARI-DEP-AUGMENT','HAS_LABEL_DEFINED_ADJUNCT_INDICATION',population='adult',
      indication='MDD',adjunct_to='antidepressant',previous_response_and_safety_review=True,all_resistant_depression_inherits=False)
    P('B03-SER-NSAID','HAS_COADMINISTRATION_BLEEDING_RISK',
      combination='sertraline_with_NSAIDs_or_other_haemostasis_affecting_drugs',
      risk='bleeding_including_GI',individual_risk_assessment=True,association_equals_individual_causation=False)
    P('B02-OLA-FLU','HAS_STUDY_SPECIFIC_PK_OBSERVATION',
      influencing_drug='fluoxetine',affected_drug='olanzapine',
      mean_Cmax_change_percent=16,mean_clearance_change_percent=-16,
      effect_relative_to_between_person_variability='small',usual_adjustment_due_to_this_observation=False,individual_fixed_multiplier=False)
    P('B03-FV-OTHER-SSRI','HAS_SEROTONERGIC_COADMINISTRATION_RISK',
      risk='serotonin_syndrome',all_SSRI_pair_effects_identical=False,pair_absolute_contraindication_inferred=False)
    P('B03-LI-NSAID','HAS_DIRECTIONAL_CLASS_EXPOSURE_RISK',
      influencing_class='NSAID',affected_drug='lithium',clearance_direction='may_decrease',
      exposure_direction='may_increase',more_frequent_monitoring=True,same_multiplier_for_all_members=False)
    P('B03-LI-SEVERE-RENAL','HAS_LABEL_NOT_RECOMMENDED_CONTEXT',
      renal_measure='Cockcroft_Gault_CrCl',threshold=dict(operator='lt',value=30,unit='mL/min'),
      action='not_recommended',Chinese_formal_contraindication_established=False,implies_safe_use=False)
    P('B03-FV-OCD','HAS_LABEL_DEFINED_INDICATION',indication='OCD',
      adult_and_pediatric_age_and_dose_paths_separate=True,all_ages_inherit=False)
    P('B03-VAL-OLA','HAS_DISTINCT_PK_AND_ADVERSE_EVENT_CONTEXTS',
      affected_drug='olanzapine',exposure_direction='may_decrease',
      certain_coadministration_adverse_events_reported=True,
      CN_olanzapine_no_valproate_adjustment_observation_separate=True,no_adjustment_equals_no_risk=False)
    return out


def prepare(root=ROOT):
    base=root/'knowledge_sources/v3'
    reviews=read(base/'reviews.json'); inventory=read(base/'inventory.json'); evidence=read(base/'evidence.json')
    first=read(base/'remediation/structured-batch-01.json')['operations']; policy=policies()
    remaining={uid for uid,r in reviews.items() if r['status']=='amended'}-set(first)
    if len(remaining)!=349:raise ValueError('Unexpected frozen remaining scope')
    groups={reviews[uid]['evidence_ids'][0] for uid in remaining}
    if groups!=set(policy):raise ValueError('Missing or unused explicit policies: '+str(groups^set(policy)))
    operations={}
    names={
        'B03-RELAXATION':'应用性放松训练（成人GAD规范方案）',
        'B03-MINDFULNESS-ID':'正念类干预（具体方案分别核对）',
        'B03-OLA-LAI':'奥氮平长效肌注制剂（ZYPREXA RELPREVV）',
        'B03-OCD-12W':'OCD分方案疗效复核时点',
        'B03-OCD-MAINT':'OCD有效治疗后的继续治疗与复核',
        'B03-SER-MAX-NODES':'舍曲林成人剂量调整上限（指定中国产品）',
        'B03-RECURRENT-INTERVAL':'复发性抑郁发作间隔（数月，按WHO CDDR 2024）',
        'B03-ANTICOAG-EFFECT':'凝血酶原时间变化（临床意义未定）',
        'B03-WASHOUT14-NODE':'舍曲林与MAOI间的定向洗脱期',
        'B03-WASHOUT5W-NODE':'氟西汀与MAOI间的定向洗脱期',
        'B03-ARI-MECHANISM':'阿立哌唑的可能受体作用机制',
    }
    for uid in sorted(remaining):
        row=reviews[uid]; item=inventory[uid]; gid=row['evidence_ids'][0]; config=copy.deepcopy(policy[gid])
        if item['kind']=='entity' and config['disposition']!='withdraw':
            config['entity_role']=config['entity_role'] or {
                'B03-DEP-PSYCHOTIC':'PsychoticSymptomSpecifier',
                'B03-DEP-BIPOLAR-DIFF':'DifferentialConsideration',
                'B03-DEP-PSYCHOSIS-DIFF':'DifferentialConsideration',
                'B03-BIPOLAR-MANIA-DIFF':'DifferentialEpisodeContext',
            }.get(gid)
            if not config['entity_role']:raise ValueError('Entity needs an explicit role: '+uid)
            config['display_name']=names.get(gid,item['original']['name'])
            if item['original']['name'] in {'换药','增效'}:
                config['entity_role']='TreatmentStrategy'
                config['context']['strategy']=item['original']['name']
            if item['original']['name']=='抗癫痫药':
                config.update(entity_role='DrugClass',predicate='DEFINES_PHARMACOLOGICAL_CATEGORY',
                    context=dict(category='antiepileptic',member_dose_or_indication_inheritance=False))
            if item['original']['name']=='持续时间≥2年':config['display_name']='恶劣心境的年龄及初期病程要求'
            if item['original']['name']=='症状较轻但慢性化':config['display_name']='恶劣心境的症状及后续发作关系'
        operations[uid]=dict(item_id=uid,original_sha256=item['original_sha256'],review_sha256=digest(row),
            evidence_ids=row['evidence_ids'],policy_id=gid,
            edit=dict(kind='withdraw_original_assertion' if config['disposition']=='withdraw' else 'materialize_qualified_assertion',
                      **config))
        assert all(uid in evidence[eid]['item_ids'] for eid in row['evidence_ids'])
    result=dict(id='structured-02',version='kg_v3_candidate',expert_review='pending',reasoning_eligible=False,
        scope='exact_349_remaining_amendments',policy_sha256=digest(policy),operations=operations)
    write(base/'remediation/structured-batch-02.json',result)
    return result


if __name__=='__main__':
    from collections import Counter
    result=prepare()
    print(len(result['operations']),dict(Counter(o['edit']['kind'] for o in result['operations'].values())))
