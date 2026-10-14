"""선별된 KG의 tool Skill로 Skills 블록을 만든다. 표시 규칙만 담당한다."""

from collections import defaultdict
from uuid import UUID

from apolo.contracts.generate import SkillCategory, SkillItem, SkillsBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.ontology.personal import SKILL_CATEGORY_IDS
from apolo.ontology.skill_categories import SKILL_CATEGORY_CATALOG

# 서비스 이름이 "플랫폼명 + 서비스명"인 클라우드 플랫폼
_PLATFORM_PREFIXES = (
    (("azure ", "microsoft azure "), "Azure"),
    (("aws ", "amazon "), "AWS"),
    (("google cloud ",), "Google Cloud"),
    (("naver cloud ",), "Naver Cloud"),
)
_PLATFORM_CATEGORY = "cloud_deployment"


def build_skills_block(graph: ActiveKnowledgeGraph) -> SkillsBlock | None:
    names: dict[UUID, list[str]] = defaultdict(list)
    kinds: dict[UUID, str] = {}
    categories: dict[UUID, set[str]] = defaultdict(set)
    for fact in graph.facts:
        if not isinstance(fact.value, str):
            continue
        if fact.predicate == "name":
            names[fact.entity_id].append(fact.value)
        elif fact.predicate == "kind":
            kinds[fact.entity_id] = fact.value
        elif fact.predicate == "category":
            categories[fact.entity_id].add(fact.value)

    items: dict[str, list[SkillItem]] = defaultdict(list)
    platforms: dict[str, list[tuple[UUID, str, str]]] = defaultdict(list)
    for entity in graph.entities:
        if entity.class_type != "Skill" or kinds.get(entity.id) != "tool":
            continue
        if not names[entity.id]:
            continue
        name = sorted(names[entity.id], key=str.casefold)[0]
        platform = _platform(name)
        if platform is None:
            items[_category(categories[entity.id])].append(_item([entity.id], name))
        else:
            platforms[platform[0]].append((entity.id, name, platform[1]))

    # 같은 플랫폼의 서로 다른 서비스가 둘 이상이면 플랫폼명 하나로 묶는다.
    for representative, members in platforms.items():
        if len({service for _, _, service in members if service}) >= 2:
            ids = [skill_id for skill_id, _, _ in members]
            items[_PLATFORM_CATEGORY].append(_item(ids, representative))
            continue
        for skill_id, name, _ in members:
            items[_category(categories[skill_id])].append(_item([skill_id], name))

    blocks = [
        SkillCategory(
            category=SKILL_CATEGORY_CATALOG[category][0],
            items=sorted(items[category], key=lambda item: item.name.casefold()),
        )
        for category in SKILL_CATEGORY_IDS
        if items.get(category)
    ]
    return SkillsBlock(categories=blocks) if blocks else None


def _category(values: set[str]) -> str:
    """여러 그룹이면 목록 순서상 앞의 그룹 하나에만 표시한다."""
    return next((category for category in SKILL_CATEGORY_IDS if category in values), "other")


def _platform(name: str) -> tuple[str, str] | None:
    """(대표 플랫폼명, 서비스명). 플랫폼 이름만 있으면 서비스명은 빈 문자열이다."""
    key = " ".join(name.casefold().split()) + " "
    for prefixes, representative in _PLATFORM_PREFIXES:
        if key == representative.casefold() + " ":
            return representative, ""
        for prefix in prefixes:
            if key.startswith(prefix):
                return representative, key[len(prefix) :].strip()
    return None


def _item(entity_ids: list[UUID], name: str) -> SkillItem:
    return SkillItem(entity_ids=[str(entity_id) for entity_id in entity_ids], name=name)
