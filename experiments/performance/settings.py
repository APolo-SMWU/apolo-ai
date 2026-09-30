"""성능 실험에서 공통으로 쓰는 변경 가능한 설정값.

주소·모델 endpoint는 파일 값을 바꾸거나 대응하는 APOLO_PERF_* 환경 변수로
덮어쓸 수 있다. 실험별 스크립트는 이 파일의 값을 함께 사용한다.
"""

from __future__ import annotations

import os


def _value(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


NOTION_URL = _value(
    "APOLO_PERF_NOTION_URL",
    "https://hyper-breakfast-e73.notion.site/Portfolio-Miji-Kim-3abfbcc778da80ebaf4cdf8226cae3cf?source=copy_link",
)
GITHUB_URL = _value("APOLO_PERF_GITHUB_URL", "https://github.com/miji0")
SOURCE_URLS = (NOTION_URL, GITHUB_URL)

# AI 서버는 요청 본문에서 모델을 받지 않고 서버 환경변수로 모델을 고른다.
# 따라서 모델 비교는 모델별로 다른 포트에서 실행한 서버를 지정해야 한다.
MODEL_IDS = (
    "gpt-6-luna",
    "gpt-6-sol",
    "gpt-6.1-sol",
    "gpt-5.6-luna",
)
MODEL_ENDPOINTS = {
    model_id: _value(
        f"APOLO_PERF_URL_{model_id.upper().replace('.', '_').replace('-', '_')}",
        f"http://127.0.0.1:{8101 + index}",
    )
    for index, model_id in enumerate(MODEL_IDS)
}

# 모델 비교 외 실험에서 쓰는 공통 모델.
COMMON_LLM_MODEL = "gpt-6-luna"
API_BASE_URL = _value(
    "APOLO_PERF_API_BASE_URL", MODEL_ENDPOINTS[COMMON_LLM_MODEL]
)
KG_EFFECT_API_URL = _value("APOLO_PERF_KG_EFFECT_API_URL", API_BASE_URL)
SOURCE_TIMING_MODEL = COMMON_LLM_MODEL
SOURCE_TIMING_API_URL = _value("APOLO_PERF_SOURCE_TIMING_API_URL", API_BASE_URL)

TIMEOUT_SECONDS = float(_value("APOLO_PERF_TIMEOUT_SECONDS", "300"))
REPETITIONS = int(_value("APOLO_PERF_REPETITIONS", "3"))
USER_ID_BASE = int(_value("APOLO_PERF_USER_ID_BASE", "990100"))
REQUIREMENTS = _value("APOLO_PERF_REQUIREMENTS", "")
EXPECTED_BLOCK_TYPES = tuple(
    part.strip()
    for part in _value("APOLO_PERF_EXPECTED_BLOCK_TYPES", "").split(",")
    if part.strip()
)

PROFILE = {
    "name": _value("APOLO_PERF_PROFILE_NAME", "성능 실험 사용자"),
    "email": _value("APOLO_PERF_PROFILE_EMAIL", "performance-test@example.com"),
    "phone": None,
    "github": None,
    "company": None,
    "jobTitle": None,
    "tel": None,
    "university": None,
    "department": None,
    "major": None,
}

OUTPUT_DIR = "experiments/performance/results"
