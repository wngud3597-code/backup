import streamlit as st

from data.sqlite_db import DatabaseManager
from services.advisor import (
    diagnose_user_stack,
    find_migration_alternatives,
    recommend_project_stack,
)

db = DatabaseManager()


# 1. 풀스택 추천 UI
def render_stack_recommender():
    st.subheader("🛠️ 맞춤형 풀스택 아키텍처 설계")
    st.caption(
        "프로젝트 조건에 맞춰 AI가 논리적으로 기술 조합을 직접 설계하고, 설문 지표를 팩트 근거로 매핑합니다."
    )

    with st.form("form_stack_recommend"):
        c1, c2 = st.columns(2)
        with c1:
            project_type = st.selectbox(
                "1. 프로젝트 분야",
                [
                    "웹 서비스 (풀스택)",
                    "AI / 데이터 사이언스 플랫폼",
                    "고성능 분산 백엔드",
                    "스타트업 초고속 MVP",
                ],
            )
        with c2:
            priority = st.selectbox(
                "2. 최우선 고려 가치",
                [
                    "개발 생산성 및 빠른 출시",
                    "개발자 만족도 및 높은 코드 품질",
                    "안정성 및 검증된 인력 풀",
                ],
            )

        constraints = st.text_input(
            "3. 특이사항 또는 제약 조건 (선택)",
            placeholder="예: 2인 개발팀, 서버리스 선호, 실시간 웹소켓 필요",
        )
        submitted = st.form_submit_button(
            "🚀 맞춤 스택 설계 실행", use_container_width=True
        )

    if submitted:
        with st.spinner(
            "AI가 요구사항에 맞는 최적의 4대 레이어 스택을 설계하고 있습니다..."
        ):
            res = recommend_project_stack(project_type, priority, constraints)

            st.markdown("#### 📦 AI가 직접 선정한 4대 레이어 추천안")
            cols = st.columns(4)
            cat_titles = {
                "Language": "언어",
                "WebFramework": "웹 프레임워크",
                "Database": "데이터베이스",
                "Cloud": "클라우드",
            }

            for idx, rec in enumerate(res["recommendations"]):
                with cols[idx]:
                    with st.container(border=True):
                        st.caption(cat_titles.get(rec["layer"], rec["layer"]))
                        st.subheader(rec["tech_name"])
                        st.write(rec["reason"])

                        if rec["stat"]:
                            st.caption(
                                f"📊 실사용률 `{rec['stat']['usage']}%` | 만족도 `{rec['stat']['admired']}%`"
                            )

            st.divider()
            st.markdown("#### 💡 아키텍처 총평")
            st.info(res["overall_review"])


# 2. 대안 및 마이그레이션 탐색 UI
def render_migration_finder(current_tech_id: str):
    st.subheader("🔄 지능형 대안 및 마이그레이션 탐색")
    st.caption(
        "AI가 기준 기술의 특성을 고려하여 현업에서 검토할 만한 현실적인 대안과 트레이드오프를 도출합니다."
    )

    if current_tech_id == "global":
        st.info(
            "사이드바에서 특정 기술을 선택하시면 해당 기술의 맞춤 대안 비교가 시작됩니다."
        )
        return

    data = find_migration_alternatives(current_tech_id)
    if "status" in data and data["status"] == "error":
        st.warning(data["message"])
        return

    target = data["target"]
    st.markdown(f"**기준 기술:** `{target['name']}`")

    st.markdown("#### 🌟 AI 추천 대안 기술 TOP 3~4")
    for alt in data["alternatives"]:
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1:
                st.subheader(alt["name"])
                st.info(f"🏷️ {alt['tag']}")
                if alt["stat"]:
                    st.caption(
                        f"실사용률 `{alt['stat']['usage']}%`\n\n만족도 `{alt['stat']['admired']}%`"
                    )
            with c2:
                st.markdown(f"**👍 기준 대비 장점:** {alt['pros']}")
                st.markdown(f"**⚠️ 고려할 단점/비용:** {alt['cons']}")

    if data.get("advice"):
        st.divider()
        st.caption(f"💡 **마이그레이션 핵심 조언:** {data['advice']}")


# 3. 내 스택 진단기 UI
def render_stack_diagnostics():
    st.subheader("🩺 내 기술 스택 종합 건강성 진단")
    st.caption(
        "사용 중인 기술들을 선택하시면 생태계 지표와 함께 AI 아키텍트의 심층 분석 리포트를 제공합니다."
    )

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT technology_id, canonical_name, category FROM technology ORDER BY canonical_name ASC"
        )
        all_techs = [dict(r) for r in cursor.fetchall()]

    tech_dict = {
        t["technology_id"]: f"[{t['category']}] {t['canonical_name']}"
        for t in all_techs
    }

    # 기본 선택값: Python, PostgreSQL, FastAPI, AWS
    default_keys = [
        k for k in ["python", "postgresql", "fastapi", "aws"] if k in tech_dict
    ]
    selected_stacks = st.multiselect(
        "사용 중인 기술들을 선택하세요:",
        options=list(tech_dict.keys()),
        format_func=lambda x: tech_dict[x],
        default=default_keys,
    )

    if st.button("📊 내 스택 정밀 진단 실행", use_container_width=True):
        if not selected_stacks:
            st.warning("최소 1개 이상의 기술을 선택해 주세요.")
            return

        with st.spinner(
            "선택된 기술들의 지표를 교차 검증하고 아키텍처 진단 리포트를 작성 중입니다..."
        ):
            result = diagnose_user_stack(selected_stacks)
            cards = result["cards"]
            report = result["report"]

            # 1. 상단 기술별 핵심 지표 카드
            st.markdown("#### 📌 기술별 생태계 포지션")
            cols = st.columns(min(len(cards), 4))
            for idx, res in enumerate(cards):
                col = cols[idx % 4]
                with col, st.container(border=True):
                    st.subheader(res["name"])
                    st.caption(res["tag"])
                    st.metric("실사용률", f"{res['usage']}%")
                    st.metric("기사용자 만족도", f"{res['admired']}%")

            st.divider()

            # 2. 하단 AI 종합 진단 리포트 (질문하신 핵심 답변 영역!)
            st.markdown("#### 💡 AI 수석 아키텍트의 종합 처방 리포트")
            st.markdown(report)
