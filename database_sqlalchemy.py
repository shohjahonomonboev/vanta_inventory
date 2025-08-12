# database_sqlalchemy.py
# Lightweight SQL layer that works with SQLite (dev) and Postgres (prod)

import os
import pathlib
from typing import Any, Dict, Iterable, List, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

BASE_DIR = pathlib.Path(__file__).parent
SQLITE_URL = f"sqlite:///{BASE_DIR / 'inventory.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", SQLITE_URL)

engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)


def is_sqlite() -> bool:
    return engine.url.get_backend_name() == "sqlite"


def db_all(sql: str, params: Optional[Dict[str, Any]] = None):
    with engine.begin() as conn:
        return conn.execute(text(sql), params or {}).all()


def db_one(sql: str, params: Optional[Dict[str, Any]] = None):
    with engine.begin() as conn:
        return conn.execute(text(sql), params or {}).one_or_none()


def db_exec(sql: str, params: Optional[Dict[str, Any]] = None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def ensure_schema():
    """Create tables/columns if missing. Safe in both SQLite & Postgres."""
    if is_sqlite():
        # SQLite DDL
        db_exec(
            """
            CREATE TABLE IF NOT EXISTS inventory (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE,
              buying_price REAL,
              selling_price REAL,
              quantity INTEGER,
              profit REAL,
              currency TEXT NOT NULL DEFAULT 'UZS'
            )
            """
        )
        db_exec(
            """
            CREATE TABLE IF NOT EXISTS sales (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              item_id INTEGER NOT NULL,
              qty INTEGER NOT NULL,
              sell_price REAL NOT NULL,
              profit REAL NOT NULL,
              sold_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Backfill currency if somehow null/empty
        db_exec("UPDATE inventory SET currency='UZS' WHERE currency IS NULL OR TRIM(currency)='' ")
    else:
        # Postgres DDL
        db_exec(
            """
            CREATE TABLE IF NOT EXISTS inventory (
              id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              name TEXT UNIQUE,
              buying_price NUMERIC(14,2),
              selling_price NUMERIC(14,2),
              quantity INTEGER,
              profit NUMERIC(14,2),
              currency TEXT NOT NULL DEFAULT 'UZS'
            )
            """
        )
        db_exec(
            """
            CREATE TABLE IF NOT EXISTS sales (
              id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              item_id INTEGER NOT NULL,
              qty INTEGER NOT NULL,
              sell_price NUMERIC(14,2) NOT NULL,
              profit NUMERIC(14,2) NOT NULL,
              sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Make sure currency column exists (safe if already there)
        db_exec("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'UZS'")