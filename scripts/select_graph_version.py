"""Validate a graph before updating KG_VERSION in the local ignored .env. Restart backend afterwards."""
import argparse
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.repository import GraphRepository
from core.graph.release import require_released_version

def select(version):
    require_released_version(version)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',version):
        raise ValueError('Invalid version')
    entities=GraphRepository(version).entities()
    if not entities:
        raise ValueError('Refusing to activate an empty graph')
    path=ROOT/'agent/.env'
    text=path.read_text(encoding='utf-8-sig')
    line='KG_VERSION='+version
    text=re.sub(r'^KG_VERSION=.*$',line,text,flags=re.M) if re.search(r'^KG_VERSION=',text,re.M) else text.rstrip()+'\n'+line+'\n'
    temporary=path.with_suffix('.env.tmp')
    temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)
    print('Selected graph:',version,'; restart backend to apply. No other settings displayed.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('version',choices=['legacy','kg_v1','kg_v2'])
    select(p.parse_args().version)
