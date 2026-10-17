"""Unit and property tests for the task service CRUD and completion round-trips.

Exercises ``app.services.task_service.TaskService`` end to end against a real
(in-memory SQLite) database through the real ``TaskRepository``. No mocks or
fakes are used: every assertion is checked against persisted state read back
through the session, so a passing test proves the orchestration + persistence
actually round-trips.

Covers:
  Feature: flowly-mvp, Property 1: Task creation round-trip with defaults
  Feature: flowly-mvp, Property 2: Task edit reflects updates
  Feature: flowly-mvp, Property 3: Delete removes the task
  Feature: flowly-mvp, Property 4: Completion toggle round-trip

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.2, 2.5, 2.6, 10
"""

from datetime import datetime

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.database import Base
from app.data.models import Task
from app.data.task_repository import TaskRepository
from app.domain.enums import Category, Completion, Priority, Source
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task_service import TaskNotFoundError, TaskService


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
    service = TaskService(TaskRepository(session))
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
_description_strategy = st.text(max_size=2000)
# estimated_time is a positive int when present (schema: gt=0), or None.
_estimated_strategy = st.one_of(st.none(), st.integers(min_value=1, max_value=100_000))
_deadline_strategy = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
    ),
)
_priority_strategy = st.sampled_from(list(Priority))
_category_strategy = st.sampled_from(list(Category))


@st.composite
def _task_create_strategy(draw, with_optionals=True):
    """Build a valid ``TaskCreate`` payload mirroring the schema constraints."""
    kwargs = {"title": draw(_title_strategy)}
    if with_optionals:
        kwargs.update(
            description=draw(_description_strategy),
            deadline=draw(_deadline_strategy),
            estimated_time=draw(_estimated_strategy),
            priority=draw(_priority_strategy),
            category=draw(_category_strategy),
        )
    return TaskCreate(**kwargs)


# Function-scoped fixtures cannot be reused across Hypothesis examples, so the
# property tests build their own fresh database per example instead.
_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# --------------------------------------------------------------------------- #
# Property 1: Task creation round-trip with defaults
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 1: Task creation round-trip with defaults
@_SETTINGS
@given(title=_title_strategy)
def test_create_applies_defaults_and_persists(title):
    """Creating a task with only a title persists it with the documented defaults.

    Validates 1.1 (defaults + persistence), 1.4 (returns created task),
    2.2/2.5/2.6/10 (description="", priority=Medium, category=Personal,
    completion=Incomplete, source=manual).
    """
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_task(TaskCreate(title=title))

        # Returned entity carries the trimmed title and every default.
        assert created.title == title.strip()
        assert created.description == ""
        assert created.priority == Priority.MEDIUM
        assert created.category == Category.PERSONAL
        assert created.completion == Completion.INCOMPLETE
        assert created.source == Source.MANUAL
        assert created.deadline is None
        assert created.estimated_time is None
        assert created.id is not None

        # Round-trip: read it back through a fresh session (true persistence).
        fresh = SessionLocal()
        try:
            stored = fresh.get(Task, created.id)
            assert stored is not None
            assert stored.title == title.strip()
            assert stored.description == ""
            assert stored.priority == Priority.MEDIUM
            assert stored.category == Category.PERSONAL
            assert stored.completion == Completion.INCOMPLETE
            assert stored.source == Source.MANUAL
        finally:
            fresh.close()
    finally:
        session.close()


# Feature: flowly-mvp, Property 1: Task creation round-trip with defaults
@_SETTINGS
@given(payload=_task_create_strategy())
def test_create_round_trip_preserves_all_provided_fields(payload):
    """Every provided field survives the create round-trip unchanged."""
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_task(payload)

        fresh = SessionLocal()
        try:
            stored = fresh.get(Task, created.id)
            assert stored is not None
            assert stored.title == payload.title
            assert stored.description == payload.description
            assert stored.deadline == payload.deadline
            assert stored.estimated_time == payload.estimated_time
            assert stored.priority == payload.priority
            assert stored.category == payload.category
            assert stored.completion == Completion.INCOMPLETE
            assert stored.source == Source.MANUAL
        finally:
            fresh.close()
    finally:
        session.close()


def test_create_assigns_unique_ids(service):
    """Each created task gets a distinct id (Requirement 1.2)."""
    ids = [service.create_task(TaskCreate(title=f"task-{n}")).id for n in range(10)]
    assert len(ids) == len(set(ids))
    assert all(i is not None for i in ids)


# --------------------------------------------------------------------------- #
# Property 2: Task edit reflects updates
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 2: Task edit reflects updates
@_SETTINGS
@given(
    payload=_task_create_strategy(),
    new_title=_title_strategy,
    new_description=_description_strategy,
    new_priority=_priority_strategy,
    new_category=_category_strategy,
    new_estimated=_estimated_strategy,
)
def test_edit_reflects_updates(
    payload, new_title, new_description, new_priority, new_category, new_estimated
):
    """Editing an existing task reflects every supplied field (Requirements 1.2, 2.2).

    Both the returned entity and a fresh read-back show the new values.
    """
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_task(payload)

        update = TaskUpdate(
            title=new_title,
            description=new_description,
            priority=new_priority,
            category=new_category,
            estimated_time=new_estimated,
        )
        updated = svc.update_task(created.id, update)

        assert updated.title == new_title.strip()
        assert updated.description == new_description
        assert updated.priority == new_priority
        assert updated.category == new_category
        assert updated.estimated_time == new_estimated

        fresh = SessionLocal()
        try:
            stored = fresh.get(Task, created.id)
            assert stored.title == new_title.strip()
            assert stored.description == new_description
            assert stored.priority == new_priority
            assert stored.category == new_category
            assert stored.estimated_time == new_estimated
        finally:
            fresh.close()
    finally:
        session.close()


def test_edit_only_touches_supplied_fields(service):
    """Omitted fields are left untouched; supplied ones change (exclude_unset)."""
    created = service.create_task(
        TaskCreate(title="original", description="keep me", priority=Priority.LOW)
    )

    updated = service.update_task(created.id, TaskUpdate(title="renamed"))

    assert updated.title == "renamed"
    # Untouched fields retain their original values.
    assert updated.description == "keep me"
    assert updated.priority == Priority.LOW


def test_edit_missing_id_raises_not_found(service):
    """Editing an unknown id raises the not-found condition (Requirement 1.3)."""
    with pytest.raises(TaskNotFoundError):
        service.update_task(99999, TaskUpdate(title="nope"))


# --------------------------------------------------------------------------- #
# Property 3: Delete removes the task
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 3: Delete removes the task
@_SETTINGS
@given(payload=_task_create_strategy())
def test_delete_removes_the_task(payload):
    """After delete, the id is gone from storage (Requirement 1.3)."""
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_task(payload)
        task_id = created.id

        svc.delete_task(task_id)

        # Service lookup now raises.
        with pytest.raises(TaskNotFoundError):
            svc.get_task(task_id)

        # And a fresh session confirms the row is truly gone.
        fresh = SessionLocal()
        try:
            assert fresh.get(Task, task_id) is None
        finally:
            fresh.close()
    finally:
        session.close()


def test_delete_leaves_other_tasks_intact(service):
    """Deleting one task does not disturb the others."""
    keep_a = service.create_task(TaskCreate(title="keep-a"))
    drop = service.create_task(TaskCreate(title="drop"))
    keep_b = service.create_task(TaskCreate(title="keep-b"))

    service.delete_task(drop.id)

    remaining = {t.id for t in service.list_tasks()}
    assert remaining == {keep_a.id, keep_b.id}


def test_delete_missing_id_raises_not_found(service):
    """Deleting an unknown id raises the not-found condition (Requirement 1.3)."""
    with pytest.raises(TaskNotFoundError):
        service.delete_task(99999)


# --------------------------------------------------------------------------- #
# Property 4: Completion toggle round-trip
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 4: Completion toggle round-trip
@_SETTINGS
@given(payload=_task_create_strategy(), toggles=st.integers(min_value=0, max_value=6))
def test_completion_toggle_round_trip(payload, toggles):
    """Toggling completion alternates Incomplete<->Complete and persists each state.

    A task starts Incomplete (Requirement 1.1); each toggle flips the state and
    the persisted value always matches the expected state after N flips
    (Requirements 1.4, 10).
    """
    svc, session, SessionLocal = _make_service()
    try:
        created = svc.create_task(payload)
        assert created.completion == Completion.INCOMPLETE

        state = Completion.INCOMPLETE
        for _ in range(toggles):
            state = (
                Completion.COMPLETE
                if state == Completion.INCOMPLETE
                else Completion.INCOMPLETE
            )
            returned = svc.set_completion(created.id, state)
            assert returned.completion == state

            fresh = SessionLocal()
            try:
                stored = fresh.get(Task, created.id)
                assert stored.completion == state
            finally:
                fresh.close()
    finally:
        session.close()


def test_mark_complete_then_incomplete(service):
    """Explicit Incomplete -> Complete -> Incomplete round-trip (Requirement 1.4)."""
    created = service.create_task(TaskCreate(title="toggle"))
    assert created.completion == Completion.INCOMPLETE

    done = service.set_completion(created.id, Completion.COMPLETE)
    assert done.completion == Completion.COMPLETE

    undone = service.set_completion(created.id, Completion.INCOMPLETE)
    assert undone.completion == Completion.INCOMPLETE


def test_set_completion_missing_id_raises_not_found(service):
    """Completing an unknown id raises the not-found condition (Requirement 1.3)."""
    with pytest.raises(TaskNotFoundError):
        service.set_completion(99999, Completion.COMPLETE)
