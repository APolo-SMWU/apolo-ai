"""Education block의 KG 근거 검증"""

from apolo.contracts.generate import EducationItem
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import (
    date_values,
    entity_facts,
    has_current_fact,
    item_entity_id,
    organization_names,
)


def validate_education_item(
    issues: list[ContentValidationIssue],
    item: EducationItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Education 값이 연결된 KG 근거와 일치하는지 검증한다"""

    entity_id = item_entity_id(item.entity_id)
    if entity_id is None:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다

    facts = entity_facts(graph, entity_id)
    names = organization_names(graph, entity_id)
    if names and item.organization not in names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="EDUCATION_ORGANIZATION_MISMATCH",
                message="Education organization이 KG의 Organization.name과 일치하지 않습니다.",
            )
        )
    elif not names:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.organization",
                code="EDUCATION_ORGANIZATION_NOT_FOUND",
                message="Education organization의 KG 근거가 없습니다.",
            )
        )

    values = date_values(facts)
    if item.start_date is not None and item.start_date not in values["start"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.startDate",
                code="EDUCATION_START_DATE_UNSUPPORTED",
                message="Education startDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )

    if item.end_date == "Present":
        if not has_current_fact(facts):
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.endDate",
                    code="EDUCATION_PRESENT_WITHOUT_CURRENT",
                    message="현재 재학 근거가 없으면 endDate에 Present를 사용할 수 없습니다.",
                )
            )
    elif item.end_date is not None and item.end_date not in values["end"]:
        issues.append(
            ContentValidationIssue(
                path=f"{item_path}.endDate",
                code="EDUCATION_END_DATE_UNSUPPORTED",
                message="Education endDate가 KG의 기간 근거와 일치하지 않습니다.",
            )
        )
