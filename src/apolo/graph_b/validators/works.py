"""Works block의 KG 근거 검증"""

from apolo.contracts.generate import WorkItem
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.validation_types import ContentValidationIssue
from apolo.graph_b.validators.common import entity_facts, fact_values, item_entity_id


def _skill_names(graph: ActiveKnowledgeGraph, work_id) -> set[str]:
    """Work에 usesSkill로 연결된 Skill.name을 반환한다"""

    skill_ids = {
        relation.object_entity_id
        for relation in graph.relations
        if relation.subject_entity_id == work_id and relation.predicate == "usesSkill"
    }
    return {
        fact.value
        for fact in graph.facts
        if fact.entity_id in skill_ids
        and fact.predicate == "name"
        and isinstance(fact.value, str)
    }


def validate_work_item(
    issues: list[ContentValidationIssue],
    item: WorkItem,
    graph: ActiveKnowledgeGraph,
    item_path: str,
) -> None:
    """Works 값이 연결된 Work KG 근거와 일치하는지 검증한다"""

    entity_id = item_entity_id(item.entity_id)
    if entity_id is None:
        return  # Entity 참조 오류는 공통 검증이 이미 보고한다

    facts = entity_facts(graph, entity_id)
    _validate_single_value(
        issues,
        item.title,
        fact_values(facts, "title"),
        f"{item_path}.title",
        "WORK_TITLE_UNSUPPORTED",
        "Works title이 KG의 근거와 일치하지 않습니다.",
    )
    _validate_single_value(
        issues,
        item.kind,
        fact_values(facts, "kind"),
        f"{item_path}.kind",
        "WORK_KIND_UNSUPPORTED",
        "Works kind가 KG의 근거와 일치하지 않습니다.",
    )
    if item.role is not None:
        _validate_single_value(
            issues,
            item.role,
            fact_values(facts, "role"),
            f"{item_path}.role",
            "WORK_ROLE_UNSUPPORTED",
            "Works role이 KG의 근거와 일치하지 않습니다.",
        )

    supported_skills = _skill_names(graph, entity_id)
    for skill_index, skill in enumerate(item.skills or []):
        if skill not in supported_skills:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.skills[{skill_index}]",
                    code="WORK_SKILL_UNSUPPORTED",
                    message="Works skill이 usesSkill 관계와 일치하지 않습니다.",
                )
            )

    supported_urls = fact_values(facts, "url")
    for link_index, link in enumerate(item.links):
        if link.href not in supported_urls:
            issues.append(
                ContentValidationIssue(
                    path=f"{item_path}.links[{link_index}].href",
                    code="WORK_LINK_UNSUPPORTED",
                    message="Works link가 Work의 url fact와 일치하지 않습니다.",
                )
            )


def _validate_single_value(
    issues: list[ContentValidationIssue],
    value: str,
    supported_values: set[str],
    path: str,
    code: str,
    message: str,
) -> None:
    """문자열 출력값이 해당 Fact 값인지 확인한다"""

    if value not in supported_values:
        issues.append(ContentValidationIssue(path=path, code=code, message=message))
