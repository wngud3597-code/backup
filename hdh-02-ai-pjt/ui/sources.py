import streamlit as st

from contracts import Evidence


def render_citations_and_sources(cited_evidences: list[Evidence]):
    if not cited_evidences:
        st.caption(
            "ℹ️ 인용된 외부 문서 출처가 없습니다 (근거 부족 보류 또는 메타 설명)."
        )
        return

    with st.expander("📚 확인된 실제 인용 근거 (Click to view)", expanded=False):
        for ev in cited_evidences:
            badge = (
                "📊 [정형 통계]" if ev.kind == "survey_statistics" else "📄 [공식 문맥]"
            )
            st.markdown(f"**[근거 {ev.evidence_no}] {badge} {ev.title}**")
            st.caption(f"위치: `{ev.locator}` | 출처: `{ev.provenance_id}`")
            st.text(ev.text)
            st.divider()
