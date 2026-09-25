"""프로필 Seed의 확정 사실을 학력·경력 블록으로 변환한다. LLM·DB 호출은 없다.

전체 Graph B가 아닌 초기 Seed 전용 경로다.
외부 Source와 requirements는 아직 다루지 않는다.
"""

from uuid import UUID

from apolo.contracts.generate import (
    GenerateMeta,
    GenerateResponse,
    TimelineBlock,
    TimelineItem,
)
from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.seed.validation import validate_seed_graph


def build_profile_only_response(seed: SeedKnowledgeGraph) -> GenerateResponse:
    """Person에 연결된 소속만 출력한다.

    없는 날짜·소속명은 빈 문자열로 남긴다.
    """
    if validate_seed_graph(seed):
        raise ValueError("유효하지 않은 Seed KG입니다.")

    # (entity_id, predicate) -> value 조회표
    facts: dict[tuple[UUID, str], str] = {}
    for fact in seed.facts:
        key = (fact.entity_id, fact.predicate)
        if key in facts and facts[key] != fact.value:
            raise ValueError("같은 속성에 상충하는 Seed Fact가 있습니다.")
        facts[key] = fact.value

    person = next(entity for entity in seed.entities if entity.class_type == "Person")

    education: list[TimelineItem] = []
    experience: list[TimelineItem] = []
    seen: set[UUID] = set()

    for relation in seed.relations:
        # Person의 학력·경력 관계만, 중복 없이 처리한다.
        if relation.subject_entity_id != person.id:
            continue
        if relation.predicate not in ("hasEducation", "hasExperience"):
            continue
        entity_id = relation.object_entity_id
        if entity_id in seen:
            continue
        seen.add(entity_id)

        # 소속 Entity에 연결된 Organization 이름을 찾는다.
        organizations = {
            link.object_entity_id
            for link in seed.relations
            if link.subject_entity_id == entity_id and link.predicate == "atOrganization"
        }
        if len(organizations) > 1:
            raise ValueError("Seed 소속 Entity에 여러 Organization이 연결되어 있습니다.")
        organization_id = next(iter(organizations), None)
        organization = facts.get((organization_id, "name"), "") if organization_id else ""

        is_education = relation.predicate == "hasEducation"
        role = facts.get((entity_id, "major" if is_education else "role"))
        # 교수의 학과(unit)는 직함(role)으로 바꾸지 않고
        # 부가정보(description)에 표시한다.
        unit = facts.get((entity_id, "unit")) if not is_education else None

        item = TimelineItem(
            entity_id=str(entity_id),
            start_date="",
            organization=organization,
            role=role if role and role.strip() else None,
            description=unit if unit and unit.strip() else None,
        )
        (education if is_education else experience).append(item)

    blocks: list[TimelineBlock] = []
    if education:
        blocks.append(TimelineBlock(type="education", items=education))
    if experience:
        blocks.append(TimelineBlock(type="experience", items=experience))

    return GenerateResponse(
        blocks=blocks,
        meta=GenerateMeta(
            ontology_schema_version=seed.ontology_schema_version,
            knowledge_graph_version=seed.version,
        ),
    )
