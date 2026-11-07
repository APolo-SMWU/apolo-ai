"""Skill 추출·kind·category 규칙"""

from textwrap import dedent

from apolo.ontology.skill_categories import SKILL_CATEGORY_CATALOG

_SKILL_CATEGORY_GUIDE = "\n".join(
    f"- {category} ({label}): {examples}" if examples else f"- {category} ({label})"
    for category, (label, examples) in SKILL_CATEGORY_CATALOG.items()
)

SKILL_PROMPT = dedent(
    """
    ## Skill
    Work·Experience에서 실제 사용이 확인되면 도구가 아니어도 Skill로 추출하고
    usesSkill로 연결한다. kind와 category는 Skill의 추출 여부나 관계를 바꾸지 않는다.
    다음은 Skill로 만들지 않는다. 단, 그룹 사전에 있는 이름은 Skill로 만든다.
    - 라이브러리·프레임워크의 클래스·함수·훅·모듈·설정 이름. 해당 라이브러리 Skill 하나로 본다.
      예: useEffect → React, DataFrame → pandas
    - 데이터 형식(JSON, CSV, YAML, XML)과 언어 표준 라이브러리 모듈(os, datetime, collections)

    ### kind
    모든 Skill에 kind fact를 정확히 하나 붙인다.
    - tool: 이름 그대로 설치·호출·작성하는 구체적인 기술. 언어, 쿼리 언어, 프레임워크,
      라이브러리, 데이터베이스, 클라우드 서비스, 개발·협업 도구, API 규격·프로토콜·인증 표준.
    - method: 따르는 기법·방법론·알고리즘·분석 방법·설계 방식.
    - model: 이름이 있는 특정 학습 모델·체크포인트. 예: BERT, Llama 3, Whisper
      알고리즘·아키텍처 종류(SVM, CNN, 결정 트리)는 model이 아니라 method다.
    - domain: 분야·주제·응용 영역.
    - other: 위 넷 중 어디에도 맞지 않을 때만 사용한다.
    설치·호출·작성하는 대상이면 tool, 따르는 방식이면 method로 판단한다.
    REST API, GraphQL, gRPC, OAuth 2.0, JWT처럼 구현하거나 호출하는 규격은 tool이다.
    모델을 제공하는 API·SDK는 tool이고, 그것으로 호출한 특정 모델명은 model이다.
    kind와 category fact의 evidence_refs에는 해당 Skill의 name fact와 같은 근거를 쓴다.

    ### category
    category 값은 아래 그룹 id만 사용한다. 표시 이름을 값으로 쓰지 않는다.
    - kind=tool: category를 하나 이상 붙인다. 맞는 그룹이 없으면 other를 쓴다.
    - kind=method, model, domain, other: category를 붙이지 않는다.
    그룹 사전은 화이트리스트가 아니다. 사전에 없는 기술도 성격이 맞는 그룹에 넣는다.
    사전에 같은 기술이 있으면 Skill.name은 사전의 표기를 쓴다.
    예: Postgres → PostgreSQL, ReactJS → React, sklearn → scikit-learn.
    버전 번호는 Skill.name에 붙이지 않는다. 숫자가 이름의 일부인 경우(ROS 2, OAuth 2.0)는 유지한다.
    같은 Skill을 서로 다른 용도로 쓴 근거가 있을 때만 category를 여러 개 붙인다.
    예: Selenium을 테스트와 데이터 수집에 모두 썼다면 testing_quality와 data_collection_processing.

    그룹 사전 (id (표시 이름): 예시)
    {category_guide}

    ### 예시
    원문: "Spring Boot와 JPA로 REST API를 만들고 JWT로 인증을 구현했다.
    Redis로 세션을 캐싱하고 GitHub Actions로 배포를 자동화했다."
    - Spring Boot / kind=tool / category=backend
    - JPA / kind=tool / category=orm_data_access
    - REST API / kind=tool / category=api_communication
    - JWT / kind=tool / category=auth_security
    - Redis / kind=tool / category=cache_search
    - GitHub Actions / kind=tool / category=ci_cd

    원문: "헬스케어 문서를 BERT로 분류하고 K-means로 군집을 나눴다.
    추천 화면은 A/B 테스트로 검증했고, 스마트 컨트랙트는 Hardhat으로 테스트했다."
    - BERT / kind=model / category 없음
    - 헬스케어 / kind=domain / category 없음
    - K-means / kind=method / category 없음
    - A/B Testing / kind=method / category 없음
    - Hardhat / kind=tool / category=other (맞는 그룹이 없는 도구)

    원문: "ReactJS 18의 useEffect로 화면을 갱신하고 tailwindcss로 스타일을 입혔다.
    Node v20 서버에서 postgres와 sklearn 모델을 연동했고 설정은 YAML로 관리했다."
    - React / kind=tool / category=frontend (사전 표기, 버전 제외)
    - Tailwind CSS / kind=tool / category=web_markup_styling
    - Node.js / kind=tool / category=backend
    - PostgreSQL / kind=tool / category=database
    - scikit-learn / kind=tool / category=machine_learning
    useEffect는 React의 구성요소이고 YAML은 데이터 형식이므로 Skill로 만들지 않는다.
    """
).strip().replace("{category_guide}", _SKILL_CATEGORY_GUIDE)
