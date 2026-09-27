"""Graph B 출력의 구조와 KG 참조를 결정적으로 검증한다."""

from dataclasses import dataclass

from apolo.contracts.content import GraphBOutput
from apolo.contracts.generate import SkillsBlock, TimelineBlock, WorksBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph


@dataclass(frozen=True)
class ContentValidationIssue:
    """콘텐츠 저장·응답을 보류한 이유"""

    path: str
    code: str
    message: str


_TIMELINE_ENTITY_TYPES = {
    "education": frozenset({"Education"}),
    "experience": frozenset({"Experience"}),
    "activities": frozenset({"Experience"}),
    "awards": frozenset({"Credential"}),
    "certification": frozenset({"Credential"}),
}


def validate_graph_b_output(
    output: GraphBOutput, graph: ActiveKnowledgeGraph
) -> list[ContentValidationIssue]:
    """Graph B 블록의 Entity 참조·중복·빈 블록을 검증한다."""
    entity_types = {str(entity.id): entity.class_type for entity in graph.entities}
    issues: list[ContentValidationIssue] = []
    referenced_ids: set[str] = set()

    for block_index, block in enumerate(output.blocks):
        block_path = f"blocks[{block_index}]"
        if isinstance(block, TimelineBlock):
            expected_type = _TIMELINE_ENTITY_TYPES[block.type]
            if not block.items:
                issues.append(
                    ContentValidationIssue(
                        path=block_path,
                        code="EMPTY_BLOCK",
                        message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
                    )
                )
            for item_index, item in enumerate(block.items):
                _validate_entity_reference(
                    issues,
                    referenced_ids,
                    entity_types,
                    item.entity_id,
                    expected_type,
                    f"{block_path}.items[{item_index}].entityId",
                )
        elif isinstance(block, WorksBlock):
            if not block.items:
                issues.append(
                    ContentValidationIssue(
                        path=block_path,
                        code="EMPTY_BLOCK",
                        message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
                    )
                )
            for item_index, item in enumerate(block.items):
                _validate_entity_reference(
                    issues,
                    referenced_ids,
                    entity_types,
                    item.entity_id,
                    frozenset({"Work"}),
                    f"{block_path}.items[{item_index}].entityId",
                )
        elif isinstance(block, SkillsBlock):
            _validate_skill_block(issues, block, block_path)

    return issues


def _validate_entity_reference(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    entity_id: str,
    expected_types: frozenset[str],
    path: str,
) -> None:
    if entity_id not in entity_types:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="ENTITY_NOT_FOUND",
                message="콘텐츠가 참조한 Entity가 현재 KG에 없습니다.",
            )
        )
        return
    if entity_types[entity_id] not in expected_types:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="ENTITY_TYPE_MISMATCH",
                message="블록 종류와 Entity 유형이 일치하지 않습니다.",
            )
        )
    if entity_id in referenced_ids:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="DUPLICATE_ENTITY_REFERENCE",
                message="같은 Entity를 여러 콘텐츠 항목에서 참조할 수 없습니다.",
            )
        )
    referenced_ids.add(entity_id)


def _validate_skill_block(
    issues: list[ContentValidationIssue], block: SkillsBlock, block_path: str
) -> None:
    categories = block.categories
    if not categories:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 카테고리가 하나 이상 있어야 합니다.",
            )
        )
    for category_index, category in enumerate(categories):
        if not category.items:
            issues.append(
                ContentValidationIssue(
                    path=f"{block_path}.categories[{category_index}]",
                    code="EMPTY_SKILL_CATEGORY",
                    message="기술 카테고리에는 기술이 하나 이상 있어야 합니다.",
                )
            )
