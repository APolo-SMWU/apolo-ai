"""프로필 전용 Seed KG의 저장·조회·갱신."""

import psycopg
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.seed.validation import SeedValidationIssue, validate_seed_graph


class InvalidSeedGraphError(ValueError):
    """저장을 차단한 KG 검증 오류. issues에서 위치와 이유를 확인할 수 있다."""

    def __init__(self, issues: list[SeedValidationIssue]) -> None:
        self.issues = issues
        super().__init__(f"Seed KG 검증 실패: {len(issues)}개 오류")


def load_seed_by_user_id(connection: psycopg.Connection, user_id: int) -> SeedKnowledgeGraph | None:
    """현재 Seed 범위의 KG를 조회한다. 없으면 None, 잘못된 저장 데이터는 오류로 반환한다.

    한 SQL 문으로 같은 시점의 KG·Entity·Fact·Relation을 읽는다.
    목록은 ID 순서이며 최초 입력 순서를 의미하지 않는다.
    외부 추출·철회 데이터가 섞인 전체 KG 조회는 추후 별도 모델로 확장해야 한다.
    연결과 트랜잭션의 종료는 호출부 책임이다.
    """
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """
            SELECT (to_jsonb(g) || jsonb_build_object(
                'entities', COALESCE((
                    SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
                    FROM ai.entities e WHERE e.graph_id = g.id
                ), '[]'::jsonb),
                'facts', COALESCE((
                    SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id)
                    FROM ai.facts f
                    JOIN ai.entities e ON e.id = f.entity_id
                    WHERE e.graph_id = g.id
                ), '[]'::jsonb),
                'relations', COALESCE((
                    SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)
                    FROM ai.relations r WHERE r.graph_id = g.id
                ), '[]'::jsonb)
            ))::text
            FROM ai.knowledge_graphs g WHERE g.user_id = %s
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    seed = SeedKnowledgeGraph.model_validate_json(row[0])
    issues = validate_seed_graph(seed)
    if issues:
        raise InvalidSeedGraphError(issues)
    return seed


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
        _insert_seed_items(cursor, seed)


def _insert_seed_items(cursor: psycopg.Cursor, seed: SeedKnowledgeGraph) -> None:
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


class SeedVersionConflictError(ValueError):
    """읽은 이후 KG가 변경되었거나 삭제되어 갱신할 수 없다."""


def update_profile_seed(
    connection: psycopg.Connection,
    existing: SeedKnowledgeGraph,
    updated: SeedKnowledgeGraph,
) -> None:
    """갱신 규칙으로 만든 결과를 한 트랜잭션으로 반영한다. 프로필 전용 KG에 한정한다.

    모든 KG 갱신자는 버전 확인/증가 규칙을 따라야 한다.
    충돌 시 호출부가 최신 KG를 다시 읽고 갱신 결과를 계산해야 한다.
    기존 트랜잭션 안에서는 최종 commit을 호출부가 담당한다.
    """
    for seed in (existing, updated):
        issues = validate_seed_graph(seed)
        if issues:
            raise InvalidSeedGraphError(issues)
    if (
        updated.id != existing.id
        or updated.user_id != existing.user_id
        or updated.created_at != existing.created_at
        or updated.ontology_schema_version != existing.ontology_schema_version
        or updated.version != existing.version + 1
        or updated.updated_at < existing.updated_at
    ):
        raise ValueError("KG 식별 정보는 유지하고 버전은 정확히 1 증가시켜야 합니다.")

    old_entities = {e.id: e for e in existing.entities}
    new_entities = {e.id: e for e in updated.entities}
    old_facts = {f.id: f for f in existing.facts}
    new_facts = {f.id: f for f in updated.facts}
    old_relations = {r.id: r for r in existing.relations}
    new_relations = {r.id: r for r in updated.relations}
    # 변경된 Fact/Relation만 같은 ID로 다시 넣고, 변경 없는 행은 건드리지 않는다.
    remove_facts = [key for key, item in old_facts.items() if new_facts.get(key) != item]
    remove_relations = [
        key for key, item in old_relations.items() if new_relations.get(key) != item
    ]
    additions = updated.model_copy(
        update={
            "entities": [e for e in updated.entities if e.id not in old_entities],
            "facts": [f for f in updated.facts if old_facts.get(f.id) != f],
            "relations": [r for r in updated.relations if old_relations.get(r.id) != r],
        }
    )

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE ai.knowledge_graphs SET version=%s, updated_at=%s "
            "WHERE id=%s AND user_id=%s AND version=%s",
            (updated.version, updated.updated_at, existing.id, existing.user_id, existing.version),
        )
        if cursor.rowcount != 1:
            raise SeedVersionConflictError("KG가 변경되었습니다. 최신 KG를 다시 조회해 주세요.")
        cursor.execute(
            "DELETE FROM ai.relations WHERE graph_id=%s AND id=ANY(%s)",
            (existing.id, remove_relations),
        )
        cursor.execute(
            "DELETE FROM ai.facts f USING ai.entities e "
            "WHERE f.entity_id=e.id AND e.graph_id=%s AND f.id=ANY(%s)",
            (existing.id, remove_facts),
        )
        cursor.execute(
            "DELETE FROM ai.entities WHERE graph_id=%s AND id=ANY(%s)",
            (existing.id, list(old_entities.keys() - new_entities.keys())),
        )
        cursor.executemany(
            "UPDATE ai.entities SET class_type=%s, status=%s, created_at=%s, updated_at=%s "
            "WHERE id=%s AND graph_id=%s",
            [
                (e.class_type, e.status, e.created_at, e.updated_at, e.id, updated.id)
                for e in updated.entities
                if e.id in old_entities and old_entities[e.id] != e
            ],
        )
        _insert_seed_items(cursor, additions)
