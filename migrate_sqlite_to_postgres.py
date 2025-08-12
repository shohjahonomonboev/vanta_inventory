# migrate_sqlite_to_postgres.py
# Copies data from local SQLite inventory.db -> Postgres (DATABASE_URL)

import os
import pathlib
from sqlalchemy import create_engine, text

BASE = pathlib.Path(__file__).parent
sqlite_url = f"sqlite:///{BASE / 'inventory.db'}"

# Get Postgres URL from environment
pg_url = os.getenv("DATABASE_URL")
if not pg_url:
    raise RuntimeError("❌ DATABASE_URL environment variable not set")

# Create engines
src = create_engine(sqlite_url, future=True)
dst = create_engine(pg_url, future=True)

print(f"🔄 Migrating from SQLite ({sqlite_url}) to Postgres ({pg_url})")

# Ensure destination schema exists
with dst.begin() as d:
    d.execute(text(
        """
        CREATE TABLE IF NOT EXISTS inventory (
          id INTEGER PRIMARY KEY,
          name TEXT UNIQUE,
          buying_price NUMERIC(14,2),
          selling_price NUMERIC(14,2),
          quantity INTEGER,
          profit NUMERIC(14,2),
          currency TEXT NOT NULL DEFAULT 'UZS'
        )
        """
    ))
    d.execute(text(
        """
        CREATE TABLE IF NOT EXISTS sales (
          id INTEGER PRIMARY KEY,
          item_id INTEGER NOT NULL,
          qty INTEGER NOT NULL,
          sell_price NUMERIC(14,2) NOT NULL,
          profit NUMERIC(14,2) NOT NULL,
          sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))

# Copy data
with src.begin() as s, dst.begin() as d:
    inv = s.execute(text("""
        SELECT id, name, buying_price, selling_price, quantity, profit, COALESCE(currency,'UZS')
        FROM inventory
    """)).all()

    for r in inv:
        d.execute(text(
            """
            INSERT INTO inventory (id, name, buying_price, selling_price, quantity, profit, currency)
            VALUES (:id, :name, :bp, :sp, :q, :pf, :cur)
            ON CONFLICT (id) DO NOTHING
            """
        ), {"id": r[0], "name": r[1], "bp": r[2], "sp": r[3], "q": r[4], "pf": r[5], "cur": r[6]})
    print(f"✅ Migrated {len(inv)} inventory rows.")

    sales = s.execute(text("""
        SELECT id, item_id, qty, sell_price, profit, sold_at
        FROM sales
    """)).all()

    for r in sales:
        d.execute(text(
            """
            INSERT INTO sales (id, item_id, qty, sell_price, profit, sold_at)
            VALUES (:id, :item, :qty, :sp, :pf, :ts)
            ON CONFLICT (id) DO NOTHING
            """
        ), {"id": r[0], "item": r[1], "qty": r[2], "sp": r[3], "pf": r[4], "ts": r[5]})
    print(f"✅ Migrated {len(sales)} sales rows.")

print("🎯 Migration complete.")
