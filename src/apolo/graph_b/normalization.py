"""Graph B 출력을 현재 KG의 정규값에 맞춰 안전하게 정리한다"""

import re
from collections import defaultdict
from uuid import UUID

from apolo.contracts.content import GraphBOutput
from apolo.contracts.generate import (
    AboutBlock,
    ActivitiesBlock,
    ActivityItem,
    AwardItem,
    AwardsBlock,
    CertificationBlock,
    CertificationItem,
    EducationBlock,
    EducationItem,
    ExperienceBlock,
    ExperienceItem,
    SkillCategory,
    SkillItem,
    SkillsBlock,
    WorkItem,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validators.common import (
    date_values,
    entity_facts,
    fact_values,
    has_current_fact,
    item_entity_id,
    organization_names,
)
from apolo.graph_b.validators.skill_content import _supported_skills_by_category

_BLOCK_RELATIONS = {
    "education": ("Education", "hasEducation"),
    "experience": ("Experience", "hasExperience"),
    "activities": ("Activity", "participatedIn"),
    "works": ("Work", "participatedIn"),
    "awards": ("Credential", "holds"),
    "certification": ("Credential", "holds"),
}
_EXPERIENCE_KINDS = {"fulltime", "contract", "intern", "research"}
_ACTIVITY_KINDS = {"club", "volunteer", "program", "talk"}
_OUTPUT_DATE = re.compile(r"^[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?$")


def normalize_graph_b_output(
    output: GraphBOutput, graph: ActiveKnowledgeGraph
) -> GraphBOutput:
    """LLM 표현을 KG 근거에 맞춰 보정하고 근거 없는 item을 제거한다"""

    normalized_blocks = []
    about_seen = False
    for block in output.blocks:
        if isinstance(block, AboutBlock):
            if not about_seen:
                normalized_blocks.append(block)
                about_seen = True
            continue
        if isinstance(block, EducationBlock):
            items = _normalize_education_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, ExperienceBlock):
            items = _normalize_experience_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, ActivitiesBlock):
            items = _normalize_activity_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, AwardsBlock):
            items = _normalize_award_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, CertificationBlock):
            items = _normalize_certification_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, WorksBlock):
            items = _normalize_work_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, SkillsBlock):
            categories = _normalize_skill_categories(block, graph)
            if categories:
                normalized_blocks.append(
                    block.model_copy(update={"categories": categories})
                )

    if not about_seen:
        normalized_blocks.insert(0, AboutBlock(description=""))
    return GraphBOutput(blocks=normalized_blocks)


def _normalize_education_items(
    items: list[EducationItem], graph: ActiveKnowledgeGraph
) -> list[EducationItem]:
    normalized = []
    for item in items:
        context = _entity_context(graph, item.entity_id, "education")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        organization = _required_value(item.organization, names)
        if organization is None:
            continue
        normalized.append(
            item.model_copy(
                update={
                    "organization": organization,
                    "start_date": _date_value(item.start_date, facts, "start"),
                    "end_date": _end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def _normalize_experience_items(
    items: list[ExperienceItem], graph: ActiveKnowledgeGraph
) -> list[ExperienceItem]:
    normalized = []
    for item in items:
        context = _entity_context(graph, item.entity_id, "experience")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        normalized.append(
            item.model_copy(
                update={
                    "organization": _optional_value(item.organization, names),
                    "role": _optional_value(item.role, fact_values(facts, "role")),
                    "kind": _optional_value(
                        item.kind, fact_values(facts, "kind") & _EXPERIENCE_KINDS
                    ),
                    "start_date": _date_value(item.start_date, facts, "start"),
                    "end_date": _end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def _normalize_activity_items(
    items: list[ActivityItem], graph: ActiveKnowledgeGraph
) -> list[ActivityItem]:
    normalized = []
    for item in items:
        context = _entity_context(graph, item.entity_id, "activities")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        candidates = names or fact_values(facts, "name")
        organization = _required_value(item.organization, candidates)
        if organization is None:
            continue
        normalized.append(
            item.model_copy(
                update={
                    "organization": organization,
                    "role": _optional_value(item.role, fact_values(facts, "role")),
                    "kind": _optional_value(
                        item.kind, fact_values(facts, "kind") & _ACTIVITY_KINDS
                    ),
                    "start_date": _date_value(item.start_date, facts, "start"),
                    "end_date": _end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def _normalize_award_items(
    items: list[AwardItem], graph: ActiveKnowledgeGraph
) -> list[AwardItem]:
    normalized = []
    for item in items:
        normalized_item = _normalize_credential_item(item, graph, "award")
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _normalize_certification_items(
    items: list[CertificationItem], graph: ActiveKnowledgeGraph
) -> list[CertificationItem]:
    normalized = []
    for item in items:
        normalized_item = _normalize_credential_item(item, graph, "certification")
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _normalize_credential_item(
    item: AwardItem | CertificationItem,
    graph: ActiveKnowledgeGraph,
    expected_kind: str,
) -> AwardItem | CertificationItem | None:
    context = _entity_context(
        graph,
        item.entity_id,
        "awards" if expected_kind == "award" else "certification",
    )
    if context is None:
        return None
    _, facts = context
    if expected_kind not in fact_values(facts, "kind"):
        return None
    title = _required_value(item.title, fact_values(facts, "title"))
    if title is None:
        return None
    update = {
        "title": title,
        "issuer": _optional_value(item.issuer, fact_values(facts, "issuerName")),
        "date": _credential_date_value(item.date, facts),
    }
    if isinstance(item, CertificationItem):
        update["grade"] = _optional_value(item.grade, fact_values(facts, "grade"))
    return item.model_copy(update=update)


def _normalize_work_items(
    items: list[WorkItem], graph: ActiveKnowledgeGraph
) -> list[WorkItem]:
    normalized = []
    for item in items:
        context = _entity_context(graph, item.entity_id, "works")
        if context is None:
            continue
        entity_id, facts = context
        title = _required_value(item.title, fact_values(facts, "title"))
        kind = _required_value(item.kind, fact_values(facts, "kind"))
        if title is None or kind not in {"project", "publication", "opensource"}:
            continue
        supported_skills = _work_skill_names(graph, entity_id)
        skills = [skill for skill in item.skills or [] if skill in supported_skills]
        supported_urls = fact_values(facts, "url")
        links = []
        seen_urls: set[str] = set()
        for link in item.links:
            if link.href in supported_urls and link.href not in seen_urls:
                links.append(link)
                seen_urls.add(link.href)
        normalized.append(
            item.model_copy(
                update={
                    "title": title,
                    "kind": kind,
                    "role": _optional_value(item.role, fact_values(facts, "role")),
                    "skills": skills or None,
                    "links": links,
                }
            )
        )
    return normalized


def _normalize_skill_categories(
    block: SkillsBlock, graph: ActiveKnowledgeGraph
) -> list[SkillCategory]:
    supported = _supported_skills_by_category(graph)
    if not supported:
        return []
    categories: dict[str, list[SkillItem]] = defaultdict(list)
    for category in block.categories:
        category_name = _category_value(category.category, supported)
        if category_name is None:
            continue
        supported_items = supported[category_name]
        seen_ids = {item.entity_id for item in categories[category_name]}
        for item in category.items:
            if item.entity_id not in supported_items or item.entity_id in seen_ids:
                continue
            name = _required_value(item.name, supported_items[item.entity_id])
            if name is None:
                continue
            categories[category_name].append(
                item.model_copy(update={"name": name})
            )
            seen_ids.add(item.entity_id)
    return [
        SkillCategory(category=category, items=items)
        for category, items in categories.items()
        if items
    ]


def _entity_context(
    graph: ActiveKnowledgeGraph, entity_id_value: str, block_type: str
) -> tuple[UUID, list] | None:
    entity_id = item_entity_id(entity_id_value)
    if entity_id is None:
        return None
    entity_type, relation = _BLOCK_RELATIONS[block_type]
    entity = next((item for item in graph.entities if item.id == entity_id), None)
    if entity is None or entity.class_type != entity_type:
        return None
    person_ids = {item.id for item in graph.entities if item.class_type == "Person"}
    if not any(
        item.subject_entity_id in person_ids
        and item.object_entity_id == entity_id
        and item.predicate == relation
        for item in graph.relations
    ):
        return None
    return entity_id, entity_facts(graph, entity_id)


def _required_value(value: str, candidates: set[str]) -> str | None:
    if value in candidates:
        return value
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _optional_value(value: str | None, candidates: set[str]) -> str | None:
    if value is None:
        return None
    return _required_value(value, candidates)


def _date_value(value: str | None, facts, predicate: str) -> str | None:
    if value is None:
        return None
    return _optional_value(value, _valid_dates(date_values(facts)[predicate]))


def _end_date_value(value: str | None, facts) -> str | None:
    if value is None:
        return None
    if value == "Present":
        return "Present" if has_current_fact(facts) else None
    return _optional_value(value, _valid_dates(date_values(facts)["end"]))


def _credential_date_value(value: str | None, facts) -> str | None:
    if value is None:
        return None
    supported = {
        format_value
        for format_value in (
            _format_date(fact.value)
            for fact in facts
            if fact.predicate == "date" and isinstance(fact.value, str)
        )
    }
    return _optional_value(value, _valid_dates(supported))


def _valid_dates(values: set[str]) -> set[str]:
    return {value for value in values if _OUTPUT_DATE.fullmatch(value)}


def _format_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) >= 2 and len(parts[0]) == 4 and len(parts[1]) == 2:
        return f"{parts[0]}.{parts[1]}"
    return parts[0] if parts and len(parts[0]) == 4 else value


def _work_skill_names(graph: ActiveKnowledgeGraph, work_id: UUID) -> set[str]:
    skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.subject_entity_id == work_id and relation.predicate == "usesSkill"
    }
    return {
        fact.value
        for fact in graph.facts
        if fact.entity_id in skill_ids
        and fact.predicate == "name"
        and isinstance(fact.value, str)
    }


def _category_value(value: str, supported: dict[str, dict[str, set[str]]]) -> str | None:
    if value in supported:
        return value
    if len(supported) == 1:
        return next(iter(supported))
    return None
