"""Unit tests for ``Commitment.import_key``.

Runs against a fresh in-memory SQLite database per test; ``flowly.db`` is never
touched.

Validates: Requirements 5.1, 5.2, 16.2
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.database import Base
from app.data.models import Commitment
from app.domain.enums import Source
from app.schemas.commitment import CommitmentRead


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _commitment(n: int, **kwargs) -> Commitment:
    start = datetime(2026, 1, 5, 9, 0) + timedelta(hours=n)
    return Commitment(
        title=f"commitment-{n}",
        start_time=start,
        end_time=start + timedelta(minutes=30),
        **kwargs,
    )


def test_import_key_defaults_to_null(session):
    """A commitment created without an import key stores NULL (Requirement 5.2)."""
    row = _commitment(0)
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.import_key is None
    assert row.source == Source.MANUAL


def test_many_rows_with_null_import_key_are_allowed(session):
    """The unique constraint ignores NULLs, so manual rows never conflict."""
    session.add_all([_commitment(n) for n in range(5)])
    session.commit()

    assert session.query(Commitment).filter(Commitment.import_key.is_(None)).count() == 5


def test_distinct_import_keys_are_allowed(session):
    session.add_all(
        [
            _commitment(0, source=Source.ICS_IMPORT, import_key="S|a@example.com"),
            _commitment(1, source=Source.ICS_IMPORT, import_key="S|b@example.com"),
            _commitment(2),
        ]
    )
    session.commit()

    keys = {c.import_key for c in session.query(Commitment).all()}
    assert keys == {"S|a@example.com", "S|b@example.com", None}


def test_duplicate_non_null_import_key_raises_integrity_error(session):
    """Two rows with the same non-null key violate the unique constraint (Requirement 5.2)."""
    session.add(_commitment(0, source=Source.ICS_IMPORT, import_key="S|dup@example.com"))
    session.commit()

    session.add(_commitment(1, source=Source.ICS_IMPORT, import_key="S|dup@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # Only the first row is stored.
    assert session.query(Commitment).count() == 1


def test_commitment_read_has_no_import_key():
    """The API response shape is unchanged (Requirement 16.2)."""
    assert "import_key" not in CommitmentRead.model_fields


def test_commitment_read_from_row_omits_import_key(session):
    row = _commitment(0, source=Source.ICS_IMPORT, import_key="S|x@example.com")
    session.add(row)
    session.commit()
    session.refresh(row)

    dumped = CommitmentRead.model_validate(row).model_dump()
    assert "import_key" not in dumped
    assert dumped["source"] == Source.ICS_IMPORT
