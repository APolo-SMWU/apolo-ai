"""선별된 KG에서 포트폴리오 콘텐츠를 만들기 위한 provider 독립 프롬프트"""

import json
from dataclasses import dataclass

from apolo.content_selection.rules import ContentSelection
from apolo.contracts.content import graph_b_output_json_schema
from apolo.graph_b.prompts import BLOCK_PROMPTS, COMMON_PROMPT
from apolo.graph_b.prompts.about import ABOUT_PROMPT


@dataclass(frozen=True)
class ContentGenerationPrompt:
    """Graph B LLM에 전달할 system·user 메시지"""

    system: str
    user: str


def _compact_graph_payload(selection: ContentSelection) -> dict[str, object]:
    """프롬프트에서 반복되는 원문 evidence를 카탈로그로 모은다."""
    payload = selection.graph.model_dump(mode="json")
    evidence_by_content: dict[tuple[str, str, str, str], str] = {}
    evidence_catalog: list[dict[str, str]] = []

    for collection_name in ("entities", "facts", "relations"):
        for item in payload[collection_name]:
            evidence_refs: list[str] = []
            for evidence in item.pop("evidence", []):
                key = (
                    evidence["source_document_id"],
                    evidence["source_content_hash"],
                    evidence["locator"],
                    evidence["snippet"],
                )
                ref = evidence_by_content.get(key)
                if ref is None:
                    ref = f"e{len(evidence_catalog) + 1}"
                    evidence_by_content[key] = ref
                    evidence_catalog.append(
                        {
                            "ref": ref,
                            "source_document_id": key[0],
                            "source_content_hash": key[1],
                            "locator": key[2],
                            "snippet": key[3],
                        }
                    )
                if ref not in evidence_refs:
                    evidence_refs.append(ref)
            item["evidence_refs"] = evidence_refs

    payload["evidence_catalog"] = evidence_catalog
    return payload


def build_content_generation_prompt(
    selection: ContentSelection, requirements: str = ""
) -> ContentGenerationPrompt:
    """선별된 KG와 요구사항을 콘텐츠 생성 요청으로 변환"""
    graph_payload = _compact_graph_payload(selection)
    block_prompts = [
        BLOCK_PROMPTS[class_type]
        for class_type in sorted(selection.selected_classes)
        if class_type in BLOCK_PROMPTS
    ]
    system = "\n\n".join([COMMON_PROMPT, ABOUT_PROMPT, *block_prompts])
    user = "\n\n".join(
        [
            "Graph B 출력 JSON Schema:\n"
            + json.dumps(graph_b_output_json_schema(), ensure_ascii=False, sort_keys=True),
            "선별된 콘텐츠 Entity 유형:\n"
            + json.dumps(sorted(selection.selected_classes), ensure_ascii=False),
            "사용자 요구사항:\n" + (requirements.strip() or "없음"),
            "선별된 현재 유효 KG(JSON):\n"
            + json.dumps(graph_payload, ensure_ascii=False, sort_keys=True),
        ]
    )
    return ContentGenerationPrompt(system=system, user=user)
