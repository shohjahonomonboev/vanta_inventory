# database_sqlalchemy.py
import os, time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url

_raw_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DB_URL")
DATABASE_URL = normalize_url(_raw_url)

if not DATABASE_URL:
    sqlite_path = Path(__file__).with_name("local.db")
    DATABASE_URL = f"sqlite:///{sqlite_path.as_posix()}"
    print(f"DB: No DATABASE_URL found. Using SQLite at {sqlite_path}")
else:
    print("DB: Using Postgres from env (masked).")

def make_engine():
    last_err = None
    for attempt in range(6):
        try:
            kwargs = {"pool_pre_ping": True}

            if DATABASE_URL.startswith("postgresql"):
                kwargs.update(pool_recycle=1800, pool_size=5, max_overflow=10)
            elif DATABASE_URL.startswith("sqlite"):
                kwargs.update(connect_args={"check_same_thread": False})

            eng = create_engine(DATABASE_URL, **kwargs)

            # sanity ping
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"DB engine ready (attempt {attempt+1})")
            return eng
        except OperationalError as e:
            last_err = e
            wait = 2 ** attempt
            print(f"DB connect failed (attempt {attempt+1}), retrying in {wait}s...")
            time.sleep(wait)
    raise last_err

engine = make_engine()

def ensure_schema():
    is_pg = DATABASE_URL.startswith("postgresql")
    stmts = []

    if not is_pg:
        # SQLite: enable FKs
        stmts.append("PRAGMA foreign_keys = ON;")

    if not is_pg:
        # ---------- SQLite DDL ----------
        stmts += [
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                buying_price REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit REAL NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                sell_price REAL NOT NULL,
                profit REAL NOT NULL,
                sold_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES inventory(id) ON DELETE CASCADE
            );
            """,
        ]
    else:
        # ---------- Postgres DDL ----------
        stmts += [
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                buying_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                selling_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit NUMERIC(14,2) NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
                qty INTEGER NOT NULL,
                sell_price NUMERIC(14,2) NOT NULL,
                profit NUMERIC(14,2) NOT NULL,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
        ]

    # common indexes
    stmts += [
        "CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory(name);",
        "CREATE INDEX IF NOT EXISTS idx_inventory_qty  ON inventory(quantity);",
        "CREATE INDEX IF NOT EXISTS idx_sales_item     ON sales(item_id);",
        "CREATE INDEX IF NOT EXISTS idx_sales_date     ON sales(sold_at);",
    ]

    with engine.begin() as conn:
        for s in stmts:
            conn.exec_driver_sql(s)


def db_all(sql, params=None):
    """Return all rows for a query."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [tuple(row) for row in result]

def db_one(sql, params=None):
    """Return a single row or None."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        row = result.fetchone()
        return tuple(row) if row else None

def db_exec(sql, params=None):
    """Execute a query (INSERT, UPDATE, DELETE)."""
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
