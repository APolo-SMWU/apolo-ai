"""외부 소스 식별 정보·변경 감지 상태·근거. 수집·추출·DB 저장은 별도 책임이다."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class SourceDocument(BaseModel):
    """사용자 KG에 속한 원본 소스. 같은 소스는 안정적인 source_key로 식별한다.

    MVP는 GitHub Profile/Repository와 Public Notion Page를 지원한다.
    URL 정규화와 수집 가능한 주소인지 확인하는 일은 Collector에서 처리한다.
    processed_at은 수집 시각이 아니라 분석 완료 시각이며, 분석 전에는 None이다.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    source_type: Literal["github", "notion"]
    source_key: str = Field(min_length=1, pattern=r"\S")
    source_url: str = Field(min_length=1, pattern=r"\S")
    processed_at: AwareDatetime | None = None


class SourceSnapshot(BaseModel):
    """소스의 변경 감지 상태. 본문이나 추출된 KG 사실을 저장하는 모델은 아니다.

    graph_id와 source_key로 SourceDocument에 대응한다. 참조와 유일성은 저장 시 확인한다.
    성공 시 content_hash는 필수다. 실패 시 이전 성공의 hash/version을 유지할 수 있으나,
    최초 수집부터 실패했다면 None이다. 실패 상태만으로 소스 삭제를 판단하지 않는다.
    해시 알고리즘과 콘텐츠 정규화 방식은 Collector 구현에서 정의한다.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    graph_id: UUID
    source_key: str = Field(min_length=1, pattern=r"\S")
    content_hash: str | None = Field(default=None, min_length=1, pattern=r"\S")
    source_version: str | None = Field(default=None, min_length=1, pattern=r"\S")
    last_fetched_at: AwareDatetime
    fetch_status: Literal["success", "inaccessible", "error"]

    @model_validator(mode="after")
    def require_hash_on_success(self) -> Self:
        if self.fetch_status == "success" and self.content_hash is None:
            raise ValueError("수집 성공 상태에는 content_hash가 필요합니다.")
        return self


class Evidence(BaseModel):
    """Fact 또는 Relation을 뒷받침하는 원문 조각과 그 위치.

    snippet은 생성한 요약이 아닌 원문이며 공백·줄바꿈을 그대로 보존한다.
    locator는 README 섹션, Notion block ID 등 소스 내 위치다.
    문서 존재 여부와 원문 일치는 별도 검증 책임이다.
    Fact/Relation과의 다대다 연결은 별도 연결 테이블에서 관리한다.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    source_document_id: UUID
    snippet: str = Field(min_length=1, pattern=r"\S")
    locator: str = Field(min_length=1, pattern=r"\S")
    created_at: AwareDatetime
