"""Works 블록 생성 규칙"""

from textwrap import dedent

_WORKS_DESCRIPTION_FEWSHOT = dedent(
    """
    아래는 각각 서로 다른 Work의 독립적인 description 예시다.

    [예시 1]
    근거: 학습 및 평가용 뉴스 레이블링 데이터셋 구축
    description:
    • 학습·평가용 뉴스 레이블링 데이터셋 구축

    [예시 2]
    근거: 다단계 LLM 분류 시스템을 모델링해 성능 14% 개선
    description:
    • 다단계 LLM 분류 시스템 모델링 및 성능 14% 개선

    [예시 3]
    근거: 일별 지수 산출 및 키워드 추출 모듈 개발
    description:
    • 일별 지수 산출 및 키워드 추출 모듈 개발

    [예시 4]
    근거: react-hook-form의 watch와 trigger를 활용한 수동 유효성 검사로 이메일 중복 오류 UX 개선
    description:
    • react-hook-form의 watch·trigger 기반 수동 유효성 검사로 이메일 중복 오류 UX 개선

    [예시 5]
    근거: 반응형 UI 디자인 및 프론트엔드 개발을 단독으로 진행
    description:
    • 반응형 UI 디자인 및 프론트엔드 개발 단독 수행
    """
).strip()

WORKS_PROMPT = dedent(
    f"""
    [대상과 분류]
    - 사용자가 참여한 Work Entity만 works 항목으로 반환한다.
    - kind는 해당 Work의 KG fact에 있는 project, opensource, publication 중 하나만 사용한다.
    - kind를 확인할 수 없으면 해당 Work를 생략한다.
    - Experience Entity의 기관이나 저장소 URL만으로 Work 항목을 만들지 않는다.
    - 같은 Work Entity는 한 번만 반환하고, 서로 다른 Work Entity는 각각 유지한다.

    [필드]
    - title은 해당 Work의 title fact를 그대로 사용한다.
    - role은 해당 Work의 role fact가 있을 때만 사용하고, 없으면 null로 둔다.
    - skills는 usesSkill로 연결된 Skill.name만 사용한다. 기술을 추론하거나 추가하지 않는다.

    [Description]
    - 해당 Work의 entity evidence와 Fact·Relation을 종합해 수행 내용과 기여를 구체적으로 작성한다.
    - 근거에 대상·산출물·기술·방법·성과가 있으면 빠뜨리지 않는다.
    - 구체적인 내용을 '프로젝트 개발' 같은 막연한 표현으로 축약하지 않는다.
    - 서로 다른 기여는 각각 '•' 항목으로 나누고 핵심 업무와 결과를 담는다.
    - 한국어는 '~습니다', '~했습니다' 대신 간결한 명사형·이력서 문체로 작성한다.
    - description 길이를 인위적으로 제한하지 않는다.
    - 근거 밖의 성과·기술·수치·역할·기관을 추측하거나 분량을 채우지 않는다.
    - 설명 근거가 없으면 null을 사용한다.
    - 다른 Work나 Activity Entity의 evidence를 섞지 않는다.
    Few-shot 예시:
    {_WORKS_DESCRIPTION_FEWSHOT}

    [Links와 이미지]
    - links는 Work의 url fact만 사용하고, 확인된 URL이 없으면 빈 배열을 반환한다.
    - URL이나 imageUrl을 추측해 만들지 않는다.
    - imageUrl은 해당 Work의 근거에 명시된 이미지 URL만 사용한다.
    """
).strip()
