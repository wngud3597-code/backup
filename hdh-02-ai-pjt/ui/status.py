import streamlit as st

from config import validate_config


def render_status_sidebar():
    st.sidebar.markdown("### ⚙️ 시스템 상태 및 고지")
    status = validate_config()

    if status["api_key_present"]:
        st.sidebar.success("✅ GMS / OpenAI API 연결 준비 완료")
    else:
        st.sidebar.error("❌ API 키 미설정 (.env 파일을 확인하세요)")

    with st.sidebar.expander("📌 조사 방법론 및 해석 한계", expanded=False):
        st.caption(
            "- **표본 출처:** Stack Overflow Developer Survey 2026\n"
            "- **모집단 한계:** 자발적 응답자 기반으로 전 세계 개발자의 확률 표본이 아닙니다.\n"
            "- **비인과성:** 연도 간 수치 변화를 단일 개발자의 채택 행동 변화로 직접 단정하지 않습니다.\n"
            "- **ODbL 1.0:** 본 데이터는 Open Database License를 준수합니다."
        )
