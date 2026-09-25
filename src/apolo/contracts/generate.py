"""Backend ↔ AI /generate 요청·응답 계약. 생성 workflow와 API 실행은 별도 구현한다."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apolo.contracts.profile import SeedProfileInput


class GenerateRequest(SeedProfileInput):
    """Backend 입력을 받는다. 요구사항 생략은 빈 문자열, 첨부는 MVP에서 빈 목록만 허용."""

    title: str
    external_links: list[str] = Field(alias="externalLinks")
    requirements: str = ""
    attachments: list[Any] = Field(default_factory=list, max_length=0)


class _ResponseModel(BaseModel):
    """반환 시 model_dump(mode="json", by_alias=True, exclude_none=True)를 사용한다.

    선택 필드의 None은 생략하며 날짜 미입력 값인 빈 문자열은 유지한다.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class ProjectLink(_ResponseModel):
    label: str
    href: str


class AboutBlock(_ResponseModel):
    """여러 Fact를 종합한 문장이므로 entityId를 붙이지 않는다."""

    type: Literal["about"] = "about"
    visible: bool = True
    body: str


TimelineItemKind = Literal[
    "fulltime", "intern", "research", "exchange", "volunteer", "club", "program", "talk"
]


# 빈 문자열은 날짜 미입력이다. 실제 값은 Backend의 날짜 형식과 맞춘다.
TimelineDate = Annotated[str, Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?)?$")]
TimelineEndDate = Annotated[
    str, Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?|Present)?$")
]


class TimelineItem(_ResponseModel):
    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    start_date: TimelineDate = Field(alias="startDate")
    end_date: TimelineEndDate | None = Field(default=None, alias="endDate")
    organization: str
    role: str | None = None
    description: str | None = None
    kind: TimelineItemKind | None = None


class TimelineBlock(_ResponseModel):
    type: Literal["education", "experience", "activities", "awards", "certification"]
    visible: bool = True
    items: list[TimelineItem]


class WorkItem(_ResponseModel):
    """links에는 Source에서 확인된 URL만 넣는다. AI가 URL을 만들어내지 않는다."""

    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    kind: Literal["project", "publication", "opensource"]
    title: str
    role: str | None = None
    skills: list[str] | None = None
    description: str
    image_url: str | None = Field(default=None, alias="imageUrl")
    links: list[ProjectLink] = Field(default_factory=list)


class WorksBlock(_ResponseModel):
    type: Literal["works"] = "works"
    visible: bool = True
    items: list[WorkItem]


class SkillCategory(_ResponseModel):
    category: str = Field(min_length=1, pattern=r"\S")
    items: list[str]


class SkillsBlock(_ResponseModel):
    type: Literal["skills"] = "skills"
    visible: bool = True
    categories: list[SkillCategory]


ContentBlock = Annotated[
    AboutBlock | TimelineBlock | WorksBlock | SkillsBlock, Field(discriminator="type")
]


class GenerateMeta(_ResponseModel):
    ontology_schema_version: str = Field(alias="ontologySchemaVersion")
    knowledge_graph_version: int = Field(ge=0, alias="knowledgeGraphVersion")


class GenerateWarning(_ResponseModel):
    """요청 전체를 실패시키지 않는 부분 오류."""

    source: str | None = None
    code: str
    message: str


class GenerateResponse(_ResponseModel):
    """card·profile은 Backend가 구성한다. AI는 콘텐츠·메타데이터·경고만 반환한다."""

    blocks: list[ContentBlock] = Field(default_factory=list)
    meta: GenerateMeta
    warnings: list[GenerateWarning] = Field(default_factory=list)
