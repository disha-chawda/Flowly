"""Unit tests for zone loading, ``TZID`` resolution, and conversion in ``app.ics.zones``.

Validates: Requirements 2.2, 3.2-3.5, 3.9, 3.10, 4.1, 4.2, 4.4, 4.6, 4.8
"""

from datetime import datetime

import pytest

from app.ics.zones import (
    resolve_tzid,
    resolve_upload_zone,
    to_local,
    utc_zone,
    zone_keys,
)


def _key(zone):
    return None if zone is None else zone.key


# Upload zone


def test_iana_upload_zone_is_accepted():
    assert _key(resolve_upload_zone("America/Toronto")) == "America/Toronto"


@pytest.mark.parametrize(
    "name", ["Eastern Standard Time", "america/toronto", " America/Toronto", ""]
)
def test_upload_zone_must_be_an_exact_key(name):
    assert resolve_upload_zone(name) is None


def test_zones_are_cached_per_key():
    assert resolve_upload_zone("America/Toronto") is resolve_upload_zone("America/Toronto")


def test_key_list_comes_from_tzdata():
    keys = zone_keys()
    assert {"America/Toronto", "America/New_York", "UTC", "Etc/UTC"} <= keys
    assert "Eastern Standard Time" not in keys


# TZID resolution


@pytest.mark.parametrize(
    "value",
    ['"Eastern Standard Time"', "eastern STANDARD time", "  Eastern Standard Time  "],
)
def test_windows_names_map_to_iana(value):
    assert _key(resolve_tzid(value)) == "America/New_York"


@pytest.mark.parametrize("value", ["America/Toronto", ' "America/Toronto" '])
def test_iana_tzid_resolves_exactly(value):
    assert _key(resolve_tzid(value)) == "America/Toronto"


def test_utc_resolves_through_the_key_list():
    assert _key(resolve_tzid("UTC")) == "UTC"


@pytest.mark.parametrize(
    "value",
    [
        "(UTC-05:00) Eastern Time (US & Canada)",
        "/mozilla.org/20050126_1/America/New_York",
        "../../etc/passwd",
        "",
    ],
)
def test_unmappable_tzid_is_none(value):
    assert resolve_tzid(value) is None


# Conversion


NEW_YORK = resolve_upload_zone("America/New_York")
TORONTO = resolve_upload_zone("America/Toronto")


def test_gap_time_moves_forward():
    wall = datetime(2026, 3, 8, 2, 30)
    assert to_local(wall, NEW_YORK, utc_zone()) == datetime(2026, 3, 8, 7, 30)
    assert to_local(wall, NEW_YORK, NEW_YORK) == datetime(2026, 3, 8, 3, 30)


def test_fold_time_is_the_first_instant():
    wall = datetime(2026, 11, 1, 1, 30)
    assert to_local(wall, NEW_YORK, utc_zone()) == datetime(2026, 11, 1, 5, 30)


def test_z_time_converts_to_upload_zone():
    wall = datetime(2026, 1, 15, 14, 0)
    assert to_local(wall, utc_zone(), TORONTO) == datetime(2026, 1, 15, 9, 0)


def test_result_is_naive():
    result = to_local(datetime(2026, 6, 1, 12, 0), NEW_YORK, TORONTO)
    assert result.tzinfo is None
    assert result == datetime(2026, 6, 1, 12, 0)


@pytest.mark.parametrize(
    "wall", [datetime(2026, 3, 8, 2, 30), datetime(2026, 11, 1, 1, 30)]
)
def test_floating_time_is_unchanged(wall):
    assert to_local(wall, None, TORONTO) == wall
    assert to_local(wall, None, utc_zone()) == wall
