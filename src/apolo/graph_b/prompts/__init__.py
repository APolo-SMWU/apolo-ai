"""Graph B 블록별 생성 프롬프트 레지스트리"""

from apolo.graph_b.prompts.common import COMMON_PROMPT
from apolo.graph_b.prompts.education import EDUCATION_PROMPT
from apolo.graph_b.prompts.experience import EXPERIENCE_PROMPT

BLOCK_PROMPTS: dict[str, str] = {
    "Education": EDUCATION_PROMPT,
    "Experience": EXPERIENCE_PROMPT,
}

__all__ = ["BLOCK_PROMPTS", "COMMON_PROMPT"]
