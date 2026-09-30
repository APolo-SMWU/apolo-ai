"""Source 하나의 검증된 추출 후보를 KG에 원자적으로 반영"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.db.evidence import load_matching_source_evidence, save_evidence
from apolo.db.extraction import PersistedExtraction, persist_extracted_candidates
from apolo.db.resolution import stage_extracted_entities
from apolo.db.source import PersistedCollectedSource
from apolo.extraction.evidence import matching_source_evidence, validate_source_evidence
from apolo.extraction.ownership import add_source_ownership_relations
from apolo.extraction.resolution import EntityResolution
from apolo.extraction.validation import ExtractionIssue, validate_extraction


@dataclass(frozen=True)
class GraphASourceWrite:
    """한 Source의 저장 결과와 규칙이 제외·보류한 후보 이유"""

    version: int
    resolution: EntityResolution
    persisted: PersistedExtraction
    issues: tuple[ExtractionIssue, ...]


def apply_source_extraction(
    connection: psycopg.Connection,
    graph_id: UUID,
    expected_version: int,
    source: CollectedSource,
    stored: PersistedCollectedSource,
    extraction: ExtractionResult,
    *,
    now: datetime,
) -> GraphASourceWrite:
    """근거 확인·Entity/Fact/Relation/Evidence·처리 해시·버전을 한 트랜잭션으로 반영"""
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("Graph A 저장 트랜잭션 안에서 호출해야 합니다.")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시간대가 있는 저장 시각이 필요합니다.")
    _check_source_state(graph_id, source, stored)

    grounded = validate_source_evidence(extraction, source)
    ownership_augmented = add_source_ownership_relations(source, grounded.result)
    checked = validate_extraction(ownership_augmented)
    # 한 응답 안에서 충돌한 값은 온톨로지 검증이 남긴 candidate용 Fact다.
    persistent = checked.result.model_copy(
        update={"facts": [*checked.result.facts, *checked.uncertain]}
    )
    force_candidates = frozenset(range(len(checked.result.facts), len(persistent.facts)))

    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        resolution = stage_extracted_entities(
            connection, graph_id, expected_version, persistent, now=now
        )
        persisted = persist_extracted_candidates(
            connection,
            graph_id,
            persistent,
            resolution,
            now=now,
            force_candidate_fact_indexes=force_candidates,
            current_source_document_id=stored.document.id,
            current_source_content_hash=stored.snapshot.content_hash,
        )
        _connect_evidence(
            connection, graph_id, source, stored, persistent, persisted, resolution
        )
        _mark_source_processed(cursor, graph_id, stored, now)
        cursor.execute(
            "UPDATE ai.knowledge_graphs SET version=%s,updated_at=%s WHERE id=%s AND version=%s",
            (expected_version + 1, now, graph_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ValueError("읽은 이후 KG 버전이 변경되었습니다.")

    return GraphASourceWrite(
        expected_version + 1,
        resolution,
        persisted,
        tuple([*grounded.issues, *checked.issues]),
    )


def _check_source_state(
    graph_id: UUID, source: CollectedSource, stored: PersistedCollectedSource
) -> None:
    """수집 직후의 현재 원문만 분석 대상으로 허용"""
    if (
        stored.document.graph_id != graph_id
        or stored.snapshot.graph_id != graph_id
        or stored.document.source_key != source.source_key
        or stored.snapshot.source_key != source.source_key
        or stored.snapshot.fetch_status != "success"
        or stored.snapshot.content_hash is None
    ):
        raise ValueError("현재 KG에 성공적으로 저장된 Source가 필요합니다.")
    content_hash = hashlib.sha256(source.content.encode("utf-8")).hexdigest()
    if content_hash != stored.snapshot.content_hash:
        raise ValueError("수집 원문과 저장된 Source 해시가 일치해야 합니다.")
    if stored.document.processed_content_hash == stored.snapshot.content_hash:
        raise ValueError("현재 원문 해시는 이미 Graph A에 반영되었습니다.")


def _connect_evidence(
    connection: psycopg.Connection,
    graph_id: UUID,
    source: CollectedSource,
    stored: PersistedCollectedSource,
    extraction: ExtractionResult,
    persisted: PersistedExtraction,
    resolution: EntityResolution,
) -> None:
    """현재 원문 Evidence를 Fact·Relation 또는 Work·Activity Entity에 연결"""
    evidence = load_matching_source_evidence(
        connection,
        graph_id,
        stored.document.id,
        stored.snapshot.content_hash or "",
        source.evidence_candidates,
    )
    evidence_by_pair = {(item.snippet, item.locator): item for item in evidence}
    links: dict[UUID, tuple[set[UUID], set[UUID], set[UUID]]] = {}

    def collect(
        evidence_refs: list[str], target_id: UUID, *, target_type: str
    ) -> None:
        for locator in evidence_refs:
            matches = matching_source_evidence(source, locator)
            if not matches:
                raise ValueError("원문 근거가 없는 후보는 저장할 수 없습니다.")
            for candidate in matches:
                item = evidence_by_pair.get((candidate.snippet, candidate.locator))
                if item is None:
                    raise ValueError("현재 원문 버전의 Evidence가 저장되어 있지 않습니다.")
                entity_ids, fact_ids, relation_ids = links.setdefault(
                    item.id, (set(), set(), set())
                )
                {
                    "entity": entity_ids,
                    "fact": fact_ids,
                    "relation": relation_ids,
                }[target_type].add(target_id)

    for index, fact in enumerate(extraction.facts):
        if index in persisted.fact_ids:
            collect(fact.evidence_refs, persisted.fact_ids[index], target_type="fact")
    for index, relation in enumerate(extraction.relations):
        if index in persisted.relation_ids:
            collect(
                relation.evidence_refs, persisted.relation_ids[index], target_type="relation"
            )

    resolved_entities = resolution.matched | resolution.new_ids
    for item in extraction.entity_evidence:
        entity_id = resolved_entities.get(item.entity_ref)
        if entity_id is not None:
            collect(item.evidence_refs, entity_id, target_type="entity")

    for item in evidence:
        entity_ids, fact_ids, relation_ids = links.get(
            item.id, (set(), set(), set())
        )
        if entity_ids or fact_ids or relation_ids:
            save_evidence(
                connection,
                graph_id,
                item,
                entity_ids=tuple(entity_ids),
                fact_ids=tuple(fact_ids),
                relation_ids=tuple(relation_ids),
            )


def _mark_source_processed(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    stored: PersistedCollectedSource,
    now: datetime,
) -> None:
    """현재 Snapshot 해시를 실제 반영한 시점으로 기록"""
    cursor.execute(
        "UPDATE ai.source_documents d SET processed_at=%s,processed_content_hash=%s "
        "FROM ai.source_snapshots s "
        "WHERE d.id=%s AND d.graph_id=%s AND s.graph_id=d.graph_id "
        "AND s.source_key=d.source_key AND s.fetch_status='success' "
        "AND s.content_hash=%s RETURNING d.id",
        (
            now,
            stored.snapshot.content_hash,
            stored.document.id,
            graph_id,
            stored.snapshot.content_hash,
        ),
    )
    if cursor.fetchone() is None:
        raise ValueError("현재 Source Snapshot을 확인하지 못했습니다.")
