import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Problem(Exception):
    def __init__(self, message, status=422):
        self.message, self.status = message, status
        super().__init__(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(Path(__file__).with_name("schema.sql").read_text())


@contextmanager
def connect(path, write=False):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(conn, who, kind, details):
    conn.execute(
        "INSERT INTO events(tenant,actor,at,kind,details) VALUES(?,?,?,?,?)",
        (who.tenant, who.user, now(), kind, packed(details)),
    )


def current(conn, tenant):
    row = conn.execute(
        "SELECT d.id,d.as_of FROM portfolios p JOIN datasets d ON d.id=p.dataset "
        "WHERE p.tenant=? AND d.tenant=?",
        (tenant, tenant),
    ).fetchone()
    if not row:
        raise Problem("No accepted portfolio snapshot. Import and review a workbook first.", 409)
    return dict(row)
