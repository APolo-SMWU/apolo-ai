"""같은 사용자 KG 안에서 추출 Entity의 재사용 여부 판정"""

from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID, uuid4

from apolo.contracts.extraction import ExtractionResult
from apolo.ontology.values import is_valid_value

StrongKeyType = Literal["work_url", "organization_homepage"]

_STRONG_KEY_PROPERTIES: dict[tuple[str, str], StrongKeyType] = {
    ("Work", "url"): "work_url",
    ("Organization", "homepage"): "organization_homepage",
}


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
    extraction: ExtractionResult, existing: list[ExistingEntity]
) -> EntityResolution:
    """한 사용자 KG의 기존 ID 재사용·새 ID 발급·모호한 후보 보류"""
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

        matches = {item.id for item in pool if _same_entity(candidate, item)}
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
        by_url = bool(candidate.strong_keys & stored.strong_keys)
        by_title = _shared(candidate, stored, "title")
        return _compatible(candidate, stored, "kind") and (by_url or by_title)
    if kind == "Organization":
        by_homepage = bool(candidate.strong_keys & stored.strong_keys)
        by_name = _shared(candidate, stored, "name")
        return _compatible(candidate, stored, "type") and (by_homepage or by_name)
    if kind == "Skill":
        return _shared(candidate, stored, "name")
    if kind == "Credential":
        return (
            _shared(candidate, stored, "title")
            and _has_values(candidate, stored, "date")
            and _compatible(candidate, stored, "date")
            and _compatible(candidate, stored, "issuerName")
            and _compatible(candidate, stored, "kind")
        )
    if kind == "Education":
        return (
            bool(candidate.organization_ids & stored.organization_ids)
            and (_shared(candidate, stored, "major") or _shared(candidate, stored, "degree"))
            and all(_compatible(candidate, stored, field) for field in ("major", "degree", "start"))
        )
    if kind == "Experience":
        return (
            bool(candidate.organization_ids & stored.organization_ids)
            and _shared(candidate, stored, "role")
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
            _shared(candidate, stored, "name")
            and organizations_compatible
            and all(
                _compatible(candidate, stored, field)
                for field in ("role", "kind", "start", "end", "isCurrent")
            )
        )
    return False


def _shared(left: ExistingEntity, right: ExistingEntity, predicate: str) -> bool:
    left_values = {_normalized(value) for value in left.facts.get(predicate, ())}
    right_values = {_normalized(value) for value in right.facts.get(predicate, ())}
    return bool(left_values & right_values)


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
