import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "sql" / "mes_final.db"
DUMP_PATH = Path(__file__).resolve().parent.parent / "sql" / "dump.sql"


def _ensure_db():
    """DB 파일이 없으면 dump.sql로 자동 생성 (Streamlit Cloud처럼 .db 파일이 없는 배포 환경 대응)"""
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        with open(DUMP_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()


def get_connection():
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn