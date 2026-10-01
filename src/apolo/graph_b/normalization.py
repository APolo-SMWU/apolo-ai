"""Graph B 출력을 현재 KG의 정규값에 맞춰 안전하게 정리한다"""

import re
import unicodedata
from collections import defaultdict
from urllib.parse import urlsplit
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
    ContentBlock,
    EducationBlock,
    EducationItem,
    ExperienceBlock,
    ExperienceItem,
    ProjectLink,
    SkillCategory,
    SkillItem,
    SkillsBlock,
    WorkItem,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.skill_categories import (
    SKILL_CATEGORIES,
    UNCATEGORIZED_SKILL_CATEGORY,
    canonical_skill_name,
    is_azure_platform_skill,
    platform_group_representative,
    skill_categories_for_name,
)
from apolo.graph_b.validators.common import (
    date_values,
    entity_facts,
    fact_values,
    has_current_fact,
    item_entity_id,
    organization_names,
)
from apolo.graph_b.validators.skill_content import _supported_skills_by_category
from apolo.text_similarity import shares_core_terms, similar_description, similar_title

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
            items = _deduplicate_timeline_items(
                _normalize_experience_items(block.items, graph), graph
            )
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, ActivitiesBlock):
            items = _deduplicate_timeline_items(
                _normalize_activity_items(block.items, graph), graph
            )
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, AwardsBlock):
            items = _deduplicate_credential_items(
                _normalize_award_items(block.items, graph)
            )
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, CertificationBlock):
            items = _deduplicate_credential_items(
                _normalize_certification_items(block.items, graph)
            )
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, WorksBlock):
            items = _deduplicate_work_items(
                _normalize_work_items(block.items, graph), graph
            )
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
    normalized_blocks = _merge_project_participation_into_works(normalized_blocks, graph)
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


def _deduplicate_timeline_items(
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

    current_role = _text_key(getattr(current, "role", None))
    incoming_role = _text_key(getattr(incoming, "role", None))
    current_kind = _text_key(getattr(current, "kind", None))
    incoming_kind = _text_key(getattr(incoming, "kind", None))
    if current_kind and incoming_kind and current_kind != incoming_kind:
        return False

    if isinstance(current, ActivityItem) and isinstance(incoming, ActivityItem):
        current_names = fact_values(
            entity_facts(graph, UUID(current.entity_id)), "name"
        )
        incoming_names = fact_values(
            entity_facts(graph, UUID(incoming.entity_id)), "name"
        )
        current_labels = _timeline_identity_labels(current, current_names)
        incoming_labels = _timeline_identity_labels(incoming, incoming_names)
        if not _labels_share_identity(current_labels, incoming_labels):
            return False
        if current_role and incoming_role and current_role != incoming_role:
            # 다른 KG Entity의 역할 근거는 한 Entity의 item에 합치지 않는다.
            return False
    elif current_role and incoming_role and not (
        similar_title(current_role, incoming_role)
        or shares_core_terms(current_role, incoming_role)
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

    description = _merge_descriptions(representative.description, other.description)
    role = representative.role
    if isinstance(representative, ActivityItem) and isinstance(other, ActivityItem):
        if representative.entity_id == other.entity_id:
            role = _merge_activity_roles(representative.role, other.role)
    if description == representative.description and role == representative.role:
        return representative
    return representative.model_copy(update={"description": description, "role": role})


def _merge_activity_roles(current: str | None, incoming: str | None) -> str | None:
    """같은 Activity의 중복 결과에서 역할 명칭만 role 필드에 합친다."""
    labels: list[str] = []
    seen: set[str] = set()
    for role in (current, incoming):
        if not role:
            continue
        for label in _activity_role_parts(role):
            key = _text_key(label)
            if not label or key in seen:
                continue
            candidate = ", ".join([*labels, label])
            if len(candidate) > 200:
                continue
            labels.append(label)
            seen.add(key)
    return ", ".join(labels) or None


def _normalize_activity_role(value: str | None, candidates: set[str]) -> str | None:
    if value is None or value in candidates:
        return value
    supported_parts = {
        _text_key(part): part
        for candidate in sorted(candidates)
        for part in _activity_role_parts(candidate)
    }
    parts = _activity_role_parts(value)
    if parts and all(_text_key(part) in supported_parts for part in parts):
        canonical_parts = [supported_parts[_text_key(part)] for part in parts]
        return _merge_activity_roles(None, ", ".join(canonical_parts))
    return _optional_value(value, candidates)


def _activity_role_parts(role: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]+", role) if part.strip()]


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
    if value is None or value == "Present":
        return None if value is None else 10**9
    year, _, month = value.partition(".")
    return int(year) * 12 + (int(month) if month else (12 if is_end else 1))


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


def _timeline_identity_labels(
    item: ActivityItem | ExperienceItem, names: set[str]
) -> set[str]:
    labels = set(names)
    for field in ("organization", "role", "description"):
        value = getattr(item, field, None)
        if value:
            labels.add(value)
    return labels


def _labels_share_identity(left: set[str], right: set[str]) -> bool:
    return any(similar_title(a, b) or shares_core_terms(a, b) for a in left for b in right)


def _text_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w가-힣]+", "", normalized, flags=re.UNICODE)


def _merge_descriptions(current: str | None, incoming: str | None) -> str | None:
    """중복 문장은 줄이고 병합된 항목의 서로 다른 설명은 보존한다"""
    if not current:
        return incoming
    if not incoming:
        return current
    current, incoming = current.strip(), incoming.strip()
    current_key, incoming_key = _text_key(current), _text_key(incoming)
    if current_key == incoming_key or current_key in incoming_key:
        return incoming if len(incoming) > len(current) else current
    if incoming_key in current_key:
        return current
    return f"{current.rstrip(' .;·')} · {incoming.lstrip(' ;·')}"


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
                    "role": _normalize_activity_role(item.role, fact_values(facts, "role")),
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


def _deduplicate_credential_items(
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
        if (
            isinstance(representative, CertificationItem)
            and representative.grade is None
        ):
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
    if current.issuer and incoming.issuer and not similar_title(
        current.issuer, incoming.issuer
    ):
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
                label = _work_url_label(link.href)
                if label is None:
                    continue
                links.append(link.model_copy(update={"label": label}))
                seen_urls.add(link.href)
        for href in sorted(supported_urls):
            if href in seen_urls:
                continue
            label = _work_url_label(href)
            if label is not None:
                links.append(ProjectLink(label=label, href=href))
                seen_urls.add(href)
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


def _work_url_label(href: str) -> str | None:
    """Work.url 중 화면에서 지원하는 HTTP(S) URL에 의미 기반 label 부여"""
    try:
        parsed = urlsplit(href)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or hostname is None:
        return None
    return "GitHub" if hostname in {"github.com", "www.github.com"} else "Link"


def _deduplicate_work_items(
    items: list[WorkItem], graph: ActiveKnowledgeGraph
) -> list[WorkItem]:
    """KG ID 우선, 제목·종류와 URL 근거가 일치하는 Work를 보조 병합한다"""
    merged: list[WorkItem] = []
    for item in items:
        match_index = next(
            (
                index
                for index, candidate in enumerate(merged)
                if _same_work_identity(candidate, item, graph)
            ),
            None,
        )
        if match_index is None:
            merged.append(item)
            continue

        current = merged[match_index]
        representative, other = _representative_work(current, item)
        same_entity = current.entity_id == item.entity_id
        update = {
            "description": _merge_descriptions(
                representative.description, other.description
            ),
        }
        if same_entity:
            update["skills"] = (
                list(dict.fromkeys((current.skills or []) + (item.skills or [])))
                or None
            )
            links_by_href = {link.href: link for link in current.links + item.links}
            update["links"] = list(links_by_href.values())
            if representative.image_url is None:
                update["image_url"] = other.image_url
        merged[match_index] = representative.model_copy(update=update)
    return merged


def _same_work_identity(
    current: WorkItem, incoming: WorkItem, graph: ActiveKnowledgeGraph
) -> bool:
    if current.entity_id == incoming.entity_id:
        return True
    if current.kind != incoming.kind:
        return False
    current_urls = _work_urls(graph, current.entity_id)
    incoming_urls = _work_urls(graph, incoming.entity_id)
    shared_urls = current_urls & incoming_urls
    if current_urls and incoming_urls and not shared_urls:
        return False
    if shared_urls:
        return True
    return (
        similar_title(current.title, incoming.title)
        or shares_core_terms(current.title, incoming.title)
        or similar_description(current.description or "", incoming.description or "")
        or similar_description(current.title, incoming.description or "")
        or similar_description(incoming.title, current.description or "")
    )


def _work_urls(graph: ActiveKnowledgeGraph, entity_id: str) -> set[str]:
    return fact_values(entity_facts(graph, UUID(entity_id)), "url")


def _merge_project_participation_into_works(
    blocks: list[ContentBlock], graph: ActiveKnowledgeGraph
) -> list[ContentBlock]:
    """프로젝트 참여만 반복하는 Activity는 일치하는 Work 설명에 흡수한다."""
    work_blocks = [block for block in blocks if isinstance(block, WorksBlock)]
    activity_blocks = [block for block in blocks if isinstance(block, ActivitiesBlock)]
    if not work_blocks or not activity_blocks:
        return blocks

    works = [item for block in work_blocks for item in block.items]
    updated_works: dict[str, WorkItem] = {item.entity_id: item for item in works}
    updated_blocks = []
    for block in blocks:
        if not isinstance(block, ActivitiesBlock):
            updated_blocks.append(block)
            continue

        retained = []
        for activity in block.items:
            if not _is_generic_project_participation(activity):
                retained.append(activity)
                continue
            match = next(
                (
                    updated_works[work.entity_id]
                    for work in works
                    if _activity_matches_work(
                        activity, updated_works[work.entity_id], graph
                    )
                ),
                None,
            )
            if match is None:
                retained.append(activity)
                continue
            updated_works[match.entity_id] = match.model_copy(
                update={
                    "description": _merge_descriptions(
                        match.description, activity.description
                    )
                }
            )
        if retained:
            updated_blocks.append(block.model_copy(update={"items": retained}))

    return [
        block.model_copy(
            update={"items": [updated_works[item.entity_id] for item in block.items]}
        )
        if isinstance(block, WorksBlock)
        else block
        for block in updated_blocks
    ]


def _is_generic_project_participation(item: ActivityItem) -> bool:
    if item.role:
        return False
    text = " ".join(value for value in (item.description, item.organization) if value)
    if not re.search(
        r"(프로젝트|연구|과제|project|research).{0,24}(참여|수행|participat)",
        text,
        re.I,
    ):
        return False
    specific_contribution = re.compile(
        r"(개발|구현|제작|설계|분석|평가|검증|개선|구축|운영|기획|담당|멘토링|교육|발표|수상|"
        r"develop|implement|design|analy[sz]|evaluate|build|create|lead|teach)",
        re.I,
    )
    return specific_contribution.search(text) is None


def _activity_matches_work(
    activity: ActivityItem, work: WorkItem, graph: ActiveKnowledgeGraph
) -> bool:
    activity_context = _entity_context(graph, activity.entity_id, "activities")
    work_context = _entity_context(graph, work.entity_id, "works")
    if activity_context is None or work_context is None:
        return False
    _, activity_facts = activity_context
    _, work_facts = work_context
    activity_labels = fact_values(activity_facts, "name") | {
        activity.organization,
        activity.description or "",
    }
    work_labels = fact_values(work_facts, "title") | {
        work.title,
        work.description or "",
    }
    return _labels_share_identity(activity_labels, work_labels)


def _representative_work(
    current: WorkItem, incoming: WorkItem
) -> tuple[WorkItem, WorkItem]:
    current_score = (bool(current.description), bool(current.role), len(current.title))
    incoming_score = (bool(incoming.description), bool(incoming.role), len(incoming.title))
    return (incoming, current) if incoming_score > current_score else (current, incoming)


def _normalize_skill_categories(
    block: SkillsBlock, graph: ActiveKnowledgeGraph
) -> list[SkillCategory]:
    supported = _supported_skills_by_category(graph)
    if not supported:
        return []
    names_by_skill_id: dict[str, set[str]] = defaultdict(set)
    for _category_name, skills in supported.items():
        for skill_id, names in skills.items():
            names_by_skill_id[skill_id].update(names)

    categories: dict[str, dict[str, SkillItem]] = defaultdict(dict)
    category_by_display_name: dict[str, str] = {}
    display_name_by_entity_id: dict[str, str] = {}
    for source_category in block.categories:
        requested_category = source_category.category.strip()
        for item in source_category.items:
            member_ids: list[str] = []
            for value in item.entity_ids:
                parsed_id = item_entity_id(value)
                canonical_id = str(parsed_id) if parsed_id is not None else None
                if canonical_id in names_by_skill_id and canonical_id not in member_ids:
                    member_ids.append(canonical_id)
            if not member_ids or len(member_ids) != len(item.entity_ids):
                continue

            requested_name = canonical_skill_name(item.name)
            grouped_ids: dict[str, list[str]] = defaultdict(list)
            names_by_member = [
                names_by_skill_id[skill_id] for skill_id in member_ids
            ]
            platform_name = platform_group_representative(names_by_member)
            if (
                platform_name is not None
                and requested_name.casefold() == platform_name.casefold()
            ):
                grouped_ids[platform_name].extend(member_ids)
            else:
                for skill_id in member_ids:
                    candidate_names = {
                        canonical_skill_name(name)
                        for name in names_by_skill_id[skill_id]
                    }
                    if not candidate_names:
                        continue
                    # A group may contain synonymous KG entities. If it contains distinct
                    # technologies and no shared platform representative, keep them separate.
                    name = (
                        requested_name
                        if requested_name in candidate_names
                        else sorted(candidate_names, key=str.casefold)[0]
                    )
                    grouped_ids[name].append(skill_id)

            for name, grouped_member_ids in grouped_ids.items():
                member_category_sets = [
                    {
                        category
                        for member_name in names_by_skill_id[skill_id]
                        for category in skill_categories_for_name(member_name)
                    }
                    for skill_id in grouped_member_ids
                ]
                known_category_sets = [
                    values for values in member_category_sets if values
                ]
                if known_category_sets:
                    valid_categories = set.intersection(*known_category_sets)
                else:
                    valid_categories = set()
                if requested_category in SKILL_CATEGORIES and (
                    not valid_categories or requested_category in valid_categories
                ):
                    category_name = requested_category
                elif valid_categories:
                    category_name = next(
                        category
                        for category in SKILL_CATEGORIES
                        if category in valid_categories
                    )
                else:
                    category_name = UNCATEGORIZED_SKILL_CATEGORY

                display_key = " ".join(name.split()).casefold()
                category_name = category_by_display_name.get(display_key, category_name)
                existing = categories[category_name].get(display_key)
                if existing is None:
                    categories[category_name][display_key] = SkillItem(
                        entity_ids=grouped_member_ids,
                        name=name,
                    )
                else:
                    merged_ids = list(
                        dict.fromkeys([*existing.entity_ids, *grouped_member_ids])
                    )
                    categories[category_name][display_key] = existing.model_copy(
                        update={"entity_ids": merged_ids}
                    )
                category_by_display_name[display_key] = category_name
                for skill_id in grouped_member_ids:
                    display_name_by_entity_id.setdefault(skill_id, display_key)

    # Azure 플랫폼과 서비스가 별도 Skill item으로 생성돼도 한 대표 항목으로 합친다.
    cloud_category = "클라우드 & 배포"
    azure_items = {}
    azure_ids = []
    for display_key, item in list(categories.get(cloud_category, {}).items()):
        if all(
            any(is_azure_platform_skill(name) for name in names_by_skill_id[skill_id])
            for skill_id in item.entity_ids
        ):
            azure_items[display_key] = item
            azure_ids.extend(item.entity_ids)
    azure_ids = list(dict.fromkeys(azure_ids))
    if len(azure_ids) > 1:
        for display_key, item in azure_items.items():
            del categories[cloud_category][display_key]
            for skill_id in item.entity_ids:
                display_name_by_entity_id.pop(skill_id, None)
        categories[cloud_category]["azure"] = SkillItem(
            entity_ids=azure_ids,
            name="Azure",
        )
        category_by_display_name["azure"] = cloud_category
        for skill_id in azure_ids:
            display_name_by_entity_id[skill_id] = "azure"

    # 한 KG Skill은 한 번만 표시한다. 같은 entity가 다른 이름으로 중복 출력되면
    # 먼저 확인된 표준 항목에 연결하고, 동의어 entity ID는 모두 보존한다.
    for _category_name, items in categories.items():
        for display_key, item in list(items.items()):
            unique_ids = []
            for skill_id in item.entity_ids:
                if display_name_by_entity_id.get(skill_id) == display_key:
                    unique_ids.append(skill_id)
            if unique_ids:
                items[display_key] = item.model_copy(update={"entity_ids": unique_ids})
            else:
                del items[display_key]
    return [
        SkillCategory(
            category=category,
            items=list(items.values()),
        )
        for category in SKILL_CATEGORIES
        for items in [categories.get(category, {})]
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
