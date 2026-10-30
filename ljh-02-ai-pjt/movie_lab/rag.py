"""An actual two-node StateGraph; conversation storage stays with the caller."""

import re
import time
from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END

from movie_lab.answering import create_answer_generator
from movie_lab.config import (resolve_index_path, resolve_document_index_path,
                              retrieval_settings)
from movie_lab.document_llm import _metadata_only_question
from movie_lab.document_pipeline import create_document_pipeline, safe_error
from movie_lab.embeddings import create_gms_embeddings
from movie_lab.external_index import ExternalIndex, ChunkConfig
from movie_lab.index import MetadataIndex, read_index_config
from movie_lab.retrieval import EvidenceRetriever


class RagState(TypedDict, total=False):
    movie: Any
    question: str
    history: list[dict]
    mode: str
    refresh: bool
    trace: list[str]
    preparation: dict
    retrieval: dict
    content: str
    sources: list[dict]
    validation: dict
    checks: list[dict]
    error: dict
    calls: dict
    timings: dict
    stage_calls: dict
    cache: dict
    failure_stage: str


def recent_history(history, question):
    rows = [{"role": row["role"], "content": row["content"][:1800]}
            for row in (history or []) if row.get("role") in ("user", "assistant")
            and isinstance(row.get("content"), str)][-6:]
    if rows and rows[-1] == {"role": "user", "content": question[:1800]}:
        rows.pop()
    return rows


def retrieval_question(question, history):
    # Resolve a short follow-up with the most recent user intent, not a past
    # assistant's assertions. The current question appears once in the payload.
    if len(question) < 100 and re.search(r"그럼|그것|그 현상|그 장면|이 현상|그 얘기|그 이야기", question):
        previous = next((row["content"] for row in reversed(history) if row["role"] == "user"), "")
        if previous and previous.strip() != question.strip():
            return previous[:600] + "\n후속 질문: " + question
    return question


def create_evidence_retriever(*, metadata_only=False):
    config = read_index_config(resolve_index_path())
    metadata = None
    try:
        metadata = MetadataIndex(resolve_index_path(), config, create=False)
    except Exception:
        pass
    external, embedder = None, None
    settings = retrieval_settings()
    if not metadata_only:
        from movie_lab.config import document_chunk_settings
        try:
            size, overlap = document_chunk_settings()
            external = ExternalIndex(resolve_document_index_path(), config.model_id, config.dimension,
                                     ChunkConfig(size, overlap), create=False)
            embedder = create_gms_embeddings(config.model_id, config.dimension)
        except Exception:
            if external is not None:
                external.close()
            external = None
    if metadata_only:
        from movie_lab.retrieval import RetrievalConfig
        settings = RetrievalConfig(1, settings.max_context_chars, 1)
    return EvidenceRetriever(metadata, external, embedder, settings)


def close_retriever(retriever):
    for resource in (getattr(retriever, "metadata_index", None), getattr(retriever, "external_index", None)):
        if resource is not None:
            try:
                resource.close()
            except Exception:
                pass


def generator_model_metadata(generator):
    """Keep generation identity separate from the later review response."""
    reported = getattr(generator, "reported_models", {})
    reported = dict(reported) if isinstance(reported, dict) else {}
    return {"model": getattr(generator, "model", None),
            "review_model": getattr(generator, "review_model", getattr(generator, "model", None)),
            "reported_model": reported.get("generate_answer", getattr(generator, "reported_model", None)),
            "reported_models": reported}


class MovieRag:
    def __init__(self, *, pipeline_factory=create_document_pipeline,
                 retriever_factory=create_evidence_retriever,
                 generator_factory=create_answer_generator, progress=None):
        self.pipeline_factory, self.retriever_factory = pipeline_factory, retriever_factory
        self.generator_factory, self.progress = generator_factory, progress
        graph = StateGraph(RagState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("generate", self._generate)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", END)
        self.graph = graph.compile()

    def _announce(self, text):
        if self.progress:
            self.progress(text)

    def _retrieve(self, state):
        self._announce("질문에 필요한 자료와 선택 영화 근거를 확인하는 중")
        movie, question, history = state["movie"], state["question"], state["history"]
        metadata_only = state["mode"] == "general" and _metadata_only_question(movie, question)
        preparation, pipeline, retriever = {}, None, None
        warnings = []
        preparation_started = time.perf_counter()
        if not metadata_only:
            try:
                pipeline = self.pipeline_factory()
                preparation = pipeline.prepare(movie, question, history, refresh=state.get("refresh", False), progress=self.progress)
                if not preparation.get("complete"):
                    warnings.append("자료 준비가 완료되지 않았습니다. 현재 확보한 근거로 확인되는 부분만 답합니다.")
            except Exception as error:
                preparation = {"complete": False, "error": safe_error(error)}
                warnings.append("자료 준비 연결에 실패했습니다. 기존 저장 근거와 메타데이터만 사용합니다.")
            finally:
                if pipeline:
                    try:
                        pipeline.close()
                    except Exception:
                        warnings.append("자료 저장소 종료 상태를 확인하지 못했습니다.")
        preparation_seconds = 0.0 if metadata_only else time.perf_counter() - preparation_started
        search_started = time.perf_counter()
        try:
            self._announce("영화 ID로 제한해 검색하고 겹치는 근거를 정리하는 중")
            retriever = self.retriever_factory(metadata_only=metadata_only)
            retrieval = retriever.retrieve(movie, retrieval_question(question, history), preparation)
            retrieval["diagnostics"]["warnings"].extend(warnings)
            calls = dict(preparation.get("calls", {"chat": 0, "embedding": 0, "wiki": 0}))
            calls["retrieval_embedding"] = getattr(getattr(retriever, "embedder", None), "request_count", 0)
            return {"preparation": preparation, "retrieval": retrieval, "sources": retrieval["sources"],
                    "trace": ["retrieve"], "calls": calls,
                    **retrieval_observation(preparation, metadata_only, preparation_seconds,
                                            time.perf_counter() - search_started, calls["retrieval_embedding"])}
        except Exception as error:
            # Metadata should still be available from the supplied file if the
            # vector-store/configuration factory cannot be opened.
            fallback = EvidenceRetriever(None, None, None)
            retrieval = fallback.retrieve(movie, question)
            retrieval["diagnostics"]["warnings"].append("검색 저장소 연결에 실패해 제공 메타데이터만 사용합니다.")
            return {"preparation": preparation, "retrieval": retrieval, "sources": retrieval["sources"],
                    "trace": ["retrieve"], "calls": preparation.get("calls", {}),
                    "error": {"category": "검색 저장소 연결 실패: 메타데이터로 부분 처리"},
                    **retrieval_observation(preparation, metadata_only, preparation_seconds,
                                            time.perf_counter() - search_started,
                                            getattr(getattr(retriever, "embedder", None), "request_count", 0))}
        finally:
            if retriever:
                close_retriever(retriever)

    def _generate(self, state):
        self._announce("제공 근거로 답변을 생성하고 인용 구절·의미를 확인하는 중")
        calls = {**state.get("calls", {}), "answer_model": 0}
        generator = None
        generation_started = time.perf_counter()
        try:
            if not state.get("sources"):
                return {"trace": ["retrieve", "generate"], "content": "사용할 근거를 확보하지 못했습니다. 자료 경로와 연결 상태를 확인해 주세요.",
                        "sources": [], "validation": {"generation_skipped": True, "semantic_check": "not_run"}, "calls": calls,
                        **generation_observation(state, None, generation_started)}
            generator = self.generator_factory()
            try:
                result = generator.generate(state["movie"], state["question"], state["history"], state["sources"],
                                            state["mode"], state["retrieval"]["diagnostics"].get("warnings", []))
            finally:
                calls["answer_model"] = generator.request_count
            return {**result, "calls": calls, "trace": ["retrieve", "generate"],
                    **generation_observation(state, generator, generation_started),
                    "validation": {**result["validation"], **generator_model_metadata(generator),
                                   "audit": generator.audit}}
        except Exception as error:
            return {"trace": ["retrieve", "generate"], "error": safe_error(error), "calls": calls,
                    "failure_stage": getattr(generator, "last_failure_stage", None) or ("generation_client" if generator is None else "answer_validation"),
                    **generation_observation(state, generator, generation_started),
                    "content": "", "sources": [], "validation": {"generation_failed": True,
                        **generator_model_metadata(generator),
                        "audit": getattr(generator, "audit", [])}}

    def answer(self, movie, question, history=None, mode="general", refresh=False):
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            raise ValueError("질문은 1~4000자로 입력하세요.")
        if mode not in ("general", "verify"):
            raise ValueError("답변 모드 설정을 확인하세요.")
        return self.graph.invoke({"movie": movie, "question": question.strip(),
                                  "history": recent_history(history, question.strip()),
                                  "mode": mode, "refresh": refresh})


def retrieval_observation(preparation, metadata_only, preparation_seconds, retrieval_seconds, embedding_calls):
    return {"timings": {"preparation": preparation_seconds, "retrieval": retrieval_seconds},
            "stage_calls": {"preparation": {name: preparation.get("calls", {}).get(name, 0)
                                             for name in ("chat", "wiki", "embedding")},
                            "retrieval": {"embedding": embedding_calls}},
            "cache": {"preparation_skipped": metadata_only,
                      "preparation_hit": preparation.get("cache_hit") if not metadata_only else None,
                      "document_body_hits": preparation.get("document_cache_hits", 0)}}


def generation_observation(state, generator, started):
    metrics = getattr(generator, "metrics", {})
    return {"timings": {**state.get("timings", {}), "generation_node": time.perf_counter() - started,
                        **{name: metrics.get(name, {}).get("seconds", 0.0)
                           for name in ("answer_generation", "semantic_review")}},
            "stage_calls": {**state.get("stage_calls", {}),
                            **{name: {"chat": metrics.get(name, {}).get("calls", 0)}
                               for name in ("answer_generation", "semantic_review")}}}


def create_rag_service(snapshot_archive=None, progress=None, source_mode="auto", *, max_answer_attempts=2):
    return MovieRag(pipeline_factory=lambda: create_document_pipeline(snapshot_archive, source_mode=source_mode),
                    generator_factory=lambda: create_answer_generator(max_attempts=max_answer_attempts), progress=progress)
