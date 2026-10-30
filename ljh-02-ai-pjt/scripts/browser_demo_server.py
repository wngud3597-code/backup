"""Review-only observation of the real app; never replace model/store responses.

Runs app.py itself. SDK wrappers record only operation/model/status/duration;
the unchanged RAG result and thread digests are recorded separately. The demo
allows exactly the two authorized question submissions, with one generation
attempt per submission. No key, headers or raw exception messages are logged.
"""

from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "artifacts/review_browser_demo"
EVENTS = OUTPUT / "api_events.jsonl"
QUESTIONS = {
    "157336": "이 영화의 감독과 상영 시간을 알려줘.",
    "753091": "이 영화는 크리스토퍼 놀란이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?",
}
LOCK = threading.RLock()
SUBMITTED = set()
COUNTER = 0


def emit(event, **fields):
    with LOCK:
        with EVENTS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                                     **fields}, ensure_ascii=False) + "\n")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def thread_snapshot(threads):
    return {movie_id: {"message_count": len(rows), "digest": digest(rows),
                      "user_questions": [r["content"] for r in rows if r["role"] == "user"],
                      "answers": [{"answer_id": r["answer_id"], "content": r["content"],
                                   "sources_sha256": digest(r["sources"])}
                                  for r in rows if r["role"] == "assistant"]}
            for movie_id, rows in threads.items()}


def install_observers():
    from openai.resources.chat.completions import Completions
    from openai.resources.embeddings import Embeddings
    from movie_lab import rag, state, services
    from movie_lab.document_pipeline import safe_error

    def observe_sdk(cls, kind):
        original = cls.create

        @wraps(original)
        def create(instance, *args, **kwargs):
            global COUNTER
            with LOCK:
                COUNTER += 1
                request_id = COUNTER
            started = time.perf_counter()
            emit("api_start", request_id=request_id, kind=kind, model=kwargs.get("model"))
            try:
                result = original(instance, *args, **kwargs)
            except Exception as error:
                emit("api_end", request_id=request_id, kind=kind, success=False,
                     seconds=time.perf_counter() - started, error=safe_error(error))
                raise
            reported = getattr(result, "model", None)
            requested = kwargs.get("model")
            if not (isinstance(requested, str) and isinstance(reported, str)
                    and (reported == requested or reported.startswith(requested + "-"))):
                reported = None
            emit("api_end", request_id=request_id, kind=kind, success=True,
                 seconds=time.perf_counter() - started, reported_model=reported)
            return result

        cls.create = create

    observe_sdk(Completions, "chat")
    observe_sdk(Embeddings, "embedding")
    original_create = rag.create_rag_service

    def create_rag_service(*args, **kwargs):
        # Explicit review-run budget; production default/configuration unchanged.
        kwargs["max_answer_attempts"] = 1
        service = original_create(*args, **kwargs)
        original_answer = service.answer

        def answer(movie, question, history=None, mode="general", refresh=False):
            with LOCK:
                if (QUESTIONS.get(movie.movie_id) != question
                        or movie.movie_id in SUBMITTED or len(SUBMITTED) >= 2):
                    emit("question_blocked", movie_id=movie.movie_id)
                    raise ValueError("브라우저 검증의 두 질문 전송 한도를 초과했습니다.")
                SUBMITTED.add(movie.movie_id)
            started = time.perf_counter()
            emit("answer_start", movie_id=movie.movie_id, question=question, mode=mode,
                 history_messages=len(history or []), refresh=refresh, max_answer_attempts=1)
            try:
                result = original_answer(movie, question, history, mode=mode, refresh=refresh)
            except Exception as error:
                emit("answer_error", movie_id=movie.movie_id,
                     seconds=time.perf_counter() - started, error=safe_error(error))
                raise
            emit("answer_result", movie_id=movie.movie_id, question=question, mode=mode,
                 seconds=time.perf_counter() - started,
                 result={key: result.get(key) for key in (
                     "trace", "preparation", "retrieval", "content", "sources", "checks",
                     "validation", "error", "calls", "timings", "stage_calls", "cache", "failure_stage")})
            return result

        service.answer = answer
        return service

    rag.create_rag_service = create_rag_service
    original_search = services.search_catalog

    def search_catalog(query, movies):
        started = time.perf_counter()
        emit("discovery_start", query=query)
        try:
            result = original_search(query, movies)
        except Exception as error:
            emit("discovery_error", seconds=time.perf_counter() - started, error=safe_error(error))
            raise
        emit("discovery_result", seconds=time.perf_counter() - started, result=result)
        return result

    services.search_catalog = search_catalog
    for name in ("append_user_message", "append_assistant_message", "get_thread"):
        original = getattr(state, name)

        def observe_thread(fn, operation):
            @wraps(fn)
            def invoke(threads, movie_id, *args, **kwargs):
                result = fn(threads, movie_id, *args, **kwargs)
                emit("thread_observation", operation=operation, movie_id=movie_id,
                     threads=thread_snapshot(threads))
                return result
            return invoke

        setattr(state, name, observe_thread(original, name))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    replay = "--replay" in sys.argv
    if replay:
        install_replay()
    else:
        if EVENTS.exists():
            raise SystemExit("기존 시연 호출 기록이 있습니다. 자동 재실행하지 않습니다.")
        install_observers()
        emit("server_start", entrypoint="app.py", max_question_submissions=2,
             generation_attempts_per_question=1, mock_responses=False)
    from streamlit.web import cli
    sys.argv = ["streamlit", "run", str(ROOT / "app.py"), "--server.address=127.0.0.1",
                "--server.port=" + ("8504" if replay else "8503"), "--server.headless=true", "--server.fileWatcherType=none",
                "--client.showErrorDetails=false"]
    cli.main()


def install_replay():
    """Explicit saved-result UI replay, isolated from live events and clients."""
    from copy import deepcopy
    from openai.resources.chat.completions import Completions
    from openai.resources.embeddings import Embeddings
    import streamlit as st
    from movie_lab import rag

    rows = [json.loads(line) for line in EVENTS.read_text(encoding="utf-8").splitlines() if line]
    saved = next(row["result"] for row in rows
                 if row["event"] == "answer_result" and row["movie_id"] == "753091")
    used = False

    def deny_api(*args, **kwargs):
        raise RuntimeError("저장 결과 재생에서는 실제 API를 호출하지 않습니다.")

    Completions.create = Embeddings.create = deny_api
    original_title = st.title

    def title(*args, **kwargs):
        original_title(*args, **kwargs)
        st.warning("검증용 저장 결과 재생 · 새 GMS 호출 없음 · 실제 시연 성공의 증거가 아닙니다.")
        with st.sidebar:
            st.warning("검증용 저장 결과 재생\n\n새 GMS 호출 없음\n\n실제 시연 성공의 증거가 아닙니다.")

    st.title = title

    class ReplayService:
        def answer(self, movie, question, *args, **kwargs):
            nonlocal used
            if used or movie.movie_id != "753091" or question != QUESTIONS["753091"]:
                raise ValueError("지정한 저장 결과만 한 번 재생할 수 있습니다.")
            used = True
            return deepcopy(saved)

    rag.create_rag_service = lambda *args, **kwargs: ReplayService()


if __name__ == "__main__":
    main()
