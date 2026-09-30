"""짧은 제목의 표기 차이를 보수적으로 비교하는 도구"""

import re
import unicodedata
from difflib import SequenceMatcher

_TOKEN = re.compile(r"[a-z0-9]+|[가-힣]+", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
_GENERIC_CONTENT_TOKENS = {
    "project",
    "projects",
    "application",
    "app",
    "system",
    "service",
    "agent",
    "assistant",
    "chatbot",
    "web",
    "mobile",
    "tool",
    "development",
    "developed",
    "built",
    "implementation",
    "participation",
    "participate",
    "participated",
    "research",
    "work",
    "program",
    "team",
    "프로젝트",
    "참여",
    "수행",
    "활동",
    "개발",
    "구현",
    "제작",
    "진행",
    "연구",
    "팀",
    "기반",
    "시스템",
    "서비스",
    "에이전트",
    "챗봇",
    "웹",
    "앱",
    "기술",
    "플랫폼",
    "모델",
    "프로그램",
    "과제",
    "조사",
    "및",
    "통해",
    "위한",
}


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


def shares_core_terms(left: str, right: str, *, min_shared: int = 2) -> bool:
    """긴 제목·설명에 포함된 핵심 단어가 충분히 겹치는지 비교한다.

    제목 전체의 Jaccard 유사도만으로 놓치기 쉬운 긴 제목의 축약·확장 표현을
    찾되, '프로젝트'처럼 흔한 단어 하나만 겹치는 경우는 제외한다.
    """
    left_tokens = _meaningful_tokens(left)
    right_tokens = _meaningful_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    return (
        len(shared) >= min_shared
        and len(shared) / min(len(left_tokens), len(right_tokens)) >= 0.6
    )


def similar_description(left: str, right: str) -> bool:
    """같은 산출물 설명의 축약·확장 표현인지 보수적으로 판정한다."""
    left_text = _normalize(left)
    right_text = _normalize(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return len(_meaningful_tokens(left)) >= 2
    if shares_core_terms(left, right):
        return True

    # 긴 설명 일부만 같아도 나머지에 의미 있는 기술·행동 정보가 있어야 한다.
    shorter, longer = sorted((left_text, right_text), key=len)
    shorter_original = left if len(left_text) <= len(right_text) else right
    if (
        len(shorter) >= 20
        and shorter in longer
        and len(_meaningful_tokens(shorter_original)) >= 2
    ):
        return True

    compact_left = left_text.replace(" ", "")
    compact_right = right_text.replace(" ", "")
    return (
        min(len(compact_left), len(compact_right)) >= 24
        and SequenceMatcher(None, compact_left, compact_right, autojunk=False).ratio() >= 0.78
    )


def _meaningful_tokens(value: str) -> set[str]:
    return _tokens(value) - _GENERIC_CONTENT_TOKENS


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return set(_TOKEN.findall(normalized))


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(_TOKEN.findall(normalized))
