"""평가에서 재사용하는 합성 Knowledge Graph fixture."""

from datetime import UTC, datetime
from uuid import UUID

from apolo.contracts.knowledge import (
    ActiveKnowledgeEntity,
    ActiveKnowledgeFact,
    ActiveKnowledgeGraph,
    ActiveKnowledgeRelation,
)

NOW = datetime(2026, 9, 27, tzinfo=UTC)
GRAPH_ID = UUID("00000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("00000000-0000-0000-0000-000000000002")
WORK_ID = UUID("00000000-0000-0000-0000-000000000003")
EXPERIENCE_ID = UUID("00000000-0000-0000-0000-000000000004")


def build_synthetic_graph() -> ActiveKnowledgeGraph:
    """Person·Work·Experience만 포함한 평가용 KG 생성"""
    entities = [
        ActiveKnowledgeEntity(
            id=PERSON_ID,
            graph_id=GRAPH_ID,
            class_type="Person",
            created_at=NOW,
            updated_at=NOW,
        ),
        ActiveKnowledgeEntity(
            id=WORK_ID,
            graph_id=GRAPH_ID,
            class_type="Work",
            created_at=NOW,
            updated_at=NOW,
        ),
        ActiveKnowledgeEntity(
            id=EXPERIENCE_ID,
            graph_id=GRAPH_ID,
            class_type="Experience",
            created_at=NOW,
            updated_at=NOW,
        ),
    ]
    relations = [
        ActiveKnowledgeRelation(
            id=UUID("00000000-0000-0000-0000-000000000011"),
            graph_id=GRAPH_ID,
            subject_entity_id=PERSON_ID,
            predicate="participatedIn",
            object_entity_id=WORK_ID,
            origin="user",
            provenance="profile",
            updated_at=NOW,
        ),
        ActiveKnowledgeRelation(
            id=UUID("00000000-0000-0000-0000-000000000012"),
            graph_id=GRAPH_ID,
            subject_entity_id=PERSON_ID,
            predicate="hasExperience",
            object_entity_id=EXPERIENCE_ID,
            origin="user",
            provenance="profile",
            updated_at=NOW,
        ),
    ]
    facts = [
        ActiveKnowledgeFact(
            id=UUID("00000000-0000-0000-0000-000000000021"),
            entity_id=WORK_ID,
            predicate="title",
            value="APolo",
            value_type="string",
            origin="user",
            provenance="profile",
            updated_at=NOW,
        ),
        ActiveKnowledgeFact(
            id=UUID("00000000-0000-0000-0000-000000000022"),
            entity_id=WORK_ID,
            predicate="kind",
            value="project",
            value_type="string",
            origin="user",
            provenance="profile",
            updated_at=NOW,
        ),
    ]
    return ActiveKnowledgeGraph(
        id=GRAPH_ID,
        user_id=1,
        ontology_schema_version="1.1",
        version=1,
        created_at=NOW,
        updated_at=NOW,
        entities=entities,
        facts=facts,
        relations=relations,
    )
