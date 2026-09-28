"""Graph A LLM 추출 후보. LLM은 후보만 제안하고 저장 여부는 규칙이 결정한다.

origin·provenance·locked·status와 DB ID는 코드가 정한다.
predicate·참조의 온톨로지 적합성은 별도 검증에서 항목별로 판단한다.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from apolo.ontology.personal import RelationType

# 사용자 본인 Person을 가리키는 예약 참조. Person은 추출로 만들지 않는다.
SELF_REF: Final = "self"

ExtractableClass = Literal[
    "Work", "Skill", "Experience", "Activity", "Education", "Credential", "Organization"
]

# MVP 추출 범위. 온톨로지에 있어도 여기 없는 속성·Relation은 제외한다.
EXTRACTABLE_PROPERTIES: Final[dict[ExtractableClass, frozenset[str]]] = {
    "Work": frozenset({"title", "kind", "role", "start", "end", "url"}),
    "Skill": frozenset({"name", "category"}),
    "Experience": frozenset({"role", "department", "kind", "start", "end", "isCurrent"}),
    "Activity": frozenset({"name", "role", "kind", "start", "end", "isCurrent"}),
    "Education": frozenset({"major", "degree", "start", "end", "isCurrent"}),
    "Credential": frozenset({"title", "kind", "issuerName", "date", "grade"}),
    "Organization": frozenset({"name", "type", "homepage"}),
}
EXTRACTABLE_RELATIONS: Final[frozenset[RelationType]] = frozenset(
    {
        "hasEducation",
        "hasExperience",
        "participatedIn",
        "holds",
        "atOrganization",
        "usesSkill",
        "partOf",
    }
)


class _Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EntityCandidate(_Candidate):
    """이번 추출 결과 안에서만 쓰는 임시 참조(e1, e2 …)로 식별한다."""

    ref: str = Field(pattern=r"^e[0-9]+$")
    class_type: ExtractableClass


class FactCandidate(_Candidate):
    """evidence는 원문 그대로의 조각이다. 원문 위치는 코드가 찾는다."""

    entity_ref: str = Field(pattern=r"^(self|e[0-9]+)$")
    predicate: str = Field(min_length=1, pattern=r"\S")
    value: str | bool
    evidence: str = Field(min_length=1, pattern=r"\S")
    confidence: float = Field(ge=0, le=1)


class RelationCandidate(_Candidate):
    subject_ref: str = Field(pattern=r"^(self|e[0-9]+)$")
    predicate: str = Field(min_length=1, pattern=r"\S")
    object_ref: str = Field(pattern=r"^(self|e[0-9]+)$")
    evidence: str = Field(min_length=1, pattern=r"\S")
    confidence: float = Field(ge=0, le=1)


class ExtractionResult(_Candidate):
    """Source 하나에서 추출한 후보 묶음."""

    entities: list[EntityCandidate] = Field(default_factory=list)
    facts: list[FactCandidate] = Field(default_factory=list)
    relations: list[RelationCandidate] = Field(default_factory=list)


class StructuredExtractionResult(_Candidate):
    """Structured Outputs 전용 응답 형식. 세 목록은 항상 명시한다."""

    entities: list[EntityCandidate]
    facts: list[FactCandidate]
    relations: list[RelationCandidate]

    def to_extraction_result(self) -> ExtractionResult:
        """저장·검증 단계가 쓰는 기본 후보 모델로 변환"""
        return ExtractionResult.model_validate(self.model_dump())
