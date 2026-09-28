"""Graph B 블록별 생성 프롬프트 레지스트리"""

from apolo.graph_b.prompts.activities import ACTIVITIES_PROMPT
from apolo.graph_b.prompts.common import COMMON_PROMPT
from apolo.graph_b.prompts.credentials import CREDENTIALS_PROMPT
from apolo.graph_b.prompts.education import EDUCATION_PROMPT
from apolo.graph_b.prompts.experience import EXPERIENCE_PROMPT
from apolo.graph_b.prompts.works import WORKS_PROMPT

BLOCK_PROMPTS: dict[str, str] = {
    "Activity": ACTIVITIES_PROMPT,
    "Education": EDUCATION_PROMPT,
    "Experience": EXPERIENCE_PROMPT,
    "Work": WORKS_PROMPT,
    "Credential": CREDENTIALS_PROMPT,
}

__all__ = ["BLOCK_PROMPTS", "COMMON_PROMPT"]
