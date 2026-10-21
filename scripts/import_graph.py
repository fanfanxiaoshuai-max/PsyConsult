"""Import the repository's existing KG JSON without calling an LLM or deleting data."""
import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', choices=['legacy', 'kg_v1'], default='legacy')
    parser.add_argument('--dry-run', action='store_true', help='Validate data without connecting to Neo4j')
    parser.add_argument('--strict', action='store_true', help='Refuse data with unresolved edge endpoints')
    args = parser.parse_args()
    if args.dataset == 'kg_v1':
        from build_knowledge_graph import build
        result = build(args.dry_run)
        print(json.dumps({k: v for k, v in result.items() if k not in ('pending', 'resolved_structurally')}, indent=2))
        return
    load_dotenv(ROOT / "agent" / ".env")
    files = sorted((ROOT / "mock_data").glob("*.json"))
    datasets = [(file, json.loads(file.read_text(encoding="utf-8"))) for file in files]
    ids = {node['id'] for _, data in datasets for node in data['nodes']}
    labels_by_id = {}
    for _, data in datasets:
        for node in data['nodes']:
            labels_by_id.setdefault(node['id'], set()).add(node['label'])
    expected_edges = {
        (source_label, edge['source'], edge['type'], target_label, edge['target'])
        for _, data in datasets for edge in data['edges']
        if edge['source'] in ids and edge['target'] in ids
        for source_label in labels_by_id[edge['source']]
        for target_label in labels_by_id[edge['target']]
    }
    skipped = []
    # Validate all input before performing writes; Cypher labels cannot be parameters.
    for file, data in datasets:
        for node in data["nodes"]:
            if not IDENTIFIER.fullmatch(node["label"]):
                raise ValueError(f"Invalid label in {file.name}")
        for edge in data["edges"]:
            if not IDENTIFIER.fullmatch(edge["type"]):
                raise ValueError(f"Invalid relation type in {file.name}")
            if edge["source"] not in ids or edge["target"] not in ids:
                skipped.append({'file': file.name, **edge})
    print(json.dumps({
        'files': len(files), 'node_records': sum(len(d['nodes']) for _, d in datasets),
        'unique_node_ids': len(ids), 'edge_records': sum(len(d['edges']) for _, d in datasets),
        'expected_nodes_on_empty_database': sum(len(labels) for labels in labels_by_id.values()),
        'expected_edges_on_empty_database': len(expected_edges),
        'node_ids_with_multiple_labels': {key: sorted(value) for key, value in labels_by_id.items() if len(value) > 1},
        'skipped_missing_endpoints': skipped,
    }, ensure_ascii=False, indent=2))
    if args.strict and skipped:
        raise SystemExit('Strict validation failed: unresolved endpoints. No writes performed.')
    if args.dry_run:
        return
    with GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password123")),
    ) as driver:
        driver.verify_connectivity()
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            for file, data in datasets:
                def write_graph(tx, data=data):
                    for node in data["nodes"]:
                        props = {p["key"]: p["value"] for p in node.get("properties", [])}
                        props["id"] = node["id"]
                        tx.run(f"MERGE (n:{node['label']} {{id: $id}}) SET n += $props",
                               id=node["id"], props=props).consume()
                session.execute_write(write_graph)
                print(f"{file.name}: {len(data['nodes'])} node records processed")
            # All nodes exist before importing cross-file relationships.
            for file, data in datasets:
                def write_edges(tx, data=data):
                    for edge in data['edges']:
                        if edge['source'] not in ids or edge['target'] not in ids:
                            continue
                        tx.run(f"MATCH (a {{id: $source}}), (b {{id: $target}}) "
                               f"WHERE NOT a:KGEntity AND NOT b:KGEntity MERGE (a)-[:{edge['type']}]->(b)",
                               source=edge['source'], target=edge['target']).consume()
                session.execute_write(write_edges)
            print(f"Skipped {len(skipped)} relationships with missing endpoints (listed above).")
            print("Total nodes:", session.run("MATCH (n) RETURN count(n) AS count").single()["count"])
            print("Total edges:", session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"])


if __name__ == "__main__":
    main()
