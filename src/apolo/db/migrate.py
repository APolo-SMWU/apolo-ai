"""uv run python -m apolo.db.migrate 009 처럼 sql/ 의 번호 하나를 적용한다."""

import sys
from pathlib import Path

import psycopg

from apolo.db.connection import connect_db

SQL_DIR = Path(__file__).parent / "sql"

# 번호 → (성공 문구, 실패 문구 앞부분, 확인할 점)
MIGRATIONS: dict[str, tuple[str, str, str]] = {
    "001": (
        "KG 테이블 생성 완료: ai.knowledge_graphs, ai.entities, ai.facts, ai.relations",
        "KG 테이블 생성 실패",
        "접속 정보와 ai 스키마 CREATE 권한을 확인해 주세요.",
    ),
    "002": (
        "Source 테이블 생성 완료: source_documents, source_snapshots, evidence, "
        "fact_evidence, relation_evidence",
        "Source 테이블 생성 실패",
        "기존 적용 여부·KG 테이블·접속 권한을 확인해 주세요.",
    ),
    "003": (
        "Evidence 원문 해시 컬럼 생성 완료: ai.evidence.source_content_hash",
        "Evidence hash 마이그레이션 실패",
        "기존 Evidence 유무와 DB 접속 정보를 확인해 주세요.",
    ),
    "004": (
        "Fact·Relation 출처 컬럼 생성 완료: ai.facts.provenance, ai.relations.provenance",
        "Fact·Relation 출처 마이그레이션 실패",
        "기존 추출 데이터 유무와 DB 접속 정보를 확인해 주세요.",
    ),
    "005": (
        "온톨로지 1.1 적용 완료: Class·Relation·값 타입 확장, entity_keys, 분석 해시, KG 버전",
        "온톨로지 1.1 마이그레이션 실패",
        "004 적용 여부와 DB 접속 정보를 확인해 주세요.",
    ),
    "006": (
        "온톨로지 2.0 적용 완료: Activity 추가, 폐기 속성 정리, KG 버전 2.0",
        "온톨로지 2.0 마이그레이션 실패",
        "005 적용 여부와 기존 KG 버전을 확인해 주세요.",
    ),
    "007": (
        "Entity Evidence 마이그레이션 완료: ai.entity_evidence",
        "Entity Evidence 마이그레이션 실패",
        "Source Evidence 테이블과 KG 2.0 적용 여부를 확인해 주세요.",
    ),
    "008": (
        "온톨로지 2.1 적용 완료: Source 분석 버전 기록, 이전 Skill category 정리, KG 버전 2.1",
        "온톨로지 2.1 마이그레이션 실패",
        "007 적용 여부와 기존 KG 버전을 확인해 주세요.",
    ),
    "009": (
        "파일 Source 마이그레이션 완료: ai.source_documents.source_type에 file 추가",
        "파일 Source 마이그레이션 실패",
        "source_documents_source_type_check 제약 조건 이름을 확인해 주세요.",
    ),
}


def migration_sql(number: str) -> str:
    (path,) = SQL_DIR.glob(f"{number}_*.sql")
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in MIGRATIONS:
        raise SystemExit(
            "사용법: uv run python -m apolo.db.migrate <번호>\n"
            f"번호: {', '.join(MIGRATIONS)}"
        )
    number = args[0]
    done, failed, hint = MIGRATIONS[number]
    try:
        # SQL 파일 하나를 한 트랜잭션으로 처리한다. 하나라도 실패하면 전체 롤백한다.
        with connect_db() as connection:
            connection.execute(migration_sql(number))
    except (ValueError, psycopg.Error) as error:
        if number == "001" and isinstance(error, psycopg.errors.DuplicateTable):
            raise SystemExit(
                "KG 테이블 또는 인덱스가 이미 있습니다. 기존 구조를 확인해 주세요."
            ) from None
        code = getattr(error, "sqlstate", None)
        if number == "005" and code == "PZ005":
            raise SystemExit(error.diag.message_primary) from None
        raise SystemExit(f"{failed} ({code or 'CONNECTION_OR_CONFIG'}). {hint}") from None
    print(done)


if __name__ == "__main__":
    main()
