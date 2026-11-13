"""Property tests for DST gap and fold resolution in ``app.ics.zones.to_local``.

Feature: calendar-import, Property 6: DST gap rule
Feature: calendar-import, Property 7: DST fold rule
Validates: Requirements 4.1, 4.2

Transitions are found by scanning every ``tzdata`` zone's UTC offset once a
day over one year and bisecting each change down to the second. A change to a
larger offset is a gap (wall times skipped); a change to a smaller offset is a
fold (wall times repeated). Wall times are then drawn inside each range.

Zones come from ``app.ics.zones`` (the pinned ``tzdata`` package), never from
the operating system's database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from hypothesis import example, given, settings, strategies as st

from app.ics.zones import get_zone, to_local, utc_zone, zone_keys

_YEAR = 2026
_SCAN_STEP = timedelta(days=1)
# A transition counts only if the offset is steady this long on each side, so
# a drawn wall time can't fall into a neighbouring transition's range.
_ISOLATION = timedelta(days=2)


@dataclass(frozen=True)
class Transition:
    key: str
    at: datetime  # aware UTC instant at which ``after`` takes effect
    before: timedelta  # UTC offset just before ``at``
    after: timedelta  # UTC offset from ``at`` on

    @property
    def length(self) -> timedelta:
        return abs(self.after - self.before)


def _offset(zone, instant: datetime) -> timedelta:
    return instant.astimezone(zone).utcoffset()


def _bisect(zone, lo: datetime, hi: datetime) -> datetime:
    """Return the first second in ``(lo, hi]`` whose offset differs from ``lo``'s."""
    start = _offset(zone, lo)
    while (hi - lo) > timedelta(seconds=1):
        span = int((hi - lo).total_seconds())
        mid = lo + timedelta(seconds=span // 2)
        if _offset(zone, mid) == start:
            lo = mid
        else:
            hi = mid
    return hi


def _scan(key: str) -> list[Transition]:
    zone = get_zone(key)
    found = []
    instant = datetime(_YEAR, 1, 1, tzinfo=timezone.utc)
    end = datetime(_YEAR + 1, 1, 1, tzinfo=timezone.utc)
    previous = _offset(zone, instant)
    while instant < end:
        following = instant + _SCAN_STEP
        current = _offset(zone, following)
        if current != previous:
            at = _bisect(zone, instant, following)
            before = _offset(zone, at - timedelta(seconds=1))
            after = _offset(zone, at)
            if (
                _offset(zone, at - _ISOLATION) == before
                and _offset(zone, at + _ISOLATION) == after
            ):
                found.append(Transition(key, at, before, after))
        previous = current
        instant = following
    return found


def _collect() -> tuple[dict[str, list[Transition]], dict[str, list[Transition]]]:
    gaps: dict[str, list[Transition]] = {}
    folds: dict[str, list[Transition]] = {}
    for key in sorted(zone_keys()):
        for transition in _scan(key):
            target = gaps if transition.after > transition.before else folds
            target.setdefault(key, []).append(transition)
    return gaps, folds


GAPS, FOLDS = _collect()
ALL_KEYS = sorted(zone_keys())


def _naive_utc(instant: datetime) -> datetime:
    return instant.astimezone(timezone.utc).replace(tzinfo=None)


def _shown(utc_wall: datetime, zone) -> datetime:
    """Return the naive wall time ``zone`` shows at a naive UTC instant."""
    return utc_wall.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)


@st.composite
def _inside(draw, table: dict[str, list[Transition]]):
    """Draw (transition, wall time inside its gap or fold, upload zone key)."""
    key = draw(st.sampled_from(sorted(table)))
    transition = draw(st.sampled_from(table[key]))
    seconds = draw(st.integers(0, int(transition.length.total_seconds()) - 1))
    # The range starts at the transition instant read with the smaller offset.
    low = min(transition.before, transition.after)
    wall = _naive_utc(transition.at) + low + timedelta(seconds=seconds)
    upload_key = draw(st.sampled_from(ALL_KEYS))
    return transition, wall, upload_key


_NEW_YORK_GAP = Transition(
    "America/New_York",
    datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc),
    timedelta(hours=-5),
    timedelta(hours=-4),
)
_NEW_YORK_FOLD = Transition(
    "America/New_York",
    datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),
    timedelta(hours=-4),
    timedelta(hours=-5),
)


def test_scan_finds_new_york_transitions():
    assert _NEW_YORK_GAP in GAPS["America/New_York"]
    assert _NEW_YORK_FOLD in FOLDS["America/New_York"]


# Feature: calendar-import, Property 6: DST gap rule
@settings(max_examples=200, deadline=None)
@given(case=_inside(GAPS))
@example(case=(_NEW_YORK_GAP, datetime(2026, 3, 8, 2, 30), "Etc/UTC"))
def test_gap_time_shifts_forward_by_gap_length(case):
    transition, wall, upload_key = case
    source = get_zone(transition.key)
    upload = get_zone(upload_key)

    # The drawn wall time is nonexistent: neither offset maps back to it.
    for offset in (transition.before, transition.after):
        assert _shown(wall - offset, source) != wall

    # Interpreted with the offset before the gap (Requirement 4.1).
    instant = wall - transition.before
    assert to_local(wall, source, utc_zone()) == instant
    assert to_local(wall, source, upload) == _shown(instant, upload)
    # In the source zone itself the wall time moves forward by the gap length.
    assert to_local(wall, source, source) == wall + transition.length


# Feature: calendar-import, Property 7: DST fold rule
@settings(max_examples=200, deadline=None)
@given(case=_inside(FOLDS))
@example(case=(_NEW_YORK_FOLD, datetime(2026, 11, 1, 1, 30), "Etc/UTC"))
def test_fold_time_resolves_to_earlier_instant(case):
    transition, wall, upload_key = case
    source = get_zone(transition.key)
    upload = get_zone(upload_key)

    # The drawn wall time is ambiguous: both offsets map back to it.
    first = wall - transition.before
    second = wall - transition.after
    assert _shown(first, source) == wall
    assert _shown(second, source) == wall
    assert first < second

    # Interpreted as the first of the two instants (Requirement 4.2).
    assert to_local(wall, source, utc_zone()) == first
    assert to_local(wall, source, upload) == _shown(first, upload)
    assert to_local(wall, source, source) == wall
