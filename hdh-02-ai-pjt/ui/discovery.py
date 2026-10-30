from typing import Any

import streamlit as st


def render_discovery_results(results: list[dict[str, Any]]):
    if not results:
        st.warning(
            "조건에 부합하는 기술을 찾지 못했습니다. 검색 조건을 완화해 보세요 (예: 사용률 10% 이상 언어)."
        )
        return

    st.success(f"총 {len(results)}건의 기술이 조건에 일치합니다.")

    cols = st.columns(2)
    for idx, item in enumerate(results):
        col = cols[idx % 2]
        with col, st.container(border=True):
            st.subheader(item["canonical_name"])
            st.caption(f"범주: {item['category']}")
            st.markdown(
                f"- **Usage(사용률):** `{item['usage_pct']}%`\n"
                f"- **Admired(만족도):** `{item['admired_pct']}%`\n"
                f"- **Desired(관심도):** `{item['desired_pct']}%`"
            )
            if st.button(
                f"💬 {item['canonical_name']} 분석 대화로 이동",
                key=f"btn_nav_{item['technology_id']}",
            ):
                st.session_state["selected_tech_id"] = item["technology_id"]
                st.session_state["active_tab"] = "대화 및 분석"
                st.rerun()
