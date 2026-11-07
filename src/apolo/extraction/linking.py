"""Work·기관·활동·자격 병합 판정이 함께 쓰는 결과 형식·요약 재료·채택 규칙"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource

MAX_SNIPPET_CHARS = 200
_PREFERRED_LOCATORS = ("github.api.description", "github.readme")


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LinkGroup(_Output):
    ids: list[str] = Field(min_length=2)
    confidence: float = Field(ge=0, le=1)
    reason: str


class LinkingResult(_Output):
    groups: list[LinkGroup]


@dataclass(frozen=True)
class ExtractionIndex:
    """추출 결과를 Entity ref별 문자열 Fact 값·근거 locator로 모은 것"""

    snippets: dict[str, str]
    values: dict[str, dict[str, list[str]]]
    refs: dict[str, list[str]]

    def locators(self, ref: str) -> list[str]:
        return list(dict.fromkeys(self.refs.get(ref, [])))

    def evidence(self, ref: str) -> list[tuple[str, str]]:
        """(locator, snippet). 원문 후보에 없는 locator는 뺀다"""
        return [(loc, self.snippets[loc]) for loc in self.locators(ref) if loc in self.snippets]


def index_extraction(source: CollectedSource, extraction: ExtractionResult) -> ExtractionIndex:
    values: dict[str, dict[str, list[str]]] = {}
    refs: dict[str, list[str]] = {}
    for fact in extraction.facts:
        if isinstance(fact.value, str):
            values.setdefault(fact.entity_ref, {}).setdefault(fact.predicate, []).append(fact.value)
        refs.setdefault(fact.entity_ref, []).extend(fact.evidence_refs)
    for link in extraction.entity_evidence:
        refs.setdefault(link.entity_ref, []).extend(link.evidence_refs)
    snippets = {item.locator: item.snippet for item in source.evidence_candidates}
    return ExtractionIndex(snippets, values, refs)


def first(values: Mapping[str, Sequence[str]], predicate: str) -> str | None:
    items = values.get(predicate)
    return items[0] if items else None


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


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://")) and " " not in value


class _Summary(Protocol):
    @property
    def id(self) -> str: ...


def accepted_links[S: _Summary](
    result: LinkingResult,
    summaries: Sequence[S],
    existing_ids: dict[str, UUID],
    *,
    min_confidence: float,
    compatible: Callable[[list[S]], bool],
) -> dict[str, UUID]:
    """판정 묶음을 새 후보 id → Entity ID로 바꾼다. 기존 Entity가 없으면 새 ID를 함께 쓴다

    LLM 판정이라도 기준선 미만이거나 compatible을 어기거나
    기존 Entity가 둘 이상인 묶음은 버린다.
    같은 Source의 후보가 한 묶음에 둘 이상이면 같은 ID로 두 번 만들지 않도록 버린다.
    """
    by_id = {summary.id: summary for summary in summaries}
    links: dict[str, UUID] = {}
    used: set[str] = set()
    for group in result.groups:
        ids = list(dict.fromkeys(group.ids))
        members = [by_id[i] for i in ids if i in by_id and i not in used]
        if group.confidence < min_confidence or len(members) < 2 or not compatible(members):
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
