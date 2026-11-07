"""OpenAI 구조화 출력으로 선별된 KG를 CV 섹션 항목으로 변환"""

from typing import Any

from apolo.contracts.cv import CvOutput, cv_output_json_schema
from apolo.cv.candidates import CvCandidate
from apolo.cv.prompt import build_cv_generation_prompt
from apolo.llm.client import StructuredOutputClient
from apolo.llm.config import LangSmithSettings, LlmSettings


class OpenAICvGenerationClient(StructuredOutputClient):
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
            timeout=llm_settings.cv_timeout_seconds,
            responses=responses,
        )

    def generate(self, candidates: list[CvCandidate], requirements: str = "") -> CvOutput:
        prompt = build_cv_generation_prompt(candidates, requirements)
        return self._call(
            prompt.system,
            prompt.user,
            name="cv_output",
            schema=cv_output_json_schema(),
            output_type=CvOutput,
            label="CV",
        )
