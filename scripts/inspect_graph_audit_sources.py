"""Offline extract exact recommendation anchors; downloaded original HTML stays gitignored."""
import json,sys,hashlib
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.audit import read

class Recommendations(HTMLParser):
    def __init__(self):
        super().__init__();self.depth=0;self.current=None;self.parts=[];self.sections={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='article':
            if self.current: self.depth+=1
            elif 'recommendation' in a.get('class','').split(): self.current=a['id'];self.depth=1;self.parts=[]
        if self.current and tag in ('p','li','h5','h6'):self.parts.append('\n')
    def handle_data(self,value):
        if self.current:self.parts.append(value)
    def handle_endtag(self,tag):
        if tag=='article' and self.current:
            self.depth-=1
            if not self.depth:
                self.sections[self.current]='\n'.join(line.strip() for line in ''.join(self.parts).splitlines() if line.strip())
                self.current=None

def extract():
    for sid,source in read(ROOT/'knowledge_sources/v3/catalog.json').items():
        if source.get('availability')!='available' or source['format']!='html':continue
        path=ROOT/source['local_snapshot'];raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==source['sha256']
        parser=Recommendations();parser.feed(raw.decode('utf-8'))
        assert parser.sections,'No actual recommendation content: '+sid
        path.with_suffix('.sections.json').write_text(json.dumps(parser.sections,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(sid,len(parser.sections),'original recommendation anchors')

if __name__=='__main__': extract()
