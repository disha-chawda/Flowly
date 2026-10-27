"""Unit tests for the startup schema check ``check_schema``.

Each test uses its own SQLite file under pytest's ``tmp_path``; ``flowly.db`` is
never touched. Engines are disposed so Windows can remove the temporary files.

Validates: Requirements 14.2, 14.3, 14.4
"""

import pytest
from sqlalchemy import create_engine, text

from app.data import models  # noqa: F401  (registers the tables on Base.metadata)
from app.data.database import Base, check_schema


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema_check.db'}")
    try:
        yield engine
    finally:
        engine.dispose()


def test_old_commitments_table_without_import_key_raises(engine):
    """A pre-feature commitments table stops startup with the fix (Requirement 14.3)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE commitments ("
                "id INTEGER PRIMARY KEY, "
                "title VARCHAR NOT NULL, "
                "start_time DATETIME NOT NULL, "
                "end_time DATETIME NOT NULL, "
                "source VARCHAR NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )

    with pytest.raises(RuntimeError) as excinfo:
        check_schema(engine)

    message = str(excinfo.value)
    assert "import_key" in message
    assert "flowly.db" in message
    assert "README 'Calendar import'" in message
    assert "schema_check.db" in message


def test_fresh_create_all_schema_passes(engine):
    Base.metadata.create_all(bind=engine)

    check_schema(engine)


def test_empty_database_passes(engine):
    """With no commitments table yet, there is nothing to check."""
    check_schema(engine)
