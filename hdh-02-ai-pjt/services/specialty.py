from typing import Any

from contracts import AnswerResult
from data.sqlite_db import DatabaseManager
from rag.graph import rag_pipeline


def analyze_tech_sustainability(tech_id: str) -> dict[str, Any]:
    """선택 기술의 채택-선호 괴리율(Usage vs Admired) 분석 및 RAG 문맥 해석"""
    db = DatabaseManager()
    stat = db.get_statistics(tech_id, year=2026)

    if not stat or stat.usage_pct is None or stat.admired_pct is None:
        return {
            "status": "insufficient",
            "message": "해당 기술은 3대 지표(Usage, Desired, Admired) 데이터가 모두 관측되지 않아 분석이 보류되었습니다.",
        }

    # 지표 갭 및 유형 판별 (결정적 연산)
    usage = stat.usage_pct
    desired = stat.desired_pct or 0.0
    admired = stat.admired_pct

    # 개발자 생태계 유형 판별 규칙
    if usage >= 30.0 and admired >= 60.0:
        segment = "주류 핵심 기술 (High Usage & High Admiration)"
    elif usage >= 30.0 and admired < 50.0:
        segment = "레거시 점유 기술 (High Usage & Low Admiration - 피로도 누적 위험)"
    elif usage < 15.0 and admired >= 65.0:
        segment = "열혈 팬덤 신흥 기술 (Low Usage & High Admiration - 높은 성장 잠재력)"
    else:
        segment = "안정적 범용 기술 (Moderate Usage & Admiration)"

    # RAG 파이프라인으로 배경 해석 질문 수행
    question = (
        f"{stat.technology_name}의 2026년 Usage는 {usage}%, Desired는 {desired}%, Admired는 {admired}%입니다. "
        f"이 수치들을 바탕으로 공식 지표 정의와 표본 한계를 고려하여 기술의 현재 지속성과 시장 위치를 설명해주세요."
    )

    initial_state = {
        "tech_id": tech_id,
        "question": question,
        "top_k": 3,
        "evidences": [],
        "statistical_result": None,
        "answer_result": None,
    }

    graph_res = rag_pipeline.invoke(initial_state)
    answer: AnswerResult = graph_res["answer_result"]

    return {
        "status": "success",
        "tech_name": stat.technology_name,
        "category": stat.category,
        "usage": usage,
        "desired": desired,
        "admired": admired,
        "segment": segment,
        "answer": answer,
    }
