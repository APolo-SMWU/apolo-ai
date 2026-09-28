"""Graph B 출력의 구조와 KG 참조를 결정적으로 검증"""

from apolo.contracts.content import GraphBOutput
from apolo.contracts.generate import (
    ActivitiesBlock,
    AwardsBlock,
    CertificationBlock,
    EducationBlock,
    ExperienceBlock,
    SkillsBlock,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators import (
    validate_activity_item,
    validate_award_item,
    validate_certification_item,
    validate_education_item,
    validate_experience_item,
    validate_skill_content,
    validate_work_item,
)

__all__ = ["ContentValidationIssue", "validate_graph_b_output"]


_TIMELINE_ENTITY_TYPES = {
    "education": frozenset({"Education"}),
    "experience": frozenset({"Experience"}),
    "activities": frozenset({"Activity"}),
}


def validate_graph_b_output(
    output: GraphBOutput, graph: ActiveKnowledgeGraph
) -> list[ContentValidationIssue]:
    """Graph B 블록의 Entity 참조·중복·빈 블록을 검증한다"""

    entity_types = {str(entity.id): entity.class_type for entity in graph.entities}
    issues: list[ContentValidationIssue] = []
    referenced_ids: set[str] = set()

    for block_index, block in enumerate(output.blocks):
        block_path = f"blocks[{block_index}]"
        if isinstance(block, (EducationBlock, ExperienceBlock, ActivitiesBlock)):
            _validate_timeline_block(
                issues, referenced_ids, entity_types, block, block_path, graph
            )
        elif isinstance(block, WorksBlock):
            _validate_works_block(
                issues, referenced_ids, entity_types, block, block_path, graph
            )
        elif isinstance(block, AwardsBlock):
            _validate_credential_block(
                issues,
                referenced_ids,
                entity_types,
                block,
                block_path,
                graph,
                validate_award_item,
            )
        elif isinstance(block, CertificationBlock):
            _validate_credential_block(
                issues,
                referenced_ids,
                entity_types,
                block,
                block_path,
                graph,
                validate_certification_item,
            )
        elif isinstance(block, SkillsBlock):
            validate_skill_content(issues, block, graph, block_path)

    return issues


def _validate_timeline_block(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    block: EducationBlock | ExperienceBlock | ActivitiesBlock,
    block_path: str,
    graph: ActiveKnowledgeGraph,
) -> None:
    """Timeline 계열 block의 공통 참조 검증과 항목별 검증을 수행한다"""

    if not block.items:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
            )
        )

    education_items: set[tuple[str, str | None, str | None, str, str | None]] = set()
    for item_index, item in enumerate(block.items):
        item_path = f"{block_path}.items[{item_index}]"
        _validate_entity_reference(
            issues,
            referenced_ids,
            entity_types,
            item.entity_id,
            _TIMELINE_ENTITY_TYPES[block.type],
            f"{item_path}.entityId",
            allow_duplicate=isinstance(block, EducationBlock),
        )
        if isinstance(block, EducationBlock):
            fingerprint = (
                item.entity_id,
                item.start_date,
                item.end_date,
                item.organization,
                item.role,
            )
            if fingerprint in education_items:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="DUPLICATE_EDUCATION_ITEM",
                        message="같은 Education item을 중복 반환할 수 없습니다.",
                    )
                )
            education_items.add(fingerprint)
            validate_education_item(issues, item, graph, item_path)
        elif isinstance(block, ExperienceBlock):
            validate_experience_item(issues, item, graph, item_path)
        elif isinstance(block, ActivitiesBlock):
            validate_activity_item(issues, item, graph, item_path)


def _validate_works_block(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    block: WorksBlock,
    block_path: str,
    graph: ActiveKnowledgeGraph,
) -> None:
    """Works block의 공통 Entity 참조를 검증한다"""

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
        validate_work_item(issues, item, graph, f"{block_path}.items[{item_index}]")


def _validate_credential_block(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    block: AwardsBlock | CertificationBlock,
    block_path: str,
    graph: ActiveKnowledgeGraph,
    item_validator,
) -> None:
    """Credential block의 공통 참조와 전용 필드 검증을 수행한다"""

    if not block.items:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 항목이 하나 이상 있어야 합니다.",
            )
        )
    for item_index, item in enumerate(block.items):
        item_path = f"{block_path}.items[{item_index}]"
        _validate_entity_reference(
            issues,
            referenced_ids,
            entity_types,
            item.entity_id,
            frozenset({"Credential"}),
            f"{item_path}.entityId",
        )
        item_validator(issues, item, graph, item_path)


def _validate_entity_reference(
    issues: list[ContentValidationIssue],
    referenced_ids: set[str],
    entity_types: dict[str, str],
    entity_id: str,
    expected_types: frozenset[str],
    path: str,
    *,
    allow_duplicate: bool = False,
) -> None:
    """출력 item의 Entity 존재·유형·중복 참조를 검증한다"""

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
    if entity_id in referenced_ids and not allow_duplicate:
        issues.append(
            ContentValidationIssue(
                path=path,
                code="DUPLICATE_ENTITY_REFERENCE",
                message="같은 Entity를 여러 콘텐츠 항목에서 참조할 수 없습니다.",
            )
        )
    referenced_ids.add(entity_id)
