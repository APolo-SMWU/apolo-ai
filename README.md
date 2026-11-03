# APolo AI

APolo의 AI 서비스. GitHub, Public Notion Page, 사용자 프로필(`myPageProfile`)에 흩어진 개인 정보를 Personal Ontology 기반 Personal Knowledge Graph로 구조화하고, 온라인 명함·포트폴리오·CV 콘텐츠 생성에 재사용하는 것을 목표로 한다.

AI 처리는 두 가지 LangGraph workflow로 구성된다.

- **Graph A:** 소스 수집 → 추출·정규화 → Entity / Fact / Relation / Evidence 생성 → KG 저장·갱신
- **Graph B:** KG에서 목적에 맞는 정보 선별 → 콘텐츠 생성 → 검증 → JSON 반환

콘텐츠 생성·갱신 시 Backend(Express)가 별도 AI 서버(FastAPI)를 내부 API로 호출한다. Frontend는 AI 서버를 직접 호출하지 않으며, Backend가 AI 결과를 검증하고 최종 콘텐츠를 저장한다.

## 브랜치 설명

| 순서 | 브랜치 | 주요 기능 |
|---|---|---|
| 1 | `feat/profile-seed-kg` | 프로필·KG 모델과 온톨로지 규칙, Seed 변환·검증, DB 저장·조회·중복 처리·프로필 수정 반영 |
| 2 | `feat/generate-portfolio` | 프로필 Seed → 학력·경력 블록 → `/generate` → Backend 연결 |
| 3 | `feat/source-collection` | Source·Snapshot·Evidence 저장 구조, GitHub·Public Notion 수집 |
| 4 | `feat/knowledge-construction` | LLM·LangSmith 연결, 사실 후보 추출·검증·병합·KG 저장, 요구사항 속 사용자 사실 처리, Graph A 연결 |
| 5 | `feat/content-generation` | KG 정보 선별, 콘텐츠 생성·근거·형식 검증, Graph B 연결 |
| 6 | `feat/update-content` | Source 변경 감지, KG 수정·삭제 반영, 콘텐츠 갱신·사용자 편집 보호, Backend 연결 |
| 7 | `chore/deploy-ai` | 통합 평가·배포 전 점검, Lightsail 배포 설정 |

### UPDATE CONTENT 연결 시 필수 정리

- Backend의 기존 `fetchSourceUpdates()`가 담당하는 외부 수집·해시 비교·스냅샷 관리를 AI로 이전한다. 두 서버에서 중복 수행하지 않는다.
- Backend는 소유권 확인, 링크·갱신 요청 전달, 생성 결과 저장을 담당한다.
- Backend의 `Portfolio.sourceSnapshots` 필드는 프론트 사용처와 응답 호환성을 확인한 뒤 유지·제거 여부를 조율한다. 임의로 삭제하지 않는다.
- 완료 기준: 갱신 요청에서 AI만 수집·변경 감지를 수행하고, Backend 연결 및 기존 프론트 응답 호환성을 검증한다.

## 개발 환경

- Python 3.12 이상 (`.python-version`: 3.12)
- 의존성 관리: uv (`pyproject.toml`, `uv.lock`)
- 기본 의존성: FastAPI, Uvicorn, Pydantic, LangGraph, python-dotenv
- 개발 도구: pytest, Ruff
- 패키지 위치: `src/apolo`, 테스트 위치: `tests`

```bash
uv sync --locked
uv run ruff check src tests
uv run pytest
```

## PDF·Word 첨부 연결

Backend의 `POST /portfolios/generate`는 기존 multipart `attachments` 필드로 PDF·DOCX를 받는다.
최대 5개, 파일당 10MB이며 PDF는 텍스트가 있는 문서 30쪽까지 지원한다(OCR 미지원).
링크 없이 문서만 첨부한 생성도 지원한다. JPG·PNG는 기존처럼 첨부로 저장하며 AI에서 읽지 않는다.

Backend는 원본을 비공개 S3에 저장한 뒤 `/generate`와 `/update-content`에 아래 참조를 전달한다.
`attachments` 생략·빈 목록은 기존 JSON 요청과 호환된다.

```json
{
  "attachments": [{
    "fileName": "resume.docx",
    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "sourceUrl": "portfolios/요청UUID/attachments/파일UUID.docx",
    "downloadUrl": "https://버킷.s3.ap-northeast-2.amazonaws.com/저장키?서명"
  }]
}
```

AI는 S3 원본을 크기 제한 안에서 내려받아 수집·항목별 분할·Graph A 저장을 수행하고,
이번 요청의 파일 Source를 Graph B 입력에 포함한다. 임시 다운로드 주소는 DB에 저장하지 않는다.
첨부 수집 실패는 파일명과 오류 코드로 경고하며 다른 소스 처리는 계속한다.

기존 008까지 적용된 DB에는 서비스 실행 전 `uv run python -m apolo.db.migrate_file_source`를
실행한다. `APOLO_TEST_DB=1 uv run pytest -q`는 실제 DB 통합 검증 후 테스트 변경을 롤백한다.
