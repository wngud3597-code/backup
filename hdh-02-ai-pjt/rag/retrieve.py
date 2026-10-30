import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from collection.cache import wiki_cache
from collection.service import ensure_technology_wikipedia_doc
from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL
from contracts import Evidence, StatisticalResult
from data.sqlite_db import DatabaseManager
from indexing.store import get_docs_collection, get_meta_collection

KOREAN_TECH_MAP = {
    "파이썬": "python",
    "자바스크립트": "javascript",
    "타입스크립트": "typescript",
    "러스트": "rust",
    "자바": "java",
    "고": "go",
    "코틀린": "kotlin",
    "포스트그레": "postgresql",
    "몽고": "mongodb",
    "레디스": "redis",
    "리액트": "react",
    "뷰": "vuejs",
    "장고": "django",
    "스프링": "springboot",
    "도커": "docker",
    "노드": "nodejs",
    "패스트api": "fastapi",
    "fastapi": "fastapi",
}

ROUTER_PROMPT = """
사용자의 질문을 분석하여, 우리 시스템의 104개 기술 중 가장 관련성 높고 추천/비교할 만한 기술 ID 2~4개를 JSON 배열로 출력하라.
지원 기술 ID 예시: python, javascript, typescript, rust, go, java, cplusplus, fastapi, nodejs, django, react, nextjs, postgresql, mongodb, redis, aws, gcp, vercel 등

출력 형식: {"tech_ids": ["fastapi", "python", "nodejs"]}
"""


def extract_target_techs(query: str) -> list[str]:
    q_lower = query.lower()
    found = []

    # 1. 한글/영문 직접 매핑
    for ko, eng in KOREAN_TECH_MAP.items():
        if ko in q_lower and eng not in found:
            found.append(eng)

    # 2. 질문에 직접 기술명이 없으면 (예: 'AI 백엔드 추천') LLM이 적합한 기술 3개 추론
    if not found:
        try:
            llm = ChatOpenAI(
                model=OPENAI_CHAT_MODEL,
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
            )
            res = llm.invoke(
                [
                    SystemMessage(content=ROUTER_PROMPT),
                    HumanMessage(content=f"질문: {query}"),
                ]
            )
            raw = res.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            found = json.loads(raw).get("tech_ids", [])
        except Exception:
            pass

    # 3. 보조: 벡터 유사도 검색
    if not found:
        meta_col = get_meta_collection()
        matched = meta_col.similarity_search(query, k=2)
        for m in matched:
            tid = m.metadata.get("item_id")
            if tid and tid not in found:
                found.append(tid)

    return found[:3]


def retrieve_all_evidences(
    tech_id: str, query: str, top_k: int = 4
) -> tuple[list[Evidence], StatisticalResult | None]:
    db = DatabaseManager()
    evidences: list[Evidence] = []
    ev_num = 1
    stat: StatisticalResult | None = None

    target_tech_ids = (
        extract_target_techs(query)
        if (tech_id == "global" or not tech_id)
        else [tech_id]
    )

    for tid in target_tech_ids:
        t_info = db.get_technology(tid)
        t_stat = db.get_statistics(tid, year=2026)

        if t_info:
            ensure_technology_wikipedia_doc(t_info["canonical_name"], tid)
            cached_wiki = wiki_cache.get_document(f"wiki_{tid}")

            if cached_wiki and cached_wiki.get("text"):
                evidences.append(
                    Evidence(
                        evidence_no=ev_num,
                        kind="supporting_doc",
                        title=f"{t_info['canonical_name']} 위키백과 개요",
                        text=f"[{t_info['canonical_name']} 기술 정보]\n{cached_wiki['text']}",
                        locator=cached_wiki.get("url", "wikipedia"),
                        provenance_id="wikipedia_api",
                    )
                )
                ev_num += 1

            evidences.append(
                Evidence(
                    evidence_no=ev_num,
                    kind="item_metadata",
                    title=f"{t_info['canonical_name']} 메타 정보",
                    text=f"기술명: {t_info['canonical_name']} / 범주: {t_info['category']}\n개요: {t_info['description']}",
                    locator=f"registry:{tid}",
                    provenance_id="so_survey_2026",
                )
            )
            ev_num += 1

        if t_stat:
            if tech_id != "global":
                stat = t_stat
            evidences.append(
                Evidence(
                    evidence_no=ev_num,
                    kind="survey_statistics",
                    title=f"{t_stat.technology_name} 2026 설문 통계",
                    text=f"[{t_stat.technology_name}] 범주: {t_stat.category}, Usage: {t_stat.usage_pct}%, Admired: {t_stat.admired_pct}%, Desired: {t_stat.desired_pct}%",
                    locator=t_stat.source_locator,
                    provenance_id="so_survey_2026",
                )
            )
            ev_num += 1

    docs_col = get_docs_collection()
    results = docs_col.similarity_search(query, k=2)
    for doc in results:
        evidences.append(
            Evidence(
                evidence_no=ev_num,
                kind="survey_context",
                title=doc.metadata.get("title", "설문 배경"),
                text=doc.page_content,
                locator=doc.metadata.get("locator", "methodology"),
                provenance_id="so_methodology",
            )
        )
        ev_num += 1

    return evidences, stat
