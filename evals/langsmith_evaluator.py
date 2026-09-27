"""LangSmith Dataset에서 Graph A·Graph B 결과를 평가하는 실행기."""

from collections.abc import Callable, Mapping
from typing import Any

from langsmith import Client, evaluate
from langsmith.evaluation import run_evaluator
from langsmith.schemas import Example, Run

from evals.langsmith_dataset import DEFAULT_DATASET_NAME, load_langsmith_client

EVALUATOR_NAME = "apolo_expected_fields"


def score_expected_fields(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    """기대 결과에 명시된 필드만 비교해 부분 점수와 불일치 필드를 반환"""
    if not expected:
        return {"key": EVALUATOR_NAME, "score": 1.0, "comment": "기대 필드가 없습니다."}

    mismatches = [
        key for key, expected_value in expected.items() if actual.get(key) != expected_value
    ]
    score = (len(expected) - len(mismatches)) / len(expected)
    comment = "일치" if not mismatches else f"불일치 필드: {', '.join(mismatches)}"
    return {"key": EVALUATOR_NAME, "score": score, "comment": comment}


@run_evaluator
def evaluate_graph_output(run: Run, example: Example | None = None) -> dict[str, Any]:
    """LangSmith Run 출력과 Dataset 기대 결과를 비교"""
    actual = run.outputs or {}
    expected_wrapper = example.outputs if example is not None else None
    expected = expected_wrapper.get("expected", {}) if expected_wrapper else {}
    return score_expected_fields(actual, expected)


def run_langsmith_evaluation(
    target: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    dataset_name: str = DEFAULT_DATASET_NAME,
    client: Client | None = None,
) -> Any:
    """지정한 target을 Dataset에 실행하고 deterministic evaluator를 적용"""
    return evaluate(
        target,
        data=dataset_name,
        evaluators=[evaluate_graph_output],
        client=client or load_langsmith_client(),
        experiment_prefix="apolo-ai",
        description="APolo AI Graph A·Graph B 합성 평가",
        metadata={"apoloEvaluationVersion": "1", "synthetic": True},
    )
