"""선별된 KG에서 포트폴리오 콘텐츠를 만들기 위한 provider 독립 프롬프트"""

import json
from dataclasses import dataclass

from apolo.content_selection.rules import ContentSelection
from apolo.contracts.content import graph_b_output_json_schema
from apolo.graph_b.prompts import BLOCK_PROMPTS, COMMON_PROMPT


@dataclass(frozen=True)
class ContentGenerationPrompt:
    """Graph B LLM에 전달할 system·user 메시지"""

    system: str
    user: str


def build_content_generation_prompt(
    selection: ContentSelection, requirements: str = ""
) -> ContentGenerationPrompt:
    """선별된 KG와 요구사항을 콘텐츠 생성 요청으로 변환"""
    graph_payload = selection.graph.model_dump(mode="json")
    block_prompts = [
        BLOCK_PROMPTS[class_type]
        for class_type in sorted(selection.selected_classes)
        if class_type in BLOCK_PROMPTS
    ]
    system = "\n\n".join([COMMON_PROMPT, *block_prompts])
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
