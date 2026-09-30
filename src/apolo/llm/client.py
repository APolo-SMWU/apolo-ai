"""OpenAI 구조화 출력과 LangSmith tracing을 사용하는 Graph A 후보 추출"""

import json
from typing import Any

from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import ValidationError

from apolo.contracts.extraction import ExtractionResult, StructuredExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.extraction.prompt import build_extraction_prompt
from apolo.llm.config import LangSmithSettings, LlmSettings


class ExtractionClientError(RuntimeError):
    """LLM 응답이 후보 추출 계약을 만족하지 않을 때 발생"""


class OpenAIExtractionClient:
    """Source 하나를 LLM 후보 추출 결과로 변환"""

    def __init__(
        self,
        llm_settings: LlmSettings,
        langsmith_settings: LangSmithSettings,
        *,
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

        client = OpenAI(
            api_key=llm_settings.api_key,
            timeout=llm_settings.extraction_timeout_seconds,
            max_retries=0,
        )
        if langsmith_settings.tracing_enabled:
            client = wrap_openai(client)
        self._responses = client.responses

    def extract(self, source: CollectedSource) -> ExtractionResult:
        """Source를 구조화된 LLM 후보로 추출"""
        prompt = build_extraction_prompt(source)
        response = self._responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "extraction_result",
                    "strict": True,
                    "schema": StructuredExtractionResult.model_json_schema(),
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise ExtractionClientError("LLM이 후보 추출 JSON을 반환하지 않았습니다.")

        try:
            result = StructuredExtractionResult.model_validate_json(output_text)
        except (ValidationError, json.JSONDecodeError) as error:
            message = "LLM 응답이 후보 추출 JSON 계약을 만족하지 않습니다."
            raise ExtractionClientError(message) from error
        return result.to_extraction_result()
