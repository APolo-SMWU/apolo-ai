"""OpenAI 구조화 출력을 사용하는 Graph B 콘텐츠 생성 클라이언트"""

from typing import Any

from apolo.content_selection.rules import ContentSelection
from apolo.contracts.content import GraphBOutput, graph_b_output_json_schema
from apolo.graph_b.prompt import build_content_generation_prompt
from apolo.llm.client import StructuredOutputClient
from apolo.llm.config import LangSmithSettings, LlmSettings


class OpenAIContentGenerationClient(StructuredOutputClient):
    """선별된 KG를 Graph B 콘텐츠 블록으로 변환"""

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
            timeout=llm_settings.content_timeout_seconds,
            responses=responses,
        )

    def generate(self, selection: ContentSelection, requirements: str = "") -> GraphBOutput:
        prompt = build_content_generation_prompt(selection, requirements)
        return self._call(
            prompt.system,
            prompt.user,
            name="graph_b_output",
            schema=graph_b_output_json_schema(),
            output_type=GraphBOutput,
            label="Graph B 콘텐츠",
        )
