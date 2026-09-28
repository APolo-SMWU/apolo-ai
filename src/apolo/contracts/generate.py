"""Backend ↔ AI /generate 요청·응답 계약. 생성 workflow와 API 실행은 별도 구현한다."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_serializer,
)

from apolo.contracts.profile import SeedProfileInput

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]
SkillText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
LinkLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


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
    label: LinkLabel
    href: str

    @field_validator("href")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        """프로젝트 링크를 HTTP(S) URL로 제한한다."""
        from urllib.parse import urlparse

        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("href must be an http(s) URL")
        return value.strip()


class AboutBlock(_ResponseModel):
    """여러 Fact를 종합한 문장이므로 entityId를 붙이지 않는다."""

    type: Literal["about"] = "about"
    visible: bool = True
    body: LongText


TimelineItemKind = Literal[
    "fulltime", "intern", "research", "exchange", "volunteer", "club", "program", "talk"
]


# 빈 문자열은 날짜 미입력이다. 실제 값은 Backend의 날짜 형식과 맞춘다.
TimelineDate = Annotated[str, Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?)?$")]
TimelineEndDate = Annotated[
    str, Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?|Present)?$")
]

EducationDate = Annotated[
    str | None,
    Field(pattern=r"^[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?$")
]
EducationEndDate = Annotated[
    str | None,
    Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?|Present)$")
]


class EducationItem(_ResponseModel):
    """Education 전용 항목. description·kind는 Education 계약에서 금지한다."""

    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    start_date: EducationDate = Field(alias="startDate")
    end_date: EducationEndDate = Field(alias="endDate")
    organization: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    role: ShortText | None = None

    @model_serializer(mode="wrap")
    def serialize_with_required_dates(self, nxt):
        """exclude_none이어도 계약상 필수 nullable 날짜 키는 유지한다."""

        value = nxt(self)
        value["startDate"] = self.start_date
        value["endDate"] = self.end_date
        return value


class EducationBlock(_ResponseModel):
    type: Literal["education"] = "education"
    visible: bool = True
    items: list[EducationItem]


ExperienceDate = Annotated[
    str | None,
    Field(pattern=r"^[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?$")
]
ExperienceEndDate = Annotated[
    str | None,
    Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?|Present)$")
]
ExperienceItemKind = Literal["fulltime", "contract", "intern", "research"]


class ExperienceItem(_ResponseModel):
    """Experience 전용 항목. 근거가 없는 기관명은 null로 둔다."""

    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    start_date: ExperienceDate = Field(alias="startDate")
    end_date: ExperienceEndDate = Field(alias="endDate")
    organization: ShortText | None = None
    role: ShortText | None = None
    description: LongText | None = None
    kind: ExperienceItemKind | None = None

    @model_serializer(mode="wrap")
    def serialize_with_required_dates(self, nxt):
        """exclude_none이어도 계약상 필수 nullable 날짜 키는 유지한다."""

        value = nxt(self)
        value["startDate"] = self.start_date
        value["endDate"] = self.end_date
        return value


class ExperienceBlock(_ResponseModel):
    type: Literal["experience"] = "experience"
    visible: bool = True
    items: list[ExperienceItem]


ActivityDate = Annotated[
    str | None,
    Field(pattern=r"^[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?$"),
]
ActivityEndDate = Annotated[
    str | None,
    Field(pattern=r"^(?:[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?|Present)$"),
]
ActivityItemKind = Literal["club", "volunteer", "program", "talk"]


class ActivityItem(_ResponseModel):
    """Activities 전용 항목. 활동명 또는 기관명이 표시용 organization이 된다."""

    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    start_date: ActivityDate = Field(alias="startDate")
    end_date: ActivityEndDate = Field(alias="endDate")
    organization: ShortText
    role: ShortText | None = None
    description: LongText | None = None
    kind: ActivityItemKind | None = None

    @model_serializer(mode="wrap")
    def serialize_with_required_dates(self, nxt):
        """exclude_none이어도 계약상 필수 nullable 날짜 키는 유지한다."""

        value = nxt(self)
        value["startDate"] = self.start_date
        value["endDate"] = self.end_date
        return value


class ActivitiesBlock(_ResponseModel):
    type: Literal["activities"] = "activities"
    visible: bool = True
    items: list[ActivityItem]


class TimelineItem(_ResponseModel):
    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    start_date: TimelineDate = Field(alias="startDate")
    end_date: TimelineEndDate | None = Field(default=None, alias="endDate")
    organization: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
    role: ShortText | None = None
    description: LongText | None = None
    kind: TimelineItemKind | None = None


class TimelineBlock(_ResponseModel):
    type: Literal["awards", "certification"]
    visible: bool = True
    items: list[TimelineItem]


class WorkItem(_ResponseModel):
    """links에는 Source에서 확인된 URL만 넣는다. AI가 URL을 만들어내지 않는다."""

    entity_id: str = Field(min_length=1, pattern=r"\S", alias="entityId")
    kind: Literal["project", "publication", "opensource"]
    title: ShortText
    role: ShortText | None = None
    skills: list[SkillText] | None = None
    description: LongText
    image_url: str | None = Field(default=None, alias="imageUrl")
    links: list[ProjectLink] = Field(default_factory=list)

    @field_validator("image_url")
    @classmethod
    def require_http_image_url(cls, value: str | None) -> str | None:
        """이미지 주소가 있으면 HTTP(S) URL로 제한한다."""
        if value is None:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("imageUrl must be an http(s) URL")
        return value.strip()


class WorksBlock(_ResponseModel):
    type: Literal["works"] = "works"
    visible: bool = True
    items: list[WorkItem]


class SkillCategory(_ResponseModel):
    category: SkillText
    items: list[SkillText]


class SkillsBlock(_ResponseModel):
    type: Literal["skills"] = "skills"
    visible: bool = True
    categories: list[SkillCategory]


ContentBlock = Annotated[
    AboutBlock
    | EducationBlock
    | ExperienceBlock
    | ActivitiesBlock
    | TimelineBlock
    | WorksBlock
    | SkillsBlock,
    Field(discriminator="type"),
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
