"""Graph B 콘텐츠 출력 계약.

Backend가 저장할 블록 구조를 그대로 사용하되, Graph B는 콘텐츠 블록만 반환한다.
카드·프로필·메타데이터·경고는 Backend와 API 계층의 책임이다.
"""

from pydantic import BaseModel, ConfigDict

from apolo.contracts.generate import ContentBlock


class GraphBOutput(BaseModel):
    """Graph B가 생성한 콘텐츠 블록 묶음"""

    model_config = ConfigDict(extra="forbid", strict=True)

    blocks: list[ContentBlock]
