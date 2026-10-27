"""Pure ICS parsing core for calendar import (Design 1, 4).

This package imports only the standard library and the ``tzdata`` package's
data files. It never imports SQLAlchemy, FastAPI, or ``app.data``, and never
reads the clock, the network, or environment state (Requirement 12.1-12.2).
"""

from app.ics.types import (
    ImportLimits,
    ImportRecord,
    InvalidCalendarError,
    ParseResult,
    SkippedItem,
    SkipReason,
)

__all__ = [
    "ImportLimits",
    "ImportRecord",
    "InvalidCalendarError",
    "ParseResult",
    "SkippedItem",
    "SkipReason",
]
