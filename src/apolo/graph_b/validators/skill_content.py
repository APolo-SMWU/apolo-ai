"""Skills block의 KG 근거 검증"""

from collections import defaultdict

from apolo.contracts.generate import SkillsBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.skill_categories import UNCATEGORIZED_SKILL_CATEGORY
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
    for category_index, category in enumerate(block.categories):
        category_path = f"{block_path}.categories[{category_index}]"
        supported_items = supported_by_category.get(category.category)
        if supported_items is None:
            issues.append(
                ContentValidationIssue(
                    path=f"{category_path}.category",
                    code="SKILL_CATEGORY_UNSUPPORTED",
                    message="Skills category가 Skill의 category fact와 일치하지 않습니다.",
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
            skill_id = item_entity_id(item.entity_id)
            skill_key = str(skill_id) if skill_id is not None else item.entity_id
            supported_names = supported_items.get(skill_key, set())
            if item.name not in supported_names:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="SKILL_ITEM_UNSUPPORTED",
                        message="Skills item이 KG 관계·category·name 근거와 일치하지 않습니다.",
                    )
                )
            if skill_key in seen_items_by_category[category.category]:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="DUPLICATE_SKILL_ITEM",
                        message="같은 기술을 Skills 블록에서 중복 표시할 수 없습니다.",
                    )
                )
            seen_items_by_category[category.category].add(skill_key)


def _supported_skills_by_category(graph: ActiveKnowledgeGraph) -> dict[str, dict[str, set[str]]]:
    """Person 보유 기술과 Work·Experience 사용 기술을 category별로 묶는다"""

    skill_ids = {entity.id for entity in graph.entities if entity.class_type == "Skill"}
    used_skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.predicate in {"hasSkill", "usesSkill"}
        and relation.object_entity_id in skill_ids
    }
    names_by_skill: dict = defaultdict(set)
    categories_by_skill: dict = defaultdict(set)
    for fact in graph.facts:
        if fact.entity_id not in used_skill_ids or not isinstance(fact.value, str):
            continue
        if fact.predicate == "name":
            names_by_skill[fact.entity_id].add(fact.value)
        elif fact.predicate == "category":
            categories_by_skill[fact.entity_id].add(fact.value)

    supported: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for skill_id, names in names_by_skill.items():
        categories = categories_by_skill.get(skill_id) or {
            UNCATEGORIZED_SKILL_CATEGORY
        }
        for category in categories:
            supported[category][str(skill_id)].update(names)
    return {category: dict(skills) for category, skills in supported.items()}
