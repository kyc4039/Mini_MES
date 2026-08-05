from datetime import datetime

import pandas as pd

from src.db import get_connection


def fetch_dataframe(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_connection() as connection:
        return pd.read_sql_query(sql, connection, params=params)


# ── 원재료 입고 ──────────────────────────────────────────────
def raw_items():
    with get_connection() as connection:
        return connection.execute(
            "SELECT item_id, item_code, item_name, unit FROM item WHERE item_type = 'RAW' ORDER BY item_code"
        ).fetchall()


def raw_lots(keyword: str = ""):
    where = "l.lot_type = 'RAW'"
    params: list[str] = []
    if keyword:
        where += " AND (l.lot_no LIKE ? OR i.item_name LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    return fetch_dataframe(
        f"""
        SELECT
            l.lot_id,
            l.lot_no,
            i.item_name,
            i.unit,
            l.qty AS received_qty,
            COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id), 0) AS used_qty,
            l.qty - COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id), 0) AS remaining_qty,
            l.status,
            l.created_at
        FROM lot AS l
        JOIN item AS i ON l.item_id = i.item_id
        WHERE {where}
        ORDER BY l.created_at DESC
        """,
        tuple(params),
    )


def raw_stock_by_item():
    """원자재 품목별로 모든 LOT의 잔여수량을 합산."""
    return fetch_dataframe(
        """
        SELECT
            i.item_name,
            i.unit,
            SUM(sub.qty) AS received_qty,
            SUM(sub.remaining_qty) AS remaining_qty
        FROM (
            SELECT
                l.item_id,
                l.qty,
                l.qty - COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id), 0) AS remaining_qty
            FROM lot AS l
            WHERE l.lot_type = 'RAW'
        ) AS sub
        JOIN item AS i ON i.item_id = sub.item_id
        GROUP BY i.item_id
        ORDER BY i.item_code
        """
    )


# ── 공정 실적 등록 공통 (극판/조립/화성) ────────────────────────
def processes_by_group(process_group: str):
    with get_connection() as connection:
        return connection.execute(
            "SELECT process_id, process_code, process_name, seq_no FROM process WHERE process_group = ? ORDER BY seq_no",
            (process_group,),
        ).fetchall()


def equipment_by_process(process_id: int):
    with get_connection() as connection:
        return connection.execute(
            "SELECT equipment_id, equipment_code, equipment_name, status FROM equipment WHERE process_id = ? ORDER BY equipment_id",
            (process_id,),
        ).fetchall()


def workers_for_select():
    with get_connection() as connection:
        return connection.execute(
            "SELECT worker_id, worker_code, worker_name FROM worker ORDER BY worker_id"
        ).fetchall()


def work_orders_in_progress():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT wo.work_order_id, wo.work_order_no, i.item_name
            FROM work_order AS wo
            JOIN item AS i ON wo.item_id = i.item_id
            WHERE wo.status = 'IN_PROGRESS'
            ORDER BY wo.work_order_id
            """
        ).fetchall()


def wip_items():
    with get_connection() as connection:
        return connection.execute(
            "SELECT item_id, item_code, item_name, unit FROM item WHERE item_type = 'WIP' ORDER BY item_code"
        ).fetchall()


def assembly_output_items():
    """조립공정 결과 품목 선택용 — WIP(중간 조립물)과 CELL(스태킹 이후 완제품 셀)을 모두 포함."""
    with get_connection() as connection:
        return connection.execute(
            "SELECT item_id, item_code, item_name, item_type, unit FROM item WHERE item_type IN ('WIP', 'CELL') ORDER BY item_type, item_code"
        ).fetchall()


def available_lots(item_type_in: tuple = ("RAW", "WIP")):
    placeholders = ",".join("?" for _ in item_type_in)
    return fetch_dataframe(
        f"""
        SELECT * FROM (
            SELECT
                l.lot_id,
                l.lot_no,
                i.item_code,
                i.item_name,
                i.unit,
                COALESCE(p.process_name, '입고') AS from_process,
                p.process_code AS from_process_code,
                l.qty - COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id), 0) AS remaining_qty
            FROM lot AS l
            JOIN item AS i ON l.item_id = i.item_id
            LEFT JOIN process AS p ON l.process_id = p.process_id
            WHERE i.item_type IN ({placeholders})
        )
        WHERE remaining_qty > 0
        ORDER BY lot_id
        """,
        item_type_in,
    )


def process_production_history(process_id: int, limit: int = 15):
    return fetch_dataframe(
        """
        SELECT
            l.lot_no AS 결과LOT,
            pr.qty,
            e.equipment_name,
            w.worker_name,
            pr.start_time,
            pr.end_time
        FROM production_result AS pr
        JOIN lot AS l ON pr.output_lot_id = l.lot_id
        JOIN equipment AS e ON pr.equipment_id = e.equipment_id
        JOIN worker AS w ON pr.worker_id = w.worker_id
        WHERE pr.process_id = ?
        ORDER BY pr.start_time DESC
        LIMIT ?
        """,
        (process_id, limit),
    )


# ── 대시보드(app.py) 집계 ────────────────────────────────────
def inspection_specs_by_process(process_id: int):
    with get_connection() as connection:
        return connection.execute(
            "SELECT spec_id, spec_name, lower_limit, upper_limit, unit FROM inspection_spec WHERE process_id = ? ORDER BY spec_id",
            (process_id,),
        ).fetchall()


def lots_by_process(process_id: int, limit: int = 10):
    with get_connection() as connection:
        return connection.execute(
            "SELECT lot_id, lot_no FROM lot WHERE process_id = ? ORDER BY lot_id DESC LIMIT ?",
            (process_id, limit),
        ).fetchall()


def inspection_results_for_lot(lot_id: int):
    return fetch_dataframe(
        """
        SELECT s.spec_name, ir.measured_value, s.lower_limit, s.upper_limit, s.unit, ir.judge, ir.inspected_at
        FROM inspection_result AS ir
        JOIN inspection_spec AS s ON ir.spec_id = s.spec_id
        WHERE ir.lot_id = ?
        ORDER BY ir.inspected_at DESC
        """,
        (lot_id,),
    )


def lot_search(keyword: str = "", limit: int = 30):
    where = "1 = 1"
    params: list[str] = []
    if keyword:
        where += " AND (l.lot_no LIKE ? OR i.item_name LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    return fetch_dataframe(
        f"""
        SELECT l.lot_id, l.lot_no, i.item_name, l.lot_type, l.qty, l.status, l.created_at
        FROM lot AS l
        JOIN item AS i ON l.item_id = i.item_id
        WHERE {where}
        ORDER BY l.lot_id DESC
        LIMIT ?
        """,
        (*params, limit),
    )


def trace_upstream(lot_id: int):
    """역방향 추적: 이 LOT이 어떤 LOT(들)으로부터 만들어졌는지, 원자재까지 거슬러 올라간다."""
    return fetch_dataframe(
        """
        WITH RECURSIVE trace AS (
            SELECT parent_lot_id, child_lot_id, qty_used
            FROM lot_genealogy WHERE child_lot_id = ?
            UNION ALL
            SELECT g.parent_lot_id, g.child_lot_id, g.qty_used
            FROM lot_genealogy AS g
            JOIN trace AS t ON g.child_lot_id = t.parent_lot_id
        )
        SELECT
            l.lot_no,
            i.item_name,
            l.lot_type,
            trace.qty_used,
            p.process_name,
            pr.start_time
        FROM trace
        JOIN lot AS l ON l.lot_id = trace.parent_lot_id
        JOIN item AS i ON l.item_id = i.item_id
        LEFT JOIN production_result AS pr ON pr.output_lot_id = l.lot_id
        LEFT JOIN process AS p ON pr.process_id = p.process_id
        ORDER BY pr.start_time
        """,
        (lot_id,),
    )


def trace_downstream(lot_id: int):
    """정방향 추적: 이 LOT이 이후 어떤 LOT(들)으로 이어졌는지, 완제품까지 따라 내려간다."""
    return fetch_dataframe(
        """
        WITH RECURSIVE trace AS (
            SELECT parent_lot_id, child_lot_id, qty_used
            FROM lot_genealogy WHERE parent_lot_id = ?
            UNION ALL
            SELECT g.parent_lot_id, g.child_lot_id, g.qty_used
            FROM lot_genealogy AS g
            JOIN trace AS t ON g.parent_lot_id = t.child_lot_id
        )
        SELECT
            l.lot_no,
            i.item_name,
            l.lot_type,
            trace.qty_used,
            p.process_name,
            pr.start_time
        FROM trace
        JOIN lot AS l ON l.lot_id = trace.child_lot_id
        JOIN item AS i ON l.item_id = i.item_id
        LEFT JOIN production_result AS pr ON pr.output_lot_id = l.lot_id
        LEFT JOIN process AS p ON pr.process_id = p.process_id
        ORDER BY pr.start_time
        """,
        (lot_id,),
    )


def all_work_orders_detailed():
    """모든 작업지시(상태 무관)를 계획/실적 수량과 함께 반환. 작업지시 관리 페이지 목록용."""
    return fetch_dataframe(
        """
        SELECT
            wo.work_order_id,
            wo.work_order_no,
            i.item_name,
            wo.plan_qty,
            wo.status,
            COALESCE(SUM(CASE WHEN p.process_group = '화성' AND p.seq_no = (
                SELECT MAX(seq_no) FROM process WHERE process_group = '화성'
            ) THEN pr.qty END), 0) AS actual_qty
        FROM work_order AS wo
        JOIN item AS i ON wo.item_id = i.item_id
        LEFT JOIN production_result AS pr ON pr.work_order_id = wo.work_order_id
        LEFT JOIN process AS p ON pr.process_id = p.process_id
        GROUP BY wo.work_order_id
        ORDER BY wo.work_order_id DESC
        """
    )


def cell_items():
    """작업지시 대상 품목 선택용 — 완제품(CELL) 품목만."""
    with get_connection() as connection:
        return connection.execute(
            "SELECT item_id, item_code, item_name, unit FROM item WHERE item_type = 'CELL' ORDER BY item_code"
        ).fetchall()


def all_work_orders():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT wo.work_order_id, wo.work_order_no, i.item_name, wo.status
            FROM work_order AS wo
            JOIN item AS i ON wo.item_id = i.item_id
            ORDER BY wo.work_order_id DESC
            """
        ).fetchall()


def work_order_achievement(work_order_id: int):
    """선택한 작업지시의 계획 대비 실적(완성 셀 개수) 달성률."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                wo.plan_qty,
                COALESCE(SUM(CASE WHEN p.process_group = '화성' AND p.seq_no = (
                    SELECT MAX(seq_no) FROM process WHERE process_group = '화성'
                ) THEN pr.qty END), 0) AS actual_qty
            FROM work_order AS wo
            LEFT JOIN production_result AS pr ON pr.work_order_id = wo.work_order_id
            LEFT JOIN process AS p ON pr.process_id = p.process_id
            WHERE wo.work_order_id = ?
            GROUP BY wo.work_order_id
            """,
            (work_order_id,),
        ).fetchone()

    if not row or not row[0]:
        return {"plan_qty": 0, "actual_qty": 0, "rate": 0.0}

    plan_qty, actual_qty = row
    rate = round(actual_qty / plan_qty * 100, 1) if plan_qty else 0.0
    return {"plan_qty": plan_qty, "actual_qty": actual_qty, "rate": rate}


def work_order_pipeline(work_order_id: int, now_str: str | None = None):
    """작업지시가 12개 공정 중 어디까지 왔는지: 완료/진행중/대기로 분류.
    '전체 작업지시에서 가장 최근에 시작된 실적'이 몇 번째 공정인지 먼저 찾고,
    그보다 앞 단계는 완료, 그 공정 자체는 시간 비교, 뒷 단계는 대기로 판정한다."""
    if now_str is None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    with get_connection() as connection:
        processes = connection.execute(
            "SELECT process_id, process_name, process_group, seq_no FROM process ORDER BY seq_no"
        ).fetchall()

        latest_overall = connection.execute(
            """
            SELECT pr.process_id, pr.start_time, pr.end_time, p.seq_no
            FROM production_result AS pr
            JOIN process AS p ON pr.process_id = p.process_id
            WHERE pr.work_order_id = ?
            ORDER BY pr.start_time DESC
            LIMIT 1
            """,
            (work_order_id,),
        ).fetchone()

    if latest_overall is None:
        # 아직 아무 실적도 없으면 전부 대기
        return [
            {
                "process_id": process_id,
                "process_name": process_name,
                "process_group": process_group,
                "seq_no": seq_no,
                "status": "대기",
            }
            for process_id, process_name, process_group, seq_no in processes
        ]

    _, current_start, current_end, current_seq = latest_overall

    result = []
    for process_id, process_name, process_group, seq_no in processes:
        if seq_no < current_seq:
            status = "완료"
        elif seq_no > current_seq:
            status = "대기"
        else:
            if now_str < current_start:
                status = "대기"
            elif current_end and now_str > current_end:
                status = "완료"
            else:
                status = "진행중"
        result.append(
            {
                "process_id": process_id,
                "process_name": process_name,
                "process_group": process_group,
                "seq_no": seq_no,
                "status": status,
            }
        )
    return result


def equipment_exceptions():
    """RUN이 아닌(정지/점검중) 설비만 골라서 보여줌."""
    return fetch_dataframe(
        """
        SELECT equipment_name, status
        FROM equipment
        WHERE status != 'RUN'
        ORDER BY equipment_id
        """
    )


def production_group_stats(process_group: str):
    """공정 그룹(전극/조립/화성) 전체의 실적 건수와 최근 실적 시각."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*), MAX(pr.start_time)
            FROM production_result AS pr
            JOIN process AS p ON pr.process_id = p.process_id
            WHERE p.process_group = ?
            """,
            (process_group,),
        ).fetchone()
    return {"count": row[0], "latest": row[1]}


def today_group_lot_count(process_group: str, today: str):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM production_result AS pr
            JOIN process AS p ON pr.process_id = p.process_id
            WHERE p.process_group = ? AND pr.start_time LIKE ?
            """,
            (process_group, f"{today}%"),
        ).fetchone()
    return row[0]


def count_lots_by_prefix(prefix: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM lot WHERE lot_no LIKE ?", (f"{prefix}%",)
        ).fetchone()
    return row[0]


def lot_numbers_for_item(item_id: int):
    with get_connection() as connection:
        return [
            r[0]
            for r in connection.execute(
                "SELECT lot_no FROM lot WHERE item_id = ?", (item_id,)
            ).fetchall()
        ]


def equipment_status_summary():
    df = fetch_dataframe(
        """
        SELECT status, COUNT(*) AS equipment_count
        FROM equipment
        GROUP BY status
        """
    )
    total = df["equipment_count"].sum() if not df.empty else 0
    counts = dict(zip(df["status"], df["equipment_count"])) if not df.empty else {}
    run = counts.get("RUN", 0)
    rate = round(run / total * 100, 1) if total else 0.0
    return {"total": int(total), "run": run, "stop": counts.get("STOP", 0), "maint": counts.get("MAINT", 0), "rate": rate}


def equipment_list():
    return fetch_dataframe(
        """
        SELECT equipment_code, equipment_name, status
        FROM equipment
        ORDER BY equipment_id
        """
    )


def inspection_spec_list():
    return fetch_dataframe(
        """
        SELECT DISTINCT spec_name, unit
        FROM inspection_spec
        ORDER BY spec_name
        """
    )


def work_order_progress():
    return fetch_dataframe(
        """
        SELECT
            wo.work_order_id,
            wo.work_order_no,
            i.item_name,
            wo.plan_qty,
            COALESCE(SUM(CASE WHEN p.process_group = '화성' AND p.seq_no = (
                SELECT MAX(seq_no) FROM process WHERE process_group = '화성'
            ) THEN pr.qty END), 0) AS actual_qty
        FROM work_order AS wo
        JOIN item AS i ON wo.item_id = i.item_id
        LEFT JOIN production_result AS pr ON pr.work_order_id = wo.work_order_id
        LEFT JOIN process AS p ON pr.process_id = p.process_id
        WHERE wo.status = 'IN_PROGRESS'
        GROUP BY wo.work_order_id
        """
    )


def inspection_pass_rate():
    df = fetch_dataframe(
        """
        SELECT judge, COUNT(*) AS cnt
        FROM inspection_result
        GROUP BY judge
        """
    )
    total = df["cnt"].sum() if not df.empty else 0
    counts = dict(zip(df["judge"], df["cnt"])) if not df.empty else {}
    passed = counts.get("PASS", 0)
    rate = round(passed / total * 100, 1) if total else 0.0
    return {"total": int(total), "pass": passed, "fail": counts.get("FAIL", 0), "rate": rate}


def defect_by_process():
    return fetch_dataframe(
        """
        SELECT
            p.process_name,
            SUM(CASE WHEN ir.judge = 'FAIL' THEN 1 ELSE 0 END) AS fail_count,
            COUNT(*) AS total_count
        FROM inspection_result AS ir
        JOIN inspection_spec AS s ON ir.spec_id = s.spec_id
        JOIN process AS p ON s.process_id = p.process_id
        GROUP BY p.process_name
        HAVING fail_count > 0
        ORDER BY (fail_count * 1.0 / total_count) DESC
        """
    )


def recent_production(limit: int = 10):
    return fetch_dataframe(
        """
        SELECT
            l.lot_no,
            p.process_name,
            e.equipment_name,
            w.worker_name,
            pr.start_time,
            pr.end_time,
            pr.qty
        FROM production_result AS pr
        JOIN lot AS l ON pr.output_lot_id = l.lot_id
        JOIN process AS p ON pr.process_id = p.process_id
        JOIN equipment AS e ON pr.equipment_id = e.equipment_id
        JOIN worker AS w ON pr.worker_id = w.worker_id
        ORDER BY pr.start_time DESC
        LIMIT ?
        """,
        (limit,),
    )