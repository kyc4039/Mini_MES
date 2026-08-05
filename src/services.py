import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src.db import get_connection


# -- 작업지시 등록 --
@dataclass
class WorkOrderRegistration:
    work_order_no: str
    item_id: int
    plan_qty: float
    status: str = "WAITING"


def validate_work_order(data: WorkOrderRegistration) -> list[str]:
    errors: list[str] = []

    if not data.work_order_no.strip():
        errors.append("작업지시 번호를 입력하세요.")
    if data.plan_qty <= 0:
        errors.append("계획수량은 0보다 커야 합니다.")
    if data.status not in ("WAITING", "IN_PROGRESS", "COMPLETED", "CANCELED"):
        errors.append(f"status 값이 올바르지 않습니다: {data.status}")

    return errors


def register_work_order(data: WorkOrderRegistration) -> dict:
    errors = validate_work_order(data)
    if errors:
        raise ValueError("\n".join(errors))

    try:
        with get_connection() as connection:
            cursor = connection.cursor()

            next_id = cursor.execute(
                "SELECT COALESCE(MAX(work_order_id), 0) + 1 FROM work_order"
            ).fetchone()[0]

            cursor.execute(
                """
                INSERT INTO work_order (work_order_id, work_order_no, item_id, plan_qty, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (next_id, data.work_order_no.strip(), data.item_id, data.plan_qty, data.status),
            )

            connection.commit()

            return {"work_order_id": next_id, "work_order_no": data.work_order_no.strip()}
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "작업지시 번호가 이미 존재하거나 데이터베이스 제약 조건을 만족하지 못했습니다."
        ) from exc


# -- 원재료 입고 등록 --
@dataclass
class RawLotRegistration:
    lot_no: str
    item_id: int
    qty: float
    created_at: str | None = None # 지정 안하면 등록 시각(지금)을 사용


def validate_raw_lot(data: RawLotRegistration) -> list[str]:
    errors: list[str] = []

    if not data.lot_no.strip():
        errors.append("LOT 번호를 입력하세요.")
    if data.qty <= 0:
        errors.append("입고수량은 0보다 커야 합니다.")

    return errors


def register_raw_lot(data: RawLotRegistration) -> dict:
    errors = validate_raw_lot(data)
    if errors:
        raise ValueError("\n".join(errors))

    try:
        with get_connection() as connection:
            cursor = connection.cursor()

            next_lot_id = cursor.execute(
                "SELECT COALESCE(MAX(lot_id), 0) + 1 FROM lot"
            ).fetchone()[0]

            created_at = data.created_at or datetime.now().strftime("%Y-%m-%d %H:%M")

            cursor.execute(
                """
                INSERT INTO lot (lot_id, lot_no, item_id, lot_type, qty, process_id, created_at)
                VALUES (?, ?, ?, 'RAW', ?, NULL, ?)
                """,
                (next_lot_id, data.lot_no.strip(), data.item_id, data.qty, created_at),
            )

            connection.commit()

            return {"lot_id": next_lot_id, "lot_no": data.lot_no.strip(), "qty": data.qty}
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "LOT 번호가 이미 존재하거나 데이터베이스 제약 조건을 만족하지 못했습니다."
        ) from exc



# -- 검사 결과 등록 --
@dataclass
class InspectionEntry:
    spec_id: int
    measured_value: float


def register_inspection_results(lot_id: int, entries: list, inspected_at: str) -> list:
    """
    측정값을 입력받아 inspection_spec의 lower_limit/upper_limit과 비교해
    PASS/FAIL을 자동 판정하고 inspection_result에 저장한다.
    """
    if not entries:
        raise ValueError("입력된 검사항목이 없습니다.")
    if not inspected_at.strip():
        raise ValueError("검사 시각을 입력하세요.")

    results = []
    try:
        with get_connection() as connection:
            cursor = connection.cursor()

            next_id = cursor.execute(
                "SELECT COALESCE(MAX(inspection_result_id), 0) + 1 FROM inspection_result"
            ).fetchone()[0]

            for entry in entries:
                spec = cursor.execute(
                    "SELECT lower_limit, upper_limit, spec_name FROM inspection_spec WHERE spec_id = ?",
                    (entry.spec_id,),
                ).fetchone()
                if spec is None:
                    raise ValueError(f"spec_id {entry.spec_id}에 해당하는 검사기준이 없습니다.")
                lower_limit, upper_limit, spec_name = spec

                judge = "PASS"
                if lower_limit is not None and entry.measured_value < lower_limit:
                    judge = "FAIL"
                if upper_limit is not None and entry.measured_value > upper_limit:
                    judge = "FAIL"

                cursor.execute(
                    """
                    INSERT INTO inspection_result (inspection_result_id, lot_id, spec_id, measured_value, judge, inspected_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (next_id, lot_id, entry.spec_id, entry.measured_value, judge, inspected_at.strip()),
                )
                results.append({"spec_name": spec_name, "measured_value": entry.measured_value, "judge": judge})
                next_id += 1

            connection.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("검사결과 저장 중 데이터베이스 제약조건을 만족하지 못했습니다.") from exc

    return results



# -- 공정 생산실적 등록 --
@dataclass
class InputLotUsage:
    lot_id: int
    qty_used: float


@dataclass
class ProcessProductionRegistration:
    work_order_id: int
    process_id: int
    equipment_id: int
    worker_id: int
    output_item_id: int
    output_lot_no: str
    output_qty: float
    start_time: str
    end_time: str
    input_lots: list #list[InputLotUsage]


def validate_process_production(data: ProcessProductionRegistration) -> list[str]:
    errors: list[str] = []

    if not data.output_lot_no.strip():
        errors.append("결과 LOT 번호를 입력하세요.")
    if data.output_qty <= 0:
        errors.append("결과수량은 0보다 커야 합니다.")
    if not data.start_time.strip():
        errors.append("시작시각을 입력하세요.")
    if not data.input_lots:
        errors.append("투입 LOT을 1개 이상 선택하세요.")
    for usage in data.input_lots:
        if usage.qty_used <= 0:
            errors.append(f"LOT ID {usage.lot_id}의 투입 수량은 0보다 커야 합니다.")

    return errors


def register_process_production(data: ProcessProductionRegistration) -> dict:
    """
    극판/조립/화성 공정 공통 등록 로직.
    한 번의 호출로 3가지 일이 하나의 트랜잭션에 묶여서 저장된다 :
    1) 결과물 LOT을 생성 (lot)
    2) 투입 LOT들과의 계보 기록 (lot_genealogy) - 몇 개를 투입하든 각각 한 행씩
    3) 생산실적 기록 (production_result)
    """
    errors = validate_process_production(data)
    if errors:
        raise ValueError("\n".join(errors))

    try:
        with get_connection() as connection:
            cursor = connection.cursor()

            # 0. 투입 LOT마다 실제 잔여수량을 넘겨서 쓰려는 건 아닌지 먼저 확인
            #    (여기서 걸리면 아래 INSERT들이 하나도 실행되기 전이라 안전함)
            for usage in data.input_lots:
                lot_row = cursor.execute(
                    """
                    SELECT l.lot_no,
                        l.qty - COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id), 0) AS remaining_qty
                    FROM lot AS l WHERE l.lot_id = ?
                    """,
                    (usage.lot_id,),
                ).fetchone()
                if lot_row is None:
                    raise ValueError(f"lot_id {usage.lot_id}에 해당하는 LOT을 찾을 수 없습니다.")
                lot_no, remaining_qty = lot_row
                if usage.qty_used > remaining_qty:
                    raise ValueError(
                        f"'{lot_no}'의 잔여수량({remaining_qty:g})보다 많은 양({usage.qty_used:g})을 투입할 수 없습니다."
                    )

            # 1. 결과 LOT(자식) 생성 - 결과 품목의 item_type을 그대로 lot_type으로 사용
            # (예: 스태킹 단계에서 CELL 품목을 고르면 lot_type도 자동으로 'CELL')
            output_item_type = cursor.execute(
                "SELECT item_type FROM item WHERE item_id = ?", (data.output_item_id,)
            ).fetchone()
            if output_item_type is None:
                raise ValueError(f"item_id {data.output_item_id}에 해당하는 품목이 없습니다.")
            output_item_type = output_item_type[0]

            next_lot_id = cursor.execute(
                "SELECT COALESCE(MAX(lot_id), 0) + 1 FROM lot"
            ).fetchone()[0]
            cursor.execute(
                """
                INSERT INTO lot (lot_id, lot_no, item_id, lot_type, qty, process_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'COMPLETED', ?)
                """,
                (next_lot_id, data.output_lot_no.strip(), data.output_item_id, output_item_type, data.output_qty, data.process_id, data.start_time.strip()),
            )

            # 2. 계보 기록 - 투입 LOT(부모)마다 한 행씩
            next_genealogy_id = cursor.execute(
                "SELECT COALESCE(MAX(genealogy_id), 0) + 1 FROM lot_genealogy"
            ).fetchone()[0]
            for i, usage in enumerate(data.input_lots):
                cursor.execute(
                    """
                    INSERT INTO lot_genealogy (genealogy_id, parent_lot_id, child_lot_id, qty_used)
                    VALUES (?, ?, ?, ?)
                    """,
                    (next_genealogy_id + i, usage.lot_id, next_lot_id, usage.qty_used),
                )

            # 3. 생산실적 기록
            next_production_result_id = cursor.execute(
                "SELECT COALESCE(MAX(production_result_id), 0) + 1 FROM production_result"
            ).fetchone()[0]
            cursor.execute(
                """
                INSERT INTO production_result (production_result_id, work_order_id, process_id, equipment_id, worker_id, output_lot_id, start_time, end_time, qty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    next_production_result_id,
                    data.work_order_id,
                    data.process_id,
                    data.equipment_id,
                    data.worker_id,
                    next_lot_id,
                    data.start_time.strip(),
                    data.end_time.strip() or None,
                    data.output_qty,
                ),
            )

            # 4. 투입 LOT 잔여수량이 0이 되면 상태를 CONSUMED로 갱신
            for usage in data.input_lots:
                remaining = cursor.execute(
                    """
                    SELECT l.qty - COALESCE((SELECT SUM(qty_used) FROM lot_genealogy WHERE parent_lot_id = l.lot_id),0)
                    FROM lot AS l WHERE l.lot_id = ?
                    """,
                    (usage.lot_id,),
                ).fetchone()[0]
                if remaining is not None and remaining <= 0:
                    cursor.execute(
                        "UPDATE lot SET status = 'CONSUMED' WHERE lot_id = ?", (usage.lot_id,)
                    )

            connection.commit()

            return {
                "output_lot_id": next_lot_id,
                "output_lot_no": data.output_lot_no.strip(),
                "production_result_id": next_production_result_id,
            }
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            "LOT 번호가 이미 존재하거나 데이터베이스 제약조건을 만족하지 못했습니다."
        ) from exc