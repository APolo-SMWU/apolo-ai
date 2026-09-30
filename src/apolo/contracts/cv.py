"""CV 생성 LLM 출력 계약.

섹션·제목·날짜는 코드가 KG에서 정하므로 LLM은 어떤 후보를 고를지와 불릿만 반환한다.
헤더(이름·연락처)는 Backend가 구성한다.
"""

from copy import deepcopy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from apolo.contracts.content import _make_object_properties_required

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
EntityId = Annotated[str, Field(min_length=1, pattern=r"\S")]


class _CvModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class CvSelection(_CvModel):
    """CV에 넣을 항목 하나. 같은 항목을 가리키는 후보는 entityIds로 묶고 첫 id가 대표다"""

    entity_ids: list[EntityId] = Field(alias="entityIds", min_length=1)
    bullets: list[Line]


class CvOutput(_CvModel):
    """중요도가 높은 항목부터 나열한다"""

    items: list[CvSelection]


def cv_output_json_schema() -> dict[str, Any]:
    schema = deepcopy(CvOutput.model_json_schema(by_alias=True))
    _make_object_properties_required(schema)
    return schema


class CvLinkOut(_CvModel):
    label: str
    href: str


class CvEntryOut(_CvModel):
    title: str
    date: str | None = None
    subtitle: str | None = None
    location: str | None = None
    link: CvLinkOut | None = None
    bullets: list[str] = Field(default_factory=list)


class CvSectionOut(_CvModel):
    title: str
    layout: Literal["entries", "bullets"]
    entries: list[CvEntryOut]
