"""APolo AI 서버의 FastAPI 진입점."""

import logging
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apolo.collectors.public import PublicCollectionWarning
from apolo.contracts.generate import GenerateRequest, GenerateResponse, GenerateWarning
from apolo.contracts.profile import SeedProfileInput
from apolo.db.connection import connect_db
from apolo.db.seed import load_seed_by_user_id
from apolo.generation import build_profile_only_response
from apolo.graph_a.processing import GraphAProcessingWarning
from apolo.graph_a.workflow import build_graph_a
from apolo.llm.client import OpenAIExtractionClient
from apolo.llm.config import load_langsmith_settings, load_llm_settings
from apolo.seed.persistence import ensure_profile_seed
from apolo.source_collection import collect_and_store_public_sources

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
async def generate(request: GenerateRequest) -> GenerateResponse:
    """프로필 Seed 저장 후 외부 Source를 Graph A로 반영한다."""
    source = SeedProfileInput(
        userId=request.user_id,
        userType=request.user_type,
        myPageProfile=request.my_page_profile,
    )
    try:
        with connect_db() as connection:
            seed = ensure_profile_seed(connection, source, now=datetime.now(UTC))
            source_urls = [*request.external_links]
            if request.my_page_profile.github:
                source_urls.append(request.my_page_profile.github)

            warnings: list[GenerateWarning] = []
            if source_urls:
                warnings.extend(
                    await _run_graph_a(connection, seed.id, source_urls)
                )

            if "SOURCE_PROCESSING_FAILED" in {warning.code for warning in warnings}:
                response = build_profile_only_response(seed)
            else:
                latest_seed = load_seed_by_user_id(connection, request.user_id)
                if latest_seed is None:
                    latest_seed = seed
                response = build_profile_only_response(latest_seed)
            response.warnings.extend(warnings)
            if request.requirements.strip():
                response.warnings.append(GenerateWarning(
                    code="REQUIREMENTS_NOT_IMPLEMENTED",
                    message="요구사항의 사실 추출과 콘텐츠 선별은 아직 반영하지 않았습니다.",
                ))
        return response
    except Exception as error:
        
        logger.error("프로필 기반 생성 실패: %s", type(error).__name__)
        raise HTTPException(status_code=500, detail="콘텐츠 생성 중 오류가 발생했습니다.") from None


async def _run_graph_a(
    connection,
    graph_id,
    source_urls: list[str],
) -> list[GenerateWarning]:
    """공개 Source 수집과 Graph A 실행 결과를 API 경고로 변환"""
    try:
        async with httpx.AsyncClient() as client:
            collection = await collect_and_store_public_sources(
                connection,
                graph_id,
                source_urls,
                client=client,
            )
        if not collection.collected_sources:
            return [_collection_warning(item) for item in collection.warnings]
        graph = build_graph_a()
        result = graph.invoke(
            {
                "connection": connection,
                "graph_id": graph_id,
                "collection": collection,
                "extractor": OpenAIExtractionClient(
                    load_llm_settings(),
                    load_langsmith_settings(),
                ),
                "now": datetime.now(UTC),
                "result": None,
            }
        )["result"]
    except Exception:
        logger.error("Graph A 처리 실패", exc_info=True)
        return [
            GenerateWarning(
                code="SOURCE_PROCESSING_FAILED",
                message="외부 Source 처리에 실패했습니다. 프로필 정보만 반환합니다.",
            )
        ]

    warnings = [_collection_warning(item) for item in collection.warnings]
    warnings.extend(_graph_warning(item) for item in result.warnings)
    return warnings


def _collection_warning(warning: PublicCollectionWarning) -> GenerateWarning:
    """수집 경고를 Backend 응답 계약으로 변환"""
    return GenerateWarning(source=warning.source_url, code=warning.code, message=warning.message)


def _graph_warning(warning: GraphAProcessingWarning) -> GenerateWarning:
    """Graph A 경고를 Backend 응답 계약으로 변환"""
    return GenerateWarning(source=warning.source_key, code=warning.code, message=warning.message)
