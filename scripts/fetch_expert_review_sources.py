"""Cache bounded primary supplements for expert handoff, without changing original verdicts."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
PMIDS=['24921233','9742515','36072169','18232726']


def fetch():
    folder=ROOT/'.tools/knowledge_sources/v3/expert-round';folder.mkdir(parents=True,exist_ok=True)
    target=ROOT/'knowledge_sources/v3/expert';target.mkdir(parents=True,exist_ok=True)
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id='+','.join(PMIDS)
    file=folder/'abstracts.xml'
    if not file.exists():
        with urlopen(Request(url,headers={'User-Agent':'PsyConsult-evidence-review/1.0'}),timeout=40) as r:raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Oversize NLM response')
        ET.fromstring(raw);file.write_bytes(raw)
    raw=file.read_bytes();tree=ET.fromstring(raw);sources={}
    for article in tree.findall('PubmedArticle'):
        pmid=article.findtext('MedlineCitation/PMID')
        if pmid not in PMIDS:continue
        abstract=' '.join(''.join(t.itertext()) for t in article.findall('.//AbstractText'))
        if not abstract:raise ValueError('Missing original abstract: '+pmid)
        sid='expert_pmid_'+pmid
        sources[sid]=dict(id=sid,url='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',
            retrieval_url=url,title=''.join(article.find('.//ArticleTitle').itertext()),
            region='study_specific',format='xml',source_kind='primary_author_abstract',availability='available',
            full_article_reviewed=False,locator=dict(pmid=pmid),local_snapshot=file.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(raw).hexdigest(),expert_review='pending')
        print(pmid,abstract,flush=True)
    if len(sources)!=len(PMIDS):raise ValueError('Incomplete primary response')
    # A guideline is a separate context; not proof of a universal treatment order.
    sid='expert_nice_ng10';url='https://www.nice.org.uk/guidance/ng10/chapter/Recommendations'
    file=folder/'nice-ng10.html'
    try:
        if not file.exists():
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:raw=r.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('Oversize guideline')
            file.write_bytes(raw)
        raw=file.read_bytes()
        if b'lorazepam' not in raw:raise ValueError('Guideline text missing')
        sources[sid]=dict(id=sid,url=url,title='NICE NG10 rapid tranquillisation recommendations',
            region='UK',format='html',source_kind='guideline',availability='available',local_snapshot=file.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(raw).hexdigest(),expert_review='pending')
    except Exception as exc:
        sources[sid]=dict(id=sid,url=url,availability='unavailable',error=type(exc).__name__,expert_review='pending')
    prior=target/'sources.json'
    if prior.exists():
        old=json.loads(prior.read_text('utf-8'))
        for sid,row in old.items():
            if row.get('sha256') and sources.get(sid,{}).get('sha256')!=row['sha256']:
                raise ValueError('Sealed supplemental source changed: '+sid)
    prior.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n','utf-8')
    return sources


if __name__=='__main__':fetch()
