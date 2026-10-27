# Requirements Document: calendar-import

## Introduction

This feature lets the student upload an iCalendar (`.ics`) file and turn its events into FLOWLY
Commitments. It builds on the flowly-mvp codebase (`docs/requirements.md`, `docs/design.md`) and is
the first use of the `source` seam the MVP reserved for integrations (MVP Requirement 10).

Scope is deliberately narrow:

- Upload only. No URL/webcal fetching, no OAuth, no background sync.
- Events become Commitments. Nothing becomes a Task.
- Imported times are stored as naive local time in the student's browser time zone, the same
  convention manual commitments already follow.
- Re-importing the same file (or a newer export of the same calendar) updates existing imported
  commitments instead of duplicating them.
- Existing MVP behavior does not change.

## Glossary

- **ICS file**: A text file in iCalendar format (RFC 5545) containing a `VCALENDAR` with zero or
  more `VEVENT` components.
- **Event**: A `VEVENT` component in the ICS file.
- **UID**: The event's `UID` property, the identifier calendar apps keep stable across exports.
- **Upload zone**: The IANA time zone name sent with the upload, taken from the browser
  (`Intl.DateTimeFormat().resolvedOptions().timeZone`), e.g. `America/Toronto`.
- **Naive local time**: A `datetime` with `tzinfo=None` holding a wall-clock time in the upload
  zone. Manual commitments already use this convention: the frontend sends `datetime-local` values
  unchanged and `parseWallClock` in `frontend/app.js` displays them without shifting.
- **Zoned time**: An ICS date-time that names an absolute instant, either with a `Z` (UTC) suffix
  or with a `TZID` parameter.
- **Floating time**: An ICS date-time with neither a `Z` suffix nor a `TZID`. It means "this wall
  clock time wherever you are".
- **Windows time zone name**: A Windows time zone ID such as `Eastern Standard Time`, which
  Outlook and Exchange write as the `TZID` instead of an IANA name.
- **Zone mapping table**: A fixed table, built from the CLDR `windowsZones.xml` default-territory
  (`001`) entries, that maps each Windows time zone name to one IANA zone.
- **Source zone**: The IANA zone a zoned time is written in: the `TZID` zone (after mapping a
  Windows time zone name), or UTC for a `Z` time.
- **DST gap**: A range of wall-clock times skipped when clocks move forward (e.g. 02:00–03:00 on a
  spring-forward day). Times in it are *nonexistent*.
- **DST fold**: A range of wall-clock times that occurs twice when clocks move back (e.g.
  01:00–02:00 on a fall-back day). Times in it are *ambiguous*.
- **Recurring event / series**: An event with an `RRULE` (optionally `RDATE` / `EXDATE`).
- **Occurrence**: One concrete instance of a recurring event.
- **Override**: A `VEVENT` sharing a series' UID with a `RECURRENCE-ID`, replacing one occurrence.
- **Import key**: The identifier stored on an imported commitment so a later import can find it
  (Requirement 5).
- **Reference time**: The current instant for an import, passed in as an argument (never read from
  a clock inside the parsing core).
- **Import window**: The bounded date range in which recurring events are expanded. Its start is
  also the cutoff for past non-recurring events.
- **Past event**: A non-recurring event whose end, in naive local time, is at or before the import
  window start (Requirement 6.13).
- **Parsing core**: The pure, DB-free module that turns ICS content into normalized import records.
- **Import service**: The layer that matches import records against stored commitments and
  persists the result.
- **Error envelope**: The existing `{"error": {"type", "message", "details": [{"field", "issue"}]}}`
  shape built by `error_response` in `app/api/errors.py`.

## Requirements

### Requirement 1: Upload an ICS file

**User Story:** As a student, I want to upload my calendar export, so that my classes and shifts
appear as commitments without retyping them.

#### Acceptance Criteria

1. THE system SHALL expose a new endpoint that accepts `multipart/form-data` with two fields:
   `file` (the ICS file) and `timezone` (the upload zone).
2. THE system SHALL NOT fetch any URL, follow `ATTACH`/`URL` properties, or contact any external
   service while importing.
3. WHEN an import succeeds, THE system SHALL respond `200 OK` with the result summary
   (Requirement 10), even when every event was skipped.
4. THE system SHALL decide whether a file is valid from its content, not from its file name or the
   client-supplied content type.
5. THE endpoint SHALL be unauthenticated, matching the MVP's single-user, localhost-only security
   model (README "Security note").

### Requirement 2: Reject invalid requests and files

**User Story:** As a student, I want a clear error when my file can't be imported, so that I know
nothing was changed.

#### Acceptance Criteria

1. IF the `timezone` field is missing or blank, THEN THE system SHALL respond `422` with the error
   envelope and a detail with `field: "timezone"`.
2. IF `timezone` is not a key in the zone list of the pinned `tzdata` package, THEN THE system
   SHALL respond `422` with the error envelope and a detail with `field: "timezone"`. (The app reads
   zones from `tzdata` rather than the operating system so every machine uses the same rules.)
3. IF the `file` field is missing, THEN THE system SHALL respond `422` with the error envelope and
   a detail with `field: "file"`.
4. IF the file is larger than 5 MiB (5,242,880 bytes), THEN THE system SHALL respond `422` with the
   error envelope and SHALL stop reading the upload once the limit is exceeded.
5. IF the file is empty, is not valid UTF-8 (a leading UTF-8 BOM is allowed), or does not contain a
   well-formed `BEGIN:VCALENDAR` ... `END:VCALENDAR` block, THEN THE system SHALL respond `422`
   with the error envelope and a detail with `field: "file"`.
6. THE system SHALL limit an import to 2,000 import records, counted across the whole file. Every
   record the parsing core produces counts, whether it later turns out to be created, updated, or
   `unchanged`. Entries skipped for the reasons in Requirements 3–8, `duplicate` entries, and past
   events (`past_event`, Requirement 6.13) do not count.
   - THE system SHALL enforce the limit during recurrence expansion. It SHALL keep a running count
     as each imported non-recurring event and each in-window occurrence is produced, and SHALL stop
     parsing and expanding as soon as the count reaches 2,001. It SHALL NOT expand every series
     first and count afterwards.
   - Recurrence expansion SHALL NOT generate occurrences that start after the import window ends
     (Requirement 6.1), so an unbounded `RRULE` cannot run forever.
   - Recurrence expansion SHALL also stop after examining 200,000 candidate dates across the whole
     file, counting every recurrence period it steps through as at least one. This bounds rules
     that match rarely or never (e.g. `FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30`) and `COUNT` rules that
     start long before the window. WHEN this budget is exceeded, THE system SHALL respond `422`
     with the error envelope and a detail with `field: "file"`.
   - WHEN the limit is exceeded, THE system SHALL respond `422` with the error envelope and a detail
     with `field: "file"` whose `issue` states the 2,000 limit.
7. WHEN both `timezone` and `file` are invalid, THE envelope SHALL contain one detail for each.
   Exception: WHEN the request body exceeds the size limit, THE system stops reading before it
   reaches the `timezone` field, so the envelope SHALL contain only the `file` detail.
8. Every rejection SHALL use `type: "validation_error"` and an `issue` describing the reason.
9. WHEN a request is rejected, THE system SHALL NOT create, update, or delete any commitment.
10. THE system SHALL accept both CRLF and LF line endings and SHALL unfold folded content lines
    (RFC 5545 §3.1).

### Requirement 3: Convert times to naive local time in the upload zone

**User Story:** As a student, I want imported events to show at the same clock time my calendar app
shows, and to sit on the right day in my workload.

#### Acceptance Criteria

1. THE system SHALL store every imported `start_time` and `end_time` as naive local time in the
   upload zone.
2. WHEN a date-time has a `Z` suffix, THE system SHALL convert that UTC instant to the upload zone
   and drop the zone information.
3. WHEN a date-time has a `TZID`, THE system SHALL resolve it to a source zone in this order, after
   trimming surrounding whitespace and double quotes:
   1. If the value is a key in the pinned `tzdata` zone list, use that IANA zone.
   2. Otherwise, if the value matches a Windows time zone name in the zone mapping table
      (case-insensitive), use the mapped IANA zone. For example, `Eastern Standard Time` maps to
      `America/New_York`.
   3. Otherwise, the name cannot be mapped (Criterion 5).
4. WHEN the `TZID` resolves to a source zone, THE system SHALL interpret the date-time in that zone
   (applying Requirement 4 for DST gaps and folds), convert the instant to the upload zone, and drop
   the zone information.
5. IF a `TZID` cannot be mapped, including Windows display names such as
   `(UTC-05:00) Eastern Time (US & Canada)` and prefixed forms such as
   `/mozilla.org/20050126_1/America/New_York`, THEN THE system SHALL skip the event with reason
   `unknown_timezone`.
6. THE system SHALL use the IANA rules of the resolved zone and SHALL ignore `VTIMEZONE` components
   in the file.
7. THE zone mapping table SHALL be static data shipped in the parsing core, taken from a CLDR
   release stated in the code. The system SHALL NOT consult the Windows registry or any other
   operating-system zone data, so a file maps the same way on every OS.
8. Every IANA zone in the zone mapping table SHALL exist in the pinned `tzdata` package.
9. Windows time zone names SHALL be accepted only as `TZID` values inside the file. The upload's
   `timezone` field SHALL remain IANA-only (Requirement 2.2).
10. WHEN a date-time is floating, THE system SHALL store its wall-clock value unchanged, whatever
    the upload zone.
11. THE system SHALL ignore the calendar-level `X-WR-TIMEZONE` property. It SHALL NOT be used to
    interpret floating times or to resolve any `TZID`.
12. THE end time SHALL come from `DTEND`, or from `DTSTART + DURATION` when `DURATION` is given
    instead. THE system SHALL apply `DURATION` in the event's source zone before converting, with
    day and week parts nominal and hour, minute, and second parts exact (RFC 5545 §3.3.6).
13. WHEN `DTSTART` and `DTEND` use different zones, THE system SHALL convert each one separately.
14. WHEN the same file is re-imported with a different upload zone, THE system SHALL update the
    stored times of zoned events to the new zone, count them as `updated`, and leave floating
    events unchanged.

### Requirement 4: Deterministic handling of daylight-saving changes

**User Story:** As a student, I want events near a clock change to land at predictable times, so
that the same file always gives the same commitments.

#### Acceptance Criteria

1. WHEN a `TZID` date-time falls in a DST gap of its source zone, THE system SHALL interpret it with
   the UTC offset in effect before the gap (RFC 5545 §3.3.5). The wall-clock time therefore moves
   forward by the gap length; for example, 02:30 `America/Toronto` on a spring-forward day becomes
   03:30.
2. WHEN a `TZID` date-time falls in a DST fold of its source zone, THE system SHALL interpret it as
   the first of the two instants (the offset in effect before the change).
3. Criteria 1 and 2 SHALL also apply to every occurrence generated by recurrence expansion
   (Requirement 6).
4. WHEN converting an instant to the upload zone, THE system SHALL store the wall-clock time the
   upload zone shows at that instant. Inside a fold, two different instants can produce the same
   naive local time; the stored value does not record which one it was.
5. IF, after conversion, an event's end is not strictly later than its start (which can happen to
   events that cross a fold, such as 01:30 EDT to 01:15 EST), THEN THE system SHALL skip it with
   reason `dst_overlap`.
6. THE system SHALL NOT adjust floating times, even when they are nonexistent or ambiguous in the
   upload zone.
7. Stored lengths SHALL be wall-clock differences, the same as manual commitments. An event that
   spans a DST change will have a stored length that differs from its elapsed time by the size of
   the shift, and workload calculations SHALL use the stored length.
8. Given the same file, upload zone, reference time, and `tzdata` version, the import SHALL produce
   identical results on every machine and every run.

### Requirement 5: Store the import key so re-import updates instead of duplicating

**User Story:** As a student, I want to re-import an updated export of my calendar, so that changed
events are updated and I don't end up with duplicates.

#### Acceptance Criteria

1. THE Commitment model SHALL gain one new nullable column holding the import key.
2. Manually created commitments SHALL have a null import key; the column SHALL be unique among
   non-null values.
3. THE import key SHALL be the event's UID for a non-recurring event. For an occurrence of a
   recurring event, it SHALL combine the UID with the occurrence's original start.
4. THE original start in the key SHALL be written so that it does not depend on the upload zone:
   as the UTC instant for a zoned series, and as the wall-clock value written in the file for a
   floating series. Re-importing from a different upload zone therefore matches the same
   commitments.
5. WHEN an import record's key matches an existing commitment and its title, start, or end
   differ, THE system SHALL update that commitment in place (same `id`, same `created_at`) and
   count it as `updated`.
6. WHEN an import record's key matches an existing commitment and nothing differs, THE system
   SHALL leave it untouched and report it as skipped with reason `unchanged`.
7. WHEN an import record's key matches no existing commitment, THE system SHALL create a commitment
   and count it as `created`.
8. WHEN an imported commitment was edited in FLOWLY and the file is imported again, THE file's
   values SHALL win.
9. WHEN an imported commitment was deleted in FLOWLY and the file is imported again, THE system
   SHALL create it again.
10. THE system SHALL NOT delete any commitment because its event is missing from a later file
    (no sync-deletes in v1).
11. IF an event has no UID, THEN THE system SHALL skip it with reason `missing_uid`.
12. IF two records in the same file produce the same import key (other than an override replacing
    its occurrence), THEN THE system SHALL import the first and skip the rest with reason
    `duplicate`.
13. Importing the same file twice with the same upload zone and reference time SHALL produce
    `created = 0` and `updated = 0` on the second run.

### Requirement 6: Recurring events (v1 approach)

**User Story:** As a student, I want my weekly lectures imported as individual commitments, so that
each week's workload counts them.

**v1 approach:** expand each series into individual occurrences inside a bounded import window,
and store each occurrence as its own Commitment with its own import key. No recurrence rule is
stored; the Commitment model stays a single interval.

#### Acceptance Criteria

1. THE import window SHALL start at 00:00 on the reference time's date in the upload zone and end
   180 days later (exclusive).
2. THE system SHALL create one commitment for each occurrence whose start, after conversion to
   naive local time (and after any override), falls inside the import window. It SHALL ignore
   occurrences outside the window.
3. THE system SHALL expand a series in its source zone (`TZID` zone, UTC for a `Z` series, or
   floating for a floating series) and convert each occurrence separately. A 09:00
   `America/Toronto` weekly class therefore stays at 09:00 Toronto time across DST changes.
4. THE system SHALL support `RRULE` with `FREQ` of `DAILY`, `WEEKLY`, `MONTHLY`, or `YEARLY`, and
   the parts `INTERVAL`, `COUNT`, `UNTIL`, `BYDAY`, `BYMONTHDAY`, `BYMONTH`, and `WKST`.
5. THE system SHALL add `RDATE` occurrences and remove `EXDATE` occurrences.
6. WHEN an override (`RECURRENCE-ID`) exists for an occurrence, THE system SHALL use the override's
   title, start, and end for that occurrence while keeping the occurrence's import key. Moving a
   single occurrence therefore updates it on re-import.
7. WHEN an override's `RECURRENCE-ID` matches no generated occurrence, THE system SHALL import the
   override as its own occurrence with its own import key.
8. WHEN an override has `STATUS:CANCELLED`, THE system SHALL drop that occurrence and report it as
   skipped with reason `cancelled`.
9. IF an override uses `RANGE=THISANDFUTURE`, THEN THE system SHALL skip that override with reason
   `unsupported_recurrence` and import the series' occurrences without it.
10. IF an `RRULE` uses any other `FREQ` or part, or an event has more than one `RRULE`, THEN THE
    system SHALL skip the whole series with reason `unsupported_recurrence`.
11. IF a supported series has no occurrences inside the import window, THEN THE system SHALL report
    one skipped entry with reason `outside_window`.
12. Non-recurring events SHALL NOT be expanded or limited by the import window end. A non-recurring
    event that is ongoing or in the future (its end is after the import window start) SHALL be
    imported, however far in the future it starts.
13. WHEN a non-recurring event's end, after conversion to naive local time, is at or before the
    import window start, THE system SHALL skip it as a past event with reason `past_event`. An
    event that ends exactly at the window start is past, because it does not overlap the window.
    - Past events SHALL NOT count toward the 2,000-record limit (Requirement 2.6).
    - Past events SHALL be reported in aggregate, not one entry each (Requirement 10.5).
    - Checks that come earlier for an event (such as `missing_uid`, `all_day`, or
      `unknown_timezone`) take precedence, and those events are reported individually as before.
    - A commitment imported earlier whose event is now past SHALL be left unchanged
      (Requirement 5.10).
14. Recurring series SHALL NOT use the past-event rule. Their occurrences are expanded only within
    the import window (Criteria 1–2), so past occurrences stay outside it and are ignored.

**Moved-series limitation (v1):** an occurrence's import key is fixed by the series' UID and the
occurrence's *original* start. When the series itself moves, the moved occurrences get new keys.
This covers three cases:

- The series' `DTSTART` is changed for all occurrences (e.g. a class moves from 09:00 to 10:00).
- The calendar app ends the series and starts a new one with a new UID (e.g. Google Calendar's
  "this and following events" edit).
- A single event becomes recurring, or a series becomes a single event. The UID stays the same, but
  the key changes between the non-recurring form and the occurrence form.

15. WHEN a series has moved, THE system SHALL create commitments for the moved occurrences and SHALL
    leave the commitments from the old occurrences in place, because v1 never deletes
    (Criterion 5.10). The student SHALL delete the stale commitments by hand.
16. THE system SHALL NOT attempt to detect a moved series, and the summary SHALL NOT warn about one.
17. THE README SHALL describe this limitation (Requirement 17).

### Requirement 7: All-day events

**User Story:** As a student, I want all-day calendar entries (holidays, birthdays, reading week) not
to wipe out my available time.

**v1 approach:** skip all-day events and report them. A Commitment means "occupied, cannot work on
tasks"; importing an all-day entry would block the whole 16-hour workload window (MVP Requirement 7)
and set available time to zero for that day.

#### Acceptance Criteria

1. WHEN an event's `DTSTART` is a date (`VALUE=DATE`) rather than a date-time, THE system SHALL skip
   it with reason `all_day`.
2. THE all-day rule SHALL apply equally to non-recurring events, whole series, and overrides.

### Requirement 8: Event content mapping and per-event validation

**User Story:** As a student, I want imported commitments to look like ones I'd type myself, and I
want bad events skipped rather than failing the whole import.

#### Acceptance Criteria

1. THE commitment title SHALL be the event's `SUMMARY` with ICS text escapes decoded (`\,` `\;`
   `\n` `\\`) and surrounding whitespace trimmed.
2. WHEN `SUMMARY` is missing or blank, THE title SHALL be `Untitled event`.
3. WHEN the title is longer than 200 characters (`TITLE_MAX`), THE system SHALL truncate it to 200
   characters.
4. IF an event has no `DTSTART`, THEN THE system SHALL skip it with reason `missing_start`.
5. IF the end is not strictly later than the start before any time zone conversion (including a
   missing `DTEND` and `DURATION`, which RFC 5545 treats as zero length), THEN THE system SHALL skip
   it with reason `invalid_interval`.
6. WHEN an event has `STATUS:CANCELLED`, THE system SHALL skip it with reason `cancelled` and SHALL
   NOT delete a matching existing commitment.
7. IF an event cannot be interpreted (e.g. an unparseable date value), THEN THE system SHALL skip it
   with reason `malformed_event` and continue with the remaining events.
8. THE system SHALL ignore components other than `VEVENT` (`VTODO`, `VJOURNAL`, `VFREEBUSY`,
   `VALARM`, ...) and SHALL NOT count them in the summary.
9. Every commitment the import creates or updates SHALL satisfy the same title and interval rules as
   `CommitmentCreate` in `app/schemas/commitment.py`.

### Requirement 9: Source value for imported commitments

**User Story:** As a student, I want to tell imported commitments apart from ones I entered.

#### Acceptance Criteria

1. THE `Source` enum (`app/domain/enums.py`) SHALL gain the value `ics_import`.
2. THE system SHALL set `source = ics_import` on every commitment the import creates.
3. WHEN the import updates a commitment, its `source` SHALL remain `ics_import`.
4. `POST /commitments` SHALL continue to reject any `source` other than `manual` with a `422`
   error envelope, so manual creation behaves exactly as in the MVP.
5. WHEN an imported commitment is edited with `PUT /commitments/{id}`, THE system SHALL keep its
   `source` and import key.

### Requirement 10: Result summary

**User Story:** As a student, I want to see what the import did, so that I can trust it.

#### Acceptance Criteria

1. THE success response SHALL include integer counts `created`, `updated`, and `skipped`.
2. THE success response SHALL include the `timezone` used for the import.
3. THE success response SHALL include a `skipped_items` list. Each entry SHALL give the UID (or
   null), the title (or null), the start as naive local time in the upload zone (or null), a reason
   code, a human-readable message, and a `count` of the skips it stands for. Every entry except the
   past-event aggregate (Criterion 5) SHALL describe one skipped event, series, or occurrence and
   have `count = 1`.
4. Reason codes SHALL be drawn from a fixed set: `unchanged`, `duplicate`, `missing_uid`,
   `missing_start`, `invalid_interval`, `all_day`, `cancelled`, `unknown_timezone`, `dst_overlap`,
   `unsupported_recurrence`, `outside_window`, `past_event`, `malformed_event`.
5. WHEN one or more past events (Requirement 6.13) are skipped, THE system SHALL report them as a
   single `skipped_items` entry with reason `past_event`, `count` equal to the number of past
   events, null UID, title, and start, and a message naming the cutoff, e.g. "312 events ended
   before 2026-10-27 00:00 and were not imported." WHEN there are no past events, THE system SHALL
   NOT include this entry. The entry SHALL come after all other parser skips and before the
   `unchanged` entries.
6. `skipped` SHALL equal the sum of `count` over `skipped_items`.
7. Counts SHALL be per resulting commitment: each expanded occurrence counts once as created,
   updated, or skipped.
8. THE summary SHALL be deterministic: the same file, upload zone, stored state, and reference time
   SHALL yield the same summary in the same order.

### Requirement 11: Atomic persistence

**User Story:** As a student, I want an import to apply fully or not at all.

#### Acceptance Criteria

1. THE import service SHALL apply all creates and updates for one upload in a single transaction.
2. IF persistence fails partway, THEN THE system SHALL roll back and leave stored commitments as
   they were before the upload.
3. Per-event skips (Requirements 3–8) SHALL NOT fail the import.

### Requirement 12: Pure, property-testable parsing core

**User Story:** As a developer, I want the ICS logic isolated from the database, so that I can test
it thoroughly with hypothesis, the way `app/planning` is tested.

#### Acceptance Criteria

1. THE parsing core SHALL live in its own package, separate from `app/data`, `app/services`, and
   `app/api`, and SHALL NOT import SQLAlchemy, FastAPI, or any `app.data` module.
2. THE parsing core SHALL NOT read the clock, the network, or environment state, and SHALL NOT read
   files other than the time zone database. The reference time SHALL be an explicit, timezone-aware
   argument.
3. THE parsing core SHALL take ICS content, the upload zone, and the reference time, and return
   normalized import records (import key, UID, title, naive local start/end) plus skipped entries,
   or raise a single invalid-file error.
4. THE parsing core SHALL be deterministic: the same inputs SHALL yield equal outputs.
5. Matching records to stored commitments (created / updated / unchanged) SHALL be a pure function
   too, operating on plain values rather than ORM objects.
6. THE test suite SHALL include hypothesis property tests covering at least:
   - Round trip: generated events serialized to ICS and parsed back yield the expected naive local
     times in the upload zone and the same titles.
   - Zone equivalence: a `TZID` time and the equivalent `Z` instant produce the same naive local
     time.
   - Windows name equivalence: for every entry in the zone mapping table, a file using the Windows
     time zone name (in any letter case) produces the same records as the same file using the
     mapped IANA zone.
   - Unmappable names: any `TZID` that is neither an IANA key nor in the zone mapping table is
     skipped as `unknown_timezone`.
   - Floating invariance: floating times are identical for any two upload zones.
   - Key independence: import keys are identical for any two upload zones.
   - DST rules: gap times shift forward by the gap length, fold times resolve to the earlier
     instant, and fold-crossing events with `end <= start` are skipped as `dst_overlap`.
   - Recurrence: every occurrence lies inside the import window, keeps its wall-clock time in its
     source zone across DST changes, and has a unique import key.
   - Output invariants: every record has `end > start` and a title of 1–200 characters.
   - Past events: every imported non-recurring record ends after the window start; past events
     produce no records, don't count toward the 2,000 limit, and appear as one `past_event` entry
     whose `count` equals their number.
   - Idempotence: matching a file's records against the result of importing it yields no creates
     and no updates.
   - Robustness: arbitrary bytes either parse or raise the invalid-file error; nothing else escapes.
7. THE unit tests SHALL show that the 2,000 limit is enforced during expansion: a file whose
   series would expand past the limit is rejected, and the parsing core produces no more than
   2,001 records before stopping.
8. A unit test SHALL check that every IANA zone in the zone mapping table exists in the pinned
   `tzdata` zone list.
9. THE API tests SHALL cover the success response shape, each `422` rejection path (including the
   `timezone` field and the 2,000 limit), and re-import updating instead of duplicating.

### Requirement 13: Frontend import control

**User Story:** As a student, I want to import from the FLOWLY page, not only through the API docs.

#### Acceptance Criteria

1. THE Commitments section SHALL include a labelled file input accepting `.ics` and an Import
   button.
2. THE page SHALL send the browser's zone from `Intl.DateTimeFormat().resolvedOptions().timeZone`
   as the `timezone` field.
3. WHEN an import succeeds, THE page SHALL show the created / updated / skipped counts and the zone
   used, then refresh the commitments list and dashboard.
4. THE page SHALL group skipped items by reason. Each group SHALL show a readable reason label and
   the group's count (the sum of `count` over its entries), and SHALL be collapsed by default.
   Expanding a group SHALL list its entries (title, start, and message; the `past_event` entry
   shows only its message).
5. WHEN an import is rejected, THE page SHALL show the envelope's `file` or `timezone` issue using
   the existing form-error pattern.
6. Commitments with `source = ics_import` SHALL be visibly labelled as imported.
7. THE control, including the skipped-item groups, SHALL be keyboard-operable and announce results
   through the existing status region.

### Requirement 14: Database change requires recreating the dev database

**User Story:** As a developer, I want to know the upgrade step, so that the app doesn't break on my
existing `flowly.db`.

#### Acceptance Criteria

1. THE README SHALL include the database upgrade note listed in Requirement 17.
2. THE feature SHALL NOT introduce a migration tool in v1.
3. WHEN the app starts against a `commitments` table that lacks the new column, THE system SHALL
   fail at startup with a message naming the missing column and the fix, rather than failing later
   on individual requests.
4. Tests SHALL keep using temporary databases and SHALL NOT depend on `flowly.db`.

### Requirement 15: Dependencies

**User Story:** As a developer, I want every new package pinned, so that installs are reproducible.

#### Acceptance Criteria

1. THE feature SHALL add `python-multipart==0.0.32` to `requirements.txt`. FastAPI needs it to parse
   `multipart/form-data` uploads.
2. THE feature SHALL add `tzdata==2026.5` to `requirements.txt`. Windows has no system IANA time
   zone database, so `zoneinfo` depends on this package there, and pinning it fixes the DST rules
   that Requirement 4.8 relies on.
3. THE feature SHALL add `python-dateutil==2.9.0.post0` to `requirements.txt`. It is used only in
   tests, as a reference implementation to check the recurrence expander against; application
   code SHALL NOT import it.

### Requirement 16: No change to MVP behavior

**User Story:** As a student, I want everything that worked before to keep working the same way.

#### Acceptance Criteria

1. THE existing test suite (`tests/unit`, `tests/api`) SHALL pass without modification.
2. Request and response shapes of the existing `/tasks`, `/commitments`, and `/dashboard/*`
   endpoints SHALL stay the same; the import key SHALL NOT be added to `CommitmentRead`.
3. Manual commitment times SHALL keep their current meaning and SHALL NOT be converted.
4. Tasks SHALL NOT be affected by this feature.
5. Workload and daily-plan calculations SHALL treat imported commitments exactly like manual ones.

### Requirement 17: README documentation

**User Story:** As a student, I want the import rules written down, so that I know what an import
will and won't change before I run it.

#### Acceptance Criteria

1. THE README SHALL have a "Calendar import" section that covers each item below.
2. **How to import:** the Commitments section control, the accepted file type, and the 5 MiB and
   2,000-record limits.
3. **Time zones:**
   - Times are stored in the browser's time zone.
   - `Z` and `TZID` times are converted to that zone; floating times are kept as written.
   - The calendar-level `X-WR-TIMEZONE` property is ignored, so floating times are not shifted by it.
   - `VTIMEZONE` definitions in the file are ignored in favor of IANA rules.
   - Windows time zone names are mapped to IANA zones, and events whose `TZID` cannot be mapped are
     skipped.
   - Re-importing from a different time zone moves zoned events to the new zone.
4. **Overwrite rules:**
   - Re-import matches events by UID (and original start for recurring occurrences).
   - The file's title, start, and end overwrite edits made in FLOWLY.
   - Imported commitments deleted in FLOWLY come back on the next import.
   - Events removed from the file, or marked cancelled, are not deleted from FLOWLY.
   - Manual commitments are never changed by an import.
5. **Recurring events:** occurrences are imported for the next 180 days only; the supported `RRULE`
   subset; and the moved-series limitation from Requirement 6.
   **Past events:** non-recurring events that ended before today (the import window start) are
   skipped and listed as one "past events" line with a count; ongoing and future events are
   imported however far ahead they are; past events don't count toward the 2,000-record limit; and
   commitments imported earlier are kept when their event becomes past.
6. **All-day events** are skipped.
7. **Database upgrade:** this feature adds a column to `commitments`; `create_all` does not alter
   existing tables; the dev database (`flowly.db`) must be deleted and recreated, which erases its
   existing data.

## Resolved Decisions

1. **Time convention:** imported times are stored as naive local time in the browser's IANA zone,
   matching manual commitments (Requirement 3). Zoned times are converted; floating times are kept
   as written; a missing or invalid zone is rejected with `422`.
2. **File limit:** 5 MiB (Requirement 2.4).
3. **Windows time zone names** are mapped to IANA zones through a CLDR-derived table; only names
   that cannot be mapped are skipped (Requirement 3.3–3.9).
4. **The 2,000-record limit** is counted across the file and enforced while expanding, stopping at
   the first record over the limit (Requirement 2.6).
5. **Old recurring series:** expansion starts at the import window for rules without `COUNT`;
   `COUNT` rules start at `DTSTART`. A 200,000-date budget per file bounds all expansion
   (Requirement 2.6; design §5).
6. **Parser and zone data:** a hand-written parser and recurrence expander; the Windows zone table
   comes from CLDR release 49 (design §4, §5).

## Open Questions

1. **All-day events** are skipped in v1 (Requirement 7). The alternative is importing them as
   00:00–24:00 commitments, which zeroes that day's available time.
2. **Remaining limits** (2,000 records, 180-day window) are initial values; confirm or adjust.

