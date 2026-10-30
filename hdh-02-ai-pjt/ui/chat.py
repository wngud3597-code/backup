import streamlit as st

from contracts import AnswerResult
from rag.retrieve import retrieve_all_evidences
from services.chat import ask_technology_question
from ui.sources import render_citations_and_sources


def init_chat_history(tech_id: str):
    if "chat_histories" not in st.session_state:
        st.session_state.chat_histories = {}
    if tech_id not in st.session_state.chat_histories:
        st.session_state.chat_histories[tech_id] = []


def format_rendered_text(sentences: list) -> str:
    """줄바꿈과 불릿 포인트를 살리면서 [근거 n] 뱃지를 예쁘게 부착"""
    formatted_parts = []
    for s in sentences:
        txt = s.text.strip()
        cit_str = (
            "".join([f" `[근거 {c}]`" for c in s.citations]) if s.citations else ""
        )

        # 불릿 포인트나 소제목인 경우 줄바꿈 유지
        if txt.startswith(("- ", "### ", "* ")):
            formatted_parts.append(f"\n{txt}{cit_str}")
        else:
            formatted_parts.append(f"{txt}{cit_str}")

    # 자연스러운 단락 형성
    res = " ".join(formatted_parts)
    return res.replace(" \n", "\n").replace("\n ", "\n")


def handle_chat_turn(tech_id: str, prompt: str):
    init_chat_history(tech_id)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("근거 문서와 설문 통계를 분석하는 중입니다..."):
            answer_res: AnswerResult = ask_technology_question(tech_id, prompt)

            full_text = format_rendered_text(answer_res.sentences)
            st.markdown(full_text)

            all_evs, _ = retrieve_all_evidences(tech_id, prompt)
            ev_map = {e.evidence_no: e for e in all_evs}
            used_cits = set()
            for s in answer_res.sentences:
                used_cits.update(s.citations)
            cited_evs = [ev_map[cid] for cid in sorted(used_cits) if cid in ev_map]

            render_citations_and_sources(cited_evs)

    st.session_state.chat_histories[tech_id].append(
        {"question": prompt, "answer_text": full_text, "evidences": cited_evs}
    )
    st.rerun()


def render_chat_messages(tech_id: str):
    init_chat_history(tech_id)
    history = st.session_state.chat_histories[tech_id]

    for turn in history:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            st.markdown(turn["answer_text"])
            if turn.get("evidences"):
                render_citations_and_sources(turn["evidences"])
