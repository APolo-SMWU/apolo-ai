"""Skills block의 KG 근거와 카테고리 검증"""

from collections import defaultdict

from apolo.contracts.generate import SkillsBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.skill_categories import (
    SKILL_CATEGORIES,
    canonical_skill_name,
    platform_group_representative,
    skill_categories_for_name,
)
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import item_entity_id


def validate_skill_content(
    issues: list[ContentValidationIssue],
    block: SkillsBlock,
    graph: ActiveKnowledgeGraph,
    block_path: str,
) -> None:
    """카테고리·표준 기술명·entityIds가 KG 근거와 일치하는지 확인한다."""

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
    seen_display_names: set[str] = set()
    seen_entity_ids: set[str] = set()
    for category_index, category in enumerate(block.categories):
        category_path = f"{block_path}.categories[{category_index}]"
        supported_items = supported_by_category.get(category.category, {})
        if category.category not in SKILL_CATEGORIES:
            issues.append(
                ContentValidationIssue(
                    path=f"{category_path}.category",
                    code="SKILL_CATEGORY_UNSUPPORTED",
                    message="Skills category가 표준 분류 목록에 없습니다.",
                )
            )
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
                        message=(
                            "Skills item의 entityIds가 해당 category의 KG Skill 근거와 "
                            "일치하지 않습니다."
                        ),
                    )
                )
                continue

            canonical_names_by_member = [
                {canonical_skill_name(name) for name in names or set()} for names in member_names
            ]
            common_names = set.intersection(*canonical_names_by_member)
            display_name = canonical_skill_name(item.name)
            platform_name = platform_group_representative(member_names)
            if display_name not in common_names and display_name != platform_name:
                issues.append(
                    ContentValidationIssue(
                        path=f"{item_path}.name",
                        code="SKILL_ITEM_UNSUPPORTED",
                        message="기술명은 연결된 KG Skill의 표준 이름이어야 합니다.",
                    )
                )

            category_options_by_member = [
                {option for name in names or set() for option in skill_categories_for_name(name)}
                for names in member_names
            ]
            if any(
                options and category.category not in options
                for options in category_options_by_member
            ):
                issues.append(
                    ContentValidationIssue(
                        path=f"{item_path}.category",
                        code="SKILL_CATEGORY_UNSUPPORTED",
                        message="기술 카테고리가 분류 사전과 일치하지 않습니다.",
                    )
                )

            repeated_ids = seen_entity_ids.intersection(member_ids)
            if repeated_ids:
                issues.append(
                    ContentValidationIssue(
                        path=f"{item_path}.entityIds",
                        code="DUPLICATE_SKILL_ENTITY",
                        message="같은 KG Skill은 Skills 블록에 한 번만 표시할 수 있습니다.",
                    )
                )
            seen_entity_ids.update(member_ids)

            display_key = " ".join(display_name.split()).casefold()
            if display_key in seen_display_names:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="DUPLICATE_SKILL_ITEM",
                        message="같은 기술은 카테고리와 관계없이 한 번만 표시할 수 있습니다.",
                    )
                )
            seen_display_names.add(display_key)


def _supported_skills_by_category(
    graph: ActiveKnowledgeGraph,
) -> dict[str, dict[str, set[str]]]:
    """확인된 KG Skill ID와 이름을 가능한 표시 카테고리에 연결한다.

    목록에 없는 기술도 모델이 근거와 사용 맥락으로 적절히 분류할 수 있도록
    모든 표준 카테고리에서 검증 가능한 Skill로 취급한다.
    """

    skill_ids = {entity.id for entity in graph.entities if entity.class_type == "Skill"}
    used_skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.predicate in {"hasSkill", "usesSkill"}
        and relation.object_entity_id in skill_ids
    }
    names_by_skill: dict = defaultdict(set)
    for fact in graph.facts:
        if (
            fact.entity_id in used_skill_ids
            and fact.predicate == "name"
            and isinstance(fact.value, str)
        ):
            names_by_skill[fact.entity_id].add(fact.value)

    supported: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for skill_id, names in names_by_skill.items():
        categories = {category for name in names for category in skill_categories_for_name(name)}
        if not categories:
            categories = set(SKILL_CATEGORIES)
        for category in categories:
            supported[category][str(skill_id)].update(names)
    return {category: dict(skills) for category, skills in supported.items()}
