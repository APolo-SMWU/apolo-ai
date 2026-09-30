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
    works 블록은 Work Entity만 사용한다.
    works의 kind는 KG에서 확인된 project, opensource, publication 중 하나만 사용한다.
    kind를 확인할 수 없으면 해당 Work item을 만들지 않는다.
    works의 title은 Work의 title fact를 그대로 사용한다.
    works의 role은 Work의 role fact가 있을 때만 사용하고 근거가 없으면 null로 둔다.
    works의 skills는 usesSkill로 연결된 Skill.name만 사용하고 기술을 추론하지 않는다.
    works의 description은 해당 Work의 entity evidence와 Fact·Relation을 종합해 수행한 일과 기여를 구체적으로 작성한다.
    근거에 구체적인 대상·산출물·기술·방법·성과가 있으면 막연한 '프로젝트 개발'로 축약하지 말고 해당 내용을 보존한다.
    같은 Work의 서로 다른 기여는 각각 '•' 항목으로 나누고, 프로젝트의 핵심 업무와 결과가 빠지지 않도록 작성한다.
    description 길이를 인위적으로 제한하지 않는다. 단, 근거가 부족하면 내용을 추측하거나 분량을 채우지 않는다.
    한국어 description은 '~습니다', '~했습니다'로 끝내지 않고 간결한 명사형·이력서 문체로 작성한다.
    description을 뒷받침할 근거가 없으면 null을 사용한다.
    근거 없는 성과·기술·수치·역할·기관을 description에 추가하지 않는다.
    다른 Work 또는 Activity Entity의 evidence를 섞지 않는다.
    Few-shot description 예시:
    {_WORKS_DESCRIPTION_FEWSHOT}
    works의 links는 Work의 url fact만 label과 href로 변환한다.
    확인된 URL이 없으면 links는 빈 배열을 사용한다.
    AI가 URL이나 imageUrl을 새로 만들지 않는다.
    imageUrl은 제공된 근거에 명시된 이미지 URL만 사용한다.
    Experience Entity의 기관이나 저장소 URL만으로 별도 Work item을 만들지 않는다.
    개인·팀 프로젝트, 공개 저장소 기여, 학술 결과물은 확인된 kind에 따라 분류한다.
    같은 Work Entity는 한 번만 반환하고 서로 다른 Work Entity는 별도 item으로 유지한다.
    """
).strip()
