"""About 블록 생성 규칙"""

from textwrap import dedent

_ABOUT_FEWSHOT = (
    "인공지능학과 조교수로서 연구와 교육을 수행하고 있습니다. "
    "이전에는 연세대학교 컴퓨터과학과에서 박사후연구원으로 근무했으며, "
    "컴퓨터 비전과 멀티모달 학습에 관심을 두고 있습니다."
)

ABOUT_PROMPT = dedent(
    f"""
    about 블록은 항상 하나 반환한다.
    about 블록에는 description 필드만 포함한다.
    description은 KG의 Person, Education, Experience, Activity, Work, Credential, Skill 사실을
    종합한 한국어 서술문으로 작성한다.
    KG에 없는 경력, 소속, 역할, 성과, 기술, 수치, 인물, URL을 추가하거나 추론하지 않는다.
    근거가 충분하지 않으면 description은 빈 문자열로 둔다.
    description에는 마크다운 문법, 링크, 목록 기호를 사용하지 않는다.

    Few-shot 출력 예시:
    {_ABOUT_FEWSHOT}
    위 문장은 문체와 정보 연결 방식만 보여주는 예시이며, 현재 KG에 없는 사실은
    복사하거나 추가하지 않는다.
    """
).strip()
