"""Unit tests for the commitment Pydantic schemas in app/schemas/commitment.py.

Covers title validation, time-ordering rules, explicit-null rejection on
partial updates, and ORM-style construction of the read schema.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.domain.enums import Source
from app.schemas.commitment import (
    TITLE_MAX,
    CommitmentCreate,
    CommitmentRead,
    CommitmentUpdate,
)

START = datetime(2026, 10, 27, 9, 0)
END = START + timedelta(hours=1)


# ---------------------------------------------------------------------------
# CommitmentCreate
# ---------------------------------------------------------------------------


def test_create_valid_defaults_source_to_manual():
    c = CommitmentCreate(title="Lecture", start_time=START, end_time=END)
    assert c.title == "Lecture"
    assert c.start_time == START
    assert c.end_time == END
    assert c.source is Source.MANUAL


def test_create_accepts_explicit_source_value():
    c = CommitmentCreate(
        title="Lecture", start_time=START, end_time=END, source="manual"
    )
    assert c.source is Source.MANUAL


def test_create_rejects_unknown_source():
    with pytest.raises(ValidationError):
        CommitmentCreate(
            title="Lecture", start_time=START, end_time=END, source="calendar"
        )


def test_create_trims_title_whitespace():
    c = CommitmentCreate(title="  Standup  ", start_time=START, end_time=END)
    assert c.title == "Standup"


@pytest.mark.parametrize("title", ["", "   ", "\t\n "])
def test_create_rejects_empty_or_whitespace_title(title):
    with pytest.raises(ValidationError, match="must not be empty"):
        CommitmentCreate(title=title, start_time=START, end_time=END)


def test_create_accepts_title_at_max_length():
    title = "a" * TITLE_MAX
    c = CommitmentCreate(title=title, start_time=START, end_time=END)
    assert c.title == title


def test_create_rejects_title_over_max_length():
    with pytest.raises(ValidationError, match=f"at most {TITLE_MAX}"):
        CommitmentCreate(title="a" * (TITLE_MAX + 1), start_time=START, end_time=END)


def test_create_length_check_applies_after_trimming():
    # Surrounding whitespace should not count toward the limit.
    title = "  " + "a" * TITLE_MAX + "  "
    c = CommitmentCreate(title=title, start_time=START, end_time=END)
    assert len(c.title) == TITLE_MAX


def test_create_rejects_end_equal_to_start():
    with pytest.raises(ValidationError, match="strictly later"):
        CommitmentCreate(title="Lecture", start_time=START, end_time=START)


def test_create_rejects_end_before_start():
    with pytest.raises(ValidationError, match="strictly later"):
        CommitmentCreate(
            title="Lecture", start_time=START, end_time=START - timedelta(minutes=1)
        )


def test_create_accepts_minimal_positive_duration():
    end = START + timedelta(microseconds=1)
    c = CommitmentCreate(title="Blip", start_time=START, end_time=end)
    assert c.end_time == end


def test_create_parses_iso_datetime_strings():
    c = CommitmentCreate(
        title="Lecture",
        start_time="2026-10-27T09:00:00",
        end_time="2026-10-27T10:00:00",
    )
    assert c.start_time == START
    assert c.end_time == END


@pytest.mark.parametrize("missing", ["title", "start_time", "end_time"])
def test_create_requires_core_fields(missing):
    data = {"title": "Lecture", "start_time": START, "end_time": END}
    del data[missing]
    with pytest.raises(ValidationError):
        CommitmentCreate(**data)


# ---------------------------------------------------------------------------
# CommitmentUpdate
# ---------------------------------------------------------------------------


def test_update_empty_payload_is_valid():
    u = CommitmentUpdate()
    assert u.title is None
    assert u.start_time is None
    assert u.end_time is None
    assert u.model_dump(exclude_unset=True) == {}


def test_update_only_tracks_fields_that_were_sent():
    u = CommitmentUpdate(title="Renamed")
    assert u.model_dump(exclude_unset=True) == {"title": "Renamed"}


@pytest.mark.parametrize("field", ["title", "start_time", "end_time"])
def test_update_rejects_explicit_null(field):
    with pytest.raises(ValidationError, match="must not be null"):
        CommitmentUpdate(**{field: None})


def test_update_trims_title_whitespace():
    u = CommitmentUpdate(title="  Renamed  ")
    assert u.title == "Renamed"


@pytest.mark.parametrize("title", ["", "   "])
def test_update_rejects_empty_or_whitespace_title(title):
    with pytest.raises(ValidationError, match="must not be empty"):
        CommitmentUpdate(title=title)


def test_update_rejects_title_over_max_length():
    with pytest.raises(ValidationError, match=f"at most {TITLE_MAX}"):
        CommitmentUpdate(title="a" * (TITLE_MAX + 1))


def test_update_accepts_valid_time_pair():
    u = CommitmentUpdate(start_time=START, end_time=END)
    assert u.start_time == START
    assert u.end_time == END


def test_update_rejects_end_equal_to_start():
    with pytest.raises(ValidationError, match="strictly later"):
        CommitmentUpdate(start_time=START, end_time=START)


def test_update_rejects_end_before_start():
    with pytest.raises(ValidationError, match="strictly later"):
        CommitmentUpdate(start_time=END, end_time=START)


def test_update_single_time_field_skips_ordering_check():
    # With only one side provided, ordering is checked later against the
    # stored record, not by the schema.
    assert CommitmentUpdate(start_time=END).start_time == END
    assert CommitmentUpdate(end_time=START).end_time == START


# ---------------------------------------------------------------------------
# CommitmentRead
# ---------------------------------------------------------------------------


def test_read_builds_from_orm_like_object():
    created = datetime(2026, 10, 26, 12, 0)
    row = SimpleNamespace(
        id=7,
        title="Lecture",
        start_time=START,
        end_time=END,
        created_at=created,
        source=Source.MANUAL,
    )
    r = CommitmentRead.model_validate(row)
    assert r.id == 7
    assert r.title == "Lecture"
    assert r.start_time == START
    assert r.end_time == END
    assert r.created_at == created
    assert r.source is Source.MANUAL


def test_read_serializes_source_as_string_value():
    r = CommitmentRead(
        id=1,
        title="Lecture",
        start_time=START,
        end_time=END,
        created_at=START,
        source=Source.MANUAL,
    )
    assert r.model_dump(mode="json")["source"] == "manual"


def test_read_requires_all_fields():
    with pytest.raises(ValidationError):
        CommitmentRead(id=1, title="Lecture", start_time=START, end_time=END)
