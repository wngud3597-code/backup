"""Movie-scoped session state without a second copy of conversation history.

The caller owns ``threads_by_movie`` (normally in Streamlit session_state).
Each assistant message stores its answer and evidence snapshot together, so
citation numbers are local to that one answer.
"""

from collections.abc import MutableMapping
from copy import deepcopy
from typing import Any
from uuid import uuid4


Message = dict[str, Any]
MovieThreads = MutableMapping[str, list[Message]]


def _movie_id(movie_id: str | int) -> str:
    if movie_id is None or not str(movie_id).strip():
        raise ValueError("movie_id must not be empty")
    return str(movie_id).strip()


def _content(content: str) -> str:
    if not isinstance(content, str):
        raise TypeError("message content must be a string")
    if not content.strip():
        raise ValueError("message content must not be empty")
    return content


def get_thread(threads: MovieThreads, movie_id: str | int) -> list[Message]:
    """Return the one authoritative list for a movie, creating it if needed."""
    key = _movie_id(movie_id)
    thread = threads.setdefault(key, [])
    if not isinstance(thread, list):
        raise TypeError("a movie thread must be a list")
    return thread


def append_user_message(
    threads: MovieThreads, movie_id: str | int, content: str
) -> None:
    """Store a user message once; payload generation never inserts it again."""
    message = {"role": "user", "content": _content(content)}
    get_thread(threads, movie_id).append(message)


def append_assistant_message(
    threads: MovieThreads,
    movie_id: str | int,
    content: str,
    sources: list[dict],
) -> Message:
    """Store an answer and an independent snapshot of its numbered sources.

    The returned dictionary is the stored message, not another history store.
    Input source lists and nested source fields may safely be reused or changed
    by a later retrieval without altering previous answers.
    """
    answer = _content(content)
    if not isinstance(sources, list) or any(
        not isinstance(source, dict) for source in sources
    ):
        raise TypeError("sources must be a list of dictionaries")
    message = {
        "role": "assistant",
        "answer_id": str(uuid4()),
        "content": answer,
        "sources": deepcopy(sources),
    }
    get_thread(threads, movie_id).append(message)
    return message


def clear_thread(threads: MovieThreads, movie_id: str | int) -> None:
    """Clear only the selected movie's messages."""
    get_thread(threads, movie_id).clear()


def build_payload(
    threads: MovieThreads, movie_id: str | int, system_prompt: str
) -> list[dict[str, str]]:
    """Build step6's system + history pattern for the selected movie only.

    Only role/content strings are copied. Evidence and answer IDs remain in
    their assistant messages, and past citation labels are not evidence for a
    new answer. This helper does not call any model or insert a new question.
    """
    payload = [{"role": "system", "content": _content(system_prompt)}]
    for message in get_thread(threads, movie_id):
        role = message.get("role")
        if role not in {"user", "assistant"}:
            raise ValueError("movie history can contain only user/assistant roles")
        payload.append({"role": role, "content": _content(message.get("content"))})
    return payload
