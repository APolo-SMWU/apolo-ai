"""세 성능 실험 스크립트의 공통 API·결과 처리 함수."""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apolo.collectors.public import collect_public_sources  # noqa: E402, I001
from apolo.contracts.generate import GenerateResponse  # noqa: E402, I001


FATAL_WARNING_CODES = frozenset(
    {
        "GRAPH_B_INPUT_UNAVAILABLE",
        "GRAPH_B_GENERATION_FAILED",
        "GRAPH_B_OUTPUT_INVALID",
        "SOURCE_PROCESSING_FAILED",
    }
)


def generate_payload(user_id: int, links: list[str], settings: Any) -> dict[str, Any]:
    """동일한 실험 입력으로 /generate 요청 본문을 만든다."""
    return {
        "userId": user_id,
        "userType": "student",
        "myPageProfile": {**settings.PROFILE, "github": None},
        "title": "APolo 성능 실험",
        "externalLinks": links,
        "requirements": settings.REQUIREMENTS,
        "attachments": [],
    }


def check_health(base_url: str, timeout_seconds: float = 5) -> None:
    """실험 대상 API가 응답하는지 확인하고 비정상 endpoint는 중단한다."""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=timeout_seconds)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError(f"AI API health 확인 실패: {base_url} ({error})") from error
    if not isinstance(body, dict) or body.get("status") != "ok":
        raise RuntimeError(f"AI API가 정상 상태를 반환하지 않습니다: {base_url}")


def response_metrics(response: httpx.Response, expected_blocks: tuple[str, ...]) -> dict[str, Any]:
    """HTTP 응답의 API 계약·블록·경고를 요약한다."""
    try:
        body = response.json()
    except ValueError:
        return {
            "json_valid": False,
            "api_contract_valid": False,
            "response_keys": [],
            "blocks": [],
            "block_count": 0,
            "warnings": [],
            "graph_b_valid": False,
            "block_coverage": None,
            "response_body": response.text[:4000],
        }

    if not isinstance(body, dict):
        return {
            "json_valid": True,
            "api_contract_valid": False,
            "response_keys": [],
            "blocks": [],
            "block_count": 0,
            "warnings": [],
            "graph_b_valid": False,
            "block_coverage": None,
            "response_body": body,
        }

    blocks = body.get("blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    block_types = [item.get("type") for item in blocks if isinstance(item, dict)]
    warnings = body.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    warning_codes = [
        item.get("code")
        for item in warnings
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    ]
    expected = set(expected_blocks)
    coverage = (
        round(len(expected.intersection(block_types)) / len(expected), 4)
        if expected
        else None
    )
    try:
        GenerateResponse.model_validate(body)
        contract_valid = True
    except Exception:
        contract_valid = False
    return {
        "json_valid": True,
        "api_contract_valid": contract_valid,
        "content_contract_valid": contract_valid,
        "response_keys": sorted(body),
        "blocks": block_types,
        "block_count": len(blocks),
        "warnings": warning_codes,
        # 이는 Validator 세부 점수가 아니라 치명적 경고가 없는 응답의 대리 지표다.
        "graph_b_valid": contract_valid and not FATAL_WARNING_CODES.intersection(warning_codes),
        "block_coverage": coverage,
        "knowledge_graph_version": (body.get("meta") or {}).get("knowledgeGraphVersion")
        if isinstance(body, dict)
        else None,
        "response_body": body,
    }


def request_api(
    *,
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    expected_blocks: tuple[str, ...],
) -> dict[str, Any]:
    """AI API 호출을 한 건 수행하고 시간·응답 지표를 기록한다."""
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    record: dict[str, Any] = {
        "started_at": started_at,
        "base_url": base_url,
        "endpoint": endpoint,
        "user_id": payload.get("userId"),
        "source_urls": payload.get("externalLinks", payload.get("sourceLinks", [])),
    }
    try:
        with httpx.Client(base_url=base_url, timeout=timeout_seconds) as client:
            response = client.post(endpoint, json=payload)
        record.update(
            {
                "http_status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "timeout": False,
                **response_metrics(response, expected_blocks),
            }
        )
        if response.status_code != 200:
            record["graph_b_valid"] = False
    except httpx.TimeoutException as error:
        record.update(
            {
                "http_status": None,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "timeout": True,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    except httpx.HTTPError as error:
        record.update(
            {
                "http_status": None,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "timeout": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    record.setdefault("json_valid", False)
    record.setdefault("blocks", [])
    record.setdefault("block_count", 0)
    record.setdefault("warnings", [])
    record.setdefault("graph_b_valid", False)
    record.setdefault("timeout", False)
    return record


async def collect_sources(urls: list[str]) -> dict[str, Any]:
    """실험용 Direct LLM 경로에서 Graph A와 같은 공개 Source Collector를 쓴다."""
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        result = await collect_public_sources(urls, client=client)
    return {
        "sources": result.sources,
        "warnings": result.warnings,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def collect_sources_sync(urls: list[str]) -> dict[str, Any]:
    return asyncio.run(collect_sources(urls))


def normalized_title(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def duplicate_title_count(blocks: list[dict[str, Any]]) -> int:
    """Works·Activities 등 제목 필드가 있는 콘텐츠의 중복 제목 건수를 센다."""
    seen: set[str] = set()
    duplicates = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for item in block.get("items", []):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("organization") or ""
            key = normalized_title(str(title))
            if not key:
                continue
            if key in seen:
                duplicates += 1
            seen.add(key)
    return duplicates


def aggregate(records: list[dict[str, Any]], group_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = tuple(str(record.get(field, "")) for field in group_keys)
        groups.setdefault(key, []).append(record)

    summaries = []
    for key, items in sorted(groups.items()):
        elapsed = [item["elapsed_ms"] for item in items if item.get("elapsed_ms") is not None]
        successes = [item for item in items if item.get("http_status") == 200]
        warning_counts: dict[str, int] = {}
        for item in items:
            for warning in item.get("warnings", []):
                warning_counts[warning] = warning_counts.get(warning, 0) + 1
        summary: dict[str, Any] = dict(zip(group_keys, key, strict=True))
        summary.update(
            {
                "runs": len(items),
                "success_count": len(successes),
                "success_rate": round(len(successes) / len(items), 4) if items else 0,
                "median_ms": round(statistics.median(elapsed), 2) if elapsed else None,
                "max_ms": round(max(elapsed), 2) if elapsed else None,
                "mean_ms": round(statistics.fmean(elapsed), 2) if elapsed else None,
                "timeout_count": sum(bool(item.get("timeout")) for item in items),
                "json_valid_count": sum(bool(item.get("json_valid")) for item in items),
                "api_contract_valid_count": sum(
                    bool(item.get("api_contract_valid")) for item in items
                ),
                "content_contract_valid_count": sum(
                    bool(item.get("content_contract_valid")) for item in items
                ),
                "graph_b_valid_count": sum(bool(item.get("graph_b_valid")) for item in items),
                "graph_b_valid_observed_count": sum(
                    item.get("graph_b_valid") is not None for item in items
                ),
                "mean_block_coverage": round(
                    statistics.fmean(
                        item["block_coverage"]
                        for item in items
                        if item.get("block_coverage") is not None
                    ),
                    4,
                )
                if any(item.get("block_coverage") is not None for item in items)
                else None,
                "mean_duplicate_title_count": round(
                    statistics.fmean(
                        item["duplicate_title_count"]
                        for item in items
                        if item.get("duplicate_title_count") is not None
                    ),
                    4,
                )
                if any(item.get("duplicate_title_count") is not None for item in items)
                else None,
                "warning_counts": warning_counts,
            }
        )
        summaries.append(summary)
    return summaries


def save_results(
    records: list[dict[str, Any]],
    *,
    experiment: str,
    output_dir: str | Path,
    group_keys: tuple[str, ...],
) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_file = output_path / f"{experiment}-{run_id}.json"
    summary_file = output_path / f"{experiment}-{run_id}.summary.json"
    raw_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    summary_file.write_text(
        json.dumps(aggregate(records, group_keys), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return raw_file, summary_file
