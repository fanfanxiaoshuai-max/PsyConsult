"""Deterministic conversion. No LLM or invented clinical assertions."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERSION = 'kg_v1'

def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]

def normalize(root=ROOT):
    entities, sources, edges, decisions = {}, [], {}, []
    datasets = [(p, json.loads(p.read_text(encoding='utf-8'))) for p in sorted((root / 'mock_data').glob('*.json'))]
    by_name = {}
    local = {}
    for path, data in datasets:
        local[path.name] = {}
        for i, node in enumerate(data['nodes']):
            uid = stable_id(node['label'], node['id'])
            by_name.setdefault(node['id'], set()).add(uid)
            local[path.name].setdefault(node['id'], set()).add(uid)
            sid = f'{path.name}#/nodes/{i}'
            props = {p['key']: p['value'] for p in node.get('properties', [])}
            sources.append(dict(id=sid, file='mock_data/' + path.name, pointer=f'/nodes/{i}',
                                review_status='medical_source_unverified', original=node))
            if uid not in entities:
                entities[uid] = dict(id=uid, legacy_id=node['id'], label=node['label'],
                    name=props.get('name_cn') or props.get('name') or node['id'],
                    properties=props, source_ids=[], aliases=[node['id']])
            entity = entities[uid]
            entity['source_ids'].append(sid)
            for key, value in props.items():
                if key in entity['properties'] and entity['properties'][key] != value:
                    decisions.append(dict(kind='property_conflict', entity_id=uid, field=key,
                        source_id=sid, status='pending_review', reason='Different source values; retained in source records.'))
                else:
                    entity['properties'][key] = value
            for key in ('name', 'name_cn', 'name_en', 'generic_name'):
                if isinstance(props.get(key), str) and props[key].strip():
                    entity['aliases'].append(props[key].strip())
    for path, data in datasets:
        for i, edge in enumerate(data['edges']):
            sid = f'{path.name}#/edges/{i}'
            sources.append(dict(id=sid, file='mock_data/' + path.name, pointer=f'/edges/{i}',
                                review_status='medical_source_unverified', original=edge))
            endpoints = []
            for role in ('source', 'target'):
                candidates = by_name.get(edge[role], set())
                scoped = local[path.name].get(edge[role], set())
                chosen = candidates if len(candidates) == 1 else scoped
                endpoints.append(next(iter(chosen)) if len(chosen) == 1 else None)
            if not all(endpoints):
                decisions.append(dict(kind='unresolved_edge', source_id=sid, original=edge,
                    status='pending_review', reason='Missing endpoint or ambiguous entity type; excluded from active graph.'))
                continue
            if any(len(by_name[edge[r]]) > 1 for r in ('source', 'target')):
                decisions.append(dict(kind='scoped_endpoint', source_id=sid, endpoints=endpoints,
                    status='resolved_structurally', reason='Unique entity type in the originating file; no cross-label expansion.'))
            eid = stable_id(*endpoints, edge['type'])
            if eid not in edges:
                raw = edge.get('properties', {})
                props = {p['key']: p['value'] for p in raw} if isinstance(raw, list) else dict(raw)
                edges[eid] = dict(id=eid, source=endpoints[0], target=endpoints[1], type=edge['type'],
                                  properties=props, source_ids=[])
            edges[eid]['source_ids'].append(sid)
    synonym_path = root / 'agent/config/symptom_synonyms.json'
    if synonym_path.exists():
        for term, record in json.loads(synonym_path.read_text(encoding='utf-8')).items():
            candidates = by_name.get(record.get('term'), set())
            if len(candidates) == 1:
                entity = entities[next(iter(candidates))]
                entity['aliases'].append(term)
                sid = 'symptom_synonyms.json#/' + term
                entity['source_ids'].append(sid)
                sources.append(dict(id=sid, file='agent/config/symptom_synonyms.json', pointer='/' + term,
                    review_status='medical_source_unverified', original={term: record}))
    for entity in entities.values():
        entity['aliases'] = sorted(set(entity['aliases']))
    return dict(version=VERSION, entities=list(entities.values()), relations=list(edges.values()),
                sources=sources, resolutions=decisions,
                aliases=[dict(entity_id=e['id'], terms=e['aliases']) for e in entities.values()])

def write_dataset(root=ROOT):
    data = normalize(root)
    out = root / 'mock_data' / VERSION
    out.mkdir(parents=True, exist_ok=True)
    for key in ('entities', 'relations', 'sources', 'resolutions', 'aliases'):
        (out / (key + '.json')).write_text(json.dumps(data[key], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return data
