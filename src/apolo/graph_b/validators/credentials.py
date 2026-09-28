"""Awards·Certification 블록의 Credential KG 근거 검증"""

from apolo.contracts.generate import AwardItem, CertificationItem
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import (
    entity_facts,
    fact_values,
    format_output_date,
    item_entity_id,
)


def validate_award_item(
    issues: list[ContentValidationIssue],
    item: AwardItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Awards 값이 award Credential의 근거와 일치하는지 검증한다"""

    _validate_credential_item(issues, item, graph, item_path, expected_kind="award")


def validate_certification_item(
    issues: list[ContentValidationIssue],
    item: CertificationItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Certification 값이 certification Credential의 근거와 일치하는지 검증한다"""

    _validate_credential_item(issues, item, graph, item_path, expected_kind="certification")
    facts = _credential_facts(item, graph)
    if facts is None or item.grade is None:
        return
    _validate_value(
        issues,
        item.grade,
        fact_values(facts, "grade"),
        f"{item_path}.grade",
        "CERTIFICATION_GRADE_UNSUPPORTED",
        "Certification grade가 KG의 근거와 일치하지 않습니다.",
    )


def _validate_credential_item(
    issues: list[ContentValidationIssue],
    item: AwardItem | CertificationItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
    *,
    expected_kind: str,
) -> None:
    facts = _credential_facts(item, graph)
    if facts is None:
        return
    _validate_value(
        issues,
        item.title,
        fact_values(facts, "title"),
        f"{item_path}.title",
        "CREDENTIAL_TITLE_UNSUPPORTED",
        "Credential title이 KG의 근거와 일치하지 않습니다.",
    )
    _validate_value(
        issues,
        expected_kind,
        fact_values(facts, "kind"),
        f"{item_path}.kind",
        "CREDENTIAL_KIND_MISMATCH",
        "블록 종류와 Credential kind가 일치하지 않습니다.",
    )

    if item.issuer is not None:
        _validate_value(
            issues,
            item.issuer,
            fact_values(facts, "issuerName"),
            f"{item_path}.issuer",
            "CREDENTIAL_ISSUER_UNSUPPORTED",
            "Credential issuer가 KG의 근거와 일치하지 않습니다.",
        )

    if item.date is not None:
        supported_dates = {
            format_output_date(fact.value)
            for fact in facts
            if fact.predicate == "date" and isinstance(fact.value, str)
        }
        _validate_value(
            issues,
            item.date,
            supported_dates,
            f"{item_path}.date",
            "CREDENTIAL_DATE_UNSUPPORTED",
            "Credential date가 KG의 근거와 일치하지 않습니다.",
        )


def _credential_facts(item: AwardItem | CertificationItem, graph: ActiveKnowledgeGraph):
    """출력 item이 참조한 Credential의 Fact를 반환한다"""

    entity_id = item_entity_id(item.entity_id)
    if entity_id is None:
        return None
    return entity_facts(graph, entity_id)


def _validate_value(
    issues: list[ContentValidationIssue],
    value: str,
    supported_values: set[str],
    path: str,
    code: str,
    message: str,
) -> None:
    """출력값이 해당 KG Fact 값인지 확인한다"""

    if value not in supported_values:
        issues.append(ContentValidationIssue(path=path, code=code, message=message))
