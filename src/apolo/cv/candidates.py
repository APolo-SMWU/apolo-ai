"""KG Entity를 CV 섹션 후보로 분류한다. 섹션·제목·날짜는 LLM이 아니라 KG에서 정한다."""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from apolo.contracts.knowledge import ActiveKnowledgeEntity, ActiveKnowledgeGraph

CvSectionKey = Literal[
    "education",
    "experience",
    "publications",
    "projects",
    "awards",
    "activities",
    "volunteering",
    "certifications",
]

_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-\d{2})?$")
_MIN_SNIPPET = 6
_MAX_SNIPPET = 500
_MAX_SNIPPETS = 8


@dataclass(frozen=True)
class CvCandidate:
    entity_id: str
    section: CvSectionKey
    title: str
    subtitle: str | None = None
    start: str | None = None
    end: str | None = None
    date: str | None = None
    grade: str | None = None
    issuer: str | None = None
    link: str | None = None
    skills: tuple[str, ...] = ()
    snippets: tuple[str, ...] = ()


def _format_date(value: str | None) -> str | None:
    match = _DATE.match(value or "")
    if not match:
        return None
    year, month = match.group(1), match.group(2)
    return f"{year}.{month}" if month else year


def _http_url(value: str | None) -> str | None:
    parsed = urlparse(value or "")
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def build_cv_candidates(graph: ActiveKnowledgeGraph) -> list[CvCandidate]:
    entities = {entity.id: entity for entity in graph.entities}
    facts: dict = defaultdict(lambda: defaultdict(list))
    for fact in sorted(graph.facts, key=lambda f: f.updated_at, reverse=True):
        facts[fact.entity_id][fact.predicate].append(fact)

    def values(entity_id, predicate) -> list[str]:
        return [str(f.value) for f in facts[entity_id][predicate]]

    def one(entity_id, predicate) -> str | None:
        found = values(entity_id, predicate)
        return found[0] if found else None

    def linked(subject_id, predicate) -> list:
        return [
            r.object_entity_id
            for r in graph.relations
            if r.subject_entity_id == subject_id and r.predicate == predicate
        ]

    def name_of(entity_id) -> str | None:
        return one(entity_id, "name")

    def org_name(entity_id) -> str | None:
        return next((n for o in linked(entity_id, "atOrganization") if (n := name_of(o))), None)

    def skill_names(entity_id) -> tuple[str, ...]:
        names = (name_of(s) for s in linked(entity_id, "usesSkill"))
        return tuple(dict.fromkeys(n for n in names if n))

    def snippets_of(entity: ActiveKnowledgeEntity) -> list[str]:
        found = [e.snippet for e in entity.evidence]
        for predicate_facts in facts[entity.id].values():
            for fact in predicate_facts:
                found.extend(e.snippet for e in fact.evidence)
        for relation in graph.relations:
            if entity.id in (relation.subject_entity_id, relation.object_entity_id):
                found.extend(e.snippet for e in relation.evidence)
        clean = (s.strip() for s in found)
        unique = dict.fromkeys(s[:_MAX_SNIPPET] for s in clean if len(s) >= _MIN_SNIPPET)
        return list(unique)

    def period(entity_id) -> tuple[str | None, str | None]:
        start = _format_date(one(entity_id, "start"))
        end = _format_date(one(entity_id, "end"))
        if end is None and one(entity_id, "isCurrent") == "True":
            end = "Present"
        return start, end

    folded: dict = {}
    for entity in graph.entities:
        if entity.class_type == "Work":
            parent = next(iter(linked(entity.id, "partOf")), None)
            if parent in entities and entities[parent].class_type == "Experience":
                folded.setdefault(parent, []).append(entity)

    candidates: list[CvCandidate] = []
    for entity in graph.entities:
        eid, cls = entity.id, entity.class_type
        snippets = snippets_of(entity)
        start, end = period(eid)
        if cls == "Education":
            title = org_name(eid)
            if title:
                major = ", ".join(dict.fromkeys(values(eid, "major"))) or None
                candidates.append(
                    CvCandidate(str(eid), "education", title, major, start, end,
                                snippets=tuple(snippets[:_MAX_SNIPPETS]))
                )
        elif cls == "Experience":
            role, department = one(eid, "role"), one(eid, "department")
            title = org_name(eid) or role
            subtitle = " · ".join(p for p in (role, department) if p and p != title) or None
            for work in folded.get(eid, []):
                work_title = one(work.id, "title")
                snippets = [f"{work_title}: {s}" for s in snippets_of(work)] + snippets
            if title:
                candidates.append(
                    CvCandidate(str(eid), "experience", title, subtitle, start, end,
                                skills=skill_names(eid),
                                snippets=tuple(snippets[:_MAX_SNIPPETS]))
                )
        elif cls == "Activity":
            title = name_of(eid) or org_name(eid)
            section = "volunteering" if one(eid, "kind") == "volunteer" else "activities"
            if title:
                candidates.append(
                    CvCandidate(str(eid), section, title, one(eid, "role"), start, end,
                                snippets=tuple(snippets[:_MAX_SNIPPETS]))
                )
        elif cls == "Work":
            kind, title = one(eid, "kind"), one(eid, "title")
            if not title:
                continue
            if any(eid == w.id for ws in folded.values() for w in ws):
                continue
            url = next((u for v in values(eid, "url") if (u := _http_url(v))), None)
            section = "publications" if kind == "publication" else "projects"
            candidates.append(
                CvCandidate(str(eid), section, title, one(eid, "role"), start, end, link=url,
                            skills=skill_names(eid), snippets=tuple(snippets[:_MAX_SNIPPETS]))
            )
        elif cls == "Credential":
            kind, title = one(eid, "kind"), one(eid, "title")
            if not title:
                continue
            candidates.append(
                CvCandidate(
                    str(eid), "awards" if kind == "award" else "certifications", title,
                    date=_format_date(one(eid, "date")), grade=one(eid, "grade"),
                    issuer=one(eid, "issuerName"), snippets=tuple(snippets[:_MAX_SNIPPETS]),
                )
            )
    return candidates
