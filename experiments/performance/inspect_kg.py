"""특정 테스트 user_id의 Knowledge Graph 구축 결과를 조회한다."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APolo AI Knowledge Graph 조회")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--limit", type=int, default=200)
    return parser.parse_args()


def connect():
    return psycopg.connect(
        host=os.getenv("AI_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("AI_DB_PORT", "5432")),
        user=os.getenv("AI_DB_USER", "apolo_ai"),
        password=os.getenv("AI_DB_PASSWORD", ""),
        dbname=os.getenv("AI_DB_NAME", "apolo_dev"),
        row_factory=dict_row,
    )


def fetch_all(connection, query: str, params: tuple[Any, ...]):
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def build_report(connection, user_id: int, limit: int) -> dict[str, Any]:
    graph = fetch_all(
        connection,
        """
        SELECT
          g.id::text AS graph_id,
          g.user_id,
          g.version,
          g.ontology_schema_version,
          g.created_at,
          g.updated_at,
          (SELECT COUNT(*) FROM ai.source_documents d WHERE d.graph_id = g.id) AS source_count,
          (SELECT COUNT(*) FROM ai.entities e WHERE e.graph_id = g.id) AS entity_count,
          (SELECT COUNT(*) FROM ai.relations r WHERE r.graph_id = g.id) AS relation_count
        FROM ai.knowledge_graphs g
        WHERE g.user_id = %s
        """,
        (user_id,),
    )
    entity_counts = fetch_all(
        connection,
        """
        SELECT e.class_type, e.status, COUNT(*) AS count
        FROM ai.knowledge_graphs g
        JOIN ai.entities e ON e.graph_id = g.id
        WHERE g.user_id = %s
        GROUP BY e.class_type, e.status
        ORDER BY e.class_type, e.status
        """,
        (user_id,),
    )
    source_summary = fetch_all(
        connection,
        """
        SELECT
          d.source_url,
          d.source_key,
          COALESCE(s.fetch_status, 'no_snapshot') AS fetch_status,
          s.last_fetched_at,
          COUNT(DISTINCT ev.id) AS evidence_count,
          COUNT(DISTINCT fe.fact_id) AS fact_count,
          COUNT(DISTINCT re.relation_id) AS relation_count
        FROM ai.knowledge_graphs g
        JOIN ai.source_documents d ON d.graph_id = g.id
        LEFT JOIN ai.source_snapshots s
          ON s.graph_id = d.graph_id AND s.source_key = d.source_key
        LEFT JOIN ai.evidence ev
          ON ev.graph_id = d.graph_id AND ev.source_document_id = d.id
        LEFT JOIN ai.fact_evidence fe
          ON fe.graph_id = ev.graph_id AND fe.evidence_id = ev.id
        LEFT JOIN ai.relation_evidence re
          ON re.graph_id = ev.graph_id AND re.evidence_id = ev.id
        WHERE g.user_id = %s
        GROUP BY d.source_url, d.source_key, s.fetch_status, s.last_fetched_at
        ORDER BY d.source_url
        """,
        (user_id,),
    )
    facts = fetch_all(
        connection,
        """
        SELECT
          d.source_url,
          entity.class_type,
          fact.predicate,
          fact.value::text AS value,
          fact.status
        FROM ai.knowledge_graphs g
        JOIN ai.source_documents d ON d.graph_id = g.id
        JOIN ai.evidence evidence
          ON evidence.graph_id = d.graph_id
         AND evidence.source_document_id = d.id
        JOIN ai.fact_evidence link
          ON link.graph_id = evidence.graph_id AND link.evidence_id = evidence.id
        JOIN ai.facts fact
          ON fact.id = link.fact_id AND fact.entity_id = link.entity_id
        JOIN ai.entities entity
          ON entity.graph_id = link.graph_id AND entity.id = link.entity_id
        WHERE g.user_id = %s AND fact.status = 'active'
        ORDER BY d.source_url, entity.class_type, fact.predicate
        LIMIT %s
        """,
        (user_id, limit),
    )
    relations = fetch_all(
        connection,
        """
        SELECT
          d.source_url,
          subject.class_type AS subject_type,
          r.predicate,
          object_entity.class_type AS object_type,
          r.status
        FROM ai.knowledge_graphs g
        JOIN ai.source_documents d ON d.graph_id = g.id
        JOIN ai.evidence evidence
          ON evidence.graph_id = d.graph_id
         AND evidence.source_document_id = d.id
        JOIN ai.relation_evidence link
          ON link.graph_id = evidence.graph_id AND link.evidence_id = evidence.id
        JOIN ai.relations r
          ON r.graph_id = link.graph_id AND r.id = link.relation_id
        JOIN ai.entities subject
          ON subject.graph_id = r.graph_id AND subject.id = r.subject_entity_id
        JOIN ai.entities object_entity
          ON object_entity.graph_id = r.graph_id AND object_entity.id = r.object_entity_id
        WHERE g.user_id = %s AND r.status = 'active'
        ORDER BY d.source_url, r.predicate
        LIMIT %s
        """,
        (user_id, limit),
    )
    return {
        "user_id": user_id,
        "graphs": graph,
        "entity_counts": entity_counts,
        "source_summary": source_summary,
        "facts": facts,
        "relations": relations,
    }


def main() -> int:
    args = parse_args()
    load_dotenv(args.env_file)
    with connect() as connection:
        report = build_report(connection, args.user_id, args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
