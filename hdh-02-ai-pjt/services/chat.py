from contracts import AnswerResult
from rag.graph import rag_pipeline


def ask_technology_question(tech_id: str, question: str) -> AnswerResult:
    initial_state = {
        "tech_id": tech_id,
        "question": question,
        "top_k": 4,
        "evidences": [],
        "statistical_result": None,
        "answer_result": None,
    }

    final_state = rag_pipeline.invoke(initial_state)
    return final_state["answer_result"]
