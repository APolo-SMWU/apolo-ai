"""Graph B 출력의 구조와 KG 참조를 결정적으로 검증한다."""

import re
from dataclasses import dataclass
from uuid import UUID

from apolo.contracts.content import GraphBOutput
from apolo.contracts.generate import (
    ActivitiesBlock,
    ActivityItem,
    EducationBlock,
    EducationItem,
    ExperienceBlock,
    ExperienceItem,
    SkillsBlock,
    TimelineBlock,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph


@dataclass(frozen=True)
class ContentValidationIssue:
    """콘텐츠 저장·응답을 보류한 이유"""

    path: str
    code: str
    message: str


_TIMELINE_ENTITY_TYPES = {
    "education": frozenset({"Education"}),
    "experience": frozenset({"Experience"}),
    "activities": frozenset({"Activity"}),
    "awards": frozenset({"Credential"}),
    "certification": frozenset({"Credential"}),
}


def validate_graph_b_output(
    output: GraphBOutput, graph: ActiveKnowledgeGraph
) -> list[ContentValidationIssue]:
    """Graph B 블록의 Entity 참조·중복·빈 블록을 검증한다."""
    entity_types = {str(entity.id): entity.class_type for entity in graph.entities}
    issues: list[ContentValidationIssue] = []
    referenced_ids: set[str] = set()

    for block_index, block in enumerate(output.blocks):
        block_path = f"blocks[{block_index}]"
        if isinstance(block, (EducationBlock, ExperienceBlock, ActivitiesBlock, TimelineBlock)):
            expected_type = _TIMELINE_ENTITY_TYPES[block.type]
            if not block.items:
                issues.append(
                    ContentValidationIssue(
                        path=block_path,
                        code="EMPTY_BLOCK",
                        message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
                    )
                )
            education_items: set[tuple[str, str | None, str | None, str, str | None]] = set()
            for item_index, item in enumerate(block.items):
                item_path = f"{block_path}.items[{item_index}]"
                _validate_entity_reference(
                    issues,
                    referenced_ids,
                    entity_types,
                    item.entity_id,
                    expected_type,
                    f"{item_path}.entityId",
                    allow_duplicate=isinstance(block, EducationBlock),
                )
                if isinstance(block, EducationBlock):
                    fingerprint = (
                        item.entity_id,
                        item.start_date,
                        item.end_date,
                        item.organization,
                        item.role,
                    )
                    if fingerprint in education_items:
                        issues.append(
                            ContentValidationIssue(
                                path=item_path,
                                code="DUPLICATE_EDUCATION_ITEM",
                                message="같은 Education item을 중복 반환할 수 없습니다.",
                            )
                        )
                    education_items.add(fingerprint)
                    _validate_education_item(issues, item, graph, item_path)
                elif isinstance(block, ExperienceBlock):
                    _validate_experience_item(issues, item, graph, item_path)
                elif isinstance(block, ActivitiesBlock):
                    _validate_activity_item(issues, item, graph, item_path)
        elif isinstance(block, WorksBlock):
            if not block.items:
                issues.append(
                    ContentValidationIssue(
                        path=block_path,
                        code="EMPTY_BLOCK",
                        message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
                    )
                )
            for item_index, item in enumerate(block.items):
                _validate_entity_reference(
                    issues,
                    referenced_ids,
                    entity_types,
                    item.entity_id,
                    frozenset({"Work"}),
                    f"{block_path}.items[{item_index}].entityId",
                )
        elif isinstance(block, SkillsBlock):
            _validate_skill_block(issues, block, block_path)

    return issues


def _validate_entity_reference(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    entity_id: str,
    expected_types: frozenset[str],
    path: str,
    *,
    allow_duplicate: bool = False,
) -> None:
    if entity_id not in entity_types:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="ENTITY_NOT_FOUND",
                message="콘텐츠가 참조한 Entity가 현재 KG에 없습니다.",
            )
        )
        return
    if entity_types[entity_id] not in expected_types:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="ENTITY_TYPE_MISMATCH",
                message="블록 종류와 Entity 유형이 일치하지 않습니다.",
            )
        )
    if entity_id in referenced_ids and not allow_duplicate:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="DUPLICATE_ENTITY_REFERENCE",
                message="같은 Entity를 여러 콘텐츠 항목에서 참조할 수 없습니다.",
            )
        )
    referenced_ids.add(entity_id)


def _validate_skill_block(
    issues: list[ContentValidationIssue], block: SkillsBlock, block_path: str
) -> None:
    categories = block.categories
    if not categories:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 카테고리가 하나 이상 있어야 합니다.",
            )
        )
    for category_index, category in enumerate(categories):
        if not category.items:
            issues.append(
                ContentValidationIssue(
                    path=f"{block_path}.categories[{category_index}]",
                    code="EMPTY_SKILL_CATEGORY",
                    message="기술 카테고리에는 기술이 하나 이상 있어야 합니다.",
                )
            )


def _validate_education_item(
    issues: list[ContentValidationIssue],
    item: EducationItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Education 값이 연결된 KG 근거와 일치하는지 검증한다."""

    try:
        entity_id = UUID(item.entity_id)
    except ValueError:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다.

    facts = [fact for fact in graph.facts if fact.entity_id == entity_id]
    relations = [
        relation
        for relation in graph.relations
        if relation.subject_entity_id == entity_id and relation.predicate == "atOrganization"
    ]
    organization_ids = {relation.object_entity_id for relation in relations}
    organization_names = {
        fact.value
        for fact in graph.facts
        if fact.entity_id in organization_ids and fact.predicate == "name"
    }

    if organization_names and item.organization not in organization_names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="EDUCATION_ORGANIZATION_MISMATCH",
                message="Education organization이 KG의 Organization.name과 일치하지 않습니다.",
            )
        )
    elif not organization_names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="EDUCATION_ORGANIZATION_NOT_FOUND",
                message="Education organization의 KG 근거가 없습니다.",
            )
        )

    date_values = {
        predicate: {
            _format_output_date(fact.value)
            for fact in facts
            if fact.predicate == predicate and isinstance(fact.value, str)
        }
        for predicate in ("start", "end")
    }
    if item.start_date is not None and item.start_date not in date_values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="EDUCATION_START_DATE_UNSUPPORTED",
                message="Education startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        is_current = any(
            fact.predicate == "isCurrent" and fact.value is True for fact in facts
        )
        if not is_current:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="EDUCATION_PRESENT_WITHOUT_CURRENT",
                    message="현재 재학 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in date_values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="EDUCATION_END_DATE_UNSUPPORTED",
                message="Education endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )


def _validate_experience_item(
    issues: list[ContentValidationIssue],
    item: ExperienceItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Experience 값이 연결된 KG 근거와 일치하는지 검증한다."""

    try:
        entity_id = UUID(item.entity_id)
    except ValueError:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다.

    facts = [fact for fact in graph.facts if fact.entity_id == entity_id]
    relations = [
        relation
        for relation in graph.relations
        if relation.subject_entity_id == entity_id and relation.predicate == "atOrganization"
    ]
    organization_ids = {relation.object_entity_id for relation in relations}
    organization_names = {
        fact.value
        for fact in graph.facts
        if fact.entity_id in organization_ids and fact.predicate == "name"
    }

    if item.organization is not None:
        if organization_names and item.organization not in organization_names:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.organization",
                    code="EXPERIENCE_ORGANIZATION_MISMATCH",
                    message="Experience organization이 KG의 Organization.name과 일치하지 않습니다.",
                )
            )
        elif not organization_names:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.organization",
                    code="EXPERIENCE_ORGANIZATION_NOT_FOUND",
                    message="Experience organization의 KG 근거가 없습니다.",
                )
            )

    date_values = {
        predicate: {
            _format_output_date(fact.value)
            for fact in facts
            if fact.predicate == predicate and isinstance(fact.value, str)
        }
        for predicate in ("start", "end")
    }
    if item.start_date is not None and item.start_date not in date_values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="EXPERIENCE_START_DATE_UNSUPPORTED",
                message="Experience startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        is_current = any(
            fact.predicate == "isCurrent" and fact.value is True for fact in facts
        )
        if not is_current:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="EXPERIENCE_PRESENT_WITHOUT_CURRENT",
                    message="현재 재직 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in date_values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="EXPERIENCE_END_DATE_UNSUPPORTED",
                message="Experience endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.kind is not None:
        kind_values = {
            fact.value
            for fact in facts
            if fact.predicate == "kind" and isinstance(fact.value, str)
        }
        if item.kind not in kind_values:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.kind",
                    code="EXPERIENCE_KIND_UNSUPPORTED",
                    message="Experience kind가 KG의 근거와 일치하지 않습니다.",
                )
            )


def _validate_activity_item(
    issues: list[ContentValidationIssue],
    item: ActivityItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Activities 값이 연결된 Activity KG 근거와 일치하는지 검증한다."""

    try:
        entity_id = UUID(item.entity_id)
    except ValueError:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다.

    facts = [fact for fact in graph.facts if fact.entity_id == entity_id]
    relations = [
        relation
        for relation in graph.relations
        if relation.subject_entity_id == entity_id and relation.predicate == "atOrganization"
    ]
    organization_ids = {relation.object_entity_id for relation in relations}
    organization_names = {
        fact.value
        for fact in graph.facts
        if fact.entity_id in organization_ids and fact.predicate == "name"
    }
    activity_names = {
        fact.value for fact in facts if fact.predicate == "name" and isinstance(fact.value, str)
    }
    accepted_organization_values = organization_names or activity_names

    if not accepted_organization_values:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="ACTIVITY_ORGANIZATION_NOT_FOUND",
                message="Activities organization의 KG 근거가 없습니다.",
            )
        )
    elif item.organization not in accepted_organization_values:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="ACTIVITY_ORGANIZATION_MISMATCH",
                message="Activities organization이 KG의 기관명 또는 활동명과 일치하지 않습니다.",
            )
        )

    date_values = {
        predicate: {
            _format_output_date(fact.value)
            for fact in facts
            if fact.predicate == predicate and isinstance(fact.value, str)
        }
        for predicate in ("start", "end")
    }
    if item.start_date is not None and item.start_date not in date_values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="ACTIVITY_START_DATE_UNSUPPORTED",
                message="Activities startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        is_current = any(
            fact.predicate == "isCurrent" and fact.value is True for fact in facts
        )
        if not is_current:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="ACTIVITY_PRESENT_WITHOUT_CURRENT",
                    message="현재 활동 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in date_values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="ACTIVITY_END_DATE_UNSUPPORTED",
                message="Activities endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.role is not None:
        role_values = {
            fact.value for fact in facts if fact.predicate == "role" and isinstance(fact.value, str)
        }
        if item.role not in role_values:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.role",
                    code="ACTIVITY_ROLE_UNSUPPORTED",
                    message="Activities role이 KG의 근거와 일치하지 않습니다.",
                )
            )

    if item.kind is not None:
        kind_values = {
            fact.value for fact in facts if fact.predicate == "kind" and isinstance(fact.value, str)
        }
        if item.kind not in kind_values:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.kind",
                    code="ACTIVITY_KIND_UNSUPPORTED",
                    message="Activities kind가 KG의 근거와 일치하지 않습니다.",
                )
            )


def _format_output_date(value: str) -> str:
    """KG의 ISO 날짜를 Block 출력 형식(YYYY 또는 YYYY.MM)으로 변환한다."""

    match = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-\d{2})?", value)
    if match is None:
        return value
    year, month = match.groups()
    return f"{year}.{month}" if month else year
