"""LLM 추출 후보를 온톨로지 기준으로 항목별 검증한다. 틀린 항목만 제외하고 이유를 남긴다."""

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from apolo.contracts.extraction import (
    EXTRACTABLE_PROPERTIES,
    EXTRACTABLE_RELATIONS,
    SELF_REF,
    EntityCandidate,
    ExtractionResult,
    FactCandidate,
    RelationCandidate,
)
from apolo.ontology.personal import (
    MULTI_VALUED_PROPERTIES,
    PROPERTY_TYPES,
    PROPERTY_VALUES,
    RELATION_PAIRS,
)
from apolo.ontology.values import is_valid_value

# 구분자만 다른 날짜 표기(2024.3, 2024/03/05, 2024년 3월 등). 네 자리 연도와 구분자가 있어야 한다.
_DATE_NOTATION = re.compile(
    r"([0-9]{4})"
    r"(?:\s*(?:년|[./-])\s*([0-9]{1,2})"
    r"(?:\s*(?:월|[./-])\s*([0-9]{1,2}))?)?"
    r"\s*(?:년|월|일|\.)?"
)

# Entity가 무엇인지 알려 주는 속성. 보류된 값도 인정한다.
_IDENTITY_PREDICATES = {
    "Work": "title",
    "Credential": "title",
    "Skill": "name",
    "Organization": "name",
    "Experience": "role",
    "Education": "major",
}
# 이 Class는 이름 있는 소속 기관 Relation이 있으면 역할·전공이 없어도 인정한다.
_IDENTIFIED_BY_ORGANIZATION = frozenset({"Experience", "Education"})


@dataclass(frozen=True)
class ExtractionIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ExtractionValidation:
    """통과한 항목, 값 충돌로 보류한 Fact, 제외·보류 이유.

    uncertain은 버리지 않고 candidate로 저장해 이후 갱신이나 사용자 확인으로 정한다.
    """

    result: ExtractionResult
    uncertain: list[FactCandidate]
    issues: list[ExtractionIssue]


Report = Callable[[str, str, str], None]


def validate_extraction(extraction: ExtractionResult) -> ExtractionValidation:
    issues: list[ExtractionIssue] = []

    def report(code: str, path: str, message: str) -> None:
        issues.append(ExtractionIssue(code=code, path=path, message=message))

    # 같은 ref가 여러 번 나오면 어느 Entity인지 알 수 없어 모두 제외한다.
    ref_counts = Counter(entity.ref for entity in extraction.entities)
    entities: dict[str, EntityCandidate] = {}
    for index, entity in enumerate(extraction.entities):
        if ref_counts[entity.ref] > 1:
            report("DUPLICATE_REF", f"entities[{index}]", "같은 ref가 여러 Entity에 쓰였습니다.")
        else:
            entities[entity.ref] = entity

    checked_facts: list[tuple[str, FactCandidate]] = []
    for index, fact in enumerate(extraction.facts):
        path = f"facts[{index}]"
        checked = _check_fact(fact, entities, path, report)
        if checked is not None:
            checked_facts.append((path, checked))
    facts, uncertain = _merge_facts(checked_facts, entities, report)

    relations = _merge_relations(
        relation
        for index, relation in enumerate(extraction.relations)
        if _is_valid_relation(relation, entities, f"relations[{index}]", report)
    )

    unidentified = _unidentified_refs(entities, facts + uncertain, relations)
    for index, entity in enumerate(extraction.entities):
        if entity.ref in unidentified:
            report(
                "MISSING_IDENTITY",
                f"entities[{index}]",
                "식별 속성이 없어 딸린 Fact·Relation과 함께 제외합니다.",
            )
    entities = {ref: entity for ref, entity in entities.items() if ref not in unidentified}
    facts = [fact for fact in facts if fact.entity_ref not in unidentified]
    uncertain = [fact for fact in uncertain if fact.entity_ref not in unidentified]
    relations = [
        relation
        for relation in relations
        if relation.subject_ref not in unidentified and relation.object_ref not in unidentified
    ]

    result = ExtractionResult(entities=list(entities.values()), facts=facts, relations=relations)
    return ExtractionValidation(result=result, uncertain=uncertain, issues=issues)


def _unidentified_refs(
    entities: dict[str, EntityCandidate],
    facts: list[FactCandidate],
    relations: list[RelationCandidate],
) -> set[str]:
    """식별 속성이 없는 Entity ref. 기관을 먼저 판단해야 경력·학력의 소속을 판단할 수 있다."""
    identified = {(fact.entity_ref, fact.predicate) for fact in facts}

    def has_identity(ref: str) -> bool:
        return (ref, _IDENTITY_PREDICATES[entities[ref].class_type]) in identified

    unidentified = {
        ref
        for ref, entity in entities.items()
        if entity.class_type not in _IDENTIFIED_BY_ORGANIZATION and not has_identity(ref)
    }
    affiliated = {
        relation.subject_ref
        for relation in relations
        if relation.predicate == "atOrganization" and relation.object_ref not in unidentified
    }
    return unidentified | {
        ref
        for ref, entity in entities.items()
        if entity.class_type in _IDENTIFIED_BY_ORGANIZATION
        and not has_identity(ref)
        and ref not in affiliated
    }


def _merge_facts(
    checked_facts: list[tuple[str, FactCandidate]],
    entities: dict[str, EntityCandidate],
    report: Report,
) -> tuple[list[FactCandidate], list[FactCandidate]]:
    """같은 값은 confidence가 가장 높은 하나로 합친다. 값이 하나인 속성의 충돌은 보류한다."""
    groups: dict[tuple[str, str], dict[str | bool, FactCandidate]] = {}
    paths: dict[tuple[str, str], list[str]] = {}
    for path, fact in checked_facts:
        key = (fact.entity_ref, fact.predicate)
        group = groups.setdefault(key, {})
        current = group.get(fact.value)
        if current is None or fact.confidence > current.confidence:
            group[fact.value] = fact
        paths.setdefault(key, []).append(path)

    kept: list[FactCandidate] = []
    uncertain: list[FactCandidate] = []
    for (ref, predicate), group in groups.items():
        multi_valued = (entities[ref].class_type, predicate) in MULTI_VALUED_PROPERTIES
        if len(group) > 1 and not multi_valued:
            uncertain.extend(group.values())
            for path in paths[(ref, predicate)]:
                report("CONFLICTING_VALUES", path, f"{predicate} 값이 서로 달라 보류합니다.")
        else:
            kept.extend(group.values())
    return kept, uncertain


def _merge_relations(relations: Iterable[RelationCandidate]) -> list[RelationCandidate]:
    """같은 Relation은 confidence가 가장 높은 하나로 합친다."""
    merged: dict[tuple[str, str, str], RelationCandidate] = {}
    for relation in relations:
        key = (relation.subject_ref, relation.predicate, relation.object_ref)
        current = merged.get(key)
        if current is None or relation.confidence > current.confidence:
            merged[key] = relation
    return list(merged.values())


def _check_fact(
    fact: FactCandidate, entities: dict[str, EntityCandidate], path: str, report: Report
) -> FactCandidate | None:
    """통과하면 값 목록 속성만 형식을 맞춘 Fact를, 아니면 None을 반환한다."""
    if fact.entity_ref == SELF_REF:
        report("SELF_FACT", path, "본인 속성은 프로필에서만 받습니다.")
        return None
    entity = entities.get(fact.entity_ref)
    if entity is None:
        report("MISSING_ENTITY", path, "가리키는 Entity가 없습니다.")
        return None
    if fact.predicate not in EXTRACTABLE_PROPERTIES[entity.class_type]:
        report("INVALID_PROPERTY", path, f"{entity.class_type}에서 추출하지 않는 속성입니다.")
        return None

    # 추출 대상 속성은 값 타입이 하나뿐이다.
    value_type = PROPERTY_TYPES[entity.class_type][fact.predicate][0]
    allowed = PROPERTY_VALUES.get((entity.class_type, fact.predicate))
    value = fact.value
    if value_type == "date" and isinstance(value, str):
        value = _normalize_date(value)
    if allowed is not None and isinstance(value, str):
        # 값 목록이 있는 속성만 대소문자·공백 차이를 고친다.
        value = "_".join(value.lower().split())
    if not is_valid_value(value_type, value):
        report("INVALID_VALUE", path, f"{value_type} 형식이 아닙니다.")
        return None
    if allowed is not None and value not in allowed:
        report("INVALID_PROPERTY_VALUE", path, "허용된 값 목록에 없습니다.")
        return None
    return fact.model_copy(update={"value": value})


def _normalize_date(value: str) -> str:
    """표기만 다른 날짜를 ISO로 맞춘다. 맞지 않으면 그대로 두어 형식 검사에서 제외된다."""
    match = _DATE_NOTATION.fullmatch(value.strip())
    if match is None:
        return value
    year, month, day = match.groups()
    return "-".join([year] + [f"{int(part):02d}" for part in (month, day) if part])


def _is_valid_relation(
    relation: RelationCandidate, entities: dict[str, EntityCandidate], path: str, report: Report
) -> bool:
    classes = []
    for ref in (relation.subject_ref, relation.object_ref):
        if ref == SELF_REF:
            classes.append("Person")
        elif ref in entities:
            classes.append(entities[ref].class_type)
        else:
            report("MISSING_ENTITY", path, "가리키는 Entity가 없습니다.")
            return False
    if relation.predicate not in EXTRACTABLE_RELATIONS:
        report("INVALID_RELATION", path, "추출하지 않는 Relation입니다.")
        return False
    if tuple(classes) not in RELATION_PAIRS[relation.predicate]:
        report(
            "INVALID_RELATION_DIRECTION",
            path,
            f"{relation.predicate}는 {classes[0]} → {classes[1]} 연결을 허용하지 않습니다.",
        )
        return False
    return True
