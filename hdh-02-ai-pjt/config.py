import os
from pathlib import Path

from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# API 키 및 모델
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or None
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# 경로 설정
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(STORAGE_DIR / "survey_data.db"))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(STORAGE_DIR / "chroma"))

# RAG 컬렉션 명칭 (설계 문서 고정)
TECH_META_COLLECTION = "so_tech_meta_v1"
SURVEY_DOCS_COLLECTION = "so_survey_docs_v1"

# 파라미터 기본값
DEFAULT_TOP_K = 6
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def validate_config() -> dict[str, bool]:
    """환경변수 상태를 안전하게 검증하여 반환 (키 값 자체는 노출하지 않음)"""
    return {
        "api_key_present": bool(OPENAI_API_KEY),
        "db_path_exists": Path(SQLITE_DB_PATH).parent.exists(),
        "storage_ready": STORAGE_DIR.exists(),
    }
