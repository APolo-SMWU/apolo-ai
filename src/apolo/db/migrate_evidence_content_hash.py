"""uv run python -m apolo.db.migrate_evidence_content_hash 로 003을 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def evidence_content_hash_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "003_evidence_content_hash.sql").read_text(
        encoding="utf-8"
    )


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(evidence_content_hash_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"Evidence hash 마이그레이션 실패 ({code}). "
            "기존 Evidence 유무와 DB 접속 정보를 확인해 주세요."
        ) from None
    print("Evidence 원문 해시 컬럼 생성 완료: ai.evidence.source_content_hash")


if __name__ == "__main__":
    main()
