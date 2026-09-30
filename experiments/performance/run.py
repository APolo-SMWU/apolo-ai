"""Legacy 단일 API 성능 실험 실행기.

같은 Profile·Source·requirements를 반복 요청하고, 원시 결과와 집계 결과를
JSON으로 저장한다. 서버의 LLM 모델은 실행 중인 API 서버의 설정을 사용하며,
모델 비교 시에는 모델별 서버를 별도로 실행하고 --model 값만 바꿔 기록한다.

새 성능 실험은 experiment_1_model_selection.py, experiment_2_kg_effect.py,
experiment_3_source_timing.py를 사용한다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

FATAL_WARNING_CODES = frozenset(
    {
        "GRAPH_B_INPUT_UNAVAILABLE",
        "GRAPH_B_GENERATION_FAILED",
        "GRAPH_B_OUTPUT_INVALID",
        "SOURCE_PROCESSING_FAILED",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APolo AI 성능 실험 실행")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="실험 설정 JSON 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
        help="결과 저장 폴더",
    )
    parser.add_argument("--model", help="결과에 기록할 모델 이름")
    parser.add_argument(
        "--only",
        action="append",
        choices=(
            "profile-only",
            "notion-only",
            "github-only",
            "notion-github",
            "update-unchanged",
        ),
        help="실행할 시나리오를 제한한다. 여러 번 지정할 수 있다.",
    )
    return parser.parse_args()


def read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"설정 파일이 없습니다: {path}\n"
            f"config.example.json을 config.json으로 복사한 뒤 Source를 입력하세요."
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"설정 JSON을 읽을 수 없습니다: {error}") from error

    if not isinstance(config, dict):
        raise SystemExit("설정 파일의 최상위 값은 객체여야 합니다.")
    repetitions = int(config.get("repetitions", 3))
    if repetitions < 3:
        raise SystemExit("repetitions는 최소 3이어야 합니다.")
    if int(config.get("user_id_base", 0)) <= 0:
        raise SystemExit("user_id_base는 양의 테스트 전용 정수여야 합니다.")
    return config


def scenario_definitions(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = config.get("sources", {})
    notion_urls = [str(item) for item in sources.get("notion", []) if item]
    github_urls = [str(item) for item in sources.get("github", []) if item]
    scenarios: list[dict[str, Any]] = [
        {"name": "profile-only", "kind": "generate", "links": []}
    ]

    for index, url in enumerate(notion_urls, start=1):
        scenarios.append(
            {
                "name": "notion-only",
                "case_name": f"notion-{index}",
                "kind": "generate",
                "links": [url],
            }
        )
    for index, url in enumerate(github_urls, start=1):
        scenarios.append(
            {
                "name": "github-only",
                "case_name": f"github-{index}",
                "kind": "generate",
                "links": [url],
            }
        )
    if notion_urls and github_urls:
        scenarios.append(
            {
                "name": "notion-github",
                "case_name": "notion-github-1",
                "kind": "generate",
                "links": [notion_urls[0], github_urls[0]],
            }
        )
        scenarios.append(
            {
                "name": "update-unchanged",
                "case_name": "notion-github-1",
                "kind": "update",
                "links": [notion_urls[0], github_urls[0]],
            }
        )

    return scenarios


def request_payload(
    config: dict[str, Any], user_id: int, links: list[str], kind: str
) -> dict[str, Any]:
    if kind == "update":
        return {
            "userId": user_id,
            "sourceLinks": links,
            "requirements": config.get("requirements", ""),
        }

    profile = dict(config.get("profile", {}))
    profile.setdefault("github", None)
    return {
        "userId": user_id,
        "userType": "student",
        "myPageProfile": profile,
        "title": "APolo 성능 실험",
        "externalLinks": links,
        "requirements": config.get("requirements", ""),
        "attachments": [],
    }


def response_metrics(response: httpx.Response, expected_blocks: list[str]) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {
            "json_valid": False,
            "graph_b_valid": False,
            "response_keys": [],
            "blocks": [],
            "warnings": [],
            "meta": None,
            "block_coverage": None,
        }

    blocks = body.get("blocks", [])
    warnings = body.get("warnings", [])
    block_types = [block.get("type") for block in blocks if isinstance(block, dict)]
    warning_codes = [
        warning.get("code")
        for warning in warnings
        if isinstance(warning, dict) and warning.get("code")
    ]
    coverage = None
    if expected_blocks:
        coverage = round(
            len(set(expected_blocks).intersection(block_types)) / len(set(expected_blocks)),
            4,
        )
    return {
        "json_valid": True,
        "response_keys": sorted(body.keys()),
        "blocks": block_types,
        "block_count": len(blocks) if isinstance(blocks, list) else 0,
        "warnings": warning_codes,
        "graph_b_valid": not FATAL_WARNING_CODES.intersection(warning_codes),
        "block_coverage": coverage,
        "meta": body.get("meta"),
    }


def run_request(
    client: httpx.Client,
    config: dict[str, Any],
    scenario: dict[str, Any],
    repetition: int,
    user_id: int,
) -> dict[str, Any]:
    payload = request_payload(config, user_id, scenario["links"], scenario["kind"])
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    result: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "scenario": scenario["name"],
        "case_name": scenario.get("case_name", scenario["name"]),
        "repetition": repetition,
        "user_id": user_id,
        "model": config.get("model", "default"),
        "source_count": len(scenario["links"]),
        "source_urls": scenario["links"],
        "endpoint": "/update-content" if scenario["kind"] == "update" else "/generate",
    }

    try:
        response = client.post(result["endpoint"], json=payload)
        expected_blocks = [str(item) for item in config.get("expected_block_types", [])]
        result.update(
            {
                "http_status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                **response_metrics(response, expected_blocks),
            }
        )
    except httpx.TimeoutException as error:
        result.update(
            {
                "http_status": None,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "timeout": True,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    except httpx.HTTPError as error:
        result.update(
            {
                "http_status": None,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "timeout": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )

    result.setdefault("timeout", False)
    result.setdefault("json_valid", False)
    result.setdefault("graph_b_valid", False)
    result.setdefault("warnings", [])
    result.setdefault("block_coverage", None)
    return result


def aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(
            (record["model"], record["scenario"], record["case_name"]), []
        ).append(record)

    summaries: list[dict[str, Any]] = []
    for (model, scenario, case_name), items in sorted(groups.items()):
        elapsed = [item["elapsed_ms"] for item in items if item.get("elapsed_ms") is not None]
        successful = [item for item in items if item.get("http_status") == 200]
        warning_counts: dict[str, int] = {}
        for item in items:
            for warning in item.get("warnings", []):
                warning_counts[warning] = warning_counts.get(warning, 0) + 1

        summaries.append(
            {
                "model": model,
                "scenario": scenario,
                "case_name": case_name,
                "source_urls": items[0].get("source_urls", []),
                "runs": len(items),
                "success_count": len(successful),
                "success_rate": round(len(successful) / len(items), 4) if items else 0,
                "median_ms": round(statistics.median(elapsed), 2) if elapsed else None,
                "max_ms": round(max(elapsed), 2) if elapsed else None,
                "mean_ms": round(statistics.fmean(elapsed), 2) if elapsed else None,
                "timeout_count": sum(bool(item.get("timeout")) for item in items),
                "json_valid_count": sum(bool(item.get("json_valid")) for item in items),
                "graph_b_valid_count": sum(bool(item.get("graph_b_valid")) for item in items),
                "graph_b_valid_rate": round(
                    sum(bool(item.get("graph_b_valid")) for item in items) / len(items), 4
                )
                if items
                else 0,
                "non_empty_block_count": sum(
                    bool(item.get("block_count")) for item in items
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
                "warning_counts": warning_counts,
            }
        )
    return summaries


def main() -> int:
    args = parse_args()
    config = read_config(args.config)
    if args.model:
        config["model"] = args.model
    scenarios = scenario_definitions(config)
    if args.only:
        scenarios = [scenario for scenario in scenarios if scenario["name"] in args.only]
    if not scenarios:
        raise SystemExit("실행할 시나리오가 없습니다. config.json의 Source를 확인하세요.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    records: list[dict[str, Any]] = []
    user_id_base = int(config["user_id_base"])
    repetitions = int(config.get("repetitions", 3))
    timeout = httpx.Timeout(float(config.get("timeout_seconds", 300)))

    with httpx.Client(base_url=config["base_url"], timeout=timeout) as client:
        for scenario_index, scenario in enumerate(scenarios):
            for repetition in range(1, repetitions + 1):
                # 시나리오·반복마다 테스트 전용 KG를 분리해 결과가 누적되지 않게 한다.
                user_id = user_id_base + scenario_index * 1000 + repetition
                print(f"[{scenario['name']}] repetition={repetition} user_id={user_id}")
                if scenario["kind"] == "update":
                    baseline = run_request(
                        client,
                        config,
                        {"name": "baseline", "kind": "generate", "links": scenario["links"]},
                        repetition,
                        user_id,
                    )
                    print(
                        f"  baseline_status={baseline.get('http_status')} "
                        f"baseline_elapsed_ms={baseline.get('elapsed_ms')}"
                    )
                record = run_request(client, config, scenario, repetition, user_id)
                if scenario["kind"] == "update":
                    record["baseline_http_status"] = baseline.get("http_status")
                records.append(record)
                print(
                    f"  status={record.get('http_status')} "
                    f"elapsed_ms={record.get('elapsed_ms')} "
                    f"warnings={record.get('warnings', [])}"
                )

    raw_path = args.output_dir / f"{run_id}.json"
    summary_path = args.output_dir / f"{run_id}.summary.json"
    raw_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(
        json.dumps(aggregate(records), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"원시 결과: {raw_path}")
    print(f"집계 결과: {summary_path}")
    print(json.dumps(aggregate(records), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
