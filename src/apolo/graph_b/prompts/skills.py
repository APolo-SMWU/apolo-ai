"""Skills 블록 생성 규칙"""

from textwrap import dedent

from apolo.graph_b.skill_categories import SKILL_CATEGORIES, SKILL_CATEGORY_CATALOG

SKILLS_PROMPT = dedent(
    f"""
    Skills 블록에는 Person.hasSkill 또는 Work·Experience.usesSkill로 연결된 KG Skill만 사용한다.
    목록은 선택지가 아니라 분류 사전이다. 사용자가 실제로 다룬 것이 근거로 확인된 기술만 표시하고,
    목록에 없는 기술도 근거가 있으면 적절한 카테고리에 포함한다.
    근거 없이 관련 기술을 추가하지 않는다. 예: Next.js만 확인되면 React를 추가하지 않고,
    AWS만 확인되면 EC2·S3를 추가하지 않는다.

    사용할 category는 다음 표준 목록을 사용한다. 순서도 이 목록을 따른다.
    {", ".join(SKILL_CATEGORIES)}.

    아래 목록은 기술명을 표준 카테고리에 배치하기 위한 참고 사전이다.
    {SKILL_CATEGORY_CATALOG}
    - {SKILL_CATEGORIES[-1]}: 확인된 기술이 어느 표준 카테고리에도 맞지 않을 때만 사용한다.

    여러 카테고리에 등장하는 기술은 실제 사용 맥락에 맞는 곳 한 군데에만 표시한다.
    예: Selenium은 테스트 경험이면 테스트 & 품질, 데이터 수집 경험이면 데이터 수집 & 처리.
    Redis, GitHub처럼 여러 카테고리에 있는 기술도 같은 포트폴리오에서 한 번만 표시한다.
    기술명 표기를 통일한다. 예: ReactJS → React, NodeJS → Node.js, Postgres → PostgreSQL.
    Spring과 Spring Boot, Java와 JavaScript, React와 React Native처럼 다른 기술은 구분한다.
    모델 버전명(GPT-4o, T5 등), 기술 분야명(NLP, Computer Vision), 프로젝트 주제는 표시하지 않는다.
    웹 크롤링·데이터 전처리·시각화처럼 수행 작업이나 프로젝트 키워드인 Skill도 제외한다.
    연구 알고리즘·공격 기법·모델명은 도구가 아니므로 생략한다.
    분류 사전에 있더라도 도구가 아닌 작업·주제·연구 방법·알고리즘은 표시하지 않는다.

    기본은 각 KG Skill의 개별 표시다. 같은 플랫폼의 여러 서비스가 모두 근거로 확인된 경우에만
    대표 플랫폼명 하나로 묶을 수 있다. 예: Azure, Azure AI Search, Microsoft Azure PaaS,
    Azure Container Instances처럼 둘 이상이 확인되면 Azure 하나로 표시하고
    entityIds에 구성 Skill ID를 모두 보존한다.
    플랫폼만 확인된 경우 서비스명을 추론하지 않는다. 프레임워크·라이브러리 등 서로 다른 기술은
    같은 생태계라는 이유만으로 플랫폼명으로 묶지 않는다.
    표기만 다른 동의어를 하나로 정규화하면 해당 항목의 entityIds에 구성 KG Skill ID를 모두 보존한다.
    각 item은 name과 entityIds를 반환한다. 같은 기술은 카테고리와 관계없이 한 번만 표시한다.
    works.skills에는 Work의 usesSkill로 연결된 각 Skill.name을 그대로 보존한다.
    빈 category와 빈 Skills 블록은 반환하지 않는다.
    """
).strip()
