"""Build, validate, then atomically import an immutable graph dataset."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.normalizer import write_dataset
from core.graph.validator import validate
from config import get_settings
from neo4j import GraphDatabase

def build(dry_run=False, version='kg_v1'):
    if version == 'kg_v2':
        from core.graph.evidence_dataset import write_dataset_v2
        data=write_dataset_v2()
    elif version == 'kg_v1':
        data=write_dataset()
    else:
        raise ValueError('Unsupported graph version')
    report=validate(data)
    report['pending']=[r for r in data['resolutions'] if r['status']=='pending_review']
    report['resolved_structurally']=[r for r in data['resolutions'] if r['status']=='resolved_structurally']
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    report['digest']=digest
    if dry_run:
        return report
    s=get_settings()
    with GraphDatabase.driver(s.neo4j_uri,auth=(s.neo4j_user,s.neo4j_password)) as driver:
        with driver.session(database=s.neo4j_database) as session:
            for label in ('KGEntity','KGSource'):
                session.run(f'CREATE CONSTRAINT {label.lower()}_version_id IF NOT EXISTS FOR (n:{label}) REQUIRE (n.version,n.id) IS UNIQUE').consume()
            session.run('CREATE CONSTRAINT kg_dataset_version IF NOT EXISTS FOR (n:KGDataset) REQUIRE n.version IS UNIQUE').consume()
            def ingest(tx):
                old=tx.run('MATCH (d:KGDataset {version:$v}) RETURN d.digest AS digest',v=data['version']).single()
                if old and old['digest']!=digest:
                    raise ValueError('Immutable dataset differs: create a new version rather than overwrite it.')
                v=data['version']
                for label,key in [('KGEntity','entities'),('KGSource','sources')]:
                    rows=[dict(id=r['id'],payload=json.dumps(r,ensure_ascii=False)) for r in data[key]]
                    tx.run(f'UNWIND $rows AS row MERGE (n:{label} {{version:$v,id:row.id}}) SET n.payload=row.payload',v=v,rows=rows).consume()
                rows=[dict(r,payload=json.dumps(r,ensure_ascii=False)) for r in data['relations']]
                tx.run('UNWIND $rows AS row MATCH (a:KGEntity {version:$v,id:row.source}), (b:KGEntity {version:$v,id:row.target}) MERGE (a)-[r:KG_LINK {id:row.id}]->(b) SET r.kind=row.type, r.payload=row.payload',v=v,rows=rows).consume()
                count=tx.run('MATCH (a:KGEntity {version:$v})-[r:KG_LINK]->(:KGEntity {version:$v}) RETURN count(r) AS n',v=v).single()['n']
                if count!=len(rows):
                    raise ValueError('Post-import relationship count mismatch')
                tx.run('MERGE (d:KGDataset {version:$v}) SET d.ready=true,d.digest=$digest,d.report=$report',v=v,digest=digest,report=json.dumps(report,ensure_ascii=False)).consume()
            session.execute_write(ingest)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--version', choices=['kg_v1','kg_v2'], default='kg_v1')
    args=parser.parse_args()
    print(json.dumps(build(args.dry_run, args.version),ensure_ascii=False,indent=2))
