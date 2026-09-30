"""짧은 제목의 표기 차이를 보수적으로 비교하는 도구"""

import re
import unicodedata
from difflib import SequenceMatcher


_TOKEN = re.compile(r"[a-z0-9]+|[가-힣]+", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")


def similar_title(left: str, right: str) -> bool:
    """핵심 단어와 표기 유사도가 충분히 높은 제목인지 판정한다.

    같은 회차·연도 표기가 서로 다르면 유사도가 높아도 다른 항목으로 본다.
    단일 짧은 공통 단어만으로는 병합하지 않는다.
    """
    left_text = _normalize(left)
    right_text = _normalize(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True

    left_numbers = set(_NUMBER.findall(left_text))
    right_numbers = set(_NUMBER.findall(right_text))
    if left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers):
        return False

    left_tokens = set(_TOKEN.findall(left_text))
    right_tokens = set(_TOKEN.findall(right_text))
    common = left_tokens & right_tokens
    if not common:
        return False

    token_jaccard = len(common) / len(left_tokens | right_tokens)
    common_coverage = len(common) / min(len(left_tokens), len(right_tokens))
    text_ratio = SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()

    compact_left = left_text.replace(" ", "")
    compact_right = right_text.replace(" ", "")
    compact_ratio = SequenceMatcher(
        None, compact_left, compact_right, autojunk=False
    ).ratio()
    if text_ratio >= 0.90 or compact_ratio >= 0.90 or token_jaccard >= 0.78:
        return True
    return common_coverage == 1 and len(common) >= 2 and token_jaccard >= 0.60


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(_TOKEN.findall(normalized))
