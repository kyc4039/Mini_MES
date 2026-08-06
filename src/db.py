import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "sql" / "mes_final.db"
DUMP_PATH = Path(__file__).parent.parent / "sql" / "dump.sql"


def _ensure_db():
    """DB 파일이 없으면 dump.sql로 자동 생성 (Streamlit Cloud 배포용)"""
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        with open(DUMP_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()


def get_connection():
    _ensure_db()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection