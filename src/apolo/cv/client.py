"""OpenAI 구조화 출력으로 선별된 KG를 CV 섹션 항목으로 변환"""

import json
from typing import Any

from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import ValidationError

from apolo.contracts.cv import CvOutput, cv_output_json_schema
from apolo.cv.candidates import CvCandidate
from apolo.cv.prompt import build_cv_generation_prompt
from apolo.graph_b.client import ContentGenerationClientError
from apolo.llm.config import LangSmithSettings, LlmSettings


class OpenAICvGenerationClient:
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

        client = OpenAI(api_key=llm_settings.api_key)
        if langsmith_settings.tracing_enabled:
            client = wrap_openai(client)
        self._responses = client.responses

    def generate(self, candidates: list[CvCandidate], requirements: str = "") -> CvOutput:
        prompt = build_cv_generation_prompt(candidates, requirements)
        response = self._responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "cv_output",
                    "strict": True,
                    "schema": cv_output_json_schema(),
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise ContentGenerationClientError("LLM이 CV JSON을 반환하지 않았습니다.")

        try:
            return CvOutput.model_validate_json(output_text)
        except (ValidationError, json.JSONDecodeError) as error:
            message = "LLM 응답이 CV JSON 계약을 만족하지 않습니다."
            raise ContentGenerationClientError(message) from error
