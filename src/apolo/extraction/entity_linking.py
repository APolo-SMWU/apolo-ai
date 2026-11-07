"""출처마다 표기가 달라 규칙으로 합쳐지지 않는 같은 기관·활동·자격을 LLM으로 판정"""

import json
from dataclasses import dataclass
from typing import Literal, Protocol

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.dates import iso_dates_compatible, iso_periods_overlap, normalize_date
from apolo.extraction.linking import (
    MAX_SNIPPET_CHARS,
    LinkingResult,
    first,
    index_extraction,
    representative_snippet,
)
from apolo.extraction.prompts.linking import ENTITY_LINKING_PROMPTS
from apolo.extraction.work_linking import WorkLinker

LinkedClass = Literal["Organization", "Activity", "Credential"]
LINKED_ENTITY_CLASSES: tuple[LinkedClass, ...] = ("Organization", "Activity", "Credential")
MIN_ENTITY_LINK_CONFIDENCE = 0.80

# 판정에 보여줄 Fact. 첫 번째가 이름이다.
_FIELDS: dict[LinkedClass, tuple[str, ...]] = {
    "Organization": ("name", "type", "homepage"),
    "Activity": ("name", "kind", "role", "start", "end"),
    "Credential": ("title", "kind", "issuerName", "date", "grade"),
}
ID_PREFIX: dict[LinkedClass, str] = {"Organization": "O", "Activity": "A", "Credential": "C"}
_DATE_FIELDS = frozenset({"start", "end", "date"})


@dataclass(frozen=True)
class EntitySummary:
    """판정에 보여줄 요약. id는 기존 Entity(O1·A1·C1 …)나 이번 추출 후보(s…:e…)의 임시 ID다"""

    id: str
    class_type: LinkedClass
    facts: dict[str, tuple[str, ...]]
    # 기관은 연결된 활동·학력·경력, 활동은 소속 기관 이름
    related: tuple[str, ...] = ()
    snippet: str | None = None


class Linker(WorkLinker, Protocol):
    def link_entities(
        self, class_type: LinkedClass, summaries: list[EntitySummary]
    ) -> LinkingResult: ...


def summary_from_facts(
    id: str,
    class_type: LinkedClass,
    values: dict[str, list[str]],
    related: list[str],
    evidence: list[tuple[str, str]],
) -> EntitySummary | None:
    """이름이 없는 Entity는 판정하지 않는다. 기관은 근거 문장 대신 연결된 항목을 보여준다"""
    # 판정은 검증보다 먼저라 날짜 표기(2024.12)를 검증과 같은 ISO 형식으로 맞춘다
    facts = {
        predicate: tuple(
            dict.fromkeys(
                normalize_date(v) if predicate in _DATE_FIELDS else v for v in values[predicate]
            )
        )
        for predicate in _FIELDS[class_type]
        if values.get(predicate)
    }
    name = first(facts, _FIELDS[class_type][0])
    if name is None:
        return None
    snippet = None if class_type == "Organization" else representative_snippet(evidence, name)
    return EntitySummary(id, class_type, facts, tuple(dict.fromkeys(related))[:5], snippet)


def new_entity_summaries(
    source_index: int, source: CollectedSource, extraction: ExtractionResult
) -> dict[LinkedClass, dict[str, EntitySummary]]:
    """추출 결과의 기관·활동·자격 후보 요약. 키는 클래스, Entity ref다"""
    index = index_extraction(source, extraction)
    classes = {entity.ref: entity.class_type for entity in extraction.entities}

    def name_of(ref: str) -> str | None:
        facts = index.values.get(ref, {})
        names = facts.get("name") or facts.get("title") or facts.get("role")
        return names[0] if names else None

    related: dict[str, list[str]] = {}
    for relation in extraction.relations:
        if relation.predicate != "atOrganization":
            continue
        subject, org = name_of(relation.subject_ref), name_of(relation.object_ref)
        if subject:
            related.setdefault(relation.object_ref, []).append(
                f"{classes.get(relation.subject_ref)}:{subject}"
            )
        if org:
            related.setdefault(relation.subject_ref, []).append(org)

    summaries: dict[LinkedClass, dict[str, EntitySummary]] = {c: {} for c in LINKED_ENTITY_CLASSES}
    for entity in extraction.entities:
        if entity.class_type not in summaries:
            continue
        summary = summary_from_facts(
            f"s{source_index}:{entity.ref}",
            entity.class_type,
            index.values.get(entity.ref, {}),
            related.get(entity.ref, []),
            index.evidence(entity.ref),
        )
        if summary is not None:
            summaries[entity.class_type][entity.ref] = summary
    return summaries


def entities_compatible(members: list[EntitySummary]) -> bool:
    """LLM이 묶어도 홈페이지·kind·날짜·등급이 서로 다르거나 활동 기간이 겹치지 않으면 버린다"""
    class_type = members[0].class_type
    if class_type == "Organization":
        return _at_most_one(members, "homepage")
    if class_type == "Activity":
        return iso_periods_overlap(
            [(first(m.facts, "start"), first(m.facts, "end")) for m in members]
        )
    return (
        _at_most_one(members, "kind")
        and _at_most_one(members, "grade")
        and iso_dates_compatible([d for m in members for d in m.facts.get("date", ())])
    )


def build_entity_linking_prompt(
    class_type: LinkedClass, summaries: list[EntitySummary]
) -> tuple[str, str]:
    payload = [_summary_payload(summary) for summary in summaries]
    user = f"{class_type} 목록(JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return ENTITY_LINKING_PROMPTS[class_type], user


def _summary_payload(summary: EntitySummary) -> dict[str, object]:
    payload: dict[str, object] = {"id": summary.id}
    for predicate, items in summary.facts.items():
        payload[predicate] = items[0] if len(items) == 1 else list(items)
    if summary.related:
        key = "related" if summary.class_type == "Organization" else "organizations"
        payload[key] = list(summary.related)
    if summary.snippet:
        payload["snippet"] = summary.snippet[:MAX_SNIPPET_CHARS]
    return payload


def _at_most_one(members: list[EntitySummary], predicate: str) -> bool:
    values = {" ".join(v.split()).casefold() for m in members for v in m.facts.get(predicate, ())}
    return len(values) <= 1
