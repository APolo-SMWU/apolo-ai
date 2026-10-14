"""uv run python -m apolo.db.migrate_ontology_2_1 로 008을 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def ontology_2_1_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "008_ontology_2_1.sql").read_text(
        encoding="utf-8"
    )


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(ontology_2_1_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"온톨로지 2.1 마이그레이션 실패 ({code}). "
            "007 적용 여부와 기존 KG 버전을 확인해 주세요."
        ) from None
    print("온톨로지 2.1 적용 완료: Source 분석 버전 기록, 이전 Skill category 정리, KG 버전 2.1")


if __name__ == "__main__":
    main()
