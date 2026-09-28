"""Experience 블록 생성 규칙"""

from textwrap import dedent

EXPERIENCE_PROMPT = dedent(
    """
    experience 블록은 Experience Entity만 사용한다.
    experience의 organization은 profile.company 또는 연결된 Organization.name만 사용한다.
    experience 기관을 모르면 organization은 null로 두고 소속을 추론하지 않는다.
    experience의 role은 KG의 role fact만 사용하고, 근거가 없으면 null로 둔다.
    experience의 kind는 확인된 KG 값이 fulltime, contract, intern, research일 때만 사용한다.
    experience의 description은 source와 KG에 근거한 짧은 업무·성과 요약만 작성한다.
    experience에 근거 없는 성과·기술·수치·기관을 추가하지 않는다.
    experience 날짜는 확인된 기간만 YYYY 또는 YYYY.MM으로 출력하고 모르면 null을 넣는다.
    experience의 endDate에 Present는 KG에서 현재 재직(isCurrent=true)이 확인될 때만 사용한다.
    """
).strip()
