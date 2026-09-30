"""Activities 블록 생성 규칙"""

from textwrap import dedent

ACTIVITIES_PROMPT = dedent(
    """
    activities 블록은 Activity Entity만 사용하고 profile 값으로 활동을 만들지 않는다.
    activities의 organization은 연결된 Organization.name을 우선 사용한다.
    기관명이 없지만 Activity.name이 표시명으로 충분하면 Activity.name을 organization으로 사용한다.
    기관명과 활동명 모두 불충분하면 해당 activities item을 생략한다.
    organization에 국가·도시를 추가하거나 저장소 위치로 소속 기관을 추론하지 않는다.
    activities의 role은 KG의 role fact만 사용하고 근거가 없으면 null로 둔다.
    kind는 확인된 club, volunteer, program, talk만 사용하고 모르면 null로 둔다.
    activities의 description은 해당 Activity의 entity evidence와 Fact·Relation 근거로 실제 활동·업무를 구체적으로 요약한다.
    여러 역할이나 업무가 근거로 있으면 각각 짧은 '•' 항목으로 작성하고, 근거가 적으면 길이를 억지로 늘리지 않는다.
    한국어 description은 '~습니다' 문체보다 간결한 명사형·이력서 문체를 사용한다.
    activities에 근거 없는 성과·기술·수치·기관을 추가하지 않는다.
    다른 Activity 또는 Work Entity의 evidence를 섞지 않는다.
    activities 날짜는 확인된 기간만 YYYY 또는 YYYY.MM으로 출력하고 모르면 null을 넣는다.
    activities의 endDate에 Present는 KG에서 현재 활동(isCurrent=true)이 확인될 때만 사용한다.
    서로 다른 Activity Entity는 별도 item으로 유지하고 같은 Entity를 중복 반환하지 않는다.
    """
).strip()
