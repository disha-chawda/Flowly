"""Time zone loading, ``TZID`` resolution, and conversion (Design 4.4).

Zones come only from the files shipped in the pinned ``tzdata`` package, never
from the operating system's zone database, so results depend only on the
``tzdata`` version (Requirement 4.8). The key list is the package's ``zones``
file, and each zone is built once with ``ZoneInfo.from_file`` and cached.

Standard library and ``tzdata`` data files only (Requirement 12.1-12.2).
"""

from datetime import datetime, timezone
from functools import lru_cache
from importlib.resources import files
from zoneinfo import ZoneInfo

from app.ics.windows_zones import WINDOWS_TO_IANA

UTC_KEY = "Etc/UTC"  # source zone for ``Z`` date-times


@lru_cache(maxsize=1)
def zone_keys() -> frozenset[str]:
    """Return every zone key listed in the ``tzdata`` package's ``zones`` file."""
    text = files("tzdata").joinpath("zones").read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


@lru_cache(maxsize=None)
def _load(key: str) -> ZoneInfo:
    # Only called with members of ``zone_keys()``, so ``key`` cannot escape the package.
    resource = files("tzdata.zoneinfo").joinpath(*key.split("/"))
    with resource.open("rb") as handle:
        return ZoneInfo.from_file(handle, key=key)


def get_zone(key: str) -> ZoneInfo | None:
    """Return the cached zone for an exact ``tzdata`` key, or ``None``."""
    if key not in zone_keys():
        return None
    return _load(key)


def utc_zone() -> ZoneInfo:
    """Return the ``Etc/UTC`` zone used as the source for ``Z`` date-times."""
    return _load(UTC_KEY)


def resolve_upload_zone(name: str) -> ZoneInfo | None:
    """Return the zone if ``name`` is exactly a ``tzdata`` key (Requirements 2.2, 3.9).

    Windows zone names are not accepted here.
    """
    return get_zone(name)


def resolve_tzid(value: str) -> ZoneInfo | None:
    """Resolve a ``TZID`` parameter value to a source zone (Requirement 3.3).

    After trimming surrounding whitespace and double quotes, an exact ``tzdata``
    key wins; otherwise the lower-cased value is looked up in the CLDR Windows
    table. Anything else returns ``None`` (``unknown_timezone``).
    """
    name = value.strip().strip('"').strip()
    zone = get_zone(name)
    if zone is not None:
        return zone
    mapped = WINDOWS_TO_IANA.get(name.lower())
    if mapped is None:
        return None
    return get_zone(mapped)


def to_local(wall: datetime, source: ZoneInfo | None, upload: ZoneInfo) -> datetime:
    """Convert a naive wall time in ``source`` to naive local time in ``upload``.

    A ``None`` source means a floating time, which is returned unchanged
    (Requirements 3.10, 4.6). ``fold=0`` applies RFC 5545 section 3.3.5: a time
    in a DST gap uses the offset before the gap, and a time in a fold is the
    first of the two instants (Requirements 4.1, 4.2).

    The instant goes through UTC first because ``astimezone`` returns its input
    unchanged when the target is the same tzinfo object. Zones are cached, so a
    gap time whose source and upload zone match would otherwise stay
    nonexistent instead of moving forward.
    """
    if source is None:
        return wall
    aware = wall.replace(tzinfo=source, fold=0)
    return aware.astimezone(timezone.utc).astimezone(upload).replace(tzinfo=None)
