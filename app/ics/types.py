"""Shared types for the FLOWLY calendar-import parsing core.

Pure data only: no database, clock, network, or FastAPI imports (Requirement
12.1-12.2). Every other ``app.ics`` module builds on these types (Design 4.1).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SkipReason(str, Enum):
    """Fixed set of reason codes for skipped entries (Requirement 10.4)."""

    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"
    MISSING_UID = "missing_uid"
    MISSING_START = "missing_start"
    INVALID_INTERVAL = "invalid_interval"
    ALL_DAY = "all_day"
    CANCELLED = "cancelled"
    UNKNOWN_TIMEZONE = "unknown_timezone"
    DST_OVERLAP = "dst_overlap"
    UNSUPPORTED_RECURRENCE = "unsupported_recurrence"
    OUTSIDE_WINDOW = "outside_window"
    PAST_EVENT = "past_event"
    MALFORMED_EVENT = "malformed_event"


@dataclass(frozen=True)
class ImportLimits:
    """Bounds applied to one import (Requirement 2.6, 6.1; Design 5.5)."""

    max_records: int = 2_000
    max_examined_dates: int = 200_000
    window_days: int = 180


@dataclass(frozen=True)
class ImportRecord:
    """One normalized event or occurrence, ready to match against storage.

    ``start`` and ``end`` are naive local times in the upload zone.
    """

    import_key: str
    uid: str
    title: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SkippedItem:
    """One entry of the summary's ``skipped_items`` list (Requirement 10.3).

    ``start`` is a naive local time in the upload zone, or ``None`` when it was
    not known at the point of the skip. ``count`` is 1 except for the single
    ``past_event`` aggregate (Requirement 10.5).
    """

    uid: str | None
    title: str | None
    start: datetime | None
    reason: SkipReason
    message: str
    count: int = 1


@dataclass(frozen=True)
class ParseResult:
    """Output of the parsing core: records plus parser skips, in order."""

    records: tuple[ImportRecord, ...]
    skipped: tuple[SkippedItem, ...]


class InvalidCalendarError(ValueError):
    """The whole file is rejected (Requirement 2.5-2.6).

    ``issue`` is the human-readable reason; the API layer puts it in the error
    envelope detail with ``field: "file"`` (Design 3.4).
    """

    def __init__(self, issue: str) -> None:
        super().__init__(issue)
        self.issue = issue
