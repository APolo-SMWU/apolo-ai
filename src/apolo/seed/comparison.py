"""최초 프로필 Seed의 내용 비교"""

from uuid import UUID

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.seed.validation import validate_seed_graph


def same_profile_seed_content(left: SeedKnowledgeGraph, right: SeedKnowledgeGraph) -> bool:
    """ID·시간·버전·locked를 제외하고 사실과 관계를 비교한다.

    기존 locked 값은 재사용 시 그대로 보존한다. 문자열을 추가 정규화하지 않는다.
    프로필 변환기가 만드는 Person 루트 트리만 지원하며, 공유/분리된 Entity가
    있는 KG나 검증되지 않는 KG는 동일하다고 판단하지 않는다.
    """
    if (
        left.user_id != right.user_id
        or left.ontology_schema_version != right.ontology_schema_version
    ):
        return False
    if validate_seed_graph(left) or validate_seed_graph(right):
        return False
    left_content = _profile_tree(left)
    return left_content is not None and left_content == _profile_tree(right)


def _profile_tree(seed: SeedKnowledgeGraph) -> tuple | None:
    entities = {entity.id: entity for entity in seed.entities}
    facts: dict[UUID, list[tuple]] = {entity_id: [] for entity_id in entities}
    children: dict[UUID, list[tuple]] = {entity_id: [] for entity_id in entities}
    for fact in seed.facts:
        facts[fact.entity_id].append((fact.predicate, fact.value, fact.value_type))
    for relation in seed.relations:
        children[relation.subject_entity_id].append((relation.predicate, relation.object_entity_id))

    visited: set[UUID] = set()

    def visit(entity_id: UUID) -> tuple:
        if entity_id in visited:
            raise ValueError("프로필 Seed 트리가 아닌 공유/중복 연결입니다.")
        visited.add(entity_id)
        return (
            entities[entity_id].class_type,
            tuple(sorted(facts[entity_id])),
            tuple(sorted((predicate, visit(target)) for predicate, target in children[entity_id])),
        )

    person = next(entity for entity in seed.entities if entity.class_type == "Person")
    try:
        content = visit(person.id)
    except ValueError:
        return None
    return content if len(visited) == len(entities) else None
