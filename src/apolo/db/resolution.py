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
from apolo.extraction.work_linking import WorkSummary, representative_snippet
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


def load_work_summaries(connection: psycopg.Connection, graph_id: UUID) -> dict[UUID, WorkSummary]:
    """병합 판정용 활성 Work 요약. id는 W1, W2 … 순서로 붙인다"""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """
            SELECT e.id,
                COALESCE((
                    SELECT jsonb_object_agg(p.predicate, p.vals) FROM (
                        SELECT f.predicate, jsonb_agg(f.value) AS vals FROM ai.facts f
                        WHERE f.entity_id=e.id AND f.status='active' GROUP BY f.predicate
                    ) p
                ), '{}'::jsonb),
                COALESCE((
                    SELECT jsonb_agg(sf.value) FROM ai.relations r
                    JOIN ai.facts sf ON sf.entity_id=r.object_entity_id
                     AND sf.predicate='name' AND sf.status='active'
                    WHERE r.graph_id=e.graph_id AND r.subject_entity_id=e.id
                      AND r.predicate='usesSkill' AND r.status='active'
                ), '[]'::jsonb),
                COALESCE((
                    SELECT jsonb_agg(jsonb_build_object(
                        'locator', ev.locator, 'snippet', ev.snippet,
                        'source_type', d.source_type,
                        'page_title', (
                            SELECT t.snippet FROM ai.evidence t
                            WHERE t.source_document_id=d.id AND d.source_type='notion'
                              AND replace(t.locator, '-', '')
                                  = 'notion.block:' || replace(d.source_key, 'notion:page:', '')
                            LIMIT 1
                        )
                    ))
                    FROM ai.evidence ev JOIN ai.source_documents d ON d.id=ev.source_document_id
                    WHERE ev.id IN (
                        SELECT evidence_id FROM ai.entity_evidence WHERE entity_id=e.id
                        UNION SELECT evidence_id FROM ai.fact_evidence WHERE entity_id=e.id
                    )
                ), '[]'::jsonb)
            FROM ai.entities e
            WHERE e.graph_id=%s AND e.class_type='Work' AND e.status='active'
            ORDER BY e.created_at, e.id
            """,
            (graph_id,),
        )
        rows = cursor.fetchall()

    summaries: dict[UUID, WorkSummary] = {}
    for entity_id, facts, skills, evidence in rows:
        title = next((v for v in facts.get("title", []) if isinstance(v, str)), None)
        if title is None:
            continue
        contexts = [
            " > ".join(
                part
                for part in (item["page_title"], item["locator"].partition(";section_path=")[2])
                if part
            )
            for item in evidence
            if item["source_type"] == "notion"
        ]
        summaries[entity_id] = WorkSummary(
            id=f"W{len(summaries) + 1}",
            source_types=tuple(sorted({item["source_type"] for item in evidence})),
            title=title,
            kind=_first_text(facts, "kind"),
            role=_first_text(facts, "role"),
            start=_first_text(facts, "start"),
            end=_first_text(facts, "end"),
            urls=tuple(v for v in facts.get("url", []) if isinstance(v, str)),
            skills=tuple(dict.fromkeys(skills))[:5],
            snippet=representative_snippet(
                [(item["locator"], item["snippet"]) for item in evidence], title
            ),
            context=tuple(dict.fromkeys(c for c in contexts if c))[:3],
        )
    return summaries


def _first_text(facts: dict[str, list[object]], predicate: str) -> str | None:
    return next((v for v in facts.get(predicate, []) if isinstance(v, str)), None)


def stage_extracted_entities(
    connection: psycopg.Connection,
    graph_id: UUID,
    expected_version: int,
    extraction: ExtractionResult,
    *,
    now: datetime,
    forced_ids: dict[str, UUID] | None = None,
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
            extraction, load_entities_for_resolution(connection, graph_id), forced_ids
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
