from datetime import datetime, timedelta

import streamlit as st

from src import queries
from src import process_rules as pr
from src.services import InputLotUsage, ProcessProductionRegistration, register_process_production


st.set_page_config(page_title="극판공정 실적", layout="centered")

st.markdown(
    '<div style="background:linear-gradient(135deg,#5DCAA5 0%,#0F6E56 100%);'
    'border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1rem;">'
    '<div style="font-size:22px;font-weight:600;color:#fff;">극판공정 실적</div>'
    '<div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:2px;">'
    "믹싱 · 코팅 · 프레스 · 슬리팅</div></div>",
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



# ── 공정 선택 ────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 공정 선택")
    processes = queries.processes_by_group("전극")
    process_options = {row["process_name"]: row for row in processes}
    process_name = st.segmented_control(
        "공정", list(process_options.keys()), default=list(process_options.keys())[0],
        label_visibility="collapsed",
    )
    selected_process = process_options[process_name] if process_name else processes[0]
 
recipe = pr.PROCESS_RECIPE.get(selected_process["process_code"])



# ── 데이터 조회 ──────────────────────────────────────────────
group_stats = queries.production_group_stats("전극")
today_count = queries.today_group_lot_count("전극", datetime.now().strftime("%Y-%m-%d"))
work_orders = queries.work_orders_in_progress()
all_available_lots_df = queries.available_lots(("RAW", "WIP"))

if recipe:
    available_lots_df = pr.filter_input_lots(all_available_lots_df, recipe)
else:
    available_lots_df = all_available_lots_df




# ── KPI 카드 ────────────────────────────────────────────────
kpi_cols = st.columns(4)
with kpi_cols[0]:
    metric_card("오늘 생산 LOT", f"{today_count}")
with kpi_cols[1]:
    metric_card("진행중 작업지시", f"{len(work_orders)}")
with kpi_cols[2]:
    metric_card("투입 가능 LOT", f"{len(available_lots_df)}")
with kpi_cols[3]:
    latest = group_stats["latest"]
    metric_card("최근 실적", f"{latest[2:4]}-{latest[5:10]}" if latest else "-")



# ── 생산실적 등록 ─────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### 생산실적 등록")
 
    equipments = queries.equipment_by_process(selected_process["process_id"])
    workers = queries.workers_for_select()
 
    missing_categories = pr.missing_input_categories(all_available_lots_df, recipe) if recipe else []

    if not work_orders:
        st.warning("진행중인 작업지시가 없습니다.")
    elif not equipments:
        st.warning(f"'{process_name}' 공정에 등록된 설비가 없습니다.")
    elif missing_categories:
        st.warning(
            f"'{process_name}' 공정에 필요한 투입 품목 중 재고가 없는 게 있어요: "
            f"{', '.join(missing_categories)}. 먼저 이 품목들의 재고를 확보하세요."
        )
    elif available_lots_df.empty:
        st.warning(f"'{process_name}' 공정에 투입할 수 있는(잔여수량 있는) 원자재/재공품이 없습니다.")
    else:
        wo_options = {f"{r['work_order_no']} | {r['item_name']}": r["work_order_id"] for r in work_orders}
        eq_options = {f"{r['equipment_code']} | {r['equipment_name']}": r["equipment_id"] for r in equipments}
        worker_options = {f"{r['worker_code']} | {r['worker_name']}": r["worker_id"] for r in workers}
        lot_options = {
            f"{row.lot_no} | {row.item_name} | [{row.from_process}] | 잔여 {row.remaining_qty:.1f}{row.unit}": row.lot_id
            for row in available_lots_df.itertuples()
        }
 
        c1, c2, c3 = st.columns(3)
        wo_label = c1.selectbox("작업지시", list(wo_options.keys()))
        eq_label = c2.selectbox("설비", list(eq_options.keys()))
        worker_label = c3.selectbox("작업자", list(worker_options.keys()))

        if "electrode_start_dt" not in st.session_state:
            st.session_state["electrode_start_dt"] = datetime.now()

        c4, c5 = st.columns([1, 1])
        start_clock = c4.time_input(
            "시작시각",
            value=st.session_state["electrode_start_dt"].time().replace(second=0, microsecond=0),
            key="electrode_start_clock",
        )
        default_duration = pr.DEFAULT_DURATION_MIN.get(selected_process["process_code"], 20)
        duration_min = c5.number_input("예상 소요시간(분)", min_value=1, value=default_duration, step=5)

        start_dt = datetime.combine(datetime.now().date(), start_clock)
        start_time = start_dt.strftime("%Y-%m-%d %H:%M")
        end_time = (start_dt + timedelta(minutes=duration_min)).strftime("%Y-%m-%d %H:%M")
        start_time_valid = True
 
        st.caption(f"'{process_name}' 공정 표준 투입 품목만 표시됩니다.")
        input_lot_labels = st.multiselect("투입 LOT (잔여수량 표시)", list(lot_options.keys()))
 
        input_qty_map: dict[str, float] = {}
        for label in input_lot_labels:
            input_qty_map[label] = st.number_input(
                f"'{label}' 투입수량", min_value=0.0, value=1.0, step=0.5, key=f"qty_{label}"
            )
 
        # 결과 품목 — 레시피가 정의돼 있으면 자동 고정, 없으면 직접 선택
        if recipe:
            wip_items = queries.wip_items()
            matched = [r for r in wip_items if pr.matches_prefix(r["item_code"], recipe["output_prefix"])]
            if len(matched) == 1:
                selected_output_item = matched[0]
                st.info(f"결과 품목: {selected_output_item['item_code']} | {selected_output_item['item_name']}")
            elif len(matched) > 1:
                st.caption(f"'{recipe['output_prefix']}' 계열 품목이 여러 개 있어 선택이 필요합니다.")
                matched_options = {f"{r['item_code']} | {r['item_name']}": r for r in matched}
                output_item_label = st.selectbox("결과 품목", list(matched_options.keys()))
                selected_output_item = matched_options[output_item_label]
            else:
                st.error(f"'{recipe['output_prefix']}' 계열의 결과 품목을 item 테이블에서 찾을 수 없습니다.")
                selected_output_item = None
        else:
            wip_items = queries.wip_items()
            wip_item_options = {f"{r['item_code']} | {r['item_name']}": r for r in wip_items}
            output_item_label = st.selectbox("결과 품목", list(wip_item_options.keys()))
            selected_output_item = wip_item_options[output_item_label]
 
        if selected_output_item:
            existing_lot_nos = queries.lot_numbers_for_item(selected_output_item["item_id"])
            suggested_lot_no = pr.suggest_next_lot_no(
                existing_lot_nos, fallback=f"{selected_output_item['item_code']}-LOT001"
            )
 
            suggested_output_qty = pr.suggest_output_qty(selected_process["process_code"], input_qty_map)
 
            c6, c7 = st.columns(2)
            output_lot_no = c6.text_input("결과 LOT 번호", value=suggested_lot_no)
            output_qty = c7.number_input(
                "결과수량 (투입량 기준 자동계산됨, 수정 가능)",
                min_value=0.0, value=suggested_output_qty, step=0.5,
            )
 
            if st.button("생산실적 저장", type="primary", disabled=not start_time_valid):
                data = ProcessProductionRegistration(
                    work_order_id=wo_options[wo_label],
                    process_id=selected_process["process_id"],
                    equipment_id=eq_options[eq_label],
                    worker_id=worker_options[worker_label],
                    output_item_id=selected_output_item["item_id"],
                    output_lot_no=output_lot_no,
                    output_qty=output_qty,
                    start_time=start_time,
                    end_time=end_time,
                    input_lots=[
                        InputLotUsage(lot_id=lot_options[label], qty_used=input_qty_map[label])
                        for label in input_lot_labels
                    ],
                )
                try:
                    result = register_process_production(data)
                    st.success(f"저장 완료: {result['output_lot_no']}")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
 
 


# ── 최근 실적 (스크롤) ────────────────────────────────────────
with st.container(border=True):
    st.markdown(f"##### {process_name} 공정 최근 실적" if process_name else "##### 최근 실적")

    history_df = queries.process_production_history(selected_process["process_id"])
    if history_df.empty:
        st.caption("등록된 실적이 없습니다.")
    else:
        rows_html = ""
        for row in history_df.itertuples():
            rows_html += (
                '<div style="display:flex;padding:6px 0;'
                'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                f'<div style="flex:3;">{row.결과LOT}</div>'
                f'<div style="flex:2;color:#5F5E5A;">{row.equipment_name}</div>'
                f'<div style="flex:2;color:#888780;text-align:right;">{row.end_time}</div>'
                "</div>"
            )
        with st.container(height=240):
            st.markdown(rows_html, unsafe_allow_html=True)