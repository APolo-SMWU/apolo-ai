import json
from datetime import UTC, datetime
from uuid import uuid4

from apolo.content_selection.rules import ContentSelection
from apolo.contracts.extraction import (
    EntityCandidate,
    EntityEvidenceCandidate,
    ExtractionResult,
    FactCandidate,
)
from apolo.contracts.knowledge import (
    ActiveKnowledgeEntity,
    ActiveKnowledgeFact,
    ActiveKnowledgeGraph,
    ActiveKnowledgeRelation,
)
from apolo.contracts.source import CollectedSource, Evidence, EvidenceCandidate
from apolo.extraction.evidence import validate_source_evidence
from apolo.extraction.validation import validate_extraction
from apolo.graph_b.prompt import build_content_generation_prompt


def test_entity_evidence_is_validated_and_deduplicated_per_work_activity():
    result = validate_extraction(
        ExtractionResult(
            entities=[
                EntityCandidate(ref="e1", class_type="Work"),
                EntityCandidate(ref="e2", class_type="Activity"),
                EntityCandidate(ref="e3", class_type="Organization"),
            ],
            facts=[
                FactCandidate(
                    entity_ref="e1",
                    predicate="title",
                    value="APolo",
                    evidence_refs=["notion.block:work"],
                    confidence=0.99,
                ),
                FactCandidate(
                    entity_ref="e2",
                    predicate="name",
                    value="COTATO",
                    evidence_refs=["notion.block:activity"],
                    confidence=0.99,
                ),
                FactCandidate(
                    entity_ref="e3",
                    predicate="name",
                    value="COTATO",
                    evidence_refs=["notion.block:organization"],
                    confidence=0.99,
                ),
            ],
            entity_evidence=[
                EntityEvidenceCandidate(
                    entity_ref="e1",
                    evidence_refs=["notion.block:work", "notion.block:details"],
                ),
                EntityEvidenceCandidate(entity_ref="e1", evidence_refs=["notion.block:details"]),
                EntityEvidenceCandidate(entity_ref="e2", evidence_refs=["notion.block:activity"]),
                EntityEvidenceCandidate(
                    entity_ref="e3", evidence_refs=["notion.block:organization"]
                ),
            ],
        )
    )

    assert [item.entity_ref for item in result.result.entity_evidence] == ["e1", "e2"]
    assert result.result.entity_evidence[0].evidence_refs == [
        "notion.block:work",
        "notion.block:details",
    ]
    assert any(issue.code == "INVALID_ENTITY_EVIDENCE_CLASS" for issue in result.issues)


def test_source_validation_drops_entity_evidence_from_another_source():
    source = CollectedSource(
        source_type="notion",
        source_key="notion:page:sample",
        source_url="https://example.com/page",
        content="APolo contribution",
        evidence_candidates=[
            EvidenceCandidate(snippet="APolo contribution", locator="notion.block:work")
        ],
    )
    extraction = ExtractionResult(
        entities=[EntityCandidate(ref="e1", class_type="Work")],
        facts=[
            FactCandidate(
                entity_ref="e1",
                predicate="title",
                value="APolo",
                evidence_refs=["notion.block:work"],
                confidence=0.99,
            )
        ],
        entity_evidence=[
            EntityEvidenceCandidate(
                entity_ref="e1", evidence_refs=["notion.block:work", "notion.block:other"]
            )
        ],
    )

    checked = validate_source_evidence(extraction, source)

    assert checked.result.entity_evidence == []
    assert any(issue.path == "entity_evidence[0]" for issue in checked.issues)


def test_graph_b_prompt_contains_work_entity_evidence():
    now = datetime.now(UTC)
    graph_id, entity_id = uuid4(), uuid4()
    entity_evidence = Evidence(
        id=uuid4(),
        source_document_id=uuid4(),
        source_content_hash="abc123",
        snippet="공통 API 모듈 설계와 GET·POST·PUT 요청 처리",
        locator="notion.block:work-details",
        created_at=now,
    )
    entity = ActiveKnowledgeEntity(
        id=entity_id,
        graph_id=graph_id,
        class_type="Work",
        created_at=now,
        updated_at=now,
        evidence=[entity_evidence],
    )
    graph = ActiveKnowledgeGraph(
        id=graph_id,
        user_id=991007,
        ontology_schema_version="2.0",
        version=1,
        created_at=now,
        updated_at=now,
        entities=[entity],
    )

    prompt = build_content_generation_prompt(
        ContentSelection(graph=graph, selected_classes=frozenset({"Work"}))
    )

    assert entity_evidence.snippet in prompt.user
    assert '"evidence_refs": ["e1"]' in prompt.user
    assert "해당 Work의 entity evidence와 Fact·Relation" in prompt.system


def test_graph_b_prompt_deduplicates_evidence_and_preserves_its_references():
    now = datetime.now(UTC)
    graph_id, work_id, skill_id = uuid4(), uuid4(), uuid4()
    document_id = uuid4()
    evidence = Evidence(
        id=uuid4(),
        source_document_id=document_id,
        source_content_hash="same-source-version",
        snippet="README 원문 근거가 여러 KG 항목에 연결됨",
        locator="github.readme",
        created_at=now,
    )
    same_text_from_another_source = Evidence(
        id=uuid4(),
        source_document_id=uuid4(),
        source_content_hash="different-source-version",
        snippet=evidence.snippet,
        locator=evidence.locator,
        created_at=now,
    )
    graph = ActiveKnowledgeGraph(
        id=graph_id,
        user_id=991007,
        ontology_schema_version="2.0",
        version=1,
        created_at=now,
        updated_at=now,
        entities=[
            ActiveKnowledgeEntity(
                id=work_id,
                graph_id=graph_id,
                class_type="Work",
                created_at=now,
                updated_at=now,
                evidence=[evidence],
            ),
            ActiveKnowledgeEntity(
                id=skill_id,
                graph_id=graph_id,
                class_type="Skill",
                created_at=now,
                updated_at=now,
                evidence=[evidence, same_text_from_another_source],
            ),
        ],
        facts=[
            ActiveKnowledgeFact(
                id=uuid4(),
                entity_id=work_id,
                predicate="title",
                value="Evidence compaction",
                value_type="string",
                origin="extracted",
                provenance="source",
                evidence=[evidence],
                updated_at=now,
            )
        ],
        relations=[
            ActiveKnowledgeRelation(
                id=uuid4(),
                graph_id=graph_id,
                subject_entity_id=work_id,
                predicate="usesSkill",
                object_entity_id=skill_id,
                origin="extracted",
                provenance="source",
                evidence=[evidence],
                updated_at=now,
            )
        ],
    )

    prompt = build_content_generation_prompt(
        ContentSelection(graph=graph, selected_classes=frozenset({"Work", "Skill"}))
    )
    graph_json = prompt.user.split("선별된 현재 유효 KG(JSON):\n", 1)[1]
    payload = json.loads(graph_json)
    evidence_ref, other_source_ref = [item["ref"] for item in payload["evidence_catalog"]]

    assert len(payload["evidence_catalog"]) == 2
    assert prompt.user.count(evidence.snippet) == 2
    assert payload["entities"][0]["evidence_refs"] == [evidence_ref]
    assert payload["entities"][1]["evidence_refs"] == [evidence_ref, other_source_ref]
    assert payload["facts"][0]["evidence_refs"] == [evidence_ref]
    assert payload["relations"][0]["evidence_refs"] == [evidence_ref]
