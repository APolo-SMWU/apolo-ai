"""LangSmith Dataset으로 옮길 AI 평가 케이스와 기대 결과.

이 파일의 입력은 합성 데이터다. 실제 사용자 Source나 개인정보를 포함하지 않는다.
평가 실행기와 LangSmith 업로드는 별도 단계에서 구현한다.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EvaluationTarget = Literal["graph_a", "graph_b"]
EvaluationEnvironment = Literal["local", "database", "llm"]


class EvaluationCase(BaseModel):
    """Graph A 또는 Graph B 한 시나리오의 입력 조건과 기대 결과"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    target: EvaluationTarget
    environment: EvaluationEnvironment
    scenario: str = Field(min_length=1, pattern=r"\S")
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)


EVALUATION_CASES: tuple[EvaluationCase, ...] = (
    EvaluationCase(
        case_id="graph-a-normal-source",
        target="graph_a",
        environment="local",
        scenario="정상 Source에서 근거가 있는 Fact 후보 추출",
        input={
            "sourceType": "github",
            "content": "APolo is a Python project.",
            "evidence": "APolo is a Python project.",
        },
        expected={
            "warningCodes": [],
            "factValues": ["APolo", "Python"],
            "candidateValidated": True,
        },
    ),
    EvaluationCase(
        case_id="graph-a-source-conflict",
        target="graph_a",
        environment="database",
        scenario="변경된 Source가 이전 Fact의 충돌에 막히지 않음",
        input={
            "previousContent": "APolo is a frontend project.",
            "currentContent": "APolo is a backend project.",
        },
        expected={
            "activeFactValues": ["backend"],
            "excludedFactValues": ["frontend"],
            "oldEvidenceIgnored": True,
        },
    ),
    EvaluationCase(
        case_id="graph-a-failed-retry",
        target="graph_a",
        environment="database",
        scenario="분석 실패 후 같은 Content Hash를 다음 요청에서 재분석",
        input={
            "attempts": ["extraction_failed", "success"],
            "contentHash": "synthetic-source-hash",
        },
        expected={
            "firstWarningCodes": ["extraction_failed"],
            "reprocessOnNextRequest": True,
            "processedHashAfterRetry": True,
        },
    ),
    EvaluationCase(
        case_id="graph-b-project-selection",
        target="graph_b",
        environment="local",
        scenario="프로젝트 중심 요구사항에 Work Entity를 선별",
        input={"requirements": "프로젝트 중심 포트폴리오"},
        expected={"selectedBlockTypes": ["works"], "outputValid": True},
    ),
    EvaluationCase(
        case_id="graph-b-partial-generation",
        target="graph_b",
        environment="local",
        scenario="경력 Fact만 있는 KG에서 유효한 부분 콘텐츠 생성",
        input={"requirements": "경력 중심", "availableClasses": ["Experience"]},
        expected={
            "selectedBlockTypes": ["experience"],
            "outputValid": True,
            "emptyBlocks": False,
        },
    ),
    EvaluationCase(
        case_id="graph-b-invalid-entity-reference",
        target="graph_b",
        environment="local",
        scenario="현재 KG에 없는 Entity를 참조한 출력 거부",
        input={"generatedEntityId": "missing-entity"},
        expected={"outputValid": False, "issueCodes": ["ENTITY_NOT_FOUND"]},
    ),
)


def load_evaluation_cases() -> tuple[EvaluationCase, ...]:
    """정의된 합성 평가 케이스를 반환"""

    return EVALUATION_CASES
