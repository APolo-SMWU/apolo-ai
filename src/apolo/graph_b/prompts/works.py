"""Works 블록 생성 규칙"""

from textwrap import dedent

WORKS_PROMPT = dedent(
    """
    works 블록은 Work Entity만 사용한다.
    works의 kind는 KG에서 확인된 project, opensource, publication 중 하나만 사용한다.
    kind를 확인할 수 없으면 해당 Work item을 만들지 않는다.
    works의 title은 Work의 title fact를 그대로 사용한다.
    works의 role은 Work의 role fact가 있을 때만 사용하고 근거가 없으면 null로 둔다.
    works의 skills는 usesSkill로 연결된 Skill.name만 사용하고 기술을 추론하지 않는다.
    works의 description은 제공된 source evidence와 KG 사실을 짧게 요약한다.
    description을 뒷받침할 근거가 없으면 null을 사용한다.
    근거 없는 성과·기술·수치·역할·기관을 description에 추가하지 않는다.
    works의 links는 Work의 url fact만 label과 href로 변환한다.
    확인된 URL이 없으면 links는 빈 배열을 사용한다.
    AI가 URL이나 imageUrl을 새로 만들지 않는다.
    imageUrl은 제공된 근거에 명시된 이미지 URL만 사용한다.
    Experience Entity의 기관이나 저장소 URL만으로 별도 Work item을 만들지 않는다.
    개인·팀 프로젝트, 공개 저장소 기여, 학술 결과물은 확인된 kind에 따라 분류한다.
    같은 Work Entity는 한 번만 반환하고 서로 다른 Work Entity는 별도 item으로 유지한다.
    """
).strip()
