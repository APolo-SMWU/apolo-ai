"""실험 2: Direct LLM과 Source→Graph A→KG→Graph B를 같은 조건으로 비교."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import settings
from common import (
    REPO_ROOT,
    check_health,
    collect_sources_sync,
    duplicate_title_count,
    generate_payload,
    request_api,
    save_results,
)


DIRECT_SYSTEM_PROMPT = " ".join(
    (
        "Create portfolio content only from the supplied profile and source text.",
        "Do not infer missing dates, roles, organizations, skills, achievements, metrics, or URLs.",
        "Omit unsupported items instead of guessing, and use the strict output schema.",
        "For required entityId fields, use unique direct-prefixed synthetic IDs, not KG IDs.",
        "Use source URLs only when they identify the described work.",
        "Keep descriptions concise and specific in the source language.",
        "Do not add empty blocks or duplicate a work or activity.",
    )
)


def _direct_generation(model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """공개 원문을 직접 모델에 넣는 비교군. OpenAI usage도 저장한다."""
    from dotenv import load_dotenv
    from openai import OpenAI

    from apolo.contracts.content import GraphBOutput, graph_b_output_json_schema

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Direct LLM 비교군 실행에 OPENAI_API_KEY가 필요합니다.")

    collection = collect_sources_sync(payload["externalLinks"])
    sources = collection["sources"]
    source_payload = [
        {
            "sourceType": source.source_type,
            "sourceUrl": source.source_url,
            "sourceVersion": source.source_version,
            "content": source.content,
        }
        for source in sources
    ]
    if not source_payload:
        raise RuntimeError(
            "Direct LLM 비교군에 전달할 Source를 수집하지 못했습니다: "
            + ", ".join(warning.code for warning in collection["warnings"])
        )

    schema = graph_b_output_json_schema()
    user_prompt = "\n\n".join(
        (
            "Output schema:\n" + json.dumps(schema, ensure_ascii=False),
            "User profile:\n" + json.dumps(payload["myPageProfile"], ensure_ascii=False),
            "Requirements:\n" + (payload.get("requirements") or "None"),
            "Original sources:\n" + json.dumps(source_payload, ensure_ascii=False),
        )
    )

    started = time.perf_counter()
    response = OpenAI(api_key=api_key, timeout=settings.TIMEOUT_SECONDS).responses.create(
        model=model_id,
        input=[
            {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "direct_portfolio_output",
                "strict": True,
                "schema": schema,
            }
        },
    )
    generation_ms = round((time.perf_counter() - started) * 1000, 2)
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("Direct LLM이 구조화된 출력 본문을 반환하지 않았습니다.")
    output = GraphBOutput.model_validate_json(output_text)
    body = output.model_dump(mode="json", by_alias=True, exclude_none=True)
    usage = getattr(response, "usage", None)
    return {
        "body": body,
        "collection_ms": collection["elapsed_ms"],
        "generation_ms": generation_ms,
        "elapsed_ms": round(collection["elapsed_ms"] + generation_ms, 2),
        "source_count": len(sources),
        "source_content_chars": sum(len(source.content) for source in sources),
        "collection_warnings": [warning.code for warning in collection["warnings"]],
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="실험 2: KG 기반 생성 효과")
    parser.add_argument("--repetitions", type=int, default=settings.REPETITIONS)
    parser.add_argument("--user-id-base", type=int, default=settings.USER_ID_BASE + 200_000)
    parser.add_argument("--output-dir", default=settings.OUTPUT_DIR)
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("repetitions는 최소 3이어야 합니다.")

    model_id = settings.COMMON_LLM_MODEL
    base_url = settings.KG_EFFECT_API_URL.rstrip("/")
    try:
        check_health(base_url)
    except RuntimeError as error:
        parser.error(str(error))

    records = []
    print(f"[{model_id}] endpoint={base_url}")
    for repetition in range(1, args.repetitions + 1):
        user_id = args.user_id_base + repetition
        payload = generate_payload(user_id, list(settings.SOURCE_URLS), settings)
        print(f"  repetition={repetition}/{args.repetitions} user_id={user_id}")

        kg = request_api(
            base_url=base_url,
            endpoint="/generate",
            payload=payload,
            timeout_seconds=settings.TIMEOUT_SECONDS,
            expected_blocks=settings.EXPECTED_BLOCK_TYPES,
        )
        kg.update(
            {
                "experiment": "kg-effect",
                "condition": "kg-pipeline",
                "model": model_id,
                "repetition": repetition,
                "content_contract_valid": kg.get("api_contract_valid"),
            }
        )
        kg_body = kg.get("response_body") or {}
        kg_blocks = kg_body.get("blocks", []) if isinstance(kg_body, dict) else []
        kg["duplicate_title_count"] = duplicate_title_count(kg_blocks)
        kg["manual_review"] = {
            "unsupported_fact_count": None,
            "required_field_coverage": None,
            "source_conflict_retention": None,
            "reviewer_notes": "",
        }
        records.append(kg)

        direct_started = time.perf_counter()
        try:
            direct = _direct_generation(model_id, payload)
            body = direct.pop("body")
            blocks = body.get("blocks", [])
            direct_record = {
                "experiment": "kg-effect",
                "condition": "direct-llm",
                "model": model_id,
                "repetition": repetition,
                "user_id": user_id,
                "source_urls": list(settings.SOURCE_URLS),
                "http_status": 200,
                "json_valid": True,
                "api_contract_valid": None,
                "content_contract_valid": True,
                "graph_b_valid": None,
                "timeout": False,
                "blocks": [block.get("type") for block in blocks],
                "block_count": len(blocks),
                "warnings": direct["collection_warnings"],
                "duplicate_title_count": duplicate_title_count(blocks),
                "response_body": body,
                **direct,
            }
        except Exception as error:
            direct_record = {
                "experiment": "kg-effect",
                "condition": "direct-llm",
                "model": model_id,
                "repetition": repetition,
                "user_id": user_id,
                "source_urls": list(settings.SOURCE_URLS),
                "http_status": None,
                "json_valid": False,
                "api_contract_valid": None,
                "content_contract_valid": False,
                "graph_b_valid": False,
                "timeout": "timeout" in type(error).__name__.lower(),
                "elapsed_ms": round((time.perf_counter() - direct_started) * 1000, 2),
                "error_type": type(error).__name__,
                "error": str(error),
            }
        direct_record["elapsed_ms"] = direct_record.get(
            "elapsed_ms", round((time.perf_counter() - direct_started) * 1000, 2)
        )
        # 의미적 근거 준수·충돌 보존은 자동 판정하지 않고 사람이 채울 평가 칸으로 둔다.
        direct_record["manual_review"] = {
            "unsupported_fact_count": None,
            "required_field_coverage": None,
            "source_conflict_retention": None,
            "reviewer_notes": "",
        }
        records.append(direct_record)
        print(
            f"    kg_status={kg.get('http_status')} "
            f"direct_status={direct_record.get('http_status')} "
            f"direct_ms={direct_record.get('elapsed_ms')}"
        )

    raw_file, summary_file = save_results(
        records,
        experiment="experiment-2-kg-effect",
        output_dir=args.output_dir,
        group_keys=("condition",),
    )
    print(f"원시 결과: {raw_file}")
    print(f"집계 결과: {summary_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
