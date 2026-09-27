"""APolo AI 서버의 FastAPI 진입점."""

import logging
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apolo.collectors.public import PublicCollectionWarning
from apolo.contracts.generate import (
    GenerateMeta,
    GenerateRequest,
    GenerateResponse,
    GenerateWarning,
)
from apolo.contracts.profile import SeedProfileInput
from apolo.contracts.update_content import UpdateContentRequest
from apolo.db.connection import connect_db
from apolo.db.seed import load_seed_by_user_id
from apolo.generation import build_graph_b_response, build_profile_only_response
from apolo.graph_a.processing import GraphAProcessingWarning
from apolo.graph_a.workflow import build_graph_a
from apolo.graph_b.client import OpenAIContentGenerationClient
from apolo.graph_b.input import load_graph_b_input
from apolo.graph_b.service import GraphBGenerationResult, generate_graph_b_content
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
    """프로필 Seed·외부 Source를 반영한 뒤 Graph B 콘텐츠를 생성한다."""
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

            graph_b_result, graph_b_warnings = _run_graph_b(
                connection, request.user_id, request.requirements
            )
            warnings.extend(graph_b_warnings)
            if graph_b_result is not None:
                response = build_graph_b_response(graph_b_result)
            else:
                latest_seed = load_seed_by_user_id(connection, request.user_id)
                if latest_seed is None:
                    latest_seed = seed
                response = build_profile_only_response(latest_seed)
            response.warnings.extend(warnings)
        return response
    except Exception as error:
        
        logger.error("프로필 기반 생성 실패: %s", type(error).__name__)
        raise HTTPException(status_code=500, detail="콘텐츠 생성 중 오류가 발생했습니다.") from None


@app.post("/update-content", response_model=GenerateResponse, response_model_exclude_none=True)
async def update_content(request: UpdateContentRequest) -> GenerateResponse:
    """기존 KG의 변경 Source를 재수집하고 Graph A를 실행한다."""
    try:
        with connect_db() as connection:
            seed = load_seed_by_user_id(connection, request.user_id)
            if seed is None:
                return GenerateResponse(
                    blocks=[],
                    meta=GenerateMeta(
                        ontology_schema_version="1.1", knowledge_graph_version=0
                    ),
                    warnings=[
                        GenerateWarning(
                            code="UPDATE_CONTENT_KG_NOT_FOUND",
                            message="사용자의 기존 Knowledge Graph를 찾지 못했습니다.",
                        )
                    ],
                )

            warnings = await _run_graph_a(connection, seed.id, request.source_links)
            latest_seed = load_seed_by_user_id(connection, request.user_id) or seed
            warnings.append(
                GenerateWarning(
                    code="GRAPH_B_NOT_RUN",
                    message="Source 갱신은 완료했으며 콘텐츠 재생성은 다음 단계에서 연결됩니다.",
                )
            )
            return GenerateResponse(
                blocks=[],
                meta=GenerateMeta(
                    ontology_schema_version=latest_seed.ontology_schema_version,
                    knowledge_graph_version=latest_seed.version,
                ),
                warnings=warnings,
            )
    except Exception:
        logger.error("Source 갱신 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="콘텐츠 갱신 중 오류가 발생했습니다.") from None


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


def _run_graph_b(
    connection,
    user_id: int,
    requirements: str,
) -> tuple[GraphBGenerationResult | None, list[GenerateWarning]]:
    """최신 KG에서 Graph B를 실행하고 API 경고로 변환"""
    try:
        graph_b_input = load_graph_b_input(connection, user_id, requirements)
        if graph_b_input is None:
            return None, [
                GenerateWarning(
                    code="GRAPH_B_INPUT_UNAVAILABLE",
                    message="현재 유효한 KG를 찾지 못해 Graph B를 실행하지 못했습니다.",
                )
            ]
        result = generate_graph_b_content(
            graph_b_input.graph,
            graph_b_input.requirements,
            OpenAIContentGenerationClient(
                load_llm_settings(),
                load_langsmith_settings(),
            ),
        )
    except Exception:
        logger.error("Graph B 처리 실패", exc_info=True)
        return None, [
            GenerateWarning(
                code="GRAPH_B_GENERATION_FAILED",
                message="콘텐츠 생성에 실패했습니다. 프로필 정보만 반환합니다.",
            )
        ]

    if not result.is_valid:
        return None, [
            GenerateWarning(
                code="GRAPH_B_OUTPUT_INVALID",
                message="생성 결과가 현재 KG와 일치하지 않아 콘텐츠를 사용하지 않았습니다.",
            )
        ]
    return result, []
