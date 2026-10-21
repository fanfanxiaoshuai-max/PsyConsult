"""Render v2 drug review from scoped records; never invent clinical instructions."""
import html
import json
from urllib.parse import urlsplit


def render_chat_review(payload):
    """Brief chat view; the complete scoped records remain in knowledge details/export."""
    try:
        result=json.loads(payload) if isinstance(payload,str) else payload
    except (TypeError,ValueError):result={}
    if not isinstance(result,dict) or not result.get('version'):
        return '药物资料暂时无法检索，本次未完成审查，请稍后重试。'
    drugs=list(dict.fromkeys(e['name'] for e in result.get('candidates',[]) if e.get('label')=='Drug'))
    pair=result.get('pair_query',False) or len(drugs)>=2
    records=[r for r in result.get('records',[]) if r.get('project_review')=='approved' and r.get('reasoning_eligible')]
    if pair:
        # Single medicine/background records cannot answer a specific medicine-pair question.
        records=[r for r in records if r.get('subject_name') in drugs and r.get('related_name') in drugs
                 and r['subject_name']!=r['related_name']]
    if not result['version'].startswith('project-'):
        context=result.get('class_context',{})
        explicit_classes={e['id'] for e in result.get('candidates',[]) if e.get('label')=='DrugClass'}
        edges=[e for e in result.get('edges',[])+[e for e in context.get('edges',[]) if e['target'] in explicit_classes] if e.get('reasoning_eligible') is True
               and e.get('evidence',{}).get('source_review')=='source_checked_by_agent']
        nodes={e['id']:e for e in result.get('nodes',[])+context.get('nodes',[])}
        if pair:
            edges=[e for e in edges if nodes.get(e['source'],{}).get('name') in drugs and
                   (nodes.get(e['target'],{}).get('name') in drugs or e['target'] in explicit_classes)]
        records=[dict(title=e['evidence']['summary']+' '+e['evidence'].get('action',''),
                      subject_name=nodes.get(e['source'],{}).get('name','')+' → '+nodes.get(e['target'],{}).get('name',''),
                      context={},evidence=[dict(scope_conditions='；'.join(e['evidence'].get(k,'') for k in ('conditions','population','formulation','region')))]) for e in edges]
    heading='## 药物资料审查\n\n'+('**'+text('与'.join(drugs))+'**\n\n' if drugs else '')
    if not records:
        return heading+('当前启用知识版本未收录这组药物的直接相互作用记录，不能据此判断可安全合用。建议由医生或药师结合具体说明书、剂量和其他用药进一步核对。' if pair else '当前启用知识版本未找到与本问题相符的药物记录，请补充具体药名或缩小查询范围。')
    out=[]
    seen=set()
    for record in records:
        title=record['title'].strip()
        if title in seen:continue
        seen.add(title)
        label=record.get('subject_name','')
        out.append('- '+(text(label)+'：' if label else '')+text(title))
        # Preserve the original scope as plain prose, without serializing internal JSON.
        scopes=list(dict.fromkeys(p.get('scope_conditions','') for p in record.get('evidence',[]) if p.get('scope_conditions')))
        out.extend('  适用范围：'+text(scope) for scope in scopes if scope not in title)
        if len(seen)==3:break
    return heading+'\n\n'.join(out)+'\n\n'+('这里只展示最相关的资料，完整条件与来源可在知识详情查看。' if len(records)>len(seen) else '以上资料需结合实际病史和用药核对，不直接替代个体处方。')

def text(value):
    return html.escape(str(value)).replace('|','\\|').replace('\n',' ')

def render_evidence_report(payload):
    try:
        result=json.loads(payload) if isinstance(payload,str) else payload
    except (TypeError,ValueError):
        result={}
    if not isinstance(result,dict): result={}
    if result.get('version','').startswith('project-'):
        return render_published_report(result)
    if result.get('version')!='kg_v2':
        return '药物资料审查：知识图谱暂时不可用，未完成证据核对；不能据此判断安全。'
    nodes={e['id']:e for e in result.get('nodes',[])+result.get('class_context',{}).get('nodes',[])}
    sources={s['id']:s for s in result.get('sources',[])+result.get('class_context',{}).get('sources',[])}
    drugs=[e['name'] for e in result.get('candidates',[]) if e.get('label')=='Drug']
    out=['## 药物资料审查（kg_v2）','讨论药物：'+('、'.join(map(text,drugs)) or '未匹配到明确药物。')]
    out+=['报告按图谱证据字段生成。原文由程序代理核对，临床专家审核待完成；覆盖有限，未查到记录不能解释为可安全合用。']
    used=[]
    def section(title,edges):
        out.append('### '+title)
        eligible=[e for e in edges if e.get('reasoning_eligible') is True and e.get('evidence',{}).get('source_review')=='source_checked_by_agent']
        if not eligible:
            out.append('未在当前图谱找到已核对的直接证据；不能据此判断安全。')
        for edge in eligible:
            e=edge['evidence'];used.extend(edge.get('source_ids',[]))
            name=lambda uid: text(nodes.get(uid,{}).get('name',uid))
            kind={'CONTRAINDICATED_WITH':'合用禁忌','INTERACTS_WITH':'相互作用警示','REQUIRES_MONITORING':'需要监测','CONTRAINDICATED_IN':'适用状态禁忌'}.get(edge['type'],edge['type'])
            out.extend(['#### '+text(e['id'])+' · '+name(edge['source'])+' → '+name(edge['target'])+'（'+text(kind)+'）',
                        '**证据摘要：** '+text(e['summary']),
                        '**适用条件：** '+text(e['conditions']),
                        '**处理提示：** '+text(e['action']),
                        '**范围：** '+text(e['population'])+'；'+text(e['formulation'])+'；'+('美国标签补充（不代表中国批准范围）' if e['region']=='US' else '中国说明书')+'。'])
    direct=result.get('edges',[])
    section('检索到的直接记录（类别端点保持类别含义）',direct)
    context=result.get('class_context',{})
    if context.get('edges'):
        explicit_classes={e['id'] for e in result.get('candidates',[]) if e.get('label')=='DrugClass'}
        edges=[e for e in context['edges'] if not explicit_classes or e['target'] in explicit_classes]
        section('药物类别警示上下文',edges)
        out.append('这些记录的端点为药物类别；未自动推断类别成员关系，也不构成对所讨论药物对的直接禁忌确认。')
    out.append('### 原始资料')
    for sid in dict.fromkeys(used):
        s=sources.get(sid,{})
        url=s.get('url','')
        if urlsplit(url).scheme!='https': continue
        out.append('- '+text(s.get('pointer',''))+' · ['+text(s.get('title','说明书'))+']('+url+'#page='+str(s.get('pages',[1])[0])+')；修订 '+text(s.get('label_revision',''))+'；PDF第 '+text('、'.join(map(str,s.get('pages',[]))))+' 页；'+text(s.get('publisher',''))+'。')
    out.append('### 覆盖限制')
    out.append('本报告仅转述以上记录；未核实的旧关系和原始剂量属性不作为推理依据。美国标签为补充资料，医院转载扫描件保留来源身份。个体处方、换药和监测计划须由医师结合实际情况决定。')
    if result.get('truncated'): out.append('本次结果已截断，请缩小到具体药物或药物对后再查询。')
    return '\n\n'.join(out)


def render_published_report(result):
    sources={s['id']:s for s in result.get('sources',[])}
    drugs=[e['name'] for e in result.get('candidates',[]) if e.get('label')=='Drug']
    out=['## 药物资料审查',
         '知识版本：'+text(result.get('version_name',result['version']))+'（'+text(result['version'])+'）',
         '讨论药物：'+('、'.join(map(text,drugs)) or '未匹配到明确药物。')]
    def section(title,records):
        out.append('### '+title)
        if not records:out.append('当前版本未找到相应记录；不能据此判断可安全合用。')
        for r in records:
            if r.get('project_review')!='approved' or not r.get('reasoning_eligible'):continue
            out.extend(['#### '+text(r['subject_name'])+(' → '+text(r['related_name']) if r.get('related_name') else ''),
                '**记录编号：** '+text(r['id']),
                '**证据摘要：** '+text(r['title']),
                '**适用条件与参数：** '+text(json.dumps(r['context'],ensure_ascii=False))])
            for p in r['evidence']:
                s=sources.get(p['source_id'],{});url=s.get('url','')
                out.append('**来源范围：** '+text(p.get('scope_conditions','见所绑定原文'))+'；地区 '+text(p['region']))
                if urlsplit(url).scheme=='https':
                    out.append('- ['+text(p.get('source_title') or s.get('title','原文'))+']('+url+')；版本 '+text(p.get('edition') or '以原文为准')+'；定位 '+text(json.dumps(p['locator'],ensure_ascii=False)))
    section('已发布的条件性记录',result.get('records',[]))
    if result.get('context_records'):
        section('单药及类别背景（不构成所问药物对的直接证据）',result['context_records'])
    out.append('### 覆盖范围\n'+text(result['evidence_notice']))
    if result.get('truncated'):out.append('结果已截断，请缩小问题范围。')
    return '\n\n'.join(out)
