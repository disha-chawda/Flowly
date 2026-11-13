"""Unit tests for the CLDR Windows -> IANA table in ``app.ics.windows_zones``.

Targets are checked against the key list shipped in the ``tzdata`` package,
never the OS zone database (Design 4.4).

Validates: Requirements 3.3, 3.7, 3.8, 12.8
"""

from importlib.resources import files

from app.ics.windows_zones import CLDR_RELEASE, WINDOWS_TO_IANA


def _tzdata_keys() -> set[str]:
    return set(files("tzdata").joinpath("zones").read_text(encoding="utf-8").split())


def test_table_has_142_entries():
    assert len(WINDOWS_TO_IANA) == 142


def test_cldr_release_is_49():
    assert CLDR_RELEASE == "49"


def test_keys_are_lower_case():
    assert all(key == key.lower() for key in WINDOWS_TO_IANA)


def test_eastern_standard_time_maps_to_new_york():
    assert WINDOWS_TO_IANA["eastern standard time"] == "America/New_York"


def test_every_target_is_a_tzdata_key():
    missing = sorted(set(WINDOWS_TO_IANA.values()) - _tzdata_keys())
    assert missing == []
