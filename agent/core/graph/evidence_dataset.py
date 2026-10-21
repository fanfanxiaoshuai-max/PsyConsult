"""Create kg_v2 without changing the immutable v1 dataset or inferring class membership."""
import copy
import hashlib
import json
from pathlib import Path
from .normalizer import normalize, ROOT

VERSION = 'kg_v2'

def load_evidence(root=ROOT):
    root=Path(root)
    catalog=json.loads((root/'knowledge_sources/catalog.json').read_text(encoding='utf-8'))
    evidence=list(json.loads((root/'knowledge_sources/evidence.json').read_text(encoding='utf-8')).values())
    return catalog,evidence

def normalize_v2(root=ROOT):
    data=copy.deepcopy(normalize(root))
    data['version']=VERSION
    catalog,evidence=load_evidence(root)
    catalog={s['id']:s for s in catalog}
    index={(e['label'],e['name']):e for e in data['entities']}
    review=[]
    managed={r['drug'] for r in evidence}
    byid={e['id']:e for e in data['entities']}
    for edge in data['relations']:
        edge.update(reasoning_eligible=False,review_status='legacy_unverified')
        if any(byid[edge[k]]['name'] in managed for k in ('source','target')):
            status='not_covered_by_current_evidence'
            reason='旧记录未完成逐项原文核对；保留展示，不进入v2推理。'
            if edge['id']=='2c2faf6fabc3a899f8f98956':
                status='unsupported_absolute_contraindication'
                reason='P05仅支持血清素能药物类别风险警示，不能确认原记录所写的药物对绝对禁忌；亦不表示可安全联用。'
            review.append(dict(edge_id=edge['id'],source=byid[edge['source']]['name'],target=byid[edge['target']]['name'],type=edge['type'],status=status,reason=reason))
    for record in evidence:
        doc=catalog[record['source_id']]
        source_id='evidence:'+record['id']
        source=dict(doc,id=source_id,catalog_id=doc['id'],file='knowledge_sources/evidence.json',pointer='/'+record['id'],review_status=record['source_review'],expert_review=record['expert_review'],pages=record['pages'],section=record['section'],column=record.get('column'),original=record)
        data['sources'].append(source)
        endpoints=[]
        for label,name in [('Drug',record['drug']),(record['target']['label'],record['target']['name'])]:
            key=(label,name)
            if key not in index:
                uid=hashlib.sha256((label+'|evidence|'+name).encode()).hexdigest()[:24]
                item=dict(id=uid,name=name,label=label,legacy_id='',aliases=[name],properties={},source_ids=[])
                data['entities'].append(item);index[key]=item
            entity=index[key]
            entity['source_ids'].append(source_id)
            entity['source_checked_records']=entity.get('source_checked_records',0)+1
            endpoints.append(entity['id'])
        # Unique evidence ID preserves distinct conditions for identical triples.
        data['relations'].append(dict(id=hashlib.sha256(('kg_v2|'+record['id']).encode()).hexdigest()[:24],source=endpoints[0],target=endpoints[1],type=record['relation_type'],source_ids=[source_id],properties={},reasoning_eligible=True,review_status=record['source_review'],evidence=dict(record,region=doc['region'],formulation=doc['formulation'],label_revision=doc['label_revision'])))
    data['review']=review
    return data

def write_dataset_v2(root=ROOT):
    data=normalize_v2(root)
    output=Path(root)/'mock_data'/VERSION
    output.mkdir(parents=True,exist_ok=True)
    for key in ('entities','relations','sources','resolutions','aliases','review'):
        (output/(key+'.json')).write_text(json.dumps(data[key],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (Path(root)/'knowledge_sources/review.json').write_text(json.dumps(data['review'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data
