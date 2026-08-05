from datetime import datetime

import streamlit as st

from src import queries
from src.services import WorkOrderRegistration, register_work_order


st.set_page_config(page_title="작업지시 관리", layout="centered")

st.markdown(
    '<div style="background:linear-gradient(135deg,#AFA9EC 0%,#534AB7 100%);'
    'border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1rem;">'
    '<div style="font-size:22px;font-weight:600;color:#fff;">작업지시 관리</div>'
    '<div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:2px;">'
    "생산의 출발점 — 새 작업지시를 등록하고 전체 진행 상태를 확인합니다.</div></div>",
    unsafe_allow_html=True,
)


def metric_card(label: str, value: str):
    with st.container(border=True):
        st.markdown(
            '<div style="text-align:center;padding:4px 0;">'
            f'<div style="font-size:13px;color:#888780;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:19px;font-weight:600;'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
            f'title="{value}">{value}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.write("")


def suggest_work_order_no(existing_nos: list[str], date_str: str) -> str:
    """WO-{YYYYMMDD}-{그날 순번} 형식으로 제안."""
    prefix = f"WO-{date_str}-"
    matching = [n for n in existing_nos if n.startswith(prefix)]
    return f"{prefix}{len(matching) + 1:03d}"


# ── 데이터 조회 ──────────────────────────────────────────────
wo_df = queries.all_work_orders_detailed()
cell_item_list = queries.cell_items()

total_count = len(wo_df)
in_progress_count = int((wo_df["status"] == "IN_PROGRESS").sum()) if not wo_df.empty else 0
completed_count = int((wo_df["status"] == "COMPLETED").sum()) if not wo_df.empty else 0

avg_rate = 0.0
if not wo_df.empty:
    active_df = wo_df[wo_df["plan_qty"] > 0]
    if not active_df.empty:
        rates = active_df["actual_qty"] / active_df["plan_qty"] * 100
        avg_rate = round(rates.mean(), 1)

# ── KPI 카드 ────────────────────────────────────────────────
kpi_cols = st.columns(4)
with kpi_cols[0]:
    metric_card("전체 작업지시", f"{total_count}")
with kpi_cols[1]:
    metric_card("진행중", f"{in_progress_count}")
with kpi_cols[2]:
    metric_card("완료", f"{completed_count}")
with kpi_cols[3]:
    metric_card("평균 달성률", f"{avg_rate}%")


# ── 작업지시 등록 ─────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 작업지시 등록")

    if not cell_item_list:
        st.warning("등록된 완제품(CELL) 품목이 없습니다.")
    else:
        item_options = {f"{row['item_code']} | {row['item_name']}": row for row in cell_item_list}

        today_str = datetime.now().strftime("%Y%m%d")
        existing_nos = wo_df["work_order_no"].tolist() if not wo_df.empty else []
        suggested_no = suggest_work_order_no(existing_nos, today_str)

        c1, c2, c3, c4 = st.columns([1.6, 1.3, 1, 1])
        item_label = c1.selectbox("품목", list(item_options.keys()), label_visibility="collapsed", placeholder="품목")
        selected_item = item_options[item_label]

        work_order_no = c2.text_input(
            "작업지시 번호", value=suggested_no, label_visibility="collapsed"
        )
        plan_qty = c3.number_input(
            "계획수량", label_visibility="collapsed", min_value=0.0, value=100.0, step=10.0
        )
        submitted = c4.button("등록", use_container_width=True)

        if submitted:
            data = WorkOrderRegistration(
                work_order_no=work_order_no,
                item_id=selected_item["item_id"],
                plan_qty=plan_qty,
                status="WAITING",
            )
            try:
                result = register_work_order(data)
                st.success(f"{result['work_order_no']} 등록 완료 (계획 {plan_qty:g}개, 상태: WAITING)")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


# ── 작업지시 목록 (스크롤) ─────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 작업지시 목록")

    if wo_df.empty:
        st.caption("등록된 작업지시가 없습니다.")
    else:
        status_color = {
            "WAITING": "#888780",
            "IN_PROGRESS": "#378ADD",
            "COMPLETED": "#5DCAA5",
            "CANCELED": "#E24B4A",
        }
        rows_html = ""
        for row in wo_df.itertuples():
            rate = round(row.actual_qty / row.plan_qty * 100, 1) if row.plan_qty else 0.0
            color = status_color.get(row.status, "#888780")
            rows_html += (
                '<div style="display:flex;padding:6px 0;'
                'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                f'<div style="flex:2.5;">{row.work_order_no}</div>'
                f'<div style="flex:2;color:#5F5E5A;">{row.item_name}</div>'
                f'<div style="flex:2;color:#888780;">{row.actual_qty:g}/{row.plan_qty:g} ({rate}%)</div>'
                f'<div style="flex:1.3;color:{color};text-align:right;font-weight:500;">{row.status}</div>'
                "</div>"
            )
        with st.container(height=280):
            st.markdown(rows_html, unsafe_allow_html=True)