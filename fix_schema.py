# fix_schema.py — run ON RENDER to ensure tables/columns exist
import os, time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL not set")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(db_url, pool_pre_ping=True)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        buying_price NUMERIC(14,2) NOT NULL DEFAULT 0,
        selling_price NUMERIC(14,2) NOT NULL DEFAULT 0,
        quantity INTEGER NOT NULL DEFAULT 0,
        profit NUMERIC(14,2) NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'UZS',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL,
        qty INTEGER,
        sell_price NUMERIC(14,2),
        profit NUMERIC(14,2) NOT NULL DEFAULT 0,
        sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory(name)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_qty  ON inventory(quantity)",
    "CREATE INDEX IF NOT EXISTS idx_sales_item     ON sales(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_date     ON sales(sold_at)",
    # Backfill from legacy column names if they exist
    """
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='sales' AND column_name='quantity') THEN
        UPDATE sales SET qty = quantity WHERE qty IS NULL;
      END IF;

      IF EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='sales' AND column_name='total_price') THEN
        UPDATE sales
           SET sell_price = CASE
                               WHEN COALESCE(qty,0) <> 0 THEN total_price / NULLIF(qty,0)
                               ELSE COALESCE(sell_price, 0)
                             END
         WHERE sell_price IS NULL;
      END IF;
    END $$;
    """,
]

def run():
    # retry so it works even if DB is briefly waking up
    for attempt in range(6):
        try:
            with engine.begin() as conn:
                for stmt in SCHEMA:
                    conn.execute(text(stmt))
            print("✅ Schema ensured on Postgres.")
            return
        except OperationalError as e:
            wait = 2 ** attempt
            print(f"DB not ready (attempt {attempt+1}), retrying in {wait}s... {e}")
            time.sleep(wait)
    raise SystemExit("❌ Could not connect to DB after retries.")

if __name__ == "__main__":
    run()
