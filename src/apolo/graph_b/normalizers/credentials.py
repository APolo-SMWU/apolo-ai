"""수상·자격 item 보정과 중복 제거"""

from apolo.contracts.generate import (
    AwardItem,
    CertificationItem,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.dates import iso_to_output
from apolo.graph_b.normalizers.common import (
    entity_context,
    optional_value,
    required_value,
    valid_dates,
)
from apolo.graph_b.validators.common import (
    fact_values,
)
from apolo.text_similarity import shares_core_terms, similar_title


def normalize_award_items(items: list[AwardItem], graph: ActiveKnowledgeGraph) -> list[AwardItem]:
    normalized = []
    for item in items:
        normalized_item = _normalize_credential_item(item, graph, "award")
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def normalize_certification_items(
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
    context = entity_context(
        graph,
        item.entity_id,
        "awards" if expected_kind == "award" else "certification",
    )
    if context is None:
        return None
    _, facts = context
    if expected_kind not in fact_values(facts, "kind"):
        return None
    title = required_value(item.title, fact_values(facts, "title"))
    if title is None:
        return None
    update = {
        "title": title,
        "issuer": optional_value(item.issuer, fact_values(facts, "issuerName")),
        "date": _credential_date_value(item.date, facts),
    }
    if isinstance(item, CertificationItem):
        update["grade"] = optional_value(item.grade, fact_values(facts, "grade"))
    return item.model_copy(update=update)


def _credential_date_value(value: str | None, facts) -> str | None:
    if value is None:
        return None
    supported = {
        iso_to_output(fact.value) or fact.value
        for fact in facts
        if fact.predicate == "date" and isinstance(fact.value, str)
    }
    return optional_value(value, valid_dates(supported))


def deduplicate_credential_items(
    items: list[AwardItem | CertificationItem],
) -> list[AwardItem | CertificationItem]:
    """같은 자격·수상 항목을 ID 우선, 제목·발급처·날짜 기준으로 합친다"""
    merged: list[AwardItem | CertificationItem] = []
    for item in items:
        match_index = next(
            (
                index
                for index, candidate in enumerate(merged)
                if _same_credential_identity(candidate, item)
            ),
            None,
        )
        if match_index is None:
            merged.append(item)
            continue
        current = merged[match_index]
        representative, other = _representative_credential(current, item)
        update = {}
        for field in ("issuer", "date"):
            if getattr(representative, field) is None:
                update[field] = getattr(other, field)
        if isinstance(representative, CertificationItem) and representative.grade is None:
            update["grade"] = other.grade
        merged[match_index] = representative.model_copy(update=update)
    return merged


def _same_credential_identity(
    current: AwardItem | CertificationItem,
    incoming: AwardItem | CertificationItem,
) -> bool:
    if current.entity_id == incoming.entity_id:
        return True
    if not (
        similar_title(current.title, incoming.title)
        or shares_core_terms(current.title, incoming.title)
    ):
        return False
    if current.date and incoming.date and current.date != incoming.date:
        return False
    if current.issuer and incoming.issuer and not similar_title(current.issuer, incoming.issuer):
        return False
    return True


def _representative_credential(
    current: AwardItem | CertificationItem,
    incoming: AwardItem | CertificationItem,
) -> tuple[AwardItem | CertificationItem, AwardItem | CertificationItem]:
    current_score = sum(
        bool(getattr(current, field, None)) for field in ("issuer", "date", "grade")
    )
    incoming_score = sum(
        bool(getattr(incoming, field, None)) for field in ("issuer", "date", "grade")
    )
    return (incoming, current) if incoming_score > current_score else (current, incoming)
