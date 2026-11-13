"""Pure ICS parsing core for calendar import (Design 1, 4).

This package imports only the standard library and the ``tzdata`` package's
data files. It never imports SQLAlchemy, FastAPI, or ``app.data``, and never
reads the clock, the network, or environment state (Requirement 12.1-12.2).
"""

from app.ics.content import (
    CalendarDocument,
    ContentProperty,
    EventComponent,
    read_calendar,
)
from app.ics.events import normalize_events
from app.ics.matching import ImportPlan, StoredImport, plan_import
from app.ics.types import (
    ImportLimits,
    ImportRecord,
    InvalidCalendarError,
    ParseResult,
    SkippedItem,
    SkipReason,
)
from app.ics.zones import resolve_upload_zone

__all__ = [
    "CalendarDocument",
    "ContentProperty",
    "EventComponent",
    "ImportLimits",
    "ImportPlan",
    "ImportRecord",
    "InvalidCalendarError",
    "ParseResult",
    "SkippedItem",
    "SkipReason",
    "StoredImport",
    "normalize_events",
    "plan_import",
    "read_calendar",
    "resolve_upload_zone",
]
