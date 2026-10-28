"""출처마다 표기가 달라 규칙으로 합쳐지지 않는 같은 기관·활동·자격을 LLM으로 판정"""

import json
from dataclasses import dataclass
from textwrap import dedent
from typing import Literal, Protocol

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.extraction.validation import normalize_date
from apolo.extraction.work_linking import (
    WorkLinker,
    WorkLinkingResult,
    periods_overlap,
    representative_snippet,
)

LinkedClass = Literal["Organization", "Activity", "Credential"]
LINKED_ENTITY_CLASSES: tuple[LinkedClass, ...] = ("Organization", "Activity", "Credential")
MIN_ENTITY_LINK_CONFIDENCE = 0.80
MAX_SNIPPET_CHARS = 200

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

    @property
    def start(self) -> str | None:
        return _first(self.facts, "start")

    @property
    def end(self) -> str | None:
        return _first(self.facts, "end")


class Linker(WorkLinker, Protocol):
    def link_entities(
        self, class_type: LinkedClass, summaries: list[EntitySummary]
    ) -> WorkLinkingResult: ...


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
    name = _first(facts, _FIELDS[class_type][0])
    if name is None:
        return None
    snippet = None if class_type == "Organization" else representative_snippet(evidence, name)
    return EntitySummary(id, class_type, facts, tuple(dict.fromkeys(related))[:5], snippet)


def new_entity_summaries(
    source_index: int, source: CollectedSource, extraction: ExtractionResult
) -> dict[LinkedClass, dict[str, EntitySummary]]:
    """추출 결과의 기관·활동·자격 후보 요약. 키는 클래스, Entity ref다"""
    snippets = {item.locator: item.snippet for item in source.evidence_candidates}
    classes = {entity.ref: entity.class_type for entity in extraction.entities}
    values: dict[str, dict[str, list[str]]] = {}
    refs: dict[str, list[str]] = {}
    for fact in extraction.facts:
        if isinstance(fact.value, str):
            values.setdefault(fact.entity_ref, {}).setdefault(fact.predicate, []).append(fact.value)
        refs.setdefault(fact.entity_ref, []).extend(fact.evidence_refs)
    for link in extraction.entity_evidence:
        refs.setdefault(link.entity_ref, []).extend(link.evidence_refs)

    def name_of(ref: str) -> str | None:
        facts = values.get(ref, {})
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
        locators = list(dict.fromkeys(refs.get(entity.ref, [])))
        summary = summary_from_facts(
            f"s{source_index}:{entity.ref}",
            entity.class_type,
            values.get(entity.ref, {}),
            related.get(entity.ref, []),
            [(locator, snippets[locator]) for locator in locators if locator in snippets],
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
        return periods_overlap(members)
    return (
        _at_most_one(members, "kind")
        and _at_most_one(members, "grade")
        and _dates_compatible([d for m in members for d in m.facts.get("date", ())])
    )


SYSTEM_PROMPTS: dict[LinkedClass, str] = {
    "Organization": """
        한 사용자의 포트폴리오 KG에서 같은 기관·단체를 가리키는 Organization 항목을 묶는다.
        같은 기관이 이력서, 활동 기록, 프로젝트 페이지처럼 여러 출처에서 다른 표기로 적힌다.

        [같은 기관으로 묶는다]
        - 약어와 정식 이름, 영문과 국문 이름, 띄어쓰기·기호 차이.
        - 이름 앞뒤에 설명이 붙은 표기(예: 단체 성격, 소속 학교·학과 수식어)와 핵심 이름만 쓴 표기.
        - related에 같은 활동·학력·경력이 연결되어 있으면 강한 근거다.

        [묶지 않는다]
        - 상위 기관과 그 안의 다른 부서·학과·사업단·동아리. 학교와 그 학교의 동아리는 다른 기관이다.
        - 이름 일부만 겹치는 서로 다른 단체.
        - 근거가 부족해 확신할 수 없는 경우. 애매하면 묶지 않는다.
        """,
    "Activity": """
        한 사용자의 포트폴리오 KG에서 같은 활동을 가리키는 Activity 항목을 묶는다.
        같은 활동이 이력서 한 줄, 활동 상세 페이지처럼 여러 출처에서 다른 표기로 적힌다.

        [같은 활동으로 묶는다]
        - 같은 단체·프로그램에서 같은 기간에 한 활동.
          이름이 약어·정식 이름·수식어 차이로 달라도 된다.
        - 역할 표현이 달라도 같은 기수·직책을 가리키면 같은 활동이다.
        - kind가 program·volunteer처럼 달라도 이름·기간·내용이 같은 활동을 가리키면 묶는다.

        [묶지 않는다]
        - 같은 단체에서 기간·기수가 다른 활동.
        - 같은 기관 소속이지만 이름·내용이 다른 활동(예: 같은 학교의 다른 동아리).
        - 근거가 부족해 확신할 수 없는 경우. 애매하면 묶지 않는다.
        """,
    "Credential": """
        한 사용자의 포트폴리오 KG에서 같은 자격·수상 기록을 가리키는 Credential 항목을 묶는다.
        같은 기록이 이력서와 상세 페이지처럼 여러 출처에서 다른 표기로 적힌다.

        [같은 기록으로 묶는다]
        - 약어와 정식 이름(괄호 속 약어 포함), 등급·점수를 제목에 붙인 표기와 뺀 표기.
        - 대회 이름 표기가 달라도 같은 대회·같은 시기의 같은 수상.

        [묶지 않는다]
        - kind가 다른 항목(certification과 award).
        - 같은 시험·대회라도 날짜(연도·회차)가 다르거나 등급·점수가 다른 기록.
        - 필기 합격과 최종 취득처럼 단계가 다른 기록.
        - 근거가 부족해 확신할 수 없는 경우. 애매하면 묶지 않는다.
        """,
}

_OUTPUT_RULES = """
    [출력]
    - 묶을 항목만 groups로 반환한다. 묶을 것이 없으면 빈 배열이다.
    - ids에는 목록에 있는 id만 쓴다. 한 id는 한 group에만 넣는다.
    - confidence는 같은 대상이라고 확신하는 정도(0~1)다.
    - reason에는 같다고 본 근거를 한 문장으로 쓴다.
    """


def build_entity_linking_prompt(
    class_type: LinkedClass, summaries: list[EntitySummary]
) -> tuple[str, str]:
    system = dedent(SYSTEM_PROMPTS[class_type]).strip() + "\n\n" + dedent(_OUTPUT_RULES).strip()
    payload = [_summary_payload(summary) for summary in summaries]
    user = f"{class_type} 목록(JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return system, user


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


def _first(facts: dict[str, tuple[str, ...]], predicate: str) -> str | None:
    values = facts.get(predicate)
    return values[0] if values else None


def _at_most_one(members: list[EntitySummary], predicate: str) -> bool:
    values = {" ".join(v.split()).casefold() for m in members for v in m.facts.get(predicate, ())}
    return len(values) <= 1


def _dates_compatible(dates: list[str]) -> bool:
    """정밀도가 다른 날짜(2024, 2024-12, 2024-12-13)는 앞부분이 같으면 같은 날로 본다"""
    return all(
        a.startswith(b) or b.startswith(a)
        for index, a in enumerate(dates)
        for b in dates[index + 1 :]
    )
