"""합성 평가 케이스를 LangSmith Dataset 예시로 변환·업로드."""

import os
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from dotenv import load_dotenv
from langsmith import Client

from evals.cases import EVALUATION_CASES, EvaluationCase

DEFAULT_DATASET_NAME = "apolo-ai-evaluation-v1"


class LangSmithDatasetClient(Protocol):
    """Dataset 업로드에 필요한 LangSmith Client 최소 계약"""

    def has_dataset(self, *, dataset_name: str) -> bool: ...

    def create_dataset(self, dataset_name: str, **kwargs: Any) -> Any: ...

    def create_examples(self, *, dataset_name: str, examples: list[dict[str, Any]]) -> Any: ...


def build_examples(
    cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
) -> tuple[dict[str, Any], ...]:
    """평가 케이스를 중복 가능한 deterministic LangSmith 예시로 변환"""
    return tuple(
        {
            "id": _example_id(dataset_name, case.case_id),
            "inputs": {
                "caseId": case.case_id,
                "target": case.target,
                "environment": case.environment,
                "scenario": case.scenario,
                "payload": case.input,
            },
            "outputs": {"expected": case.expected},
            "metadata": {"apoloEvaluationVersion": "1", "synthetic": True},
        }
        for case in cases
    )


def upload_cases(
    client: LangSmithDatasetClient,
    cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
) -> Any:
    """Dataset을 만들고 평가 예시를 ID 기준으로 upsert"""
    if not client.has_dataset(dataset_name=dataset_name):
        client.create_dataset(
            dataset_name,
            description="APolo AI Graph A·Graph B 합성 평가 Dataset",
            metadata={"apoloEvaluationVersion": "1", "synthetic": True},
        )
    return client.create_examples(
        dataset_name=dataset_name,
        examples=list(build_examples(cases, dataset_name=dataset_name)),
    )


def load_langsmith_client() -> Client:
    """환경 변수에서 LangSmith Client를 생성. API 키가 없으면 실행하지 않음"""
    load_dotenv()
    api_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    if not api_key:
        raise ValueError("LANGSMITH_API_KEY가 설정되지 않았습니다.")
    return Client(api_key=api_key)


def _example_id(dataset_name: str, case_id: str) -> UUID:
    """Dataset·케이스 조합에서 반복 실행 가능한 예시 ID 생성"""
    return uuid5(NAMESPACE_URL, f"{dataset_name}:{case_id}")


def main() -> int:
    """합성 평가 케이스를 LangSmith Dataset에 업로드"""
    result = upload_cases(load_langsmith_client())
    print(f"uploaded={len(EVALUATION_CASES)} result={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
