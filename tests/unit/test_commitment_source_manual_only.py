"""Unit tests: ``CommitmentCreate`` accepts only ``source = manual``.

Adding ``Source.ICS_IMPORT`` must not let clients create imported rows through
``POST /commitments``; only the calendar import sets that source. Pure schema
tests, no database.

Validates: Requirements 9.1, 9.4, 16.1; Design §2, §8
"""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.enums import Source
from app.schemas.commitment import CommitmentCreate, CommitmentUpdate

START = datetime(2026, 10, 27, 9, 0)
END = START + timedelta(hours=1)


def test_source_enum_has_ics_import():
    assert Source.ICS_IMPORT.value == "ics_import"
    assert Source("ics_import") is Source.ICS_IMPORT


@pytest.mark.parametrize("source", ["ics_import", Source.ICS_IMPORT])
def test_create_rejects_ics_import_source(source):
    with pytest.raises(ValidationError) as exc_info:
        CommitmentCreate(title="Lecture", start_time=START, end_time=END, source=source)

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("source",)
    assert "source must be 'manual'" in errors[0]["msg"]


def test_create_accepts_explicit_manual_source():
    c = CommitmentCreate(title="Lecture", start_time=START, end_time=END, source="manual")
    assert c.source is Source.MANUAL


def test_create_defaults_source_to_manual():
    c = CommitmentCreate(title="Lecture", start_time=START, end_time=END)
    assert c.source is Source.MANUAL


def test_update_has_no_source_field():
    assert "source" not in CommitmentUpdate.model_fields
