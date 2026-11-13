"""Property value parsing for the ICS core (Design 4.3).

Each parser turns one raw property value (as written after the ``:`` of a
content line) into a typed value, or raises ``ValueParseError``. That error is
internal to ``app.ics``: the event pipeline catches it and skips the event as
``malformed_event`` (Requirement 8.7). It is deliberately not re-exported from
the package and never reaches the API layer.

Sections:

- Errors
- DATE and DATE-TIME
- DURATION
- TEXT
- RRULE: ``parse_rrule`` raises ``ValueParseError`` for a malformed rule and
  ``UnsupportedRuleError`` for a rule outside the supported subset (Design 5.2)

Standard library only (Requirement 12.1).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TypeVar

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ValueParseError(ValueError):
    """A property value could not be parsed; the event becomes ``malformed_event``."""


# ---------------------------------------------------------------------------
# DATE and DATE-TIME
# ---------------------------------------------------------------------------

# ASCII digits only: ``\d`` would also accept other Unicode digits.
_DATE_RE = re.compile(r"([0-9]{4})([0-9]{2})([0-9]{2})")
_DATE_TIME_RE = re.compile(r"([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})(Z?)")


@dataclass(frozen=True)
class DateTimeValue:
    """A DATE-TIME value as written in the file.

    ``wall`` is always naive. ``utc`` is true for a ``Z`` suffix; otherwise the
    value is floating or, with a ``TZID`` parameter, in that zone. Resolving the
    zone is the job of ``zones.py`` (Design 4.4).
    """

    wall: datetime
    utc: bool


def parse_date(value: str) -> date:
    """Parse a DATE value (``YYYYMMDD``)."""
    match = _DATE_RE.fullmatch(value.strip())
    if match is None:
        raise ValueParseError(f"'{value}' is not a DATE value (YYYYMMDD).")
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueParseError(f"'{value}' is not a valid date.") from None


def parse_date_time(value: str) -> DateTimeValue:
    """Parse a DATE-TIME value (``YYYYMMDDTHHMMSS`` with optional ``Z``).

    The fields are validated by ``datetime`` itself, so impossible dates and a
    leap second (``60``) are rejected.
    """
    match = _DATE_TIME_RE.fullmatch(value.strip())
    if match is None:
        raise ValueParseError(f"'{value}' is not a DATE-TIME value (YYYYMMDDTHHMMSS[Z]).")
    *fields, zulu = match.groups()
    year, month, day, hour, minute, second = (int(part) for part in fields)
    try:
        wall = datetime(year, month, day, hour, minute, second)
    except ValueError:
        raise ValueParseError(f"'{value}' is not a valid date-time.") from None
    return DateTimeValue(wall=wall, utc=zulu == "Z")


def parse_date_or_date_time(value: str, value_type: str | None = None) -> date | DateTimeValue:
    """Parse a property that may hold a DATE or a DATE-TIME (``DTSTART``, ``EXDATE``, ...).

    ``value_type`` is the property's ``VALUE`` parameter, if any. With
    ``VALUE=DATE`` the value must be a DATE; with ``VALUE=DATE-TIME`` it must be
    a DATE-TIME. Without the parameter the form of the value decides: a bare
    ``YYYYMMDD`` is a DATE. A ``date`` result marks an all-day ``DTSTART``
    (Requirement 7.1).
    """
    kind = value_type.strip().upper() if value_type is not None else None
    if kind == "DATE":
        return parse_date(value)
    if kind == "DATE-TIME":
        return parse_date_time(value)
    if kind is not None:
        raise ValueParseError(f"VALUE={value_type} is not a DATE or DATE-TIME.")
    if _DATE_RE.fullmatch(value.strip()):
        return parse_date(value)
    return parse_date_time(value)


def parse_date_or_date_time_list(
    value: str, value_type: str | None = None
) -> tuple[date | DateTimeValue, ...]:
    """Parse a comma-separated list of DATE or DATE-TIME values (``EXDATE``, ``RDATE``).

    Every item must parse, and an empty list or empty item is an error.
    """
    items = value.split(",")
    if any(not item.strip() for item in items):
        raise ValueParseError(f"'{value}' contains an empty date value.")
    return tuple(parse_date_or_date_time(item, value_type) for item in items)


# ---------------------------------------------------------------------------
# DURATION
# ---------------------------------------------------------------------------

_DURATION_WEEKS_RE = re.compile(r"([+-]?)P([0-9]+)W")
_DURATION_DAY_TIME_RE = re.compile(
    r"([+-]?)P(?:([0-9]+)D)?(T(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?)?"
)


@dataclass(frozen=True)
class DurationValue:
    """A DURATION split into its nominal and exact parts (RFC 5545 3.3.6).

    ``nominal_days`` (weeks are stored as 7 days each) is added to the start's
    wall time; ``exact`` is then added to the resolved instant (Design 4.4).
    A negative duration has both parts negated.
    """

    nominal_days: int
    exact: timedelta


def parse_duration(value: str) -> DurationValue:
    """Parse ``[+-]PnW`` or ``[+-]P[nD][T[nH][nM][nS]]``.

    At least one component is required, and a ``T`` must be followed by at
    least one of ``H``, ``M``, ``S``. So ``P`` and ``PT`` are invalid.
    """
    text = value.strip()
    weeks_match = _DURATION_WEEKS_RE.fullmatch(text)
    if weeks_match is not None:
        sign, weeks = weeks_match.groups()
        days, hours, minutes, seconds = None, None, None, None
    else:
        match = _DURATION_DAY_TIME_RE.fullmatch(text)
        if match is None:
            raise ValueParseError(f"'{value}' is not a DURATION value.")
        sign, days, time_part, hours, minutes, seconds = match.groups()
        weeks = None
        if days is None and time_part is None:
            raise ValueParseError(f"'{value}' is a DURATION with no components.")
        if time_part is not None and hours is None and minutes is None and seconds is None:
            raise ValueParseError(f"'{value}' has 'T' with no hours, minutes, or seconds.")
    try:
        nominal_days = 7 * int(weeks or 0) + int(days or 0)
        exact = timedelta(
            hours=int(hours or 0), minutes=int(minutes or 0), seconds=int(seconds or 0)
        )
        # Reject values that can never be applied to a datetime.
        timedelta(days=nominal_days) + exact
    except (OverflowError, ValueError):
        # ValueError: digit strings beyond Python's int conversion limit.
        raise ValueParseError(f"'{value}' is too large for a DURATION.") from None
    if sign == "-":
        return DurationValue(nominal_days=-nominal_days, exact=-exact)
    return DurationValue(nominal_days=nominal_days, exact=exact)


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------

_TEXT_ESCAPES = {"\\": "\\", ";": ";", ",": ",", "n": "\n", "N": "\n"}


def unescape_text(value: str) -> str:
    """Decode RFC 5545 TEXT escapes: ``\\\\``, ``\\;``, ``\\,``, ``\\n``/``\\N``.

    TEXT accepts any value (Design 4.3), so this never raises. A backslash not
    followed by one of those characters is kept as written, which tolerates
    exporters that write ``\\:`` or a trailing backslash.
    """
    if "\\" not in value:
        return value
    out: list[str] = []
    index, length = 0, len(value)
    while index < length:
        char = value[index]
        if char == "\\" and index + 1 < length and value[index + 1] in _TEXT_ESCAPES:
            out.append(_TEXT_ESCAPES[value[index + 1]])
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# RRULE
# ---------------------------------------------------------------------------


class UnsupportedRuleError(ValueError):
    """A well-formed ``RRULE`` outside the supported subset (Design 5.2).

    The event pipeline maps it to ``unsupported_recurrence`` and skips the whole
    series. It is deliberately not a ``ValueParseError``, so a handler for
    malformed values cannot swallow it by accident.
    """


class Frequency(str, Enum):
    """The supported ``FREQ`` values (Requirement 6.4)."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


# Weekday numbers match ``date.weekday()``: Monday is 0, Sunday is 6.
WEEKDAYS: dict[str, int] = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclass(frozen=True)
class WeekdayNum:
    """One ``BYDAY`` item: a weekday with an optional ordinal (``2MO``, ``-1FR``)."""

    weekday: int
    ordinal: int | None = None


@dataclass(frozen=True)
class RuleSpec:
    """A validated ``RRULE`` in the supported subset (Design 5.2, 5.4).

    List parts keep the order written in the file; an empty tuple means the
    part is absent. ``until`` is still in the file's form; converting it to the
    series' source wall time is the event pipeline's job (Design 5.4).
    """

    freq: Frequency
    interval: int = 1
    count: int | None = None
    until: date | DateTimeValue | None = None
    byday: tuple[WeekdayNum, ...] = ()
    bymonthday: tuple[int, ...] = ()
    bymonth: tuple[int, ...] = ()
    wkst: int = 0


_SUPPORTED_PARTS = frozenset(
    {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"}
)
_PART_NAME_RE = re.compile(r"[A-Za-z0-9-]+")
_UNSIGNED_RE = re.compile(r"[0-9]+")
_MONTHDAY_RE = re.compile(r"([+-]?)([0-9]{1,2})")
_WEEKDAY_NUM_RE = re.compile(r"(?:([+-]?)([0-9]{1,2}))?([A-Z]{2})")


def parse_rrule(value: str) -> RuleSpec:
    """Parse and validate an ``RRULE`` value (``NAME=VALUE`` parts joined by ``;``).

    Raises ``ValueParseError`` for a malformed rule (``malformed_event``) and
    ``UnsupportedRuleError`` for a valid rule outside the supported subset
    (``unsupported_recurrence``). Checks run in this order, and the first
    failure decides the outcome:

    1. Syntax: every part is ``NAME=VALUE`` with a non-empty value, and no part
       is repeated (malformed).
    2. ``FREQ`` is present (malformed).
    3. ``FREQ`` is one of the four supported values and every part is in the
       supported set (unsupported). Values of unsupported parts are not checked.
    4. Values of the supported parts parse and are in range (malformed).
    5. ``COUNT`` and ``UNTIL`` are not both given (malformed).
    6. No ordinal ``BYDAY`` with ``DAILY``/``WEEKLY`` and no ``BYMONTHDAY`` with
       ``WEEKLY`` (unsupported); ordinals are within +-1..5 for ``MONTHLY`` and
       for ``YEARLY`` with ``BYMONTH`` (malformed).

    Part names and enumerated values (``FREQ``, ``BYDAY``, ``WKST``) are
    case-insensitive (RFC 5545 3.1). ``UNTIL`` uses the DATE and DATE-TIME
    parsers above unchanged.
    """
    parts: dict[str, str] = {}
    for part in value.strip().split(";"):
        name, sep, part_value = part.partition("=")
        if not sep or not _PART_NAME_RE.fullmatch(name) or not part_value:
            raise ValueParseError(f"'{part}' is not a NAME=VALUE recurrence rule part.")
        key = name.upper()
        if key in parts:
            raise ValueParseError(f"The recurrence rule part {key} is repeated.")
        parts[key] = part_value

    if "FREQ" not in parts:
        raise ValueParseError("The recurrence rule has no FREQ.")
    try:
        freq = Frequency(parts["FREQ"].upper())
    except ValueError:
        raise UnsupportedRuleError(f"FREQ={parts['FREQ']} is not supported.") from None
    unknown = sorted(set(parts) - _SUPPORTED_PARTS)
    if unknown:
        raise UnsupportedRuleError(f"The recurrence rule part {unknown[0]} is not supported.")

    interval = _parse_positive("INTERVAL", parts.get("INTERVAL", "1"))
    count = _parse_positive("COUNT", parts["COUNT"]) if "COUNT" in parts else None
    until = parse_date_or_date_time(parts["UNTIL"]) if "UNTIL" in parts else None
    byday = _parse_list("BYDAY", parts.get("BYDAY"), _parse_weekday_num)
    bymonthday = _parse_list("BYMONTHDAY", parts.get("BYMONTHDAY"), _parse_monthday)
    bymonth = _parse_list("BYMONTH", parts.get("BYMONTH"), _parse_month)
    wkst = _parse_weekday(parts["WKST"]) if "WKST" in parts else 0

    if count is not None and until is not None:
        raise ValueParseError("A recurrence rule cannot have both COUNT and UNTIL.")

    has_ordinal = any(item.ordinal is not None for item in byday)
    if has_ordinal and freq in (Frequency.DAILY, Frequency.WEEKLY):
        raise UnsupportedRuleError(f"BYDAY with an ordinal is not supported with FREQ={freq.value}.")
    if bymonthday and freq is Frequency.WEEKLY:
        raise UnsupportedRuleError("BYMONTHDAY is not supported with FREQ=WEEKLY.")
    if has_ordinal and (freq is Frequency.MONTHLY or bymonth):
        # Within a month there are at most five of any weekday. YEARLY without
        # BYMONTH counts within the year, and +-53 was checked per item.
        for item in byday:
            if item.ordinal is not None and abs(item.ordinal) > 5:
                raise ValueParseError(
                    f"BYDAY ordinal {item.ordinal} is out of range; it must be within +-1..5 here."
                )

    return RuleSpec(
        freq=freq,
        interval=interval,
        count=count,
        until=until,
        byday=byday,
        bymonthday=bymonthday,
        bymonth=bymonth,
        wkst=wkst,
    )


def _parse_positive(name: str, text: str) -> int:
    """Parse ``INTERVAL`` or ``COUNT``: unsigned digits, at least 1."""
    if not _UNSIGNED_RE.fullmatch(text):
        raise ValueParseError(f"{name}={text} is not a whole number.")
    try:
        number = int(text)
    except ValueError:
        # Digit strings beyond Python's int conversion limit.
        raise ValueParseError(f"{name}={text} is too large.") from None
    if number < 1:
        raise ValueParseError(f"{name} must be at least 1.")
    return number


def _parse_list(name: str, text: str | None, parse_item: Callable[[str], _T]) -> tuple[_T, ...]:
    """Parse a comma-separated part; an empty item is malformed."""
    if text is None:
        return ()
    items = text.split(",")
    if any(not item for item in items):
        raise ValueParseError(f"{name}={text} contains an empty item.")
    return tuple(parse_item(item) for item in items)


def _parse_weekday(text: str) -> int:
    weekday = WEEKDAYS.get(text.upper())
    if weekday is None:
        raise ValueParseError(f"'{text}' is not a weekday (MO, TU, WE, TH, FR, SA, SU).")
    return weekday


def _parse_weekday_num(text: str) -> WeekdayNum:
    """Parse ``[+-][n]WD`` with ``n`` within 1..53 (Design 5.2)."""
    match = _WEEKDAY_NUM_RE.fullmatch(text.upper())
    if match is None:
        raise ValueParseError(f"BYDAY item '{text}' is not a weekday with an optional ordinal.")
    sign, digits, weekday = match.groups()
    if digits is None:
        return WeekdayNum(weekday=_parse_weekday(weekday))
    ordinal = int(digits)
    if not 1 <= ordinal <= 53:
        raise ValueParseError(f"BYDAY ordinal in '{text}' must be within +-1..53.")
    return WeekdayNum(weekday=_parse_weekday(weekday), ordinal=-ordinal if sign == "-" else ordinal)


def _parse_monthday(text: str) -> int:
    """Parse a ``BYMONTHDAY`` item: +-1..31, never 0."""
    match = _MONTHDAY_RE.fullmatch(text)
    if match is None or not 1 <= int(match.group(2)) <= 31:
        raise ValueParseError(f"BYMONTHDAY item '{text}' must be within +-1..31.")
    day = int(match.group(2))
    return -day if match.group(1) == "-" else day


def _parse_month(text: str) -> int:
    """Parse a ``BYMONTH`` item: 1..12, unsigned."""
    if not re.fullmatch(r"[0-9]{1,2}", text) or not 1 <= int(text) <= 12:
        raise ValueParseError(f"BYMONTH item '{text}' must be within 1..12.")
    return int(text)
