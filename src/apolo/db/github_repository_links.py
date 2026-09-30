"""수집된 GitHub 저장소 URL을 유일하게 연결되는 Work에만 추가한다."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from apolo.contracts.source import Evidence
from apolo.db.evidence import save_evidence
from apolo.db.source import PersistedCollectedSource
from apolo.source_collection import StoredPublicCollection

GITHUB_REPOSITORY_SOURCE_PREFIX = "github:repository:"
GITHUB_REPOSITORY_URL_LOCATOR = "github.api.html_url"


@dataclass(frozen=True)
class GitHubRepositoryUrlLinkResult:
    """URL 추가 수, 모호하거나 실패한 Source 키"""

    linked_count: int
    ambiguous_source_keys: tuple[str, ...]
    failed_source_keys: tuple[str, ...]


def link_github_repository_urls(
    connection: psycopg.Connection,
    graph_id: UUID,
    collection: StoredPublicCollection,
    *,
    now: datetime,
) -> GitHubRepositoryUrlLinkResult:
    """재추출 없이 처리 완료된 저장소의 canonical URL fact와 근거만 추가한다.

    같은 저장소 Source의 현재 근거를 가진 활성 Work가 정확히 하나이고,
    self의 participatedIn 근거도 같은 Source에서 확인될 때만 연결한다.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("시간대가 있는 저장 시각이 필요합니다.")

    linked_count = 0
    ambiguous_source_keys: list[str] = []
    failed_source_keys: list[str] = []
    for source, stored in zip(
        collection.collected_sources, collection.saved_sources, strict=True
    ):
        if not _is_repository_source(source.source_key, stored):
            continue
        try:
            result = _link_repository_url(
                connection, graph_id, source.source_key, stored, now=now
            )
        except Exception:
            failed_source_keys.append(source.source_key)
            continue

        if result == "linked":
            linked_count += 1
        elif result == "ambiguous":
            ambiguous_source_keys.append(source.source_key)

    return GitHubRepositoryUrlLinkResult(
        linked_count=linked_count,
        ambiguous_source_keys=tuple(ambiguous_source_keys),
        failed_source_keys=tuple(failed_source_keys),
    )


def _link_repository_url(
    connection: psycopg.Connection,
    graph_id: UUID,
    source_key: str,
    stored: PersistedCollectedSource,
    *,
    now: datetime,
) -> Literal["linked", "ambiguous", "skipped"]:
    """단일 Repository Source의 URL fact·근거 추가를 원자적으로 처리"""
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT version FROM ai.knowledge_graphs WHERE id=%s FOR UPDATE",
            (graph_id,),
        )
        graph_row = cursor.fetchone()
        if graph_row is None:
            raise ValueError("소속 KG를 찾지 못했습니다.")
        graph_version = graph_row[0]

        cursor.execute(
            "SELECT source_url,processed_content_hash FROM ai.source_documents "
            "WHERE id=%s AND graph_id=%s AND source_key=%s",
            (stored.document.id, graph_id, source_key),
        )
        document_row = cursor.fetchone()
        if (
            document_row is None
            or document_row[1] != stored.snapshot.content_hash
            or not _is_github_repository_url(document_row[0])
        ):
            return "skipped"
        source_url = document_row[0]

        work_ids = _load_unambiguous_work_ids(
            cursor,
            graph_id,
            stored.document.id,
            stored.snapshot.content_hash or "",
        )
        if len(work_ids) > 1:
            return "ambiguous"
        if not work_ids:
            return "skipped"

        work_id = work_ids[0]
        fact_id, fact_changed = _ensure_repository_url_fact(
            cursor, work_id, source_url, now=now
        )
        evidence, evidence_changed = _ensure_repository_url_evidence(
            cursor,
            graph_id,
            stored,
            source_url,
            now=now,
        )
        links_changed = _repository_evidence_links_missing(
            cursor, graph_id, work_id, fact_id, evidence.id
        )
        if links_changed:
            save_evidence(
                connection,
                graph_id,
                evidence,
                entity_ids=(work_id,),
                fact_ids=(fact_id,),
            )

        if fact_changed or evidence_changed or links_changed:
            cursor.execute(
                "UPDATE ai.knowledge_graphs SET version=%s,updated_at=%s "
                "WHERE id=%s AND version=%s",
                (graph_version + 1, now, graph_id, graph_version),
            )
            if cursor.rowcount != 1:
                raise ValueError("URL 연결 중 KG 버전이 변경되었습니다.")
            return "linked"
        return "skipped"


def _is_repository_source(
    source_key: str,
    stored: PersistedCollectedSource,
) -> bool:
    """저장 성공한 저장소 Snapshot만 허용하고 처리 완료 여부는 DB에서 확인"""
    document = stored.document
    snapshot = stored.snapshot
    return (
        source_key.startswith(GITHUB_REPOSITORY_SOURCE_PREFIX)
        and document.source_type == "github"
        and document.source_key == source_key
        and snapshot.source_key == source_key
        and snapshot.fetch_status == "success"
        and snapshot.content_hash is not None
    )


def _is_github_repository_url(value: str) -> bool:
    """저장소 단위의 HTTPS GitHub URL인지 확인"""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"github.com", "www.github.com"}
        and len(path_parts) == 2
        and not parsed.query
        and not parsed.fragment
    )


def _load_unambiguous_work_ids(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    source_document_id: UUID,
    source_content_hash: str,
) -> list[UUID]:
    """현재 저장소 Source로 설명되고 본인 참여가 입증된 Work를 조회"""
    cursor.execute(
        """
        SELECT DISTINCT work.id
        FROM ai.entities work
        JOIN ai.facts identity_fact
          ON identity_fact.entity_id=work.id
         AND identity_fact.predicate IN ('title','kind')
         AND identity_fact.status='active'
        JOIN ai.fact_evidence identity_link
          ON identity_link.graph_id=work.graph_id
         AND identity_link.entity_id=work.id
         AND identity_link.fact_id=identity_fact.id
        JOIN ai.evidence identity_evidence
          ON identity_evidence.graph_id=identity_link.graph_id
         AND identity_evidence.id=identity_link.evidence_id
         AND identity_evidence.source_document_id=%s
         AND identity_evidence.source_content_hash=%s
        JOIN ai.relations participation
          ON participation.graph_id=work.graph_id
         AND participation.object_entity_id=work.id
         AND participation.predicate='participatedIn'
         AND participation.status='active'
        JOIN ai.entities person
          ON person.graph_id=participation.graph_id
         AND person.id=participation.subject_entity_id
         AND person.class_type='Person'
         AND person.status='active'
        JOIN ai.relation_evidence participation_link
          ON participation_link.graph_id=participation.graph_id
         AND participation_link.relation_id=participation.id
        JOIN ai.evidence participation_evidence
          ON participation_evidence.graph_id=participation_link.graph_id
         AND participation_evidence.id=participation_link.evidence_id
         AND participation_evidence.source_document_id=%s
         AND participation_evidence.source_content_hash=%s
        WHERE work.graph_id=%s
          AND work.class_type='Work'
          AND work.status='active'
        ORDER BY work.id
        """,
        (
            source_document_id,
            source_content_hash,
            source_document_id,
            source_content_hash,
            graph_id,
        ),
    )
    return [row[0] for row in cursor.fetchall()]


def _ensure_repository_url_fact(
    cursor: psycopg.Cursor,
    work_id: UUID,
    source_url: str,
    *,
    now: datetime,
) -> tuple[UUID, bool]:
    """Work.url을 추가하고 같은 URL candidate만 활성화"""
    cursor.execute(
        "SELECT id,status FROM ai.facts WHERE entity_id=%s AND predicate='url' "
        "AND value=to_jsonb(%s::text) "
        "AND (status='active' OR (status='candidate' AND origin='extracted' "
        "AND provenance='source')) "
        "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,id "
        "FOR UPDATE",
        (work_id, source_url),
    )
    existing = cursor.fetchone()
    if existing is not None:
        fact_id, status = existing
        if status == "candidate":
            cursor.execute(
                "UPDATE ai.facts SET status='active',updated_at=%s WHERE id=%s "
                "AND status='candidate'",
                (now, fact_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("GitHub URL 후보 Fact를 활성화하지 못했습니다.")
            return fact_id, True
        return fact_id, False

    fact_id = uuid4()
    cursor.execute(
        "INSERT INTO ai.facts "
        "(id,entity_id,predicate,value,value_type,origin,confidence,locked,status,updated_at,"
        "provenance) "
        "VALUES (%s,%s,'url',%s,'uri','extracted',1.0,false,'active',%s,'source')",
        (fact_id, work_id, Jsonb(source_url), now),
    )
    return fact_id, True


def _ensure_repository_url_evidence(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    stored: PersistedCollectedSource,
    source_url: str,
    *,
    now: datetime,
) -> tuple[Evidence, bool]:
    """GitHub API의 canonical repository URL을 메타데이터 근거로 저장"""
    content_hash = stored.snapshot.content_hash
    if content_hash is None:
        raise ValueError("처리 완료된 GitHub Source 해시가 필요합니다.")
    cursor.execute(
        "SELECT (to_jsonb(e)-'graph_id')::text FROM ai.evidence e "
        "WHERE graph_id=%s AND source_document_id=%s "
        "AND source_content_hash=%s AND snippet=%s AND locator=%s "
        "ORDER BY created_at,id LIMIT 1 FOR UPDATE",
        (
            graph_id,
            stored.document.id,
            content_hash,
            source_url,
            GITHUB_REPOSITORY_URL_LOCATOR,
        ),
    )
    existing = cursor.fetchone()
    if existing is not None:
        return Evidence.model_validate_json(existing[0]), False

    evidence = Evidence(
        id=uuid4(),
        source_document_id=stored.document.id,
        source_content_hash=content_hash,
        snippet=source_url,
        locator=GITHUB_REPOSITORY_URL_LOCATOR,
        created_at=now,
    )
    return evidence, True


def _repository_evidence_links_missing(
    cursor: psycopg.Cursor,
    graph_id: UUID,
    work_id: UUID,
    fact_id: UUID,
    evidence_id: UUID,
) -> bool:
    """Entity·Fact 연결 중 빠진 것이 있는지 조회"""
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM ai.entity_evidence "
        "WHERE graph_id=%s AND entity_id=%s AND evidence_id=%s), "
        "EXISTS (SELECT 1 FROM ai.fact_evidence "
        "WHERE graph_id=%s AND entity_id=%s AND fact_id=%s AND evidence_id=%s)",
        (graph_id, work_id, evidence_id, graph_id, work_id, fact_id, evidence_id),
    )
    entity_linked, fact_linked = cursor.fetchone()
    return not entity_linked or not fact_linked
