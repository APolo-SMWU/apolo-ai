"""검증된 Seed KG의 최초 저장. 기존 KG 갱신·중복 병합은 별도로 처리한다."""

import psycopg
from psycopg.types.json import Jsonb

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.seed.validation import SeedValidationIssue, validate_seed_graph


class InvalidSeedGraphError(ValueError):
    """저장을 차단한 KG 검증 오류. issues에서 위치와 이유를 확인할 수 있다."""

    def __init__(self, issues: list[SeedValidationIssue]) -> None:
        self.issues = issues
        super().__init__(f"Seed KG 검증 실패: {len(issues)}개 오류")


def save_initial_seed(connection: psycopg.Connection, seed: SeedKnowledgeGraph) -> None:
    """KG 전체를 원자적으로 INSERT한다. ID·버전·입력 객체는 변경하지 않는다.

    기존 사용자/ID 충돌을 포함한 DB 오류는 호출부로 전달한다.
    기존 트랜잭션 안에서는 savepoint를 사용하므로 최종 commit은 호출부 책임이다.
    트랜잭션이 없는 연결에서는 이 함수의 정상 종료 시 commit한다.
    연결 생성·종료는 호출부 책임이다.
    """
    issues = validate_seed_graph(seed)
    if issues:
        raise InvalidSeedGraphError(issues)

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO ai.knowledge_graphs "
            "(id, user_id, ontology_schema_version, version, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                seed.id,
                seed.user_id,
                seed.ontology_schema_version,
                seed.version,
                seed.created_at,
                seed.updated_at,
            ),
        )
        cursor.executemany(
            "INSERT INTO ai.entities "
            "(id, graph_id, class_type, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (e.id, e.graph_id, e.class_type, e.status, e.created_at, e.updated_at)
                for e in seed.entities
            ],
        )
        cursor.executemany(
            "INSERT INTO ai.facts "
            "(id, entity_id, predicate, value, value_type, origin, confidence, locked, "
            "status, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    f.id,
                    f.entity_id,
                    f.predicate,
                    Jsonb(f.value),
                    f.value_type,
                    f.origin,
                    f.confidence,
                    f.locked,
                    f.status,
                    f.updated_at,
                )
                for f in seed.facts
            ],
        )
        cursor.executemany(
            "INSERT INTO ai.relations "
            "(id, graph_id, subject_entity_id, predicate, object_entity_id, origin, "
            "confidence, locked, status, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    r.id,
                    r.graph_id,
                    r.subject_entity_id,
                    r.predicate,
                    r.object_entity_id,
                    r.origin,
                    r.confidence,
                    r.locked,
                    r.status,
                    r.updated_at,
                )
                for r in seed.relations
            ],
        )
