"""uv run python -m apolo.db.migrate_file_source 로 009를 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def file_source_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "009_file_source.sql").read_text(encoding="utf-8")


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(file_source_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"파일 Source 마이그레이션 실패 ({code}). "
            "source_documents_source_type_check 제약 조건 이름을 확인해 주세요."
        ) from None
    print("파일 Source 마이그레이션 완료: ai.source_documents.source_type에 file 추가")


if __name__ == "__main__":
    main()
