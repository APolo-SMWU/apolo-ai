"""변경된 Source의 LLM 후보 추출과 KG 저장을 연결하는 Graph A 처리"""

import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.db.github_repository_links import link_github_repository_urls
from apolo.db.graph_a import GraphASourceWrite, apply_source_extraction
from apolo.db.resolution import load_entity_summaries, load_work_summaries
from apolo.db.source import PersistedCollectedSource
from apolo.extraction.chunking import merge_extractions, split_source
from apolo.extraction.entity_linking import (
    LINKED_ENTITY_CLASSES,
    MIN_ENTITY_LINK_CONFIDENCE,
    EntitySummary,
    LinkedClass,
    Linker,
    entities_compatible,
    new_entity_summaries,
)
from apolo.extraction.work_linking import WorkSummary, accepted_links, new_work_summaries
from apolo.llm.config import load_llm_settings
from apolo.source_collection import StoredPublicCollection

logger = logging.getLogger(__name__)


class CandidateExtractor(Protocol):
    """Source에서 후보를 제안하는 LLM 클라이언트 계약"""

    def extract(self, source: CollectedSource) -> ExtractionResult: ...


@dataclass(frozen=True)
class GraphAProcessingWarning:
    """Source 처리 실패를 호출부에 알리는 안전한 경고"""

    source_key: str
    code: str
    message: str


@dataclass(frozen=True)
class GraphAProcessingResult:
    """이번 수집 결과에서 처리한 Source와 부분 실패 경고"""

    writes: tuple[GraphASourceWrite, ...]
    warnings: tuple[GraphAProcessingWarning, ...]


def process_pending_sources(
    connection: psycopg.Connection,
    graph_id: UUID,
    collection: StoredPublicCollection,
    extractor: CandidateExtractor,
    *,
    now: datetime | None = None,
    linker: Linker | None = None,
) -> GraphAProcessingResult:
    """변경 Source를 제한된 동시성으로 추출하고 병합 판정 후 원래 순서대로 저장"""
    processed_at = now or datetime.now(UTC)
    if processed_at.tzinfo is None or processed_at.utcoffset() is None:
        raise ValueError("시간대가 있는 처리 시각이 필요합니다.")

    writes: list[GraphASourceWrite] = []
    warnings: list[GraphAProcessingWarning] = []
    pending = collection.sources_needing_extraction()
    if pending:
        chunks = [split_source(source) for source, _ in pending]
        worker_count = min(
            load_llm_settings().max_parallel_extractions, sum(len(parts) for parts in chunks)
        )
        extracted: list[
            tuple[int, CollectedSource, PersistedCollectedSource, ExtractionResult]
        ] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                [executor.submit(extractor.extract, part) for part in parts] for parts in chunks
            ]
            for index, ((source, stored), parts) in enumerate(zip(pending, futures, strict=True)):
                try:
                    # 조각 하나라도 실패하면 Source 전체를 실패로 둔다
                    extraction = merge_extractions([future.result() for future in parts])
                    extracted.append((index, source, stored, extraction))
                except Exception as error:
                    logger.warning(
                        "Graph A 추출 실패 %s: %s", source.source_key, type(error).__name__
                    )
                    warnings.append(
                        GraphAProcessingWarning(
                            source_key=source.source_key,
                            code="extraction_failed",
                            message="LLM 후보 추출에 실패했습니다.",
                        )
                    )

        links = _link_entities(connection, graph_id, extracted, linker)
        for index, source, stored, extraction in extracted:
            forced_ids = {
                ref: links[f"s{index}:{ref}"]
                for ref in (entity.ref for entity in extraction.entities)
                if f"s{index}:{ref}" in links
            }
            try:
                with connection.transaction():
                    expected_version = _lock_and_load_version(connection, graph_id)
                    write = apply_source_extraction(
                        connection,
                        graph_id,
                        expected_version,
                        source,
                        stored,
                        extraction,
                        now=processed_at,
                        forced_ids=forced_ids,
                    )
                    writes.append(write)
            except Exception as error:
                logger.warning("Graph A 저장 실패 %s: %s", source.source_key, type(error).__name__)
                warnings.append(
                    GraphAProcessingWarning(
                        source_key=source.source_key,
                        code="persistence_failed",
                        message="후보 검증 또는 KG 저장에 실패했습니다.",
                    )
                )
            else:
                if write.issues:
                    # 추출 값에는 개인정보가 있을 수 있어 코드와 개수만 남긴다.
                    counts = Counter(issue.code for issue in write.issues)
                    logger.warning(
                        "Graph A 검증 경고 %s: %s",
                        source.source_key,
                        ", ".join(f"{code}x{n}" for code, n in sorted(counts.items())),
                    )

    github_links = link_github_repository_urls(
        connection,
        graph_id,
        collection,
        now=processed_at,
    )
    warnings.extend(
        GraphAProcessingWarning(
            source_key=source_key,
            code="github_work_link_ambiguous",
            message="저장소 Source에 연결된 Work가 여러 개라 GitHub URL을 추가하지 않았습니다.",
        )
        for source_key in github_links.ambiguous_source_keys
    )
    warnings.extend(
        GraphAProcessingWarning(
            source_key=source_key,
            code="github_work_link_failed",
            message="저장소 URL을 Work에 연결하지 못했습니다.",
        )
        for source_key in github_links.failed_source_keys
    )

    return GraphAProcessingResult(tuple(writes), tuple(warnings))


def _link_entities(
    connection: psycopg.Connection,
    graph_id: UUID,
    extracted: list[tuple[int, CollectedSource, PersistedCollectedSource, ExtractionResult]],
    linker: Linker | None,
) -> dict[str, UUID]:
    """새 후보와 기존 Entity를 클래스별로 동시에 판정한다. 실패한 클래스는 규칙 병합만 쓴다"""
    if linker is None or not extracted:
        return {}
    try:
        jobs = _linking_jobs(connection, graph_id, extracted, linker)
    except Exception as error:
        logger.warning("병합 판정 준비 실패: %s", type(error).__name__)
        return {}
    links: dict[str, UUID] = {}
    if not jobs:
        return links
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {label: executor.submit(job) for label, job in jobs.items()}
        for label, future in futures.items():
            try:
                links.update(future.result())
            except Exception as error:
                logger.warning("%s 병합 판정 실패: %s", label, type(error).__name__)
    return links


def _linking_jobs(
    connection: psycopg.Connection,
    graph_id: UUID,
    extracted: list[tuple[int, CollectedSource, PersistedCollectedSource, ExtractionResult]],
    linker: Linker,
) -> dict[str, Callable[[], dict[str, UUID]]]:
    """DB 조회는 여기서 끝내고 LLM 판정만 클래스별 작업으로 넘긴다"""
    jobs: dict[str, Callable[[], dict[str, UUID]]] = {}
    new_works = [
        summary
        for index, source, _, extraction in extracted
        for summary in new_work_summaries(index, source, extraction).values()
    ]
    if new_works:
        existing_works = load_work_summaries(connection, graph_id)
        works = [*existing_works.values(), *new_works]
        if len(works) >= 2:
            ids = {summary.id: entity_id for entity_id, summary in existing_works.items()}
            jobs["Work"] = partial(_judge_works, linker, works, ids)

    new_entities: dict[LinkedClass, list[EntitySummary]] = {c: [] for c in LINKED_ENTITY_CLASSES}
    for index, source, _, extraction in extracted:
        for class_type, by_ref in new_entity_summaries(index, source, extraction).items():
            new_entities[class_type].extend(by_ref.values())
    if any(new_entities.values()):
        existing = load_entity_summaries(connection, graph_id)
        for class_type, new in new_entities.items():
            items = [*existing[class_type].values(), *new]
            if new and len(items) >= 2:
                ids = {s.id: entity_id for entity_id, s in existing[class_type].items()}
                jobs[class_type] = partial(_judge_entities, linker, class_type, items, ids)
    return jobs


def _judge_works(
    linker: Linker, works: list[WorkSummary], existing_ids: dict[str, UUID]
) -> dict[str, UUID]:
    return accepted_links(linker.link(works), works, existing_ids)


def _judge_entities(
    linker: Linker,
    class_type: LinkedClass,
    items: list[EntitySummary],
    existing_ids: dict[str, UUID],
) -> dict[str, UUID]:
    return accepted_links(
        linker.link_entities(class_type, items),
        items,
        existing_ids,
        min_confidence=MIN_ENTITY_LINK_CONFIDENCE,
        compatible=entities_compatible,
    )


def _lock_and_load_version(connection: psycopg.Connection, graph_id: UUID) -> int:
    """저장 직전에 KG 행을 잠그고 현재 버전을 조회"""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT version FROM ai.knowledge_graphs WHERE id=%s FOR UPDATE",
            (graph_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("소속 KG를 찾지 못했습니다.")
    return row[0]
