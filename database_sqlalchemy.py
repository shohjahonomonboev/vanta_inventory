
# database_sqlalchemy.py
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
import os, time
import urllib.parse as up  # optional (for masked logging)

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("DB_URL")
)

assert DATABASE_URL, "DATABASE_URL not set"

# (Optional) Show masked DB URL in logs (helps debugging without leaking the password)
try:
    parts = up.urlparse(DATABASE_URL)
    masked = f"{parts.scheme}://{parts.username}:***@{parts.hostname}:{parts.port}{parts.path}{'?' + parts.query if parts.query else ''}"
    print("DB URL (masked):", masked)
except Exception:
    pass

def make_engine():
    """
    Create a SQLAlchemy engine with connection health checks and retries.
    - pool_pre_ping: validates connections before use
    - pool_recycle: refresh connections every 30 minutes (cloud DBs close idle ones)
    - retry: exponential backoff so deploys don’t crash if DB isn’t ready
    """
    last_err = None
    for attempt in range(6):  # ~1 + 2 + 4 + 8 + 16 + 32 = ~63s max
        try:
            eng = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_size=5,
                max_overflow=10,
            )
            # Quick test: open/close a connection
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"DB engine ready (attempt {attempt+1})")
            return eng
        except OperationalError as e:
            last_err = e
            wait = 2 ** attempt
            print(f"DB connect failed (attempt {attempt+1}), retrying in {wait}s...")
            time.sleep(wait)
    # If all retries failed, raise the last error
    raise last_err

# Needed for the quick test above
from sqlalchemy import text

engine = make_engine()
