from langchain_core.documents import Document

from data.sqlite_db import DatabaseManager
from indexing.store import get_meta_collection


def index_technology_metadata() -> int:
    db = DatabaseManager()
    collection = get_meta_collection()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM technology")
        rows = cursor.fetchall()

    docs = []
    ids = []
    for r in rows:
        tech_id = r["technology_id"]
        # 검색 대상 텍스트: 기술명, 범주, 설명
        text_content = f"기술명: {r['canonical_name']}\n범주: {r['category']}\n개요: {r['description']}"

        doc = Document(
            page_content=text_content,
            metadata={
                "item_id": tech_id,
                "title": r["canonical_name"],
                "category": r["category"],
                "source_kind": "item_metadata",
                "locator": f"tech_registry:{tech_id}",
                "provenance_id": "so_survey_2026",
            },
        )
        docs.append(doc)
        ids.append(f"meta:{tech_id}")

    # 멱등 upsert (동일 ID 덮어쓰기)
    collection.add_documents(documents=docs, ids=ids)
    return len(docs)


if __name__ == "__main__":
    count = index_technology_metadata()
    print(f"✅ 기술 메타데이터 컬렉션 색인 완료: 총 {count}건 저장.")
