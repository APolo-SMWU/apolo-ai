"""uv run python -m apolo.db.migrate_fact_relation_provenance 로 004를 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def fact_relation_provenance_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "004_fact_relation_provenance.sql").read_text(
        encoding="utf-8"
    )


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(fact_relation_provenance_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"Fact·Relation 출처 마이그레이션 실패 ({code}). "
            "기존 추출 데이터 유무와 DB 접속 정보를 확인해 주세요."
        ) from None
    print("Fact·Relation 출처 컬럼 생성 완료: ai.facts.provenance, ai.relations.provenance")


if __name__ == "__main__":
    main()
