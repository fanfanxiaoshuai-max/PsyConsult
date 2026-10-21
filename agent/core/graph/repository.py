"""Read-only graph access. Versioned entities never mix with legacy nodes."""
import json
from neo4j import GraphDatabase, READ_ACCESS
from threading import RLock

_drivers = {}
_driver_lock = RLock()

def close_graph_connections():
    with _driver_lock:
        for driver in _drivers.values():
            driver.close()
        _drivers.clear()

def graph_driver(settings):
    uri = settings.neo4j_uri.replace("://localhost:", "://127.0.0.1:")
    key = (uri, settings.neo4j_user, settings.neo4j_password)
    with _driver_lock:
        if key not in _drivers:
            _drivers[key] = GraphDatabase.driver(uri, auth=(settings.neo4j_user, settings.neo4j_password), connection_timeout=5, connection_acquisition_timeout=10, max_transaction_retry_time=5)
        return _drivers[key]
from config import get_settings
from .retriever import matches_group
from .release import require_released_version

class GraphRepository:
    def __init__(self, version=None):
        self.settings = get_settings()
        self.version = version or self.settings.kg_version

    def _read(self, query, **params):
        s = self.settings
        driver = graph_driver(s)
        with driver.session(database=s.neo4j_database, default_access_mode=READ_ACCESS) as session:
            return session.execute_read(lambda tx: tx.run(query, **params).data())

    def _ready(self):
        require_released_version(self.version)
        if self.version != 'legacy':
            rows = self._read('MATCH (d:KGDataset {version:$v, ready:true}) RETURN d.version AS version', v=self.version)
            if not rows:
                raise RuntimeError('图谱版本未导入或尚未验证完成')

    def entities(self):
        self._ready()
        if self.version == 'legacy':
            rows = self._read("MATCH (n) WHERE NOT any(l IN labels(n) WHERE l STARTS WITH 'KG') RETURN elementId(n) AS uid, labels(n) AS labels, properties(n) AS props")
            return [dict(id=r['uid'], name=str(r['props'].get('name_cn') or r['props'].get('name') or r['props'].get('id', '')), legacy_id=str(r['props'].get('id', '')), label=r['labels'][0], properties=r['props'], aliases=list({str(r['props'].get(k,'')) for k in ('id','name','name_cn','name_en','generic_name')} - {''}), source_ids=[]) for r in rows]
        rows = self._read('MATCH (n:KGEntity {version:$v}) RETURN n.payload AS payload', v=self.version)
        return [json.loads(r['payload']) for r in rows]

    def sources(self, ids):
        if not ids or self.version == 'legacy':
            return []
        return [json.loads(r['payload']) for r in self._read('MATCH (s:KGSource {version:$v}) WHERE s.id IN $ids RETURN s.payload AS payload', v=self.version, ids=ids)]

    def detail(self, uid):
        entity = next((e for e in self.entities() if e['id'] == uid), None)
        if entity:
            return dict(version=self.version, entity=entity, sources=sorted(self.sources(entity['source_ids']), key=lambda s:s.get('review_status')!='source_checked_by_agent'))
        return None

    def neighbors(self, ids, group='all', limit=40, relation_type=None, pair_ids=None, include_unreviewed=False):
        entities = self.entities()
        index = {e['id']:e for e in entities}
        if self.version == 'legacy':
            rows = self._read("MATCH (a)-[r]->(b) WHERE (elementId(a) IN $ids OR elementId(b) IN $ids) AND NOT any(l IN labels(a)+labels(b) WHERE l STARTS WITH 'KG') RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target, type(r) AS type, properties(r) AS properties", ids=ids)
            edges = [dict(**r, source_ids=[]) for r in rows]
        else:
            edges = [json.loads(r['payload']) for r in self._read('MATCH (a:KGEntity {version:$v})-[r:KG_LINK]->(b:KGEntity {version:$v}) WHERE a.id IN $ids OR b.id IN $ids RETURN r.payload AS payload', v=self.version, ids=ids)]
        if self.version == 'kg_v2' and not include_unreviewed:
            edges = [e for e in edges if e.get('reasoning_eligible') is True]
        edges = sorted([e for e in edges if matches_group(e['type'], group) and (not relation_type or e['type']==relation_type)], key=lambda e:e['id'])
        if pair_ids:
            edges = [e for e in edges if e['source'] in pair_ids and e['target'] in pair_ids]
        total = len(edges)
        edges = edges[:limit]
        wanted = set(ids) | {e[k] for e in edges for k in ('source','target')}
        return dict(version=self.version, nodes=[index[i] for i in sorted(wanted) if i in index], edges=edges, total=total,
                    sources=self.sources(sorted({s for e in edges for s in e['source_ids']})),
                    truncated=total > limit, message='' if edges else '当前图谱未收录符合条件的关系。')

    def stats(self):
        entities = self.entities()
        if self.version == 'legacy':
            rows=self._read("MATCH (a)-[r]->(b) WHERE NOT any(l IN labels(a)+labels(b) WHERE l STARTS WITH 'KG') RETURN type(r) AS type, count(*) AS count")
            return dict(version=self.version, entities=len(entities), relations=sum(r['count'] for r in rows), relation_types=sorted(r['type'] for r in rows), pending=[], evidence_notice='旧图谱没有逐记录来源；医学原文待核实。')
        row=self._read('MATCH (d:KGDataset {version:$v, ready:true}) RETURN d.report AS report',v=self.version)[0]
        report=json.loads(row['report'])
        report.update(version=self.version, relation_types=[r['type'] for r in self._read('MATCH (:KGEntity {version:$v})-[r:KG_LINK]->() RETURN DISTINCT r.kind AS type ORDER BY type',v=self.version)], evidence_notice=('30条原文已由程序代理核对，尚未经临床专家审核；其中6条为美国标签补充证据。旧记录不进入v2推理。' if self.version=='kg_v2' else '仓库来源已定位；医学原文待核实。'))
        return report
