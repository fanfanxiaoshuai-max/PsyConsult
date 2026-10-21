"""Cache explicitly selected primary supplements; do not alter sealed audit reviews."""
import hashlib,json,sys
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
PUBMED=['9627209','22426846','15257068','21739267','10920469','22933237','19698511','34787653','20015461','18725912','36350591','20092882','18832427','14709947','10327910']
LABELS={
    'us_sertraline_supplement':'e1864a7e-44b9-4399-9554-0c18b46fbdd6',
    'us_ziprasidone_supplement':'ccfd5ba2-7271-f3dd-4c98-7418c1a4b54a',
    'us_buspirone_supplement':'a9bb9216-3dac-4e8a-9df9-f72c2eaef160',
    'us_hydrochlorothiazide_supplement':'9e6a0c83-1494-44ca-90e0-3f43fa8ec746',
}
SMPC={'uk_clozapine_supplement':'10290','uk_fluvoxamine_supplement':'1169'}

def main():
    folder=ROOT/'.tools/knowledge_sources/v3/remediation';folder.mkdir(parents=True,exist_ok=True)
    target=ROOT/'knowledge_sources/v3/remediation';target.mkdir(parents=True,exist_ok=True)
    sources={}
    for pmid in PUBMED:sources['pmid_'+pmid]=dict(url='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',region='study_specific',source_kind='primary_article_abstract',scope='Original author abstract indexed by PubMed; full article not reviewed')
    for sid,key in LABELS.items():sources[sid]=dict(url='https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid='+key+'&type=display',region='US',source_kind='product_label',scope='US specific product only, not Chinese approval')
    for sid,key in SMPC.items():sources[sid]=dict(url='https://www.medicines.org.uk/emc/product/'+key+'/smpc',region='UK',source_kind='manufacturer_smpc',scope='UK specific product, not Chinese approval')
    prior=json.loads((target/'sources.json').read_text('utf-8-sig')) if (target/'sources.json').exists() else {}
    def fetch(pair):
        sid,meta=pair;file=folder/(sid+'.html');row=dict(meta,id=sid,expert_review='pending')
        # Preserve the official NLM XML fallback when the landing page is blocked.
        cached=prior.get(sid,{})
        if cached.get('availability')=='available' and cached.get('format')=='xml':
            snapshot=ROOT/cached['local_snapshot']
            if snapshot.is_file() and hashlib.sha256(snapshot.read_bytes()).hexdigest()==cached['sha256']:
                return sid,cached
        try:
            if file.exists():raw=file.read_bytes()
            else:
                with urlopen(Request(meta['url'],headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as response:raw=response.read(3_000_001)
                if len(raw)>3_000_000:raise ValueError('Oversize original')
                file.write_bytes(raw)
            if sid.startswith('pmid_') and b'id="abstract"' not in raw:raise ValueError('No original abstract; possibly access challenge')
            sha=hashlib.sha256(raw).hexdigest()
            if prior.get(sid,{}).get('sha256') and prior[sid]['sha256']!=sha:raise ValueError('Previously cached source changed')
            row.update(availability='available',retrieved_at='2026-10-20',sha256=sha,local_snapshot=file.relative_to(ROOT).as_posix())
        except Exception as exc:row.update(availability='unavailable',error=type(exc).__name__)
        print(sid,row['availability'],flush=True)
        return sid,row
    with ThreadPoolExecutor(4) as pool:results=dict(pool.map(fetch,sources.items()))
    if any(results['pmid_'+pmid]['availability']!='available' for pmid in PUBMED):
        # Official NLM API, same papers, not a third-party summary or access bypass.
        url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id='+','.join(PUBMED)
        file=folder/'primary-abstracts.xml'
        if not file.exists():
            with urlopen(Request(url,headers={'User-Agent':'PsyConsult-source-audit/1.0'}),timeout=45) as response:raw=response.read(3_000_001)
            if len(raw)>3_000_000:raise ValueError('Oversize NLM response')
            ET.fromstring(raw);file.write_bytes(raw)
        raw=file.read_bytes();tree=ET.fromstring(raw);sha=hashlib.sha256(raw).hexdigest()
        for article in tree.findall('PubmedArticle'):
            pmid=article.findtext('MedlineCitation/PMID');sid='pmid_'+str(pmid)
            if sid not in results or article.find('MedlineCitation/Article/Abstract') is None:continue
            row=results[sid]
            if row['availability']=='available':continue
            row.update(failed_html_url=row['url'],landing_url='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',url=url,
                availability='available',format='xml',locator={'kind':'pubmed_article','pmid':pmid},
                sha256=sha,local_snapshot=file.relative_to(ROOT).as_posix(),retrieved_at='2026-10-20')
            row.pop('error',None)
    (target/'sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
