"""환경변수를 이용한 PostgreSQL 연결. import 시에는 접속하지 않는다."""

import os

import psycopg
from dotenv import load_dotenv


def connect_db() -> psycopg.Connection:
    """호출부에서 with connect_db() as connection 형태로 사용한다.

    정상 종료 시 commit, 예외 발생 시 rollback하고 연결을 닫는다.
    search_path는 기본 조회 경로일 뿐 접근 권한 제한을 대신하지 않는다.
    """
    load_dotenv()
    password = os.getenv("AI_DB_PASSWORD")
    if not password:
        raise ValueError(".env에 AI_DB_PASSWORD를 설정해 주세요.")

    return psycopg.connect(
        host=os.getenv("AI_DB_HOST", "127.0.0.1"),
        port=os.getenv("AI_DB_PORT", "5432"),
        dbname=os.getenv("AI_DB_NAME", "apolo_dev"),
        user=os.getenv("AI_DB_USER", "apolo_ai"),
        password=password,
        connect_timeout=5,
        options="-c search_path=ai,pg_catalog",
    )
