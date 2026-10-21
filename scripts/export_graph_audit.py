"""Export every frozen audit item to a searchable, offline HTML review register."""
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read,validate_audit

STATUS={'source_supported':'有条件支持','amended':'需修订（候选）','insufficient_evidence':'依据不足','quarantined':'继续隔离','structural_only':'仅结构一致','pending_review':'尚待对照','conflicting':'依据有分歧','unavailable_source':'原文不可得'}

def render_register(inventory,reviews,evidence,catalog):
    counts=Counter(r['status'] for r in reviews.values())
    options=''.join('<option value="'+escape(k,quote=True)+'">'+escape(v)+'（'+str(counts[k])+'）</option>' for k,v in STATUS.items() if counts[k])
    cards=''.join('<span>'+escape(STATUS.get(k,k))+' <b>'+str(v)+'</b></span>' for k,v in counts.items())
    rows=[]
    for n,(uid,item) in enumerate(inventory.items(),1):
        row=reviews[uid];status=row['status'];proof=[]
        for eid in row.get('evidence_ids',[]):
            claim=evidence[eid];source=catalog[claim['source_id']];loc=claim['locator']
            position=('PDF物理页 '+','.join(map(str,loc['pages']))) if loc['kind']=='pdf_pages' else '原文锚点 '+', '.join(loc['anchors'])
            proof.append('<li><a target="_blank" rel="noreferrer" href="'+escape(source['url'],quote=True)+'">'+escape(claim['source_id'])+'</a> · '+escape(source['region'])+' · '+escape(position)+'<p>'+escape(claim['summary'])+'</p><p>限制：'+escape(claim['conditions'])+'</p><small>证据 '+escape(eid)+' · SHA256 '+escape(claim['source_sha256'])+'</small></li>')
        proposal=row.get('proposed_change',row.get('candidate_disposition'))
        change='<h3>候选处理</h3><pre>'+escape(json.dumps(proposal,ensure_ascii=False,indent=2))+'</pre>' if proposal else ''
        rows.append('<details class="item" data-status="'+escape(status,quote=True)+'"><summary><span class="number">'+str(n)+'</span> <b>'+escape(STATUS.get(status,status))+'</b> '+escape(item['summary'])+'</summary><div class="body"><small>'+escape(uid)+' · '+escape(item['priority'])+'</small><p>'+escape(row['reason'])+'</p><p>'+escape(row.get('comparison_scope','按该项原始值及证据中的版本、地区、人群和条件解释；不是专家审核。'))+'</p><h3>原始记录</h3><pre>'+escape(json.dumps(item['original'],ensure_ascii=False,indent=2))+'</pre>'+change+'<h3>证据与限制</h3><ul>'+''.join(proof)+'</ul><p>原文对照：'+escape(str(row.get('reviewed_at') or '尚未完成'))+'；临床专家审核：待审。</p></div></details>')
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PsyConsult 全量核验台账</title>
<style>body{font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif;background:#f4f6f8;color:#20313d;margin:0}main{max-width:1100px;margin:auto;padding:30px 22px}h1{font-size:27px}header{background:white;border:1px solid #dbe3e8;border-radius:12px;padding:22px}header p{margin:10px 0}#counts{display:flex;gap:10px;flex-wrap:wrap}#counts span{background:#edf3f6;padding:6px 12px;border-radius:6px}.controls{display:flex;gap:12px;margin:22px 0;flex-wrap:wrap}input,select{font:inherit;padding:10px;border:1px solid #b8c7d0;border-radius:6px}input{flex:1;min-width:240px}.item{background:white;border:1px solid #dbe3e8;border-radius:8px;margin:9px 0}.item[hidden]{display:none}summary{padding:14px;cursor:pointer}.number{color:#6b7e8b;margin-right:8px}summary b{display:inline-block;min-width:145px;font-size:13px;color:#275368}.body{padding:0 22px 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:12px;border-radius:6px;font-size:12px}small{color:#566d7c;overflow-wrap:anywhere}h3{font-size:16px}li{margin:14px 0}li p{margin:4px 0}a{color:#17658a}</style>
<main><header><h1>PsyConsult 知识图谱全量核验台账</h1><p>固定范围899项：230个实体、250个属性、406条关系、13条隔离记录。实体身份与每个医学属性分别审查。</p><p><b>逐项检查有结论 ≠ 所有主张已获支持。</b>本页为原文对照及候选处理台账；临床专家审核全部待审，399项修订尚未应用，运行系统仍为kg_v2。</p><div id="counts">'''+cards+'''</div></header><div class="controls"><input id="query" type="search" aria-label="搜索完整台账" placeholder="搜索名称、编号、理由或来源"><select id="status" aria-label="按核验结论筛选"><option value="">全部结论</option>'''+options+'''</select><span id="visible"></span></div>'''+''.join(rows)+'''</main><script>const entries=[...document.querySelectorAll('.item')].map(el=>({el,text:el.textContent.toLocaleLowerCase()}));const q=document.querySelector('#query'),s=document.querySelector('#status');function filter(){const query=q.value.trim().toLocaleLowerCase();let count=0;for(const row of entries){row.el.hidden=!!((s.value&&row.el.dataset.status!==s.value)||(query&&!row.text.includes(query)));if(!row.el.hidden)count++}document.querySelector('#visible').textContent=count+' / '+entries.length+' 项'}q.addEventListener('input',filter);s.addEventListener('change',filter);filter();</script></html>'''

    return document.replace('399项修订',str(counts['amended'])+'项修订')

def export(root=ROOT):
    root=Path(root);base=root/'knowledge_sources/v3'
    inventory,reviews=validate_audit(root)
    evidence=read(base/'evidence.json');catalog=read(base/'catalog.json')
    html=render_register(inventory,reviews,evidence,catalog)
    target=root/'docs/KNOWLEDGE-GRAPH-V3-REGISTER.html'
    target.write_text(html,encoding='utf-8')
    lines=['# 依据不足与隔离记录','', '日期：2026-10-20。下列条目均已在指定原文范围内检查，但尚不能作为充分支持的自动推理规则。依据不足不表示主张相反或相关联用安全；隔离记录不直接导入。','']
    for status,title in [('insufficient_evidence','依据不足'),('quarantined','继续隔离')]:
        selected=[(uid,item,reviews[uid]) for uid,item in inventory.items() if reviews[uid]['status']==status]
        lines.extend(['## '+title+'（'+str(len(selected))+'项）',''])
        for uid,item,row in selected:
            lines.extend(['### '+item['summary'],'','- 编号：`'+uid+'`','- 优先级：'+item['priority'],'- 结论：'+row['reason'],'- 处理：'+row.get('candidate_disposition','不启用未经充分支持的自动规则；保留原记录和证据。'),''])
            for eid in row.get('evidence_ids',[]):
                claim=evidence[eid]
                source=catalog[claim['source_id']]
                loc=claim['locator'];position=('PDF物理页 '+','.join(map(str,loc['pages']))) if loc['kind']=='pdf_pages' else '原文锚点 '+', '.join(loc['anchors'])
                lines.extend(['来源：['+claim['source_id']+']('+source['url']+')；'+position+'。','限制：'+claim['conditions'],''])
    (root/'docs/KNOWLEDGE-GRAPH-V3-OPEN-ITEMS.md').write_text('\n'.join(lines),encoding='utf-8')
    return target

if __name__=='__main__':print(export())
