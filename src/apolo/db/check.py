"""uv run python -m apolo.db.check 로 로컬 DB 접속을 확인한다."""

import psycopg

from apolo.db.connection import connect_db


def main() -> None:
    try:
        with connect_db() as connection:
            row = connection.execute(
                "SELECT 1, current_user, current_database(), current_schema()"
            ).fetchone()
            assert row is not None
            result, user, database, schema = row
            if schema != "ai":
                raise ValueError("ai 스키마의 존재 여부와 USAGE 권한을 확인해 주세요.")
    except (ValueError, psycopg.Error):
        # 접속 오류 원문에 포함될 수 있는 접속 정보를 출력하지 않는다.
        raise SystemExit(
            "DB 연결 확인 실패: Docker 실행, .env 접속 정보, ai 스키마 권한을 확인해 주세요."
        ) from None

    print(f"SELECT 1: {result}")
    print(f"user={user}, database={database}, schema={schema}")


if __name__ == "__main__":
    main()
