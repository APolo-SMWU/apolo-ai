"""Work item 보정·중복 제거와 프로젝트 참여 Activity 흡수"""

import re
from urllib.parse import urlsplit
from uuid import UUID

from apolo.contracts.generate import (
    ActivitiesBlock,
    ActivityItem,
    ContentBlock,
    ProjectLink,
    WorkItem,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.normalizers.common import (
    entity_context,
    labels_share_identity,
    merge_descriptions,
    optional_value,
    required_value,
)
from apolo.graph_b.validators.common import (
    entity_facts,
    fact_values,
)


def normalize_work_items(items: list[WorkItem], graph: ActiveKnowledgeGraph) -> list[WorkItem]:
    normalized = []
    for item in items:
        context = entity_context(graph, item.entity_id, "works")
        if context is None:
            continue
        entity_id, facts = context
        title = required_value(item.title, fact_values(facts, "title"))
        kind = required_value(item.kind, fact_values(facts, "kind"))
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
                    "role": optional_value(item.role, fact_values(facts, "role")),
                    "skills": skills or None,
                    "links": links,
                }
            )
        )
    return normalized


def _work_skill_names(graph: ActiveKnowledgeGraph, work_id: UUID) -> set[str]:
    skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.subject_entity_id == work_id and relation.predicate == "usesSkill"
    }
    return {
        fact.value
        for fact in graph.facts
        if fact.entity_id in skill_ids and fact.predicate == "name" and isinstance(fact.value, str)
    }


def _work_url_label(href: str) -> str | None:
    """Work.url 중 화면에서 지원하는 HTTP(S) URL에 의미 기반 label 부여"""
    try:
        parsed = urlsplit(href)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or hostname is None:
        return None
    host = hostname.lower().removeprefix("www.")
    path = parsed.path.lower()
    if host == "github.com":
        return "GitHub"
    google_slides = host == "docs.google.com" and path.startswith("/presentation/")
    if path.endswith((".ppt", ".pptx")) or google_slides or host in _SLIDE_HOSTS:
        return "PPT"
    for label, hosts in _WORK_URL_LABELS:
        if any(host == h or host.endswith(f".{h}") for h in hosts):
            return label
    if host == "huggingface.co" and path.startswith("/spaces/"):
        return "Demo"
    return "Link"


_SLIDE_HOSTS = frozenset(
    {
        "slideshare.net",
        "speakerdeck.com",
        "canva.com",
        "miricanvas.com",
        "figma.com",
    }
)


_WORK_URL_LABELS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Paper",
        frozenset(
            {
                "arxiv.org",
                "doi.org",
                "dl.acm.org",
                "ieeexplore.ieee.org",
                "openreview.net",
                "aclanthology.org",
                "semanticscholar.org",
                "dbpia.co.kr",
                "riss.kr",
                "kci.go.kr",
            }
        ),
    ),
    ("Video", frozenset({"youtube.com", "youtu.be", "vimeo.com"})),
    ("Notion", frozenset({"notion.so", "notion.site"})),
    (
        "Demo",
        frozenset(
            {
                "vercel.app",
                "netlify.app",
                "github.io",
                "pages.dev",
                "streamlit.app",
                "herokuapp.com",
            }
        ),
    ),
)


def deduplicate_work_items(items: list[WorkItem], graph: ActiveKnowledgeGraph) -> list[WorkItem]:
    """같은 KG ID이거나 URL 근거가 겹치는 Work를 합친다"""
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
            "description": merge_descriptions(representative.description, other.description),
        }
        if same_entity:
            update["skills"] = (
                list(dict.fromkeys((current.skills or []) + (item.skills or []))) or None
            )
            links_by_href = {link.href: link for link in current.links + item.links}
            update["links"] = list(links_by_href.values())
            if representative.image_url is None:
                update["image_url"] = other.image_url
        merged[match_index] = representative.model_copy(update=update)
    return merged


def _same_work_identity(current: WorkItem, incoming: WorkItem, graph: ActiveKnowledgeGraph) -> bool:
    if current.entity_id == incoming.entity_id:
        return True
    if current.kind != incoming.kind:
        return False
    # 다른 Entity의 같은 프로젝트 여부는 Graph A 병합 판정이 정한다. 여기서는 URL만 본다.
    return bool(_work_urls(graph, current.entity_id) & _work_urls(graph, incoming.entity_id))


def _work_urls(graph: ActiveKnowledgeGraph, entity_id: str) -> set[str]:
    return fact_values(entity_facts(graph, UUID(entity_id)), "url")


def _representative_work(current: WorkItem, incoming: WorkItem) -> tuple[WorkItem, WorkItem]:
    current_score = (bool(current.description), bool(current.role), len(current.title))
    incoming_score = (bool(incoming.description), bool(incoming.role), len(incoming.title))
    return (incoming, current) if incoming_score > current_score else (current, incoming)


def merge_project_participation_into_works(
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
                    if _activity_matches_work(activity, updated_works[work.entity_id], graph)
                ),
                None,
            )
            if match is None:
                retained.append(activity)
                continue
            updated_works[match.entity_id] = match.model_copy(
                update={"description": merge_descriptions(match.description, activity.description)}
            )
        if retained:
            updated_blocks.append(block.model_copy(update={"items": retained}))

    return [
        block.model_copy(update={"items": [updated_works[item.entity_id] for item in block.items]})
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
    activity_context = entity_context(graph, activity.entity_id, "activities")
    work_context = entity_context(graph, work.entity_id, "works")
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
    return labels_share_identity(activity_labels, work_labels)
