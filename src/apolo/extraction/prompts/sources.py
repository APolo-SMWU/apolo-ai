"""Source 형식별 원문 읽기 안내. 안내가 없는 형식은 공통 규칙만 쓴다"""

from textwrap import dedent

_FILE_PROMPT = dedent(
    """
    ## 파일 항목과 청크 문맥
    같은 항목의 이름·기간·역할·기술·설명이 여러 줄, 문단, 표 행에 나뉠 수 있다.
    글자 크기가 같거나 제목이 없어도 원문 순서와 배치 단서를 함께 읽는다.
    layout의 들여쓰기·줄 간격·빈 문단·제목·목록·표 정보는 약한 보조 단서다.
    배치나 section path만으로 같은 항목이라고 단정하거나 사실을 만들지 않는다.
    보조 문맥 locator의 원문은 다른 청크와 겹칠 수 있다. 이를 독립 항목으로
    반복 추출하지 말고 현재 본문 항목의 연결에 필요한 경우만 근거로 인용한다.
    서로 다른 항목의 기간·역할·기술을 섞지 말고 연결이 불확실하면 생략한다.
    """
).strip()

_NOTION_PROMPT = dedent(
    """
    ## Notion 페이지 재구성
    Notion은 페이지 전체를 순서대로 읽고 블록 하나씩 독립적으로 분류하지 않는다.
    Collector가 제공한 순서와 반복 레이아웃을 이용해 논리 항목을 재구성한다.
    제목·이름에 날짜, 기관, Tech Stack, My Role & Contributions, 업무·기여 설명 등 별도 블록의 정보를 연결한다.
    반복 라벨은 Entity로 만들지 말고 값만 현재 항목에 붙인다.
    다음 항목 제목이 나오면 연결 대상을 바꾸고, 서로 다른 항목의 정보를 섞지 않는다.
    'header', 'sub_header' 같은 블록 형식이나 section path만으로 의미·분류를 단정하지 않는다.
    section path는 약한 보조 문맥일 뿐 사실이나 근거 locator가 아니다.
    연결 대상이 확실하지 않은 정보는 생략한다.
    """
).strip()

SOURCE_PROMPTS: dict[str, str] = {"file": _FILE_PROMPT, "notion": _NOTION_PROMPT}
