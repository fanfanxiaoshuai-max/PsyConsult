"""Deterministic offline candidate. Removing an unsafe claim is not approving its replacement."""
import copy
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from .audit import ROOT, digest, read, write, validate_audit

VERSION = 'kg_v3_candidate'
LABEL_LOCATORS = {
    'us_sertraline_supplement': ('1; 2.1; 5.2; 7', ['Posttraumatic stress disorder', 'Social anxiety disorder', 'Panic disorder', 'other SSRIs']),
    'us_ziprasidone_supplement': ('INDICATIONS AND USAGE', ['Ziprasidone capsules are an atypical antipsychotic']),
    'us_buspirone_supplement': ('INDICATIONS AND USAGE', ['Generalized Anxiety Disorder', 'more than 3 to 4 weeks']),
    'us_hydrochlorothiazide_supplement': ('DRUG INTERACTIONS / Lithium', ['reduce the renal clearance of lithium']),
    'uk_clozapine_supplement': ('4.3 Contraindications', ['previous chemotherapy', 'Uncontrolled epilepsy', 'Severe renal or cardiac disorders']),
    'uk_fluvoxamine_supplement': ('4.1 Therapeutic indications', ['Major depressive episode', 'Obsessive Compulsive Disorder']),
}


def source_receipts(root, sources):
    receipts = {}
    for sid, source in sources.items():
        if source.get('availability') != 'available':
            raise ValueError('Supplement unavailable: ' + sid)
        path = (root / source['local_snapshot']).resolve()
        if not path.is_relative_to((root / '.tools/knowledge_sources').resolve()):
            raise ValueError('Source outside cache: ' + sid)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Source hash mismatch: ' + sid)
        if source.get('format') == 'xml':
            pmid = source['locator']['pmid']
            article = next((a for a in ET.fromstring(raw).findall('.//PubmedArticle')
                            if a.findtext('./MedlineCitation/PMID') == pmid), None)
            if article is None or not article.findall('.//AbstractText'):
                raise ValueError('Missing primary abstract: ' + sid)
            text = ' '.join(''.join(a.itertext()) for a in article.findall('.//AbstractText'))
            locator = dict(kind='pubmed_article_abstract', pmid=pmid,
                           title=''.join(article.find('.//ArticleTitle').itertext()),
                           full_article_reviewed=False)
        else:
            text = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', raw.decode('utf-8'))))
            section, needles = LABEL_LOCATORS[sid]
            if not all(n.casefold() in text.casefold() for n in needles):
                raise ValueError('Examined label text missing: ' + sid)
            locator = dict(kind='html_text_matches', section=section, needles=needles)
        receipts[sid] = dict(source_sha256=source['sha256'], locator=locator,
                             examined_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                             expert_review='pending')
    return receipts


def build_candidate(root=ROOT):
    root = Path(root)
    base = root / 'knowledge_sources/v3'
    inventory, reviews = validate_audit(root)
    evidence = read(base / 'evidence.json')
    rechecks = read(base / 'remediation/rechecks.json')['items']
    sources = read(base / 'remediation/sources.json')
    receipts = source_receipts(root, sources)
    expected_open = {uid for uid, r in reviews.items() if r['status'] == 'insufficient_evidence'}
    if set(rechecks) != expected_open:
        raise ValueError('Supplemental ledger must cover the exact original open set')
    outcomes = {'scoped_replacement_available', 'conflicting_evidence', 'original_claim_not_established', 'still_open'}
    for uid, row in rechecks.items():
        if (row['original_review_sha256'] != digest(reviews[uid]) or
            row['expert_review'] != 'pending' or row['original_claim_enabled'] is not False or
            row['outcome'] not in outcomes or not row['scope_limit'] or not row['conclusion'] or
            not set(row['source_ids']).issubset(sources) or
            (row['outcome'] != 'still_open' and not row['source_ids'])):
            raise ValueError('Invalid supplement: ' + uid)

    entities = copy.deepcopy(read(base / 'baseline/entities.json'))
    relations = copy.deepcopy(read(base / 'baseline/relations.json'))
    by_id = {e['id']: e for e in entities}
    actions, replacements, quarantine = {}, [], []
    for entity in entities:
        # Raw aliases can contain the same unqualified clinical assertion as a name.
        entity['aliases'] = []
        entity['properties'] = {}
        entity['reasoning_eligible'] = False
        entity['review_status'] = reviews['entity:' + entity['id']]['status']
        entity['display_only'] = True
    for uid, item in inventory.items():
        row, kind = reviews[uid], item['kind']
        status = row['status']
        action = dict(item_id=uid, summary=item['summary'], original_sha256=item['original_sha256'],
                      review_sha256=digest(row), status=status, reasoning_eligible=False,
                      evidence_ids=row.get('evidence_ids', []), reason=row['reason'])
        if status == 'amended':
            action['action'] = {'property': 'remove_original_property', 'relation': 'disable_original_relation',
                                'entity': 'restrict_entity_to_display'}[kind]
            proposal = copy.deepcopy(row.get('proposed_change'))
            if not proposal:
                raise ValueError('Missing amendment: ' + uid)
            proofs = [copy.deepcopy(evidence[eid]) for eid in row['evidence_ids']]
            replacements.append(dict(item_id=uid, original_sha256=item['original_sha256'],
                proposed_change=proposal, evidence=proofs, expert_review='pending',
                implementation_status='draft_scoped_record' if isinstance(proposal.get('replacement'), dict)
                                      else 'requires_structured_replacement',
                reasoning_eligible=False))
        elif status == 'quarantined':
            action['action'] = 'keep_isolated'
            quarantine.append(copy.deepcopy(item))
        elif status == 'insufficient_evidence':
            action['action'] = 'disable_original_and_record_recheck'
            action['supplement'] = copy.deepcopy(rechecks[uid])
        else:
            action['action'] = 'retain_audited_reference_only'
            if kind == 'property':
                prop = item['original']
                # Preserve accepted properties only as offline reference, never as agent input.
                by_id[prop['entity_id']]['properties'][prop['key']] = copy.deepcopy(prop['value'])
        actions[uid] = action
    for edge in relations:
        uid = 'relation:' + edge['id']
        edge['reasoning_eligible'] = False
        edge['review_status'] = reviews[uid]['status']
        # Legacy payloads are unscoped, even if a relationship is medically source-supported.
        edge['properties'] = {}
        edge['audit_item_id'] = uid
    from .structured_candidate import materialize
    batch=read(base/'remediation/structured-batch-01.json')
    catalog=read(base/'catalog.json')
    first=materialize(batch,entities,relations,replacements,inventory,reviews,evidence,catalog)
    from .remaining_candidate import apply_remaining,merge_structured
    second_batch=read(base/'remediation/structured-batch-02.json')
    second=apply_remaining(second_batch,batch,entities,relations,replacements,inventory,reviews,evidence,catalog)
    structured=merge_structured(first,second,entities)
    for uid in structured['changes']:
        actions[uid]['structured_operation']=structured['changes'][uid]
    seals = {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in
             ['baseline.json', 'inventory.json', 'reviews.json', 'evidence.json', 'catalog.json',
              'remediation/sources.json', 'remediation/rechecks.json', 'remediation/structured-batch-01.json',
              'remediation/structured-batch-02.json']}
    summary = dict(total=len(actions), amendment_safety_actions=sum(a['status'] == 'amended' for a in actions.values()),
                   clinical_amendments_approved=0, replacement_drafts=len(replacements),
                   structured_drafts=sum(r['implementation_status'] == 'draft_scoped_record' for r in replacements),
                   structured_items_applied=len(structured['changes']),
                   remaining_structured_items=len(replacements)-len(structured['changes']),
                   scoped_clinical_records=len(structured['clinical_records']),
                   qualified_assertions=len(structured['qualified_assertions']),
                   remaining_batch_qualified_items=second['counts_by_operation']['materialize_qualified_assertion'],
                   remaining_batch_withdrawn_items=len(second['withdrawn_items']),
                   rechecks=dict(Counter(r['outcome'] for r in rechecks.values())),
                   quarantined=len(quarantine), reasoning_eligible=0, activation_ready=False,
                   release_blockers=[f'{len(structured["changes"])}条已落实候选结构化编辑，{len(replacements)-len(structured["changes"])}条仍待结构化；均未完成临床验收',
                                     '55条补查均未恢复旧断言，13条继续隔离',
                                     '临床专家审核尚未完成'])
    return dict(version=VERSION, stage='offline_candidate', activation_ready=False,
                baseline_version='kg_v2', input_sha256=seals, source_receipts=receipts,
                summary=summary, entities=entities, relations=relations, actions=actions,
                replacement_drafts=replacements, quarantine=quarantine, structured=structured)


def validate_candidate(candidate, root=ROOT):
    """Rebuild from sealed inputs; any changed eligibility, dropped item or altered draft fails."""
    expected = build_candidate(root)
    if digest(candidate) != digest(expected):
        raise ValueError('Candidate differs from audited inputs or release safeguards')
    return candidate['summary']


def write_candidate(root=ROOT):
    root = Path(root)
    candidate = build_candidate(root)
    first,second=candidate['structured']['batches']
    old_receipt=root/'knowledge_sources/v3/remediation/structured-receipt-01.json'
    if old_receipt.exists() and read(old_receipt)['batch_sha256']!=first['batch_sha256']:
        raise ValueError('First batch historical receipt changed; refuse to overwrite completed work')
    folder = root / 'mock_data' / VERSION
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / 'candidate.json', candidate)
    write(folder / 'structured-graph.json', candidate['structured']['graph'])
    write(folder / 'structured-graph-01.json',first['graph'])
    if not old_receipt.exists():
        write(old_receipt,dict(batch_id=first['batch_id'],batch_sha256=first['batch_sha256'],
            operations=first['changes'],first_graph_sha256=digest(first['graph']),
            scope='reproduced_first_batch_snapshot_not_historical_activation'))
    write(root / 'knowledge_sources/v3/remediation/structured-receipt-02.json',
          dict(batch_id=second['batch_id'],
               batch_sha256=second['batch_sha256'],
               candidate_sha256=digest(candidate),
               operations=second['changes'],
               counts_by_operation=second['counts_by_operation']))
    summary = candidate['summary']
    write(root / 'knowledge_sources/v3/remediation/progress.json', dict(summary, candidate_sha256=digest(candidate)))
    # Values are escaped and the filter only reads textContent. No original source markup executes.
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    drafts = {r['item_id']: r for r in candidate['replacement_drafts']}
    for uid, action in candidate['actions'].items():
        detail = drafts.get(uid, action.get('supplement', {}))
        rows.append('<tr><td>' + esc(uid) + '</td><td>' + esc(action['summary']) + '</td><td>' +
                    esc(action['status']) + '</td><td>' + esc(action['action']) + '</td><td><pre>' +
                    esc(json.dumps(detail, ensure_ascii=False, indent=2)) + '</pre></td></tr>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>图谱候选处置台账</title>
<style>body{font:15px system-ui;background:#f5f7fa;color:#203044;margin:32px}h1{font-size:24px}
input{padding:12px;width:min(700px,90%);margin:16px 0}table{border-collapse:collapse;width:100%;background:white}
td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}pre{white-space:pre-wrap;max-width:600px;max-height:280px;overflow:auto;font-size:13px}td:first-child{word-break:break-all;max-width:200px}</style>
<h1>知识图谱候选版 · 处置台账</h1><p>离线候选，尚未发布。旧断言停用不等于新结论审核通过。临床专家未审核。</p>
<p>399条安全处置；55条补查；13条隔离；新增自动推理规则：0。</p>
<input id="q" placeholder="搜索药物、疾病、状态或处置说明"><table><thead><tr><th>记录</th><th>内容</th><th>原审核</th><th>候选处置</th><th>修订草案 / 补查详情</th></tr></thead><tbody>'''
    page += ''.join(rows) + '''</tbody></table><script>document.getElementById('q').addEventListener('input',e=>{
const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></html>'''
    (root / 'docs/KNOWLEDGE-GRAPH-V3-REMEDIATION.html').write_text(page, encoding='utf-8')
    # A short before/after register, separate from the unapplied clinical proposals.
    short_rows=[]
    records={r['id']:r for r in candidate['structured']['clinical_records']}
    for uid,result in candidate['structured']['changes'].items():
        detail=copy.deepcopy(result)
        if 'record_ids' in detail:
            detail['records']=[records[rid] for rid in detail.pop('record_ids')]
        short_rows.append('<tr><td>'+esc(candidate['actions'][uid]['summary'])+'</td><td><pre>'+
            esc(json.dumps(detail,ensure_ascii=False,indent=2))+'</pre></td></tr>')
    structured_page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>首批结构化修订对照</title>
<style>body{font:15px system-ui;background:#f5f7fa;color:#203044;margin:32px}h1{font-size:24px}
input{padding:12px;width:min(700px,90%);margin:16px 0}table{border-collapse:collapse;width:100%;background:white}
td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}
pre{white-space:pre-wrap;max-height:380px;overflow:auto;font-size:13px}</style>
<h1>首批结构化修订 · 修改前后对照</h1><p>离线候选；临床专家未审核；当前运行版没有切换。</p>'''
    structured_page+='<p>已应用候选编辑：'+str(summary['structured_items_applied'])+'项；待结构化：'+str(summary['remaining_structured_items'])+'项。</p>'
    structured_page+='''<input id="q" placeholder="搜索药物、编码、病程或关系"><table><thead><tr><th>原条目</th><th>实际编辑及证据</th></tr></thead><tbody>'''
    structured_page+=''.join(short_rows)+'''</tbody></table><script>document.getElementById('q').addEventListener('input',e=>{
const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></html>'''
    structured_page=structured_page.replace('首批结构化修订','全量结构化处置')
    (root/'docs/KNOWLEDGE-GRAPH-V3-STRUCTURED-ALL.html').write_text(structured_page,encoding='utf-8')
    return summary
