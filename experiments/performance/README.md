# APolo 성능 실험

세 실험은 별도 스크립트로 실행한다. 반복 횟수는 기본 3회이며, 기본 입력 Source는 공개 Notion 포트폴리오와 GitHub 프로필이다.

## 공통 설정

주소·프로필·반복 횟수·timeout·AI API 주소는 [`settings.py`](./settings.py)에서 바꾼다. 환경변수 `APOLO_PERF_NOTION_URL`, `APOLO_PERF_GITHUB_URL`, `APOLO_PERF_API_BASE_URL`, `APOLO_PERF_KG_EFFECT_API_URL`, `APOLO_PERF_SOURCE_TIMING_API_URL`, `APOLO_PERF_REPETITIONS`, `APOLO_PERF_USER_ID_BASE`로도 덮어쓸 수 있다.

```python
NOTION_URL = "https://hyper-breakfast-e73.notion.site/Portfolio-Miji-Kim-3abfbcc778da80ebaf4cdf8226cae3cf?source=copy_link"
GITHUB_URL = "https://github.com/miji0"
```

모델 선정 실험의 후보는 `gpt-6-luna`, `gpt-6-sol`, `gpt-6.1-sol`, `gpt-5.6-luna`다. 실험 1만 네 모델을 비교하고, 실험 2의 Direct LLM 및 실험 3에서 공통으로 사용하는 모델은 `gpt-6-luna`다. 요청 본문이 모델을 선택하지 않고 AI 서버의 `APOLO_EXTRACTION_MODEL` 설정을 사용하므로, 모델 비교용 서버 주소를 `MODEL_ENDPOINTS`에 연결한다. 기본 포트는 `8101`–`8104`이며 공통 Luna 서버의 기본 포트는 `8101`이다.

각 모델 서버는 별도 터미널에서 띄운다. 모든 프로세스는 프로젝트 `.env`의 같은 DB·API 키를 사용할 수 있다.

```bash
APOLO_EXTRACTION_MODEL=gpt-6-luna PYTHONPATH=src .venv/bin/uvicorn apolo.api:app --host 127.0.0.1 --port 8101
APOLO_EXTRACTION_MODEL=gpt-6-sol PYTHONPATH=src .venv/bin/uvicorn apolo.api:app --host 127.0.0.1 --port 8102
APOLO_EXTRACTION_MODEL=gpt-6.1-sol PYTHONPATH=src .venv/bin/uvicorn apolo.api:app --host 127.0.0.1 --port 8103
APOLO_EXTRACTION_MODEL=gpt-5.6-luna PYTHONPATH=src .venv/bin/uvicorn apolo.api:app --host 127.0.0.1 --port 8104
```

실험 2와 3은 기본적으로 `http://127.0.0.1:8101`의 Luna 서버를 사용한다. 실험 2는 `KG_EFFECT_API_URL`을, 실험 3은 `SOURCE_TIMING_API_URL`을 사용하므로 별도로 실행 중인 서버 주소를 지정할 수 있다. `USER_ID_BASE`는 운영 사용자와 겹치지 않는 테스트 범위로 설정한다. 각 실행에서 새 ID를 쓰므로 같은 DB를 사용해도 테스트 KG가 겹치지 않는다.

## 실험 1: 모델 선정

같은 Profile·Notion·GitHub 입력을 각 모델 서버에 최소 3회 보내 처리 시간, 성공률, JSON 응답, 경고, 블록 커버리지를 기록한다.

```bash
PYTHONPATH=src .venv/bin/python experiments/performance/experiment_1_model_selection.py
# 한 모델만 실행
PYTHONPATH=src .venv/bin/python experiments/performance/experiment_1_model_selection.py --model gpt-6-sol
```

모델별 endpoint가 실제로 그 모델을 실행하는지 확인해야 한다. 스크립트는 모델 이름을 API에 전달하지 않으며, 잘못된 이름표를 방지하려고 한 번에 모든 모델을 실행할 때 중복 endpoint를 거부한다.

## 실험 2: KG 기반 생성 효과

같은 원문 Source와 Profile로 KG Pipeline(`/generate`)과 Direct LLM을 비교한다. 두 경로 모두 `gpt-6-luna`를 사용한다. KG Pipeline은 `KG_EFFECT_API_URL`이 가리키는 Luna 설정 AI 서버에서 실행하고, Direct LLM은 공개 Source Collector로 수집한 원문을 `OPENAI_API_KEY`를 사용해 Luna에 직접 전달한다.

```bash
PYTHONPATH=src .venv/bin/python experiments/performance/experiment_2_kg_effect.py
```

Direct LLM 결과의 `entityId`는 `direct-` 접두어를 가진 비교용 가상 ID이며 실제 KG ID가 아니다. 구조·중복 제목은 자동 기록하지만, 근거 없는 사실 수와 원문 충돌 보존은 결과 JSON의 `manual_review`에 사람이 채워야 한다. 원문 전체를 한 요청에 넣기 때문에 입력이 크면 TPM 제한으로 실패할 수 있으며 실패도 결과에 남긴다. 제공한 GitHub 프로필이 너무 크면 `GITHUB_URL`을 대표 저장소 URL로 바꾸거나 실험용 공개 Source를 줄인다.

## 실험 3: Source 수집·갱신 시간

Profile-only, Notion-only, GitHub-only, Notion+GitHub, 일부 Source 실패, 변경 없는 갱신을 실행한다. API 전체 시간과 Collector 개별 실행 시간을 따로 기록한다.

```bash
PYTHONPATH=src .venv/bin/python experiments/performance/experiment_3_source_timing.py
# 공개 Source를 직접 수정한 뒤 갱신까지 확인
PYTHONPATH=src .venv/bin/python experiments/performance/experiment_3_source_timing.py --include-changed-update
```

`--include-changed-update`는 각 반복의 baseline 뒤 대기한다. 공개 Notion 또는 GitHub 원문을 실제로 수정한 다음 Enter를 누른다. 원문 해시가 달라지지 않으면 해당 반복을 변경 갱신으로 기록하지 않는다. Collector 개별 측정을 건너뛰려면 `--skip-standalone-fetch`를 지정한다.

현재 `/update-content` 응답에는 Graph B 내부 호출 횟수나 Graph A/B 단계별 시간이 없다. 결과 JSON에 이 값은 자동으로 채워지지 않으므로 LangSmith에서 해당 요청의 Trace를 별도 확인해야 한다. 현재 `src/apolo/api.py`의 `/update-content` 구현은 Graph A 뒤 Graph B를 항상 호출하므로, 변경 없는 갱신에서 Graph B를 생략하는 기준은 현 코드로는 통과하지 않는다.

## 결과와 주의사항

원시 응답과 집계 JSON은 `experiments/performance/results/`에 저장된다. 결과 폴더는 Git에 추가하지 않는다. `graph_b_valid`는 API의 치명적 경고 코드가 없는지를 나타내는 대리 지표일 뿐, Fact 단위의 근거 정확도를 평가하지 않는다. 세부 의미 품질은 모델 간 동일한 출력과 Source 원문을 대조해 기록한다.

KG 저장 내용을 살펴볼 때는 기존 조회 스크립트를 쓸 수 있다.

```bash
PYTHONPATH=src .venv/bin/python experiments/performance/inspect_kg.py --user-id 990101
```
