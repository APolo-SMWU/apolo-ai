"""검증된 외부 추출 후보를 Fact·Relation으로 저장하는 결정 규칙"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from apolo.contracts.extraction import ExtractionResult
from apolo.extraction.resolution import EntityResolution
from apolo.ontology.personal import MULTI_VALUED_PROPERTIES, PROPERTY_TYPES

# 같은 출발 Entity에서 여러 대상이 자연스러운 Relation이다.
_MULTI_TARGET_RELATIONS = frozenset(
    {"hasEducation", "hasExperience", "holds", "participatedIn", "usesSkill"}
)


@dataclass(frozen=True)
class PersistedExtraction:
    """후보 순서별 저장 행 ID, 모호한 Entity 때문에 건너뛴 후보 위치"""

    fact_ids: dict[int, UUID]
    relation_ids: dict[int, UUID]
    skipped_facts: tuple[int, ...]
    skipped_relations: tuple[int, ...]


def persist_extracted_candidates(
    connection: psycopg.Connection,
    graph_id: UUID,
    extraction: ExtractionResult,
    resolution: EntityResolution,
    *,
    now: datetime,
    force_candidate_fact_indexes: frozenset[int] = frozenset(),
    current_source_document_id: UUID | None = None,
    current_source_content_hash: str | None = None,
) -> PersistedExtraction:
    """Fact·Relation을 source 추출값으로 저장, 충돌 후보는 candidate로 보관

    Graph A의 바깥 트랜잭션 안에서 Entity·Evidence·처리 해시와 함께 호출한다.
    그래프 버전 증가는 전체 저장이 성공한 뒤 호출부가 담당한다.
    """
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("Graph A 저장 트랜잭션 안에서 호출해야 합니다.")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시간대가 있는 저장 시각이 필요합니다.")

    entity_ids = resolution.matched | resolution.new_ids
    classes = {entity.ref: entity.class_type for entity in extraction.entities}
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        _ensure_active_entities(cursor, graph_id, set(entity_ids.values()))
        facts_by_entity = _load_existing_facts(
            cursor,
            graph_id,
            set(entity_ids.values()),
            current_source_document_id=current_source_document_id,
            current_source_content_hash=current_source_content_hash,
        )
        relations_by_subject = _load_existing_relations(
            cursor,
            graph_id,
            current_source_document_id=current_source_document_id,
            current_source_content_hash=current_source_content_hash,
        )
        stale_fact_keys = _load_stale_source_fact_keys(
            cursor,
            graph_id,
            set(entity_ids.values()),
            current_source_document_id,
            current_source_content_hash,
        )
        stale_relation_keys = _load_stale_source_relation_keys(
            cursor,
            graph_id,
            current_source_document_id,
            current_source_content_hash,
        )
        fact_ids: dict[int, UUID] = {}
        relation_ids: dict[int, UUID] = {}
        skipped_facts: list[int] = []
        skipped_relations: list[int] = []

        for index, fact in enumerate(extraction.facts):
            entity_id = entity_ids.get(fact.entity_ref)
            class_type = classes.get(fact.entity_ref)
            if entity_id is None or class_type is None:
                skipped_facts.append(index)
                continue
            key = (entity_id, fact.predicate)
            existing = facts_by_entity.setdefault(key, [])
            same = next((item for item in existing if item.value == fact.value), None)
            if same is not None:
                if index not in force_candidate_fact_indexes:
                    _promote_fact_if_unblocked(cursor, same, existing, now=now)
                fact_ids[index] = same.id
                continue
            multi_valued = (class_type, fact.predicate) in MULTI_VALUED_PROPERTIES
            status = (
                "candidate"
                if index in force_candidate_fact_indexes
                else "active"
                if key in stale_fact_keys
                else "active"
                if multi_valued or not any(_blocks_new_fact(item) for item in existing)
                else "candidate"
            )
            fact_id = uuid4()
            value_type = PROPERTY_TYPES[class_type][fact.predicate][0]
            cursor.execute(
                "INSERT INTO ai.facts "
                "(id,entity_id,predicate,value,value_type,origin,confidence,locked,"
                "status,updated_at,provenance) "
                "VALUES (%s,%s,%s,%s,%s,'extracted',%s,false,%s,%s,'source')",
                (
                    fact_id,
                    entity_id,
                    fact.predicate,
                    Jsonb(fact.value),
                    value_type,
                    fact.confidence,
                    status,
                    now,
                ),
            )
            item = _StoredFact(fact_id, fact.value, status, "source", False)
            existing.append(item)
            fact_ids[index] = fact_id

        for index, relation in enumerate(extraction.relations):
            subject_id = entity_ids.get(relation.subject_ref)
            object_id = entity_ids.get(relation.object_ref)
            if subject_id is None or object_id is None:
                skipped_relations.append(index)
                continue
            key = (subject_id, relation.predicate)
            existing = relations_by_subject.setdefault(key, [])
            same = next((item for item in existing if item.object_entity_id == object_id), None)
            if same is not None:
                _promote_relation_if_unblocked(cursor, same, existing, now=now)
                relation_ids[index] = same.id
                continue
            status = (
                "active"
                if key in stale_relation_keys
                or relation.predicate in _MULTI_TARGET_RELATIONS
                or not any(_blocks_new_relation(item) for item in existing)
                else "candidate"
            )
            relation_id = uuid4()
            cursor.execute(
                "INSERT INTO ai.relations "
                "(id,graph_id,subject_entity_id,predicate,object_entity_id,origin,confidence,"
                "locked,status,updated_at,provenance) "
                "VALUES (%s,%s,%s,%s,%s,'extracted',%s,false,%s,%s,'source')",
                (
                    relation_id,
                    graph_id,
                    subject_id,
                    relation.predicate,
                    object_id,
                    relation.confidence,
                    status,
                    now,
                ),
            )
            existing.append(_StoredRelation(relation_id, object_id, status, "source", False))
            relation_ids[index] = relation_id

    return PersistedExtraction(
        fact_ids, relation_ids, tuple(skipped_facts), tuple(skipped_relations)
    )


def _load_stale_source_fact_keys(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    entity_ids: set[UUID],
    source_document_id: UUID | None,
    source_content_hash: str | None,
) -> set[tuple[UUID, str]]:
    """현재 Source만 갱신된 단일 Fact를 active로 대체할 식별자 조회"""
    if not entity_ids or source_document_id is None or source_content_hash is None:
        return set()
    cursor.execute(
        """
        SELECT fact.entity_id, fact.predicate
        FROM ai.facts fact
        JOIN ai.fact_evidence link
          ON link.graph_id=%s AND link.fact_id=fact.id
        JOIN ai.evidence evidence
          ON evidence.graph_id=link.graph_id AND evidence.id=link.evidence_id
        LEFT JOIN ai.source_documents document
          ON document.graph_id=evidence.graph_id
         AND document.id=evidence.source_document_id
        WHERE fact.entity_id=ANY(%s)
          AND fact.origin='extracted' AND fact.provenance='source'
        GROUP BY fact.id, fact.entity_id, fact.predicate
        HAVING BOOL_OR(
            evidence.source_document_id=%s
            AND evidence.source_content_hash<>%s
        )
        AND NOT BOOL_OR(
            (
                evidence.source_document_id=%s
                AND evidence.source_content_hash=%s
            )
            OR (
                evidence.source_document_id<>%s
                AND document.processed_content_hash IS NOT NULL
                AND evidence.source_content_hash=document.processed_content_hash
            )
        )
        """,
        (
            graph_id,
            list(entity_ids),
            source_document_id,
            source_content_hash,
            source_document_id,
            source_content_hash,
            source_document_id,
        ),
    )
    return {(entity_id, predicate) for entity_id, predicate in cursor.fetchall()}


def _load_stale_source_relation_keys(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    source_document_id: UUID | None,
    source_content_hash: str | None,
) -> set[tuple[UUID, str]]:
    """현재 Source만 갱신된 단일 Relation을 active로 대체할 식별자 조회"""
    if source_document_id is None or source_content_hash is None:
        return set()
    cursor.execute(
        """
        SELECT relation.subject_entity_id, relation.predicate
        FROM ai.relations relation
        JOIN ai.relation_evidence link
          ON link.graph_id=relation.graph_id AND link.relation_id=relation.id
        JOIN ai.evidence evidence
          ON evidence.graph_id=link.graph_id AND evidence.id=link.evidence_id
        LEFT JOIN ai.source_documents document
          ON document.graph_id=evidence.graph_id
         AND document.id=evidence.source_document_id
        WHERE relation.graph_id=%s
          AND relation.origin='extracted' AND relation.provenance='source'
        GROUP BY relation.id, relation.subject_entity_id, relation.predicate
        HAVING BOOL_OR(
            evidence.source_document_id=%s
            AND evidence.source_content_hash<>%s
        )
        AND NOT BOOL_OR(
            (
                evidence.source_document_id=%s
                AND evidence.source_content_hash=%s
            )
            OR (
                evidence.source_document_id<>%s
                AND document.processed_content_hash IS NOT NULL
                AND evidence.source_content_hash=document.processed_content_hash
            )
        )
        """,
        (
            graph_id,
            source_document_id,
            source_content_hash,
            source_document_id,
            source_content_hash,
            source_document_id,
        ),
    )
    return {(subject_id, predicate) for subject_id, predicate in cursor.fetchall()}


@dataclass(frozen=True)
class _StoredFact:
    id: UUID
    value: str | bool
    status: str
    provenance: str
    has_current_evidence: bool


@dataclass(frozen=True)
class _StoredRelation:
    id: UUID
    object_entity_id: UUID
    status: str
    provenance: str
    has_current_evidence: bool


def _blocks_new_fact(item: _StoredFact) -> bool:
    """현재 유효한 active Fact만 새 단일값을 candidate로 보류"""
    return item.status == "active" and (
        item.provenance == "profile" or item.has_current_evidence
    )


def _promote_fact_if_unblocked(
    cursor: psycopg.Cursor,
    same: _StoredFact,
    existing: list[_StoredFact],
    *,
    now: datetime,
) -> None:
    """같은 값이 다시 확인되면 다른 유효 Fact가 없을 때 candidate를 active로 승격"""
    if same.status != "candidate" or any(
        item is not same and _blocks_new_fact(item) for item in existing
    ):
        return
    cursor.execute(
        "UPDATE ai.facts SET status='active',updated_at=%s WHERE id=%s AND status='candidate'",
        (now, same.id),
    )


def _blocks_new_relation(item: _StoredRelation) -> bool:
    """현재 유효한 active Relation만 새 단일 대상 연결을 candidate로 보류"""
    return item.status == "active" and (
        item.provenance == "profile" or item.has_current_evidence
    )


def _promote_relation_if_unblocked(
    cursor: psycopg.Cursor,
    same: _StoredRelation,
    existing: list[_StoredRelation],
    *,
    now: datetime,
) -> None:
    """같은 Relation이 다시 확인되면 다른 유효 연결이 없을 때 candidate를 active로 승격"""
    if same.status != "candidate" or any(
        item is not same and _blocks_new_relation(item) for item in existing
    ):
        return
    cursor.execute(
        "UPDATE ai.relations SET status='active',updated_at=%s WHERE id=%s AND status='candidate'",
        (now, same.id),
    )


def _load_existing_facts(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    entity_ids: set[UUID],
    *,
    current_source_document_id: UUID | None,
    current_source_content_hash: str | None,
) -> dict[tuple[UUID, str], list[_StoredFact]]:
    if not entity_ids:
        return {}
    cursor.execute(
        "SELECT f.id,f.entity_id,f.predicate,f.value,f.status,f.provenance, "
        "EXISTS ("
        "SELECT 1 FROM ai.fact_evidence link "
        "JOIN ai.evidence evidence ON evidence.graph_id=link.graph_id "
        "AND evidence.id=link.evidence_id "
        "JOIN ai.source_documents document ON document.graph_id=evidence.graph_id "
        "AND document.id=evidence.source_document_id "
        "WHERE link.graph_id=e.graph_id AND link.fact_id=f.id "
        "AND document.processed_content_hash IS NOT NULL "
        "AND evidence.source_content_hash=document.processed_content_hash "
        "AND NOT (%s::uuid IS NOT NULL AND document.id=%s "
        "AND document.processed_content_hash IS DISTINCT FROM %s)"
        ") "
        "FROM ai.facts f "
        "JOIN ai.entities e ON e.id=f.entity_id "
        "WHERE e.graph_id=%s AND f.entity_id=ANY(%s) "
        "AND f.status IN ('active','candidate') FOR KEY SHARE OF f,e",
        (
            current_source_document_id,
            current_source_document_id,
            current_source_content_hash,
            graph_id,
            list(entity_ids),
        ),
    )
    items: dict[tuple[UUID, str], list[_StoredFact]] = {}
    for (
        fact_id,
        entity_id,
        predicate,
        value,
        status,
        provenance,
        has_current_evidence,
    ) in cursor.fetchall():
        items.setdefault((entity_id, predicate), []).append(
            _StoredFact(fact_id, value, status, provenance, has_current_evidence)
        )
    return items


def _load_existing_relations(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    *,
    current_source_document_id: UUID | None,
    current_source_content_hash: str | None,
) -> dict[tuple[UUID, str], list[_StoredRelation]]:
    cursor.execute(
        "SELECT r.id,r.subject_entity_id,r.predicate,r.object_entity_id,r.status,r.provenance, "
        "EXISTS ("
        "SELECT 1 FROM ai.relation_evidence link "
        "JOIN ai.evidence evidence ON evidence.graph_id=link.graph_id "
        "AND evidence.id=link.evidence_id "
        "JOIN ai.source_documents document ON document.graph_id=evidence.graph_id "
        "AND document.id=evidence.source_document_id "
        "WHERE link.graph_id=r.graph_id AND link.relation_id=r.id "
        "AND document.processed_content_hash IS NOT NULL "
        "AND evidence.source_content_hash=document.processed_content_hash "
        "AND NOT (%s::uuid IS NOT NULL AND document.id=%s "
        "AND document.processed_content_hash IS DISTINCT FROM %s)"
        ") "
        "FROM ai.relations r "
        "WHERE r.graph_id=%s AND r.status IN ('active','candidate') FOR KEY SHARE",
        (
            current_source_document_id,
            current_source_document_id,
            current_source_content_hash,
            graph_id,
        ),
    )
    items: dict[tuple[UUID, str], list[_StoredRelation]] = {}
    for (
        relation_id,
        subject_id,
        predicate,
        object_id,
        status,
        provenance,
        has_current_evidence,
    ) in cursor.fetchall():
        items.setdefault((subject_id, predicate), []).append(
            _StoredRelation(relation_id, object_id, status, provenance, has_current_evidence)
        )
    return items


def _ensure_active_entities(cursor: psycopg.Cursor, graph_id: UUID, entity_ids: set[UUID]) -> None:
    """Fact가 다른 KG Entity를 참조하지 않도록 저장 대상의 소속·상태 확인"""
    if not entity_ids:
        return
    cursor.execute(
        "SELECT id FROM ai.entities WHERE graph_id=%s AND status='active' AND id=ANY(%s) "
        "FOR KEY SHARE",
        (graph_id, list(entity_ids)),
    )
    if {row[0] for row in cursor.fetchall()} != entity_ids:
        raise ValueError("추출 Entity는 같은 KG의 active Entity여야 합니다.")
