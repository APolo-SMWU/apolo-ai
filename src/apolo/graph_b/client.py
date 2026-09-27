"""OpenAI 구조화 출력을 사용하는 Graph B 콘텐츠 생성 클라이언트"""

import json
from typing import Any

from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import ValidationError

from apolo.content_selection.rules import ContentSelection
from apolo.contracts.content import GraphBOutput, graph_b_output_json_schema
from apolo.graph_b.prompt import build_content_generation_prompt
from apolo.llm.config import LangSmithSettings, LlmSettings


class ContentGenerationClientError(RuntimeError):
    """LLM 응답이 Graph B 출력 계약을 만족하지 않을 때 발생"""


class OpenAIContentGenerationClient:
    """선별된 KG를 Graph B 콘텐츠 블록으로 변환"""

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

    def generate(
        self, selection: ContentSelection, requirements: str = ""
    ) -> GraphBOutput:
        """선별된 KG에서 구조화된 콘텐츠 블록을 생성"""
        prompt = build_content_generation_prompt(selection, requirements)
        response = self._responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "graph_b_output",
                    "strict": True,
                    "schema": graph_b_output_json_schema(),
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise ContentGenerationClientError("LLM이 Graph B 콘텐츠 JSON을 반환하지 않았습니다.")

        try:
            return GraphBOutput.model_validate_json(output_text)
        except (ValidationError, json.JSONDecodeError) as error:
            message = "LLM 응답이 Graph B 콘텐츠 JSON 계약을 만족하지 않습니다."
            raise ContentGenerationClientError(message) from error
