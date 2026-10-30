"""프로젝트 경로와 기존 GMS 연결 규약. 비밀키 값은 읽지 않는다."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GMS_BASE_URL = "https://gms.ssafy.io/gmsapi/api.openai.com/v1/"
GMS_KEY_ENV = "GMS_KEY"
DEFAULT_GMS_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_GMS_EMBEDDING_MODEL = "text-embedding-3-small"


def resolve_gms_chat_model(value: str | None = None) -> str:
    """명시값 → GMS_CHAT_MODEL → 기본 모델 순으로 선택한다. 키는 읽지 않는다."""
    configured = value if value is not None else os.environ.get("GMS_CHAT_MODEL")
    return (configured or "").strip() or DEFAULT_GMS_CHAT_MODEL


def resolve_gms_generation_model(value: str | None = None) -> str:
    """Explicit generation setting, then the existing shared chat fallback."""
    configured = value if value is not None else os.environ.get("GMS_GENERATION_MODEL")
    return (configured or "").strip() or resolve_gms_chat_model()


def resolve_gms_review_model(value: str | None = None) -> str:
    """Explicit review setting, then the existing shared chat fallback."""
    configured = value if value is not None else os.environ.get("GMS_REVIEW_MODEL")
    return (configured or "").strip() or resolve_gms_chat_model()


def gms_chat_options(model: str) -> dict:
    """Provider options, not a claim of GMS model/parameter support.

    Keep the previously verified mini request unchanged. GPT-5.4 mini uses
    the current Chat Completions completion cap and explicit no-reasoning
    mode; GMS still requires an actual compatible response.
    """
    if model == "gpt-5.4-mini" or model.startswith("gpt-5.4-mini-"):
        return {"model": model, "temperature": 0, "max_completion_tokens": 1800,
                "reasoning_effort": "none"}
    return {"model": model, "temperature": 0, "max_tokens": 1800}


def resolve_gms_embedding_model(value: str | None = None) -> str:
    """기본값은 후보일 뿐이며 GMS 지원은 실제 검사로 별도 확인한다."""
    configured = value if value is not None else os.environ.get("GMS_EMBEDDING_MODEL")
    return (configured or "").strip() or DEFAULT_GMS_EMBEDDING_MODEL


def resolve_index_path(value: str | Path | None = None) -> Path:
    configured = value if value is not None else os.environ.get("MOVIE_INDEX_PATH")
    path = Path(configured) if configured else Path("data/runtime/chroma")
    return path if path.is_absolute() else PROJECT_ROOT / path


def resolve_movies_path(value: str | Path | None = None) -> Path:
    """상대 경로는 실행 디렉터리가 아닌 프로젝트 루트 기준으로 해석한다."""
    configured = value if value is not None else os.environ.get("MOVIES_DATA_PATH")
    path = Path(configured) if configured else Path("data/movies.json")
    return path if path.is_absolute() else PROJECT_ROOT / path


def project_path(value: str | Path | None, env_name: str, default: str) -> Path:
    configured = value if value is not None else os.environ.get(env_name)
    path = Path(configured) if configured else Path(default)
    return path if path.is_absolute() else PROJECT_ROOT / path


def resolve_document_index_path(value: str | Path | None = None) -> Path:
    return project_path(value, "DOCUMENT_INDEX_PATH", "data/runtime/documents")


def resolve_document_cache_path(value: str | Path | None = None) -> Path:
    return project_path(value, "DOCUMENT_CACHE_PATH", "data/runtime/document_cache")


def resolve_snapshot_path(value: str | Path | None = None) -> Path:
    return project_path(value, "MOVIE_SNAPSHOT_PATH", "data/movie_snapshots.zip")


def document_chunk_settings() -> tuple[int, int]:
    size = int(os.environ.get("DOCUMENT_CHUNK_SIZE", "900"))
    overlap = int(os.environ.get("DOCUMENT_CHUNK_OVERLAP", "120"))
    if not 200 <= size <= 4000 or not 0 <= overlap < size:
        raise ValueError("청킹 설정 범위를 확인하세요.")
    return size, overlap


def retrieval_settings():
    from movie_lab.retrieval import RetrievalConfig
    return RetrievalConfig(top_k=int(os.environ.get("RAG_TOP_K", "6")),
                           max_context_chars=int(os.environ.get("RAG_CONTEXT_CHARS", "14000")),
                           max_per_document=int(os.environ.get("RAG_MAX_PER_DOCUMENT", "2")))
