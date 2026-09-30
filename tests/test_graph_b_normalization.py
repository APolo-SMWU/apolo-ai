from datetime import UTC, datetime
from uuid import uuid4

from apolo.contracts.generate import ActivityItem
from apolo.contracts.knowledge import (
    ActiveKnowledgeEntity,
    ActiveKnowledgeFact,
    ActiveKnowledgeGraph,
    ActiveKnowledgeRelation,
)
from apolo.graph_b.normalization import (
    _merge_timeline_items,
    _normalize_activity_items,
)
from apolo.graph_b.validators.activities import validate_activity_item


def _activity_graph(role_values: list[str]) -> tuple[ActiveKnowledgeGraph, str]:
    now = datetime.now(UTC)
    graph_id, person_id, activity_id = uuid4(), uuid4(), uuid4()
    graph = ActiveKnowledgeGraph(
        id=graph_id,
        user_id=1,
        ontology_schema_version="2.0",
        version=1,
        created_at=now,
        updated_at=now,
        entities=[
            ActiveKnowledgeEntity(
                id=person_id,
                graph_id=graph_id,
                class_type="Person",
                created_at=now,
                updated_at=now,
            ),
            ActiveKnowledgeEntity(
                id=activity_id,
                graph_id=graph_id,
                class_type="Activity",
                created_at=now,
                updated_at=now,
            ),
        ],
        facts=[
            ActiveKnowledgeFact(
                id=uuid4(),
                entity_id=activity_id,
                predicate="name",
                value="빅데이터 연합동아리 BOAZ",
                value_type="string",
                origin="extracted",
                provenance="source",
                updated_at=now,
            ),
            *[
                ActiveKnowledgeFact(
                    id=uuid4(),
                    entity_id=activity_id,
                    predicate="role",
                    value=role,
                    value_type="string",
                    origin="extracted",
                    provenance="source",
                    updated_at=now,
                )
                for role in role_values
            ],
        ],
        relations=[
            ActiveKnowledgeRelation(
                id=uuid4(),
                graph_id=graph_id,
                subject_entity_id=person_id,
                predicate="participatedIn",
                object_entity_id=activity_id,
                origin="extracted",
                provenance="source",
                updated_at=now,
            )
        ],
    )
    return graph, str(activity_id)


def test_activity_normalization_accepts_multiple_role_facts():
    roles = ["25기 분석 부문", "25기 기획팀 운영진"]
    graph, activity_id = _activity_graph(roles)
    item = ActivityItem(
        entity_id=activity_id,
        start_date=None,
        end_date=None,
        organization="빅데이터 연합동아리 BOAZ",
        role=", ".join(roles),
        description="• 분석 데이터 검토",
        kind=None,
    )

    normalized = _normalize_activity_items([item], graph)[0]
    issues = []
    validate_activity_item(issues, normalized, graph, "blocks[0].items[0]")

    assert normalized.role == ", ".join(roles)
    assert not any(issue.code == "ACTIVITY_ROLE_UNSUPPORTED" for issue in issues)


def test_merging_activity_roles_keeps_them_out_of_description():
    roles = ["25기 분석 부문", "25기 기획팀 운영진"]
    graph, activity_id = _activity_graph(roles)
    first = ActivityItem(
        entity_id=activity_id,
        start_date="2025.07",
        end_date="2026.07",
        organization="빅데이터 연합동아리 BOAZ",
        role=roles[0],
        description="• 분석 데이터 검토",
        kind="club",
    )
    second = first.model_copy(update={"role": roles[1], "description": "• 기획 일정 구성"})

    merged = _merge_timeline_items(first, second)

    assert merged.role == ", ".join(roles)
    assert merged.description == "• 분석 데이터 검토 · • 기획 일정 구성"
    assert all(role not in (merged.description or "") for role in roles)
