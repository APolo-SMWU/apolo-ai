"""사용자가 제공한 Source의 소유 관계를 안전하게 보강"""

from collections import defaultdict

from apolo.contracts.extraction import EntityCandidate, ExtractionResult, RelationCandidate
from apolo.contracts.source import CollectedSource

_OWNER_PREDICATES = {
    "Education": "hasEducation",
    "Experience": "hasExperience",
    "Activity": "participatedIn",
    "Work": "participatedIn",
    "Credential": "holds",
    "Skill": "hasSkill",
}

_SOURCE_CLASSES = {
    "notion": frozenset(_OWNER_PREDICATES),
    "github": frozenset({"Work", "Skill"}),
}

_IDENTITY_PREDICATES = {
    "Work": "title",
    "Skill": "name",
    "Experience": "role",
    "Activity": "name",
    "Education": "major",
    "Credential": "title",
}


def add_source_ownership_relations(
    source: CollectedSource, extraction: ExtractionResult
) -> ExtractionResult:
    """누락된 사용자 소유 관계를 검증 가능한 근거로만 보강

    Source는 사용자가 제출한 URL에 속하지만, GitHub에서는 Work만 자동 연결한다.
    Skill은 프로젝트나 경력에서 사용된 기술일 수 있으므로 직접 보유 기술로 승격하지 않는다.
    """
    allowed_classes = _SOURCE_CLASSES.get(source.source_type, frozenset())
    if not allowed_classes:
        return extraction

    entities = {entity.ref: entity for entity in extraction.entities}
    facts_by_ref: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for fact in extraction.facts:
        facts_by_ref[fact.entity_ref].append((fact.predicate, fact.evidence_refs))

    organization_evidence: dict[str, list[list[str]]] = defaultdict(list)
    skill_used_by: set[str] = set()
    for relation in extraction.relations:
        if relation.predicate == "atOrganization":
            organization_evidence[relation.subject_ref].append(relation.evidence_refs)
        elif relation.predicate == "usesSkill":
            skill_used_by.add(relation.object_ref)

    owned_pairs = {
        (relation.predicate, relation.object_ref)
        for relation in extraction.relations
        if relation.subject_ref == "self"
    }
    added: list[RelationCandidate] = []
    for entity in entities.values():
        if entity.class_type not in allowed_classes:
            continue
        if entity.class_type == "Skill" and entity.ref in skill_used_by:
            continue

        predicate = _OWNER_PREDICATES[entity.class_type]
        if (predicate, entity.ref) in owned_pairs:
            continue
        evidence = _ownership_evidence(entity, facts_by_ref, organization_evidence)
        if evidence is None:
            continue
        added.append(
            RelationCandidate(
                subject_ref="self",
                predicate=predicate,
                object_ref=entity.ref,
                evidence_refs=evidence,
                confidence=0.55,
            )
        )

    if not added:
        return extraction
    return extraction.model_copy(update={"relations": [*extraction.relations, *added]})


def _ownership_evidence(
    entity: EntityCandidate,
    facts_by_ref: dict[str, list[tuple[str, list[str]]]],
    organization_evidence: dict[str, list[list[str]]],
) -> list[str] | None:
    identity_predicate = _IDENTITY_PREDICATES.get(entity.class_type)
    if identity_predicate is not None:
        for predicate, evidence in facts_by_ref.get(entity.ref, []):
            if predicate == identity_predicate and evidence:
                return evidence
    for evidence in organization_evidence.get(entity.ref, []):
        if evidence:
            return evidence
    for _, evidence in facts_by_ref.get(entity.ref, []):
        if evidence:
            return evidence
    return None
