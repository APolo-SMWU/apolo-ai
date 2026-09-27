"""Fact 값이 value_type 형식에 맞는지 확인한다.

형식만 확인한다. 값이 사실인지, 해당 속성에 허용된 값인지는 판단하지 않는다.
형식이 틀린 값을 고치거나 비슷한 값으로 추측해 바꾸지 않는다.
"""

import re
from datetime import date
from urllib.parse import urlparse

from apolo.ontology.personal import ValueType

_DATE_PATTERN = re.compile(r"([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?)?")


def is_valid_value(value_type: ValueType, value: object) -> bool:
    """value_type 형식에 맞으면 True를 반환한다. 형식 규칙이 없는 타입은 오류"""
    if value_type == "boolean":
        return isinstance(value, bool)
    if not isinstance(value, str) or not value.strip():
        return False
    if value_type == "string":
        return True
    if value_type == "date":
        return _is_iso_date(value)
    if value_type == "uri":
        return _is_http_url(value)
    raise ValueError(f"형식 규칙이 없는 value_type입니다: {value_type}")


def _is_iso_date(value: str) -> bool:
    """YYYY·YYYY-MM·YYYY-MM-DD 중 하나이고 달력에 있는 날짜인지"""
    match = _DATE_PATTERN.fullmatch(value)
    if match is None:
        return False
    year, month, day = (int(part) if part else 1 for part in match.groups())
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _is_http_url(value: str) -> bool:
    """http·https URL이고 호스트가 있는지"""
    if any(character.isspace() for character in value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
