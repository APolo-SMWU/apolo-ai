"""외부 API 없이 실행하는 deterministic Graph A·Graph B 평가기."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from apolo.content_selection.rules import select_relevant_knowledge
from apolo.contracts.content import GraphBOutput
from apolo.contracts.extraction import (
    EntityCandidate,
    ExtractionResult,
    FactCandidate,
    RelationCandidate,
)
from apolo.contracts.generate import TimelineBlock, TimelineItem, WorkItem, WorksBlock
from apolo.contracts.knowledge import (
    ActiveKnowledgeEntity,
    ActiveKnowledgeGraph,
    ActiveKnowledgeRelation,
)
from apolo.contracts.source import CollectedSource, EvidenceCandidate
from apolo.extraction.evidence import validate_source_evidence
from apolo.extraction.validation import validate_extraction
from apolo.graph_b.validation import validate_graph_b_output
from evals.cases import EVALUATION_CASES, EvaluationCase, load_evaluation_cases

_NOW = datetime(2026, 9, 27, tzinfo=UTC)
_GRAPH_ID = UUID("00000000-0000-0000-0000-000000000001")
_PERSON_ID = UUID("00000000-0000-0000-0000-000000000002")
_WORK_ID = UUID("00000000-0000-0000-0000-000000000003")
_EXPERIENCE_ID = UUID("00000000-0000-0000-0000-000000000004")


@dataclass(frozen=True)
class LocalEvaluationResult:
    """로컬 평가 한 건의 통과 여부와 설명"""

    case_id: str
    passed: bool
    detail: str


def run_local_evaluations(
    cases: tuple[EvaluationCase, ...] = EVALUATION_CASES,
) -> tuple[LocalEvaluationResult, ...]:
    """environment=local인 케이스만 deterministic 함수로 평가"""
    return tuple(_evaluate_case(case) for case in cases if case.environment == "local")


def _evaluate_case(case: EvaluationCase) -> LocalEvaluationResult:
    try:
        if case.case_id == "graph-a-normal-source":
            return _evaluate_normal_source(case)
        if case.case_id == "graph-b-project-selection":
            return _evaluate_project_selection(case)
        if case.case_id == "graph-b-partial-generation":
            return _evaluate_partial_generation(case)
        if case.case_id == "graph-b-invalid-entity-reference":
            return _evaluate_invalid_reference(case)
        raise ValueError(f"로컬 평가기가 지원하지 않는 케이스입니다: {case.case_id}")
    except Exception as error:
        return LocalEvaluationResult(case.case_id, False, f"{type(error).__name__}: {error}")


def _evaluate_normal_source(case: EvaluationCase) -> LocalEvaluationResult:
    content = str(case.input["content"])
    evidence = str(case.input["evidence"])
    source = CollectedSource(
        source_type="github",
        source_key="github:repository:synthetic",
        source_url="https://github.com/example/synthetic",
        content=content,
        evidence_candidates=[EvidenceCandidate(snippet=evidence, locator="github.readme")],
    )
    extraction = ExtractionResult(
        entities=[
            EntityCandidate(ref="e1", class_type="Work"),
            EntityCandidate(ref="e2", class_type="Skill"),
        ],
        facts=[
            FactCandidate(
                entity_ref="e1",
                predicate="title",
                value="APolo",
                evidence="APolo",
                confidence=1.0,
            ),
            FactCandidate(
                entity_ref="e2",
                predicate="name",
                value="Python",
                evidence="Python",
                confidence=1.0,
            ),
        ],
        relations=[
            RelationCandidate(
                subject_ref="e1",
                predicate="usesSkill",
                object_ref="e2",
                evidence=evidence,
                confidence=1.0,
            )
        ],
    )
    grounded = validate_source_evidence(extraction, source)
    checked = validate_extraction(grounded.result)
    values = [str(fact.value) for fact in checked.result.facts]
    expected_values = [str(value) for value in case.expected["factValues"]]
    expected_valid = bool(case.expected["candidateValidated"])
    passed = (not grounded.issues and not checked.issues) == expected_valid
    passed = passed and values == expected_values
    detail = f"facts={values}, issues={len(grounded.issues) + len(checked.issues)}"
    return LocalEvaluationResult(case.case_id, passed, detail)


def _evaluate_project_selection(case: EvaluationCase) -> LocalEvaluationResult:
    graph = _synthetic_graph()
    selection = select_relevant_knowledge(graph, str(case.input["requirements"]))
    work = next(entity for entity in selection.graph.entities if entity.id == _WORK_ID)
    output = GraphBOutput(
        blocks=[
            WorksBlock(
                items=[
                    WorkItem(
                        entity_id=str(work.id),
                        kind="project",
                        title="APolo",
                        description="Personal Knowledge Graph project",
                    )
                ]
            )
        ]
    )
    issues = validate_graph_b_output(output, selection.graph)
    block_types = [block.type for block in output.blocks]
    expected_types = [str(value) for value in case.expected["selectedBlockTypes"]]
    expected_valid = bool(case.expected["outputValid"])
    passed = (not issues) == expected_valid
    passed = passed and block_types == expected_types and "Work" in selection.selected_classes
    detail = (
        f"selected={sorted(selection.selected_classes)}, "
        f"blocks={block_types}, issues={len(issues)}"
    )
    return LocalEvaluationResult(case.case_id, passed, detail)


def _evaluate_partial_generation(case: EvaluationCase) -> LocalEvaluationResult:
    graph = _synthetic_graph()
    selection = select_relevant_knowledge(graph, str(case.input["requirements"]))
    output = GraphBOutput(
        blocks=[
            TimelineBlock(
                type="experience",
                items=[
                    TimelineItem(
                        entity_id=str(_EXPERIENCE_ID),
                        start_date="",
                        organization="",
                        role="Developer",
                    )
                ],
            )
        ]
    )
    issues = validate_graph_b_output(output, selection.graph)
    block_types = [block.type for block in output.blocks]
    expected_types = [str(value) for value in case.expected["selectedBlockTypes"]]
    expected_valid = bool(case.expected["outputValid"])
    empty_blocks = any(not block.items for block in output.blocks)
    expected_empty_blocks = bool(case.expected["emptyBlocks"])
    passed = (
        (not issues) == expected_valid
        and block_types == expected_types
        and "Experience" in selection.selected_classes
        and empty_blocks == expected_empty_blocks
    )
    detail = (
        f"selected={sorted(selection.selected_classes)}, "
        f"blocks={block_types}, issues={len(issues)}"
    )
    return LocalEvaluationResult(case.case_id, passed, detail)


def _evaluate_invalid_reference(case: EvaluationCase) -> LocalEvaluationResult:
    graph = _synthetic_graph()
    selection = select_relevant_knowledge(graph)
    output = GraphBOutput(
        blocks=[
            WorksBlock(
                items=[
                    WorkItem(
                        entity_id=str(case.input["generatedEntityId"]),
                        kind="project",
                        title="Unknown",
                        description="Entity does not exist in the KG",
                    )
                ]
            )
        ]
    )
    issues = validate_graph_b_output(output, selection.graph)
    issue_codes = [issue.code for issue in issues]
    expected_codes = [str(value) for value in case.expected["issueCodes"]]
    expected_valid = bool(case.expected["outputValid"])
    passed = (not issues) == expected_valid and issue_codes == expected_codes
    detail = f"valid={not issues}, issue_codes={issue_codes}"
    return LocalEvaluationResult(case.case_id, passed, detail)


def _synthetic_graph() -> ActiveKnowledgeGraph:
    entities = [
        ActiveKnowledgeEntity(
            id=_PERSON_ID,
            graph_id=_GRAPH_ID,
            class_type="Person",
            created_at=_NOW,
            updated_at=_NOW,
        ),
        ActiveKnowledgeEntity(
            id=_WORK_ID,
            graph_id=_GRAPH_ID,
            class_type="Work",
            created_at=_NOW,
            updated_at=_NOW,
        ),
        ActiveKnowledgeEntity(
            id=_EXPERIENCE_ID,
            graph_id=_GRAPH_ID,
            class_type="Experience",
            created_at=_NOW,
            updated_at=_NOW,
        ),
    ]
    relations = [
        ActiveKnowledgeRelation(
            id=UUID("00000000-0000-0000-0000-000000000011"),
            graph_id=_GRAPH_ID,
            subject_entity_id=_PERSON_ID,
            predicate="participatedIn",
            object_entity_id=_WORK_ID,
            origin="user",
            provenance="profile",
            updated_at=_NOW,
        ),
        ActiveKnowledgeRelation(
            id=UUID("00000000-0000-0000-0000-000000000012"),
            graph_id=_GRAPH_ID,
            subject_entity_id=_PERSON_ID,
            predicate="hasExperience",
            object_entity_id=_EXPERIENCE_ID,
            origin="user",
            provenance="profile",
            updated_at=_NOW,
        ),
    ]
    return ActiveKnowledgeGraph(
        id=_GRAPH_ID,
        user_id=1,
        ontology_schema_version="1.1",
        version=1,
        created_at=_NOW,
        updated_at=_NOW,
        entities=entities,
        relations=relations,
    )


def main() -> int:
    """로컬 평가 결과를 출력하고 실패가 있으면 1을 반환"""
    cases = load_evaluation_cases()
    results = run_local_evaluations(cases)
    skipped = len(cases) - len(results)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.case_id}: {result.detail}")
    print(f"evaluated={len(results)} skipped={skipped}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
