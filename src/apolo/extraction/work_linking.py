"""출처가 달라 제목·URL로 합쳐지지 않는 같은 프로젝트 Work를 LLM으로 판정"""

import json
from dataclasses import dataclass
from typing import Protocol

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.dates import iso_periods_overlap, normalize_date
from apolo.extraction.linking import (
    MAX_SNIPPET_CHARS,
    LinkingResult,
    first,
    index_extraction,
    representative_snippet,
)
from apolo.extraction.prompts.linking import WORK_LINKING_PROMPT

MIN_LINK_CONFIDENCE = 0.85


@dataclass(frozen=True)
class WorkSummary:
    """판정에 보여줄 Work 요약. id는 기존 Work(W…)나 이번 추출 후보(s…:e…)의 임시 ID다"""

    id: str
    source_types: tuple[str, ...]
    title: str
    kind: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None
    urls: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    snippet: str | None = None
    # 근거가 적힌 페이지 제목·섹션·토글 경로. 제목이 일반적인 Work를 구분하는 단서다.
    context: tuple[str, ...] = ()


class WorkLinker(Protocol):
    def link(self, works: list[WorkSummary]) -> LinkingResult: ...


def new_work_summaries(
    source_index: int, source: CollectedSource, extraction: ExtractionResult
) -> dict[str, WorkSummary]:
    """추출 결과의 Work 후보 요약. 키는 Entity ref다"""
    index = index_extraction(source, extraction)
    page_title = source.evidence_candidates[0].snippet if source.evidence_candidates else None
    skills: dict[str, list[str]] = {}
    for relation in extraction.relations:
        name = index.values.get(relation.object_ref, {}).get("name")
        if relation.predicate == "usesSkill" and name:
            skills.setdefault(relation.subject_ref, []).append(name[0])

    summaries: dict[str, WorkSummary] = {}
    for entity in extraction.entities:
        facts = index.values.get(entity.ref, {})
        if entity.class_type != "Work" or not facts.get("title"):
            continue
        sections = [
            locator.partition(";section_path=")[2]
            for locator in index.locators(entity.ref)
            if ";section_path=" in locator
        ]
        summaries[entity.ref] = WorkSummary(
            id=f"s{source_index}:{entity.ref}",
            source_types=(source.source_type,),
            title=facts["title"][0],
            kind=first(facts, "kind"),
            role=first(facts, "role"),
            # 판정은 검증보다 먼저라 날짜 표기(2024.12)를 검증과 같은 ISO 형식으로 맞춘다
            start=_first_date(facts, "start"),
            end=_first_date(facts, "end"),
            urls=tuple(facts.get("url", [])),
            skills=tuple(skills.get(entity.ref, [])[:5]),
            snippet=representative_snippet(index.evidence(entity.ref), facts["title"][0]),
            context=tuple(
                dict.fromkeys(
                    " > ".join(part for part in (page_title, section) if part)
                    for section in sections or [""]
                )
            )[:3],
        )
    return summaries


def works_compatible(members: list[WorkSummary]) -> bool:
    """publication과 그 외가 섞이거나 기간이 겹치지 않으면 다른 Work다.

    project와 opensource는 같은 계열로 본다.
    """
    families = {m.kind == "publication" for m in members if m.kind}
    return len(families) <= 1 and iso_periods_overlap([(m.start, m.end) for m in members])


def _first_date(facts: dict[str, list[str]], predicate: str) -> str | None:
    value = first(facts, predicate)
    return normalize_date(value) if value else None


def build_work_linking_prompt(works: list[WorkSummary]) -> tuple[str, str]:
    payload = [_summary_payload(work) for work in works]
    user = "Work 목록(JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return WORK_LINKING_PROMPT, user


def _summary_payload(work: WorkSummary) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": work.id,
        "sources": list(work.source_types),
        "title": work.title,
    }
    optional = {
        "kind": work.kind,
        "role": work.role,
        "start": work.start,
        "end": work.end,
        "urls": list(work.urls),
        "skills": list(work.skills),
        "snippet": (work.snippet or "")[:MAX_SNIPPET_CHARS] or None,
        "context": list(work.context),
    }
    payload.update({key: value for key, value in optional.items() if value})
    return payload
