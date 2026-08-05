import streamlit as st

from src import queries


st.set_page_config(page_title="배터리 셀 MES", layout="centered")

st.markdown(
    '<div style="background:linear-gradient(135deg,#378ADD 0%,#5DCAA5 100%);'
    'border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1rem;">'
    '<div style="font-size:24px;font-weight:600;color:#fff;">배터리 셀 MES</div>'
    '<div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:2px;">'
    "전극 · 조립 · 화성 공정 통합 현황판</div></div>",
    unsafe_allow_html=True,
)

# ── 데이터 조회 ──────────────────────────────────────────────
eq = queries.equipment_status_summary()
insp = queries.inspection_pass_rate()
wo_df = queries.work_order_progress()
recent_df = queries.recent_production(10)

wo_rate = 0.0
if not wo_df.empty:
    row = wo_df.iloc[0]
    if float(row["plan_qty"]) > 0:
        wo_rate = round(float(row["actual_qty"]) / float(row["plan_qty"]) * 100, 1)

# ── ① KPI 카드 (각각 별도 컨테이너 + 가운데 정렬) ────────────────
def metric_card(label: str, value: str):
    with st.container(border=True):
        st.markdown(
            '<div style="text-align:center;padding:4px 0;">'
            f'<div style="font-size:13px;color:#888780;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:24px;font-weight:600;">{value}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.write("")


metrics = [
    ("설비 가동률", f"{eq['rate']}%"),
    ("작업지시 진행률", f"{wo_rate}%"),
    ("검사 합격률", f"{insp['rate']}%"),
    ("최근 생산 건수", f"{len(recent_df)}"),
]
kpi_cols = st.columns(4)
for col, (label, value) in zip(kpi_cols, metrics):
    with col:
        metric_card(label, value)


# ── ② 공정 진행 파이프라인 ────────────────────────────────────
all_wo = queries.all_work_orders()

with st.container(border=True):
    color_map = {"완료": "#5DCAA5", "진행중": "#378ADD", "대기": "#D9D7CE"}
    legend_items = "".join(
        '<span style="margin-left:16px;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;'
        f'background:{color};margin-right:5px;vertical-align:middle;"></span>'
        f'<span style="vertical-align:middle;">{label}</span></span>'
        for label, color in color_map.items()
    )
    title_col, legend_col = st.columns([3, 2])
    title_col.markdown("##### 공정 진행 파이프라인")
    legend_col.markdown(
        f'<div style="text-align:right;font-size:12px;color:#5F5E5A;padding-top:8px;">'
        f"{legend_items}</div>",
        unsafe_allow_html=True,
    )

    if not all_wo:
        st.info("등록된 작업지시가 없습니다.")
    else:
        wo_options = {
            f"{row['work_order_no']} | {row['item_name']} ({row['status']})": row["work_order_id"]
            for row in all_wo
        }
        

        with st.container(border=True):
            
            selected_label = st.selectbox(
                "작업지시 선택", list(wo_options.keys()), label_visibility="collapsed"
            )
            selected_wo_id = wo_options[selected_label]
            

            achievement = queries.work_order_achievement(selected_wo_id)
            rate = achievement["rate"]
            bar_color = "#E24B4A" if rate < 30 else ("#EF9F27" if rate < 70 else "#5DCAA5")
            st.markdown(
                '<div style="display:flex;justify-content:space-between;'
                'font-size:13px;margin-bottom:4px;">'
                f'<span>작업지시 달성률</span>'
                f'<span style="color:#888780;">{achievement["actual_qty"]:.0f} / {achievement["plan_qty"]:.0f} ({rate}%)</span>'
                "</div>"
                '<div style="height:8px;border-radius:4px;background:#F1EFE8;">'
                f'<div style="height:8px;border-radius:4px;width:{max(rate, 2)}%;'
                f'background:{bar_color};"></div></div>',
                unsafe_allow_html=True,
            )

            pipeline = queries.work_order_pipeline(selected_wo_id)

            groups: dict[str, list] = {}
            for step in pipeline:
                groups.setdefault(step["process_group"], []).append(step)

            st.write("")

            cols = st.columns(len(groups))
            for col, (group_name, steps) in zip(cols, groups.items()):
                with col:
                    bars = "".join(
                        f'<div style="flex:1;height:6px;border-radius:3px;'
                        f'background:{color_map[s["status"]]};"></div>'
                        for s in steps
                    )
                    st.markdown(
                        f'<div style="font-size:12px;color:#888780;margin-bottom:3px;">{group_name}</div>'
                        f'<div style="display:flex;gap:3px;">{bars}</div>',
                        unsafe_allow_html=True,
                    )
            st.write("")



# ── ③ 설비 현황 + 공정별 불량현황 (카드 2개 나란히) ──────────────
col5, col6 = st.columns(2)

with col5:
    with st.container(border=True):
        st.markdown("##### 설비 현황")
        exceptions_df = queries.equipment_exceptions()
        status_html = {
            "MAINT": '<span style="color:#BA7517;">점검중</span>',
            "STOP": '<span style="color:#C0392B;">정지</span>',
        }

        with st.container(height=120):
            rows_html = ""
            for row in exceptions_df.itertuples():
                label = status_html.get(row.status, row.status)
                rows_html += (
                    '<div style="display:flex;justify-content:space-between;'
                    'padding:5px 0;border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                    f'<span>{row.equipment_name}</span><span>{label}</span></div>'
                )
            rows_html += (
                '<div style="display:flex;justify-content:space-between;padding:5px 0;font-size:14px;">'
                f'<span>그 외 {eq["run"]}대</span>'
                '<span><span style="color:#1D9E75;">가동중</span></span></div>'
            )
            st.markdown(rows_html, unsafe_allow_html=True)

with col6:
    with st.container(border=True):
        st.markdown("##### 공정별 불량 현황")
        defect_df = queries.defect_by_process()
        if defect_df.empty:
            st.caption("불량 이력이 없습니다.")
        else:
            with st.container(height=120):
                rows_html = ""
                for row in defect_df.itertuples():
                    rate = round(row.fail_count / row.total_count * 100)
                    rows_html += (
                        '<div style="margin-bottom:10px;">'
                        '<div style="display:flex;justify-content:space-between;'
                        f'font-size:14px;margin-bottom:4px;"><span>{row.process_name}</span>'
                        f'<span style="color:#888780;font-size:13px;">{row.fail_count}/{row.total_count}건 ({rate}%)</span></div>'
                        '<div style="height:6px;border-radius:3px;background:#F1EFE8;">'
                        f'<div style="height:6px;border-radius:3px;width:{rate}%;'
                        'background:#F0BBB0;"></div></div>'
                        "</div>"
                    )
                st.markdown(rows_html, unsafe_allow_html=True)



# ── ④ 최근 생산실적 (고정 높이 + 스크롤, 네이티브 container) ─────
with st.container(border=True):
    st.markdown("##### 최근 생산실적")
    if recent_df.empty:
        st.caption("생산실적이 없습니다.")
    else:
        with st.container(height=260):
            rows_html = ""
            for row in recent_df.itertuples():
                completed_at = row.end_time if row.end_time else row.start_time
                rows_html += (
                    '<div style="display:flex;padding:5px 0;'
                    'border-bottom:0.5px solid #EDEBE3;font-size:14px;">'
                    f'<div style="flex:3;">{row.lot_no}</div>'
                    f'<div style="flex:2;color:#5F5E5A;">{row.process_name} 완료</div>'
                    f'<div style="flex:2;color:#888780;text-align:right;">{completed_at}</div>'
                    "</div>"
                )
            st.markdown(rows_html, unsafe_allow_html=True)