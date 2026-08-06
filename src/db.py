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


def _resolve_db_path() -> Path:
    if _PRIMARY_DB_PATH.exists():
        return _PRIMARY_DB_PATH
    try:
        _PRIMARY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _build_db(_PRIMARY_DB_PATH)
        return _PRIMARY_DB_PATH
    except (OSError, sqlite3.OperationalError):
        # sql/ 폴더가 읽기전용인 배포 환경 -> 임시 폴더에 생성
        if not _FALLBACK_DB_PATH.exists():
            _build_db(_FALLBACK_DB_PATH)
        return _FALLBACK_DB_PATH


DB_PATH = _resolve_db_path()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn