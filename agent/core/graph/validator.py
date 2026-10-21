"""Fail closed on malformed normalized data before any database writes."""
import re

def validate(data):
    errors = []
    ids = [e['id'] for e in data['entities']]
    source_ids = {s['id'] for s in data['sources']}
    edge_ids = [r['id'] for r in data['relations']]
    if len(ids) != len(set(ids)) or len(edge_ids) != len(set(edge_ids)):
        errors.append('Duplicate stable IDs')
    for item in data['entities'] + data['relations']:
        if not item.get('source_ids') or not set(item['source_ids']) <= source_ids:
            errors.append('Missing provenance: ' + item['id'])
    for edge in data['relations']:
        if edge['source'] not in ids or edge['target'] not in ids:
            errors.append('Dangling edge: ' + edge['id'])
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', edge['type']):
            errors.append('Invalid relation type: ' + edge['type'])
    if data['version'] == 'kg_v2':
        source_index={s['id']:s for s in data['sources']}
        evidence_ids=[]
        for edge in data['relations']:
            if not edge.get('reasoning_eligible'):
                continue
            evidence=edge.get('evidence', {})
            evidence_ids.append(evidence.get('id'))
            required=('summary','conditions','action','population','region','formulation','pages','label_revision')
            if any(not evidence.get(k) for k in required) or evidence.get('source_review')!='source_checked_by_agent' or evidence.get('expert_review')!='pending':
                errors.append('Incomplete scoped evidence: '+edge['id'])
            if evidence.get('region') not in ('CN','US') or not evidence.get('pages') or any(type(p) is not int or p<1 for p in evidence.get('pages',[])):
                errors.append('Invalid region or page locator: '+edge['id'])
            for sid in edge['source_ids']:
                source=source_index.get(sid,{})
                if not re.fullmatch(r'[0-9a-f]{64}',source.get('sha256','')) or not source.get('url','').startswith('https://') or source.get('used_for_claims') is not True or source.get('review_status')!='source_checked_by_agent' or source.get('pages')!=evidence.get('pages') or source.get('catalog_id')!=evidence.get('source_id') or any(source.get(k)!=evidence.get(k) for k in ('region','formulation','label_revision')):
                    errors.append('Invalid source proof: '+edge['id'])
        if len(evidence_ids)!=len(set(evidence_ids)):
            errors.append('Duplicate evidence IDs')
    if errors:
        raise ValueError('; '.join(errors))
    report = dict(entities=len(ids), relations=len(edge_ids), sources=len(source_ids),
                pending=sum(r['status'] == 'pending_review' for r in data['resolutions']))

    if data['version']=='kg_v2':
        checked=[e for e in data['relations'] if e.get('reasoning_eligible')]
        report.update(source_checked_relations=len(checked),legacy_unverified_relations=len(data['relations'])-len(checked),expert_reviewed_relations=0,cn_records=sum(e['evidence']['region']=='CN' for e in checked),us_supplement_records=sum(e['evidence']['region']=='US' for e in checked),review=data['review'])
    return report
