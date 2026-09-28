"""Experience block의 KG 근거 검증"""

from apolo.contracts.generate import ExperienceItem
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import (
    date_values,
    entity_facts,
    fact_values,
    has_current_fact,
    item_entity_id,
    organization_names,
)


def validate_experience_item(
    issues: list[ContentValidationIssue],
    item: ExperienceItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Experience 값이 연결된 KG 근거와 일치하는지 검증한다"""

    entity_id = item_entity_id(item.entity_id)
    if entity_id is None:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다

    facts = entity_facts(graph, entity_id)
    names = organization_names(graph, entity_id)
    if item.organization is not None:
        if names and item.organization not in names:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.organization",
                    code="EXPERIENCE_ORGANIZATION_MISMATCH",
                    message="Experience organization이 KG의 Organization.name과 일치하지 않습니다.",
                )
            )
        elif not names:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.organization",
                    code="EXPERIENCE_ORGANIZATION_NOT_FOUND",
                    message="Experience organization의 KG 근거가 없습니다.",
                )
            )

    values = date_values(facts)
    if item.start_date is not None and item.start_date not in values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="EXPERIENCE_START_DATE_UNSUPPORTED",
                message="Experience startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        if not has_current_fact(facts):
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="EXPERIENCE_PRESENT_WITHOUT_CURRENT",
                    message="현재 재직 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="EXPERIENCE_END_DATE_UNSUPPORTED",
                message="Experience endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.kind is not None and item.kind not in fact_values(facts, "kind"):
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.kind",
                code="EXPERIENCE_KIND_UNSUPPORTED",
                message="Experience kind가 KG의 근거와 일치하지 않습니다.",
            )
        )
