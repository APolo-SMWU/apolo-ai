"""About 블록 생성 규칙"""

from textwrap import dedent

_ABOUT_FEWSHOT = """
[예시 1: 독립된 사용자]
입력 KG 사실:
- Person.role: Professor
- Person --hasExperience--> Experience
- Experience.role: 조교수
- Experience.department: 인공지능학과
- Experience.isCurrent: true
- Experience --atOrganization--> Organization
- Organization.name: 연세대학교
- Person --participatedIn--> Work 1
- Work 1.title: 컴퓨터 비전 기반 이미지 분류 연구
- Work 1.kind: publication
- Person --participatedIn--> Work 2
- Work 2.title: 멀티모달 학습을 활용한 시각·언어 모델
- Work 2.kind: publication
- Work 2 --usesSkill--> Skill
- Skill.name: PyTorch

출력:
연세대학교 인공지능학과 조교수로 재직 중입니다. 주요 연구 분야는 컴퓨터 비전과 멀티모달 학습입니다.

[예시 2: 독립된 사용자]
입력 KG 사실:
- Person.role: Professor
- Person --hasEducation--> Education 1
- Education 1.degree: 학사; Education 1.major: 수학; Education 1.isCurrent: false
- Education 1 --atOrganization--> Organization: 연세대학교
- Person --hasEducation--> Education 2
- Education 2.degree: 석사; Education 2.major: 컴퓨터공학; Education 2.isCurrent: false
- Education 2 --atOrganization--> Organization: 서울대학교
- Person --hasEducation--> Education 3
- Education 3.degree: 박사; Education 3.major: 컴퓨터과학; Education 3.isCurrent: false
- Education 3 --atOrganization--> Organization: 일리노이 대학교 어바나-샴페인(UIUC)
- Person --hasExperience--> Experience
- Experience.role: 박사후 연구원
- Experience.department: 컴퓨터과학과
- Experience.isCurrent: false
- Experience --atOrganization--> Organization: 프린스턴 대학교
- Person --participatedIn--> Work 1
- Work 1.title: 모바일 컴퓨팅 시스템의 성능 및 신뢰성 연구
- Work 1.kind: publication
- Person --participatedIn--> Work 2
- Work 2.title: 프로그래밍 언어를 활용한 모바일 시스템 검증
- Work 2.kind: publication
- Person --participatedIn--> Work 3
- Work 3.title: 소프트웨어 공학 기반 시스템 안정성 개선
- Work 3.kind: project

출력:
연세대학교에서 수학 학사, 서울대학교에서 컴퓨터공학 석사, 일리노이 대학교 어바나-샴페인(UIUC)에서 컴퓨터과학 박사 학위를 취득했습니다.
프린스턴 대학교 컴퓨터과학과에서 박사후 연구원으로 근무했습니다. 연구 주제는 주로 모바일 컴퓨팅, 프로그래밍 언어, 소프트웨어 공학입니다.

[예시 3: 독립된 사용자]
입력 KG 사실:
- Person.role: Student
- Person --hasEducation--> Education
- Education.major: 통계학; Education.major: 소프트웨어융합학
- Education.isCurrent: true
- Education --atOrganization--> Organization
- Organization.name: 숙명여자대학교
- Person --hasExperience--> Experience
- Experience.role: LLM 애플리케이션 및 검색(RAG) 개발 실무
- Person --participatedIn--> Work 1
- Work 1.title: 문서 검색을 위한 RAG 애플리케이션 개발
- Work 1.kind: project
- Work 1 --usesSkill--> Skill 1
- Skill 1.name: Python
- Person --participatedIn--> Work 2
- Work 2.title: LLM 기반 질의응답 서비스 개발
- Work 2.kind: project
- Work 2 --usesSkill--> Skill 2
- Skill 2.name: LangChain

출력:
숙명여자대학교에서 통계학과 소프트웨어융합학을 복수 전공하고 있습니다.
LLM·RAG 기반 검색 애플리케이션을 개발해왔으며, 생성형 AI와 정보 검색에 관심을 두고 있습니다.

[예시 4: 독립된 사용자]
입력 KG 사실:
- Person --participatedIn--> Work 1
- Work 1.title: 네트워크 트래픽 이상 탐지 연구
- Work 1.kind: publication
- Work 1 --usesSkill--> Skill 1
- Skill 1.name: Python
- Person --participatedIn--> Work 2
- Work 2.title: 자동차 시스템 침입 탐지
- Work 2.kind: project
- Work 2 --usesSkill--> Skill 2
- Skill 2.name: scikit-learn
- Person --participatedIn--> Work 3
- Work 3.title: 웹·봇 활동 분석을 통한 보안 위협 탐지
- Work 3.kind: publication
- Person --participatedIn--> Work 4
- Work 4.title: 신뢰할 수 있는 머신러닝 기반 AI 보안
- Work 4.kind: project

출력:
AI 보안, 이상 탐지, 침입 탐지를 중심으로 연구해왔습니다.
네트워크 트래픽·자동차 시스템·웹 활동의 보안 위협 탐지에 주력하고 있습니다.

[예시 5: 독립된 사용자]
입력 KG 사실:
- Person.role: Professional
- Person --hasExperience--> Experience
- Experience.role: 백엔드 개발자
- Experience.kind: fulltime
- Experience.isCurrent: true
- Experience.start: 2021-02
- Person --participatedIn--> Work 1
- Work 1.title: 대규모 트래픽 처리
- Work 1.role: 백엔드 개발
- Work 1.kind: project
- Person --participatedIn--> Work 2
- Work 2.title: Spring 기반 아키텍처 리팩토링
- Work 2.role: 주도
- Work 2.kind: project
- Work 2 --usesSkill--> Skill
- Skill.name: Spring

출력:
현재 백엔드 개발자로 근무하며 대규모 트래픽 처리 프로젝트를 수행했습니다.
Spring 기반 아키텍처 리팩토링을 주도한 경험이 있습니다.
""".strip()

ABOUT_PROMPT = dedent(
    f"""
    about 블록은 항상 하나 반환한다.
    about 블록에는 description 필드만 포함한다.
    description은 KG의 Person, Education, Experience, Activity, Work, Credential, Skill 사실을 바탕으로 1~3개의 자연스러운 한국어 문장으로 작성한다.
    별도의 관심 분야 Fact가 없어도 KG 전반을 살펴 반복되거나 서로 뒷받침하는 주제를 관심 키워드로 종합할 수 있다.
    전공, 경력·활동의 역할과 소속, Work 제목 및 종류, 그 맥락에 연결된 Skill을 함께 살펴 주제를 도출한다.
    Skill은 대개 도구·기술이므로 단일 Skill만으로 관심 분야를 추론하지 않는다. 관련 Work·Experience·Activity의 주제를 보조하는 근거로만 활용한다.
    주제 근거가 약하거나 한 번만 나타나는 경우 관심 분야로 단정하지 말고 해당 학력·경력·프로젝트 사실만 서술한다.
    분석 과정을 설명하지 않는다. 'KG에서 반복적으로 나타납니다', '주요 주제로 파악됩니다'처럼 발견 사실을 보고하는 표현 대신, 본인이 직접 소개하듯 연구·관심·전문 분야를 자연스럽고 단정적으로 서술한다.
    현재 소속이나 전공이 KG에서 확인되면 우선 소개한다. 확인되지 않으면 근거가 있는 경력·활동·작업부터 서술한다.
    이름은 포함하지 않는다.
    KG에 없는 경력, 소속, 역할, 성과, 도구, 수치, 인물, URL을 추가하거나 추론하지 않는다. 여러 KG 사실을 요약한 관심 키워드는 예외적으로 도출할 수 있다.
    불필요한 수식어와 반복 표현을 사용하지 않는다.
    근거가 충분하지 않으면 description은 빈 문자열로 둔다.
    description에는 마크다운 문법, 링크, 목록 기호를 사용하지 않는다.

    Few-shot 출력 예시:
    {_ABOUT_FEWSHOT}
    각 예시는 서로 다른 독립된 사용자다. 예시 간 사실을 합치지 않는다.
    예시는 문장 구성 방식만 참고하고, 현재 KG에 없는 사실은 복사하거나 추가하지 않는다.
    """
).strip()
