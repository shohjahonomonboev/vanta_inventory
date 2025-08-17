import os, time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# --- Normalize DB URL (fix old postgres:// scheme) ---
def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url

# Detect DB URL
_raw_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DB_URL")
DATABASE_URL = normalize_url(_raw_url)

if not DATABASE_URL:
    sqlite_path = Path(__file__).with_name("local.db")
    DATABASE_URL = f"sqlite:///{sqlite_path.as_posix()}"
    print(f"DB: No DATABASE_URL found → using SQLite at {sqlite_path}")
else:
    if DATABASE_URL.startswith("postgresql"):
        safe_url = DATABASE_URL.split("@")[-1]
        print(f"DB: Using Postgres at {safe_url} (password hidden)")
    else:
        print(f"DB: Using custom DB URL ({DATABASE_URL.split('://',1)[0]})")

# --- Engine creation ---
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
# ---- Schema helpers ----
def _column_exists(conn, table: str, col: str) -> bool:
    if DATABASE_URL.startswith("postgresql"):
        row = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
            LIMIT 1
        """), {"t": table, "c": col}).fetchone()
        return bool(row)
    else:
        # SQLite
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        return any(r[1] == col for r in rows)

def _ensure_column(conn, table: str, col: str, col_type_sql: str):
    if not _column_exists(conn, table, col):
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {col_type_sql}")

def _ensure_index(conn, index_name: str, table: str, column: str, unique: bool = False):
    uniq = "UNIQUE " if unique else ""
    conn.exec_driver_sql(f"CREATE {uniq}INDEX IF NOT EXISTS {index_name} ON {table}({column});")



# --- Helpers ---
def is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")

def _dedupe_inventory_names(conn):
    """Merge duplicate inventory names into one row each."""
    dups = conn.execute(text("""
        SELECT name FROM inventory
        GROUP BY name
        HAVING COUNT(*) > 1
    """)).fetchall()
    if not dups:
        return 0

    changed = 0
    for (dup_name,) in dups:
        rows = conn.execute(text("""
            SELECT id, buying_price, selling_price, quantity, profit, currency, created_at
            FROM inventory
            WHERE name = :n
            ORDER BY created_at DESC NULLS LAST, id DESC
        """), {"n": dup_name}).fetchall()
        if not rows:
            continue
        keep_id = rows[0][0]

        total_qty = sum(int(r[3] or 0) for r in rows)
        total_profit = sum(float(r[4] or 0.0) for r in rows)

        conn.execute(text("""
            UPDATE inventory
            SET quantity = :q, profit = :p
            WHERE id = :id
        """), {"q": total_qty, "p": total_profit, "id": keep_id})

        conn.execute(text("""
            DELETE FROM inventory
            WHERE name = :n AND id <> :id
        """), {"n": dup_name, "id": keep_id})

        changed += 1
    return changed

# --- Schema ---
_schema_checked = False

def ensure_schema():
    global _schema_checked
    if _schema_checked:
        return

    is_pg = DATABASE_URL.startswith("postgresql")
    stmts = []

    # Enable foreign keys on SQLite
    if not is_pg:
        stmts.append("PRAGMA foreign_keys = ON;")

    # ---- Base tables (create-if-missing; do not alter existing columns here) ----
    if not is_pg:
        stmts += [
            """CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                -- rolling columns added later via _ensure_column
                buying_price REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit REAL NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );""",
            """CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                sell_price REAL NOT NULL,
                profit REAL NOT NULL,
                sold_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES inventory(id) ON DELETE CASCADE
            );""",
            """CREATE TABLE IF NOT EXISTS currency (
                code TEXT PRIMARY KEY,
                symbol TEXT,
                rate REAL
            );""",
        ]
    else:
        stmts += [
            """CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                -- rolling columns added later via _ensure_column
                buying_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                selling_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit NUMERIC(14,2) NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );""",
            """CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
                qty INTEGER NOT NULL,
                sell_price NUMERIC(14,2) NOT NULL,
                profit NUMERIC(14,2) NOT NULL,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );""",
            """CREATE TABLE IF NOT EXISTS currency (
                code TEXT PRIMARY KEY,
                symbol TEXT,
                rate NUMERIC(14,6)
            );""",
        ]

    # ---- Apply schema + rolling upgrades ----
    with engine.begin() as conn:
        for s in stmts:
            conn.exec_driver_sql(s)

        # Rolling column upgrades (safe on both SQLite & Postgres)
        _ensure_column(conn, "inventory", "category", "TEXT")
        _ensure_column(conn, "inventory", "updated_at", "TIMESTAMP")

        # One-time backfill for updated_at (no-op if already set)
        conn.exec_driver_sql("""
            UPDATE inventory
               SET updated_at = CURRENT_TIMESTAMP
             WHERE updated_at IS NULL
        """)

        # Drop legacy non-unique index if it exists
        try:
            conn.exec_driver_sql("DROP INDEX IF EXISTS idx_inventory_name;")
        except Exception:
            pass

        # Deduplicate names before enforcing uniqueness
        deduped = _dedupe_inventory_names(conn)
        if deduped:
            print(f"Schema: deduped {deduped} duplicate inventory name(s).")

        # Indexes (idempotent)
        _ensure_index(conn, "idx_inventory_name_unique", "inventory", "name", unique=True)
        _ensure_index(conn, "idx_inventory_cat",  "inventory", "category")
        _ensure_index(conn, "idx_inventory_qty",  "inventory", "quantity")
        _ensure_index(conn, "idx_sales_item",     "sales",     "item_id")
        _ensure_index(conn, "idx_sales_date",     "sales",     "sold_at")

    _schema_checked = True



# --- DB helpers ---
def db_all(sql, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [tuple(row) for row in result]

def db_one(sql, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        row = result.fetchone()
        return tuple(row) if row else None

def db_exec(sql, params=None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
