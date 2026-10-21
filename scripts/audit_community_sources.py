"""Offline source mapping audit. Success is structural, never medical approval."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'agent'))
from core.public_support import KB, sections, knowledge_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = sections()  # Fails on unknown mappings, missing audit, URL drift or stale overrides.
    sources = {s['id']: s for r in rows for s in r['sources']}
    overrides = json.loads((KB/'section_overrides.json').read_text(encoding='utf-8'))
    report = dict(knowledge_version=knowledge_version(), documents=len({r['doc_id'] for r in rows}),
                  sections=len(rows), sources=len(sources),
                  source_status_counts=dict(Counter(s['status'] for s in sources.values())),
                  source_scope_checks=list(sources.values()), clinical_approval=False,
                  scoped_summary_overrides=sum(len(v) for v in overrides.values()),
                  imported_documents_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                             for p in sorted((KB/'community_mental_health').glob('*.md'))},
                  note='Structural and assisted source-scope checks only. Raw imported metadata is retained as provenance, not current clinical approval. One portal fetch is blocked; two policy sources use official search/reprint evidence, not live service verification.')
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in {'source_scope_checks', 'imported_documents_sha256'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
