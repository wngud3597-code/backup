"""step7_skeleton.py에서 이어 만든 영화 정보·대화 보존 앱.

실행: python -m streamlit run app.py
명시적인 탐색·자료 준비·질문 작업에서만 API를 호출한다.
"""

from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone

import streamlit as st

from movie_lab.config import resolve_index_path, resolve_movies_path
from movie_lab.data import DataLoadError, Movie, load_movies, movie_label
from movie_lab.evidence import cited_sources
from movie_lab.index import inspect_index_status
from movie_lab.discovery import discover_movies
from movie_lab.services import search_catalog
from movie_lab.document_pipeline import create_document_pipeline, safe_error
from movie_lab.config import resolve_snapshot_path
from movie_lab.state import append_user_message, append_assistant_message, clear_thread, get_thread
from movie_lab.rag import create_rag_service
from movie_lab.display import answer_for_display, movie_summary, suggested_questions


@st.cache_data(show_spinner=False, max_entries=4)
def load_catalog(path: str, modified_at: int, size: int) -> dict[str, Movie]:
    """파일 변경 시 캐시를 갱신한다. 사용자 대화는 캐시에 저장하지 않는다."""
    return load_movies(path)


def on_movie_change() -> None:
    movie_id = st.session_state.selected_movie_id
    # A draft about the previous film must never follow a new film selection.
    st.session_state.question = ""
    if movie_id:
        thread = get_thread(st.session_state.threads_by_movie, movie_id)
        st.session_state.document_question = next((row["content"] for row in reversed(thread) if row["role"] == "user"), "")


def select_discovered_movie(movie_id: str) -> None:
    st.session_state.selected_movie_id = movie_id
    on_movie_change()


def clear_selected_thread() -> None:
    movie_id = st.session_state.selected_movie_id
    if movie_id:
        clear_thread(st.session_state.threads_by_movie, movie_id)


def fill_search_example(text: str) -> None:
    """Only fill the search box; the form remains the request boundary."""
    st.session_state.discovery_query = text


def fill_suggested_question(movie_id: str, text: str) -> None:
    """Streamlit chat prefill does not return a submission until Send is used."""
    if st.session_state.selected_movie_id == movie_id:
        st.session_state.question = text


def selection_label(movie: Movie) -> str:
    return movie_label(movie).rsplit(" · ID ", 1)[0]


def render_movie_card(movie: Movie) -> None:
    summary = movie_summary(movie)
    st.caption("선택한 영화")
    title = movie.title or movie.original_title or "제목 미상"
    st.subheader(f"{title} ({summary['year']})")
    st.write(f"**감독** {summary['director']} · **상영 시간** {summary['runtime']}")
    st.caption(summary["genres"])
    st.write(f"**제공 데이터 평점** {summary['rating']} · {summary['vote_count']}")
    with st.expander("영화 상세 정보", expanded=False):
        st.write(f"영화 ID: {movie.movie_id}")
        st.write(f"원제: {movie.original_title or '미상'}")
        st.write(f"개봉일: {movie.release_date or '미상'}")
        st.write("출연: " + (", ".join(movie.cast) or "정보 없음"))
        st.write(f"원래 평점: {movie.vote_average if movie.vote_average is not None else '미상'}/10 · 평가 수: {summary['vote_count']}")
        st.caption("배포 메타데이터에 포함된 값이며 실시간 평점이 아닙니다.")
        if movie.tmdb_url:
            st.markdown(f"[영화 정보 원문 · TMDB]({movie.tmdb_url})")
    with st.expander("줄거리 보기 · 스포일러 포함 가능", expanded=False):
        st.write(movie.overview or "줄거리 정보가 없습니다.")


def render_sources(answer: str, sources: list[dict]) -> None:
    """step7과 같이 이 답변이 실제 인용한 번호의 출처만 표시한다."""
    from movie_lab.evidence import source_caption, source_quotes
    from movie_lab.display import metadata_quote_fields

    used = cited_sources(answer, sources)
    if not used:
        st.caption("답변에 인용된 근거가 없습니다.")
        return
    with st.expander(f"답변에 사용한 근거 {len(used)}건"):
        st.caption("답변의 [근거 N]과 연결된 원문입니다.")
        for number, source in used:
            title = source.get("title") or "제목 정보 없음"
            st.markdown(f"**[근거 {number}]** {title}")
            st.caption(source_caption(source))
            url = source.get("url", "")
            if isinstance(url, str):
                try:
                    parsed = urlsplit(url)
                    valid_url = parsed.scheme in {"https", "http"} and bool(parsed.netloc)
                except ValueError:
                    valid_url = False
                if valid_url:
                    st.markdown(f"[원문 열기]({url})")
            quotes = source_quotes(source)
            if source.get("source_kind") == "metadata" or source.get("scope") == "movie_metadata":
                fields = metadata_quote_fields(answer, number, source)
                if fields:
                    st.caption("관련 구절")
                    for field in fields:
                        st.write(field)
                elif quotes:
                    st.caption("인용 구절은 ‘전체 원래 인용’을 펼쳐 확인할 수 있습니다.")
                if quotes:
                    with st.expander(f"전체 원래 인용 · {len(quotes)}개 구절", expanded=False):
                        for position, quote in enumerate(quotes, 1):
                            st.caption(f"원래 구절 {position}")
                            st.write(quote)
            else:
                for quote in quotes:
                    st.write(quote)


def render_box_office() -> None:
    """Independent KOBIS lookup. Only an explicit form submission may request data."""
    from movie_lab.kobis import create_kobis_service, PUBLIC_SOURCE_URL, TERMS_URL

    with st.expander("날짜별 국내 박스오피스 · KOBIS", expanded=False):
        st.caption("날짜별 국내 흥행 정보입니다. 영화 대화의 근거와는 별도로 제공합니다.")
        st.markdown(f"출처: [영화진흥위원회 통합전산망 오픈 API]({PUBLIC_SOURCE_URL}) · [이용약관]({TERMS_URL})")
        with st.expander("조회 설정 안내", expanded=False):
            st.caption("이 보조 조회에만 별도 KOBIS_API_KEY가 필요합니다. 영화 찾기와 질문에는 필요하지 않습니다. 키는 로컬 .env에 설정합니다.")
        st.caption("조회 캐시는 비활성입니다. 같은 날짜도 조회 버튼을 다시 누르면 새 요청을 시작합니다. 일반 화면 재표시는 재호출하지 않습니다.")
        yesterday = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=1)
        with st.form("kobis_lookup"):
            target = st.date_input("집계 날짜 (한국 기준)", value=yesterday,
                                   max_value=yesterday, format="YYYY-MM-DD", key="kobis_target_date")
            submitted = st.form_submit_button("박스오피스 조회", key="kobis_submit")
        if submitted:
            try:
                if "kobis_service" not in st.session_state:
                    st.session_state.kobis_service = create_kobis_service(cache_ttl=0)
                # Migrate a service already retained by an older browser session.
                st.session_state.kobis_service.cache_ttl = 0
                with st.spinner("해당 날짜의 KOBIS 집계를 확인하는 중..."):
                    st.session_state.kobis_report = st.session_state.kobis_service.daily_box_office(target, refresh=True)
            except Exception:
                # KOBIS request URLs can contain credentials; never echo the exception.
                st.session_state.kobis_report = {"status": "failure", "error": {
                    "category": "조회 준비 실패", "message": "KOBIS 설정과 연결 상태를 확인하세요."}}
        report = st.session_state.get("kobis_report")
        if not report:
            st.caption("날짜를 고른 뒤 조회 버튼을 눌러 확인하세요.")
            return
        st.caption(f"최근 명시 조회의 HTTP 요청: {report.get('calls', '미상')}회 · 화면 재표시만으로는 재호출하지 않습니다.")
        state = report.get("status")
        if state == "unconfigured":
            st.info("KOBIS_API_KEY가 설정되지 않았습니다. 키를 로컬 .env에 설정한 뒤 앱을 다시 실행하세요.")
            return
        if state == "failure":
            error = report.get("error") or {}
            st.warning(error.get("message") or "KOBIS 조회에 실패했습니다. 기존 영화 서비스는 계속 사용할 수 있습니다.")
            st.caption(f"오류 분류: {error.get('category') or '확인 필요'} · HTTP 상태: {error.get('http_status') or '미수신'}")
            return
        st.write(f"**조회 집계일:** {report.get('target_date', '미상')} · 국내 일별 박스오피스 상위 목록")
        st.caption(f"집계 범위: {report.get('show_range') or '응답에 집계 범위 없음'} · 지역·한국/외국·다양성/상업 필터 미지정 · 최대 10개")
        st.caption("일별 관객·매출과 개봉 이후 누적 관객·매출을 구분합니다. 집계값은 조회 시점에 따라 달라질 수 있으며 모든 영화의 최종 흥행정보가 아닙니다.")
        if state == "empty":
            st.info("해당 조회 조건의 결과가 없습니다. 빈 결과나 누락 수치를 0으로 바꾸지 않습니다.")
        else:
            def number(value):
                return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else "미상"
            st.dataframe([{"순위": number(row.get("rank")), "영화명": row.get("title") or "미상",
                           "KOBIS 영화 코드": row.get("movie_code") or "미상",
                           "일별 관객 (명)": number(row.get("audience_daily")),
                           "누적 관객 (명)": number(row.get("audience_cumulative")),
                           "일별 매출 (원)": number(row.get("sales_daily")),
                           "누적 매출 (원)": number(row.get("sales_cumulative"))}
                          for row in report.get("rows", [])], hide_index=True)
        source = report.get("source") or {}
        st.caption(f"수집 시점: {source.get('collected_at') or '미상'} · 현재 화면의 명시 조회 결과")
        st.caption("현재 화면만 임시 표시하며 파일·DB·LLM·RAG로 전달하지 않습니다. 새 조회에 과거 결과를 재사용하지 않습니다.")


st.set_page_config(page_title="Movie Lab", layout="centered")
st.title("Movie Lab")
st.caption("영화를 고르고 질문하면, 답변과 원문 근거를 함께 확인할 수 있어요.")
# Native theme/layout do the styling. Only long content and small-screen spacing
# need scoped CSS; no remote assets, hidden controls or DOM rewriting.
st.html("""<style>
[data-testid="stMain"] .block-container {max-width: 58rem; padding-top: 2.5rem;}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] {overflow-wrap: anywhere; line-height: 1.65;}
[data-testid="stMain"] button p {white-space: normal; overflow-wrap: anywhere;}
@media (max-width: 640px) {
  [data-testid="stMain"] .block-container {padding: 1.25rem 1rem 6rem;}
  [data-testid="stMain"] h1 {font-size: 2rem;}
  [data-testid="stMain"] h3 {font-size: 1.35rem;}
}
</style>""")
try:
    path = resolve_movies_path()
    attributes = path.stat()
    movies = load_catalog(str(path), attributes.st_mtime_ns, attributes.st_size)
except DataLoadError as error:
    st.error(str(error))
    st.stop()
except OSError:
    st.error("영화 데이터 파일을 읽을 수 없습니다. MOVIES_DATA_PATH 설정을 확인하세요.")
    st.stop()

st.session_state.setdefault("threads_by_movie", {})
st.session_state.setdefault("selected_movie_id", None)
if st.session_state.selected_movie_id not in movies:
    st.session_state.selected_movie_id = None

with st.sidebar:
    st.header("내 영화 선택")
    movie_id = st.selectbox(
        "질문할 영화",
        options=list(movies),
        index=None,
        key="selected_movie_id",
        format_func=lambda value: selection_label(movies[value]),
        placeholder="제목으로 검색하거나 영화를 고르세요",
        on_change=on_movie_change,
    )
    st.caption(f"불러온 영화 {len(movies):,}편")
    st.caption("대화는 현재 브라우저 세션 동안 영화별로 보존됩니다.")
    with st.expander("대화 관리", expanded=False):
        st.button("이 영화의 대화 지우기", key="clear_current_thread",
                  on_click=clear_selected_thread, disabled=not movie_id, width="stretch")
    with st.expander("고급 설정 · 저장소 진단", expanded=False):
        index_status = inspect_index_status(resolve_index_path(), movies)
        if index_status["state"] == "ready":
            st.caption(f"메타데이터 색인 {index_status['count']:,}건 · 저장소 연결됨")
        elif index_status["state"] == "absent":
            st.caption("메타데이터 색인이 없습니다. 저장된 문서 0건")
        elif index_status["state"] == "partial":
            st.warning(f"메타데이터 색인 {index_status['count']:,}건 중 현재 데이터와 일치하는 문서는 {index_status['verified']:,}건입니다. 색인 갱신이 필요합니다.")
        elif index_status["state"] == "incompatible":
            st.warning("메타데이터 색인 설정이 현재 텍스트 버전과 다릅니다. 새 색인이 필요합니다.")
        else:
            st.warning("메타데이터 저장소 연결에 실패했습니다. 경로와 저장소 상태를 확인하세요.")

with st.expander("자연어로 영화 찾기", expanded=not bool(movie_id)):
    st.write("제목을 찾거나 감독·연도·장르로 범위를 좁혀보세요.")
    with st.container(horizontal=True):
        for index, example in enumerate(("인터스텔라", "크리스토퍼 놀란 감독 영화", "2014년 SF 영화")):
            st.button(example, key=f"discovery_example_{index}", on_click=fill_search_example, args=(example,))
    with st.form("movie_discovery"):
        discovery_query = st.text_input("제목·감독·연도·장르 또는 찾는 내용", key="discovery_query", placeholder="예: 2014년 SF 영화")
        discover_clicked = st.form_submit_button("영화 탐색", key="run_discovery", type="primary")
    st.caption("예시는 검색어만 채웁니다. ‘영화 탐색’을 눌러 검색하세요.")
    if discover_clicked and not discovery_query.strip():
        st.info("찾고 싶은 제목이나 조건을 입력해주세요.")
    if discover_clicked and discovery_query.strip():
        with st.spinner("조건과 영화 메타데이터를 확인하는 중..."):
            try:
                st.session_state.discovery_report = search_catalog(discovery_query.strip(), movies)
            except Exception:
                st.session_state.discovery_report = discover_movies(discovery_query.strip(), movies)
                st.session_state.discovery_report["notes"].append("의미 검색 연결에 실패해 메타데이터 조건·키워드 검색을 사용했습니다.")
    found = st.session_state.get("discovery_report")
    if found:
        st.caption(f"검색 결과 · {found.get('query', '')}")
        for note in found["unverifiable"]:
            st.warning(note)
        for note in found["notes"]:
            st.caption(note)
        if not found["results"]:
            discovery_state = found.get("discovery_state")
            if discovery_state == "unsupported":
                st.info("해석하거나 검증할 수 없는 조건이 있어 조건 충족 결과를 확정하지 않았습니다.")
            elif discovery_state == "unverifiable_data":
                st.info("조건 확인에 필요한 필드가 부족해 일치 여부를 확인하지 못했습니다.")
            else:
                st.info("현재 데이터에서 확인할 수 있는 결과가 없습니다.")
        if found.get("missing_by_movie"):
            st.caption(f"조건 필드가 부족해 검증하지 못한 작품 {len(found['missing_by_movie']):,}편은 일치 결과에서 제외했습니다.")
        for result in found["results"]:
            if result["movie_id"] not in movies:
                continue
            st.write("**" + selection_label(movies[result["movie_id"]]) + "**")
            for evidence in result["evidence"]:
                st.caption(evidence)
            st.button("이 영화 선택", key=f"choose_discovery_{result['movie_id']}",
                      on_click=select_discovered_movie, args=(result["movie_id"],))

if not movie_id:
    st.write("영화를 고르면 이곳에서 질문하고 답변의 원문을 확인할 수 있어요.")
    st.caption(f"제공 데이터 {len(movies):,}편 · 검색 결과에서 선택하거나 사이드바의 ‘질문할 영화’를 이용하세요.")
    render_box_office()
    st.stop()

movie = movies[movie_id]
render_movie_card(movie)

st.session_state.setdefault("preparations_by_movie", {})
with st.expander("고급 설정 · 자료 미리 준비", expanded=False):
    st.caption("질문하면 필요한 자료를 자동으로 확인합니다. 자료 경로나 수집 방식을 바꾸거나 미리 준비할 때만 사용하세요.")
    st.text_area("자료를 준비할 질문", key="document_question")
    with st.expander("자료 경로와 갱신 설정"):
        snapshot_input = st.text_input("스냅샷 ZIP 경로", value=str(resolve_snapshot_path()), key="snapshot_path")
        source_choice = st.selectbox("자료 사용 방식", ["실시간 우선", "제공 스냅샷"], key="document_source_mode")
        source_mode = "snapshot" if source_choice == "제공 스냅샷" else "auto"
        refresh_documents = st.checkbox("성공 캐시를 갱신하고 원문을 다시 확인", key="refresh_documents")
        st.caption("실시간 위키 요청에는 로컬 WIKI_CONTACT 설정이 필요합니다. 없거나 접근이 제한되면 지정한 스냅샷을 사용합니다.")
    prepare_clicked = st.button("자료 준비", key="prepare_documents")
    if prepare_clicked:
        preparation_question = st.session_state.document_question.strip()
        if not preparation_question:
            st.warning("자료를 준비할 질문을 입력하세요.")
        else:
            thread = get_thread(st.session_state.threads_by_movie, movie_id)
            if not thread or thread[-1] != {"role": "user", "content": preparation_question}:
                append_user_message(st.session_state.threads_by_movie, movie_id, preparation_question)
            pipeline = None
            with st.status("질문 자료를 준비하는 중...", expanded=True) as preparation_status:
                try:
                    pipeline = create_document_pipeline(snapshot_input, source_mode=source_mode)
                    prepared = pipeline.prepare(movie, preparation_question, thread,
                                                refresh=refresh_documents, progress=st.write)
                    st.session_state.preparations_by_movie[movie_id] = prepared
                    preparation_status.update(label="자료 준비 완료" if prepared["complete"] else "자료 준비 일부 실패",
                                              state="complete" if prepared["complete"] else "error", expanded=False)
                except Exception as error:
                    st.session_state.preparations_by_movie[movie_id] = {"complete": False, "error": safe_error(error)}
                    preparation_status.update(label="자료 준비 실패", state="error", expanded=False)
                finally:
                    if pipeline is not None:
                        try:
                            pipeline.close()
                        except Exception:
                            st.warning("자료 저장소 종료 상태를 확인하지 못했습니다.")
    prepared = st.session_state.preparations_by_movie.get(movie_id)
    if prepared:
        if prepared.get("error"):
            st.warning(prepared["error"]["category"])
        if prepared.get("live_reason"):
            st.caption(prepared["live_reason"])
        if prepared.get("cache_hit"):
            st.caption("이 질문의 성공한 수집 결과를 재사용했습니다.")
        if prepared.get("queries"):
            st.write("검색어: " + " / ".join(prepared["queries"]))
        if prepared.get("selection", {}).get("reasons"):
            with st.expander("후보 선별 이유 · 제목과 요약 기준"):
                names = {row["candidate_id"]: row["title"] for row in prepared.get("candidate_titles", [])}
                for reason in prepared["selection"]["reasons"]:
                    st.caption(f"{names.get(reason['candidate_id'], reason['candidate_id'])}: {reason['reason']}")
        for document in prepared.get("documents", []):
            label = "실시간 수집" if document["source_kind"] == "live" else "제공 스냅샷"
            st.write(f"{document['title']} · {label} · {document['identity']}")
            st.markdown(f"[원문]({document['url']})")
            st.caption(f"수집 시점: {document['collected_at']}")
        if prepared.get("index"):
            st.caption(f"수집 문서 {len(prepared.get('documents', []))}건 · 확인된 청크 {prepared['index']['chunk_count']}개")
        for rejected in prepared.get("rejected", []):
            st.caption(f"제외: {rejected['title']} · {rejected['reason']}")

selected_mode = st.radio("질문 방식", ["근거 기반 질문", "작품·현실 배경 확인"],
                         key="answer_mode", horizontal=True)
mode = "verify" if selected_mode == "작품·현실 배경 확인" else "general"
if mode == "verify":
    st.caption("확인할 주장을 적어주세요. 영화 정보·작품 속 묘사·현실 사실을 나누어 확인합니다.")
else:
    st.caption("아래 질문창에 궁금한 점을 적어주세요. 답변 아래에서 원문을 확인할 수 있습니다.")
messages = get_thread(st.session_state.threads_by_movie, movie_id)
suggestions = suggested_questions(movie)
if suggestions and mode == "general":
    with st.expander("이렇게 질문해보세요", expanded=not bool(messages)):
        for index, suggestion in enumerate(suggestions):
            st.button(suggestion, key=f"suggest_question_{movie_id}_{index}",
                      on_click=fill_suggested_question, args=(movie_id, suggestion), width="stretch")
        st.caption("질문창에 문구만 채웁니다. 내용을 확인하고 전송하세요.")
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(answer_for_display(message["content"], message["sources"])
                    if message["role"] == "assistant" else message["content"])
        if message["role"] == "assistant":
            render_sources(message["content"], message["sources"])

retry = False
had_pending_question = bool(messages and messages[-1]["role"] == "user")
if had_pending_question:
    retry = st.button("마지막 질문으로 다시 답변", key="retry_answer")
question = st.chat_input("확인할 주장을 입력하세요" if mode == "verify" else "이 영화에 대해 질문하세요",
                         key="question", submit_mode="disable")
requested_question = question.strip() if isinstance(question, str) else (messages[-1]["content"] if retry else "")
if requested_question:
    answer_to_render = None
    answer_notice = None
    answer_failure = None
    if question:
        append_user_message(st.session_state.threads_by_movie, movie_id, requested_question)
        with st.chat_message("user"):
            st.markdown(requested_question)
    with st.status("질문에 필요한 자료를 확인하는 중...", expanded=False) as answer_status:
        def show_progress(event: str) -> None:
            # Labels follow real backend events; there is no synthetic percentage
            # or separate review event where the backend only reports a pair.
            if event == "질문에 필요한 자료와 선택 영화 근거를 확인하는 중":
                answer_status.update(label="질문에 필요한 자료를 확인하는 중...")
            elif event == "영화 ID로 제한해 검색하고 겹치는 근거를 정리하는 중":
                answer_status.update(label="선택한 영화의 근거를 찾는 중...")
            elif event == "제공 근거로 답변을 생성하고 인용 구절·의미를 확인하는 중":
                answer_status.update(label="답변 작성 · 근거 검토 중...")
            st.caption(event)
        try:
            service = create_rag_service(snapshot_input, progress=show_progress, source_mode=source_mode)
            result = service.answer(movie, requested_question, messages, mode=mode, refresh=refresh_documents)
            if result.get("content"):
                answer_to_render = append_assistant_message(st.session_state.threads_by_movie, movie_id, result["content"], result["sources"])
                semantic_status = result.get("validation", {}).get("semantic_check")
                if semantic_status == "item_review_held":
                    answer_status.update(label="판정 검토 보류", state="error", expanded=False)
                    answer_notice = ("warning", "판정과 인용 근거의 관계를 확인하지 못해 검토를 보류했습니다. 주장이 거짓이라는 뜻은 아닙니다.")
                elif semantic_status == "item_review_partial":
                    answer_status.update(label="일부 항목 검토 보류", state="complete", expanded=False)
                    answer_notice = ("warning", "확인된 항목과 검토를 보류한 항목을 나누어 표시했습니다. 보류한 항목에는 근거를 붙이지 않습니다.")
                elif semantic_status == "no_factual_assertions" or result.get("validation", {}).get("generation_skipped"):
                    answer_status.update(label="근거 부족 안내", state="complete", expanded=False)
                    answer_notice = ("info", "현재 확보한 근거로는 질문한 내용을 확인하지 못했습니다. 근거 부족을 거짓으로 판정하지 않습니다.")
                elif semantic_status == "item_review_passed" and any(check.get("verdict") == "근거 부족" for check in result.get("checks", [])):
                    answer_status.update(label="일부 확인 · 근거 부족 포함", state="complete", expanded=False)
                    answer_notice = ("info", "확인 가능한 항목은 근거와 함께 답했지만, 일부 항목은 현재 확보한 근거로 확인하지 못했습니다. 근거 부족을 거짓으로 판정하지 않습니다.")
                else:
                    answer_status.update(label="답변과 인용 확인 완료", state="complete", expanded=False)
                for notice in result.get("retrieval", {}).get("diagnostics", {}).get("warnings", []):
                    st.caption(notice)
            else:
                answer_status.update(label="답변 생성 실패", state="error", expanded=False)
                answer_failure = result.get("error", {}).get("category", "답변을 확인하지 못했습니다.")
        except Exception as error:
            answer_status.update(label="답변 생성 실패", state="error", expanded=False)
            answer_failure = safe_error(error)["category"]
    if answer_failure:
        st.error(answer_failure)
        st.caption("질문과 이전 기록을 보존했습니다. 마지막 질문으로 다시 답변할 수 있습니다.")
        if not had_pending_question:
            st.button("마지막 질문으로 다시 답변", key="retry_answer")
    if answer_to_render:
        # Keep the completed answer outside the collapsed progress container.
        if answer_notice:
            if answer_notice[0] == "warning":
                st.warning(answer_notice[1])
            else:
                st.info(answer_notice[1])
        if result.get("retrieval", {}).get("diagnostics", {}).get("external_error"):
            st.warning("근거 검색 연결에 실패해 저장된 자료로 답했습니다. 일부 근거를 놓쳤을 수 있습니다.")
        with st.chat_message("assistant"):
            st.markdown(answer_for_display(answer_to_render["content"], answer_to_render["sources"]))
            render_sources(answer_to_render["content"], answer_to_render["sources"])
elif question:
    st.warning("질문 내용을 입력하세요.")

# Secondary lookup is kept out of the reading path between a question and answer.
render_box_office()
