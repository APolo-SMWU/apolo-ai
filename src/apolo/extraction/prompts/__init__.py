"""Graph A 추출 프롬프트 섹션 레지스트리"""

from apolo.extraction.prompts.common import COMMON_PROMPT, EVIDENCE_PROMPT
from apolo.extraction.prompts.dates import DATE_PROMPT
from apolo.extraction.prompts.skills import SKILL_PROMPT
from apolo.extraction.prompts.sources import SOURCE_PROMPTS

SYSTEM_PROMPTS: tuple[str, ...] = (COMMON_PROMPT, DATE_PROMPT, EVIDENCE_PROMPT, SKILL_PROMPT)

__all__ = ["SOURCE_PROMPTS", "SYSTEM_PROMPTS"]
