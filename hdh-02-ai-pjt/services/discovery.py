import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL
from data.sqlite_db import DatabaseManager

db = DatabaseManager()

PARSE_PROMPT = """
당신은 기술 탐색 쿼리 분석기이다. 사용자의 자연어 입력에서 조건 검색 파라미터를 JSON으로 추출하라.

[추출 규칙]
1. category: "Language", "Database", "Cloud", "WebFramework" 중 하나 (없으면 null)
2. min_usage: 최소 사용률(%) 숫자 (예: "사용률 20% 이상", "점유율 15프로 넘는" -> 20.0 또는 15.0 / "인기 있는" -> 20.0 / 없으면 null)
3. min_admired: 최소 만족도(%) 숫자 (예: "만족도 60% 이상", "선호도 70 넘는" -> 60.0 또는 70.0 / "만족도 높은" -> 65.0 / 없으면 null)
4. keywords: 기술의 특성/용도 관련 키워드 리스트 (예: "데이터 분석", "머신러닝", "경량", "시스템 프로그래밍" 등 / 없으면 [])
5. sort_by: "usage" 또는 "admired" (기본 "usage", 만족도/선호도 중심 질문이면 "admired")

반드시 순수 JSON만 출력하라.
예시 출력: {"category": "Language", "min_usage": 10.0, "min_admired": 60.0, "keywords": ["데이터"], "sort_by": "admired"}
"""


def parse_and_filter_technologies(user_query: str) -> list[dict]:
    # 1. LLM을 통한 정밀 조건 파싱
    llm = ChatOpenAI(
        model=OPENAI_CHAT_MODEL, api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL
    )

    try:
        res = llm.invoke(
            [
                SystemMessage(content=PARSE_PROMPT),
                HumanMessage(content=f"검색어: {user_query}"),
            ]
        )
        raw_text = res.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        criteria = json.loads(raw_text)
    except Exception:
        # LLM 파싱 실패 시 빈 리스트 반환 (전체 다 쏟아내는 참사 방지)
        return []

    category = criteria.get("category")
    min_usage = criteria.get("min_usage")
    min_admired = criteria.get("min_admired")
    keywords: list[str] = criteria.get("keywords", [])
    sort_by = criteria.get("sort_by", "usage")

    # 2. SQLite 동적 쿼리 조립
    query = """
        SELECT t.technology_id, t.canonical_name, t.category, t.description,
               o.usage_pct, o.desired_pct, o.admired_pct
        FROM technology t
        JOIN observation o ON t.technology_id = o.technology_id
        WHERE o.year = 2026
    """
    params = []

    if category:
        query += " AND t.category = ?"
        params.append(category)

    if min_usage is not None:
        query += " AND o.usage_pct >= ?"
        params.append(float(min_usage))

    if min_admired is not None:
        query += " AND o.admired_pct >= ?"
        params.append(float(min_admired))

    # 정렬
    order_col = "o.admired_pct" if sort_by == "admired" else "o.usage_pct"
    query += f" ORDER BY {order_col} DESC"

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    # 3. 키워드 필터링 (설명문 또는 기술명에 키워드가 있는 것만 추가 검증)
    if keywords:
        filtered = []
        for r in rows:
            target_text = (r["canonical_name"] + " " + r["description"]).lower()
            if any(k.lower() in target_text for k in keywords):
                filtered.append(r)
        return filtered

    return rows
