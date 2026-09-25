"""APolo AI 서버의 FastAPI 진입점."""

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apolo.contracts.generate import GenerateRequest, GenerateResponse, GenerateWarning
from apolo.contracts.profile import SeedProfileInput
from apolo.db.connection import connect_db
from apolo.generation import build_profile_only_response
from apolo.seed.persistence import ensure_profile_seed

app = FastAPI(title="APolo AI")
logger = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
    # 원본 입력에는 개인정보가 있으므로 오류 응답에 그대로 포함하지 않는다.
    return JSONResponse(status_code=400, content={"detail": "요청 필드와 형식을 확인해 주세요."})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse, response_model_exclude_none=True)
def generate(request: GenerateRequest) -> GenerateResponse:
    """프로필 Seed 전용 초기 경로. 외부 소스 수집·LLM 생성은 아직 실행하지 않는다."""
    source = SeedProfileInput(
        userId=request.user_id,
        userType=request.user_type,
        myPageProfile=request.my_page_profile,
    )
    try:
        with connect_db() as connection:
            seed = ensure_profile_seed(connection, source, now=datetime.now(UTC))
            response = build_profile_only_response(seed)
            if request.external_links or request.my_page_profile.github:
                response.warnings.append(GenerateWarning(
                    code="SOURCE_COLLECTION_NOT_IMPLEMENTED",
                    message="외부 링크와 GitHub는 수집하지 않았습니다. 프로필 입력만 반영했습니다.",
                ))
            if request.requirements.strip():
                response.warnings.append(GenerateWarning(
                    code="REQUIREMENTS_NOT_IMPLEMENTED",
                    message="요구사항의 사실 추출과 콘텐츠 선별은 아직 반영하지 않았습니다.",
                ))
        return response
    except Exception as error:
        
        logger.error("프로필 기반 생성 실패: %s", type(error).__name__)
        raise HTTPException(status_code=500, detail="콘텐츠 생성 중 오류가 발생했습니다.") from None
