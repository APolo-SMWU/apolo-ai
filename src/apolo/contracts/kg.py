"""프로필 Seed를 표현하는 데이터 모델. DB 테이블이나 저장 규칙은 정의하지 않는다."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from apolo.ontology.seed import SeedClassType, SeedRelationType, SeedValueType


class SeedEntity(BaseModel):
    """대상의 식별 정보. 이름·전공 등의 속성은 SeedFact로 분리한다."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    class_type: SeedClassType
    status: Literal["active"] = "active"
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SeedFact(BaseModel):
    """프로필에서 직접 확인된 속성값. 현재 Seed 값은 문자열 또는 URI 문자열이다."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    entity_id: UUID
    predicate: str = Field(min_length=1)
    value: str
    value_type: SeedValueType
    origin: Literal["user"] = "user"
    confidence: None = None
    locked: bool = False
    status: Literal["active"] = "active"
    updated_at: AwareDatetime


class SeedRelation(BaseModel):
    """사용자 입력으로 확인된 Entity 간 연결."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    subject_entity_id: UUID
    predicate: SeedRelationType
    object_entity_id: UUID
    origin: Literal["user"] = "user"
    confidence: None = None
    locked: bool = False
    status: Literal["active"] = "active"
    updated_at: AwareDatetime


class SeedKnowledgeGraph(BaseModel):
    """사용자 KG 메타데이터와 Seed 묶음. 사용자 전체 KG나 DB 저장 완료를 의미하지 않는다.

    ID 발급·재사용과 버전 결정은 호출부 책임이다.
    참조 존재 여부와 Ontology의 속성·관계 규칙은 후속 검증 단계에서 확인한다.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    user_id: int = Field(gt=0)
    ontology_schema_version: str = Field(min_length=1)
    version: int = Field(ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    entities: list[SeedEntity] = Field(default_factory=list)
    facts: list[SeedFact] = Field(default_factory=list)
    relations: list[SeedRelation] = Field(default_factory=list)
