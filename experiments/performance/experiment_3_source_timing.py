"""실험 3: Profile·Source 수집·콘텐츠 갱신 처리시간 측정."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import settings  # noqa: E402
from common import (  # noqa: E402, I001
    check_health,
    collect_sources_sync,
    generate_payload,
    request_api,
    save_results,
)


def _source_hashes(urls: list[str]) -> dict[str, str]:
    collection = collect_sources_sync(urls)
    return {
        source.source_url: hashlib.sha256(source.content.encode("utf-8")).hexdigest()
        for source in collection["sources"]
    }


def _generate(
    user_id: int, links: list[str], repetition: int, case_name: str
) -> dict[str, Any]:
    payload = generate_payload(user_id, links, settings)
    record = request_api(
        base_url=settings.SOURCE_TIMING_API_URL,
        endpoint="/generate",
        payload=payload,
        timeout_seconds=settings.TIMEOUT_SECONDS,
        expected_blocks=settings.EXPECTED_BLOCK_TYPES,
    )
    record.update(
        {
            "experiment": "source-timing",
            "scenario": case_name,
            "model": settings.SOURCE_TIMING_MODEL,
            "repetition": repetition,
            "source_count": len(links),
        }
    )
    return record


def _update(user_id: int, links: list[str], repetition: int, case_name: str) -> dict[str, Any]:
    payload = {
        "userId": user_id,
        "sourceLinks": links,
        "requirements": settings.REQUIREMENTS,
    }
    record = request_api(
        base_url=settings.SOURCE_TIMING_API_URL,
        endpoint="/update-content",
        payload=payload,
        timeout_seconds=settings.TIMEOUT_SECONDS,
        expected_blocks=settings.EXPECTED_BLOCK_TYPES,
    )
    record.update(
        {
            "experiment": "source-timing",
            "scenario": case_name,
            "model": settings.SOURCE_TIMING_MODEL,
            "repetition": repetition,
            "source_count": len(links),
        }
    )
    return record


def _measure_standalone_fetch(urls: tuple[str, ...], repetition: int) -> list[dict[str, Any]]:
    records = []
    for source_url in urls:
        try:
            collection = collect_sources_sync([source_url])
            sources = collection["sources"]
            records.append(
                {
                    "experiment": "source-timing",
                    "scenario": "standalone-source-fetch",
                    "source_url": source_url,
                    "repetition": repetition,
                    "elapsed_ms": collection["elapsed_ms"],
                    "source_count": len(sources),
                    "source_content_chars": sum(len(source.content) for source in sources),
                    "warnings": [warning.code for warning in collection["warnings"]],
                }
            )
        except Exception as error:
            records.append(
                {
                    "experiment": "source-timing",
                    "scenario": "standalone-source-fetch",
                    "source_url": source_url,
                    "repetition": repetition,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="실험 3: Source 수집·갱신 처리시간")
    parser.add_argument("--repetitions", type=int, default=settings.REPETITIONS)
    parser.add_argument("--user-id-base", type=int, default=settings.USER_ID_BASE + 400_000)
    parser.add_argument("--output-dir", default=settings.OUTPUT_DIR)
    parser.add_argument(
        "--include-changed-update",
        action="store_true",
        help="baseline 뒤 수동으로 공개 Source를 수정하고 변경 여부를 확인한 뒤 갱신한다.",
    )
    parser.add_argument(
        "--skip-standalone-fetch",
        action="store_true",
        help="Collector 개별 측정을 생략한다.",
    )
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("repetitions는 최소 3이어야 합니다.")
    try:
        check_health(settings.SOURCE_TIMING_API_URL)
    except RuntimeError as error:
        parser.error(str(error))

    notion_url, github_url = settings.SOURCE_URLS
    scenarios = [
        ("profile-only", []),
        ("notion-only", [notion_url]),
        ("github-only", [github_url]),
        ("notion-github", [notion_url, github_url]),
        # 지원하지 않는 주소의 실패가 정상 Source 처리까지 막지 않는지 확인한다.
        ("partial-source-failure", [notion_url, "https://example.com/not-a-supported-source"]),
    ]
    records: list[dict[str, Any]] = []
    for repetition in range(1, args.repetitions + 1):
        print(f"repetition={repetition}/{args.repetitions}")
        if not args.skip_standalone_fetch:
            records.extend(_measure_standalone_fetch(settings.SOURCE_URLS, repetition))
        for scenario_index, (name, links) in enumerate(scenarios):
            user_id = args.user_id_base + scenario_index * 1000 + repetition
            record = _generate(user_id, links, repetition, name)
            records.append(record)
            print(
                f"  [{name}] status={record.get('http_status')} "
                f"elapsed_ms={record.get('elapsed_ms')} warnings={record.get('warnings')}"
            )

        # 동일 Source로 먼저 KG를 만든 뒤 즉시 갱신한다.
        unchanged_user_id = args.user_id_base + 10_000 + repetition
        unchanged_links = [notion_url, github_url]
        baseline = _generate(
            unchanged_user_id,
            unchanged_links,
            repetition,
            "update-unchanged-baseline",
        )
        baseline_hashes = _source_hashes(unchanged_links)
        unchanged = _update(
            unchanged_user_id,
            unchanged_links,
            repetition,
            "update-unchanged",
        )
        post_update_hashes = _source_hashes(unchanged_links)
        unchanged.update(
            {
                "baseline_http_status": baseline.get("http_status"),
                "baseline_knowledge_graph_version": baseline.get("knowledge_graph_version"),
                "source_changed_during_update": baseline_hashes != post_update_hashes,
                "graph_b_call_count": None,
                "graph_b_call_count_note": (
                    "API 응답에는 내부 LLM 호출 횟수가 없어 LangSmith에서 확인 필요"
                ),
            }
        )
        records.extend((baseline, unchanged))
        print(
            f"  [update-unchanged] status={unchanged.get('http_status')} "
            f"elapsed_ms={unchanged.get('elapsed_ms')} "
            f"kg_version={unchanged.get('knowledge_graph_version')}"
        )

        if args.include_changed_update:
            changed_user_id = args.user_id_base + 20_000 + repetition
            links = [notion_url, github_url]
            before_hashes = _source_hashes(links)
            changed_baseline = _generate(
                changed_user_id, links, repetition, "update-changed-baseline"
            )
            print(
                "  공개 Notion 또는 GitHub Source 내용을 수정한 뒤 Enter를 누르세요 "
                "(수정하지 않으면 이 반복은 변경 갱신으로 기록되지 않습니다)."
            )
            input()
            after_hashes = _source_hashes(links)
            changed_urls = [
                url for url in links if before_hashes.get(url) != after_hashes.get(url)
            ]
            if changed_urls:
                changed = _update(
                    changed_user_id, links, repetition, "update-changed"
                )
                changed["changed_source_urls"] = changed_urls
                changed["baseline_http_status"] = changed_baseline.get("http_status")
                changed["baseline_knowledge_graph_version"] = changed_baseline.get(
                    "knowledge_graph_version"
                )
                changed["graph_b_call_count"] = None
                records.append(changed)
            else:
                records.append(
                    {
                        "experiment": "source-timing",
                        "scenario": "update-changed",
                        "model": settings.SOURCE_TIMING_MODEL,
                        "repetition": repetition,
                        "user_id": changed_user_id,
                        "source_changed": False,
                        "skipped_reason": "입력한 Source 내용의 해시가 baseline과 같습니다.",
                    }
                )

    if args.skip_standalone_fetch:
        records = [item for item in records if item.get("scenario") != "standalone-source-fetch"]
    raw_file, summary_file = save_results(
        records,
        experiment="experiment-3-source-timing",
        output_dir=args.output_dir,
        group_keys=("scenario", "source_url"),
    )
    print(f"원시 결과: {raw_file}")
    print(f"집계 결과: {summary_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
