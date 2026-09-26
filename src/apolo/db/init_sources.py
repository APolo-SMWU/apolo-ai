"""uv run python -m apolo.db.init_sources 로 소스·근거 테이블을 추가한다."""

from pathlib import Path

import psycopg

from apolo.db.connection import connect_db


def source_schema_sql() -> str:
    return (Path(__file__).parent / "sql" / "002_source_evidence.sql").read_text(encoding="utf-8")


def main() -> None:
    try:
        with connect_db() as connection:
            connection.execute(source_schema_sql())
    except (ValueError, psycopg.Error) as error:
        code = getattr(error, "sqlstate", None) or "CONNECTION_OR_CONFIG"
        raise SystemExit(
            f"Source 테이블 생성 실패 ({code}). 기존 적용 여부·KG 테이블·접속 권한을 확인해 주세요."
        ) from None
    print(
        "Source 테이블 생성 완료: source_documents, source_snapshots, evidence, "
        "fact_evidence, relation_evidence"
    )


if __name__ == "__main__":
    main()
