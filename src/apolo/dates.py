"""날짜 표기 규칙. KG는 ISO(2024, 2024-03, 2024-03-15), 출력 블록은 2024·2024.03·Present"""

import re

PRESENT = "Present"
# 출력 블록의 연·월 형식. contracts의 날짜 패턴이 이 값으로 만들어진다.
OUTPUT_DATE = r"[0-9]{4}(?:\.(?:0[1-9]|1[0-2]))?"

# 구분자만 다른 날짜 표기(2024.3, 2024/03/05, 2024년 3월 등). 네 자리 연도와 구분자가 있어야 한다.
_DATE_NOTATION = re.compile(
    r"([0-9]{4})"
    r"(?:\s*(?:년|[./-])\s*([0-9]{1,2})"
    r"(?:\s*(?:월|[./-])\s*([0-9]{1,2}))?)?"
    r"\s*(?:년|월|일|\.)?"
)
_ISO = re.compile(r"(\d{4})(?:-(\d{2}))?(?:-\d{2})?")
_OUTPUT = re.compile(r"(\d{4})(?:\.(\d{1,2}))?")
_PRESENT_RANK = 10**9


def normalize_date(value: str) -> str:
    """표기만 다른 날짜를 ISO로 맞춘다. 맞지 않으면 그대로 두어 형식 검사에서 제외된다."""
    match = _DATE_NOTATION.fullmatch(value.strip())
    if match is None:
        return value
    year, month, day = match.groups()
    return "-".join([year] + [f"{int(part):02d}" for part in (month, day) if part])


def iso_to_output(value: str | None) -> str | None:
    """KG의 ISO 날짜를 출력 형식(YYYY·YYYY.MM)으로 바꾼다. ISO가 아니면 None"""
    match = _ISO.fullmatch(value or "")
    if match is None:
        return None
    year, month = match.groups()
    return f"{year}.{month}" if month else year


def date_rank(value: str, *, default_month: int) -> int | None:
    """출력 날짜를 비교용 숫자(연×100+월)로 바꾼다. 월이 없으면 default_month, Present는 최대"""
    if value == PRESENT:
        return _PRESENT_RANK
    match = _OUTPUT.fullmatch(value)
    if match is None:
        return None
    year, month = match.groups()
    return int(year) * 100 + (int(month) if month else default_month)
