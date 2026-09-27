"""LangSmith 평가 입력을 실제 Graph B 선별·검증 흐름에 연결."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from apolo.contracts.content import GraphBOutput
from apolo.contracts.extraction import (
    EntityCandidate,
    ExtractionResult,
    FactCandidate,
    RelationCandidate,
)
from apolo.contracts.generate import (
    TimelineBlock,
    TimelineItem,
    WorkItem,
    WorksBlock,
)
from apolo.contracts.source import CollectedSource, EvidenceCandidate
from apolo.db.connection import connect_db
from apolo.db.graph_a import apply_source_extraction
from apolo.db.knowledge import load_active_knowledge_graph
from apolo.db.source import load_source, persist_collected_source
from apolo.extraction.evidence import validate_source_evidence
from apolo.extraction.validation import validate_extraction
from apolo.graph_a.processing import process_pending_sources
from apolo.graph_b.service import ContentGenerator, generate_graph_b_content
from apolo.source_collection import StoredPublicCollection
from evals.fixtures import EXPERIENCE_ID, WORK_ID, build_synthetic_graph


def evaluation_target(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Dataset의 target·environment에 맞는 Graph A·Graph B 평가로 분기"""
    target = _required_text(inputs.get("target"), "target")
    environment = _required_text(inputs.get("environment"), "environment")
    if target == "graph_b":
        return graph_b_target(inputs)
    if target == "graph_a" and environment == "local":
        return graph_a_local_target(inputs)
    if target == "graph_a" and environment == "database":
        case_id = _required_text(inputs.get("caseId"), "caseId")
        if case_id == "graph-a-source-conflict":
            return graph_a_database_target(inputs)
        if case_id == "graph-a-failed-retry":
            return graph_a_failed_retry_target(inputs)
    raise ValueError(
        f"지원하지 않는 평가 target입니다: target={target}, environment={environment}"
    )


def graph_b_target(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """LangSmith 한 건의 입력을 Graph B 결과 요약으로 변환"""
    case_id = _required_text(inputs.get("caseId"), "caseId")
    payload = inputs.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("payload는 객체여야 합니다.")

    requirements = str(payload.get("requirements", ""))
    result = generate_graph_b_content(
        build_synthetic_graph(),
        requirements,
        _SyntheticContentGenerator(case_id, payload),
    )
    return {
        "selectedBlockTypes": [block.type for block in result.output.blocks],
        "outputValid": result.is_valid,
        "issueCodes": [issue.code for issue in result.issues],
        "emptyBlocks": any(_is_empty_block(block) for block in result.output.blocks),
    }


def graph_a_local_target(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """LangSmith 정상 Source 케이스를 Graph A 검증 함수에 연결"""
    case_id = _required_text(inputs.get("caseId"), "caseId")
    if case_id != "graph-a-normal-source":
        raise ValueError(f"Graph A local target이 지원하지 않는 케이스입니다: {case_id}")
    payload = inputs.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("payload는 객체여야 합니다.")

    content = _required_text(payload.get("content"), "content")
    evidence = _required_text(payload.get("evidence"), "evidence")
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
    issues = [*grounded.issues, *checked.issues]
    return {
        "warningCodes": [issue.code for issue in issues],
        "factValues": [str(fact.value) for fact in checked.result.facts],
        "candidateValidated": not issues,
    }


def graph_a_database_target(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Source 변경 케이스를 PostgreSQL Graph A 저장 경계에 연결"""
    case_id = _required_text(inputs.get("caseId"), "caseId")
    if case_id != "graph-a-source-conflict":
        raise ValueError(f"Graph A database target이 지원하지 않는 케이스입니다: {case_id}")

    graph_id = uuid4()
    user_id = 1_900_000_000 + graph_id.int % 100_000_000
    now = datetime(2026, 9, 27, tzinfo=UTC)
    source_v1 = _source_version("frontend")
    source_v2 = _source_version("backend")
    try:
        with connect_db() as connection:
            with connection.transaction():
                connection.execute(
                    "INSERT INTO ai.knowledge_graphs "
                    "VALUES (%s,%s,'1.1',0,%s,%s)",
                    (graph_id, user_id, now, now),
                )
                stored_v1 = persist_collected_source(
                    connection,
                    graph_id,
                    source_v1,
                    fetched_at=now,
                )
                apply_source_extraction(
                    connection,
                    graph_id,
                    0,
                    source_v1,
                    stored_v1,
                    _source_extraction("frontend", source_v1.source_url),
                    now=now,
                )
                stored_v2 = persist_collected_source(
                    connection,
                    graph_id,
                    source_v2,
                    fetched_at=now.replace(hour=1),
                )
                apply_source_extraction(
                    connection,
                    graph_id,
                    1,
                    source_v2,
                    stored_v2,
                    _source_extraction("backend", source_v2.source_url),
                    now=now.replace(hour=2),
                )
                graph = load_active_knowledge_graph(connection, user_id)
                if graph is None:
                    raise ValueError("평가용 KG를 조회하지 못했습니다.")
                active_values = [
                    str(fact.value) for fact in graph.facts if fact.predicate == "title"
                ]
                all_values = [
                    row[0]
                    for row in connection.execute(
                        "SELECT f.value #>> '{}' FROM ai.facts f "
                        "JOIN ai.entities e ON e.id=f.entity_id "
                        "WHERE e.graph_id=%s AND f.predicate='title'",
                        (graph_id,),
                    ).fetchall()
                ]
                result = {
                    "activeFactValues": active_values,
                    "excludedFactValues": [
                        value for value in all_values if value not in active_values
                    ],
                    "oldEvidenceIgnored": "frontend" not in active_values,
                }
                raise _RollbackEvaluation(result)
    except _RollbackEvaluation as rollback:
        return rollback.result


def graph_a_failed_retry_target(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """추출 실패 후 같은 원문을 다시 Graph A에 반영하는 흐름에 연결"""
    case_id = _required_text(inputs.get("caseId"), "caseId")
    if case_id != "graph-a-failed-retry":
        raise ValueError(f"Graph A retry target이 지원하지 않는 케이스입니다: {case_id}")

    graph_id = uuid4()
    user_id = 1_900_000_000 + graph_id.int % 100_000_000
    now = datetime(2026, 9, 27, tzinfo=UTC)
    source = _source_version("backend")
    try:
        with connect_db() as connection:
            with connection.transaction():
                connection.execute(
                    "INSERT INTO ai.knowledge_graphs "
                    "VALUES (%s,%s,'1.1',0,%s,%s)",
                    (graph_id, user_id, now, now),
                )
                first_stored = persist_collected_source(
                    connection,
                    graph_id,
                    source,
                    fetched_at=now,
                )
                first = process_pending_sources(
                    connection,
                    graph_id,
                    StoredPublicCollection([source], [first_stored], []),
                    _RetryExtractor(fail=True),
                    now=now,
                )
                failed_document, _ = load_source(
                    connection,
                    graph_id,
                    source.source_key,
                )
                if failed_document is None:
                    raise ValueError("실패한 Source 상태를 조회하지 못했습니다.")

                retry_stored = persist_collected_source(
                    connection,
                    graph_id,
                    source,
                    fetched_at=now.replace(hour=1),
                )
                second = process_pending_sources(
                    connection,
                    graph_id,
                    StoredPublicCollection([source], [retry_stored], []),
                    _RetryExtractor(fail=False),
                    now=now.replace(hour=2),
                )
                retried_document, retried_snapshot = load_source(
                    connection,
                    graph_id,
                    source.source_key,
                )
                if retried_document is None or retried_snapshot is None:
                    raise ValueError("재시도한 Source 상태를 조회하지 못했습니다.")
                result = {
                    "firstWarningCodes": [warning.code for warning in first.warnings],
                    "reprocessOnNextRequest": (
                        retry_stored.content_changed is False
                        and len(second.writes) == 1
                    ),
                    "processedHashAfterRetry": (
                        retried_document.processed_content_hash
                        == retried_snapshot.content_hash
                    ),
                }
                raise _RollbackEvaluation(result)
    except _RollbackEvaluation as rollback:
        return rollback.result


class _RollbackEvaluation(Exception):
    """평가용 DB 변경을 rollback한 뒤 결과만 반환하는 내부 제어 예외"""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__()
        self.result = result


class _RetryExtractor:
    """재시도 평가에서 첫 호출만 실패시키는 합성 Extractor"""

    def __init__(self, *, fail: bool) -> None:
        self._fail = fail

    def extract(self, source: CollectedSource) -> ExtractionResult:
        if self._fail:
            raise RuntimeError("synthetic extraction failure")
        return _source_extraction("backend", source.source_url)


def _source_version(title: str) -> CollectedSource:
    content = f"APolo {title} project at https://github.com/example/apolo"
    return CollectedSource(
        source_type="github",
        source_key="github:repository:synthetic-conflict",
        source_url="https://github.com/example/apolo",
        content=content,
        evidence_candidates=[EvidenceCandidate(snippet=content, locator="github.readme")],
    )


def _source_extraction(title: str, source_url: str) -> ExtractionResult:
    return ExtractionResult(
        entities=[EntityCandidate(ref="e1", class_type="Work")],
        facts=[
            FactCandidate(
                entity_ref="e1",
                predicate="title",
                value=title,
                evidence=title,
                confidence=1.0,
            ),
            FactCandidate(
                entity_ref="e1",
                predicate="url",
                value=source_url,
                evidence=source_url,
                confidence=1.0,
            ),
        ],
    )


class _SyntheticContentGenerator(ContentGenerator):
    """평가 케이스별 고정 출력을 반환하는 Graph B generator"""

    def __init__(self, case_id: str, payload: Mapping[str, Any]) -> None:
        self._case_id = case_id
        self._payload = payload

    def generate(self, selection, requirements: str = "") -> GraphBOutput:
        del requirements
        if self._case_id == "graph-b-project-selection":
            entity_id = str(WORK_ID)
            return GraphBOutput(
                blocks=[
                    WorksBlock(
                        items=[
                            WorkItem(
                                entity_id=entity_id,
                                kind="project",
                                title="APolo",
                                description="Personal Knowledge Graph project",
                            )
                        ]
                    )
                ]
            )
        if self._case_id == "graph-b-partial-generation":
            return GraphBOutput(
                blocks=[
                    TimelineBlock(
                        type="experience",
                        items=[
                            TimelineItem(
                                entity_id=str(EXPERIENCE_ID),
                                start_date="",
                                organization="",
                                role="Developer",
                            )
                        ],
                    )
                ]
            )
        if self._case_id == "graph-b-invalid-entity-reference":
            entity_id = _required_text(self._payload.get("generatedEntityId"), "generatedEntityId")
            return GraphBOutput(
                blocks=[
                    WorksBlock(
                        items=[
                            WorkItem(
                                entity_id=entity_id,
                                kind="project",
                                title="Unknown",
                                description="Entity does not exist in the KG",
                            )
                        ]
                    )
                ]
            )
        raise ValueError(f"Graph B target이 지원하지 않는 케이스입니다: {self._case_id}")


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}은 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _is_empty_block(block: Any) -> bool:
    if isinstance(block, TimelineBlock | WorksBlock):
        return not block.items
    return False
