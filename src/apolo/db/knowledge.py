"""Graph B가 사용할 현재 유효한 KG 조회."""

from collections.abc import Collection

import psycopg
from psycopg.rows import tuple_row

from apolo.contracts.knowledge import ActiveKnowledgeGraph


def load_active_knowledge_graph(
    connection: psycopg.Connection,
    user_id: int,
    source_keys: Collection[str] | None = None,
) -> ActiveKnowledgeGraph | None:
    """사용자의 active KG를 조회하고 오래된 Source 근거를 제외한다.

    ``source_keys``가 주어지면 해당 요청에서 수집한 Source의 Evidence만 사용한다.
    프로필 provenance는 Evidence 없이 사용한다. Source provenance는 연결된 Evidence 중
    하나라도 SourceDocument의 마지막 처리 해시와 일치할 때만 사용한다. 수집은 되었지만
    아직 Graph A 분석이 끝나지 않은 최신 Snapshot은 기존 처리 결과를 무효화하지 않는다.
    연결과 트랜잭션의 종료는 호출부 책임이다.
    """
    source_scope_sql = ""
    params: tuple[object, ...]
    if source_keys is None:
        params = (user_id,)
    else:
        scoped_keys = sorted(set(source_keys))
        source_scope_sql = " AND document.source_key = ANY(%s)"
        params = (scoped_keys, scoped_keys, user_id)

    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            f"""
            WITH current_fact_evidence AS (
                SELECT
                    link.fact_id,
                    jsonb_agg(
                        (to_jsonb(evidence) - 'graph_id') ORDER BY evidence.id
                    ) AS items
                FROM ai.fact_evidence link
                JOIN ai.evidence evidence
                  ON evidence.graph_id = link.graph_id
                 AND evidence.id = link.evidence_id
                JOIN ai.source_documents document
                  ON document.graph_id = evidence.graph_id
                 AND document.id = evidence.source_document_id
                WHERE document.processed_content_hash IS NOT NULL
                  AND evidence.source_content_hash = document.processed_content_hash
                  {source_scope_sql}
                GROUP BY link.fact_id
            ),
            current_relation_evidence AS (
                SELECT
                    link.relation_id,
                    jsonb_agg(
                        (to_jsonb(evidence) - 'graph_id') ORDER BY evidence.id
                    ) AS items
                FROM ai.relation_evidence link
                JOIN ai.evidence evidence
                  ON evidence.graph_id = link.graph_id
                 AND evidence.id = link.evidence_id
                JOIN ai.source_documents document
                  ON document.graph_id = evidence.graph_id
                 AND document.id = evidence.source_document_id
                WHERE document.processed_content_hash IS NOT NULL
                  AND evidence.source_content_hash = document.processed_content_hash
                  {source_scope_sql}
                GROUP BY link.relation_id
            )
            SELECT jsonb_build_object(
                'id', graph.id,
                'user_id', graph.user_id,
                'ontology_schema_version', graph.ontology_schema_version,
                'version', graph.version,
                'created_at', graph.created_at,
                'updated_at', graph.updated_at,
                'entities', COALESCE((
                    SELECT jsonb_agg(jsonb_build_object(
                        'id', entity.id,
                        'graph_id', entity.graph_id,
                        'class_type', entity.class_type,
                        'status', entity.status,
                        'created_at', entity.created_at,
                        'updated_at', entity.updated_at
                    ) ORDER BY entity.id)
                    FROM ai.entities entity
                    WHERE entity.graph_id = graph.id
                      AND entity.status = 'active'
                ), '[]'::jsonb),
                'facts', COALESCE((
                    SELECT jsonb_agg(jsonb_build_object(
                        'id', fact.id,
                        'entity_id', fact.entity_id,
                        'predicate', fact.predicate,
                        'value', fact.value,
                        'value_type', fact.value_type,
                        'origin', fact.origin,
                        'provenance', fact.provenance,
                        'confidence', fact.confidence,
                        'locked', fact.locked,
                        'status', fact.status,
                        'evidence', CASE
                            WHEN fact.provenance = 'source'
                                THEN COALESCE(fact_evidence.items, '[]'::jsonb)
                            ELSE '[]'::jsonb
                        END,
                        'updated_at', fact.updated_at
                    ) ORDER BY fact.id)
                    FROM ai.facts fact
                    JOIN ai.entities entity ON entity.id = fact.entity_id
                    LEFT JOIN current_fact_evidence fact_evidence
                        ON fact_evidence.fact_id = fact.id
                    WHERE entity.graph_id = graph.id
                      AND entity.status = 'active'
                      AND fact.status = 'active'
                      AND fact.provenance IN ('profile', 'source')
                      AND (
                          fact.provenance = 'profile'
                          OR fact_evidence.fact_id IS NOT NULL
                      )
                ), '[]'::jsonb),
                'relations', COALESCE((
                    SELECT jsonb_agg(jsonb_build_object(
                        'id', relation.id,
                        'graph_id', relation.graph_id,
                        'subject_entity_id', relation.subject_entity_id,
                        'predicate', relation.predicate,
                        'object_entity_id', relation.object_entity_id,
                        'origin', relation.origin,
                        'provenance', relation.provenance,
                        'confidence', relation.confidence,
                        'locked', relation.locked,
                        'status', relation.status,
                        'evidence', CASE
                            WHEN relation.provenance = 'source'
                                THEN COALESCE(relation_evidence.items, '[]'::jsonb)
                            ELSE '[]'::jsonb
                        END,
                        'updated_at', relation.updated_at
                    ) ORDER BY relation.id)
                    FROM ai.relations relation
                    JOIN ai.entities subject_entity
                      ON subject_entity.graph_id = relation.graph_id
                     AND subject_entity.id = relation.subject_entity_id
                    JOIN ai.entities object_entity
                      ON object_entity.graph_id = relation.graph_id
                     AND object_entity.id = relation.object_entity_id
                    LEFT JOIN current_relation_evidence relation_evidence
                        ON relation_evidence.relation_id = relation.id
                    WHERE relation.graph_id = graph.id
                      AND relation.status = 'active'
                      AND subject_entity.status = 'active'
                      AND object_entity.status = 'active'
                      AND relation.provenance IN ('profile', 'source')
                      AND (
                          relation.provenance = 'profile'
                          OR relation_evidence.relation_id IS NOT NULL
                      )
                ), '[]'::jsonb)
            )::text
            FROM ai.knowledge_graphs graph
            WHERE graph.user_id = %s
            """,
            params,
        )
        row = cursor.fetchone()

    if row is None:
        return None
    return ActiveKnowledgeGraph.model_validate_json(row[0])
