"""Apply explicit, evidence-bound edits to the offline candidate only."""
import copy
import math
from collections import Counter
from .audit import read, digest

KINDS={'replace_entity_role','replace_relation_type','replace_with_related_categories',
       'remove_code_assignment','replace_code_assignment','replace_with_scoped_records',
       'retire_unqualified_dose'}
RULE_KINDS={'dose','concentration_target','washout','interaction_management'}
UNITS={'mg/day','day','mEq/L','mmol/L','fraction_of_original_dose'}


def validate_structured_batch(batch, inventory, reviews, evidence, catalog):
    if (batch.get('id')!='structured-01' or batch.get('version')!='kg_v3_candidate' or
        batch.get('expert_review')!='pending' or batch.get('reasoning_eligible') is not False):
        raise ValueError('Invalid structured batch identity or approval')
    if not batch.get('operations'):raise ValueError('Empty structured batch')
    entity_ids={i['original']['id'] for i in inventory.values() if i['kind']=='entity'}
    for uid,op in batch['operations'].items():
        item=inventory.get(uid); review=reviews.get(uid,{}); edit=op.get('edit',{}); kind=edit.get('kind')
        if (not item or op.get('item_id')!=uid or review.get('status')!='amended' or
            op.get('original_sha256')!=item['original_sha256'] or
            op.get('review_sha256')!=digest(review) or op.get('evidence_ids')!=review.get('evidence_ids') or
            kind not in KINDS):raise ValueError('Stale or invalid structured operation: '+uid)
        original=item['original']
        if kind=='replace_entity_role':
            if (item['kind']!='entity' or original['label']!=edit.get('expected_label') or
                edit.get('label')!='CourseSpecifier' or edit.get('disease_id') not in entity_ids):
                raise ValueError('Invalid course role: '+uid)
            if not edit.get('definition',{}).get('course'):
                raise ValueError('Missing course definition: '+uid)
        elif kind=='replace_relation_type':
            allowed={('SUBTYPE_OF','HAS_EXAMPLE'),('HAS_SUBTYPE','HAS_COURSE_SPECIFIER')}
            if (item['kind']!='relation' or original['type']!=edit.get('expected_type') or
                (edit['expected_type'],edit.get('type')) not in allowed or
                edit.get('diagnostic_sufficiency') is not False):
                raise ValueError('Invalid structural relationship: '+uid)
        elif kind in {'remove_code_assignment','replace_code_assignment','replace_with_related_categories','retire_unqualified_dose'}:
            if item['kind']!='property' or edit.get('key')!=original['key']:
                raise ValueError('Wrong property target: '+uid)
            if kind=='remove_code_assignment' and (edit.get('code')!=original['value'] or
                    edit.get('replacement_code') is not None or not edit.get('reason_code')):
                raise ValueError('Invalid code retirement: '+uid)
            if kind=='replace_code_assignment' and (edit.get('old_code')!=original['value'] or
                    not all(edit.get(k) for k in ['system','edition','code','concept']) or
                    edit.get('code')!=review['proposed_change'].get('value')):
                raise ValueError('Invalid code replacement: '+uid)
            if kind=='replace_with_related_categories' and (edit.get('equivalent_to_umbrella') is not False or
                    edit.get('exhaustive') is not False or not edit.get('mappings') or
                    not edit.get('system') or not edit.get('edition')):
                raise ValueError('Unqualified related category: '+uid)
            if kind=='retire_unqualified_dose' and (edit.get('replacement_value') is not None or not edit.get('followup')):
                raise ValueError('Concentration cannot replace starting dose: '+uid)
        else:
            if not edit.get('records'):raise ValueError('No scoped records: '+uid)
            for record in edit['records']:
                proof=evidence.get(record.get('evidence_id'),{}); source=catalog.get(record.get('source_id'),{})
                if (not record.get('key') or record.get('subject_id') not in entity_ids or
                    record.get('kind') not in RULE_KINDS or not record.get('context',{}).get('population') or
                    not record.get('constraints') or not record.get('parameters') or
                    record.get('evidence_id') not in op['evidence_ids'] or uid not in proof.get('item_ids',[]) or
                    proof.get('source_id')!=record.get('source_id') or
                    source.get('availability')!='available' or source.get('used_for_claims') is not True or
                    proof.get('source_sha256')!=source.get('sha256')):
                    raise ValueError('Missing scoped clinical provenance: '+uid)
                if record['kind']=='concentration_target' and source.get('region')=='US' and not record['context'].get('sampling_hours_after_dose'):
                    raise ValueError('Missing sample timing: '+uid)
                for param in record['parameters']:
                    if param.get('unit') not in UNITS:raise ValueError('Unknown unit: '+uid)
                    numeric={k:v for k,v in param.items() if k in {'value','lower','upper','minimum','denominator'}}
                    if not numeric or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in numeric.values()):
                        raise ValueError('Invalid quantity: '+uid)
                    if 'lower' in numeric and ('upper' not in numeric or numeric['lower']>numeric['upper']):
                        raise ValueError('Invalid interval: '+uid)
                    if record['kind']=='washout' and (param.get('from_entity') not in entity_ids or
                            param.get('to_entity') not in entity_ids or param['from_entity']==param['to_entity']):
                        raise ValueError('Missing washout direction: '+uid)
                    if record['kind']=='concentration_target' and param['unit']!={'US':'mEq/L','UK':'mmol/L'}.get(source.get('region')):
                        raise ValueError('Concentration unit differs from bound source: '+uid)
    return True


def materialize(batch, entities, relations, replacements, inventory, reviews, evidence, catalog):
    validate_structured_batch(batch,inventory,reviews,evidence,catalog)
    nodes={e['id']:e for e in entities}; edges={r['id']:r for r in relations}
    drafts={r['item_id']:r for r in replacements}
    records={}; changes={}
    for uid,op in batch['operations'].items():
        item=inventory[uid]; original=item['original']; edit=op['edit']; kind=edit['kind']
        qualifiers=[dict(evidence_id=eid,conditions=evidence[eid]['conditions'],
                         source_id=evidence[eid]['source_id'],locator=evidence[eid]['locator'])
                    for eid in op['evidence_ids']]
        result=dict(kind=kind,evidence=qualifiers,expert_review='pending',reasoning_eligible=False)
        if kind=='replace_entity_role':
            node=nodes[original['id']]
            node.update(label=edit['label'],qualifies_disease_id=edit['disease_id'],
                        course_definition=copy.deepcopy(edit['definition']),
                        structured_evidence=qualifiers,structured_item_id=uid)
            result.update(before=original['label'],after=edit['label'],entity_id=node['id'],
                          course_definition=copy.deepcopy(edit['definition']))
        elif kind=='replace_relation_type':
            edge=edges[original['id']]
            edge.update(type=edit['type'],structured_item_id=uid,structured_evidence=qualifiers,
                        diagnostic_sufficiency=False)
            result.update(before=original['type'],after=edit['type'],
                          source=edge['source'],target=edge['target'],relation_id=edge['id'])
        elif kind in {'remove_code_assignment','replace_code_assignment','replace_with_related_categories','retire_unqualified_dose'}:
            node=nodes[original['entity_id']]
            node['properties'].pop(original['key'],None)
            result.update(entity_id=node['id'],key=original['key'],before=original['value'])
            if kind=='replace_code_assignment':
                coding={k:edit[k] for k in ('code','system','edition','concept')}
                coding.update(evidence=qualifiers,equivalent_to_named_concept=True,
                              expert_review='pending',reasoning_eligible=False)
                node.setdefault('codings',[]).append(coding)
                result['after']=coding
            elif kind=='replace_with_related_categories':
                mappings=[dict(mapping,system=edit['system'],edition=edit['edition'],
                    relation='related_category',equivalent_to_umbrella=False,exhaustive=False,
                    evidence=qualifiers,expert_review='pending',reasoning_eligible=False)
                    for mapping in edit['mappings']]
                for mapping in mappings:
                    if mapping not in node.setdefault('related_categories',[]):node['related_categories'].append(mapping)
                result['after']=mappings
            else:
                retirement=dict(key=original['key'],value=original['value'],
                                replacement=None,reason=edit.get('reason_code',edit.get('followup')))
                node.setdefault('retired_assignments',[]).append(retirement)
                result.update(after=None,followup_required=True)
        else:
            record_ids=[]
            for spec in edit['records']:
                rid='v3-rule:'+spec['key']; proof=evidence[spec['evidence_id']]; source=catalog[spec['source_id']]
                record=copy.deepcopy(spec)
                record.update(id=rid,label='ScopedClinicalRule',name=spec['key'],
                    expert_review='pending',reasoning_eligible=False,
                    scope=dict(region=source['region'],title=source['title'],
                               formulation=source.get('formulation'),
                               edition=source.get('label_revision',source.get('edition')),
                               conditions=proof['conditions']),
                    evidence=copy.deepcopy(proof),source_sha256=source['sha256'])
                if rid in records and digest(records[rid])!=digest(record):
                    raise ValueError('Conflicting scoped record key: '+rid)
                records[rid]=record
                record_ids.append(rid)
            result['record_ids']=record_ids
            if item['kind']=='property':
                nodes[original['entity_id']]['properties'].pop(original['key'],None)
            if item['kind']=='relation':edges[original['id']]['superseded_by']=record_ids
        drafts[uid].update(implementation_status='structured_applied_candidate',structured_result=result)
        changes[uid]=result
    scoped_links=[dict(id='link:'+rid,source=rule['subject_id'],target=rid,type='HAS_SCOPED_RULE',
                       reasoning_eligible=False,expert_review='pending',evidence_id=rule['evidence_id'])
                  for rid,rule in sorted(records.items())]
    graph_links=[copy.deepcopy(r) for r in relations if r.get('structured_item_id')]+scoped_links
    wanted={r[k] for r in graph_links for k in ('source','target')}
    wanted.update(r['entity_id'] for r in changes.values() if 'entity_id' in r)
    graph_nodes=[]
    for node in entities:
        if node['id'] in wanted:
            graph_nodes.append({k:copy.deepcopy(node[k]) for k in
                ('id','name','label','codings','related_categories','reasoning_eligible','display_only','structured_evidence','course_definition')
                if k in node})
    graph_nodes.extend(copy.deepcopy(records[k]) for k in sorted(records))
    graph=dict(version='kg_v3_candidate',activation_ready=False,expert_review='pending',
               nodes=graph_nodes,edges=graph_links)
    return dict(batch_id=batch['id'],batch_sha256=digest(batch),changes=changes,
                clinical_records=[records[k] for k in sorted(records)],clinical_links=scoped_links,
                graph=graph,counts_by_operation=dict(Counter(x['kind'] for x in changes.values())))


def inspect_candidate(candidate, query, limit=30):
    """Read-only preview: search the materialized values, never retired values or raw drafts."""
    if not query.strip():raise ValueError('请输入搜索词')
    needle=query.strip().casefold()
    import json
    def contains(value):return needle in json.dumps(value,ensure_ascii=False).casefold()
    hits=[e for e in candidate['entities'] if not e.get('withdrawn') and contains(dict(name=e['name'],codings=e.get('codings',[])))]
    ids={e['id'] for e in hits}
    records=[r for r in candidate['structured']['clinical_records'] if r['subject_id'] in ids or
             contains(dict(key=r['key'],context=r['context'],parameters=r['parameters']))]
    links=[r for r in candidate['relations'] if r.get('structured_item_id') and (r['source'] in ids or r['target'] in ids)]
    assertions=[a for a in candidate['structured'].get('qualified_assertions',[]) if a['subject_id'] in ids or
                contains(dict(context=a['context'],name=a['name']))]
    # For a clinical-rule search include its drug and related records' endpoint labels.
    ids.update(r['subject_id'] for r in records)
    ids.update(a['subject_id'] for a in assertions)
    ids.update(r[k] for r in links for k in ('source','target'))
    def project(node):
        return {k:node[k] for k in ('id','name','label','codings','related_categories',
                'reasoning_eligible','display_only','course_definition','structured_evidence') if k in node}
    result=dict(version=candidate['version'],notice='离线候选预览；临床专家未审核，不用于自动诊断或个人处方。',
        activation_ready=False,matched_entities=[project(n) for n in hits[:limit]],
        relations=links[:limit],clinical_records=records[:limit],qualified_assertions=assertions[:limit],
        nodes=[project(e) for e in candidate['entities'] if e['id'] in ids and not e.get('withdrawn')][:limit],
        totals=dict(entities=len(hits),relations=len(links),clinical_records=len(records),qualified_assertions=len(assertions)))
    result['truncated']=any(n>limit for n in result['totals'].values()) or len(ids)>limit
    return result
