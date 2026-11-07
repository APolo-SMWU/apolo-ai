"""Graph B 정규화에서 블록이 함께 쓰는 KG 근거 조회·값 보정"""

import re
import unicodedata
from uuid import UUID

from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.dates import OUTPUT_DATE, PRESENT
from apolo.graph_b.validators.common import (
    date_values,
    entity_facts,
    has_current_fact,
    item_entity_id,
)
from apolo.text_similarity import shares_core_terms, similar_title

_BLOCK_RELATIONS = {
    "education": ("Education", "hasEducation"),
    "experience": ("Experience", "hasExperience"),
    "activities": ("Activity", "participatedIn"),
    "works": ("Work", "participatedIn"),
    "awards": ("Credential", "holds"),
    "certification": ("Credential", "holds"),
}


_OUTPUT_DATE = re.compile(rf"^{OUTPUT_DATE}$")


def entity_context(
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


def required_value(value: str, candidates: set[str]) -> str | None:
    if value in candidates:
        return value
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def optional_value(value: str | None, candidates: set[str]) -> str | None:
    if value is None:
        return None
    return required_value(value, candidates)


def date_value(value: str | None, facts, predicate: str) -> str | None:
    if value is None:
        return None
    return optional_value(value, valid_dates(date_values(facts)[predicate]))


def end_date_value(value: str | None, facts) -> str | None:
    if value is None:
        return None
    if value == PRESENT:
        return PRESENT if has_current_fact(facts) else None
    return optional_value(value, valid_dates(date_values(facts)["end"]))


def valid_dates(values: set[str]) -> set[str]:
    return {value for value in values if _OUTPUT_DATE.fullmatch(value)}


def text_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w가-힣]+", "", normalized, flags=re.UNICODE)


def merge_descriptions(current: str | None, incoming: str | None) -> str | None:
    """중복 문장은 줄이고 병합된 항목의 서로 다른 설명은 보존한다"""
    if not current:
        return incoming
    if not incoming:
        return current
    current, incoming = current.strip(), incoming.strip()
    current_key, incoming_key = text_key(current), text_key(incoming)
    if current_key == incoming_key or current_key in incoming_key:
        return incoming if len(incoming) > len(current) else current
    if incoming_key in current_key:
        return current
    return f"{current.rstrip(' .;·')} · {incoming.lstrip(' ;·')}"


def labels_share_identity(left: set[str], right: set[str]) -> bool:
    return any(similar_title(a, b) or shares_core_terms(a, b) for a in left for b in right)
