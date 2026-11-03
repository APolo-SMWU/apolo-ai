"""겹친 원문에서 재추출한 Entity 참조만 맞춘다. 값·근거 병합은 기존 검증기가 맡는다."""

from collections import defaultdict

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource
from apolo.ontology.personal import MULTI_VALUED_PROPERTIES

_IDENTITIES = {
    "Work": {"title"},
    "Skill": {"name"},
    "Organization": {"name", "homepage"},
    "Education": {"major", "degree"},
    "Experience": {"role"},
    "Activity": {"name"},
    "Credential": {"title"},
}


def merge_overlap_entities(
    result: ExtractionResult, origins: dict[str, int], source: CollectedSource
) -> ExtractionResult:
    entities = {entity.ref: entity for entity in result.entities}
    if len(entities) != len(result.entities):
        # 동일 응답 안의 잘못된 ref는 후속 검증에 맡긴다.
        return result
    valid_locators = {
        candidate.locator
        for candidate in source.evidence_candidates
        if candidate.locator not in {"pdf.title", "docx.title"}
        and candidate.snippet in source.content
    }
    anchors = defaultdict(set)
    values = defaultdict(lambda: defaultdict(set))
    for fact in result.facts:
        entity = entities.get(fact.entity_ref)
        if entity is None:
            continue
        value = (type(fact.value).__name__, str(fact.value))
        values[entity.ref][fact.predicate].add(value)
        if (
            fact.predicate in _IDENTITIES.get(entity.class_type, set())
            and set(fact.evidence_refs) <= valid_locators
        ):
            for locator in set(fact.evidence_refs) & valid_locators:
                anchors[(entity.class_type, fact.predicate, value, locator)].add(entity.ref)

    parent = {ref: ref for ref in entities}
    chunk_ids = {ref: {origins[ref]} for ref in entities}
    affiliations = defaultdict(set)
    for relation in result.relations:
        if relation.predicate == "atOrganization":
            affiliations[relation.subject_ref].add(relation.object_ref)

    def root(ref):
        while ref in parent and parent[ref] != ref:
            parent[ref] = parent[parent[ref]]
            ref = parent[ref]
        return ref

    # 소속 기관을 먼저 묶어 학력·경력의 다른 기관을 섞지 않는다.
    for key, refs in sorted(anchors.items(), key=lambda item: item[0][0] != "Organization"):
        by_origin = defaultdict(set)
        for ref in refs:
            by_origin[origins[ref]].add(ref)
        if any(len(items) != 1 for items in by_origin.values()):
            continue
        ordered = sorted(refs, key=lambda ref: (origins[ref], int(ref[1:])))
        for ref in ordered[1:]:
            left, right = root(ordered[0]), root(ref)
            if left == right:
                continue
            if chunk_ids[left] & chunk_ids[right]:
                continue
            class_type = key[0]
            if any(
                (class_type, predicate) not in MULTI_VALUED_PROPERTIES
                and values[left][predicate]
                and values[right][predicate]
                and values[left][predicate] != values[right][predicate]
                for predicate in values[left].keys() | values[right].keys()
            ):
                continue
            left_orgs = {root(ref) for ref in affiliations[left]}
            right_orgs = {root(ref) for ref in affiliations[right]}
            if left_orgs and right_orgs and left_orgs != right_orgs:
                continue
            parent[right] = left
            chunk_ids[left].update(chunk_ids[right])
            affiliations[left].update(affiliations[right])
            for predicate, items in values[right].items():
                values[left][predicate].update(items)

    # 원문 근거를 먼저 검증한 뒤 validate_extraction이 중복 값과 근거를 합친다.
    # 여기서 미리 합치면 잘못된 근거 하나가 정상 후보까지 탈락시킬 수 있다.
    return ExtractionResult(
        entities=[entity for entity in result.entities if root(entity.ref) == entity.ref],
        facts=[
            fact.model_copy(update={"entity_ref": root(fact.entity_ref)}) for fact in result.facts
        ],
        relations=[
            relation.model_copy(
                update={
                    "subject_ref": root(relation.subject_ref),
                    "object_ref": root(relation.object_ref),
                }
            )
            for relation in result.relations
        ],
        entity_evidence=[
            link.model_copy(update={"entity_ref": root(link.entity_ref)})
            for link in result.entity_evidence
        ],
    )
