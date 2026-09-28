"""Graph B 검증 실패를 전달하기 위한 내부 공통 타입"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentValidationIssue:

    path: str
    code: str
    message: str
