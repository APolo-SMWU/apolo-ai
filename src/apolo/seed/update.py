"""프로필만으로 구성된 Seed KG의 갱신 결과를 만든다. DB에는 쓰지 않는다."""

from datetime import datetime
from uuid import UUID

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.contracts.profile import SeedProfileInput
from apolo.seed.comparison import same_profile_seed_content
from apolo.seed.profile import build_initial_profile_seed
from apolo.seed.validation import validate_seed_graph


def build_updated_profile_seed(
    existing: SeedKnowledgeGraph, source: SeedProfileInput, *, now: datetime
) -> SeedKnowledgeGraph:
    """최신 전체 프로필로 현재 Seed를 갱신한다. 부분 PATCH 입력을 받는 함수가 아니다.

    제거된 값은 결과에서 제외하며 과거 경력/학력으로 추측해 보관하지 않는다.
    사용자 직접 수정이므로 locked 값도 수정할 수 있지만 잠금 표시는 유지한다.
    외부 추출/자유문장 사실이 섞이기 전의 프로필 전용 KG에만 사용해야 한다.
    입력 객체는 변경하지 않으며, 변경이 없으면 기존 KG의 깊은 복사본을 반환한다.
    """
    if source.user_id != existing.user_id:
        raise ValueError("다른 사용자의 프로필로 KG를 갱신할 수 없습니다.")
    if validate_seed_graph(existing) or not same_profile_seed_content(existing, existing):
        raise ValueError("유효한 프로필 Seed 트리가 필요합니다.")
    candidate = build_initial_profile_seed(source, graph_id=existing.id, now=now)
    old_keys = _entity_keys(existing)
    new_keys = _entity_keys(candidate)
    if same_profile_seed_content(existing, candidate):
        return existing.model_copy(deep=True)
    if now < existing.updated_at:
        raise ValueError("갱신 시각이 기존 KG의 수정 시각보다 이전입니다.")

    old_entities = {old_keys[e.id]: e for e in existing.entities}
    remap: dict[UUID, UUID] = {}
    for entity in candidate.entities:
        previous = old_entities.get(new_keys[entity.id])
        original_id = entity.id
        if previous is not None:
            entity.id = previous.id
            entity.created_at = previous.created_at
            entity.updated_at = previous.updated_at
        remap[original_id] = entity.id

    old_facts = {(f.entity_id, f.predicate): f for f in existing.facts}
    for fact in candidate.facts:
        fact.entity_id = remap[fact.entity_id]
        previous = old_facts.get((fact.entity_id, fact.predicate))
        if previous is not None:
            fact.id = previous.id
            fact.locked = previous.locked
            if (fact.value, fact.value_type) == (previous.value, previous.value_type):
                fact.updated_at = previous.updated_at

    old_relations = {
        (r.subject_entity_id, r.predicate, r.object_entity_id): r for r in existing.relations
    }
    for relation in candidate.relations:
        relation.subject_entity_id = remap[relation.subject_entity_id]
        relation.object_entity_id = remap[relation.object_entity_id]
        previous = old_relations.get(
            (relation.subject_entity_id, relation.predicate, relation.object_entity_id)
        )
        if previous is not None:
            relation.id = previous.id
            relation.locked = previous.locked
            relation.updated_at = previous.updated_at

    for entity in candidate.entities:
        if _entity_content(existing, entity.id) != _entity_content(candidate, entity.id):
            entity.updated_at = now
    candidate.created_at = existing.created_at
    candidate.version = existing.version + 1
    if validate_seed_graph(candidate):
        raise ValueError("갱신 결과가 KG 규칙을 만족하지 않습니다.")
    return candidate


def _entity_keys(seed: SeedKnowledgeGraph) -> dict[UUID, tuple]:
    """이름이 바뀌는 Person, 값이 바뀌는 연락 수단은 같은 입력 항목으로 식별한다."""
    properties: dict[UUID, dict[str, str]] = {e.id: {} for e in seed.entities}
    for fact in seed.facts:
        if fact.predicate in properties[fact.entity_id]:
            raise ValueError("프로필 Seed에 동일 속성이 여러 개 있습니다.")
        properties[fact.entity_id][fact.predicate] = fact.value
    organizations = {
        e.id: (properties[e.id].get("type"), properties[e.id].get("name"))
        for e in seed.entities
        if e.class_type == "Organization"
    }
    affiliations = {
        r.subject_entity_id: organizations[r.object_entity_id]
        for r in seed.relations
        if r.predicate == "atOrganization"
    }
    person = next(e for e in seed.entities if e.class_type == "Person")
    role = properties[person.id].get("role")
    keys = {}
    for entity in seed.entities:
        values = properties[entity.id]
        key: tuple = (entity.class_type,)
        if entity.class_type == "Channel":
            key += (values.get("kind"), values.get("scope"))
        elif entity.class_type == "Organization":
            key += organizations[entity.id]
        elif entity.class_type in {"Education", "Experience"}:
            key += (role, affiliations.get(entity.id))
        if key in keys.values():
            raise ValueError("프로필 입력 항목과 Entity를 일대일로 대응할 수 없습니다.")
        keys[entity.id] = key
    return keys


def _entity_content(seed: SeedKnowledgeGraph, entity_id: UUID) -> tuple:
    facts = sorted(
        (f.predicate, f.value, f.value_type) for f in seed.facts if f.entity_id == entity_id
    )
    outgoing = sorted(
        (r.predicate, r.object_entity_id)
        for r in seed.relations
        if r.subject_entity_id == entity_id
    )
    return facts, outgoing
