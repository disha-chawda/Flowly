"""Windows time zone name to IANA zone table (Design 4.4).

Generated static data. ``TZID`` resolution looks up a lower-cased Windows name
here after an exact ``tzdata`` key match fails (Requirement 3.3). Nothing in
this module reads files or the network at runtime.

Source: the ``territory="001"`` (default territory) ``mapZone`` rows of
``common/supplemental/windowsZones.xml`` at CLDR git tag ``release-49``. That
file has 142 such rows, no two names collide when lower-cased, and each row
maps to exactly one zone. Targets are kept as CLDR writes them, including
legacy link names such as ``America/Buenos_Aires`` and ``America/Godthab``;
all of them are keys in ``tzdata`` 2026.5 (Requirement 3.8).

Regenerating for a new CLDR release:

1. Download ``common/supplemental/windowsZones.xml`` at the new tag, e.g.
   ``https://raw.githubusercontent.com/unicode-org/cldr/release-NN/common/supplemental/windowsZones.xml``.
2. Keep only the ``<mapZone ... territory="001" .../>`` rows, in file order.
3. For each row, map the lower-cased ``other`` attribute to the ``type``
   attribute. Check that no two names collide when lower-cased.
4. Update ``CLDR_RELEASE``, ``CLDR_SOURCE``, ``WINDOWS_ZONES_VERSION`` (the
   ``otherVersion`` attribute of ``<mapTimezones>``) and ``WINDOWS_TO_IANA``.
5. Run ``tests/unit/test_ics_windows_zones.py``, which checks every target
   against the pinned ``tzdata`` key list, and update its expected entry count.

Standard library only (Requirement 12.1).
"""

CLDR_RELEASE = "49"  # published 2026-10-22, git tag release-49
CLDR_SOURCE = (
    "https://github.com/unicode-org/cldr/blob/release-49/"
    "common/supplemental/windowsZones.xml"
)
WINDOWS_ZONES_VERSION = "7e11800"  # otherVersion attribute in that file

# 142 entries, keys lower-cased, in source file order.
WINDOWS_TO_IANA: dict[str, str] = {
    "dateline standard time": "Etc/GMT+12",
    "utc-11": "Etc/GMT+11",
    "aleutian standard time": "America/Adak",
    "hawaiian standard time": "Pacific/Honolulu",
    "marquesas standard time": "Pacific/Marquesas",
    "alaskan standard time": "America/Anchorage",
    "utc-09": "Etc/GMT+9",
    "pacific standard time (mexico)": "America/Tijuana",
    "utc-08": "Etc/GMT+8",
    "pacific standard time": "America/Los_Angeles",
    "us mountain standard time": "America/Phoenix",
    "mountain standard time (mexico)": "America/Mazatlan",
    "mountain standard time": "America/Denver",
    "british columbia standard time": "America/Vancouver",
    "yukon standard time": "America/Whitehorse",
    "alberta standard time": "America/Edmonton",
    "central america standard time": "America/Guatemala",
    "central standard time": "America/Chicago",
    "easter island standard time": "Pacific/Easter",
    "central standard time (mexico)": "America/Mexico_City",
    "canada central standard time": "America/Regina",
    "manitoba standard time": "America/Winnipeg",
    "sa pacific standard time": "America/Bogota",
    "eastern standard time (mexico)": "America/Cancun",
    "eastern standard time": "America/New_York",
    "haiti standard time": "America/Port-au-Prince",
    "cuba standard time": "America/Havana",
    "us eastern standard time": "America/Indianapolis",
    "turks and caicos standard time": "America/Grand_Turk",
    "paraguay standard time": "America/Asuncion",
    "atlantic standard time": "America/Halifax",
    "venezuela standard time": "America/Caracas",
    "central brazilian standard time": "America/Cuiaba",
    "sa western standard time": "America/La_Paz",
    "pacific sa standard time": "America/Santiago",
    "newfoundland standard time": "America/St_Johns",
    "tocantins standard time": "America/Araguaina",
    "e. south america standard time": "America/Sao_Paulo",
    "sa eastern standard time": "America/Cayenne",
    "argentina standard time": "America/Buenos_Aires",
    "greenland standard time": "America/Godthab",
    "montevideo standard time": "America/Montevideo",
    "magallanes standard time": "America/Punta_Arenas",
    "saint pierre standard time": "America/Miquelon",
    "bahia standard time": "America/Bahia",
    "utc-02": "Etc/GMT+2",
    "azores standard time": "Atlantic/Azores",
    "cape verde standard time": "Atlantic/Cape_Verde",
    "utc": "Etc/UTC",
    "gmt standard time": "Europe/London",
    "greenwich standard time": "Atlantic/Reykjavik",
    "sao tome standard time": "Africa/Sao_Tome",
    "morocco standard time": "Africa/Casablanca",
    "w. europe standard time": "Europe/Berlin",
    "central europe standard time": "Europe/Budapest",
    "romance standard time": "Europe/Paris",
    "central european standard time": "Europe/Warsaw",
    "w. central africa standard time": "Africa/Lagos",
    "jordan standard time": "Asia/Amman",
    "gtb standard time": "Europe/Bucharest",
    "middle east standard time": "Asia/Beirut",
    "egypt standard time": "Africa/Cairo",
    "e. europe standard time": "Europe/Chisinau",
    "syria standard time": "Asia/Damascus",
    "west bank standard time": "Asia/Hebron",
    "south africa standard time": "Africa/Johannesburg",
    "fle standard time": "Europe/Kiev",
    "israel standard time": "Asia/Jerusalem",
    "south sudan standard time": "Africa/Juba",
    "kaliningrad standard time": "Europe/Kaliningrad",
    "sudan standard time": "Africa/Khartoum",
    "libya standard time": "Africa/Tripoli",
    "namibia standard time": "Africa/Windhoek",
    "arabic standard time": "Asia/Baghdad",
    "turkey standard time": "Europe/Istanbul",
    "arab standard time": "Asia/Riyadh",
    "belarus standard time": "Europe/Minsk",
    "russian standard time": "Europe/Moscow",
    "e. africa standard time": "Africa/Nairobi",
    "iran standard time": "Asia/Tehran",
    "arabian standard time": "Asia/Dubai",
    "astrakhan standard time": "Europe/Astrakhan",
    "azerbaijan standard time": "Asia/Baku",
    "russia time zone 3": "Europe/Samara",
    "mauritius standard time": "Indian/Mauritius",
    "saratov standard time": "Europe/Saratov",
    "georgian standard time": "Asia/Tbilisi",
    "volgograd standard time": "Europe/Volgograd",
    "caucasus standard time": "Asia/Yerevan",
    "afghanistan standard time": "Asia/Kabul",
    "west asia standard time": "Asia/Tashkent",
    "ekaterinburg standard time": "Asia/Yekaterinburg",
    "pakistan standard time": "Asia/Karachi",
    "qyzylorda standard time": "Asia/Qyzylorda",
    "india standard time": "Asia/Calcutta",
    "sri lanka standard time": "Asia/Colombo",
    "nepal standard time": "Asia/Katmandu",
    "central asia standard time": "Asia/Bishkek",
    "bangladesh standard time": "Asia/Dhaka",
    "omsk standard time": "Asia/Omsk",
    "myanmar standard time": "Asia/Rangoon",
    "se asia standard time": "Asia/Bangkok",
    "altai standard time": "Asia/Barnaul",
    "w. mongolia standard time": "Asia/Hovd",
    "north asia standard time": "Asia/Krasnoyarsk",
    "n. central asia standard time": "Asia/Novosibirsk",
    "tomsk standard time": "Asia/Tomsk",
    "china standard time": "Asia/Shanghai",
    "north asia east standard time": "Asia/Irkutsk",
    "singapore standard time": "Asia/Singapore",
    "w. australia standard time": "Australia/Perth",
    "taipei standard time": "Asia/Taipei",
    "ulaanbaatar standard time": "Asia/Ulaanbaatar",
    "aus central w. standard time": "Australia/Eucla",
    "transbaikal standard time": "Asia/Chita",
    "tokyo standard time": "Asia/Tokyo",
    "north korea standard time": "Asia/Pyongyang",
    "korea standard time": "Asia/Seoul",
    "yakutsk standard time": "Asia/Yakutsk",
    "cen. australia standard time": "Australia/Adelaide",
    "aus central standard time": "Australia/Darwin",
    "e. australia standard time": "Australia/Brisbane",
    "aus eastern standard time": "Australia/Sydney",
    "west pacific standard time": "Pacific/Port_Moresby",
    "tasmania standard time": "Australia/Hobart",
    "vladivostok standard time": "Asia/Vladivostok",
    "lord howe standard time": "Australia/Lord_Howe",
    "bougainville standard time": "Pacific/Bougainville",
    "russia time zone 10": "Asia/Srednekolymsk",
    "magadan standard time": "Asia/Magadan",
    "norfolk standard time": "Pacific/Norfolk",
    "sakhalin standard time": "Asia/Sakhalin",
    "central pacific standard time": "Pacific/Guadalcanal",
    "russia time zone 11": "Asia/Kamchatka",
    "new zealand standard time": "Pacific/Auckland",
    "utc+12": "Etc/GMT-12",
    "fiji standard time": "Pacific/Fiji",
    "chatham islands standard time": "Pacific/Chatham",
    "utc+13": "Etc/GMT-13",
    "tonga standard time": "Pacific/Tongatapu",
    "samoa standard time": "Pacific/Apia",
    "line islands standard time": "Pacific/Kiritimati",
}
