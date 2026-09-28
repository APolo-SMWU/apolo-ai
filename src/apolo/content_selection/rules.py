"""요구사항에 따라 Graph B 입력 후보 범위를 결정한다
이 단계에서는 명시적인 범주 단어와 KG 관계만 사용해 LLM에 전달할 후보를 줄인다
"""

from dataclasses import dataclass
from uuid import UUID

from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.ontology.personal import ClassType

_CONTENT_CLASSES: frozenset[ClassType] = frozenset(
    {"Education", "Experience", "Activity", "Work", "Credential", "Skill"}
)
_CONTEXT_CLASSES: frozenset[ClassType] = frozenset({"Organization", "Channel", "Skill"})
_SKILL_BRIDGE_CLASSES: frozenset[ClassType] = frozenset({"Work", "Experience"})
_REQUIREMENT_CLASS_TERMS: dict[ClassType, tuple[str, ...]] = {
    "Work": ("프로젝트", "작업", "project", "work"),
    "Skill": ("기술", "스킬", "기술스택", "skill", "stack"),
    "Experience": ("경력", "경험", "career", "experience"),
    "Activity": (
        "활동",
        "대외활동",
        "동아리",
        "봉사",
        "프로그램",
        "발표",
        "activity",
        "activities",
    ),
    "Education": ("학력", "교육", "전공", "education"),
    "Credential": ("수상", "자격", "credential", "award", "certification"),
}


@dataclass(frozen=True)
class ContentSelection:
    """Graph B에 전달할 KG 후보와 선택된 콘텐츠 Entity 유형"""

    graph: ActiveKnowledgeGraph
    selected_classes: frozenset[ClassType]


def select_relevant_knowledge(
    graph: ActiveKnowledgeGraph, requirements: str = ""
) -> ContentSelection:
    """요구사항과 Person에서 연결된 Entity를 기준으로 콘텐츠 후보를 선별한다

    명시적인 범주가 없으면 모든 콘텐츠 Entity를 유지한다
    """
    requested_classes = _classes_from_requirements(requirements)
    selected_content_classes = requested_classes or _CONTENT_CLASSES
    selected_entity_ids = _connected_entity_ids(graph, selected_content_classes)

    entities = [entity for entity in graph.entities if entity.id in selected_entity_ids]
    facts = [fact for fact in graph.facts if fact.entity_id in selected_entity_ids]
    relations = [
        relation
        for relation in graph.relations
        if relation.subject_entity_id in selected_entity_ids
        and relation.object_entity_id in selected_entity_ids
    ]
    selected_graph = graph.model_copy(
        update={"entities": entities, "facts": facts, "relations": relations}
    )
    output_classes = requested_classes or _CONTENT_CLASSES
    return ContentSelection(
        graph=selected_graph,
        selected_classes=frozenset(
            entity.class_type for entity in entities if entity.class_type in output_classes
        ),
    )


def _classes_from_requirements(requirements: str) -> frozenset[ClassType]:
    normalized = requirements.casefold()
    return frozenset(
        class_type
        for class_type, terms in _REQUIREMENT_CLASS_TERMS.items()
        if any(term.casefold() in normalized for term in terms)
    )


def _connected_entity_ids(
    graph: ActiveKnowledgeGraph, selected_content_classes: frozenset[ClassType]
) -> set[UUID]:
    entities_by_id = {entity.id: entity for entity in graph.entities}
    selected_ids = {entity.id for entity in graph.entities if entity.class_type == "Person"}

    bridge_classes = _SKILL_BRIDGE_CLASSES if "Skill" in selected_content_classes else frozenset()
    traversable_classes = _CONTEXT_CLASSES | selected_content_classes | bridge_classes
    changed = True
    while changed:
        changed = False
        for relation in graph.relations:
            # Person에서 관계 방향을 따라 확장하고 Organization에서 콘텐츠로 역추적하지 않는다
            if (
                relation.subject_entity_id in selected_ids
                and relation.object_entity_id not in selected_ids
            ):
                object_entity = entities_by_id.get(relation.object_entity_id)
                if object_entity and object_entity.class_type in traversable_classes:
                    selected_ids.add(relation.object_entity_id)
                    changed = True
    return selected_ids
