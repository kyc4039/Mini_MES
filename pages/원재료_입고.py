import streamlit as st
from datetime import datetime

from src import queries
from src import process_rules as pr
from src.services import RawLotRegistration, register_raw_lot


st.set_page_config(page_title="원자재 입고", layout="centered")

st.markdown(
    '<div style="background:linear-gradient(135deg,#EF9F27 0%,#BA7517 100%);'
    'border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1rem;">'
    '<div style="font-size:22px;font-weight:600;color:#fff;">원재료 입고</div>'
    '<div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:2px;">'
    "원자재 LOT을 등록하고 품목별 재고 현황을 확인합니다.</div></div>",
    unsafe_allow_html=True,
)



# ── 데이터 조회 ──────────────────────────────────────────────
raw_items = queries.raw_items()
lots_df = queries.raw_lots()
stock_df = queries.raw_stock_by_item()

LOW_STOCK_RATIO = 0.2 # 잔여비율 20% 미만이면 재고부족 임박으로 간주

low_stock_count = 0
if not stock_df.empty:
    ratio = stock_df["remaining_qty"] / stock_df["received_qty"]
    low_stock_count = int((ratio < LOW_STOCK_RATIO).sum())

latest_intake = lots_df["created_at"].max() if not lots_df.empty else "-"
latest_intake_display = f"{latest_intake[2:4]}-{latest_intake[5:10]}" if latest_intake != "-" else "-"  # YY-MM-DD



# ── ① KPI 카드 ──────────────────────────────────────────────
def metric_card(label: str, value: str, danger: bool = False):
    color = "#C0392B" if danger and value != "0" else "inherit"
    with st.container(border=True):
        st.markdown(
            '<div style="text-align:center;padding:4px 0;">'
            f'<div style="font-size:13px;color:#888780;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:19px;font-weight:600;color:{color};'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
            f'title="{value}">{value}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.write("")

kpi_cols = st.columns(4)
with kpi_cols[0]:
    metric_card("원자재 품목", f"{len(raw_items)}")
with kpi_cols[1]:
    metric_card("총 입고 LOT", f"{len(lots_df)}")
with kpi_cols[2]:
    metric_card("재고부족 임박", f"{low_stock_count}", danger=True)
with kpi_cols[3]:
    metric_card("최근 입고", latest_intake_display)




# ── ② 품목별 잔여재고 ─────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 품목별 잔여재고")

    if stock_df.empty:
        st.caption("등록된 원자재가 없습니다.")
    else:
        rows_html = ""
        for row in stock_df.itertuples():
            ratio = row.remaining_qty / row.received_qty if row.received_qty else 0
            width_pct = max(round(ratio * 100), 2)
            bar_color = "#E24B4A" if ratio < LOW_STOCK_RATIO else "#5DCAA5"
            rows_html += (
                '<div style="margin-bottom:10px;">'
                '<div style="display:flex;justify-content:space-between;'
                f'font-size:14px;margin-bottom:4px;"><span>{row.item_name}</span>'
                f'<span style="color:#888780;">{row.remaining_qty:.1f}{row.unit}</span></div>'
                '<div style="height:6px;border-radius:3px;background:#F1EFE8;">'
                f'<div style="height:6px;border-radius:3px;width:{width_pct}%;'
                f'background:{bar_color};"></div></div>'
                "</div>"
            )
        st.markdown(rows_html, unsafe_allow_html=True)
        st.write("")



# ── ③ 입고 등록 ──────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 입고 등록")

    if not raw_items:
        st.warning("등록된 원자재 품목이 없습니다.")
    else:
        item_options = {f"{row['item_code']} | {row['item_name']}": row for row in raw_items}

        if "raw_intake_dt" not in st.session_state:
            st.session_state["raw_intake_dt"] = datetime.now()

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        item_label = c1.selectbox("품목", list(item_options.keys()), label_visibility="collapsed", placeholder="품목")
        selected_item = item_options[item_label]

        intake_clock = c2.time_input(
            "입고시각", value=st.session_state["raw_intake_dt"].time().replace(second=0, microsecond=0),
            label_visibility="collapsed", key="raw_intake_clock",
        )
        qty = c3.number_input("입고수량", label_visibility="collapsed", min_value=0.0, value=10.0, step=1.0)
        submitted = c4.button("등록", use_container_width=True)

        if submitted:
            existing_lot_nos = queries.lot_numbers_for_item(selected_item["item_id"])
            suggested_lot_no = pr.suggest_next_lot_no(
                existing_lot_nos, fallback=f"{selected_item['item_code']}-LOT001"
            )
            intake_dt = datetime.combine(datetime.now().date(), intake_clock)
            data = RawLotRegistration(
                lot_no=suggested_lot_no,
                item_id=selected_item["item_id"],
                qty=qty,
                created_at=intake_dt.strftime("%Y-%m-%d %H:%M"),
            )
            try:
                result = register_raw_lot(data)
                st.success(f"{result['lot_no']} ({result['qty']} {selected_item['unit']}) 등록 완료")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


# ── ④ LOT 현황 (스크롤) ──────────────────────────────────────
with st.container(border=True):
    st.markdown("##### LOT 현황")

    if lots_df.empty:
        st.caption("등록된 LOT이 없습니다.")
    else:
        status_color = {"IN_PROCESS": "#378ADD", "CONSUMED": "#888780", "HOLD": "#BA7517"}
        rows_html = ""
        for row in lots_df.itertuples():
            color = status_color.get(row.status, "#888780")
            rows_html += (
                '<div style="display:flex;padding:6px 0;'
                'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                f'<div style="flex:3;">{row.lot_no}</div>'
                f'<div style="flex:2;color:#5F5E5A;">{row.item_name}</div>'
                f'<div style="flex:2;color:{color};text-align:right;">잔여 {row.remaining_qty:.1f}{row.unit}</div>'
                "</div>"
            )
        with st.container(height=260):
            st.markdown(rows_html, unsafe_allow_html=True)