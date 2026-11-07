"""외부 원문에서 KG 후보를 제안받기 위한 provider 독립 프롬프트"""

import json
from dataclasses import dataclass

from apolo.contracts.extraction import (
    EXTRACTABLE_PROPERTIES,
    EXTRACTABLE_RELATIONS,
    StructuredExtractionResult,
)
from apolo.contracts.source import CollectedSource
from apolo.extraction.prompts import SOURCE_PROMPTS, SYSTEM_PROMPTS
from apolo.ontology.personal import PROPERTY_VALUES, RELATION_PAIRS


@dataclass(frozen=True)
class ExtractionPrompt:
    """LLM provider에 전달할 system·user 메시지"""

    system: str
    user: str


def build_extraction_prompt(source: CollectedSource) -> ExtractionPrompt:
    """Source 하나를 ExtractionResult 후보 요청으로 변환"""
    source_prompt = SOURCE_PROMPTS.get(source.source_type)
    system = "\n\n".join([*SYSTEM_PROMPTS, *([source_prompt] if source_prompt else [])])
    user = "\n\n".join([_allowed_schema(), _source_section(source)])
    return ExtractionPrompt(system=system, user=user)


def _allowed_schema() -> str:
    """온톨로지에서 추출 가능한 property·값·relation과 응답 JSON Schema"""
    allowed_properties = {
        class_type: sorted(properties) for class_type, properties in EXTRACTABLE_PROPERTIES.items()
    }
    allowed_property_values = {
        f"{class_type}.{predicate}": sorted(values)
        for (class_type, predicate), values in sorted(PROPERTY_VALUES.items())
        if predicate in EXTRACTABLE_PROPERTIES.get(class_type, frozenset())
    }
    allowed_relation_pairs = {
        predicate: [
            {"subjectClass": subject, "objectClass": object_} for subject, object_ in sorted(pairs)
        ]
        for predicate, pairs in sorted(RELATION_PAIRS.items())
        if predicate in EXTRACTABLE_RELATIONS
    }
    return "\n\n".join(
        [
            "## 허용 스키마\nEntity class별 허용 property:\n" + _json(allowed_properties),
            "열거 property별 허용 값:\n" + _json(allowed_property_values),
            "허용 relation predicate:\n"
            + json.dumps(sorted(EXTRACTABLE_RELATIONS), ensure_ascii=False),
            "허용 relation 방향(subjectClass → objectClass):\n" + _json(allowed_relation_pairs),
            "ExtractionResult JSON Schema:\n"
            + _json(StructuredExtractionResult.model_json_schema()),
        ]
    )


def _source_section(source: CollectedSource) -> str:
    """원문 메타데이터·근거 후보·원문. 원문은 신뢰할 수 없는 데이터로 표시한다"""
    metadata = {
        "source_type": source.source_type,
        "source_key": source.source_key,
        "source_url": source.source_url,
        "source_version": source.source_version,
    }
    evidence_candidates = [
        candidate.model_dump(exclude_none=True, exclude_defaults=True)
        for candidate in source.evidence_candidates
    ]
    return "\n\n".join(
        [
            "## Source\n원문 메타데이터:\n" + _json(metadata),
            "근거 후보(evidence_refs는 이 목록의 locator 값 중에서 선택):\n"
            + json.dumps(evidence_candidates, ensure_ascii=False),
            "보조 문맥 locator:\n"
            + json.dumps(source.context_evidence_refs, ensure_ascii=False),
            "신뢰할 수 없는 원문 내용:\n" + source.content,
        ]
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
