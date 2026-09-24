"""Backend 프로필에서 직접 확인된 사실만 초기 KG로 변환한다."""

from datetime import datetime
from uuid import UUID, uuid4

from apolo.contracts.kg import SeedEntity, SeedFact, SeedKnowledgeGraph, SeedRelation
from apolo.contracts.profile import SeedProfileInput
from apolo.ontology.seed import (
    SEED_ONTOLOGY_VERSION,
    SeedClassType,
    SeedRelationType,
    SeedValueType,
)


def _has_value(value: str | None) -> bool:
    """빈 사실을 만들지 않는다. 값이 있는 문자열 자체는 변경하지 않는다."""
    return value is not None and bool(value.strip())


def build_initial_profile_seed(
    source: SeedProfileInput, *, graph_id: UUID, now: datetime
) -> SeedKnowledgeGraph:
    """LLM·DB 호출 없이 최초 프로필 Seed를 만든다.

    graph_id와 timezone이 있는 now는 호출부에서 전달한다.
    version=0은 저장 전 상태이며, 저장 후 KG 버전을 결정하지 않는다.
    각 실행은 새 항목 UUID를 발급한다. 기존 KG 갱신·ID 재사용·중복 처리는
    저장 단계에서 별도로 구현해야 하며 이 결과로 기존 KG를 덮어쓰면 안 된다.
    """
    seed = SeedKnowledgeGraph(
        id=graph_id,
        user_id=source.user_id,
        ontology_schema_version=SEED_ONTOLOGY_VERSION,
        version=0,
        created_at=now,
        updated_at=now,
    )
    profile = source.my_page_profile

    def add_entity(class_type: SeedClassType) -> SeedEntity:
        entity = SeedEntity(
            id=uuid4(),
            graph_id=graph_id,
            class_type=class_type,
            created_at=now,
            updated_at=now,
        )
        seed.entities.append(entity)
        return entity

    def add_fact(
        entity: SeedEntity,
        predicate: str,
        value: str | None,
        value_type: SeedValueType = "string",
    ) -> None:
        if value is None or not _has_value(value):
            return
        seed.facts.append(
            SeedFact(
                id=uuid4(),
                entity_id=entity.id,
                predicate=predicate,
                value=value,
                value_type=value_type,
                origin="user",
                updated_at=now,
            )
        )

    def add_relation(
        subject: SeedEntity,
        predicate: SeedRelationType,
        target: SeedEntity,
    ) -> None:
        seed.relations.append(
            SeedRelation(
                id=uuid4(),
                graph_id=graph_id,
                subject_entity_id=subject.id,
                predicate=predicate,
                object_entity_id=target.id,
                origin="user",
                updated_at=now,
            )
        )

    person = add_entity("Person")
    roles = {"student": "Student", "professor": "Professor", "professional": "Professional"}
    add_fact(person, "name", profile.name)
    add_fact(person, "role", roles[source.user_type])

    # 공통 Class를 사용하되, 유형에 따라 소속의 의미와 연결만 다르게 표현한다.
    affiliation: SeedEntity | None = None
    organization_name: str | None = None
    organization_type = "university"
    if source.user_type == "student":
        if _has_value(profile.university) or _has_value(profile.major):
            affiliation = add_entity("Education")
            add_fact(affiliation, "major", profile.major)
            add_relation(person, "hasEducation", affiliation)
        organization_name = profile.university
    elif source.user_type == "professor":
        if _has_value(profile.university) or _has_value(profile.department):
            affiliation = add_entity("Experience")
            add_fact(affiliation, "unit", profile.department)
            add_relation(person, "hasExperience", affiliation)
        organization_name = profile.university
    else:
        if _has_value(profile.company) or _has_value(profile.job_title):
            affiliation = add_entity("Experience")
            add_fact(affiliation, "role", profile.job_title)
            add_relation(person, "hasExperience", affiliation)
        organization_name = profile.company
        organization_type = "company"

    if affiliation is not None and _has_value(organization_name):
        organization = add_entity("Organization")
        add_fact(organization, "name", organization_name)
        add_fact(organization, "type", organization_type)
        add_relation(affiliation, "atOrganization", organization)

    def add_channel(kind: str, value: str | None, scope: str | None = None) -> None:
        if not _has_value(value):
            return
        channel = add_entity("Channel")
        add_fact(channel, "kind", kind)
        add_fact(channel, "value", value, "uri" if kind == "github" else "string")
        add_fact(channel, "scope", scope)
        add_relation(person, "hasChannel", channel)

    add_channel("email", profile.email)
    add_channel("phone", profile.phone, "personal")
    add_channel("github", profile.github)
    if source.user_type in ("professor", "professional"):
        add_channel("phone", profile.tel, "work")

    return seed
