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
                # Only for Postgres
                kwargs.update(
                    pool_recycle=1800,
                    pool_size=5,
                    max_overflow=10,
                )
            elif DATABASE_URL.startswith("sqlite"):
                # SQLite needs this when used with threaded servers
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
