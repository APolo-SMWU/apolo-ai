"""같은 사용자 KG 안에서 추출 Entity의 재사용 여부 판정"""

import re
from dataclasses import dataclass, field, replace
from functools import cache
from typing import Literal
from uuid import UUID, uuid4

from apolo.contracts.extraction import ExtractionResult
from apolo.ontology.skill_categories import SKILL_CATEGORY_CATALOG
from apolo.ontology.values import is_valid_value
from apolo.text_similarity import similar_title

StrongKeyType = Literal["work_url", "organization_homepage"]

_STRONG_KEY_PROPERTIES: dict[tuple[str, str], StrongKeyType] = {
    ("Work", "url"): "work_url",
    ("Organization", "homepage"): "organization_homepage",
}
# 동일 skill 처리
_PARENTHESIZED = re.compile(r"^\s*(.+?)\s*\(([^()]+)\)\s*$")
_SPACED_VERSION = re.compile(r"^(.*\S)\s+v?\d+(?:\.\d+)*$", re.IGNORECASE)
_ATTACHED_VERSION = re.compile(r"^(.*[A-Za-z+#])\d+(?:\.\d+)*$")


@dataclass(frozen=True)
class StrongEntityKey:
    """같은 KG 안에서 한 Entity만 가질 수 있는 외부 식별자"""

    key_type: StrongKeyType
    key_value: str
    is_strong: Literal[True] = True


@dataclass(frozen=True)
class ExistingEntity:
    """같은 사용자 KG에 저장된 활성 Entity의 식별용 정보"""

    id: UUID
    class_type: str
    facts: dict[str, frozenset[str | bool]]
    organization_ids: frozenset[UUID] = frozenset()
    strong_keys: frozenset[StrongEntityKey] = frozenset()


@dataclass(frozen=True)
class EntityResolution:
    """기존 ID 재사용, 복수 일치 보류, 새 Entity 후보를 구분한 결과"""

    matched: dict[str, UUID]
    ambiguous: tuple[str, ...]
    unmatched: tuple[str, ...]
    new_ids: dict[str, UUID] = field(default_factory=dict)


def candidate_strong_keys(extraction: ExtractionResult) -> dict[str, list[StrongEntityKey]]:
    """형식이 유효한 URL Fact에서만 키 생성, 이름·제목만으로는 생성하지 않음"""
    classes: dict[str, str] = {}
    for entity in extraction.entities:
        if entity.ref in classes:
            raise ValueError("중복된 Entity ref에서는 식별 키를 만들 수 없습니다.")
        classes[entity.ref] = entity.class_type

    keys: dict[str, list[StrongEntityKey]] = {ref: [] for ref in classes}
    for fact in extraction.facts:
        class_type = classes.get(fact.entity_ref)
        key_type = _STRONG_KEY_PROPERTIES.get((class_type, fact.predicate))
        if key_type is None or not is_valid_value("uri", fact.value):
            continue
        key = StrongEntityKey(key_type=key_type, key_value=fact.value)
        if key not in keys[fact.entity_ref]:
            keys[fact.entity_ref].append(key)
    return keys


def resolve_existing_entities(
    extraction: ExtractionResult,
    existing: list[ExistingEntity],
    forced_ids: dict[str, UUID] | None = None,
) -> EntityResolution:
    """한 사용자 KG의 기존 ID 재사용·새 ID 발급·모호한 후보 보류

    forced_ids는 Work 병합 판정이 정한 ref → Work ID다. 규칙 비교보다 먼저 적용한다.
    아직 없는 ID면 그 ID로 새 Work를 만들어 뒤따르는 Source가 같은 ID를 쓰게 한다.
    """
    forced_ids = forced_ids or {}
    classes: dict[str, str] = {}
    for entity in extraction.entities:
        if entity.ref in classes:
            raise ValueError("중복된 Entity ref를 식별할 수 없습니다.")
        classes[entity.ref] = entity.class_type

    facts: dict[str, dict[str, frozenset[str | bool]]] = {ref: {} for ref in classes}
    values: dict[str, dict[str, set[str | bool]]] = {ref: {} for ref in classes}
    for fact in extraction.facts:
        if fact.entity_ref in values:
            values[fact.entity_ref].setdefault(fact.predicate, set()).add(fact.value)
    for ref, predicates in values.items():
        facts[ref] = {predicate: frozenset(items) for predicate, items in predicates.items()}

    affiliations: dict[str, set[str]] = {ref: set() for ref in classes}
    for relation in extraction.relations:
        if relation.predicate == "atOrganization" and relation.subject_ref in affiliations:
            affiliations[relation.subject_ref].add(relation.object_ref)

    strong_keys = candidate_strong_keys(extraction)
    matched: dict[str, UUID] = {}
    ambiguous: list[str] = []
    unmatched: list[str] = []
    new_ids: dict[str, UUID] = {}
    resolved_ids: dict[str, UUID] = {}
    stored_ids = {entity.id for entity in existing}
    pool = list(existing)
    # 학력·경력·활동은 소속 기관의 ID가 정해진 뒤에 비교한다
    order = {
        "Organization": 0,
        "Work": 1,
        "Skill": 1,
        "Credential": 1,
        "Activity": 2,
        "Education": 2,
        "Experience": 2,
    }
    for entity in sorted(extraction.entities, key=lambda item: order.get(item.class_type, 3)):
        ref = entity.ref
        candidate = ExistingEntity(
            id=UUID(int=0),
            class_type=entity.class_type,
            facts=facts[ref],
            strong_keys=frozenset(strong_keys[ref]),
        )
        if entity.class_type in {"Activity", "Education", "Experience"}:
            org_refs = affiliations[ref]
            if any(org in ambiguous for org in org_refs):
                ambiguous.append(ref)
                continue
            if len(org_refs) > 1 or any(org not in resolved_ids for org in org_refs):
                ambiguous.append(ref)
                continue
            candidate = ExistingEntity(
                id=candidate.id,
                class_type=candidate.class_type,
                facts=candidate.facts,
                organization_ids=frozenset(
                    resolved_ids[org] for org in org_refs if org in resolved_ids
                ),
            )
            if entity.class_type in {"Education", "Experience"} and not org_refs:
                entity_id = uuid4()
                resolved_ids[ref] = entity_id
                new_ids[ref] = entity_id
                unmatched.append(ref)
                pool.append(replace(candidate, id=entity_id))
                continue

        forced_id = forced_ids.get(ref) if entity.class_type == "Work" else None
        if forced_id is not None and not any(item.id == forced_id for item in pool):
            resolved_ids[ref] = forced_id
            new_ids[ref] = forced_id
            unmatched.append(ref)
            pool.append(replace(candidate, id=forced_id))
            continue
        if forced_id is not None:
            matches = {forced_id}
        else:
            matches = {item.id for item in pool if _same_entity(candidate, item)}
        if len(matches) > 1:
            matching_entities = [item for item in pool if item.id in matches]
            if all(
                _same_entity(left, right)
                for index, left in enumerate(matching_entities)
                for right in matching_entities[index + 1 :]
            ):
                # 기존 KG에 이미 저장된 중복 후보는 안정적인 ID 하나로 갱신한다.
                # 남은 기존 ID는 Graph B의 표시 단계에서도 중복 제거한다.
                matches = {min(matches, key=lambda entity_id: entity_id.int)}
        if len(matches) == 1:
            entity_id = next(iter(matches))
            resolved_ids[ref] = entity_id
            if entity_id in stored_ids:
                matched[ref] = entity_id
            else:
                unmatched.append(ref)
                new_ids[ref] = entity_id
            # 이번 묶음에서 추가로 확인한 이름·URL도 뒤따르는 후보의 식별에 사용한다
            for index, item in enumerate(pool):
                if item.id == entity_id:
                    merged_facts = {
                        predicate: item.facts.get(predicate, frozenset())
                        | candidate.facts.get(predicate, frozenset())
                        for predicate in item.facts.keys() | candidate.facts.keys()
                    }
                    pool[index] = replace(
                        item,
                        facts=merged_facts,
                        strong_keys=item.strong_keys | candidate.strong_keys,
                    )
                    break
        elif matches:
            ambiguous.append(ref)
        else:
            entity_id = uuid4()
            resolved_ids[ref] = entity_id
            new_ids[ref] = entity_id
            unmatched.append(ref)
            pool.append(replace(candidate, id=entity_id))
    return EntityResolution(matched, tuple(ambiguous), tuple(unmatched), new_ids)


def _same_entity(candidate: ExistingEntity, stored: ExistingEntity) -> bool:
    if candidate.class_type != stored.class_type:
        return False
    kind = candidate.class_type
    if kind == "Work":
        candidate_urls = _key_values(candidate, "work_url")
        stored_urls = _key_values(stored, "work_url")
        by_url = bool(candidate_urls & stored_urls)
        by_title = _similar_fact(candidate, stored, "title")
        urls_conflict = bool(candidate_urls and stored_urls and not by_url)
        return (
            _compatible(candidate, stored, "kind")
            and not urls_conflict
            and (by_url or by_title)
        )
    if kind == "Organization":
        candidate_homepages = _key_values(candidate, "organization_homepage")
        stored_homepages = _key_values(stored, "organization_homepage")
        by_homepage = bool(candidate_homepages & stored_homepages)
        by_name = _similar_fact(candidate, stored, "name")
        homepages_conflict = bool(
            candidate_homepages and stored_homepages and not by_homepage
        )
        return (
            _compatible(candidate, stored, "type")
            and not homepages_conflict
            and (by_homepage or by_name)
        )
    if kind == "Skill":
        return _compatible(candidate, stored, "kind") and bool(
            _skill_aliases(candidate) & _skill_aliases(stored)
        )
    if kind == "Credential":
        return (
            _similar_fact(candidate, stored, "title")
            and _has_values(candidate, stored, "date")
            and _compatible(candidate, stored, "date")
            and _compatible(candidate, stored, "issuerName")
            and _compatible(candidate, stored, "kind")
        )
    if kind == "Education":
        return (
            bool(candidate.organization_ids & stored.organization_ids)
            and (
                _similar_fact(candidate, stored, "major")
                or _similar_fact(candidate, stored, "degree")
            )
            and all(_compatible(candidate, stored, field) for field in ("major", "degree", "start"))
        )
    if kind == "Experience":
        return (
            bool(candidate.organization_ids & stored.organization_ids)
            and _similar_fact(candidate, stored, "role")
            and all(
                _compatible(candidate, stored, field)
                for field in ("department", "kind", "start")
            )
        )
    if kind == "Activity":
        organizations_compatible = (
            not candidate.organization_ids
            or not stored.organization_ids
            or bool(candidate.organization_ids & stored.organization_ids)
        )
        return (
            _similar_fact(candidate, stored, "name")
            and organizations_compatible
            and all(
                _compatible(candidate, stored, field)
                for field in ("kind", "start", "end", "isCurrent")
            )
        )
    return False


def _skill_aliases(entity: ExistingEntity) -> set[str]:
    """이름의 표기 차이를 지운 비교 키. 'Retrieval-Augmented Generation (RAG)'은 RAG도 포함"""
    aliases = set()
    is_tool = "tool" in {_normalized(value) for value in entity.facts.get("kind", ())}
    for name in entity.facts.get("name", ()):
        if not isinstance(name, str):
            continue
        aliases.add(_skill_key(name))
        unversioned = _without_version(name) if is_tool else None
        if unversioned is not None:
            aliases.add(_skill_key(unversioned))
        match = _PARENTHESIZED.match(name)
        if match is None:
            continue
        outer, inner = match.group(1), match.group(2)
        if _is_acronym(inner, outer) or _is_acronym(outer, inner):
            aliases |= {_skill_key(outer), _skill_key(inner)}
    aliases.discard("")
    return aliases


def _skill_key(name: str) -> str:
    # C, C++, C#처럼 기호로만 구분되는 이름이 합쳐지지 않도록 기호를 먼저 글자로 바꾼다.
    text = name.casefold().replace("+", "plus").replace("#", "sharp")
    return re.sub(r"[\W_]+", "", text)


def _without_version(name: str) -> str | None:
    """버전을 뗀 이름. ROS 2처럼 사전에 있는 이름과 S3처럼 숫자가 이름인 경우는 떼지 않는다"""
    catalog = _catalog_keys()
    if _skill_key(name) in catalog:
        return None
    spaced = _SPACED_VERSION.match(name)
    if spaced is not None:
        return spaced.group(1)
    attached = _ATTACHED_VERSION.match(name)
    if attached is not None and _skill_key(attached.group(1)) in catalog:
        return attached.group(1)
    return None


@cache
def _catalog_keys() -> frozenset[str]:
    return frozenset(
        _skill_key(name)
        for _, examples in SKILL_CATEGORY_CATALOG.values()
        for name in examples.split(",")
        if name.strip()
    )


def _is_acronym(short: str, long: str) -> bool:
    words = [word for word in re.split(r"[\s\-_/]+", long) if word]
    initials = "".join(word[0] for word in words)
    return len(words) > 1 and short.strip().casefold() == initials.casefold()


def _similar_fact(left: ExistingEntity, right: ExistingEntity, predicate: str) -> bool:
    left_values = left.facts.get(predicate, frozenset())
    right_values = right.facts.get(predicate, frozenset())
    return any(
        isinstance(a, str) and isinstance(b, str) and similar_title(a, b)
        for a in left_values
        for b in right_values
    )


def _key_values(entity: ExistingEntity, key_type: StrongKeyType) -> set[str]:
    return {
        key.key_value for key in entity.strong_keys if key.key_type == key_type
    }


def _compatible(left: ExistingEntity, right: ExistingEntity, predicate: str) -> bool:
    left_values = {_normalized(value) for value in left.facts.get(predicate, ())}
    right_values = {_normalized(value) for value in right.facts.get(predicate, ())}
    if not left_values or not right_values:
        return True
    if predicate in {"start", "end", "date"}:
        return any(
            isinstance(a, str)
            and isinstance(b, str)
            and (a == b or a.startswith(b + "-") or b.startswith(a + "-"))
            for a in left_values
            for b in right_values
        )
    return bool(left_values & right_values)


def _has_values(left: ExistingEntity, right: ExistingEntity, predicate: str) -> bool:
    return bool(left.facts.get(predicate) and right.facts.get(predicate))


def _normalized(value: str | bool) -> str | bool:
    return " ".join(value.split()).casefold() if isinstance(value, str) else value
