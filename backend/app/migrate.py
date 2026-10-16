"""Versioned PostgreSQL migrations for fresh and existing installations."""
import hashlib
from pathlib import Path
import re

from sqlalchemy import inspect, text
from .core.db import Base, engine
from . import models

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATIONS = (
    "MIGRATION_HARDENING.sql", "MIGRATION_VARIANTS.sql", "MIGRATION_FINAL_PASS.sql",
    "MIGRATION_PRACTICE_MODE.sql", "MIGRATION_GENERATION_BATCHES.sql", "MIGRATION_APPLICATION.sql",
)


def migrate(target=engine):
    with target.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(728419002)"))
        if not inspect(connection).has_table("users"):
            Base.metadata.create_all(connection)
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT NOW())")
        for name in MIGRATIONS:
            sql = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            stored = connection.execute(text("SELECT checksum FROM schema_migrations WHERE name=:name"), {"name": name}).scalar()
            if stored:
                if stored != checksum:
                    raise RuntimeError(f"Applied migration changed: {name}; add a new migration instead")
                continue
            sql = re.sub(r"(?im)^\s*(?:BEGIN|COMMIT);\s*$", "", sql)
            connection.exec_driver_sql(sql)
            connection.execute(text("INSERT INTO schema_migrations(name, checksum) VALUES (:name, :checksum)"), {"name": name, "checksum": checksum})


if __name__ == "__main__":
    migrate()
    print("Database migrations complete.")
