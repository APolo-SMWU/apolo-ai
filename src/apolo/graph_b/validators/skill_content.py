"""Skills block의 KG 근거 검증"""

from collections import defaultdict

from apolo.contracts.generate import SkillsBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue


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
    seen_items: set[str] = set()
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
            supported_items = set()
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
            if item not in supported_items:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="SKILL_ITEM_UNSUPPORTED",
                        message="Skills item이 usesSkill 관계와 category fact에 일치하지 않습니다.",
                    )
                )
            if item in seen_items:
                issues.append(
                    ContentValidationIssue(
                        path=item_path,
                        code="DUPLICATE_SKILL_ITEM",
                        message="같은 기술을 Skills 블록에서 중복 표시할 수 없습니다.",
                    )
                )
            seen_items.add(item)


def _supported_skills_by_category(graph: ActiveKnowledgeGraph) -> dict[str, set[str]]:
    """Person 보유 기술과 Work·Experience 사용 기술을 category별로 묶는다"""

    used_skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.predicate in {"hasSkill", "usesSkill"}
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

    supported: dict[str, set[str]] = defaultdict(set)
    for skill_id, names in names_by_skill.items():
        for category in categories_by_skill.get(skill_id, set()):
            supported[category].update(names)
    return dict(supported)
