"""변경된 Source의 LLM 후보 추출과 KG 저장을 연결하는 Graph A 처리"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.db.graph_a import GraphASourceWrite, apply_source_extraction
from apolo.source_collection import StoredPublicCollection

MAX_PARALLEL_EXTRACTIONS = 4


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
    changed: bool = False


def process_pending_sources(
    connection: psycopg.Connection,
    graph_id: UUID,
    collection: StoredPublicCollection,
    extractor: CandidateExtractor,
    *,
    now: datetime | None = None,
) -> GraphAProcessingResult:
    """변경 Source를 제한된 동시성으로 추출하고 저장은 원래 순서대로 처리"""
    processed_at = now or datetime.now(UTC)
    if processed_at.tzinfo is None or processed_at.utcoffset() is None:
        raise ValueError("시간대가 있는 처리 시각이 필요합니다.")

    writes: list[GraphASourceWrite] = []
    warnings: list[GraphAProcessingWarning] = []
    pending = collection.sources_needing_extraction()
    if not pending:
        return GraphAProcessingResult(tuple(writes), tuple(warnings), changed=False)

    worker_count = min(MAX_PARALLEL_EXTRACTIONS, len(pending))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(extractor.extract, source) for source, _ in pending]
        for (source, stored), future in zip(pending, futures, strict=True):
            try:
                extraction = future.result()
            except Exception:
                warnings.append(
                    GraphAProcessingWarning(
                        source_key=source.source_key,
                        code="extraction_failed",
                        message="LLM 후보 추출에 실패했습니다.",
                    )
                )
                continue

            try:
                with connection.transaction():
                    expected_version = _lock_and_load_version(connection, graph_id)
                    writes.append(
                        apply_source_extraction(
                            connection,
                            graph_id,
                            expected_version,
                            source,
                            stored,
                            extraction,
                            now=processed_at,
                        )
                    )
            except Exception:
                warnings.append(
                    GraphAProcessingWarning(
                        source_key=source.source_key,
                        code="persistence_failed",
                        message="후보 검증 또는 KG 저장에 실패했습니다.",
                    )
                )

    return GraphAProcessingResult(
        tuple(writes),
        tuple(warnings),
        changed=bool(writes),
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
