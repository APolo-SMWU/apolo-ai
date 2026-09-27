"""Backend ↔ AI /update-content 요청 계약."""

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UpdateContentRequest(BaseModel):
    """기존 KG의 Source를 다시 확인하고 요구사항을 재사용하기 위한 Backend 입력."""

    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: int = Field(gt=0, alias="userId")
    source_links: list[str] = Field(default_factory=list, alias="sourceLinks")
    requirements: str = Field(default="", max_length=2_000)

    @field_validator("source_links")
    @classmethod
    def require_http_urls(cls, values: list[str]) -> list[str]:
        """Source 링크를 HTTP(S) URL로 제한하고 앞뒤 공백을 정리"""
        normalized: list[str] = []
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("sourceLinks must contain only http(s) URLs")
            normalized.append(value.strip())
        return normalized
