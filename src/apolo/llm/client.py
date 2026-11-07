"""OpenAI 구조화 출력과 LangSmith tracing을 사용하는 LLM 클라이언트"""

import json
from typing import Any

from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from apolo.contracts.extraction import ExtractionResult, StructuredExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.extraction.entity_linking import (
    EntitySummary,
    LinkedClass,
    build_entity_linking_prompt,
)
from apolo.extraction.linking import LinkingResult
from apolo.extraction.prompt import build_extraction_prompt
from apolo.extraction.work_linking import WorkSummary, build_work_linking_prompt
from apolo.llm.config import LangSmithSettings, LlmSettings


class LlmOutputError(RuntimeError):
    """LLM 응답이 JSON 계약을 만족하지 않을 때 발생"""


class StructuredOutputClient:
    """JSON schema로 응답 형식을 강제하는 OpenAI 호출 공통부"""

    def __init__(
        self,
        llm_settings: LlmSettings,
        langsmith_settings: LangSmithSettings,
        *,
        timeout: float,
        responses: Any | None = None,
    ) -> None:
        if not llm_settings.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        if langsmith_settings.tracing_enabled and not langsmith_settings.api_key:
            raise ValueError("LangSmith tracing 활성화에는 LANGSMITH_API_KEY가 필요합니다.")

        self._model = llm_settings.extraction_model
        if responses is not None:
            self._responses = responses
            return

        client = OpenAI(api_key=llm_settings.api_key, timeout=timeout, max_retries=0)
        if langsmith_settings.tracing_enabled:
            client = wrap_openai(client)
        self._responses = client.responses

    def _call[T: BaseModel](
        self,
        system: str,
        user: str,
        *,
        name: str,
        schema: dict[str, Any],
        output_type: type[T],
        label: str,
    ) -> T:
        response = self._responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text={
                "format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise LlmOutputError(f"LLM이 {label} JSON을 반환하지 않았습니다.")
        try:
            return output_type.model_validate_json(output_text)
        except (ValidationError, json.JSONDecodeError) as error:
            raise LlmOutputError(f"LLM 응답이 {label} JSON 계약을 만족하지 않습니다.") from error


class OpenAIExtractionClient(StructuredOutputClient):
    """Source 하나를 LLM 후보 추출 결과로 변환"""

    def __init__(
        self,
        llm_settings: LlmSettings,
        langsmith_settings: LangSmithSettings,
        *,
        responses: Any | None = None,
    ) -> None:
        super().__init__(
            llm_settings,
            langsmith_settings,
            timeout=llm_settings.extraction_timeout_seconds,
            responses=responses,
        )

    def extract(self, source: CollectedSource) -> ExtractionResult:
        prompt = build_extraction_prompt(source)
        result = self._call(
            prompt.system,
            prompt.user,
            name="extraction_result",
            schema=StructuredExtractionResult.model_json_schema(),
            output_type=StructuredExtractionResult,
            label="후보 추출",
        )
        return result.to_extraction_result()


class OpenAIWorkLinkingClient(StructuredOutputClient):
    """출처가 다른 같은 프로젝트 Work와 같은 기관·활동·자격 묶음 판정"""

    def __init__(
        self,
        llm_settings: LlmSettings,
        langsmith_settings: LangSmithSettings,
        *,
        responses: Any | None = None,
    ) -> None:
        super().__init__(
            llm_settings,
            langsmith_settings,
            timeout=llm_settings.extraction_timeout_seconds,
            responses=responses,
        )

    def link(self, works: list[WorkSummary]) -> LinkingResult:
        return self._judge(*build_work_linking_prompt(works))

    def link_entities(
        self, class_type: LinkedClass, summaries: list[EntitySummary]
    ) -> LinkingResult:
        return self._judge(*build_entity_linking_prompt(class_type, summaries))

    def _judge(self, system: str, user: str) -> LinkingResult:
        return self._call(
            system,
            user,
            name="work_linking_result",
            schema=LinkingResult.model_json_schema(),
            output_type=LinkingResult,
            label="병합 판정",
        )
