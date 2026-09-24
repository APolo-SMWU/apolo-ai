# APolo AI

APolo의 AI 서비스. GitHub, Public Notion Page, 사용자 프로필(`myPageProfile`)에 흩어진 개인 정보를 Personal Ontology 기반 Personal Knowledge Graph로 구조화하고, 온라인 명함·포트폴리오·CV 콘텐츠 생성에 재사용하는 것을 목표로 한다.

AI 처리는 두 가지 LangGraph workflow로 구성된다.

- **Graph A:** 소스 수집 → 추출·정규화 → Entity / Fact / Relation / Evidence 생성 → KG 저장·갱신
- **Graph B:** KG에서 목적에 맞는 정보 선별 → 콘텐츠 생성 → 검증 → JSON 반환

콘텐츠 생성·갱신 시 Backend(Express)가 별도 AI 서버(FastAPI)를 내부 API로 호출한다. Frontend는 AI 서버를 직접 호출하지 않으며, Backend가 AI 결과를 검증하고 최종 콘텐츠를 저장한다.

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
