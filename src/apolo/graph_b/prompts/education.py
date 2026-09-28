"""Education 블록 생성 규칙"""

from textwrap import dedent

EDUCATION_PROMPT = dedent(
    """
    education 블록은 Education Entity만 사용하고 description·kind 필드는 반환하지 않는다.
    education organization은 Organization.name만 사용하고 위치·국가는 추론하지 않는다.
    education의 role은 KG의 major를 사용하고, degree fact가 있을 때만 학위를 포함한다.
    education에 degree fact가 없으면 학위를 추론하지 않는다.
    education 날짜는 확인된 기간만 YYYY 또는 YYYY.MM으로 출력하고 모르면 null을 넣는다.
    education의 endDate에 Present는 KG에서 현재 재학(isCurrent=true)이 확인될 때만 사용한다.
    education 항목은 종료일·시작일 최신순으로 정렬하고 profile·source 충돌은 삭제하지 않는다.
    """
).strip()
