"""Skills block의 구조 검증"""

from apolo.contracts.generate import SkillsBlock
from apolo.graph_b.validation_types import ContentValidationIssue


def validate_skill_block(
    issues: list[ContentValidationIssue], block: SkillsBlock, block_path: str
) -> None:
    """Skills 카테고리와 항목의 비어 있음 여부를 검증한다"""

    if not block.categories:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 카테고리가 하나 이상 있어야 합니다.",
            )
        )
    for category_index, category in enumerate(block.categories):
        if not category.items:
            issues.append(
                ContentValidationIssue(
                    path=f"{block_path}.categories[{category_index}]",
                    code="EMPTY_SKILL_CATEGORY",
                    message="기술 카테고리에는 기술이 하나 이상 있어야 합니다.",
                )
            )
