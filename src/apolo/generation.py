"""프로필 Seed의 확정 사실을 학력·경력 블록으로 변환한다. LLM·DB 호출은 없다.

전체 Graph B가 아닌 초기 Seed 전용 경로다.
외부 Source와 requirements는 아직 다루지 않는다.
"""

import re
from uuid import UUID

from apolo.contracts.generate import (
    EducationBlock,
    EducationItem,
    ExperienceBlock,
    ExperienceItem,
    GenerateMeta,
    GenerateResponse,
)
from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.graph_b.service import GraphBGenerationResult
from apolo.seed.validation import validate_seed_graph


def build_profile_only_response(seed: SeedKnowledgeGraph) -> GenerateResponse:
    """Person에 연결된 소속만 출력한다.

    프로필 Seed에는 학력 기간이 없으므로 날짜는 null로 남긴다.
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

    education: list[EducationItem] = []
    experience: list[ExperienceItem] = []
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
        # 교수의 학과(department)는 직함(role)으로 바꾸지 않고
        # 부가정보(description)에 표시한다.
        department = facts.get((entity_id, "department")) if not is_education else None

        if is_education:
            # Education은 학교명이 없으면 유효한 item을 만들 수 없다.
            if not organization.strip():
                continue
            item = EducationItem(
                entity_id=str(entity_id),
                start_date=None,
                end_date=None,
                organization=organization,
                role=role if role and role.strip() else None,
            )
        else:
            item = ExperienceItem(
                entity_id=str(entity_id),
                start_date=None,
                end_date=None,
                organization=organization.strip() or None,
                role=role if role and role.strip() else None,
                description=department if department and department.strip() else None,
            )
        (education if is_education else experience).append(item)

    education.sort(key=_education_sort_key, reverse=True)

    blocks: list[EducationBlock | ExperienceBlock] = []
    if education:
        blocks.append(EducationBlock(type="education", items=education))
    if experience:
        blocks.append(ExperienceBlock(type="experience", items=experience))

    return GenerateResponse(
        blocks=blocks,
        meta=GenerateMeta(
            ontology_schema_version=seed.ontology_schema_version,
            knowledge_graph_version=seed.version,
        ),
    )


def build_graph_b_response(result: GraphBGenerationResult) -> GenerateResponse:
    """검증된 Graph B 블록과 현재 KG 메타데이터를 API 응답으로 변환"""
    if not result.is_valid:
        raise ValueError("검증되지 않은 Graph B 결과는 응답에 사용할 수 없습니다.")
    graph = result.selection.graph
    blocks = [
        block.model_copy(
            update={
                "items": sorted(block.items, key=_education_sort_key, reverse=True)
            }
        )
        if isinstance(block, EducationBlock)
        else block
        for block in result.output.blocks
    ]
    return GenerateResponse(
        blocks=blocks,
        meta=GenerateMeta(
            ontology_schema_version=graph.ontology_schema_version,
            knowledge_graph_version=graph.version,
        ),
    )


def _education_sort_key(item: EducationItem) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Education은 종료일, 시작일이 최신인 순서로 표시한다.

    Present는 가장 최신으로, 확인되지 않은 날짜(null)는 가장 오래된 값으로 취급한다.
    """

    return (_education_date_key(item.end_date), _education_date_key(item.start_date))


def _education_date_key(value: str | None) -> tuple[int, int, int]:
    if value == "Present":
        return (2, 9999, 12)
    if value is None:
        return (0, 0, 0)
    match = re.fullmatch(r"(\d{4})(?:\.(\d{2}))?", value)
    if match is None:
        return (0, 0, 0)
    return (1, int(match.group(1)), int(match.group(2) or 0))
