from langchain_core.documents import Document

from indexing.store import get_docs_collection

# 공식 조사 정의 및 배경 문서
SURVEY_CONTEXT_DOCS = [
    {
        "id": "doc_def_usage",
        "title": "Usage 지표 공식 정의",
        "text": "Usage(사용률)는 지난 1년간 해당 프로그래밍 언어, 데이터베이스, 클라우드 또는 프레임워크를 실제로 개발에 사용했다고 응답한 비율이다. 분모는 설문 전체 응답자가 아닌 해당 문항에 응답한 유효 응답자 수(n=14,099 등) 기준이며, 복수 선택이 가능하므로 범주 내 백분율 합계는 100%를 초과할 수 있다.",
        "role": "survey_definition",
        "locator": "survey.stackoverflow.co/2026/methodology#usage",
    },
    {
        "id": "doc_def_admired",
        "title": "Admired vs Desired 지표 공식 정의",
        "text": "Admired(지속 희망률)는 지난 1년 동안 해당 기술을 사용한 개발자 중 내년에도 계속 사용하고 싶다고 답한 비율(기사용자 만족도)이다. 분모가 전체 응답자가 아닌 '해당 기술 사용자'로 제한된다. 반면 Desired(관심 희망률)는 현재 사용 여부와 상관없이 향후 사용해보고 싶다고 응답한 비율이다.",
        "role": "survey_definition",
        "locator": "survey.stackoverflow.co/2026/methodology#admired-desired",
    },
    {
        "id": "doc_def_methodology",
        "title": "조사 방법론 및 표본 한계",
        "text": "Stack Overflow Developer Survey는 169개국 30,903명 이상의 자발적 참여로 이루어진 온라인 조사이다. 이는 전 세계 개발자 모집단의 무작위 확률 표본이 아니며, 영어권 및 Stack Overflow 활성 사용자에게 편향이 존재할 수 있다. 연도 간 단순 수치 변화를 동일 개발자의 행동 인과 관계로 해석해서는 안 된다.",
        "role": "survey_methodology",
        "locator": "survey.stackoverflow.co/2026/methodology#sampling",
    },
]


def index_survey_documents() -> int:
    collection = get_docs_collection()
    docs = []
    ids = []
    for item in SURVEY_CONTEXT_DOCS:
        doc = Document(
            page_content=f"{item['title']}\n\n{item['text']}",
            metadata={
                "doc_id": item["id"],
                "title": item["title"],
                "source_role": item["role"],
                "source_kind": "survey_context",
                "locator": item["locator"],
                "provenance_id": "so_methodology_2026",
            },
        )
        docs.append(doc)
        ids.append(f"doc:{item['id']}")

    collection.add_documents(documents=docs, ids=ids)
    return len(docs)


if __name__ == "__main__":
    count = index_survey_documents()
    print(f"✅ 설문 컨텍스트 문서 컬렉션 색인 완료: 총 {count}건 저장.")
