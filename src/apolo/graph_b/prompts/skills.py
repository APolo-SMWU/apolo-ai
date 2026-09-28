"""Skills 블록 생성 규칙"""

from textwrap import dedent

SKILLS_PROMPT = dedent(
    """
    skills 블록은 KG의 Skill Entity만 사용한다.
    skills의 category는 Skill의 category fact를 그대로 사용한다.
    category fact가 없는 Skill은 표시하지 않고 카테고리를 추론하지 않는다.
    skills의 items는 Person hasSkill 또는 Work·Experience usesSkill로 연결된 Skill.name만 사용한다.
    KG에 없는 기술을 추가하거나 비슷한 기술명으로 바꾸지 않는다.
    하나의 Skill이 여러 category fact를 가지면 확인된 카테고리에만 표시한다.
    같은 category 안에서 같은 기술을 중복 표시하지 않는다.
    빈 category와 빈 skills 블록은 반환하지 않는다.
    """
).strip()
