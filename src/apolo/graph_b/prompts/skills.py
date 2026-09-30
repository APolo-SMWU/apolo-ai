"""Skills 블록 생성 규칙"""

from textwrap import dedent

from apolo.graph_b.skill_categories import SKILL_CATEGORIES

SKILLS_PROMPT = dedent(
    f"""
    Skills 블록에는 Person.hasSkill 또는 Work·Experience.usesSkill로 연결된 KG Skill 중
    사용자가 실제로 다룬 구체적인 언어·프레임워크·라이브러리·플랫폼·도구만 표시한다.
    모델명, 기술 분야, 연구 알고리즘·방법, 프로젝트 주제는 제외한다.
    예: GPT-4o·T5, Computer Vision·NLP, RAG·GraphRAG·FGSM·PGD는 생략하고,
    PyTorch·FastAPI·PostgreSQL은 표시한다.

    category는 KG category fact에 의존하지 않고 Skill.name으로 표시 분류한다.
    사용할 수 있는 category: {", ".join(SKILL_CATEGORIES)}.
    - 프로그래밍 언어: Python, TypeScript, SQL, R 등
    - 프론트엔드·모바일: HTML/CSS, React, Android 등
    - 백엔드·API: FastAPI, REST, Flask 등
    - 데이터베이스: PostgreSQL, MySQL 등
    - AI·ML 도구: PyTorch, Transformers, LangGraph, FAISS 등 실제 도구·라이브러리
    - 데이터·시각화: Tableau, Pandas 등
    - 클라우드·인프라: Azure, AWS, Docker 등
    - 개발·자동화 도구: GitHub, Figma, Storybook, n8n 등
    위 분류에 맞지 않는 구체적인 기술만 {SKILL_CATEGORIES[-1]}로 표시한다.

    기본적으로 각 KG Skill을 개별 기술명으로 표시한다.
    같은 플랫폼에 속한 여러 서비스를 함께 보여줄 때만 플랫폼 대표명 하나로 묶는다.
    Azure PaaS·Azure Container Instances처럼 여러 Azure 서비스가 있으면 Azure로 묶을 수 있다.
    단순히 기술 생태계가 가깝거나 이름이 비슷하다는 이유로 기술들을 묶지 않는다.
    묶인 항목의 entityIds에는 구성하는 모든 KG Skill ID를 넣는다.
    이 묶음 규칙은 Skills 블록에만 적용한다. works.skills에는 Work의 usesSkill로 연결된
    각 Skill의 원래 KG 이름을 그대로 보존한다.

    각 item은 name과 entityIds를 반환한다. KG에 없는 기술을 추가하거나 근거 없는 플랫폼 그룹을
    만들지 않는다. 같은 category 안에서는 같은 표시 이름을 한 번만 반환한다.
    빈 category와 빈 Skills 블록은 반환하지 않는다.

    예:
    KG Skill: Azure PaaS(id=e1), Azure Container Instances(id=e2),
    Python(id=e3), TypeScript(id=e4), GPT-4o(id=e5)
    출력: 클라우드·인프라 → Azure(entityIds=[e1,e2]);
    프로그래밍 언어 → Python(entityIds=[e3]), TypeScript(entityIds=[e4]). GPT-4o는 제외한다.

    예:
    KG Skill: React(id=e1), Next.js(id=e2)
    출력: 프론트엔드·모바일 → React(entityIds=[e1]), Next.js(entityIds=[e2]).
    서로 관련된 기술이라도 개별 표시한다.
    """
).strip()
