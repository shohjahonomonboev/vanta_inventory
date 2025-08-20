# database_sqlalchemy.py
import os, time
from pathlib import Path
from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import OperationalError

# --- URL normalization (fix old postgres:// scheme) --------------------------
def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    # Support old Heroku-style URLs
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url

# Detect DB URL (envs: DATABASE_URL, POSTGRES_URL, DB_URL) --------------------
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

def is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")

def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")

# --- Engine creation ---------------------------------------------------------
def make_engine():
    last_err = None
    for attempt in range(6):
        try:
            kwargs = {"pool_pre_ping": True}
            if is_postgres():
                # Reasonable production-ish pool defaults for PG
                kwargs.update(pool_recycle=1800, pool_size=5, max_overflow=10)
            elif is_sqlite():
                # Needed to allow access from multiple threads (Flask dev server etc.)
                kwargs.update(connect_args={"check_same_thread": False})

            eng = create_engine(DATABASE_URL, **kwargs)

            # SQLite: enforce foreign keys on every new DB-API connection
            if is_sqlite():
                @event.listens_for(eng, "connect")
                def _set_sqlite_pragma(dbapi_connection, connection_record):
                    cur = dbapi_connection.cursor()
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.close()

            # Sanity ping
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

# ---- Schema helpers ---------------------------------------------------------
def _column_exists(conn, table: str, col: str) -> bool:
    if is_postgres():
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

def _dedupe_inventory_names(conn):
    """
    Merge duplicate inventory names into a single row (keep newest),
    summing quantity and profit. Works on both Postgres & SQLite.
    """
    dups = conn.execute(text("""
        SELECT name FROM inventory
        GROUP BY name
        HAVING COUNT(*) > 1
    """)).fetchall()
    if not dups:
        return 0

    changed = 0
    for (dup_name,) in dups:
        if is_postgres():
            rows = conn.execute(text("""
                SELECT id, buying_price, selling_price, quantity, profit, currency, created_at
                FROM inventory
                WHERE name = :n
                ORDER BY created_at DESC NULLS LAST, id DESC
            """), {"n": dup_name}).fetchall()
        else:
            # SQLite has no NULLS LAST; emulate with (created_at IS NULL)
            rows = conn.execute(text("""
                SELECT id, buying_price, selling_price, quantity, profit, currency, created_at
                FROM inventory
                WHERE name = :n
                ORDER BY (created_at IS NULL), created_at DESC, id DESC
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

# --- Schema management -------------------------------------------------------
_schema_checked = False

def ensure_schema():
    global _schema_checked
    if _schema_checked:
        return

    stmts = []

    # Enable foreign keys for SQLite (also enforced on each connection via event)
    if not is_postgres():
        stmts.append("PRAGMA foreign_keys = ON;")

    # Base tables (create if missing). Keep types simple and portable.
    if not is_postgres():
        stmts += [
            """CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                buying_price REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit REAL NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                buying_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                selling_price NUMERIC(14,2) NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                profit NUMERIC(14,2) NOT NULL DEFAULT 0,
                currency TEXT DEFAULT 'UZS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    with engine.begin() as conn:
        # 1) Create base objects
        for s in stmts:
            conn.exec_driver_sql(s)

        # 2) Rolling column upgrades (add if missing)
        _ensure_column(conn, "inventory", "category",   "TEXT")
        _ensure_column(conn, "inventory", "created_at", "TIMESTAMP")
        _ensure_column(conn, "inventory", "updated_at", "TIMESTAMP")

        # 3) Backfill timestamps (idempotent)
        conn.exec_driver_sql("UPDATE inventory SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        conn.exec_driver_sql("UPDATE inventory SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

        # 4) On Postgres, ensure defaults for future inserts
        if is_postgres():
            conn.exec_driver_sql("ALTER TABLE inventory ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP")
            conn.exec_driver_sql("ALTER TABLE inventory ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP")

        # 5) Drop legacy non-unique index (ignore errors)
        try:
            conn.exec_driver_sql("DROP INDEX IF EXISTS idx_inventory_name;")
        except Exception:
            pass

        # 6) Deduplicate names prior to unique index
        deduped = _dedupe_inventory_names(conn)
        if deduped:
            print(f"Schema: deduped {deduped} duplicate inventory name(s).")

        # 7) Indices
        _ensure_index(conn, "idx_inventory_name_unique", "inventory", "name", unique=True)
        _ensure_index(conn, "idx_inventory_cat",  "inventory", "category")
        _ensure_index(conn, "idx_inventory_qty",  "inventory", "quantity")
        _ensure_index(conn, "idx_sales_item",     "sales",     "item_id")
        _ensure_index(conn, "idx_sales_date",     "sales",     "sold_at")

    _schema_checked = True

# --- DB helpers --------------------------------------------------------------
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
