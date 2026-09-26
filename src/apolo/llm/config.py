"""Graph A LLM·LangSmith 실행 환경 설정"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_EXTRACTION_MODEL = "gpt-5.6-luna"
DEFAULT_LANGSMITH_PROJECT = "apolo-ai"


@dataclass(frozen=True)
class LlmSettings:
    """후보 추출 LLM 설정"""

    api_key: str | None
    extraction_model: str


@dataclass(frozen=True)
class LangSmithSettings:
    """LangSmith tracing 설정"""

    tracing_enabled: bool
    api_key: str | None
    project: str


def load_llm_settings() -> LlmSettings:
    """환경 변수에서 후보 추출 LLM 설정을 읽음"""
    load_dotenv()
    return LlmSettings(
        api_key=_optional_env("OPENAI_API_KEY"),
        extraction_model=os.getenv("APOLO_EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL),
    )


def load_langsmith_settings() -> LangSmithSettings:
    """환경 변수에서 LangSmith tracing 설정을 읽음"""
    load_dotenv()
    return LangSmithSettings(
        tracing_enabled=os.getenv("LANGSMITH_TRACING", "").lower() == "true",
        api_key=_optional_env("LANGSMITH_API_KEY"),
        project=os.getenv("LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT),
    )


def _optional_env(name: str) -> str | None:
    """빈 환경 변수는 미설정으로 처리"""
    value = os.getenv(name, "").strip()
    return value or None
