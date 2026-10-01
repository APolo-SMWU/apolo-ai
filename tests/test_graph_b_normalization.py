from datetime import UTC, datetime
from uuid import uuid4

from apolo.contracts.generate import ActivityItem, SkillCategory, SkillItem, SkillsBlock
from apolo.contracts.knowledge import (
    ActiveKnowledgeEntity,
    ActiveKnowledgeFact,
    ActiveKnowledgeGraph,
    ActiveKnowledgeRelation,
)
from apolo.graph_b.normalization import (
    _merge_timeline_items,
    _normalize_activity_items,
    _normalize_skill_categories,
)
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.activities import validate_activity_item
from apolo.graph_b.validators.skill_content import (
    _supported_skills_by_category,
    validate_skill_content,
)


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


def _skill_graph(names: list[str]) -> tuple[ActiveKnowledgeGraph, dict[str, str]]:
    now = datetime.now(UTC)
    graph_id, person_id = uuid4(), uuid4()
    skill_ids = {name: uuid4() for name in names}
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
            *[
                ActiveKnowledgeEntity(
                    id=skill_id,
                    graph_id=graph_id,
                    class_type="Skill",
                    created_at=now,
                    updated_at=now,
                )
                for skill_id in skill_ids.values()
            ],
        ],
        facts=[
            ActiveKnowledgeFact(
                id=uuid4(),
                entity_id=skill_id,
                predicate="name",
                value=name,
                value_type="string",
                origin="extracted",
                provenance="source",
                updated_at=now,
            )
            for name, skill_id in skill_ids.items()
        ],
        relations=[
            ActiveKnowledgeRelation(
                id=uuid4(),
                graph_id=graph_id,
                subject_entity_id=person_id,
                predicate="hasSkill",
                object_entity_id=skill_id,
                origin="extracted",
                provenance="source",
                updated_at=now,
            )
            for skill_id in skill_ids.values()
        ],
    )
    return graph, {name: str(skill_id) for name, skill_id in skill_ids.items()}


def test_azure_platform_and_services_merge_with_all_entity_ids():
    names = [
        "Azure",
        "Azure AI Search",
        "Microsoft Azure PaaS",
        "Azure Container Instances",
        "Python",
    ]
    graph, ids = _skill_graph(names)
    block = SkillsBlock(
        categories=[
            SkillCategory(
                category="클라우드 & 배포",
                items=[SkillItem(entityIds=[ids[name]], name=name) for name in names],
            )
        ]
    )

    normalized = _normalize_skill_categories(block, graph)
    cloud_items = next(
        category.items
        for category in normalized
        if category.category == "클라우드 & 배포"
    )
    azure = next(item for item in cloud_items if item.name == "Azure")

    assert set(azure.entity_ids) == {ids[name] for name in names[:4]}
    assert len([item for item in cloud_items if item.name == "Azure"]) == 1
    issues: list[ContentValidationIssue] = []
    validate_skill_content(
        issues,
        SkillsBlock(categories=normalized),
        graph,
        "blocks[0]",
    )
    assert issues == []


def test_project_tasks_and_methods_are_excluded_from_skills_only():
    names = [
        "Python",
        "웹 크롤링",
        "크롤링",
        "자연어 전처리",
        "시각화",
        "FGSM",
        "Square Attack",
        "GraphRAG",
        "RAGAS",
        "LangGraph",
    ]
    graph, ids = _skill_graph(names)
    block = SkillsBlock(
        categories=[
            SkillCategory(
                category="기타",
                items=[SkillItem(entityIds=[ids[name]], name=name) for name in names],
            )
        ]
    )

    normalized = _normalize_skill_categories(block, graph)
    displayed_names = {item.name for category in normalized for item in category.items}
    supported = _supported_skills_by_category(graph)
    supported_ids = {skill_id for skills in supported.values() for skill_id in skills}

    assert displayed_names == {"Python", "RAGAS", "LangGraph"}
    assert ids["Python"] in supported_ids
    assert ids["RAGAS"] in supported_ids
    assert ids["LangGraph"] in supported_ids
    assert not ({ids[name] for name in names[1:8]} & supported_ids)
    assert any(category.category == "언어" for category in normalized)
