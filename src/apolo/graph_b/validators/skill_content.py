"""Skills block의 KG 근거 검증"""

from collections import defaultdict

from apolo.contracts.generate import SkillsBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.skill_categories import (
    UNCATEGORIZED_SKILL_CATEGORY,
    skill_display_category,
)
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import item_entity_id


def validate_skill_content(
    issues: list[ContentValidationIssue],
    block: SkillsBlock,
    graph: ActiveKnowledgeGraph,
    block_path: str,
) -> None:
    """Skills category와 item이 연결된 Skill KG 근거와 일치하는지 검증한다"""

    if not block.categories:
        issues.append(
            ContentValidationIssue(
                path=block_path,
                code="EMPTY_BLOCK",
                message="콘텐츠 블록에는 카테고리가 하나 이상 있어야 합니다.",
            )
        )
        return

    supported_by_category = _supported_skills_by_category(graph)
    seen_items_by_category: dict[str, set[str]] = defaultdict(set)
    seen_entity_ids_by_category: dict[str, set[str]] = defaultdict(set)
    for category_index, category in enumerate(block.categories):
        category_path = f"{block_path}.categories[{category_index}]"
        supported_items = supported_by_category.get(category.category)
        if supported_items is None:
            issues.append(
                ContentValidationIssue(
                    path=f"{category_path}.category",
                    code="SKILL_CATEGORY_UNSUPPORTED",
                    message="Skills category가 기술명 기반 표시 분류와 일치하지 않습니다.",
                )
            )
            supported_items = {}
        if not category.items:
            issues.append(
                ContentValidationIssue(
                    path=category_path,
                    code="EMPTY_SKILL_CATEGORY",
                    message="기술 카테고리에는 기술이 하나 이상 있어야 합니다.",
                )
            )
        for item_index, item in enumerate(category.items):
            item_path = f"{category_path}.items[{item_index}]"
            parsed_ids = [item_entity_id(value) for value in item.entity_ids]
            member_ids = [str(value) for value in parsed_ids if value is not None]
            member_names = [supported_items.get(skill_id) for skill_id in member_ids]
            if (
                len(member_ids) != len(item.entity_ids)
                or len(member_ids) != len(set(member_ids))
                or any(names is None for names in member_names)
            ):
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="SKILL_ITEM_UNSUPPORTED",
                        message="Skills item의 entityIds가 해당 category의 KG Skill 근거와 일치하지 않습니다.",
                    )
                )
                continue
            # 단일 항목은 실제 KG 이름을 사용하고, 그룹 대표명만 달라질 수 있다.
            if len(member_ids) == 1 and item.name not in (member_names[0] or set()):
                issues.append(
                    ContentValidationIssue(
                        path=f"{item_path}.name",
                        code="SKILL_ITEM_UNSUPPORTED",
                        message="개별 Skills 항목 이름은 KG Skill 이름과 일치해야 합니다.",
                    )
                )
            repeated_ids = seen_entity_ids_by_category[category.category].intersection(member_ids)
            if repeated_ids:
                issues.append(
                    ContentValidationIssue(
                        path=f"{item_path}.entityIds",
                        code="DUPLICATE_SKILL_ENTITY",
                        message="같은 KG Skill을 Skills 블록의 여러 항목에 중복 연결할 수 없습니다.",
                    )
                )
            seen_entity_ids_by_category[category.category].update(member_ids)
            display_name = " ".join(item.name.split()).casefold()
            if display_name in seen_items_by_category[category.category]:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="DUPLICATE_SKILL_ITEM",
                        message="같은 기술을 Skills 블록에서 중복 표시할 수 없습니다.",
                    )
                )
            seen_items_by_category[category.category].add(display_name)


def _supported_skills_by_category(graph: ActiveKnowledgeGraph) -> dict[str, dict[str, set[str]]]:
    """Skills 블록에 포함 가능한 KG Skill을 표시용 분류별로 묶는다"""

    skill_ids = {entity.id for entity in graph.entities if entity.class_type == "Skill"}
    used_skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.predicate in {"hasSkill", "usesSkill"}
        and relation.object_entity_id in skill_ids
    }
    names_by_skill: dict = defaultdict(set)
    for fact in graph.facts:
        if fact.entity_id not in used_skill_ids or not isinstance(fact.value, str):
            continue
        if fact.predicate == "name":
            names_by_skill[fact.entity_id].add(fact.value)

    supported: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for skill_id, names in names_by_skill.items():
        categories = {skill_display_category(name) for name in names}
        named_categories = categories - {UNCATEGORIZED_SKILL_CATEGORY}
        category = (
            next(iter(named_categories))
            if len(named_categories) == 1
            else UNCATEGORIZED_SKILL_CATEGORY
        )
        supported[category][str(skill_id)].update(names)
    return {category: dict(skills) for category, skills in supported.items()}
