"""근거와 Fact·Relation 연결 저장. 원문 일치 검증과 KG 사실 생성은 별도 책임이다."""

from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from apolo.contracts.source import Evidence


def save_evidence(
    connection: psycopg.Connection,
    graph_id: UUID,
    evidence: Evidence,
    *,
    fact_ids: tuple[UUID, ...] = (),
    relation_ids: tuple[UUID, ...] = (),
) -> None:
    """근거와 연결을 원자적으로 추가한다. 같은 ID·내용·연결의 재저장은 허용한다.

    같은 근거 ID의 내용 변경은 거부한다. 새 내용은 새 ID를 사용한다.
    기존 연결을 제거하지 않으며, 연결 없는 근거도 저장할 수 있다.
    연결 대상은 같은 KG에 존재해야 한다. KG 버전·분석 시각은 변경하지 않는다.
    기존 트랜잭션 안에서는 savepoint, 없으면 독립 트랜잭션으로 처리한다.
    """
    evidence = Evidence.model_validate(evidence.model_dump())
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute("SELECT id FROM ai.knowledge_graphs WHERE id=%s FOR UPDATE", (graph_id,))
        if cursor.fetchone() is None:
            raise ValueError("소속 KG가 존재하지 않습니다.")
        cursor.execute(
            "INSERT INTO ai.evidence "
            "(id,graph_id,source_document_id,snippet,locator,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (
                evidence.id,
                graph_id,
                evidence.source_document_id,
                evidence.snippet,
                evidence.locator,
                evidence.created_at,
            ),
        )
        cursor.execute(
            "SELECT (to_jsonb(e)-'graph_id')::text FROM ai.evidence e "
            "WHERE id=%s AND graph_id=%s FOR UPDATE",
            (evidence.id, graph_id),
        )
        stored = cursor.fetchone()
        if stored is None or Evidence.model_validate_json(stored[0]) != evidence:
            raise ValueError("기존 Evidence ID의 KG 또는 내용을 변경할 수 없습니다.")

        for fact_id in sorted(set(fact_ids)):
            cursor.execute(
                "SELECT f.entity_id FROM ai.facts f JOIN ai.entities e ON e.id=f.entity_id "
                "WHERE f.id=%s AND e.graph_id=%s FOR KEY SHARE OF f,e",
                (fact_id, graph_id),
            )
            fact = cursor.fetchone()
            if fact is None:
                raise ValueError("같은 KG의 Fact가 존재하지 않습니다.")
            cursor.execute(
                "INSERT INTO ai.fact_evidence (graph_id,entity_id,fact_id,evidence_id) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (fact_id,evidence_id) DO NOTHING",
                (graph_id, fact[0], fact_id, evidence.id),
            )
        for relation_id in sorted(set(relation_ids)):
            cursor.execute(
                "SELECT id FROM ai.relations WHERE id=%s AND graph_id=%s FOR KEY SHARE",
                (relation_id, graph_id),
            )
            if cursor.fetchone() is None:
                raise ValueError("같은 KG의 Relation이 존재하지 않습니다.")
            cursor.execute(
                "INSERT INTO ai.relation_evidence (graph_id,relation_id,evidence_id) "
                "VALUES (%s,%s,%s) ON CONFLICT (relation_id,evidence_id) DO NOTHING",
                (graph_id, relation_id, evidence.id),
            )


def load_fact_evidence(
    connection: psycopg.Connection, graph_id: UUID, fact_id: UUID
) -> list[Evidence]:
    """해당 KG의 Fact 근거를 ID 순서로 조회한다. 대상·연결이 없으면 빈 목록이다."""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT (to_jsonb(e)-'graph_id')::text FROM ai.evidence e "
            "JOIN ai.fact_evidence l ON l.graph_id=e.graph_id AND l.evidence_id=e.id "
            "WHERE l.graph_id=%s AND l.fact_id=%s ORDER BY e.id",
            (graph_id, fact_id),
        )
        return [Evidence.model_validate_json(row[0]) for row in cursor.fetchall()]


def load_relation_evidence(
    connection: psycopg.Connection, graph_id: UUID, relation_id: UUID
) -> list[Evidence]:
    """해당 KG의 Relation 근거를 ID 순서로 조회한다. 대상·연결이 없으면 빈 목록이다."""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT (to_jsonb(e)-'graph_id')::text FROM ai.evidence e "
            "JOIN ai.relation_evidence l ON l.graph_id=e.graph_id AND l.evidence_id=e.id "
            "WHERE l.graph_id=%s AND l.relation_id=%s ORDER BY e.id",
            (graph_id, relation_id),
        )
        return [Evidence.model_validate_json(row[0]) for row in cursor.fetchall()]
