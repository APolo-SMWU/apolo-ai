"""Graph A LLM·LangSmith 실행 환경 설정"""

import math
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_EXTRACTION_MODEL = "gpt-5.6-luna"
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 240.0
DEFAULT_LANGSMITH_PROJECT = "apolo-ai"


@dataclass(frozen=True)
class LlmSettings:
    """후보 추출 LLM 설정"""

    api_key: str | None
    extraction_model: str
    extraction_timeout_seconds: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS


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
        extraction_timeout_seconds=_positive_float_env(
            "APOLO_EXTRACTION_TIMEOUT_SECONDS", DEFAULT_EXTRACTION_TIMEOUT_SECONDS
        ),
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


def _positive_float_env(name: str, default: float) -> float:
    """양수인 실수 환경 변수를 읽고 잘못된 값은 기본값으로 대체"""
    value = _optional_env(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default
