"""uv run python -m apolo.db.migrate_ontology_1_1 로 005를 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def ontology_1_1_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "005_ontology_1_1.sql").read_text(encoding="utf-8")


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(ontology_1_1_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"온톨로지 1.1 마이그레이션 실패 ({code}). "
            "004 적용 여부와 DB 접속 정보를 확인해 주세요."
        ) from None
    print("온톨로지 1.1 적용 완료: Class·Relation·값 타입 확장, entity_keys, 분석 해시, KG 버전")


if __name__ == "__main__":
    main()
