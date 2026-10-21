"""Entity-aware deterministic retrieval shared by chat and browser."""
import json
from .models import GraphEntity

GROUPS = {
 'symptoms': ('SYMPTOM', 'REQUIRES', 'EXCLUDED', 'DIFFERENTIATED', 'CHARACTERIZED', 'ASSOCIATED'),
 'treatment': ('TREAT', 'FIRST_LINE', 'SECOND_LINE', 'THERAPY', 'DOSE'),
 'side_effects': ('SIDE_EFFECT', 'CAUSES', 'RISK', 'CONTRAINDICATED_IN', 'CHARACTERISTIC', 'MONITORING'),
 'interactions': ('INTERACT', 'CONCENTRATION', 'METABOLISM', 'WITH', 'NEUROTOXICITY', 'POTENTIATES'),
}

# Search vocabulary only: preserve entity IDs, labels and medical review status.
SEARCH_ALIASES = {
    ('Disease', '抑郁障碍'): ('抑郁症',),
    ('Disease', '双相障碍'): ('双相情感障碍',),
    ('DifferentialDiagnosis', '双相障碍'): ('双相情感障碍',),
}


def entity_terms(entity):
    terms=set([entity['name'],entity.get('legacy_id','')]+entity.get('aliases',[]))
    terms.update(SEARCH_ALIASES.get((entity['label'],entity['name']),()))
    if entity['label']=='DrugClass' and entity['name']=='MAOIs':
        terms.update(['MAOI','单胺氧化酶抑制剂'])
    return [a for a in terms if isinstance(a,str) and a.strip()]


def rank_entities(query: str, entities: list[GraphEntity]) -> list[GraphEntity]:
    query = query.strip().casefold()
    ranked = []
    for entity in entities:
        aliases = entity_terms(entity)
        terms = [a.casefold() for a in aliases if isinstance(a, str) and a.strip()]
        exact = any(t == query for t in terms)
        contained = [len(t) for t in terms if len(t) >= 2 and t in query]
        partial = any(query in t for t in terms) if len(query) >= 2 else False
        score = 10000 if exact else 100 + max(contained) if contained else 1 if partial else 0
        if score:
            ranked.append((score, entity))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]['label'], pair[1]['id']))
    return [entity for _, entity in ranked]

def infer_group(query):
    for group, terms in [('interactions', ('相互作用', '合用', '联用', '一起')), ('side_effects', ('副作用', '不良反应', '禁忌', '监测')), ('symptoms', ('症状', '诊断', '鉴别')), ('treatment', ('治疗', '用药', '剂量'))]:
        if any(term in query for term in terms):
            return group
    return 'all'

def matches_group(relation_type, group):
    return group == 'all' or any(term in relation_type for term in GROUPS.get(group, ()))

def retrieve(repository, query, limit=20):
    if getattr(repository,'is_snapshot',False):return repository.retrieve(query,limit)
    candidates = rank_entities(query, repository.entities())
    if not candidates:
        return dict(version=repository.version, candidates=[], nodes=[], edges=[], truncated=False, message='当前图谱未收录相关实体。')
    # Keep all exact/contained entities, including same-name entities of different types.
    explicit = [e for e in candidates if any(len(a) >= 2 and a.casefold() in query.casefold() for a in entity_terms(e))]
    chosen = explicit or candidates[:5]
    chosen = chosen[:12]
    drugs = {e['id'] for e in chosen if e['label'] == 'Drug'}
    pair_ids = drugs if len(drugs) >= 2 and infer_group(query) == 'interactions' else None
    result = repository.neighbors([e['id'] for e in chosen], group=infer_group(query), limit=limit, pair_ids=pair_ids)
    if pair_ids:
        result['message'] = '仅返回已匹配药物之间的直接关系；无直接关系不表示可安全合用。'
    if repository.version=='kg_v2':
        # No unverified dose/indication properties enter the agent context.
        safe_keys=('id','name','label','aliases','source_checked_records')
        result['nodes']=[{k:e[k] for k in safe_keys if k in e} for e in result['nodes']]
        chosen=[{k:e[k] for k in safe_keys if k in e} for e in chosen]
        if pair_ids:
            context=repository.neighbors(sorted(pair_ids),group='interactions',limit=40)
            # Class warnings are context, not asserted direct drug-pair edges.
            drug_index={e['id']:e for e in context['nodes']}
            class_edges=[e for e in context['edges'] if drug_index.get(e['target'],{}).get('label')=='DrugClass']
            result['class_context']=dict(edges=class_edges,nodes=[{k:e[k] for k in safe_keys if k in e} for e in context['nodes']],sources=context.get('sources',[]),notice='仅为药物类别警示上下文；未自动推断成员关系或药物对禁忌。')
        result['message'] += ' 仅使用已核对原文的有限证据，未经临床专家审核；未收录不表示安全。'
    result['candidates'] = chosen
    return result

def format_result(result):
    keys=('id','catalog_id','file','pointer','review_status','title','url','pages','section','column','label_revision','region','formulation','sha256','expert_review','publisher','source_kind','manufacturer','approval_number')
    def sources(items):
        return [{k:s[k] for k in keys if k in s} for s in items]
    result['sources']=sources(result.get('sources',[]))
    if 'class_context' in result:
        result['class_context']['sources']=sources(result['class_context']['sources'])
    if not result.get('version','').startswith('project-'):
        result['evidence_notice'] = ('仅列出程序代理核对原文的条件性记录；临床专家审核待完成。美国标签不代表中国批准适应范围。旧记录与实体原属性未作为已验证事实传入。未收录不表示安全。' if result.get('version')=='kg_v2' else '来源可定位到仓库记录；医学原文尚未核实。未收录不等于不存在。')
    return json.dumps(result, ensure_ascii=False)
