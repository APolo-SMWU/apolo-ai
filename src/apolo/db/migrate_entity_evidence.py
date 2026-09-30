"""uv run python -m apolo.db.migrate_entity_evidence 로 007을 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def entity_evidence_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "007_entity_evidence.sql").read_text(
        encoding="utf-8"
    )


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(entity_evidence_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"Entity Evidence 마이그레이션 실패 ({code}). "
            "Source Evidence 테이블과 KG 2.0 적용 여부를 확인해 주세요."
        ) from None
    print("Entity Evidence 마이그레이션 완료: ai.entity_evidence")


if __name__ == "__main__":
    main()
