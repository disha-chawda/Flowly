"""Unit and property tests for the dashboard Today/Upcoming view selection.

Exercises ``app.services.dashboard_service.DashboardService.today_view`` and
``.upcoming_view`` end to end against a real (in-memory SQLite) database through
the real ``TaskRepository``/``CommitmentRepository``. No mocks or fakes are used:
tasks are persisted and read back through the service, so a passing test proves
the selection, filtering, and ordering logic actually works against stored rows.

Covers:
  Feature: flowly-mvp, Property 17: Today view selection
  Feature: flowly-mvp, Property 18: Upcoming view selection and ordering

Validates: Requirements 12 (Today_View), 13 (Upcoming_View).
  * Today view (Req 12): all Tasks whose Deadline falls on the target calendar
    date, including completed ones (completion preserved so they can be labeled
    complete); empty when none match.
  * Upcoming view (Req 13): all INCOMPLETE Tasks whose Deadline falls strictly
    after the target date, ordered by Deadline ascending; empty when none match.
"""

from datetime import date, datetime, time, timedelta

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.commitment_repository import CommitmentRepository
from app.data.database import Base
from app.data.models import Task
from app.data.task_repository import TaskRepository
from app.domain.enums import Category, Completion, Priority, Source
from app.services.dashboard_service import DashboardService


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
    service = DashboardService(
        TaskRepository(session),
        CommitmentRepository(session),
    )
    return service, session


@pytest.fixture
def service():
    svc, session = _make_service()
    try:
        yield svc
    finally:
        session.close()


def _add_task(session, *, deadline, completion=Completion.INCOMPLETE, title="t"):
    """Persist a Task directly and return it (bypasses schema validation so the
    tests can place tasks at arbitrary deadlines quickly)."""
    task = Task(
        title=title,
        description="",
        deadline=deadline,
        estimated_time=None,
        priority=Priority.MEDIUM,
        category=Category.PERSONAL,
        completion=completion,
        source=Source.MANUAL,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


# --------------------------------------------------------------------------- #
# Hypothesis strategies constrained to the real input space.
# --------------------------------------------------------------------------- #
# A target calendar date in a range that leaves room on both sides for
# before/on/after deadlines without hitting datetime min/max.
_target_date_strategy = st.dates(
    min_value=date(2010, 1, 1),
    max_value=date(2090, 12, 31),
)
# Deadlines are datetimes; selection is by calendar date so the time-of-day must
# not matter. Cover the full day range to exercise that.
_time_of_day_strategy = st.times()
_completion_strategy = st.sampled_from(list(Completion))


@st.composite
def _task_spec_strategy(draw, target: date):
    """Build a (day_offset, time_of_day, completion) spec for one task.

    ``day_offset`` places the deadline before (-), on (0), or after (+) the
    target date. ``None`` means the task has no deadline at all.
    """
    day_offset = draw(
        st.one_of(
            st.none(),
            st.integers(min_value=-400, max_value=400),
        )
    )
    tod = draw(_time_of_day_strategy)
    completion = draw(_completion_strategy)
    return day_offset, tod, completion


# Function-scoped fixtures cannot be reused across Hypothesis examples, so the
# property tests build their own fresh database per example instead.
_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _deadline_for(target: date, day_offset, tod: time):
    """Return a datetime deadline at ``target + day_offset`` days / ``tod``.

    ``day_offset`` of ``None`` yields ``None`` (a task with no deadline). Offsets
    that would fall outside the datetime range are clamped by construction since
    the target range is kept well inside datetime.min/max.
    """
    if day_offset is None:
        return None
    return datetime.combine(target + timedelta(days=day_offset), tod)


# --------------------------------------------------------------------------- #
# Property 17: Today view selection
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 17: Today view selection
@_SETTINGS
@given(
    target=_target_date_strategy,
    specs=st.lists(st.deferred(lambda: _any_spec), min_size=0, max_size=12),
)
def test_today_view_selects_exactly_deadlines_on_target(target, specs):
    """Today view returns exactly the tasks whose deadline's date equals target.

    Validates Requirement 12.1 (all tasks due on the target date) and 12.4
    (empty when none match). Completed tasks ARE included (12.3): selection is by
    deadline date only, independent of completion state. Tasks with a deadline on
    another date, and tasks with no deadline, are excluded.
    """
    svc, session = _make_service()
    try:
        expected_ids = set()
        for day_offset, tod, completion in specs:
            dl = _deadline_for(target, day_offset, tod)
            created = _add_task(session, deadline=dl, completion=completion)
            if dl is not None and dl.date() == target:
                expected_ids.add(created.id)

        result = svc.today_view(target)
        result_ids = {t.id for t in result}

        # Exactly the tasks due on the target date, regardless of completion.
        assert result_ids == expected_ids
        # Every returned task really does fall on the target date.
        assert all(t.deadline is not None and t.deadline.date() == target for t in result)
        # Empty when nothing matches (12.4).
        if not expected_ids:
            assert result == []
    finally:
        session.close()


# Feature: flowly-mvp, Property 17: Today view selection
@_SETTINGS
@given(
    target=_target_date_strategy,
    specs=st.lists(st.deferred(lambda: _any_spec), min_size=0, max_size=12),
)
def test_today_view_preserves_completion_state(target, specs):
    """Completed tasks stay in the Today view with completion preserved (Req 12.3).

    Each returned task's completion field is whatever was stored, so the API can
    label complete tasks as complete rather than dropping them.
    """
    svc, session = _make_service()
    try:
        expected = {}  # id -> stored completion
        for day_offset, tod, completion in specs:
            dl = _deadline_for(target, day_offset, tod)
            created = _add_task(session, deadline=dl, completion=completion)
            if dl is not None and dl.date() == target:
                expected[created.id] = completion

        result = svc.today_view(target)

        assert {t.id for t in result} == set(expected)
        for t in result:
            assert t.completion == expected[t.id]
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Property 18: Upcoming view selection and ordering
# --------------------------------------------------------------------------- #
# Feature: flowly-mvp, Property 18: Upcoming view selection and ordering
@_SETTINGS
@given(
    target=_target_date_strategy,
    specs=st.lists(st.deferred(lambda: _any_spec), min_size=0, max_size=12),
)
def test_upcoming_view_selects_incomplete_future_in_deadline_order(target, specs):
    """Upcoming view returns incomplete tasks due strictly after target, ascending.

    Validates Requirement 13.1 (incomplete tasks whose deadline is after the
    target date), 13.2 (ordered by deadline earliest to latest), and 13.4 (empty
    when none match). Completed tasks, tasks due on/before the target, and tasks
    with no deadline are all excluded.
    """
    svc, session = _make_service()
    try:
        expected_ids = set()
        for day_offset, tod, completion in specs:
            dl = _deadline_for(target, day_offset, tod)
            created = _add_task(session, deadline=dl, completion=completion)
            is_future = dl is not None and dl.date() > target
            if is_future and completion == Completion.INCOMPLETE:
                expected_ids.add(created.id)

        result = svc.upcoming_view(target)
        result_ids = {t.id for t in result}

        # Exactly the incomplete, strictly-future tasks.
        assert result_ids == expected_ids
        # No completed tasks leak in, and every deadline is strictly after target.
        for t in result:
            assert t.completion == Completion.INCOMPLETE
            assert t.deadline is not None and t.deadline.date() > target
        # Ordered by deadline ascending (13.2).
        deadlines = [t.deadline for t in result]
        assert deadlines == sorted(deadlines)
        # Empty when nothing matches (13.4).
        if not expected_ids:
            assert result == []
    finally:
        session.close()


# Shared spec strategy used by the property tests above. Defined after the
# composite so the deferred reference resolves to a concrete strategy that draws
# a (day_offset, time_of_day, completion) tuple with a fixed reference date; the
# absolute target is irrelevant because only the relative day offset matters.
_any_spec = st.tuples(
    st.one_of(st.none(), st.integers(min_value=-400, max_value=400)),
    _time_of_day_strategy,
    _completion_strategy,
)


# --------------------------------------------------------------------------- #
# Concrete example-based unit cases (edge cases and specific behaviors).
# --------------------------------------------------------------------------- #
def test_today_view_empty_when_no_tasks(service):
    """No tasks at all => empty Today view (Requirement 12.4)."""
    assert service.today_view(date(2025, 6, 1)) == []


def test_today_view_empty_when_none_on_date(service):
    """Tasks exist but none due on the date => empty Today view (12.4)."""
    svc, session = _make_service()
    try:
        _add_task(session, deadline=datetime(2025, 5, 31, 12, 0))
        _add_task(session, deadline=datetime(2025, 6, 2, 9, 0))
        _add_task(session, deadline=None)  # no deadline, never in Today view
        assert svc.today_view(date(2025, 6, 1)) == []
    finally:
        session.close()


def test_today_view_includes_completed_and_incomplete_on_date(service):
    """Both completed and incomplete tasks due on the date appear (12.1, 12.3)."""
    svc, session = _make_service()
    try:
        incomplete = _add_task(
            session,
            deadline=datetime(2025, 6, 1, 8, 0),
            completion=Completion.INCOMPLETE,
        )
        complete = _add_task(
            session,
            deadline=datetime(2025, 6, 1, 23, 59),
            completion=Completion.COMPLETE,
        )
        result = svc.today_view(date(2025, 6, 1))
        by_id = {t.id: t for t in result}
        assert set(by_id) == {incomplete.id, complete.id}
        assert by_id[incomplete.id].completion == Completion.INCOMPLETE
        assert by_id[complete.id].completion == Completion.COMPLETE
    finally:
        session.close()


def test_today_view_matches_any_time_of_day_on_date(service):
    """Selection is by calendar date, so time-of-day on the boundary still counts."""
    svc, session = _make_service()
    try:
        midnight = _add_task(session, deadline=datetime(2025, 6, 1, 0, 0, 0))
        last_tick = _add_task(session, deadline=datetime(2025, 6, 1, 23, 59, 59))
        # Just outside the day on either side.
        _add_task(session, deadline=datetime(2025, 5, 31, 23, 59, 59))
        _add_task(session, deadline=datetime(2025, 6, 2, 0, 0, 0))
        result_ids = {t.id for t in svc.today_view(date(2025, 6, 1))}
        assert result_ids == {midnight.id, last_tick.id}
    finally:
        session.close()


def test_upcoming_view_empty_when_no_tasks(service):
    """No tasks at all => empty Upcoming view (Requirement 13.4)."""
    assert service.upcoming_view(date(2025, 6, 1)) == []


def test_upcoming_view_excludes_on_and_before_target(service):
    """Deadlines on or before the target date are excluded (13.1)."""
    svc, session = _make_service()
    try:
        _add_task(session, deadline=datetime(2025, 5, 30, 9, 0))  # before
        _add_task(session, deadline=datetime(2025, 6, 1, 23, 59))  # on target
        after = _add_task(session, deadline=datetime(2025, 6, 2, 0, 0))  # after
        result_ids = {t.id for t in svc.upcoming_view(date(2025, 6, 1))}
        assert result_ids == {after.id}
    finally:
        session.close()


def test_upcoming_view_excludes_completed_future(service):
    """Completed tasks are excluded even when their deadline is in the future (13.1)."""
    svc, session = _make_service()
    try:
        _add_task(
            session,
            deadline=datetime(2025, 6, 10, 9, 0),
            completion=Completion.COMPLETE,
        )
        incomplete = _add_task(
            session,
            deadline=datetime(2025, 6, 5, 9, 0),
            completion=Completion.INCOMPLETE,
        )
        result = svc.upcoming_view(date(2025, 6, 1))
        assert [t.id for t in result] == [incomplete.id]
    finally:
        session.close()


def test_upcoming_view_excludes_no_deadline(service):
    """Tasks without a deadline are not in the Upcoming view (13.1)."""
    svc, session = _make_service()
    try:
        _add_task(session, deadline=None, completion=Completion.INCOMPLETE)
        future = _add_task(session, deadline=datetime(2025, 6, 5, 9, 0))
        result_ids = {t.id for t in svc.upcoming_view(date(2025, 6, 1))}
        assert result_ids == {future.id}
    finally:
        session.close()


def test_upcoming_view_orders_by_deadline_ascending(service):
    """Future incomplete tasks are returned earliest-deadline first (13.2)."""
    svc, session = _make_service()
    try:
        late = _add_task(session, deadline=datetime(2025, 6, 20, 9, 0))
        early = _add_task(session, deadline=datetime(2025, 6, 3, 9, 0))
        middle = _add_task(session, deadline=datetime(2025, 6, 10, 9, 0))
        result = svc.upcoming_view(date(2025, 6, 1))
        assert [t.id for t in result] == [early.id, middle.id, late.id]
    finally:
        session.close()


def test_today_view_accepts_datetime_target(service):
    """Passing a datetime target is normalized to its date for selection."""
    svc, session = _make_service()
    try:
        match = _add_task(session, deadline=datetime(2025, 6, 1, 7, 0))
        _add_task(session, deadline=datetime(2025, 6, 2, 7, 0))
        result_ids = {t.id for t in svc.today_view(datetime(2025, 6, 1, 15, 30))}
        assert result_ids == {match.id}
    finally:
        session.close()
