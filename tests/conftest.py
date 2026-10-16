import os

import pytest


@pytest.fixture
def db():
    """Use only an explicitly supplied disposable database ending in _test."""
    url = os.getenv("QUANTFORGE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set QUANTFORGE_TEST_DATABASE_URL to a disposable PostgreSQL *_test database")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    from app.core.db import Base
    from app import models
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Integration tests require a disposable database name ending in _test")
    engine = create_engine(url)
    from app.migrate import migrate
    migrate(engine)
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = sessionmaker(engine, expire_on_commit=False)()
    session.add(models.User(email="admin@test.example", name="Test Admin", password_hash="unused", role="admin"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
