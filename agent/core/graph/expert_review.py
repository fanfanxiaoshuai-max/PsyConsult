"""Evidence traceability recheck and unsigned expert handoff; never clinical certification."""
import hashlib
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from .audit import ROOT,read,write,digest
from .remediation import validate_candidate

STATUS_LABELS={'amended':'已修订 · 待专家审核','source_supported':'原文有条件支持',
    'insufficient_evidence':'依据不足','quarantined':'隔离','structural_only':'仅结构一致'}


def source_title(sid,source):
    if source.get('title'):return source['title']
    names={'us_venlafaxine_er':'文拉法辛缓释胶囊 · 美国标签','us_duloxetine':'度洛西汀迟释胶囊 · 美国标签',
        'us_aripiprazole':'阿立哌唑 · 美国标签','us_risperidone':'利培酮 · 美国标签',
        'us_quetiapine':'喹硫平普通片 · 美国标签','us_lamotrigine_generic':'拉莫三嗪 · 所核美国标签',
        'uk_sodium_valproate':'Epilim丙戊酸钠肠溶片 · 英国SmPC',
        'us_olanzapine_lai':'ZYPREXA RELPREVV长效肌注制剂 · 美国标签',
        'us_paliperidone_lai':'帕利哌酮长效制剂 · 所核美国标签','us_risperidone_lai':'利培酮长效制剂 · 所核美国标签',
        'nice_rtms_ocd':'NICE · OCD重复经颅磁刺激建议','nice_dbs_ocd_htg577':'NICE HTG577 · OCD深部脑刺激建议',
        'who_atc_benzodiazepines':'WHO ATC · 苯二氮卓类分类'}
    if sid.startswith('who_icd10_'):return 'WHO ICD-10 2019 · '+sid.removeprefix('who_icd10_').replace('_','.')
    return names.get(sid,source.get('drug') or sid)


def supplemental_findings(reviews,inventory,sources):
    """All original open items remain open. New papers cannot silently promote them."""
    notes={
        'relation:7efcc9ce0710295737b50093':(['expert_pmid_24921233','expert_pmid_9742515'],
            '病例报告提供舍曲林与丙戊酸相关的风险信号；其中一篇还合用利培酮。摘要不能确定全部制剂、发生率、具体机制或普遍因果。',
            'case_report_signal_only'),
        'relation:0e7ad968542880407cddfb87':(['expert_pmid_36072169'],
            '新增喹硫平后出现综合征的病例同时涉及舍曲林和曲唑酮；不能从多药个案隔离为任意喹硫平—舍曲林组合的确定效应。',
            'confounded_case_report_only'),
    }
    for uid in ['relation:30839551104abb739dff0abe','relation:fd9d051b51eb529d2d975459','relation:a869d1c0251ffa70e8dad203']:
        available=sources.get('expert_nice_ng10',{}).get('availability')=='available'
        notes[uid]=(['expert_nice_ng10'] if available else [],
            '快速镇静指南中的特定肌注药物和激越情境，不等于精神分裂症、躁狂或全部急性治疗的通用二线排序。原断言继续不启用。',
            'specific_acute_context_not_general_second_line')
    for uid in ['relation:b3798c9846a8bf13b3f4e523','relation:92224e3d66cab22b56496279']:
        notes[uid]=(['expert_pmid_18232726'],
            '本轮查到的是氯氮平与奥氮平的比较试验，不是两药联合试验；不能用其证明合用无适应证、无风险或确定相互作用。',
            'comparison_does_not_answer_combination_claim')
    result={}
    for uid,row in reviews.items():
        if row['status'] not in {'insufficient_evidence','quarantined'}:continue
        ids,note,outcome=notes.get(uid,([],row['reason'],
            'retain_isolation' if row['status']=='quarantined' else 'bounded_prior_evidence_reexamined'))
        result[uid]=dict(item_id=uid,summary=inventory[uid]['summary'],original_status=row['status'],
            additional_source_ids=ids,conclusion=note,outcome=outcome,
            original_claim_enabled=False,expert_review='pending',
            next_step=('确认具体端点、制剂及范围后按新记录重建，或继续隔离。' if row['status']=='quarantined'
                       else '专家评估证据适用性；不足时保留停用，不把病例、类别或比较研究泛化。'))
    if len(result)!=68:raise ValueError('Original open scope changed')
    return result


def validate_supplement_sources(root,sources):
    for sid,source in sources.items():
        if source.get('availability')=='unavailable':continue
        path=(root/source['local_snapshot']).resolve()
        if not path.is_relative_to((root/'.tools/knowledge_sources').resolve()):raise ValueError('Source outside cache')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Expert source changed: '+sid)
        if source['format']=='xml':
            articles=ET.fromstring(raw).findall('PubmedArticle')
            if not any(a.findtext('MedlineCitation/PMID')==source['locator']['pmid'] and a.findall('.//AbstractText') for a in articles):
                raise ValueError('Primary abstract missing: '+sid)
        elif source['format']=='html' and b'lorazepam' not in raw:raise ValueError('Guideline text missing')


def build_packet(root=ROOT):
    b=root/'knowledge_sources/v3'
    candidate=read(root/'mock_data/kg_v3_candidate/candidate.json');validate_candidate(candidate,root)
    inventory=read(b/'inventory.json');reviews=read(b/'reviews.json');evidence=read(b/'evidence.json')
    sources=read(b/'catalog.json');supp_sources=read(b/'expert/sources.json')
    validate_supplement_sources(root,supp_sources)
    findings=supplemental_findings(reviews,inventory,supp_sources)
    prior=read(b/'remediation/rechecks.json')['items']
    extra_index=dict(read(b/'remediation/sources.json'),**supp_sources)
    rows=[]
    for uid,item in inventory.items():
        review=reviews[uid];change=candidate['structured']['changes'].get(uid)
        proofs=[]
        for eid in review.get('evidence_ids',[]):
            p=evidence[eid];s=sources[p['source_id']]
            proofs.append(dict(evidence_id=eid,source_id=p['source_id'],url=s['url'],
                source_title=source_title(p['source_id'],s),region=s['region'],
                edition=s.get('label_revision',s.get('edition')),sha256=s['sha256'],
                locator=p['locator'],finding=p['summary'],conditions=p['conditions']))
        additional_ids=set((findings.get(uid) or {}).get('additional_source_ids',[]))|set((prior.get(uid) or {}).get('source_ids',[]))
        additional_sources=[]
        for sid in sorted(additional_ids):
            s=extra_index[sid]
            additional_sources.append(dict(id=sid,title=s.get('title') or ('原作者摘要 · '+sid if 'pmid' in sid else sid),
                url=s.get('landing_url',s['url']),region=s['region'],sha256=s.get('sha256'),
                scope=s.get('scope','仅该来源的限定情境'),full_article_reviewed=s.get('full_article_reviewed',False) if 'pmid' in sid else None))
        rows.append(dict(item_id=uid,kind=item['kind'],summary=item['summary'],
            medical_review_required=item['medical_review_required'],original_status=review['status'],
            status_label=STATUS_LABELS[review['status']],original= item['original'],original_sha256=item['original_sha256'],
            review_sha256=digest(review),reason=review['reason'],candidate_change=change,evidence=proofs,
            supplemental_review=findings.get(uid),prior_supplement=prior.get(uid),
            additional_sources=additional_sources,
            expert_review='pending' if item['medical_review_required'] else 'not_applicable',
            expert_decision=None,expert_name=None,expert_comment=None,
            questions=(['核对缺失端点及含义；不得自动补造。','确认继续隔离或提出带来源的新记录。'] if review['status']=='quarantined' else
                       ['核对精确断言、来源版本、地区、人群及制剂条件。','确认结构化结果与临床原文一致；不足时保留停用。'])))
    supported={r['item_id'] for r in rows if r['original_status']=='amended'}
    if supported!=set(candidate['structured']['changes']):raise ValueError('Candidate/expert coverage mismatch')
    summary=dict(total_items=len(rows),medical_items=sum(r['medical_review_required'] for r in rows),
        amended_items_rechecked=len(supported),open_items_reexamined=len(findings),
        original_status_counts=dict(Counter(r['original_status'] for r in rows)),
        candidate_sha256=digest(candidate),expert_approved=0,clinical_certification=False,
        activation_ready=False,review_kind='source_traceability_and_candidate_consistency',
        supplemental_sources_available=sum(s.get('availability')!='unavailable' for s in supp_sources.values()))
    return dict(version='expert-handoff-01',generated_on=str(date.today()),summary=summary,
        instructions='本包未签署；原文核对和软件验收不是临床专业审核。请逐项填写专家结论、姓名和意见；原始JSON保留不覆盖。',
        supplemental_sources={sid:{k:v for k,v in s.items() if k not in {'local_snapshot','retrieval_url'}} for sid,s in supp_sources.items()},
        rows=rows)


def write_packet(root=ROOT):
    packet=build_packet(root);folder=root/'knowledge_sources/v3/expert';folder.mkdir(parents=True,exist_ok=True)
    write(folder/'packet.json',packet)
    write(folder/'recheck-report.json',dict(packet['summary'],packet_sha256=digest(packet)))
    return packet['summary']
