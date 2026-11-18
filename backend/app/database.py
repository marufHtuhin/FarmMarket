import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import (
    database_pool_recycle,
    db_connect_args,
    normalize_database_url,
)

load_dotenv()
DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./farmmarket.db"))
# SQLite -> check_same_thread; TiDB Cloud (*.tidbcloud.com) -> verified TLS
# automatically (certifi CA bundle); DB_SSL forces TLS on/off. Railway
# MySQL keeps the empty default. See config.db_connect_args.
connect_args = db_connect_args(DATABASE_URL)
_engine_kwargs: dict = {"pool_pre_ping": True, "connect_args": connect_args}
_pool_recycle = database_pool_recycle(DATABASE_URL)
if _pool_recycle is not None:
    # TiDB Starter closes idle connections after 5 min.
    _engine_kwargs["pool_recycle"] = _pool_recycle
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass


def escape_like(value: str) -> str:
    """Wrap a user search term for a case-insensitive LIKE match, escaping
    the LIKE wildcards (``%``, ``_``) and the escape character itself so a
    search for ``%`` matches a literal percent sign instead of every row.
    Use with ``.ilike(escape_like(term), escape="\\")`` (backslash escape)."""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
