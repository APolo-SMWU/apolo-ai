"""공개 소스 수집 결과를 사용자 KG에 저장"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx
import psycopg

from apolo.collectors.public import (
    PublicCollectionWarning,
    collect_public_sources,
)
from apolo.contracts.source import CollectedSource
from apolo.db.source import PersistedCollectedSource, persist_collected_source


@dataclass(frozen=True)
class StoredPublicCollection:
    """같은 순서의 수집 원문·저장 상태와 수집 경고"""

    collected_sources: list[CollectedSource]
    saved_sources: list[PersistedCollectedSource]
    warnings: list[PublicCollectionWarning]

    def sources_needing_extraction(
        self,
    ) -> list[tuple[CollectedSource, PersistedCollectedSource]]:
        """현재 수집 해시와 마지막 분석 해시가 다른 Source 선택"""
        pending = []
        for source, saved in zip(self.collected_sources, self.saved_sources, strict=True):
            if (
                source.source_key != saved.document.source_key
                or source.source_key != saved.snapshot.source_key
            ):
                raise ValueError("수집 원문과 저장 상태의 Source 키가 일치해야 합니다.")
            if (
                saved.snapshot.fetch_status == "success"
                and saved.snapshot.content_hash != saved.document.processed_content_hash
            ):
                pending.append((source, saved))
        return pending


async def collect_and_store_public_sources(
    connection: psycopg.Connection,
    graph_id: UUID,
    source_urls: list[str],
    *,
    client: httpx.AsyncClient,
    fetched_at: datetime | None = None,
) -> StoredPublicCollection:
    """GitHub·Notion 수집 후 성공한 Source만 한 트랜잭션으로 저장"""
    collected = await collect_public_sources(source_urls, client=client)
    fetched_at = fetched_at or datetime.now(UTC)
    warnings = list(collected.warnings)
    collected_sources: list[CollectedSource] = []
    saved_sources: list[PersistedCollectedSource] = []
    seen_keys: set[str] = set()

    with connection.transaction():
        for source in collected.sources:
            if source.source_key in seen_keys:
                warnings.append(
                    PublicCollectionWarning(
                        source_url=source.source_url,
                        code="duplicate_source",
                        message="같은 Source가 여러 번 수집되어 첫 결과만 저장했습니다.",
                    )
                )
                continue
            seen_keys.add(source.source_key)
            saved_sources.append(
                persist_collected_source(
                    connection, graph_id, source, fetched_at=fetched_at
                )
            )
            collected_sources.append(source)

    return StoredPublicCollection(
        collected_sources=collected_sources,
        saved_sources=saved_sources,
        warnings=warnings,
    )
