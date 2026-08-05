import streamlit as st

from src import queries


st.set_page_config(page_title="셀 시리얼 추적", layout="centered")

st.markdown(
    '<div style="background:linear-gradient(135deg,#B4B2A9 0%,#5F5E5A 100%);'
    'border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1rem;">'
    '<div style="font-size:22px;font-weight:600;color:#fff;">셀 시리얼 추적</div>'
    '<div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:2px;">'
    "역방향: 이 LOT의 원료 추적 · 정방향: 이 LOT이 어디까지 영향을 미쳤는지 추적</div></div>",
    unsafe_allow_html=True,
)


def metric_card(label: str, value: str, color: str = "inherit"):
    with st.container(border=True):
        st.markdown(
            '<div style="text-align:center;padding:4px 0;">'
            f'<div style="font-size:13px;color:#888780;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:14px;font-weight:600;color:{color};'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
            f'title="{value}">{value}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.write("")


# ── 검색 + LOT 선택 ────────────────────────────────────────────
with st.container(border=True):
    search_keywork = st.text_input(
        "LOT 번호 또는 품목명 검색", label_visibility="collapsed", placeholder="LOT 번호 또는 품목명 검색 (예: CELL-SN, 활물질)",
    )
    lots_df = queries.lot_search(keyword=search_keywork)

if lots_df.empty:
    st.info("검색 결과가 없습니다.")
    st.stop()

lot_label_map = {
    f"{row.lot_no} | {row.item_name} | {row.lot_type} | {row.status}": row.lot_id
    for row in lots_df.itertuples()
}
selected_label = st.selectbox("추적할 LOT 선택", list(lot_label_map.keys()))
selected_lot_id = lot_label_map[selected_label]
selected_row = lots_df[lots_df["lot_id"] == selected_lot_id].iloc[0]

st.write("")


# ── LOT 요약 카드 ───────────────────────────────────────────────
status_color = {"IN_PROCESS": "#378ADD", "CONSUMED": "#888780", "HOLD": "#BA7517", "COMPLETED": "#5DCAA5"}
kpi_cols = st.columns(4)
with kpi_cols[0]:
    metric_card("LOT 번호", selected_row["lot_no"])
with kpi_cols[1]:
    metric_card("품목", selected_row["item_name"])
with kpi_cols[2]:
    metric_card("현재 상태", selected_row["status"], color=status_color.get(selected_row["status"], "inherit"))
with kpi_cols[3]:
    created = selected_row["created_at"]
    metric_card("생성일", f"{created[2:4]}-{created[5:10]}" if created else "-")


# ── 추적 방향 + 결과 ────────────────────────────────────────────
with st.container(border=True):
    direction = st.segmented_control(
        "추적 방향",
        ["역방향 (원료 추적)", "정방향 (영향범위 추적)"],
        default="역방향 (원료 추적)",
        label_visibility="collapsed",
    )

    if direction and direction.startswith("역방향"):
        trace_df = queries.trace_upstream(selected_lot_id)
    else:
        trace_df = queries.trace_downstream(selected_lot_id)

    if trace_df.empty:
        st.caption("연결된 계보 기록이 없습니다. (원자재이거나, 아직 다음 공정에 투입되지 않은 LOT일 수 있습니다.)")
    else:
        rows_html = ""
        for row in trace_df.itertuples():
            process_display = row.process_name if row.process_name else "입고"
            time_display = row.start_time if row.start_time else "-"
            rows_html += (
                '<div style="display:flex;padding:6px 0;'
                'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                f'<div style="flex:3;">{row.lot_no}</div>'
                f'<div style="flex:2;color:#5F5E5A;">{row.item_name}</div>'
                f'<div style="flex:1.5;color:#888780;">{process_display}</div>'
                f'<div style="flex:2;color:#888780;text-align:right;">{time_display}</div>'
                "</div>"
            )
        with st.container(height=280):
            st.markdown(rows_html, unsafe_allow_html=True)
        st.caption(f"총 {len(trace_df)}건의 LOT이 연결되어 있습니다.")

st.write("")


# ── 검사 이력 (CELL 타입일 때만) ─────────────────────────────────
if selected_row["lot_type"] == "CELL":
    with st.container(border=True):
        st.markdown("##### 검사 이력")
        insp_df = queries.inspection_results_for_lot(selected_lot_id)
        if insp_df.empty:
            st.caption("이 LOT에 대한 검사 이력이 없습니다.")
        else:
            rows_html = ""
            for row in insp_df.itertuples():
                judge_color = "#5DCAA5" if row.judge == "PASS" else "#E24B4A"
                rows_html += (
                    '<div style="display:flex;padding:6px 0;'
                    'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                    f'<div style="flex:2;">{row.spec_name}</div>'
                    f'<div style="flex:2;color:#5F5E5A;">{row.measured_value} {row.unit} '
                    f'(기준 {row.lower_limit}~{row.upper_limit})</div>'
                    f'<div style="flex:1;color:{judge_color};text-align:right;font-weight:500;">{row.judge}</div>'
                    "</div>"
                )
            with st.container(height=200):
                st.markdown(rows_html, unsafe_allow_html=True)
        st.write("")

st.write("")        
st.caption(
    "이 추적은 lot_genealogy 테이블을 재귀적으로 따라가며 계산된다."
    "믹싱처럼 여러 LOT이 하나로 합쳐진 지점, 슬러팅처럼 하나가 여러 LOT으로 나뉜 지점도 자동으로 반영된다."
)
