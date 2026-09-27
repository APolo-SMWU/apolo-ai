"""Graph A LangGraph 실행 그래프"""

from langgraph.graph import END, START, StateGraph

from apolo.graph_a.processing import process_pending_sources
from apolo.graph_a.state import GraphAState


def process_sources_node(state: GraphAState) -> dict[str, object]:
    """변경 Source를 추출·검증·저장 service에 전달"""
    result = process_pending_sources(
        state["connection"],
        state["graph_id"],
        state["collection"],
        state["extractor"],
        now=state["now"],
    )
    return {"result": result}


def build_graph_a():
    """Graph A 단일 처리 노드를 컴파일"""
    graph = StateGraph(GraphAState)
    graph.add_node("process_sources", process_sources_node)
    graph.add_edge(START, "process_sources")
    graph.add_edge("process_sources", END)
    return graph.compile()
