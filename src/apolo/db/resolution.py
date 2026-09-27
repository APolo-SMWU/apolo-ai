"""Graph A Entity 식별 정보 조회와 트랜잭션 내 신규 Entity 준비"""

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from apolo.contracts.extraction import ExtractionResult
from apolo.extraction.resolution import (
    EntityResolution,
    ExistingEntity,
    StrongEntityKey,
    candidate_strong_keys,
    resolve_existing_entities,
)
from apolo.ontology.values import is_valid_value


def load_entities_for_resolution(
    connection: psycopg.Connection, graph_id: UUID
) -> list[ExistingEntity]:
    """같은 KG의 활성 Entity와 식별용 Fact·소속·강한 키를 한 시점에 조회"""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """
            SELECT e.id, e.class_type,
                COALESCE((
                    SELECT jsonb_agg(jsonb_build_object('predicate', f.predicate, 'value', f.value))
                    FROM ai.facts f WHERE f.entity_id=e.id AND f.status='active'
                ), '[]'::jsonb),
                COALESCE((
                    SELECT array_agg(r.object_entity_id)
                    FROM ai.relations r
                    WHERE r.graph_id=e.graph_id AND r.subject_entity_id=e.id
                      AND r.predicate='atOrganization' AND r.status='active'
                ), ARRAY[]::uuid[]),
                COALESCE((
                    SELECT jsonb_agg(jsonb_build_object('type', k.key_type, 'value', k.key_value))
                    FROM ai.entity_keys k WHERE k.entity_id=e.id AND k.is_strong
                ), '[]'::jsonb)
            FROM ai.entities e WHERE e.graph_id=%s AND e.status='active'
            ORDER BY e.id
            """,
            (graph_id,),
        )
        rows = cursor.fetchall()

    existing: list[ExistingEntity] = []
    for entity_id, class_type, fact_rows, organization_ids, key_rows in rows:
        facts: dict[str, set[str | bool]] = {}
        keys = {
            StrongEntityKey(key["type"], key["value"])
            for key in key_rows
            if key["type"] in {"work_url", "organization_homepage"}
        }
        for fact in fact_rows:
            predicate, value = fact["predicate"], fact["value"]
            facts.setdefault(predicate, set()).add(value)
            key_type = {
                ("Work", "url"): "work_url",
                ("Organization", "homepage"): "organization_homepage",
            }.get((class_type, predicate))
            if key_type and is_valid_value("uri", value):
                keys.add(StrongEntityKey(key_type, value))
        existing.append(
            ExistingEntity(
                id=entity_id,
                class_type=class_type,
                facts={predicate: frozenset(values) for predicate, values in facts.items()},
                organization_ids=frozenset(organization_ids),
                strong_keys=frozenset(keys),
            )
        )
    return existing


def stage_extracted_entities(
    connection: psycopg.Connection,
    graph_id: UUID,
    expected_version: int,
    extraction: ExtractionResult,
    *,
    now: datetime,
) -> EntityResolution:
    """KG 잠금 후 새 Entity·URL 키 삽입, Fact·Relation 저장과 같은 외부 트랜잭션 필수

    호출부가 Fact·Relation·Evidence와 처리 해시를 저장한 뒤 버전을 올려야 한다.
    모호한 후보는 건너뛰며 기존 Entity의 Fact와 프로필 출처는 수정하지 않는다.
    """
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("Graph A 저장 트랜잭션 안에서 호출해야 합니다.")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시간대가 있는 저장 시각이 필요합니다.")

    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT version FROM ai.knowledge_graphs WHERE id=%s FOR UPDATE", (graph_id,)
        )
        row = cursor.fetchone()
        if row is None or row[0] != expected_version:
            raise ValueError("KG가 없거나 읽은 이후 버전이 변경되었습니다.")

        resolution = resolve_existing_entities(
            extraction, load_entities_for_resolution(connection, graph_id)
        )
        classes = {entity.ref: entity.class_type for entity in extraction.entities}
        new_entities = {entity_id: classes[ref] for ref, entity_id in resolution.new_ids.items()}
        cursor.executemany(
            "INSERT INTO ai.entities "
            "(id,graph_id,class_type,status,created_at,updated_at) "
            "VALUES (%s,%s,%s,'active',%s,%s)",
            [
                (entity_id, graph_id, class_type, now, now)
                for entity_id, class_type in new_entities.items()
            ],
        )

        keys = candidate_strong_keys(extraction)
        resolved_ids = resolution.matched | resolution.new_ids
        key_rows = {
            (entity_id, key.key_type, key.key_value)
            for ref, entity_id in resolved_ids.items()
            for key in keys[ref]
        }
        cursor.executemany(
            "INSERT INTO ai.entity_keys "
            "(graph_id,entity_id,key_type,key_value,is_strong) "
            "VALUES (%s,%s,%s,%s,true) "
            "ON CONFLICT (entity_id,key_type,key_value) DO NOTHING",
            [
                (graph_id, entity_id, key_type, key_value)
                for entity_id, key_type, key_value in sorted(key_rows)
            ],
        )
        return resolution
