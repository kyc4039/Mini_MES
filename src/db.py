import sqlite3
import tempfile
from pathlib import Path

DUMP_PATH = Path(__file__).resolve().parent.parent / "sql" / "dump.sql"
_PRIMARY_DB_PATH = Path(__file__).resolve().parent.parent / "sql" / "mes_final.db"
_FALLBACK_DB_PATH = Path(tempfile.gettempdir()) / "mes_final.db"


def _build_db(path: Path):
    conn = sqlite3.connect(path)
    with open(DUMP_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def _has_tables(path: Path) -> bool:
    """파일이 존재해도 테이블이 하나도 없으면(빈 DB) False."""
    try:
        conn = sqlite3.connect(path)
        row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()
        conn.close()
        return row[0] > 0
    except sqlite3.OperationalError:
        return False


def _resolve_db_path() -> Path:
    if _PRIMARY_DB_PATH.exists() and _has_tables(_PRIMARY_DB_PATH):
        return _PRIMARY_DB_PATH
    try:
        _PRIMARY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _build_db(_PRIMARY_DB_PATH)
        return _PRIMARY_DB_PATH
    except (OSError, sqlite3.OperationalError):
        if not _FALLBACK_DB_PATH.exists() or not _has_tables(_FALLBACK_DB_PATH):
            _build_db(_FALLBACK_DB_PATH)
        return _FALLBACK_DB_PATH


DB_PATH = _resolve_db_path()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn