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
    source: CollectedSource, quote: str
) -> list[EvidenceCandidate]:
    """인용문을 포함하는 원문 근거 조각을 모두 반환"""
    if not quote.strip() or quote not in source.content:
        return []
    return [
        candidate
        for candidate in source.evidence_candidates
        if candidate.snippet in source.content and quote in candidate.snippet
    ]


def validate_source_evidence(
    extraction: ExtractionResult, source: CollectedSource
) -> SourceEvidenceValidation:
    """온톨로지 검증 전에 근거가 없는 Fact·Relation 후보 제외"""
    issues: list[ExtractionIssue] = []
    facts = []
    for index, fact in enumerate(extraction.facts):
        if matching_source_evidence(source, fact.evidence):
            facts.append(fact)
        else:
            issues.append(
                ExtractionIssue(
                    code="UNSUPPORTED_EVIDENCE",
                    path=f"facts[{index}]",
                    message="인용문을 수집 원문의 근거 조각에서 찾지 못했습니다.",
                )
            )

    relations = []
    for index, relation in enumerate(extraction.relations):
        if matching_source_evidence(source, relation.evidence):
            relations.append(relation)
        else:
            issues.append(
                ExtractionIssue(
                    code="UNSUPPORTED_EVIDENCE",
                    path=f"relations[{index}]",
                    message="인용문을 수집 원문의 근거 조각에서 찾지 못했습니다.",
                )
            )

    return SourceEvidenceValidation(
        result=ExtractionResult(
            entities=extraction.entities,
            facts=facts,
            relations=relations,
        ),
        issues=issues,
    )
