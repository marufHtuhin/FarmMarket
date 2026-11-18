"""Seed the external_data_sources registry (idempotent).

The admin list endpoint self-seeds on first read, so this script is only a
convenience for operators who want the six rows present before any admin
opens the page. Run from the backend/ directory:

    python scripts/seed_data_sources.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.routers.data_sources import SEED_SOURCES, ensure_seeded  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seeded(db)
        print(f"External data sources seeded ({len(SEED_SOURCES)} known sources).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
