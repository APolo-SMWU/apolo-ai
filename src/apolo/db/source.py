"""외부 소스의 수집 상태 저장·조회. 수집 실행이나 KG 사실 변경은 하지 않는다."""

from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from apolo.contracts.source import SourceDocument, SourceSnapshot


def load_source(
    connection: psycopg.Connection, graph_id: UUID, source_key: str
) -> tuple[SourceDocument, SourceSnapshot | None] | None:
    """문서와 최신 수집 상태를 한 SQL로 조회한다. 없는 문서는 None이다."""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT to_jsonb(d)::text, to_jsonb(s)::text FROM ai.source_documents d "
            "LEFT JOIN ai.source_snapshots s USING (graph_id, source_key) "
            "WHERE d.graph_id=%s AND d.source_key=%s",
            (graph_id, source_key),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return (
        SourceDocument.model_validate_json(row[0]),
        SourceSnapshot.model_validate_json(row[1]) if row[1] is not None else None,
    )


def save_source_capture(
    connection: psycopg.Connection, document: SourceDocument, snapshot: SourceSnapshot
) -> tuple[SourceDocument, SourceSnapshot]:
    """수집 결과를 원자적으로 저장하고 실제 저장된 ID·상태를 반환한다.

    입력 ID는 최초 생성 시에만 사용한다. 재수집은 기존 ID와 분석 시각을 유지한다.
    실패한 수집은 이전 성공의 해시·버전을 보존한다. 최초 실패는 둘 다 None이다.
    이전보다 오래된 조회 시각은 오류로 거부한다. 동시 저장은 KG 행 잠금으로 직렬화한다.
    기존 트랜잭션에서는 savepoint만 사용한다. 최종 commit·연결 종료는 호출부 책임이다.
    트랜잭션이 없으면 정상 종료 시 commit한다.
    """
    # model_copy 등으로 검증을 우회한 입력도 저장 전에 다시 확인한다.
    document = SourceDocument.model_validate(document.model_dump())
    snapshot = SourceSnapshot.model_validate(snapshot.model_dump())
    if (document.graph_id, document.source_key) != (snapshot.graph_id, snapshot.source_key):
        raise ValueError("문서와 Snapshot의 KG·소스 키가 일치해야 합니다.")
    if document.processed_at is not None:
        raise ValueError("수집 저장은 분석 완료 시각을 설정하지 않습니다.")

    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT id FROM ai.knowledge_graphs WHERE id=%s FOR UPDATE", (document.graph_id,)
        )
        if cursor.fetchone() is None:
            raise ValueError("소속 KG가 존재하지 않습니다.")
        existing = load_source(connection, document.graph_id, document.source_key)
        previous = existing[1] if existing else None
        if existing and existing[0].source_type != document.source_type:
            raise ValueError("같은 소스 키의 종류를 변경할 수 없습니다.")
        if previous and snapshot.last_fetched_at < previous.last_fetched_at:
            raise ValueError("기존 상태보다 오래된 수집 결과입니다.")

        content_hash, source_version = snapshot.content_hash, snapshot.source_version
        if snapshot.fetch_status != "success":
            content_hash = previous.content_hash if previous else None
            source_version = previous.source_version if previous else None

        cursor.execute(
            "INSERT INTO ai.source_documents (id,graph_id,source_type,source_key,source_url) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (graph_id,source_key) "
            "DO UPDATE SET source_url=EXCLUDED.source_url",
            (
                document.id,
                document.graph_id,
                document.source_type,
                document.source_key,
                document.source_url,
            ),
        )
        cursor.execute(
            "INSERT INTO ai.source_snapshots "
            "(id,graph_id,source_key,content_hash,source_version,last_fetched_at,fetch_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (graph_id,source_key) DO UPDATE SET "
            "content_hash=EXCLUDED.content_hash, source_version=EXCLUDED.source_version, "
            "last_fetched_at=EXCLUDED.last_fetched_at, fetch_status=EXCLUDED.fetch_status",
            (
                snapshot.id,
                snapshot.graph_id,
                snapshot.source_key,
                content_hash,
                source_version,
                snapshot.last_fetched_at,
                snapshot.fetch_status,
            ),
        )
        stored = load_source(connection, document.graph_id, document.source_key)
        if stored is None or stored[1] is None:
            raise RuntimeError("저장한 소스 상태를 조회하지 못했습니다.")
        return stored[0], stored[1]
