"""Activities 블록 생성 규칙"""

from textwrap import dedent

ACTIVITIES_PROMPT = dedent(
    """
    activities는 KG의 Activity Entity만 사용하며, profile 값만으로 항목을 만들지 않는다.
    organization은 연결된 Organization.name을 우선 사용한다.
    기관명이 없으면 표시명으로 충분한 Activity.name을 사용하고, 둘 다 불충분하면 항목을 생략한다.
    organization에 국가·도시를 덧붙이거나 저장소 위치로 소속 기관을 추론하지 않는다.

    role은 해당 Activity의 KG role fact만 사용한다.
    확인된 기수·소속 부문·팀·직책·활동 내 역할명을 간결하게 표시한다.
    여러 role fact는 쉼표로 구분하고, 근거가 없으면 null을 사용한다.
    kind는 확인된 club, volunteer, program, talk만 사용하고, 알 수 없으면 null을 사용한다.
    description은 해당 Activity의 entity evidence와 Fact·Relation을 근거로 작성한다.
    수행 내용·대상·주제·산출물·성과 등 role에 없는 부가 정보만 담는다.
    role을 그대로 나열하거나 다른 말로 반복하지 않는다.
    역할 외 설명 근거가 없으면 description은 null로 둔다.
    description은 간결한 명사형·이력서 문체를 사용한다.
    서로 다른 수행 내용은 짧은 '•' 항목으로 나누고, 근거가 적으면 늘리지 않는다.
    
    근거 없는 성과·기술·수치·기관을 추가하거나 다른 Activity·Work Entity의 evidence를 섞지 않는다.
    날짜는 확인된 기간만 YYYY 또는 YYYY.MM 형식으로 쓰고, 모르면 null을 사용한다.
    endDate의 Present는 KG에서 isCurrent=true가 확인될 때만 사용한다.
    서로 다른 Activity Entity는 별도 항목으로 유지하고, 같은 Entity는 한 번만 반환한다.

    역할과 설명 예시:
    - role fact '영상팀', evidence '숏츠·롱폼 영상 제작'
      role: '영상팀' / description: '• 숏츠·롱폼 영상 제작'
    - role fact '멘토링', evidence '비이공계 학생 대상 파이썬·데이터 분석 기초 멘토링'
      role: '멘토링' / description: '• 비이공계 학생 대상 파이썬·데이터 분석 기초'
    - role fact '9기', 활동 설명 근거는 기수·소속뿐
      role: '9기' / description: null
    """
).strip()
