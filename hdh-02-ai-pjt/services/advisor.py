import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL
from data.sqlite_db import DatabaseManager

db = DatabaseManager()


def get_llm():
    return ChatOpenAI(
        model=OPENAI_CHAT_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL
    )


# 1. 프로젝트 맞춤 스택 추천 (100% LLM 사고 기반)
RECOMMEND_PROMPT = """
당신은 수석 소프트웨어 아키텍트이다. 사용자의 프로젝트 요구사항을 분석하여 [언어, 웹 프레임워크, 데이터베이스, 클라우드] 4개 레이어의 최적 기술을 직접 판단하여 설계하라.
단순히 인기 순위로 뽑지 말고, 프로젝트의 목적과 우선가치에 기술적으로 가장 핏이 맞는 조합을 논리적으로 선정하라.

반드시 아래 JSON 형식으로만 응답하라.
출력 형식:
{
  "recommendations": [
    {"layer": "Language", "tech_name": "기술명", "reason": "선정 이유"},
    {"layer": "WebFramework", "tech_name": "기술명", "reason": "선정 이유"},
    {"layer": "Database", "tech_name": "기술명", "reason": "선정 이유"},
    {"layer": "Cloud", "tech_name": "기술명", "reason": "선정 이유"}
  ],
  "overall_review": "이 스택 조합의 시너지 효과 및 종합 아키텍처 총평"
}
"""


def recommend_project_stack(project_type: str, priority: str, constraints: str) -> dict:
    llm = get_llm()
    user_input = f"프로젝트 종류: {project_type}\n최우선 가치: {priority}\n제약/상황: {constraints or '없음'}"

    try:
        res = llm.invoke(
            [SystemMessage(content=RECOMMEND_PROMPT), HumanMessage(content=user_input)]
        )
        raw_text = res.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw_text)
    except Exception:
        data = {
            "recommendations": [],
            "overall_review": "스택 설계 분석 중 오류가 발생했습니다.",
        }

    # LLM이 직접 선정한 기술들의 설문 지표(Usage, Admired)를 백그라운드에서 매핑 (근거 청크용)
    enriched_recommendations = []
    for item in data.get("recommendations", []):
        tname = item.get("tech_name", "")
        # DB에서 이름 일치 여부 확인
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM technology WHERE canonical_name LIKE ? OR technology_id LIKE ?",
                (f"%{tname}%", f"%{tname.lower()}%"),
            )
            t_row = cursor.fetchone()

            stat_info = None
            if t_row:
                stat = db.get_statistics(t_row["technology_id"])
                if stat:
                    stat_info = {"usage": stat.usage_pct, "admired": stat.admired_pct}

        enriched_recommendations.append(
            {
                "layer": item.get("layer", ""),
                "tech_name": tname,
                "reason": item.get("reason", ""),
                "stat": stat_info,
            }
        )

    return {
        "project_type": project_type,
        "priority": priority,
        "recommendations": enriched_recommendations,
        "overall_review": data.get("overall_review", ""),
    }


# 2. 대안 및 마이그레이션 탐색 (100% LLM 사고 기반)
ALTERNATIVE_PROMPT = """
당신은 기술 마이그레이션 전문 컨설턴트이다. 사용자가 제시한 기준 기술에 대해, 실제로 현업에서 진지하게 고려되는 현실적이고 강력한 대안 기술 3~4개를 직접 판단하여 제시하라.
동일 범주의 단순 나열이 아니라, '어떤 상황에서 이 대안으로 갈아탈 만한지' 트레이드오프와 차이점을 명확히 짚어라.

반드시 아래 JSON 형식으로만 응답하라.
출력 형식:
{
  "alternatives": [
    {
      "tech_name": "대안 기술명",
      "tag": "대안의 핵심 포지션 (예: 초고성능, 최신 표준, 개발 생산성 극대화 등)",
      "pros_vs_target": "기준 기술 대비 장점 및 추천 시나리오",
      "cons_or_tradeoff": "전환 시 감수해야 할 단점이나 비용"
    }
  ],
  "migration_advice": "마이그레이션 결정 시 주의할 핵심 조언"
}
"""


def find_migration_alternatives(tech_id: str) -> dict:
    target_tech = db.get_technology(tech_id)
    target_stat = db.get_statistics(tech_id)
    if not target_tech:
        return {"status": "error", "message": "기술 정보를 찾을 수 없습니다."}

    llm = get_llm()
    user_prompt = f"기준 기술: {target_tech['canonical_name']} (범주: {target_tech['category']})\n설명: {target_tech['description']}"

    try:
        res = llm.invoke(
            [
                SystemMessage(content=ALTERNATIVE_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )
        raw_text = res.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw_text)
    except Exception:
        data = {
            "alternatives": [],
            "migration_advice": "대안 분석 중 오류가 발생했습니다.",
        }

    # 대안 기술들의 설문 지표를 참고용으로 매핑
    alts_with_stats = []
    for alt in data.get("alternatives", []):
        tname = alt.get("tech_name", "")
        stat_info = None
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT technology_id FROM technology WHERE canonical_name LIKE ? OR technology_id LIKE ?",
                (f"%{tname}%", f"%{tname.lower()}%"),
            )
            row = cursor.fetchone()
            if row:
                s = db.get_statistics(row["technology_id"])
                if s:
                    stat_info = {"usage": s.usage_pct, "admired": s.admired_pct}

        alts_with_stats.append(
            {
                "name": tname,
                "tag": alt.get("tag", ""),
                "pros": alt.get("pros_vs_target", ""),
                "cons": alt.get("cons_or_tradeoff", ""),
                "stat": stat_info,
            }
        )

    return {
        "target": {"name": target_tech["canonical_name"], "stat": target_stat},
        "alternatives": alts_with_stats,
        "advice": data.get("migration_advice", ""),
    }


# 3. 내 스택 진단
DIAGNOSE_PROMPT = """
당신은 기술 스택을 종합 진찰하는 수석 소프트웨어 아키텍트이다.
사용자가 현재 실무/프로젝트에서 사용 중인 기술 조합과 설문 통계 지표를 분석하여, 깊이 있고 현실적인 '스택 건강성 진단 리포트'를 작성하라.

[작성 가이드 - 가독성 높은 마크다운 형식]
1. **스택 종합 평가 & 조화도 (Synergy):**
   - 선택된 기술들이 서로 얼마나 궁합이 잘 맞는지, 현재 시장 표준 대비 얼마나 현대적(Modern)인지 총평하라.
2. **핵심 강점 포인트:**
   - 이 스택을 썼을 때 얻는 실무적 이점(생산성, 성능, 인력 풀, 생태계 등)을 불릿 포인트(`- `)로 짚어라.
3. **잠재적 리스크 및 주의점:**
   - 특정 기술의 낮은 만족도(피로도), 성능 병목, 혹은 운영 비용(클라우드 등) 측면에서 발생할 수 있는 주의사항을 짚어라.
4. **향후 권장 액션 (Next Step):**
   - 이 스택에 추가하면 시너지가 폭발할 만한 보조 도구(예: 캐시, 컨테이너, 모니터링 등)나 최적화 방향을 1~2개 제안하라.

글자 벽돌을 피하고 소제목과 볼드, 불릿을 활용하여 가독성을 극대화하라.
"""


def diagnose_user_stack(tech_ids: list[str]) -> dict:
    diagnostics = []
    stack_summary_lines = []

    for tid in tech_ids:
        t = db.get_technology(tid)
        s = db.get_statistics(tid)
        if t and s:
            status_tag = "안정적 주류"
            if s.usage_pct >= 30.0 and s.admired_pct >= 60.0:
                status_tag = "👑 강력한 주류"
            elif s.usage_pct < 15.0 and s.admired_pct >= 70.0:
                status_tag = "🚀 급부상 팬덤"
            elif s.usage_pct >= 20.0 and s.admired_pct < 45.0:
                status_tag = "⚠️ 레거시 피로도 주의"

            diagnostics.append(
                {
                    "id": tid,
                    "name": t["canonical_name"],
                    "category": t["category"],
                    "usage": s.usage_pct,
                    "admired": s.admired_pct,
                    "tag": status_tag,
                }
            )
            stack_summary_lines.append(
                f"- [{t['category']}] {t['canonical_name']} (사용률: {s.usage_pct}%, 만족도: {s.admired_pct}%)"
            )

    # LLM에게 종합 진단 리포트 요청
    llm = get_llm()
    user_context = "사용 중인 스택 목록:\n" + "\n".join(stack_summary_lines)

    try:
        res = llm.invoke(
            [SystemMessage(content=DIAGNOSE_PROMPT), HumanMessage(content=user_context)]
        )
        report_text = res.content.strip()
    except Exception:
        report_text = "스택 종합 진단 분석 중 오류가 발생했습니다."

    return {"cards": diagnostics, "report": report_text}
