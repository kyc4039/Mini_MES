"""공정별 표준 레시피와 관련 계산 규칙 — 극판/조립/화성 페이지가 공통으로 사용.

process_code는 스키마 전체(전극·조립·화성)에서 유일하므로, 딕셔너리 하나로
12개 공정을 전부 관리한다. 이전에는 이 내용이 각 페이지 파일에 거의 똑같이
복사되어 있었는데, 여기 하나로 모아서 규칙을 고칠 때 한 곳만 고치면 되게 했다.
"""

import re
from datetime import datetime

from src import queries


# ── 공정별 표준 레시피 ──────────────────────────────────────────
# input_prefixes: 투입 가능한 품목 카테고리(접두사)
# output_prefix: 결과 품목 카테고리
# predecessors: 카테고리별로 "정확히 이 공정에서 나온 것만 인정"하는 제약.
#               원자재(RAW-*)처럼 제약이 필요 없는 카테고리는 predecessors에서 생략한다.
PROCESS_RECIPE = {
    # 전극
    "MIX-01": {"input_prefixes": ["RAW-CATH", "RAW-BINDER"], "output_prefix": "WIP-CATHSLURRY"},
    "COAT-01": {
        "input_prefixes": ["WIP-CATHSLURRY", "RAW-ALFOIL"],
        "output_prefix": "WIP-CATHCOATED",
        "predecessors": {"WIP-CATHSLURRY": "MIX-01"},
    },
    "PRESS-01": {
        "input_prefixes": ["WIP-CATHCOATED"],
        "output_prefix": "WIP-CATHPRESSED",
        "predecessors": {"WIP-CATHCOATED": "COAT-01"},
    },
    "SLIT-01": {
        "input_prefixes": ["WIP-CATHPRESSED"],
        "output_prefix": "WIP-CATHSHEET",
        "predecessors": {"WIP-CATHPRESSED": "PRESS-01"},
    },
    # 조립
    "NOTCH-01": {
        "input_prefixes": ["WIP-CATHSHEET"],
        "output_prefix": "WIP-CATHUNIT",
        "predecessors": {"WIP-CATHSHEET": "SLIT-01"},
    },
    "STACK-01": {
        "input_prefixes": ["WIP-CATHUNIT", "RAW-SEPARATOR"],
        "output_prefix": "CELL-EV",
        "predecessors": {"WIP-CATHUNIT": "NOTCH-01"},
    },
    "SEAL-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "STACK-01"},
    },
    "INJECT-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "SEAL-01"},
    },
    # 화성
    "AGE-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "INJECT-01"},
    },
    "FORM-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "AGE-01"},
    },
    "DEGAS-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "FORM-01"},
    },
    "FINAL-01": {
        "input_prefixes": ["CELL-EV"],
        "output_prefix": "CELL-EV",
        "predecessors": {"CELL-EV": "DEGAS-01"},
    },
}

# ── 공정별 결과수량 계산 규칙 ─────────────────────────────────
# "sum" = 투입량 합계, "fixed" = 고정값, "carry" = 주 투입물 수량 그대로
OUTPUT_QTY_RULE = {
    "MIX-01": ("sum", None),
    "COAT-01": ("fixed", 1),
    "PRESS-01": ("carry", None),
    "SLIT-01": ("fixed", 1),
    "NOTCH-01": ("carry", None),
    "STACK-01": ("fixed", 1),
    "SEAL-01": ("carry", None),
    "INJECT-01": ("carry", None),
    "AGE-01": ("carry", None),
    "FORM-01": ("carry", None),
    "DEGAS-01": ("carry", None),
    "FINAL-01": ("carry", None),
}

# ── 공정별 기본 예상 소요시간(분) — 지금까지 실적 기준 참고값 ────
DEFAULT_DURATION_MIN = {
    "MIX-01": 25,
    "COAT-01": 35,
    "PRESS-01": 25,
    "SLIT-01": 15,
    "NOTCH-01": 15,
    "STACK-01": 30,
    "SEAL-01": 20,
    "INJECT-01": 20,
    "AGE-01": 240,
    "FORM-01": 50,
    "DEGAS-01": 20,
    "FINAL-01": 15,
}

# ── CELL LOT번호 생성용 영문 태그 (노칭은 CELL을 만들지 않아서 제외) ──
PROCESS_ENGLISH_TAG = {
    "STACK-01": "STACK",
    "SEAL-01": "SEAL",
    "INJECT-01": "INJECT",
    "AGE-01": "AGE",
    "FORM-01": "FORM",
    "DEGAS-01": "DEGAS",
    "FINAL-01": "FINAL",
}


def matches_prefix(item_code: str, prefix: str) -> bool:
    """item_code가 prefix 계열인지 확인 (예: RAW-CATH-001, RAW-CATH-002 모두 'RAW-CATH'에 매칭)."""
    return item_code == prefix or item_code.startswith(f"{prefix}-")


def filter_input_lots(all_lots_df, recipe):
    """품목 카테고리 매칭 + (정의돼 있다면) 정확히 그 직전 공정에서 나온 LOT만 통과."""
    def check(row):
        for prefix in recipe["input_prefixes"]:
            if matches_prefix(row["item_code"], prefix):
                required_predecessor = recipe.get("predecessors", {}).get(prefix)
                if required_predecessor is None:
                    return True
                return row["from_process_code"] == required_predecessor
        return False
    return all_lots_df[all_lots_df.apply(check, axis=1)]


def missing_input_categories(all_lots_df, recipe) -> list[str]:
    """레시피가 요구하는 투입 품목 카테고리 중, 조건(직전공정 포함)을 만족하는 재고가
    아예 없는 것들을 찾아냄. UI에서 '이거 재고 없어요'라고 콕 짚어줄 때 쓴다."""
    missing = []
    for prefix in recipe["input_prefixes"]:
        matched = all_lots_df[all_lots_df["item_code"].apply(lambda c: matches_prefix(c, prefix))]
        required_predecessor = recipe.get("predecessors", {}).get(prefix)
        if required_predecessor is not None:
            matched = matched[matched["from_process_code"] == required_predecessor]
        if matched.empty:
            missing.append(prefix)
    return missing


def suggest_output_qty(process_code: str, input_qty_map: dict) -> float:
    """OUTPUT_QTY_RULE에 따라 결과수량 기본값을 계산 (수정 가능한 제안값일 뿐)."""
    rule = OUTPUT_QTY_RULE.get(process_code)
    if not rule:
        return 1.0
    rule_type, value = rule
    if rule_type == "sum":
        return sum(input_qty_map.values()) if input_qty_map else 0.0
    if rule_type == "fixed":
        return float(value)
    if rule_type == "carry":
        return next(iter(input_qty_map.values()), 1.0) if input_qty_map else 1.0
    return 1.0


def suggest_next_lot_no(existing_lot_nos: list[str], fallback: str) -> str:
    """기존 LOT번호 중 가장 큰 순번 다음 값을 제안. 패턴이 없으면 fallback 반환."""
    best_prefix, best_num, best_width = None, 0, 3
    for lot_no in existing_lot_nos:
        m = re.match(r"^(.*?)(\d+)$", lot_no)
        if m:
            prefix, num_str = m.group(1), m.group(2)
            num = int(num_str)
            if num >= best_num:
                best_prefix, best_num, best_width = prefix, num, len(num_str)
    if best_prefix is None:
        return fallback
    return f"{best_prefix}{best_num + 1:0{best_width}d}"


def suggest_cell_lot_no(reference_dt: datetime, process_tag: str) -> str:
    """CELL 품목 전용 — CELL-SN-{공정영문태그}-{YYMMDD}-{그 공정·그날 순번(01~)} 형식으로 생성."""
    date_str = reference_dt.strftime("%y%m%d")
    prefix = f"CELL-SN-{process_tag}-{date_str}-"
    count = queries.count_lots_by_prefix(prefix)
    return f"{prefix}{count + 1:02d}"