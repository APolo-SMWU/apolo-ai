"""uv run python -m apolo.db.init_schema 로 최초 KG 테이블을 생성한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def initial_schema_sql() -> str:
    return (Path(__file__).parent / "sql" / "001_initial_kg.sql").read_text(encoding="utf-8")


def main() -> None:
    try:
        # 모든 DDL을 한 트랜잭션으로 처리한다. 하나라도 실패하면 전체 롤백한다.
        with connect_db() as connection:
            connection.execute(initial_schema_sql())
    except psycopg.errors.DuplicateTable:
        raise SystemExit(
            "KG 테이블 또는 인덱스가 이미 있습니다. 기존 구조를 확인해 주세요."
        ) from None
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"KG 테이블 생성 실패 ({code}). 접속 정보와 ai 스키마 CREATE 권한을 확인해 주세요."
        ) from None
    print("KG 테이블 생성 완료: ai.knowledge_graphs, ai.entities, ai.facts, ai.relations")


if __name__ == "__main__":
    main()
