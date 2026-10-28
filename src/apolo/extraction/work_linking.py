"""출처가 달라 제목·URL로 합쳐지지 않는 같은 프로젝트 Work를 LLM으로 판정"""

import json
from dataclasses import dataclass
from textwrap import dedent
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource

MIN_LINK_CONFIDENCE = 0.85
MAX_SNIPPET_CHARS = 200


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


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkLinkGroup(_Output):
    ids: list[str] = Field(min_length=2)
    confidence: float = Field(ge=0, le=1)
    reason: str


class WorkLinkingResult(_Output):
    groups: list[WorkLinkGroup]


class WorkLinker(Protocol):
    def link(self, works: list[WorkSummary]) -> WorkLinkingResult: ...


def new_work_summaries(
    source_index: int, source: CollectedSource, extraction: ExtractionResult
) -> dict[str, WorkSummary]:
    """추출 결과의 Work 후보 요약. 키는 Entity ref다"""
    snippets = {item.locator: item.snippet for item in source.evidence_candidates}
    page_title = source.evidence_candidates[0].snippet if source.evidence_candidates else None
    values: dict[str, dict[str, list[str]]] = {}
    refs: dict[str, list[str]] = {}
    for fact in extraction.facts:
        if isinstance(fact.value, str):
            values.setdefault(fact.entity_ref, {}).setdefault(fact.predicate, []).append(fact.value)
        refs.setdefault(fact.entity_ref, []).extend(fact.evidence_refs)
    for link in extraction.entity_evidence:
        refs.setdefault(link.entity_ref, []).extend(link.evidence_refs)
    skills: dict[str, list[str]] = {}
    for relation in extraction.relations:
        name = values.get(relation.object_ref, {}).get("name")
        if relation.predicate == "usesSkill" and name:
            skills.setdefault(relation.subject_ref, []).append(name[0])

    summaries: dict[str, WorkSummary] = {}
    for entity in extraction.entities:
        facts = values.get(entity.ref, {})
        if entity.class_type != "Work" or not facts.get("title"):
            continue
        locators = list(dict.fromkeys(refs.get(entity.ref, [])))
        sections = [
            locator.partition(";section_path=")[2]
            for locator in locators
            if ";section_path=" in locator
        ]
        summaries[entity.ref] = WorkSummary(
            id=f"s{source_index}:{entity.ref}",
            source_types=(source.source_type,),
            title=facts["title"][0],
            kind=_first(facts, "kind"),
            role=_first(facts, "role"),
            start=_first(facts, "start"),
            end=_first(facts, "end"),
            urls=tuple(facts.get("url", [])),
            skills=tuple(skills.get(entity.ref, [])[:5]),
            snippet=representative_snippet(
                [(locator, snippets[locator]) for locator in locators if locator in snippets],
                facts["title"][0],
            ),
            context=tuple(
                dict.fromkeys(
                    " > ".join(part for part in (page_title, section) if part)
                    for section in sections or [""]
                )
            )[:3],
        )
    return summaries


def accepted_links(
    result: WorkLinkingResult, works: list[WorkSummary], existing_ids: dict[str, UUID]
) -> dict[str, UUID]:
    """판정 묶음을 새 후보 id → Work ID로 바꾼다. 기존 Work가 없으면 새 ID를 함께 쓴다

    LLM 판정이라도 publication과 그 외가 섞이거나 기간이 겹치지 않거나
    기존 Work가 둘 이상인 묶음은 버린다. project와 opensource는 같은 계열로 본다.
    같은 Source의 후보가 한 묶음에 둘 이상이면 같은 ID로 두 번 만들지 않도록 버린다.
    """
    by_id = {work.id: work for work in works}
    links: dict[str, UUID] = {}
    used: set[str] = set()
    for group in result.groups:
        members = _valid_members(group, by_id, used)
        if members is None:
            continue
        existing = [m.id for m in members if m.id in existing_ids]
        new = [m.id for m in members if m.id not in existing_ids]
        sources = [i.split(":")[0] for i in new]
        if len(existing) > 1 or not new or len(sources) != len(set(sources)):
            continue
        target = existing_ids[existing[0]] if existing else uuid4()
        links.update({i: target for i in new})
        used.update(m.id for m in members)
    return links


def _valid_members(
    group: WorkLinkGroup, by_id: dict[str, WorkSummary], used: set[str]
) -> list[WorkSummary] | None:
    """기준선 미만, publication과 그 외가 섞인 묶음, 기간이 겹치지 않는 묶음은 버린다"""
    ids = list(dict.fromkeys(group.ids))
    members = [by_id[i] for i in ids if i in by_id and i not in used]
    if group.confidence < MIN_LINK_CONFIDENCE or len(members) < 2:
        return None
    families = {m.kind == "publication" for m in members if m.kind}
    if len(families) > 1 or not _periods_overlap(members):
        return None
    return members


def _first(facts: dict[str, list[str]], predicate: str) -> str | None:
    values = facts.get(predicate)
    return values[0] if values else None


def _periods_overlap(works: list[WorkSummary]) -> bool:
    """시작일이 있는 Work끼리만 비교한다. 끝이 없으면 진행 중으로 본다"""
    ranges = [(w.start, w.end or "9999") for w in works if w.start]
    return all(
        _not_after(a_start, b_end) and _not_after(b_start, a_end)
        for index, (a_start, a_end) in enumerate(ranges)
        for b_start, b_end in ranges[index + 1 :]
    )


def _not_after(left: str, right: str) -> bool:
    """정밀도가 다른 ISO 날짜(YYYY, YYYY-MM, YYYY-MM-DD)는 짧은 쪽 길이로 비교한다"""
    length = min(len(left), len(right))
    return left[:length] <= right[:length]


SYSTEM_PROMPT = dedent(
    """
    너는 한 사용자의 포트폴리오 Work 목록에서 같은 프로젝트를 가리키는 항목을 묶는다.
    같은 프로젝트가 GitHub 저장소, Notion 페이지, 이력서 문장처럼 여러 출처에서
    다른 이름으로 적힌다.

    [같은 Work로 묶는다]
    - 같은 산출물(같은 서비스·시스템·모델·연구)을 가리킨다.
      이름이 영어 저장소명과 한국어 설명처럼 달라도 된다.
    - 목적, 핵심 기능, 기술, 기간, 팀·역할 같은 근거가 함께 맞아떨어진다.
    - 이력서 한 줄처럼 제목이 일반적이어도 context가 같은 활동·프로그램을 가리키고
      제목의 핵심 단어가 다른 Work의 제목·내용과 맞으면 묶는다.
    - 제목의 표현(구현·연구·개발 등)이 달라도 kind가 같고 같은 대상·방법을 다루면 같은 산출물이다.
    - urls가 서로 달라도 같은 서비스를 이루는 저장소(프론트엔드·백엔드 등)면 같은 Work다.
      URL이 다르다는 점은 다른 산출물일 수 있다는 참고 신호일 뿐 그것만으로 판단하지 않는다.

    [묶지 않는다]
    - 주제나 기술만 비슷한 다른 산출물: 후속 연구, 다른 대회 출품작, 같은 기술을 쓴 다른 서비스.
    - context(동아리·활동·회사)만 같고 제목·내용은 서로 다른 프로젝트일 수 있는 경우.
    - publication과 project·opensource. 같은 연구의 논문과 구현은 다른 산출물이다.
      project와 opensource는 같은 계열이라 kind만 다르면 내용으로 판단한다.
    - 근거가 부족해 확신할 수 없는 경우. 애매하면 묶지 않는다.

    [출력]
    - 묶을 항목만 groups로 반환한다. 묶을 것이 없으면 빈 배열이다.
    - ids에는 목록에 있는 id만 쓴다. 한 id는 한 group에만 넣는다.
    - confidence는 같은 프로젝트라고 확신하는 정도(0~1)다.
    - reason에는 같다고 본 근거를 한 문장으로 쓴다.
    """
).strip()


def representative_snippet(evidence: list[tuple[str, str]], title: str) -> str | None:
    """(locator, snippet) 중 설명이 담긴 근거. 저장소 설명·README를 먼저, URL·제목 자체는 제외"""
    texts = [
        (locator, snippet.strip())
        for locator, snippet in evidence
        if snippet.strip() and snippet.strip() != title and not _is_url(snippet.strip())
    ]
    for preferred in _PREFERRED_LOCATORS:
        match = next((text for locator, text in texts if locator == preferred), None)
        if match:
            return match
    return max((text for _, text in texts), key=len, default=None)


_PREFERRED_LOCATORS = ("github.api.description", "github.readme")


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://")) and " " not in value


def build_work_linking_prompt(works: list[WorkSummary]) -> tuple[str, str]:
    payload = [_summary_payload(work) for work in works]
    user = "Work 목록(JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return SYSTEM_PROMPT, user


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
