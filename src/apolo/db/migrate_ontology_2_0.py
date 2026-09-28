"""uv run python -m apolo.db.migrate_ontology_2_0 로 006을 적용한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def ontology_2_0_migration_sql() -> str:
    return (Path(__file__).parent / "sql" / "006_ontology_2_0.sql").read_text(
        encoding="utf-8"
    )


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(ontology_2_0_migration_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"온톨로지 2.0 마이그레이션 실패 ({code}). "
            "005 적용 여부와 기존 KG 버전을 확인해 주세요."
        ) from None
    print("온톨로지 2.0 적용 완료: Activity 추가, 폐기 속성 정리, KG 버전 2.0")


if __name__ == "__main__":
    main()
