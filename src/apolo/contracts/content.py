"""Graph B 콘텐츠 출력 계약.

Backend가 저장할 블록 구조를 그대로 사용하되, Graph B는 콘텐츠 블록만 반환한다.
카드·프로필·메타데이터·경고는 Backend와 API 계층의 책임이다.
"""

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict

from apolo.contracts.generate import ContentBlock


class GraphBOutput(BaseModel):
    """Graph B가 생성한 콘텐츠 블록 묶음"""

    model_config = ConfigDict(extra="forbid", strict=True)

    blocks: list[ContentBlock]


def graph_b_output_json_schema() -> dict[str, Any]:
    """OpenAI Strict Structured Outputs에 맞춘 Graph B JSON Schema"""
    schema = deepcopy(GraphBOutput.model_json_schema())
    _make_object_properties_required(schema)
    return schema


def _make_object_properties_required(value: Any) -> None:
    """스키마의 모든 object 속성을 required로 정규화"""
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            value["required"] = list(properties)
        if "oneOf" in value:
            value["anyOf"] = value.pop("oneOf")
        value.pop("discriminator", None)
        value.pop("default", None)
        for child in value.values():
            _make_object_properties_required(child)
    elif isinstance(value, list):
        for child in value:
            _make_object_properties_required(child)
