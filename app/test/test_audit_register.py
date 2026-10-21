from html.parser import HTMLParser
from pathlib import Path
from scripts.export_graph_audit import render_register

class Details(HTMLParser):
    def __init__(self):super().__init__();self.count=0
    def handle_starttag(self,tag,attrs):
        if tag=='details' and dict(attrs).get('class')=='item':self.count+=1

def test_register_exports_all_frozen_items_once():
    root=Path(__file__).resolve().parents[2]
    parser=Details();parser.feed((root/'docs/KNOWLEDGE-GRAPH-V3-REGISTER.html').read_text('utf-8'))
    assert parser.count==899

def test_register_escapes_original_values_and_does_not_execute_them():
    malicious='<img src=x onerror="alert(1)">'
    inventory={'item':dict(summary=malicious,priority='P0',original={'value':malicious})}
    reviews={'item':dict(status='insufficient_evidence',reason=malicious,expert_review='pending',evidence_ids=[],reviewed_at='2026-10-20')}
    rendered=render_register(inventory,reviews,{}, {})
    assert malicious not in rendered
    assert '&lt;img' in rendered and '&quot;alert(1)&quot;' in rendered
    parser=Details();parser.feed(rendered)
    assert parser.count==1
