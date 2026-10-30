from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from contracts import AnswerResult, Evidence, StatisticalResult
from rag.generate import generate_answer_from_evidence
from rag.retrieve import retrieve_all_evidences


class GraphState(TypedDict):
    tech_id: str
    question: str
    top_k: int
    evidences: list[Evidence]
    statistical_result: StatisticalResult | None
    answer_result: AnswerResult | None


def retrieve_node(state: GraphState) -> dict[str, Any]:
    evidences, stat = retrieve_all_evidences(
        tech_id=state["tech_id"], query=state["question"], top_k=state.get("top_k", 4)
    )
    return {"evidences": evidences, "statistical_result": stat}


def generate_node(state: GraphState) -> dict[str, Any]:
    answer = generate_answer_from_evidence(
        question=state["question"],
        evidences=state["evidences"],
        stat=state.get("statistical_result"),
    )
    return {"answer_result": answer}


def build_rag_graph():
    builder = StateGraph(GraphState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)

    # 2개 노드 단방향 파이프라인
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    return builder.compile()


# 싱글톤 그래프 인스턴스
rag_pipeline = build_rag_graph()
