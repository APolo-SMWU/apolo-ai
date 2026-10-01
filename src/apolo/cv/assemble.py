"""LLM 선택 결과와 후보를 합쳐 Backend가 렌더링할 CV 섹션으로 조립한다."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from apolo.contracts.cv import CvEntryOut, CvLinkOut, CvOutput, CvSectionOut
from apolo.contracts.generate import GenerateWarning
from apolo.cv.candidates import CvCandidate, CvSectionKey

_SECTIONS: tuple[tuple[CvSectionKey, str, str], ...] = (
    ("education", "학력", "entries"),
    ("experience", "경력", "entries"),
    ("publications", "논문", "bullets"),
    ("projects", "프로젝트", "entries"),
    ("awards", "수상", "entries"),
    ("activities", "대외활동", "entries"),
    ("volunteering", "봉사활동", "entries"),
    ("certifications", "자격 및 어학", "bullets"),
)
_LIMITS: dict[str, int] = {
    "education": 3,
    "experience": 6,
    "publications": 6,
    "projects": 6,
    "awards": 8,
    "activities": 6,
    "volunteering": 4,
    "certifications": 8,
}
_BULLET_SECTIONS = {"experience", "projects", "activities", "volunteering"}
_KEEP_LLM_ORDER = {"projects"}
_MAX_BULLETS = 3


@dataclass
class _Group:
    section: CvSectionKey
    members: list[CvCandidate]
    bullets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssembledCv:
    sections: list[CvSectionOut]
    warnings: list[GenerateWarning]


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def _range(start: str | None, end: str | None) -> str:
    end = "현재" if end == "Present" else end
    if start and end:
        return start if start == end else f"{start} – {end}"
    return start or end or ""


def _periods(members: list[CvCandidate]) -> list[tuple[str | None, str | None]]:
    by_start: dict[str, tuple[str | None, str | None]] = {}
    for m in members:
        if not (m.start or m.end):
            continue
        key = m.start or f"~{m.end}"
        if key not in by_start or (by_start[key][1] is None and m.end):
            by_start[key] = (m.start, m.end)
    return [by_start[k] for k in sorted(by_start)]


def _sort_key(group: _Group) -> str:
    keys = [
        "9999" if end == "Present" else (end or start or "")
        for start, end in _periods(group.members)
    ]
    keys += [m.date or "" for m in group.members]
    return max(keys, default="")


def _first(members: list[CvCandidate], name: str) -> str | None:
    return next((v for m in members if (v := getattr(m, name))), None)


def _link(members: list[CvCandidate]) -> CvLinkOut | None:
    href = _first(members, "link")
    if not href:
        return None
    label = "Source Code" if urlparse(href).netloc.endswith("github.com") else "Link"
    return CvLinkOut(label=label, href=href)


def _entry(group: _Group) -> CvEntryOut:
    members, title = group.members, group.members[0].title
    grade, issuer = _first(members, "grade"), _first(members, "issuer")
    date = _first(members, "date")
    if group.section == "certifications":
        line = title + (f", {issuer}" if issuer else "") + (f" — {grade}" if grade else "")
        return CvEntryOut(title=line + (f" ({date})" if date else ""))
    subtitle = _first(members, "subtitle")
    if group.section == "publications":
        return CvEntryOut(title=f"{title} ({subtitle})" if subtitle else title)
    if group.section == "awards":
        return CvEntryOut(title=title, date=date)
    ranges = ", ".join(_range(s, e) for s, e in _periods(members))
    repeated = {_norm(title), _norm(subtitle or "")}
    bullets = [b for b in group.bullets if _norm(b) not in repeated]
    return CvEntryOut(
        title=title,
        date=ranges or None,
        subtitle=subtitle,
        link=_link(members),
        bullets=bullets if group.section in _BULLET_SECTIONS else [],
    )


def assemble_cv(candidates: list[CvCandidate], output: CvOutput) -> AssembledCv:
    by_id = {c.entity_id: c for c in candidates}
    used: set[str] = set()
    warnings: list[GenerateWarning] = []
    groups: list[_Group] = []

    def drop(code: str, entity_id: str) -> None:
        warnings.append(
            GenerateWarning(code=code, message=f"CV 항목에서 제외한 후보: {entity_id}")
        )

    for selection in output.items:
        group: _Group | None = None
        for entity_id in selection.entity_ids:
            candidate = by_id.get(entity_id)
            if candidate is None:
                drop("CV_UNKNOWN_ENTITY", entity_id)
            elif entity_id in used:
                drop("CV_DUPLICATE_ENTITY", entity_id)
            elif group is not None and candidate.section != group.section:
                used.add(entity_id)
                groups.append(_Group(candidate.section, [candidate]))
                drop("CV_SECTION_MISMATCH", entity_id)
            else:
                used.add(entity_id)
                if group is None:
                    group = _Group(candidate.section, [])
                group.members.append(candidate)
        if group is not None:
            group.bullets = list(dict.fromkeys(selection.bullets))[:_MAX_BULLETS]
            groups.append(group)

    merged: dict[tuple[str, str], _Group] = {}
    for group in groups:
        key = (group.section, _norm(group.members[0].title))
        if key in merged:
            merged[key].members += group.members
            merged[key].bullets = list(dict.fromkeys(merged[key].bullets + group.bullets))
            merged[key].bullets = merged[key].bullets[:_MAX_BULLETS]
        else:
            merged[key] = group

    sections: list[CvSectionOut] = []
    for key, title, layout in _SECTIONS:
        items = [g for g in merged.values() if g.section == key]
        if key not in _KEEP_LLM_ORDER:
            items = sorted(items, key=_sort_key, reverse=True)
        entries = [_entry(g) for g in items[: _LIMITS[key]]]
        if entries:
            sections.append(CvSectionOut(title=title, layout=layout, entries=entries))
    return AssembledCv(sections=sections, warnings=warnings)
