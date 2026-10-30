from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from config import (
    CHROMA_PERSIST_DIR,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    SURVEY_DOCS_COLLECTION,
    TECH_META_COLLECTION,
)


def get_embedding_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL, api_key=OPENAI_API_KEY)


def get_meta_collection() -> Chroma:
    """so_tech_meta_v1: 기술별 기본 메타데이터 컬렉션"""
    return Chroma(
        collection_name=TECH_META_COLLECTION,
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=get_embedding_model(),
    )


def get_docs_collection() -> Chroma:
    """so_survey_docs_v1: 설문 표 문맥 및 지표 정의 컬렉션"""
    return Chroma(
        collection_name=SURVEY_DOCS_COLLECTION,
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=get_embedding_model(),
    )
