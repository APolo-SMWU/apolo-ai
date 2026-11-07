"""학력·경력·활동 item 보정과 경력·활동 중복 제거"""

import re
import unicodedata
from uuid import UUID

from apolo.contracts.generate import (
    ActivityItem,
    EducationItem,
    ExperienceItem,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.dates import date_rank
from apolo.graph_b.normalizers.common import (
    date_value,
    end_date_value,
    entity_context,
    labels_share_identity,
    merge_descriptions,
    optional_value,
    required_value,
    text_key,
)
from apolo.graph_b.validators.common import (
    entity_facts,
    fact_values,
    organization_names,
)
from apolo.text_similarity import shares_core_terms, similar_title

_EXPERIENCE_KINDS = {"fulltime", "contract", "intern", "research"}


_ACTIVITY_KINDS = {"club", "volunteer", "program", "talk"}


def normalize_education_items(
    items: list[EducationItem], graph: ActiveKnowledgeGraph
) -> list[EducationItem]:
    normalized = []
    for item in items:
        context = entity_context(graph, item.entity_id, "education")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        organization = required_value(item.organization, names)
        if organization is None:
            continue
        normalized.append(
            item.model_copy(
                update={
                    "organization": organization,
                    "start_date": date_value(item.start_date, facts, "start"),
                    "end_date": end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def normalize_experience_items(
    items: list[ExperienceItem], graph: ActiveKnowledgeGraph
) -> list[ExperienceItem]:
    normalized = []
    for item in items:
        context = entity_context(graph, item.entity_id, "experience")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        normalized.append(
            item.model_copy(
                update={
                    "organization": optional_value(item.organization, names),
                    "role": optional_value(item.role, fact_values(facts, "role")),
                    "kind": optional_value(
                        item.kind, fact_values(facts, "kind") & _EXPERIENCE_KINDS
                    ),
                    "start_date": date_value(item.start_date, facts, "start"),
                    "end_date": end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def normalize_activity_items(
    items: list[ActivityItem], graph: ActiveKnowledgeGraph
) -> list[ActivityItem]:
    normalized = []
    for item in items:
        context = entity_context(graph, item.entity_id, "activities")
        if context is None:
            continue
        entity_id, facts = context
        names = organization_names(graph, entity_id)
        candidates = names or fact_values(facts, "name")
        organization = required_value(item.organization, candidates)
        if organization is None:
            continue
        normalized.append(
            item.model_copy(
                update={
                    "organization": organization,
                    "role": _normalize_activity_role(item.role, fact_values(facts, "role")),
                    "kind": optional_value(item.kind, fact_values(facts, "kind") & _ACTIVITY_KINDS),
                    "start_date": date_value(item.start_date, facts, "start"),
                    "end_date": end_date_value(item.end_date, facts),
                }
            )
        )
    return normalized


def _normalize_activity_role(value: str | None, candidates: set[str]) -> str | None:
    if value is None or value in candidates:
        return value
    supported_parts = {
        text_key(part): part
        for candidate in sorted(candidates)
        for part in _activity_role_parts(candidate)
    }
    parts = _activity_role_parts(value)
    if parts and all(text_key(part) in supported_parts for part in parts):
        canonical_parts = [supported_parts[text_key(part)] for part in parts]
        return _merge_activity_roles(None, ", ".join(canonical_parts))
    return optional_value(value, candidates)


def _activity_role_parts(role: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]+", role) if part.strip()]


def _merge_activity_roles(current: str | None, incoming: str | None) -> str | None:
    """같은 Activity의 중복 결과에서 역할 명칭만 role 필드에 합친다."""
    labels: list[str] = []
    seen: set[str] = set()
    for role in (current, incoming):
        if not role:
            continue
        for label in _activity_role_parts(role):
            key = text_key(label)
            if not label or key in seen:
                continue
            candidate = ", ".join([*labels, label])
            if len(candidate) > 200:
                continue
            labels.append(label)
            seen.add(key)
    return ", ".join(labels) or None


def deduplicate_timeline_items(
    items: list[EducationItem | ExperienceItem | ActivityItem],
    graph: ActiveKnowledgeGraph,
) -> list[EducationItem | ExperienceItem | ActivityItem]:
    """같은 Entity 또는 제목·기관·기간이 유사한 타임라인 항목을 합친다"""

    merged: list[EducationItem | ExperienceItem | ActivityItem] = []
    for item in items:
        match_index = next(
            (
                index
                for index, candidate in enumerate(merged)
                if _same_timeline_identity(candidate, item, graph)
            ),
            None,
        )
        if match_index is None:
            merged.append(item)
            continue
        merged[match_index] = _merge_timeline_items(merged[match_index], item)
    return merged


def _same_timeline_identity(
    current: EducationItem | ExperienceItem | ActivityItem,
    incoming: EducationItem | ExperienceItem | ActivityItem,
    graph: ActiveKnowledgeGraph,
) -> bool:
    if current.entity_id == incoming.entity_id:
        return True

    current_organization = _organization_key(current.organization)
    incoming_organization = _organization_key(incoming.organization)
    if not current_organization or not incoming_organization:
        return False
    if not _organizations_compatible(
        current_organization,
        incoming_organization,
        current.organization or "",
        incoming.organization or "",
    ):
        return False

    current_role = text_key(getattr(current, "role", None))
    incoming_role = text_key(getattr(incoming, "role", None))
    current_kind = text_key(getattr(current, "kind", None))
    incoming_kind = text_key(getattr(incoming, "kind", None))
    if current_kind and incoming_kind and current_kind != incoming_kind:
        return False

    if isinstance(current, ActivityItem) and isinstance(incoming, ActivityItem):
        current_names = fact_values(entity_facts(graph, UUID(current.entity_id)), "name")
        incoming_names = fact_values(entity_facts(graph, UUID(incoming.entity_id)), "name")
        current_labels = _timeline_identity_labels(current, current_names)
        incoming_labels = _timeline_identity_labels(incoming, incoming_names)
        if not labels_share_identity(current_labels, incoming_labels):
            return False
        if current_role and incoming_role and current_role != incoming_role:
            # 다른 KG Entity의 역할 근거는 한 Entity의 item에 합치지 않는다.
            return False
    elif (
        current_role
        and incoming_role
        and not (
            similar_title(current_role, incoming_role)
            or shares_core_terms(current_role, incoming_role)
        )
    ):
        return False

    return _periods_overlap(
        current.start_date,
        current.end_date,
        incoming.start_date,
        incoming.end_date,
    )


def _merge_timeline_items(
    current: EducationItem | ExperienceItem | ActivityItem,
    incoming: EducationItem | ExperienceItem | ActivityItem,
) -> EducationItem | ExperienceItem | ActivityItem:
    """중복 item은 KG 검증을 통과한 대표 item을 유지하고 설명만 보강한다"""

    representative, other = _representative_timeline_item(current, incoming)
    if not isinstance(representative, (ExperienceItem, ActivityItem)):
        return representative

    description = merge_descriptions(representative.description, other.description)
    role = representative.role
    if isinstance(representative, ActivityItem) and isinstance(other, ActivityItem):
        if representative.entity_id == other.entity_id:
            role = _merge_activity_roles(representative.role, other.role)
    if description == representative.description and role == representative.role:
        return representative
    return representative.model_copy(update={"description": description, "role": role})


def _representative_timeline_item(
    current: EducationItem | ExperienceItem | ActivityItem,
    incoming: EducationItem | ExperienceItem | ActivityItem,
) -> tuple[
    EducationItem | ExperienceItem | ActivityItem,
    EducationItem | ExperienceItem | ActivityItem,
]:
    current_score = _timeline_coverage_score(current)
    incoming_score = _timeline_coverage_score(incoming)
    if incoming_score > current_score:
        return incoming, current
    return current, incoming


def _timeline_coverage_score(
    item: EducationItem | ExperienceItem | ActivityItem,
) -> tuple[int, int, int, int]:
    start = _period_bound(item.start_date, is_end=False)
    end = _period_bound(item.end_date, is_end=True)
    span = (end - start) if start is not None and end is not None else 0
    known_dates = int(item.start_date is not None) + int(item.end_date is not None)
    known_fields = sum(
        int(bool(getattr(item, field, None))) for field in ("organization", "role", "kind")
    )
    organization_length = len(getattr(item, "organization", None) or "")
    return span, known_dates, known_fields, organization_length


def _periods_overlap(
    current_start: str | None,
    current_end: str | None,
    incoming_start: str | None,
    incoming_end: str | None,
) -> bool:
    current_start_bound = _period_bound(current_start, is_end=False)
    current_end_bound = _period_bound(current_end, is_end=True)
    incoming_start_bound = _period_bound(incoming_start, is_end=False)
    incoming_end_bound = _period_bound(incoming_end, is_end=True)
    if current_end_bound is not None and incoming_start_bound is not None:
        if current_end_bound < incoming_start_bound:
            return False
    if incoming_end_bound is not None and current_start_bound is not None:
        if incoming_end_bound < current_start_bound:
            return False
    return True


def _period_bound(value: str | None, *, is_end: bool) -> int | None:
    if value is None:
        return None
    return date_rank(value, default_month=12 if is_end else 1)


def _organization_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = re.sub(r"[^\w가-힣]+", "", normalized, flags=re.UNICODE)
    return compact.replace("여대", "여자대학교")


def _organizations_compatible(
    current_key: str, incoming_key: str, current: str, incoming: str
) -> bool:
    if current_key == incoming_key:
        return True
    if similar_title(current, incoming):
        return True
    # Notion may alternate between an institution and its department/team name.
    shorter, longer = sorted((current_key, incoming_key), key=len)
    return len(shorter) >= 4 and shorter in longer


def _timeline_identity_labels(item: ActivityItem | ExperienceItem, names: set[str]) -> set[str]:
    labels = set(names)
    for field in ("organization", "role", "description"):
        value = getattr(item, field, None)
        if value:
            labels.add(value)
    return labels
