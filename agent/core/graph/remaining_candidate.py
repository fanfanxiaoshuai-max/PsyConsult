"""Materialize qualified facts and explicit withdrawals, never a generic prose wrapper."""
import copy
import math
import re
from collections import Counter
from .audit import digest

def _check_json(value):
    if isinstance(value,dict):
        for key,child in value.items():
            if not isinstance(key,str):raise ValueError('Non-string context key')
            _check_json(child)
    elif isinstance(value,list):
        for child in value:_check_json(child)
    elif isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite clinical value')
    elif value is not None and type(value) not in (str,int,float,bool):raise ValueError('Unknown clinical value type')


def validate_remaining_batch(batch, first, inventory, reviews, evidence, catalog):
    if (batch.get('id')!='structured-02' or batch.get('version')!='kg_v3_candidate' or
        batch.get('expert_review')!='pending' or batch.get('reasoning_eligible') is not False):
        raise ValueError('Invalid remaining batch identity or approval')
    expected={uid for uid,r in reviews.items() if r['status']=='amended'}-set(first['operations'])
    if set(batch.get('operations',{}))!=expected or len(expected)!=349:
        raise ValueError('Remaining batch must cover the exact disjoint 349 items')
    for uid,op in batch['operations'].items():
        row=reviews[uid];item=inventory[uid];edit=op.get('edit',{})
        if (op.get('item_id')!=uid or op.get('original_sha256')!=item['original_sha256'] or
            op.get('review_sha256')!=digest(row) or op.get('evidence_ids')!=row['evidence_ids'] or
            op.get('policy_id')!=row['evidence_ids'][0]):raise ValueError('Stale remaining operation: '+uid)
        if not re.fullmatch('[A-Z][A-Z_]+',edit.get('predicate','')) or not edit.get('context'):
            raise ValueError('Missing semantic predicate or structured conditions: '+uid)
        _check_json(edit['context'])
        if edit.get('kind')=='withdraw_original_assertion':
            if (edit.get('disposition')!='withdraw' or edit['context'].get('replacement_value','missing') is not None
                or not edit['context'].get('reason')):raise ValueError('Invalid explicit withdrawal: '+uid)
        elif edit.get('kind')=='materialize_qualified_assertion':
            if edit.get('disposition')!='qualify':raise ValueError('Invalid qualified disposition: '+uid)
            if item['kind']=='entity' and (not edit.get('entity_role') or not edit.get('display_name')):
                raise ValueError('Entity requires a concrete role and display name: '+uid)
            ctx=edit['context'];predicate=edit['predicate']
            for profile in ctx.get('dose_profiles',[]):
                if not profile.get('population') or profile.get('unit') not in {'mg','mg/day'}:
                    raise ValueError('Dose profile lacks population or unit: '+uid)
                for value in profile.values():
                    if type(value) in (int,float) and value<=0:
                        raise ValueError('Nonpositive dose profile value: '+uid)
                    if isinstance(value,list) and value and all(type(v) in (int,float) for v in value):
                        if any(v<=0 for v in value) or (len(value)==2 and value[0]>value[1]):
                            raise ValueError('Invalid dose profile interval: '+uid)
            if predicate=='HAS_CAUSAL_ATTRIBUTION_EXCLUSION' and (
                ctx.get('causal_attribution_required') is not True or
                ctx.get('comorbidity_or_use_history_alone_excludes') is not False):
                raise ValueError('Comorbidity cannot be unconditional exclusion: '+uid)
            if predicate=='HAS_REPORTED_ADVERSE_EVENT' and ctx.get('individual_causation_established') is not False:
                raise ValueError('Adverse report is not certain individual causation: '+uid)
            if predicate in {'HAS_DIRECTIONAL_WASHOUT_REQUIREMENT','HAS_LABEL_CONTRAINDICATION_AND_DIRECTIONAL_WASHOUT'}:
                directions=ctx.get('directions',[])
                if len(directions)!=2 or any(not all(d.get(k) for k in ('from_drug','to_drug','minimum','unit')) for d in directions):
                    raise ValueError('Missing directional washout: '+uid)
                a,b=directions
                if (a['from_drug'],a['to_drug'])!=(b['to_drug'],b['from_drug']) or a['from_drug']==a['to_drug']:
                    raise ValueError('Invalid switch endpoints: '+uid)
                if any(type(d['minimum']) not in (int,float) or d['minimum']<=0 or d['unit'] not in {'day','week'} for d in directions):
                    raise ValueError('Invalid directional time: '+uid)
            if op['policy_id']=='B03-OLA-LAI' and (ctx.get('route')!='deep_intramuscular_gluteal' or not ctx.get('scope_correction')):
                raise ValueError('LAI route must be corrected against original label: '+uid)
        else:raise ValueError('Unknown remaining operation: '+uid)
        for eid in op['evidence_ids']:
            proof=evidence.get(eid,{});source=catalog.get(proof.get('source_id'),{})
            if (uid not in proof.get('item_ids',[]) or source.get('used_for_claims') is not True or
                source.get('availability')!='available' or proof.get('source_sha256')!=source.get('sha256') or
                not proof.get('locator') or proof.get('scope')!='medical_source_comparison'):
                raise ValueError('Missing item-bound original evidence: '+uid)
    return True


def apply_remaining(batch, first, entities, relations, replacements, inventory, reviews, evidence, catalog):
    validate_remaining_batch(batch,first,inventory,reviews,evidence,catalog)
    nodes={e['id']:e for e in entities};edges={e['id']:e for e in relations}
    names={e['name']:e['id'] for e in entities};drafts={r['item_id']:r for r in replacements}
    facts={};changes={};retired=[]
    for uid,op in batch['operations'].items():
        item=inventory[uid]; original=item['original'];edit=op['edit'];context=copy.deepcopy(edit['context'])
        result=dict(kind=edit['kind'],policy_id=op['policy_id'],expert_review='pending',reasoning_eligible=False)
        result['evidence']=[dict(evidence_id=eid,source_id=evidence[eid]['source_id'],
            sha256=evidence[eid]['source_sha256'],locator=copy.deepcopy(evidence[eid]['locator'])) for eid in op['evidence_ids']]
        if item['kind']=='entity':
            node=nodes[original['id']]; subject_id=node['id']
            result.update(entity_id=subject_id,before=dict(name=original['name'],label=original['label']))
        elif item['kind']=='property':
            subject_id=original['entity_id'];node=nodes[subject_id]
            node['properties'].pop(original['key'],None)
            result.update(entity_id=subject_id,key=original['key'],before=copy.deepcopy(original['value']))
        else:
            edge=edges[original['id']];subject_id=original['source']
            result.update(relation_id=edge['id'],before={k:original[k] for k in ('source','type','target')})
            edge.update(retired_from_materialized_view=True,reasoning_eligible=False)
        if edit['kind']=='withdraw_original_assertion':
            if item['kind']=='entity':
                node.update(withdrawn=True,aliases=[],properties={},display_only=True)
            result.update(after=None,reason_code=context['reason'],replacement_value=None,followup_required=True)
            retired.append(uid)
        else:
            if context.get('subject_override'):
                if context['subject_override'] not in names:raise ValueError('Unknown corrected subject: '+uid)
                subject_id=names[context.pop('subject_override')]
            related=None
            if item['kind']=='relation':
                target_id=original['target'] if subject_id!=original['target'] else original['source']
                related=dict(entity_id=target_id,role='related_reference_not_unqualified_claim',clinical_value_inferred=False)
            provenance=[]
            for eid in op['evidence_ids']:
                proof=evidence[eid];source=catalog[proof['source_id']]
                provenance.append(dict(evidence_id=eid,source_id=proof['source_id'],sha256=source['sha256'],
                    region=source['region'],source_title=source.get('title') or source.get('drug') or proof['source_id'],locator=copy.deepcopy(proof['locator']),
                    edition=source.get('label_revision',source.get('edition')),
                    formulation=source.get('formulation'),audited_finding=proof['summary'],
                    scope_conditions=(context['scope_correction'] if op['policy_id']=='B03-OLA-LAI' else proof['conditions'])))
            semantic=dict(subject_id=subject_id,predicate=edit['predicate'],context=context,
                          related_concept=related,provenance=provenance)
            fid='v3-fact:'+digest(semantic)[:24]
            fact=dict(semantic,id=fid,label='ScopedClinicalAssertion',kind='qualified_assertion',
                name=nodes[subject_id]['name']+' · '+edit['predicate'],
                reasoning_eligible=False,expert_review='pending',diagnostic_sufficiency=False,
                category_inheritance=False,policy_id=op['policy_id'])
            if fid not in facts:facts[fid]=dict(fact,audit_item_ids=[])
            facts[fid]['audit_item_ids'].append(uid)
            result.update(after=dict(predicate=edit['predicate'],subject_id=subject_id,context=context),assertion_ids=[fid])
            result['evidence']=copy.deepcopy(provenance)
            if item['kind']=='entity':
                node.update(label=edit['entity_role'],name=edit['display_name'],aliases=[],
                    qualified_definition_refs=[fid],structured_item_id=uid)
                node['properties'].pop('name',None)
                node['properties'].pop('name_cn',None)
                result['after'].update(label=node['label'],name=node['name'])
            elif item['kind']=='property':
                node.setdefault('qualified_property_refs',{})[original['key']]=[fid]
            else:edge['superseded_by']=[fid]
        drafts[uid].update(implementation_status='structured_applied_candidate',structured_result=result)
        changes[uid]=result
    facts_list=[facts[k] for k in sorted(facts)]
    for fact in facts_list:
        fact['name']=nodes[fact['subject_id']]['name']+' · '+fact['predicate']
    links=[dict(id='qualified-link:'+f['id'],source=f['subject_id'],target=f['id'],
                type='HAS_QUALIFIED_ASSERTION',reasoning_eligible=False,expert_review='pending') for f in facts_list]
    return dict(batch_id=batch['id'],batch_sha256=digest(batch),changes=changes,
        qualified_assertions=facts_list,qualified_links=links,withdrawn_items=retired,
        counts_by_operation=dict(Counter(r['kind'] for r in changes.values())))


def merge_structured(first,second,entities):
    if set(first['changes']) & set(second['changes']):raise ValueError('Batches overlap')
    changes=dict(first['changes'],**second['changes']);assert len(changes)==399
    nodes={n['id']:copy.deepcopy(n) for n in first['graph']['nodes']}
    wanted={f['subject_id'] for f in second['qualified_assertions']}
    wanted.update(r['entity_id'] for r in second['changes'].values() if 'entity_id' in r and r['after'] is not None)
    for entity in entities:
        if entity['id'] in nodes or entity['id'] in wanted:
            if entity.get('withdrawn'):
                nodes.pop(entity['id'],None)
                continue
            nodes[entity['id']]={k:copy.deepcopy(entity[k]) for k in
                ('id','name','label','codings','related_categories','reasoning_eligible','display_only',
                 'structured_evidence','course_definition','qualified_definition_refs','qualified_property_refs') if k in entity}
    for fact in second['qualified_assertions']:nodes[fact['id']]=copy.deepcopy(fact)
    links=copy.deepcopy(first['graph']['edges'])+copy.deepcopy(second['qualified_links'])
    missing={link[k] for link in links for k in ('source','target') if link[k] not in nodes}
    if missing:
        raise ValueError('Structured graph has unresolved or withdrawn endpoints: '+str(sorted(missing)))
    graph=dict(version='kg_v3_candidate',activation_ready=False,expert_review='pending',
        nodes=[nodes[k] for k in sorted(nodes)],edges=links)
    return dict(batch_id='structured-01+02',batch_sha256=digest([first['batch_sha256'],second['batch_sha256']]),
        batches=[first,second],changes=changes,clinical_records=first['clinical_records'],
        clinical_links=first['clinical_links'],qualified_assertions=second['qualified_assertions'],
        graph=graph,counts_by_operation=dict(Counter(r['kind'] for r in changes.values())))
