import uuid
import pytest
from sqlalchemy import create_engine, text, inspect
from app.migrate import migrate

pytestmark = pytest.mark.integration


def test_fresh_install_and_migration_repeatability(db):
    schema = "fresh_" + uuid.uuid4().hex
    with db.bind.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    fresh = create_engine(db.bind.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        migrate(fresh)
        migrate(fresh)
        tables = inspect(fresh).get_table_names()
        assert {"questions", "quiz_sessions", "generation_jobs", "schema_migrations"} <= set(tables)
        assert "review_status" in {c["name"] for c in inspect(fresh).get_columns("questions")}
        assert {"answers", "revision", "result"} <= {c["name"] for c in inspect(fresh).get_columns("quiz_sessions")}
    finally:
        fresh.dispose()
        with db.bind.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
