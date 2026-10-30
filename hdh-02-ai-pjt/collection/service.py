from langchain_core.documents import Document

from collection.cache import wiki_cache
from collection.client import WikipediaClient
from indexing.store import get_docs_collection


def ensure_technology_wikipedia_doc(tech_name: str, tech_id: str) -> bool:
    """선택된 기술의 위키백과 본문이 없으면 외부 API로 수집하여 Chroma에 즉시 색인"""
    cache_key = f"wiki_doc_{tech_id}"

    # 1. 로컬 캐시 확인 (NF2002: 재호출 금지)
    cached_doc = wiki_cache.get_document(cache_key)
    if cached_doc:
        return True

    # 2. 외부 위키백과 API 호출 (선택 기술 자체 문서 우선 검색)
    # 기술명이 일반 단어와 충돌할 수 있으므로 'programming language', 'database' 등 키워드 결합 시도
    search_queries = [tech_name, f"{tech_name} programming", f"{tech_name} software"]
    candidates = []
    for q in search_queries:
        candidates = WikipediaClient.search_candidates(q, limit=2)
        if candidates:
            break

    # 후보가 없으면 기술명 그대로 시도
    target_title = candidates[0]["title"] if candidates else tech_name
    doc_data = WikipediaClient.fetch_page_summary(target_title)

    if not doc_data or not doc_data.get("text"):
        return False

    # 3. 캐시에 영속 보존
    wiki_cache.set_document(cache_key, doc_data)

    # 4. Chroma 문서 컬렉션(so_survey_docs_v1)에 실시간 청크 색인
    docs_col = get_docs_collection()
    content_text = f"[{doc_data['title']} - 위키백과 기술 개요]\n{doc_data['text']}"

    doc = Document(
        page_content=content_text,
        metadata={
            "doc_id": f"wiki_{tech_id}",
            "title": f"{doc_data['title']} (Wikipedia)",
            "source_role": "supporting_tech_doc",
            "source_kind": "wikipedia",
            "locator": doc_data.get("url", "https://en.wikipedia.org"),
            "provenance_id": "wikipedia_api",
        },
    )
    docs_col.add_documents(documents=[doc], ids=[f"wiki:{tech_id}"])
    return True
