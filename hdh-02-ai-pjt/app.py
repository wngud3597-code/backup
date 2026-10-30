import streamlit as st

from data.sqlite_db import DatabaseManager
from services.discovery import parse_and_filter_technologies
from ui.advisor import (
    render_migration_finder,
    render_stack_diagnostics,
    render_stack_recommender,
)
from ui.chat import handle_chat_turn, render_chat_messages
from ui.discovery import render_discovery_results
from ui.status import render_status_sidebar

st.set_page_config(
    page_title="StackOverflowing - Tech Navigator", page_icon="🚀", layout="wide"
)

# 👇 본문 + 하단 채팅바 둘 다 1050px로 칼같이 일치시키는 CSS
st.markdown(
    """
<style>
/* 1. 본문 영역 너비 제한 */
.stMainBlockContainer,
[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] > div:first-child {
    max-width: 1050px !important;
    padding-top: 1.5rem !important;
    padding-bottom: 6rem !important;
    margin: 0 auto !important;
}

/* 2. ⭐ 하단 고정 채팅바 너비도 본문과 똑같이 1050px로 중앙 정렬 */
[data-testid="stBottom"] > div,
.stBottom > div,
div[data-testid="stChatInput"] {
    max-width: 1050px !important;
    margin: 0 auto !important;
}

/* 하단 배경 깔끔하게 투명 처리 */
[data-testid="stBottom"] {
    background-color: transparent !important;
}
</style>
""",
    unsafe_allow_html=True,
)

if "selected_tech_id" not in st.session_state:
    st.session_state["selected_tech_id"] = "global"

db = DatabaseManager()

# 1. 사이드바
st.sidebar.title("🚀 StackOverflowing")
st.sidebar.caption("개발자 설문 데이터 기반 기술 의사결정 네비게이터")
render_status_sidebar()

st.sidebar.divider()
st.sidebar.subheader("🎯 기술 포커스 선택")

with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT technology_id, canonical_name, category FROM technology ORDER BY canonical_name ASC"
    )
    all_techs = [dict(r) for r in cursor.fetchall()]

tech_options = {"global": "🌐 [전체 기술 / 자유 질의]"}
for t in all_techs:
    tech_options[t["technology_id"]] = f"[{t['category']}] {t['canonical_name']}"

selected_id = st.sidebar.selectbox(
    "분석 대상 선택:",
    options=list(tech_options.keys()),
    format_func=lambda x: tech_options[x],
    index=list(tech_options.keys()).index(st.session_state["selected_tech_id"])
    if st.session_state["selected_tech_id"] in tech_options
    else 0,
)
st.session_state["selected_tech_id"] = selected_id

# 2. 메인 헤더
if selected_id == "global":
    st.title("🌐 전체 기술 생태계 자유 질의 & 의사결정")
    st.caption(
        "기술에 구애받지 않고 아키텍처, 비교, 트렌드 등 무엇이든 자유롭게 질문하세요."
    )
else:
    current_tech = db.get_technology(selected_id)
    current_stat = db.get_statistics(selected_id, year=2026)
    st.title(f"🚀 {current_tech['canonical_name']} 분석 대시보드")
    st.write(current_tech["description"])

    if current_stat:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usage (실사용률)", f"{current_stat.usage_pct}%")
        col2.metric("Desired (관심 희망률)", f"{current_stat.desired_pct}%")
        col3.metric("Admired (기사용자 만족도)", f"{current_stat.admired_pct}%")
        col4.metric("유효 응답자 수(n)", f"{current_stat.question_n:,}명")

st.divider()

# 3. 탭 구성
tabs = [
    "💬 인텔리전트 Q&A",
    "🛠️ 맞춤형 풀스택 추천",
    "🔄 대안 탐색 & 스택 진단",
    "🔎 조건 탐색",
]
tab1, tab2, tab3, tab4 = st.tabs(tabs)

with tab1:
    render_chat_messages(selected_id)

with tab2:
    render_stack_recommender()

with tab3:
    c_sub1, c_sub2 = st.tabs(["대안 및 마이그레이션 탐색", "내 스택 진단기"])
    with c_sub1:
        render_migration_finder(selected_id)
    with c_sub2:
        render_stack_diagnostics()

with tab4:
    st.subheader("🔎 자연어 및 수치 조건 기술 탐색")
    query_input = st.text_input("검색 조건을 입력하세요:", value="만족도 70% 이상 언어")
    if st.button("조건 검색 실행", key="btn_discovery"):
        results = parse_and_filter_technologies(query_input)
        render_discovery_results(results)

# 4. ⭐ ChatGPT 스타일 화면 최하단 플로팅 고정 채팅바 (탭 밖 루트 레벨 배치)
placeholder_msg = (
    "기술 비교, 추천, 트렌드 등을 자유롭게 질문하세요..."
    if selected_id == "global"
    else f"{tech_options[selected_id]}에 대해 질문하세요..."
)

if user_input := st.chat_input(placeholder_msg):
    handle_chat_turn(selected_id, user_input)
