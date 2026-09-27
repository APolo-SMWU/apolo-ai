"""Graph B에 전달할 최신 KG와 사용자 요구사항을 준비한다."""

from dataclasses import dataclass

import psycopg

from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.db.knowledge import load_active_knowledge_graph


@dataclass(frozen=True)
class GraphBInput:
    """Graph B 선별 단계가 읽을 입력"""

    graph: ActiveKnowledgeGraph
    requirements: str


def load_graph_b_input(
    connection: psycopg.Connection, user_id: int, requirements: str
) -> GraphBInput | None:
    """사용자의 최신 active KG를 조회해 Graph B 입력으로 변환"""
    graph = load_active_knowledge_graph(connection, user_id)
    if graph is None:
        return None
    return GraphBInput(graph=graph, requirements=requirements.strip())
