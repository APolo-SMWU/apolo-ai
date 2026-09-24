"""Seed 모델의 형식 검증 이후 수행하는 KG 참조·온톨로지 규칙 검사."""

from dataclasses import dataclass

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.ontology.seed import (
    SEED_ONTOLOGY_VERSION,
    SEED_PROPERTY_TYPES,
    SEED_PROPERTY_VALUES,
    SEED_RELATION_PAIRS,
)


@dataclass(frozen=True)
class SeedValidationIssue:
    code: str
    path: str
    message: str


def validate_seed_graph(seed: SeedKnowledgeGraph) -> list[SeedValidationIssue]:
    """오류가 없으면 빈 목록을 반환한다. 입력 수정·DB 조회·사실의 진위 판단은 하지 않는다.

    Pydantic 모델로 타입 검증된 Seed를 받는다. 의미상 동일한 Entity의 병합이나
    기존 DB와의 중복 처리는 이 함수의 범위가 아니다.
    """
    issues: list[SeedValidationIssue] = []

    def report(code: str, path: str, message: str) -> None:
        issues.append(SeedValidationIssue(code=code, path=path, message=message))

    if seed.ontology_schema_version != SEED_ONTOLOGY_VERSION:
        report(
            "UNSUPPORTED_ONTOLOGY_VERSION",
            "ontology_schema_version",
            f"지원하는 Seed 온톨로지 버전은 {SEED_ONTOLOGY_VERSION}입니다.",
        )
        return issues  # 알 수 없는 버전을 현재 버전 규칙으로 판단하지 않는다.

    for collection_name in ("entities", "facts", "relations"):
        seen = set()
        for index, item in enumerate(getattr(seed, collection_name)):
            if item.id in seen:
                report(
                    "DUPLICATE_ID",
                    f"{collection_name}[{index}].id",
                    "같은 종류의 항목에서 ID가 중복됩니다.",
                )
            seen.add(item.id)

    person_count = sum(entity.class_type == "Person" for entity in seed.entities)
    if person_count != 1:
        report("INVALID_PERSON_COUNT", "entities", "사용자 본인 Person은 정확히 하나여야 합니다.")

    entities = {}
    for index, entity in enumerate(seed.entities):
        entities.setdefault(entity.id, entity)
        if entity.graph_id != seed.id:
            report("GRAPH_MISMATCH", f"entities[{index}].graph_id", "Entity가 다른 KG에 속합니다.")

    for index, fact in enumerate(seed.facts):
        path = f"facts[{index}]"
        entity = entities.get(fact.entity_id)
        if entity is None:
            report("MISSING_ENTITY", f"{path}.entity_id", "Fact의 대상 Entity가 없습니다.")
            continue

        allowed_types = SEED_PROPERTY_TYPES[entity.class_type].get(fact.predicate)
        if allowed_types is None:
            report(
                "INVALID_PROPERTY",
                f"{path}.predicate",
                f"{entity.class_type}에 허용되지 않은 속성입니다.",
            )
            continue
        if fact.value_type not in allowed_types:
            report(
                "INVALID_VALUE_TYPE",
                f"{path}.value_type",
                f"허용하는 값 타입: {', '.join(allowed_types)}",
            )
        if not fact.value.strip():
            report("EMPTY_FACT_VALUE", f"{path}.value", "비어 있는 값은 Fact로 저장하지 않습니다.")
        allowed_values = SEED_PROPERTY_VALUES.get((entity.class_type, fact.predicate))
        if allowed_values is not None and fact.value not in allowed_values:
            report(
                "INVALID_PROPERTY_VALUE", f"{path}.value", "속성에 정의된 값 범위를 벗어났습니다."
            )

    for index, relation in enumerate(seed.relations):
        path = f"relations[{index}]"
        if relation.graph_id != seed.id:
            report("GRAPH_MISMATCH", f"{path}.graph_id", "Relation이 다른 KG에 속합니다.")
        subject = entities.get(relation.subject_entity_id)
        target = entities.get(relation.object_entity_id)
        if subject is None:
            report("MISSING_ENTITY", f"{path}.subject_entity_id", "출발 Entity가 없습니다.")
        if target is None:
            report("MISSING_ENTITY", f"{path}.object_entity_id", "도착 Entity가 없습니다.")
        if subject is None or target is None:
            continue
        pair = (subject.class_type, target.class_type)
        if pair not in SEED_RELATION_PAIRS[relation.predicate]:
            report(
                "INVALID_RELATION_DIRECTION",
                f"{path}.predicate",
                f"{relation.predicate}는 {pair[0]} → {pair[1]} 연결을 허용하지 않습니다.",
            )

    return issues
