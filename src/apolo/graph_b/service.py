"""Graph B의 선별·생성·검증 경계를 하나의 호출로 묶는다."""

from dataclasses import dataclass
from typing import Protocol

from apolo.content_selection.rules import ContentSelection, select_relevant_knowledge
from apolo.contracts.content import GraphBOutput
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.normalization import normalize_graph_b_output
from apolo.graph_b.validation import ContentValidationIssue, validate_graph_b_output


class ContentGenerator(Protocol):
    """선별 결과를 콘텐츠 블록으로 변환하는 클라이언트 계약"""

    def generate(self, selection: ContentSelection, requirements: str = "") -> GraphBOutput: ...


@dataclass(frozen=True)
class GraphBGenerationResult:
    """선별 기준·생성 결과·검증 이슈를 함께 보존"""

    selection: ContentSelection
    output: GraphBOutput
    issues: tuple[ContentValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """검증을 통과해 저장·응답에 사용할 수 있는지 반환"""
        return not self.issues


def generate_graph_b_content(
    graph: ActiveKnowledgeGraph,
    requirements: str,
    generator: ContentGenerator,
) -> GraphBGenerationResult:
    """현재 KG에서 콘텐츠 후보를 선별하고 생성 결과를 같은 후보로 검증"""
    selection = select_relevant_knowledge(graph, requirements)
    output = normalize_graph_b_output(generator.generate(selection, requirements), selection.graph)
    issues = tuple(validate_graph_b_output(output, selection.graph))
    return GraphBGenerationResult(selection=selection, output=output, issues=issues)
