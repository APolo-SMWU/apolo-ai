"""Block별 검증기가 공유하는 KG 조회·값 변환 도구"""

import re
from uuid import UUID

from apolo.contracts.knowledge import ActiveKnowledgeGraph


def item_entity_id(value: str) -> UUID | None:
    """출력 item의 Entity ID를 UUID로 변환한다"""

    try:
        return UUID(value)
    except ValueError:
        return None


def entity_facts(graph: ActiveKnowledgeGraph, entity_id: UUID):
    """Entity에 직접 연결된 Fact를 반환한다"""

    return [fact for fact in graph.facts if fact.entity_id == entity_id]


def organization_names(graph: ActiveKnowledgeGraph, entity_id: UUID) -> set[str]:
    """Entity의 atOrganization relation으로 연결된 기관명을 반환한다"""

    organization_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.subject_entity_id == entity_id and relation.predicate == "atOrganization"
    }
    return {
        fact.value
        for fact in graph.facts
        if fact.entity_id in organization_ids
        and fact.predicate == "name"
        and isinstance(fact.value, str)
    }


def fact_values(facts, predicate: str) -> set[str]:
    """문자열 Fact의 값을 모아 반환한다"""

    return {
        fact.value
        for fact in facts
        if fact.predicate == predicate and isinstance(fact.value, str)
    }


def date_values(facts) -> dict[str, set[str]]:
    """KG 날짜 Fact를 block 출력 형식으로 변환한다"""

    return {
        predicate: {
            format_output_date(fact.value)
            for fact in facts
            if fact.predicate == predicate and isinstance(fact.value, str)
        }
        for predicate in ("start", "end")
    }


def has_current_fact(facts) -> bool:
    """현재 상태를 나타내는 isCurrent=true Fact가 있는지 확인한다"""

    return any(fact.predicate == "isCurrent" and fact.value is True for fact in facts)


def format_output_date(value: str) -> str:
    """KG의 ISO 날짜를 Block 출력 형식(YYYY 또는 YYYY.MM)으로 변환한다"""

    match = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-\d{2})?", value)
    if match is None:
        return value
    year, month = match.groups()
    return f"{year}.{month}" if month else year
