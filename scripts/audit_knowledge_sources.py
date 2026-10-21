"""Verify downloaded source bytes and page locators; uses optional pypdf for source auditing only."""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]

def audit():
    catalog=json.loads((ROOT/'knowledge_sources/catalog.json').read_text(encoding='utf-8'))
    records=list(json.loads((ROOT/'knowledge_sources/evidence.json').read_text(encoding='utf-8')).values())
    proofs=[]
    for doc in catalog:
        if not doc.get('used_for_claims'):
            assert not any(e['source_id']==doc['id'] for e in records)
            proofs.append(dict(id=doc['id'],used_for_claims=False,availability=doc['availability']))
            continue
        path=ROOT/doc['local_snapshot']
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual==doc['sha256'],doc['id']+' changed; do not silently trust a revised PDF'
        pages=PdfReader(path).pages
        selected=sorted({p for e in records if e['source_id']==doc['id'] for p in e['pages']})
        assert selected and all(1<=p<=len(pages) for p in selected)
        proofs.append(dict(id=doc['id'],sha256=actual,pdf_pages=len(pages),cited_pages=selected,method='agent visual scan reading' if doc['id']=='cn_paroxetine_hospital' else 'agent text extraction and page inspection',expert_review='pending',source_bytes_verified=True))
    report=dict(checked_at='2026-10-19',source_records=proofs,evidence_count=len(records),expert_reviewed=False)
    (ROOT/'knowledge_sources/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Verified source bytes, page bounds, and unavailable-source exclusion:',len(records),'records')

if __name__=='__main__': audit()
