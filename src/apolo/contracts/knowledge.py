"""Graph B가 읽는 현재 유효한 Personal Knowledge Graph 모델.

프로필 Seed 전용 모델과 달리 외부 추출 Fact·Relation을 함께 표현한다.
DB 조회와 유효성 판단은 이 모델을 만드는 호출부의 책임이다.
"""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from apolo.contracts.source import Evidence
from apolo.ontology.personal import ClassType, RelationType, ValueType

KnowledgeOrigin = Literal["user", "extracted"]
KnowledgeProvenance = Literal["profile", "source"]


class ActiveKnowledgeEntity(BaseModel):
    """현재 표시 대상이 될 수 있는 Entity"""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    class_type: ClassType
    status: Literal["active"] = "active"
    created_at: AwareDatetime
    updated_at: AwareDatetime
    evidence: list[Evidence] = Field(default_factory=list)


class ActiveKnowledgeFact(BaseModel):
    """현재 표시 대상이 될 수 있는 Fact와 검증된 근거"""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    entity_id: UUID
    predicate: str = Field(min_length=1)
    value: str | bool
    value_type: ValueType
    origin: KnowledgeOrigin
    provenance: KnowledgeProvenance
    confidence: float | None = Field(default=None, ge=0, le=1)
    locked: bool = False
    status: Literal["active"] = "active"
    evidence: list[Evidence] = Field(default_factory=list)
    updated_at: AwareDatetime


class ActiveKnowledgeRelation(BaseModel):
    """현재 표시 대상이 될 수 있는 Relation과 검증된 근거"""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    subject_entity_id: UUID
    predicate: RelationType
    object_entity_id: UUID
    origin: KnowledgeOrigin
    provenance: KnowledgeProvenance
    confidence: float | None = Field(default=None, ge=0, le=1)
    locked: bool = False
    status: Literal["active"] = "active"
    evidence: list[Evidence] = Field(default_factory=list)
    updated_at: AwareDatetime


class ActiveKnowledgeGraph(BaseModel):
    """Graph B가 콘텐츠 선별에 사용하는 현재 유효한 KG"""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    user_id: int = Field(gt=0)
    ontology_schema_version: str = Field(min_length=1)
    version: int = Field(ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    entities: list[ActiveKnowledgeEntity] = Field(default_factory=list)
    facts: list[ActiveKnowledgeFact] = Field(default_factory=list)
    relations: list[ActiveKnowledgeRelation] = Field(default_factory=list)
