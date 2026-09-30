"""Graph B에 전달할 최신 KG와 사용자 요구사항을 준비한다."""

from collections.abc import Collection
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
    connection: psycopg.Connection,
    user_id: int,
    requirements: str,
    *,
    source_keys: Collection[str] | None = None,
) -> GraphBInput | None:
    """현재 요청 Source 범위의 active KG를 조회해 Graph B 입력으로 변환"""
    if source_keys is None:
        graph = load_active_knowledge_graph(connection, user_id)
    else:
        graph = load_active_knowledge_graph(connection, user_id, source_keys=source_keys)
    if graph is None:
        return None
    return GraphBInput(graph=graph, requirements=requirements.strip())
