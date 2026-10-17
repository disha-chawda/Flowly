"""Unit and property tests for the commitment service CRUD round-trips.

Exercises ``app.services.commitment_service.CommitmentService`` end to end
against a real (in-memory SQLite) database through the real
``CommitmentRepository``. No mocks or fakes are used: every assertion is checked
against persisted state read back through the session, so a passing test proves
the orchestration + persistence actually round-trips.

Covers:
  Feature: flowly-mvp, Property 7: Commitment creation round-trip with end-after-start validation
  Feature: flowly-mvp, Property 8: Commitment edit and delete

Validates: Requirements 3.1, 3.2, 3.3, 10
"""

from datetime import datetime, timedelta

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.commitment_repository import CommitmentRepository
from app.data.database import Base
from app.data.models import Commitment
from app.domain.enums import Source
from app.schemas.commitment import CommitmentCreate, CommitmentUpdate
from app.services.commitment_service import (
    CommitmentNotFoundError,
    CommitmentService,
    InvalidCommitmentIntervalError,
)


# --------------------------------------------------------------------------- #
# Test-database plumbing: a fresh in-memory SQLite per service under test.
# StaticPool keeps the single shared in-memory connection alive for the life of
# the engine, so repository commits and later reads see the same database.
# --------------------------------------------------------------------------- #
def _make_service():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    service = CommitmentService(CommitmentRepository(session))
    return service, session, SessionLocal


@pytest.fixture
def service():
    svc, session, _ = _make_service()
    try:
        yield svc
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Hypothesis strategies constrained to the real input space (schema rules).
# --------------------------------------------------------------------------- #
# Titles: 1..200 chars after trimming, and not whitespace-only.
_title_strategy = st.text(min_size=1, max_size=200).filter(
    lambda s: 1 <= len(s.strip()) <= 200
)
# Start time anywhere in a wide, naive-datetime range.
_start_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
)
# Duration strictly positive so end_time is always strictly after start_time.
_duration_strategy = st.integers(min_value=1, max_value=60 * 24 * 365).map(
    lambda minutes: timedelta(minutes=minutes)
)


@st.composite
def _valid_commitment_create(draw):
    """Build a valid ``CommitmentCreate`` (end strictly after start)."""
    title = draw(_title_strategy)
    start = draw(_start_strategy)
    end = start + draw(_duration_strategy)
    return CommitmentCreate(title=title, start_time=start, end_time=end)


# Function-scoped fixtures cannot be reused across Hypothesis examples, so the
# property tests build their own fresh database per example instead.
_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# --------------------------------------------------------------------------- #
# Property 7: Commitment creation round-trip with end-after-start validation
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 7: Commitment creation round-trip with end-after-start validation
@_SETTINGS
@given(payload=_valid_commitment_create())
def test_create_round_trip_persists_all_fields(payload):
    """A valid commitment persists with every field intact and source=manual.

    Validates 3.1 (create with valid title + end after start, persist),
    10 (source defaults to manual).
    """
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_commitment(payload)

        # Returned entity carries the supplied values and the manual source.
        assert created.id is not None
        assert created.title == payload.title
        assert created.start_time == payload.start_time
        assert created.end_time == payload.end_time
        assert created.source == Source.MANUAL
        # The validated payload guarantees end strictly after start.
        assert created.end_time > created.start_time

        # Round-trip: read it back through a fresh session (true persistence).
        fresh = SessionLocal()
        try:
            stored = fresh.get(Commitment, created.id)
            assert stored is not None
            assert stored.title == payload.title
            assert stored.start_time == payload.start_time
            assert stored.end_time == payload.end_time
            assert stored.source == Source.MANUAL
            assert stored.end_time > stored.start_time
        finally:
            fresh.close()
    finally:
        session.close()


# Feature: flowly-mvp, Property 7: Commitment creation round-trip with end-after-start validation
@_SETTINGS
@given(
    title=_title_strategy,
    start=_start_strategy,
    # Non-positive offset => end_time <= start_time, which must be rejected.
    offset_minutes=st.integers(min_value=-60 * 24, max_value=0),
)
def test_create_rejects_end_not_after_start(title, start, offset_minutes):
    """end_time at or before start_time is rejected and nothing is persisted.

    Validates 3.1 (end strictly after start) and 10 (validation). The schema
    raises before the service ever touches the repository, so storage stays
    empty.
    """
    svc, session, SessionLocal = _make_service()
    try:
        end = start + timedelta(minutes=offset_minutes)
        with pytest.raises(ValueError):
            CommitmentCreate(title=title, start_time=start, end_time=end)

        # No row was created by the rejected payload.
        fresh = SessionLocal()
        try:
            assert fresh.query(Commitment).count() == 0
        finally:
            fresh.close()
    finally:
        session.close()


def test_create_assigns_unique_ids(service):
    """Each created commitment gets a distinct id (Requirement 3.1)."""
    base = datetime(2025, 1, 1, 9, 0)
    ids = []
    for n in range(10):
        start = base + timedelta(hours=n)
        payload = CommitmentCreate(
            title=f"commitment-{n}",
            start_time=start,
            end_time=start + timedelta(minutes=30),
        )
        ids.append(service.create_commitment(payload).id)
    assert len(ids) == len(set(ids))
    assert all(i is not None for i in ids)


def test_create_defaults_source_to_manual(service):
    """A created commitment carries source=manual by default (Requirement 10)."""
    created = service.create_commitment(
        CommitmentCreate(
            title="lecture",
            start_time=datetime(2025, 3, 1, 10, 0),
            end_time=datetime(2025, 3, 1, 11, 30),
        )
    )
    assert created.source == Source.MANUAL


# --------------------------------------------------------------------------- #
# Property 8: Commitment edit and delete
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 8: Commitment edit and delete
@_SETTINGS
@given(
    original=_valid_commitment_create(),
    new_title=_title_strategy,
    new_start=_start_strategy,
    new_duration=_duration_strategy,
)
def test_edit_reflects_updates(original, new_title, new_start, new_duration):
    """Editing an existing commitment reflects every supplied field.

    Validates 3.2 (edit existing commitment). Both the returned entity and a
    fresh read-back show the new values.
    """
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_commitment(original)
        new_end = new_start + new_duration

        update = CommitmentUpdate(
            title=new_title,
            start_time=new_start,
            end_time=new_end,
        )
        updated = svc.update_commitment(created.id, update)

        # The schema trims titles (Requirements 3.1/10), so compare trimmed.
        assert updated.title == new_title.strip()
        assert updated.start_time == new_start
        assert updated.end_time == new_end
        assert updated.end_time > updated.start_time

        fresh = SessionLocal()
        try:
            stored = fresh.get(Commitment, created.id)
            assert stored.title == new_title.strip()
            assert stored.start_time == new_start
            assert stored.end_time == new_end
        finally:
            fresh.close()
    finally:
        session.close()


# Feature: flowly-mvp, Property 8: Commitment edit and delete
@_SETTINGS
@given(payload=_valid_commitment_create())
def test_delete_removes_the_commitment(payload):
    """After delete, the id is gone from storage (Requirement 3.3)."""
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_commitment(payload)
        commitment_id = created.id

        svc.delete_commitment(commitment_id)

        # Service lookup now raises.
        with pytest.raises(CommitmentNotFoundError):
            svc.get_commitment(commitment_id)

        # And a fresh session confirms the row is truly gone.
        fresh = SessionLocal()
        try:
            assert fresh.get(Commitment, commitment_id) is None
        finally:
            fresh.close()
    finally:
        session.close()


def test_edit_only_touches_supplied_fields(service):
    """Omitted fields are left untouched; supplied ones change (exclude_unset)."""
    created = service.create_commitment(
        CommitmentCreate(
            title="original",
            start_time=datetime(2025, 5, 1, 9, 0),
            end_time=datetime(2025, 5, 1, 10, 0),
        )
    )

    updated = service.update_commitment(
        created.id, CommitmentUpdate(title="renamed")
    )

    assert updated.title == "renamed"
    # Untouched time fields retain their original values.
    assert updated.start_time == datetime(2025, 5, 1, 9, 0)
    assert updated.end_time == datetime(2025, 5, 1, 10, 0)


def test_edit_missing_id_raises_not_found(service):
    """Editing an unknown id raises the not-found condition (Requirement 3.2)."""
    with pytest.raises(CommitmentNotFoundError):
        service.update_commitment(99999, CommitmentUpdate(title="nope"))


def test_delete_leaves_other_commitments_intact(service):
    """Deleting one commitment does not disturb the others (Requirement 3.3)."""
    base = datetime(2025, 6, 1, 8, 0)

    def _make(title, offset_hours):
        start = base + timedelta(hours=offset_hours)
        return service.create_commitment(
            CommitmentCreate(
                title=title,
                start_time=start,
                end_time=start + timedelta(minutes=30),
            )
        )

    keep_a = _make("keep-a", 0)
    drop = _make("drop", 1)
    keep_b = _make("keep-b", 2)

    service.delete_commitment(drop.id)

    remaining = {c.id for c in service.list_commitments()}
    assert remaining == {keep_a.id, keep_b.id}


def test_delete_missing_id_raises_not_found(service):
    """Deleting an unknown id raises the not-found condition (Requirement 3.3)."""
    with pytest.raises(CommitmentNotFoundError):
        service.delete_commitment(99999)


# --------------------------------------------------------------------------- #
# Regression: partial update must not bypass the end-after-start rule.
# The schema can only compare fields present in the same payload, so a partial
# update touching only one time field must be re-validated by the service
# against the stored value. Otherwise an inverted interval is persisted, giving
# compute_workload a negative length. Validates Requirements 3.1, 3.2.
# --------------------------------------------------------------------------- #
def _seed(service):
    return service.create_commitment(
        CommitmentCreate(
            title="meeting",
            start_time=datetime(2025, 1, 1, 9, 0),
            end_time=datetime(2025, 1, 1, 10, 0),
        )
    )


def test_update_only_start_past_end_is_rejected(service):
    """Updating only start_time past the stored end_time is rejected."""
    created = _seed(service)

    with pytest.raises(InvalidCommitmentIntervalError):
        service.update_commitment(
            created.id,
            CommitmentUpdate(start_time=datetime(2025, 1, 1, 11, 0)),
        )

    # Stored commitment is unchanged (no inverted interval persisted).
    stored = service.get_commitment(created.id)
    assert stored.start_time == datetime(2025, 1, 1, 9, 0)
    assert stored.end_time == datetime(2025, 1, 1, 10, 0)
    assert stored.end_time > stored.start_time


def test_update_only_end_before_start_is_rejected(service):
    """Updating only end_time before the stored start_time is rejected."""
    created = _seed(service)

    with pytest.raises(InvalidCommitmentIntervalError):
        service.update_commitment(
            created.id,
            CommitmentUpdate(end_time=datetime(2025, 1, 1, 8, 0)),
        )

    stored = service.get_commitment(created.id)
    assert stored.start_time == datetime(2025, 1, 1, 9, 0)
    assert stored.end_time == datetime(2025, 1, 1, 10, 0)
    assert stored.end_time > stored.start_time


def test_update_only_start_equal_to_end_is_rejected(service):
    """A zero-length interval (start == stored end) is rejected too."""
    created = _seed(service)

    with pytest.raises(InvalidCommitmentIntervalError):
        service.update_commitment(
            created.id,
            CommitmentUpdate(start_time=datetime(2025, 1, 1, 10, 0)),
        )

    stored = service.get_commitment(created.id)
    assert stored.start_time == datetime(2025, 1, 1, 9, 0)
    assert stored.end_time == datetime(2025, 1, 1, 10, 0)


def test_update_only_start_still_before_end_is_accepted(service):
    """A partial start update that keeps start < end still succeeds."""
    created = _seed(service)

    updated = service.update_commitment(
        created.id,
        CommitmentUpdate(start_time=datetime(2025, 1, 1, 9, 30)),
    )

    assert updated.start_time == datetime(2025, 1, 1, 9, 30)
    assert updated.end_time == datetime(2025, 1, 1, 10, 0)
    assert updated.end_time > updated.start_time


def test_invalid_interval_error_is_a_value_error(service):
    """InvalidCommitmentIntervalError is a ValueError subclass for callers."""
    created = _seed(service)
    with pytest.raises(ValueError):
        service.update_commitment(
            created.id,
            CommitmentUpdate(start_time=datetime(2025, 1, 1, 12, 0)),
        )
