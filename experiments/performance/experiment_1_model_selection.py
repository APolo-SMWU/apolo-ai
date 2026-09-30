"""실험 1: 같은 입력을 네 모델 서버에 보내 포트폴리오 생성 성능 비교."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import settings  # noqa: E402
from common import check_health, generate_payload, request_api, save_results  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="실험 1: LLM 모델 선정")
    parser.add_argument("--model", choices=settings.MODEL_IDS, help="한 모델만 실행")
    parser.add_argument("--repetitions", type=int, default=settings.REPETITIONS)
    parser.add_argument("--user-id-base", type=int, default=settings.USER_ID_BASE)
    parser.add_argument("--output-dir", default=settings.OUTPUT_DIR)
    args = parser.parse_args()

    if args.repetitions < 3:
        parser.error("repetitions는 최소 3이어야 합니다.")
    model_ids = [args.model] if args.model else list(settings.MODEL_IDS)
    endpoints = {model: settings.MODEL_ENDPOINTS[model].rstrip("/") for model in model_ids}
    if len(set(endpoints.values())) != len(endpoints):
        parser.error(
            "모델별 endpoint가 중복됩니다. API는 요청의 model 필드를 사용하지 않으므로 "
            "모델마다 실제 모델 설정이 다른 서버 주소를 지정해야 합니다."
        )
    try:
        for model_id, base_url in endpoints.items():
            check_health(base_url)
            print(f"[{model_id}] health=ok endpoint={base_url}")
    except RuntimeError as error:
        parser.error(str(error))

    records = []
    for model_index, model_id in enumerate(model_ids):
        base_url = endpoints[model_id]
        print(f"[{model_id}] endpoint={base_url}")
        for repetition in range(1, args.repetitions + 1):
            user_id = args.user_id_base + model_index * 10_000 + repetition
            payload = generate_payload(user_id, list(settings.SOURCE_URLS), settings)
            record = request_api(
                base_url=base_url,
                endpoint="/generate",
                payload=payload,
                timeout_seconds=settings.TIMEOUT_SECONDS,
                expected_blocks=settings.EXPECTED_BLOCK_TYPES,
            )
            record.update(
                {
                    "experiment": "model-selection",
                    "model": model_id,
                    "repetition": repetition,
                    "source_count": len(settings.SOURCE_URLS),
                }
            )
            records.append(record)
            print(
                f"  run={repetition}/{args.repetitions} status={record.get('http_status')} "
                f"elapsed_ms={record.get('elapsed_ms')} warnings={record.get('warnings')}"
            )

    raw_file, summary_file = save_results(
        records,
        experiment="experiment-1-model-selection",
        output_dir=args.output_dir,
        group_keys=("model",),
    )
    print(f"원시 결과: {raw_file}")
    print(f"집계 결과: {summary_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
