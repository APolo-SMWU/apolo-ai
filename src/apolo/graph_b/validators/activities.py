"""Activities block의 KG 근거 검증"""

from apolo.contracts.generate import ActivityItem
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


def validate_activity_item(
    issues: list[ContentValidationIssue],
    item: ActivityItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Activities 값이 연결된 Activity KG 근거와 일치하는지 검증한다"""

    entity_id = item_entity_id(item.entity_id)
    if entity_id is None:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다

    facts = entity_facts(graph, entity_id)
    names = organization_names(graph, entity_id)
    activity_names = fact_values(facts, "name")
    accepted_names = names or activity_names
    if not accepted_names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="ACTIVITY_ORGANIZATION_NOT_FOUND",
                message="Activities organization의 KG 근거가 없습니다.",
            )
        )
    elif item.organization not in accepted_names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="ACTIVITY_ORGANIZATION_MISMATCH",
                message="Activities organization이 KG의 기관명 또는 활동명과 일치하지 않습니다.",
            )
        )

    values = date_values(facts)
    if item.start_date is not None and item.start_date not in values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="ACTIVITY_START_DATE_UNSUPPORTED",
                message="Activities startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        if not has_current_fact(facts):
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="ACTIVITY_PRESENT_WITHOUT_CURRENT",
                    message="현재 활동 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="ACTIVITY_END_DATE_UNSUPPORTED",
                message="Activities endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.role is not None and item.role not in fact_values(facts, "role"):
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.role",
                code="ACTIVITY_ROLE_UNSUPPORTED",
                message="Activities role이 KG의 근거와 일치하지 않습니다.",
            )
        )

    if item.kind is not None and item.kind not in fact_values(facts, "kind"):
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.kind",
                code="ACTIVITY_KIND_UNSUPPORTED",
                message="Activities kind가 KG의 근거와 일치하지 않습니다.",
            )
        )
