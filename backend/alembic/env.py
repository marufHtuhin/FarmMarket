"""Alembic environment for FarmMarket.

- Database URL comes from the DATABASE_URL environment variable (or .env),
  the same source app/database.py uses. The sqlalchemy.url in alembic.ini
  is only a placeholder and is overridden here.
- target_metadata is app.models.Base.metadata, so `alembic revision
  --autogenerate` picks up every model change.
- Run from backend/:  alembic upgrade head | alembic revision --autogenerate -m "..."
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# backend/ on sys.path so `app` imports work regardless of the caller's cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import db_connect_args, normalize_database_url  # noqa: E402

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./farmmarket.db"))
config.set_main_option("sqlalchemy.url", DATABASE_URL)

from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Pass the same connect args as app/database.py so migrations can
    # reach TiDB Cloud Starter too (auto-detected TLS via db_connect_args;
    # NullPool: pool_recycle is irrelevant).
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=db_connect_args(DATABASE_URL),
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
