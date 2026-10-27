# Implementation Plan: calendar-import

## Overview

This plan implements `.ics` upload for FLOWLY as specified in `requirements.md` and `design.md` in
this folder, on top of the existing flowly-mvp codebase.

Work proceeds strictly bottom-up so every step builds on the last with no orphaned code:
dependency pins and install → `Source` enum, `import_key` column, and startup schema check → the
pure `app/ics/` core one module at a time (types → values → recurrence → zones → content → events
→ matching), each paired with its tests → repository and service → API endpoint → frontend →
README → final checkpoint.

The recurrence expander is built and checked against `python-dateutil` (Property 9) before
anything else depends on it, because the design replaces `dateutil` with a hand-written expander
(Design §5.1) and every later recurrence test assumes the expander is right.

Property-based tests use `hypothesis` with a minimum of 100 iterations each, and every property
test is tagged with a comment of the form `Feature: calendar-import, Property {number}:
{property_text}` (Design Correctness Properties). All tests run with no network access: the CLDR
table is generated once during task 6.1 and committed as data.

Ground rules for every task:

- Existing tests in `tests/unit/` and `tests/api/` are not modified (Requirement 16.1). New tests go
  in new files.
- New tests use temporary or in-memory SQLite databases and never touch `flowly.db`
  (Requirement 14.4).
- `app/ics/` never imports SQLAlchemy, FastAPI, `app.data`, or `dateutil` (Requirements 12.1,
  15.3).
- Do not delete the developer's `flowly.db`. When a task makes the old file incompatible, tell the
  user to recreate it.

## Tasks

- [x] 1. Pin and install dependencies
  - [x] 1.1 Add the three pins to `requirements.txt` and install
    - Append `python-multipart==0.0.32`, `tzdata==2026.5`, and `python-dateutil==2.9.0.post0` to `requirements.txt`; leave the existing pins unchanged.
    - Install with `python -m pip install -r requirements.txt` and confirm `import python_multipart`, `import tzdata`, and `import dateutil` succeed, and that `tzdata`'s version is `2026.5`.
    - Run the existing suite (`python -m pytest`) to confirm the upgrade from the installed `tzdata` 2023.3 breaks nothing.
    - _Requirements: 15.1, 15.2, 15.3, 16.1; Design §11_

- [ ] 2. Extend the domain, model, and startup checks
  - [x] 2.1 Add `Source.ICS_IMPORT` and keep `POST /commitments` manual-only
    - Add `ICS_IMPORT = "ics_import"` to `Source` in `app/domain/enums.py`.
    - In the same commit, add the `_manual_only` `field_validator("source")` to `CommitmentCreate` in `app/schemas/commitment.py`, so no commit lets clients create `ics_import` rows.
    - New test file `tests/unit/test_commitment_source_manual_only.py`: `CommitmentCreate(source="ics_import")` raises `ValidationError` with "source must be 'manual'"; `source="manual"` and the default still pass; `CommitmentUpdate` has no `source` field.
    - _Requirements: 9.1, 9.4, 16.1; Design §2, §8_

  - [ ] 2.2 Add `Commitment.import_key`
    - Add `import_key: Mapped[str | None] = mapped_column(nullable=True, unique=True, default=None)` to `Commitment` in `app/data/models.py`. Do not add it to `CommitmentRead`.
    - New test file `tests/unit/test_commitment_import_key.py` (in-memory SQLite): many rows with `NULL` keys are allowed; two rows with the same non-null key raise `IntegrityError`; `CommitmentRead.model_fields` has no `import_key`.
    - After this task the developer's existing `flowly.db` no longer matches the model. Tell the user it must be recreated; don't delete it.
    - _Requirements: 5.1, 5.2, 16.2; Design §2_

  - [ ] 2.3 Add the startup schema check
    - Implement `check_schema(engine)` in `app/data/database.py` as in Design §7, and call it in `lifespan` in `app/main.py` right after `create_all()`.
    - New test file `tests/unit/test_schema_check.py`: against a temporary SQLite file whose `commitments` table was created without `import_key`, `check_schema` raises `RuntimeError` naming `import_key`, `flowly.db`, and README "Calendar import"; against a fresh `create_all` schema and against an empty database it returns normally.
    - _Requirements: 14.2, 14.3, 14.4; Design §7_

- [ ] 3. Create the pure `app/ics` package
  - [ ] 3.1 Implement `app/ics/__init__.py` and `app/ics/types.py`
    - Define `SkipReason` (all 13 codes, including `past_event`), `ImportLimits`, `ImportRecord`, `SkippedItem` (with `count: int = 1`), `ParseResult`, and `InvalidCalendarError(issue)` exactly as in Design §4.1. `__init__.py` re-exports the public names as later modules land.
    - New test file `tests/unit/test_ics_boundary.py`: parse every `app/ics/*.py` with `ast` and assert no import of `sqlalchemy`, `fastapi`, `starlette`, `app.data`, `app.services`, `app.api`, or `dateutil`, and no use of `datetime.now`, `date.today`, `time.time`, `os.environ`, or `open(`. The test covers each module added later automatically.
    - _Requirements: 10.4, 12.1, 12.2, 12.3; Design §1, §4.1_

- [ ] 4. Implement value parsing (`app/ics/values.py`)
  - [ ] 4.1 Implement scalar value parsers
    - DATE-TIME (`YYYYMMDDTHHMMSS[Z]`, second `60` rejected), DATE (`YYYYMMDD` or `VALUE=DATE`), DURATION (weeks; or days plus `T` hours/minutes/seconds; optional sign), and TEXT unescaping (`\\`, `\;`, `\,`, `\n`/`\N`), each returning a typed value or raising a private parse error that the event pipeline maps to `malformed_event`.
    - Duration results keep the nominal (weeks/days) and exact (H/M/S) parts separate for Design §4.4.
    - New test file `tests/unit/test_ics_values.py`: valid and invalid examples for each type, including `PT0S`, `-PT1H`, `P1W`, `P1DT2H`, `P` (invalid), `20260230T090000` (invalid date), and every escape.
    - _Requirements: 3.12, 7.1, 8.1, 8.7; Design §4.3_

  - [ ] 4.2 Implement `RRULE` parsing and validation
    - Parse `NAME=VALUE;…` into a frozen `RuleSpec` (freq, interval, count, until, byday with optional ordinals, bymonthday, bymonth, wkst).
    - Classify problems per Design §5.2: syntax errors, repeated parts, `COUNT` with `UNTIL`, `INTERVAL < 1`, `COUNT < 1`, and out-of-range numbers → malformed; any other `FREQ` or part, ordinal `BYDAY` with `DAILY`/`WEEKLY`, and `BYMONTHDAY` with `WEEKLY` → unsupported.
    - New test file `tests/unit/test_ics_rrule.py`: one example per row of the Design §5.2 table, plus the ordinal ranges (±1..5 for `MONTHLY` and `YEARLY`+`BYMONTH`, ±1..53 for `YEARLY` alone).
    - _Requirements: 6.4, 6.10, 8.7; Design §4.3, §5.2_

- [ ] 5. Implement recurrence expansion (`app/ics/recurrence.py`)
  - [ ] 5.1 Implement the period walk from `DTSTART`
    - `expand(rule, dtstart, lo, hi, until=None, budget=…)` works in naive source wall time and returns sorted original starts in `[lo, hi]`. Implement the defaults from `DTSTART`, periods aligned to `INTERVAL` (weeks start on `WKST`), the candidate table for each `FREQ`, invalid-day dropping, `DTSTART` as the first occurrence counted toward `COUNT`, `UNTIL` (inclusive), and stopping when a period starts after `hi` or `UNTIL` (Design §5.4). Always start at period 0 in this task.
    - New test file `tests/unit/test_ics_recurrence_edge_cases.py`: weekly `BYDAY=MO,WE,FR` with `DTSTART` on a Wednesday; monthly `BYMONTHDAY=31` skips 30-day months; `BYMONTHDAY=-1`; `BYDAY=-1FR`; yearly Feb 29 only in leap years; `INTERVAL=2` weekly with `WKST=SU` vs `MO`; `COUNT` with a non-matching `DTSTART` (RFC behavior); `UNTIL` exactly on an occurrence.
    - _Requirements: 6.3, 6.4; Design §5.4_

  - [ ] 5.2 Write the property test comparing the expander with `dateutil`
    - **Property 9: Expander agrees with the reference**
    - **Validates: Requirements 6.3–6.5**
    - New file `tests/unit/test_ics_recurrence_oracle_property.py`; `hypothesis`, min 100 iterations. Generate supported rules (`BYMONTHDAY` limited to 1–28 and ±1), `DTSTART`s, and bounded horizons; compare against `dateutil.rrule` with the same explicit parts, adding `DTSTART` and reducing `COUNT` by one when `DTSTART` doesn't match the rule. Only this test file imports `dateutil`. Tag: `Feature: calendar-import, Property 9: Expander agrees with the reference`.

  - [ ] 5.3 Start expansion at the import window for rules without `COUNT`
    - Compute `p0` as the largest multiple of `INTERVAL` whose period starts at or before `lo`'s period (never below 0) when the rule has no `COUNT`; keep `p0 = 0` for `COUNT` rules.
    - **Property 10: Starting at the window changes nothing**
    - **Validates: Requirements 6.1–6.2; Design §5.4**
    - New file `tests/unit/test_ics_recurrence_window_property.py`; `hypothesis`, min 100 iterations. For supported rules without `COUNT` and `DTSTART`s up to ~5 years before `lo`, compare against the period-0 walk filtered to `[lo, hi]`. Also assert the number of periods examined stays within `(hi − lo)` ÷ period length + 2. Tag: `Feature: calendar-import, Property 10: Starting at the window changes nothing`.

  - [ ] 5.4 Add the examined-date budget, `RDATE`, and `EXDATE`
    - Add a file-wide budget object shared across calls: each examined period costs `1 + len(candidates)`, each `RDATE` costs 1, and going over 200,000 raises `InvalidCalendarError` with the Design §5.4 message.
    - Merge `RDATE` values, remove `EXDATE` values (exact wall-time match; a DATE `EXDATE` removes all originals on that date), de-duplicate, and sort.
    - Extend `tests/unit/test_ics_recurrence_edge_cases.py`: `FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30` with `COUNT=5` from 1990 is stopped by the budget rather than scanning to year 9999 (assert on the budget count, not time); `MONTHLY;BYDAY=1MO;BYMONTHDAY=20` (never matches) likewise; a daily `COUNT` series from 1990 fits within the budget; `RDATE` and both `EXDATE` forms.
    - _Requirements: 2.6, 6.5; Design §5.4, §5.5_

- [ ] 6. Implement time zones (`app/ics/windows_zones.py`, `app/ics/zones.py`)
  - [ ] 6.1 Generate the CLDR 49 Windows → IANA table
    - Download `common/supplemental/windowsZones.xml` at tag `release-49` once, keep the `territory="001"` rows, lower-case the Windows names, and write `windows_zones.py` with `CLDR_RELEASE = "49"`, `CLDR_SOURCE`, `WINDOWS_ZONES_VERSION = "7e11800"`, `WINDOWS_TO_IANA` (142 entries), and the regeneration steps in the module docstring. The download is a one-off step; no runtime or test code fetches anything.
    - New test file `tests/unit/test_ics_windows_zones.py`: 142 entries; `CLDR_RELEASE == "49"`; all keys lower-case; `"eastern standard time" → "America/New_York"`; every target is in the `tzdata` zone list.
    - _Requirements: 3.3, 3.7, 3.8, 12.8; Design §4.4_

  - [ ] 6.2 Implement `zones.py`
    - Load the key list from the `tzdata` package's `zones` file and build zones with `ZoneInfo.from_file(...)`, cached per key, never using the OS database. Implement `resolve_upload_zone(name)` (exact key only), `resolve_tzid(value)` (trim whitespace and quotes → exact key → lower-cased Windows table → `None`), and `to_local(wall, source, upload)` with `fold=0` (Design §4.4).
    - New test file `tests/unit/test_ics_zones.py`: `America/Toronto` valid and `Eastern Standard Time` invalid as an upload zone; `"Eastern Standard Time"` (quoted) and `eastern STANDARD time` resolve to `America/New_York`; `UTC` resolves via the key list; `(UTC-05:00) Eastern Time (US & Canada)` and `/mozilla.org/20050126_1/America/New_York` resolve to `None`; the gap example (02:30 → 03:30 `America/New_York` on 2026-03-08) and the fold example (01:30 → 05:30Z on 2026-11-01); floating input is returned unchanged.
    - _Requirements: 2.2, 3.2–3.5, 3.9, 3.10, 4.1, 4.2, 4.4, 4.6, 4.8; Design §4.4_

  - [ ] 6.3 Write property tests for DST resolution
    - **Property 6: DST gap rule**
    - **Property 7: DST fold rule**
    - **Validates: Requirements 4.1, 4.2**
    - New file `tests/unit/test_ics_zones_dst_property.py`; `hypothesis`, min 100 iterations each. Draw zones from the `tzdata` keys, find gap and fold transitions by scanning each zone's UTC offsets over a year, and draw wall times inside them. Tags: `Feature: calendar-import, Property 6: DST gap rule` and `Feature: calendar-import, Property 7: DST fold rule`.

- [ ] 7. Implement the content-line reader (`app/ics/content.py`)
  - [ ] 7.1 Implement `read_calendar`
    - BOM strip and strict UTF-8 decode, empty check, CRLF/LF normalization, unfolding, line tokenizing (quoted and multi-value parameters, upper-cased names, `BadLine` tokens), and the component tree with `BEGIN`/`END` matching, top-level `VCALENDAR` only, multiple calendars, nesting limit 8, and `VEVENT` malformed marking. Return a `CalendarDocument` with the `VEVENT`s in file order; drop other components (Design §4.2).
    - New test file `tests/unit/test_ics_content.py`: one example per `InvalidCalendarError` message in Design §4.2 (invalid UTF-8, empty, continuation on first line, unmatched `END`, missing `END`, content outside `VCALENDAR`, no `VCALENDAR`, nesting depth 9); a BOM-prefixed file; LF-only and mixed line endings; a bad line inside a `VEVENT` marks only that event; a bad line inside `VTIMEZONE` is ignored; `VTODO`/`VALARM` are dropped.
    - _Requirements: 2.5, 2.10, 3.6, 8.8; Design §4.2_

  - [ ] 7.2 Write property tests for the reader
    - **Property 1: Content-line round trip**
    - **Property 15: Robustness** (reader half: `read_calendar` returns a document or raises `InvalidCalendarError`)
    - **Validates: Requirements 2.5, 2.10, 8.1**
    - New file `tests/unit/test_ics_content_property.py`; `hypothesis`, min 100 iterations each. A test helper serializes generated events with escaping and 75-octet folding. Tags: `Feature: calendar-import, Property 1: Content-line round trip` and `Feature: calendar-import, Property 15: Robustness`.

- [ ] 8. Implement event normalization (`app/ics/events.py`)
  - [ ] 8.1 Implement the non-recurring pipeline
    - `normalize_events(doc, upload_zone, reference, limits)`: reject a naive `reference`; compute the window; group events by UID; run pipeline rows 1–7, 9, and 11–13 for events without `RRULE` or `RECURRENCE-ID` (title rules, `DTEND`/`DURATION`/zero-length end, floating/zoned mix, conversion, `dst_overlap`, `S|<uid>` keys, `duplicate`, and the 2,000-record limit counted as records are emitted). Skipped items carry UID, title, and start when known.
    - New test file `tests/unit/test_ics_events_single.py`: one example per reason (`malformed_event`, `missing_uid`, `cancelled`, `missing_start`, `all_day`, `unknown_timezone`, `invalid_interval`, `dst_overlap`, `duplicate`); `Untitled event`; a 250-character title is cut to 200 and trimmed; `DURATION:P1D` across a DST change; `DTSTART` and `DTEND` in different zones; `X-WR-TIMEZONE` and a `VTIMEZONE` block change nothing; a naive `reference` raises `ValueError`.
    - _Requirements: 2.6, 3.1–3.6, 3.10–3.13, 4.5, 4.7, 5.3, 5.11, 5.12, 7.1, 7.2, 8.1–8.7, 8.9, 10.3; Design §4.4, §4.5_

  - [ ] 8.2 Add the past-event rule and aggregate entry
    - Add pipeline row 10 for non-recurring events: `end_local <= window_start` increments a `past_events` counter and emits nothing; after all events, append one `SkippedItem(reason=PAST_EVENT, count=N, uid=None, title=None, start=None)` with the cutoff message when `N > 0`, placed last among parser skips.
    - New test file `tests/unit/test_ics_events_past.py`: an event ending exactly at `window_start` is past; ending one second later is imported; yesterday-to-tomorrow is imported; two years ahead is imported; 3,000 past events plus 10 current give 10 records and one `past_event` entry with `count` 3,000 and no limit error; an old all-day event is reported as `all_day`; an old fold-crossing event is counted as past, not `dst_overlap`.
    - _Requirements: 2.6, 6.12, 6.13, 10.3, 10.5; Design §4.4, §4.5_

  - [ ] 8.3 Add the recurring branch
    - For masters with `RRULE`: map rule problems to `malformed_event`/`unsupported_recurrence`; convert `UNTIL`, `EXDATE`, and `RDATE` to source wall time per Design §5.4; compute `lo`/`hi` from the window with the 2-day margin; call `expand` with the shared budget; build `R|<stamp>|<uid>` keys; apply overrides (their own skip checks, `cancelled`, `RANGE=THISANDFUTURE`); give `DTEND` series their exact duration; filter by the window; run rows 11–13 (not row 10); process unconsumed and orphan overrides as standalone occurrences; add `outside_window` when a series yields nothing; keep the Design §4.5 order.
    - New test file `tests/unit/test_ics_events_recurring.py`: weekly `America/Toronto` class across the November DST change stays at 09:00 local in an `America/Toronto` upload and moves by an hour in a `UTC` upload; an override that moves one occurrence keeps its key; a cancelled override is `cancelled`; `THISANDFUTURE` is skipped and the series imports unmodified; an orphan override imports; a series ending before the window gives `outside_window`; more than one `RRULE` gives `unsupported_recurrence`; a floating series keeps floating keys; Google-style and Outlook-style fixtures (Windows `TZID`s plus an ignored `VTIMEZONE`) produce the expected records.
    - _Requirements: 3.3, 4.3, 5.3, 5.4, 6.1–6.11, 6.14, 7.2; Design §4.5, §5.4_

  - [ ] 8.4 Write property tests for time-zone behavior at file level
    - **Property 2: Floating invariance**
    - **Property 3: Zone equivalence**
    - **Property 4: Windows name equivalence**
    - **Property 5: Unmappable names are skipped**
    - **Validates: Requirements 3.2–3.5, 3.10, 4.6**
    - New file `tests/unit/test_ics_events_zone_property.py`; `hypothesis`, min 100 iterations each. Tag each, e.g. `Feature: calendar-import, Property 4: Windows name equivalence`.

  - [ ] 8.5 Write property tests for record and recurrence invariants
    - **Property 8: Fold overlap is skipped, never inverted**
    - **Property 11: Recurrence invariants**
    - **Property 12: Key independence**
    - **Property 13: Record invariants** (titles validated with `_validate_title` from `app/schemas/commitment.py`)
    - **Validates: Requirements 4.5, 5.4, 5.12, 6.1–6.3, 8.1–8.3, 8.9**
    - New file `tests/unit/test_ics_events_invariants_property.py`; `hypothesis`, min 100 iterations each. Tag each with its property line.

  - [ ] 8.6 Write property tests for limits, past events, robustness, and determinism
    - **Property 14: Limits are enforced during expansion**
    - **Property 15: Robustness** (normalizer half)
    - **Property 17: Determinism**
    - **Property 18: Past events are skipped and counted once**
    - **Validates: Requirements 2.6, 4.8, 6.12–6.14, 8.7, 10.5, 10.8, 12.4, 12.7**
    - New file `tests/unit/test_ics_events_limits_property.py`; `hypothesis`, min 100 iterations each. For Property 14, use instrumented counters (records emitted, dates examined) to show expansion stops at 2,001 records or at the budget. Include the fixed example of 12 daily series over 180 days (2,160 records) being rejected. Tag each with its property line.

- [ ] 9. Implement matching (`app/ics/matching.py`)
  - [ ] 9.1 Implement `plan_import`
    - `StoredImport`, `ImportPlan`, and `plan_import(records, stored)` as in Design §6.1: create when the key is new, `unchanged` (`SkippedItem`, "Already up to date.") when title/start/end are equal, update otherwise; keep record order.
    - New test file `tests/unit/test_ics_matching.py`: one example of each outcome; a change to only `end` is an update; record order is kept.
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 12.5; Design §6.1_

  - [ ] 9.2 Write property test for matching
    - **Property 16: Matching partition and idempotence**
    - **Validates: Requirements 5.5–5.7, 5.13**
    - New file `tests/unit/test_ics_matching_property.py`; `hypothesis`, min 100 iterations. Tag: `Feature: calendar-import, Property 16: Matching partition and idempotence`.

- [ ] 10. Checkpoint — pure `app/ics` core verified
  - Ensure all tests pass, including `tests/unit/test_ics_boundary.py` over every core module, and ask the user if questions arise.

- [ ] 11. Implement persistence and the import service
  - [ ] 11.1 Add import methods to `CommitmentRepository`
    - `get_by_import_keys(keys)` querying in chunks of 500, and `apply_import(new, changed)` that adds new rows, sets title/start/end on changed rows, commits once, and rolls back and re-raises on any error (Design §6.3). Existing methods unchanged.
    - New test file `tests/unit/test_commitment_repository_import.py` (in-memory SQLite): lookup across more than 500 keys; manual rows are never returned; a forced failure (e.g. a duplicate `import_key` in `new`) leaves the table exactly as before; updated rows keep `id`, `created_at`, and `source`.
    - _Requirements: 5.5, 9.3, 11.1, 11.2; Design §6.3_

  - [ ] 11.2 Implement `app/schemas/calendar_import.py`
    - `SkippedItemRead` (with `count`) and `ImportSummary` as in Design §3.3, with `reason` typed as `SkipReason`.
    - Extend coverage with a small test in a new file `tests/unit/test_calendar_import_schemas.py`: a `past_event` item with null fields serializes as in the Design §3.3 example.
    - _Requirements: 10.1–10.6; Design §3.3_

  - [ ] 11.3 Implement `CalendarImportService`
    - `app/services/calendar_import_service.py` with an injected clock: `normalize_events` → `get_by_import_keys` → `plan_import` → `apply_import` (new rows with `source=ics_import` and their `import_key`) → summary with `skipped = sum(count)` and items ordered parser skips, then `unchanged` (Design §6.2).
    - New test file `tests/unit/test_calendar_import_service.py` with a fixed clock: first import creates; second import of the same file gives 0 created and 0 updated; an edited file updates in place; an imported row deleted in FLOWLY is recreated; a row edited in FLOWLY is overwritten; manual rows are untouched; a different upload zone updates zoned events and leaves floating ones; moving the clock forward reports a now-past event in the `past_event` count and leaves its row unchanged; an event removed from the file is not deleted.
    - **Property 19: Summary totals add up**
    - **Validates: Requirements 10.3, 10.5–10.6**
    - `hypothesis`, min 100 iterations, over generated parse results and plans. Tag: `Feature: calendar-import, Property 19: Summary totals add up`.
    - _Requirements: 3.14, 5.5–5.10, 5.13, 6.13, 9.2, 9.3, 10.1–10.8, 11.1–11.3, 16.3; Design §6.2_

- [ ] 12. Implement the API endpoint
  - [ ] 12.1 Add `UploadValidationError` to `app/api/errors.py`
    - The exception class and a handler returning `error_response(422, VALIDATION_ERROR, "Request validation failed", details)`, registered in `register_error_handlers`.
    - New test file `tests/api/test_upload_validation_error.py`: a throwaway route that raises it returns the standard envelope with two details.
    - _Requirements: 2.8; Design §3.4_

  - [ ] 12.2 Implement `app/api/calendar_import.py` and wire it into `app/main.py`
    - `POST /commitments/import` with the Design §3.2 reading steps (content-type check, `Content-Length` check, streamed byte count with `MAX_BODY`, replayed `Request.form(max_files=1, max_fields=1, max_part_size=1024)`, collected `timezone`/`file` details including the structure check from `read_calendar`), `run_in_threadpool` for the service call, `InvalidCalendarError` → `UploadValidationError` on `file`, and `openapi_extra` describing both fields. Include the router in `create_app()` before the commitments router.
    - _Requirements: 1.1–1.5, 2.1–2.9, 16.2; Design §3.1, §3.2, §3.4_

  - [ ] 12.3 Write API tests for the import endpoint
    - New file `tests/api/test_calendar_import_api.py`, following the existing fixture pattern (`get_db` override, `TestClient` not used as a context manager) and overriding the service's clock.
    - Success: response shape and counts, `count` on every item, `skipped` equals the sum of counts with past events present, `timezone` echoed.
    - Rejections, each asserting the envelope: non-multipart body; missing `file`; missing `timezone`; unknown `timezone`; both invalid (two details); oversized body via `Content-Length`; oversized chunked body via an `httpx` generator (only the `file` detail); file over 5,242,880 bytes; invalid UTF-8; no `VCALENDAR`; over 2,000 records; over the date budget. After each rejection `GET /commitments` is unchanged.
    - Re-import, source, and compatibility: same file twice; edited file updates in place; `POST /commitments` with `source: "ics_import"` gives 422; `PUT` on an imported row keeps `source`; `GET /commitments` items have no `import_key`; `GET /commitments/import` still returns 422; imported commitments count toward `/dashboard/workload` exactly like manual ones.
    - _Requirements: 1.1–1.4, 2.1–2.9, 5.13, 9.4, 9.5, 12.9, 16.2, 16.4, 16.5; Design §3, Testing Strategy_

- [ ] 13. Checkpoint — backend verified
  - Ensure all tests pass, confirm `git status` shows no changes to existing test files, and ask the user if questions arise.

- [ ] 14. Build the frontend import control
  - [ ] 14.1 Add the import form and upload call
    - `frontend/index.html`: the `#import-form` card from Design §9 in the Commitments section.
    - `frontend/app.js`: `api()` passes `FormData` bodies through without setting `Content-Type`; `CommitmentsApi.importIcs`; `submitImportForm` (client-side "file is required" in the envelope shape, `timezone` from `Intl.DateTimeFormat().resolvedOptions().timeZone`, counts and zone rendered into `#import-result`, `setStatus` announcement, file input reset, `refreshAll()`, and `showFormErrors` for `file`/`timezone` on 422); fill `#import-timezone` on load.
    - _Requirements: 13.1, 13.2, 13.3, 13.5, 13.7; Design §9_

  - [ ] 14.2 Render skipped items grouped by reason, collapsed by default
    - `renderSkippedGroups(items)` with the `SKIP_REASON_LABELS` map: one `<details>` per reason (no `open` attribute) in first-seen order, `<summary>` with label and the sum of `count`, and a `<ul>` of entries (title, formatted start, message; message only for `past_event`); unknown reasons fall back to the raw code. Add the group and result styles to `frontend/styles.css`.
    - _Requirements: 13.4, 13.7; Design §9_

  - [ ] 14.3 Label imported commitments
    - `renderCommitmentItem` adds `<span class="badge">Imported</span>` when `c.source === "ics_import"`; add `.badge` to `styles.css`.
    - _Requirements: 13.6; Design §9_

  - [ ] 14.4 Write frontend contract tests for the import control
    - New file `tests/api/test_frontend_import_contract.py` (the existing `test_frontend_contract.py` stays unchanged and must still pass, including its API-route matching for the new `api("/commitments/import", { method: "POST" … })` call).
    - Assert: `#import-form` exists with a labelled `input type="file"` whose `accept` includes `.ics`; `data-error-for="file"` and `data-error-for="timezone"` elements exist; `app.js` reads `resolvedOptions().timeZone`; `renderSkippedGroups` creates `details` elements and never sets `open`; `SKIP_REASON_LABELS` has a label for every `SkipReason` value; the badge text `Imported` is present.
    - _Requirements: 13.1–13.7, 16.1; Design §9_

- [ ] 15. Document the feature
  - [ ] 15.1 Add the README "Calendar import" section
    - Cover every item in Requirement 17.2–17.7: how to import and the limits; time zones (browser zone, floating kept, `X-WR-TIMEZONE` and `VTIMEZONE` ignored, Windows names mapped, unmapped skipped, zone change on re-import); overwrite rules; recurring events, the supported `RRULE` subset, and the moved-series limitation (all three cases); past events; all-day events; and the database upgrade note (delete and recreate `flowly.db`, which erases data).
    - Add `app/ics/` to the architecture table and `/commitments/import` to "Main API routes".
    - _Requirements: 6.17, 14.1, 17.1–17.7; Design §10_

- [ ] 16. Final checkpoint — calendar import verified
  - Ensure all tests pass (`python -m pytest`), and ask the user if questions arise.
  - Ask the user before recreating their `flowly.db`. With a fresh database, start `uvicorn app.main:app` (the user runs it), import a small sample `.ics` from the page, re-import it, and confirm the second summary shows 0 created and 0 updated.

## Notes

- No tasks are optional. Every property in Design Correctness Properties (1–19) has a test task.
- Each task lists the `requirements.md` criteria it implements as `Requirement.Criterion` numbers and the `design.md` sections it follows.
- The recurrence expander (task 5) is checked against `dateutil` immediately after its first version, before the window start, budget, or event pipeline build on it.
- Property-based tests use `hypothesis` with a minimum of 100 iterations and are tagged `Feature: calendar-import, Property {number}: {property_text}`. Properties 1–18 test the pure `app/ics` core; Property 19 tests the service's summary.
- `python-dateutil` is imported only by `tests/unit/test_ics_recurrence_oracle_property.py`; `tests/unit/test_ics_boundary.py` enforces that `app/ics` never imports it.
- Task 2.2 makes an existing `flowly.db` incompatible. From then on, task 2.3's startup check stops the server with instructions until the user recreates the file; tests are unaffected because they use temporary databases and don't run `lifespan`.
- Checkpoints come after the pure core (task 10), the backend (task 13), and the full feature (task 16).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1"] },
    { "id": 2, "tasks": ["2.3", "4.1", "6.1", "7.1", "9.1", "11.1", "11.2", "12.1"] },
    { "id": 3, "tasks": ["4.2", "6.2", "7.2", "9.2"] },
    { "id": 4, "tasks": ["5.1", "6.3", "8.1"] },
    { "id": 5, "tasks": ["5.2", "8.2"] },
    { "id": 6, "tasks": ["5.3"] },
    { "id": 7, "tasks": ["5.4"] },
    { "id": 8, "tasks": ["8.3"] },
    { "id": 9, "tasks": ["8.4", "8.5", "8.6", "11.3"] },
    { "id": 10, "tasks": ["12.2"] },
    { "id": 11, "tasks": ["12.3", "14.1"] },
    { "id": 12, "tasks": ["14.2"] },
    { "id": 13, "tasks": ["14.3"] },
    { "id": 14, "tasks": ["14.4", "15.1"] }
  ]
}
```
