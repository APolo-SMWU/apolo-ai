"""추출 후보의 근거 인용을 수집 원문과 대조"""

from dataclasses import dataclass

from apolo.contracts.extraction import ExtractionResult
from apolo.contracts.source import CollectedSource, EvidenceCandidate
from apolo.extraction.validation import ExtractionIssue


@dataclass(frozen=True)
class SourceEvidenceValidation:
    """원문 근거가 확인된 후보와 제외 이유"""

    result: ExtractionResult
    issues: list[ExtractionIssue]


def matching_source_evidence(
    source: CollectedSource, locator: str
) -> list[EvidenceCandidate]:
    """locator가 정확히 일치하는 원문 근거 조각을 반환"""
    if not locator.strip():
        return []
    return [
        candidate
        for candidate in source.evidence_candidates
        if candidate.locator == locator and candidate.snippet in source.content
    ]


def matching_source_evidence_refs(
    source: CollectedSource, locators: list[str]
) -> list[EvidenceCandidate] | None:
    """모든 locator가 근거 후보에 있으면 일치하는 후보 조각을 반환"""
    if not locators:
        return None

    matched: dict[tuple[str, str], EvidenceCandidate] = {}
    for locator in locators:
        candidates = matching_source_evidence(source, locator)
        if not candidates:
            return None
        matched.update(
            {(candidate.snippet, candidate.locator): candidate for candidate in candidates}
        )
    return list(matched.values())


def validate_source_evidence(
    extraction: ExtractionResult, source: CollectedSource
) -> SourceEvidenceValidation:
    """온톨로지 검증 전에 현재 Source에서 찾을 수 없는 근거 후보 제외"""
    issues: list[ExtractionIssue] = []
    facts = []
    for index, fact in enumerate(extraction.facts):
        if matching_source_evidence_refs(source, fact.evidence_refs) is not None:
            facts.append(fact)
        else:
            issues.append(
                ExtractionIssue(
                    code="UNSUPPORTED_EVIDENCE",
                    path=f"facts[{index}]",
                    message="evidence_refs locator를 현재 Source에서 찾지 못했습니다.",
                )
            )

    relations = []
    for index, relation in enumerate(extraction.relations):
        if matching_source_evidence_refs(source, relation.evidence_refs) is not None:
            relations.append(relation)
        else:
            issues.append(
                ExtractionIssue(
                    code="UNSUPPORTED_EVIDENCE",
                    path=f"relations[{index}]",
                    message="evidence_refs locator를 현재 Source에서 찾지 못했습니다.",
                )
            )

    entity_evidence = []
    for index, item in enumerate(extraction.entity_evidence):
        if matching_source_evidence_refs(source, item.evidence_refs) is not None:
            entity_evidence.append(item)
        else:
            issues.append(
                ExtractionIssue(
                    code="UNSUPPORTED_EVIDENCE",
                    path=f"entity_evidence[{index}]",
                    message="evidence_refs locator를 현재 Source에서 찾지 못했습니다.",
                )
            )

    return SourceEvidenceValidation(
        result=ExtractionResult(
            entities=extraction.entities,
            facts=facts,
            relations=relations,
            entity_evidence=entity_evidence,
        ),
        issues=issues,
    )
