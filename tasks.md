# Implementation Plan: FLOWLY MVP

## Overview

This plan builds the FLOWLY MVP backend and a minimal decoupled frontend as described in
`docs/design.md`. The stack is Python + FastAPI + Pydantic + SQLAlchemy + SQLite, tested with
pytest, `hypothesis`, and FastAPI `TestClient`.

Work proceeds strictly bottom-up so every step builds on the last with no orphaned code:
project scaffolding/config → domain enums → SQLAlchemy models + database setup → repositories →
Pydantic schemas → pure planning core (intervals, workload, daily plan) paired with their property
and unit tests → services → API routers with centralized error handling → API/integration tests →
a minimal decoupled frontend → final wiring and run.

The pure planning core (Design §8 workload, §9 daily plan, interval union) is written as
side-effect-free functions and paired directly with its tests, because the design emphasizes testing
this logic in isolation (Design §1, Testing Strategy).

Property-based tests use `hypothesis` with a minimum of 100 iterations each, and every property test
is tagged with a comment of the form `Feature: flowly-mvp, Property {number}: {property_text}`
(Design Testing Strategy). All tests run with no external network access.

Scope is strictly the MVP. No Canvas, Google Calendar, email, transit, notifications, ML/AI,
analytics, auth, or multi-user work appears here (Requirements §15; Design Scope boundaries).

## Tasks

- [x] 1. Scaffold project structure and configuration
  - Create the `flowly/` package layout from Design §4: `app/` with `api/`, `schemas/`, `services/`, `planning/`, `data/`, `domain/` subpackages (each with `__init__.py`), plus `frontend/` and `tests/unit/` and `tests/api/` directories.
- Add a dependency manifest (`requirements.txt` or `pyproject.toml`) declaring the required dependencies: FastAPI, Pydantic, SQLAlchemy, uvicorn, pytest, and hypothesis.
  - Implement `app/config.py` with a settings object exposing `DATABASE_URL` (default SQLite file URL), so the engine is selected by configuration rather than code.
  - Add a `pytest` configuration (e.g., `pytest.ini` or `pyproject` section) that discovers `tests/unit` and `tests/api`.
  - _Requirements: §9, §10; Design §2, §4, §6_

- [x] 2. Define shared domain enums
  - [x] 2.1 Implement `app/domain/enums.py`
    - Define `Priority` (`High`, `Medium`, `Low`), `Category` (`Academic`, `Work`, `Personal`, `Career`), `Completion` (`Incomplete`, `Complete`), and `Source` (`manual`) as string-valued enums.
    - _Requirements: §2.5, §2.6, §1.4, §10; Design §5_

- [x] 3. Set up database and ORM models
  - [x] 3.1 Implement `app/data/database.py`
    - Build the SQLAlchemy engine and session factory from `DATABASE_URL` in config, declare the ORM base, and provide a session-provider dependency plus a `create_all` helper for table creation.
    - _Requirements: §9, §10; Design §3, §4_

  - [x] 3.2 Implement `app/data/models.py` ORM models
    - Define the `Task` model with `id`, `title`, `description` (default `""`), `deadline` (nullable), `estimated_time` (nullable minutes), `priority` (default `Medium`), `category` (default `Personal`), `completion` (default `Incomplete`), `created_at` (server now), and `source` (default `manual`).
    - Define the `Commitment` model with `id`, `title`, `start_time`, `end_time`, `source` (default `manual`), and `created_at`.
    - _Requirements: §2.1–§2.6, §3.1, §9, §10; Design §5_

- [x] 4. Implement data-access repositories
  - [x] 4.1 Implement `app/data/task_repository.py`
    - Provide create, get-by-id, list, update, delete, and set-completion methods against the `Task` model, each operating within a single transaction (full commit or rollback — no partial writes).
    - _Requirements: §1.1–§1.4, §9, §10; Design §4, §7, Error Handling_

  - [x] 4.2 Implement `app/data/commitment_repository.py`
    - Provide create, get-by-id, list, update, and delete methods against the `Commitment` model, each in a single transaction.
    - _Requirements: §3.1–§3.3, §9; Design §4, §7_

- [x] 5. Define Pydantic schemas with boundary validation
  - [x] 5.1 Implement `app/schemas/task.py`
    - Define `TaskCreate`, `TaskUpdate`, and `TaskRead`. Enforce `title` length 1–200 after trimming (reject empty/whitespace-only), `estimated_time` a positive integer when present, and `priority`/`category` restricted to their enums. Apply defaults (`description=""`, `priority=Medium`, `category=Personal`, `completion=Incomplete`, `source=manual`).
    - _Requirements: §2.1–§2.6, §1.1, §10, §11; Design §5, §6, Error Handling_

  - [x] 5.2 Implement `app/schemas/commitment.py`
    - Define `CommitmentCreate`, `CommitmentUpdate`, and `CommitmentRead`. Enforce `title` length 1–200 after trimming and `end_time` strictly after `start_time`; default `source=manual`.
    - _Requirements: §3.1, §3.4, §10, §11; Design §5, §6, Error Handling_

  - [x] 5.3 Implement `app/schemas/dashboard.py`
    - Define `WorkloadSummary`, `DailyPlan` (with per-task `fits` flag), `TodayView`, and `UpcomingView` response models matching the shapes in Design §6.
    - _Requirements: §4, §5, §6, §7, §8; Design §6, §8, §9_

- [x] 6. Implement the pure interval-union planning function
  - [x] 6.1 Implement `app/planning/intervals.py`
    - Write a pure `merge_intervals` function: sort intervals by start, walk left to right, extend when the next interval starts at or before the current end, otherwise close and open a new one. Return the merged intervals. No DB, clock, or I/O.
  - [x] 6.2 Write property test for interval union
    - **Property 9: Committed time is the union of intervals (no double-counting)**
    - **Validates: Requirements §3.4**
    - Use `hypothesis` (min 100 iterations). Generate overlapping, nested, and adjacent intervals; assert union length never exceeds the sum of individual lengths. Tag: `Feature: flowly-mvp, Property 9: Committed time is the union of intervals (no double-counting)`.
  - [x] 6.3 Write unit tests for interval union edge cases
    - Empty set, single interval, back-to-back (adjacent) intervals, fully nested intervals, and identical intervals.
    - _Requirements: §3.4; Design Testing Strategy (unit tests)_

- [x] 7. Implement the pure workload-calculation function
  - [x] 7.1 Implement `app/planning/workload.py`
    - Pure function over target `date`, incomplete tasks due that date, and commitments. Fixed 960-minute window; committed = union length (reuse `intervals.py`); `available = max(0, 960 - committed)`; estimated = sum of `estimated_time` (missing counts as 0); `difference = available - estimated` (not clamped); `overloaded = estimated > available`. Return the `WorkloadSummary` fields.
    - _Requirements: §2.4, §3.4, §7; Design §8_

  - [x] 7.2 Write a unit test for committed time within the planning window
  - Verify that the workload calculation never counts more than the 960-minute planning window as committed time.
  - Test cases should include commitments that overlap, extend beyond the planning window, and meet or exceed the full window.
  - *Requirements: §7; Design §8*

  - [x] 7.3 Write property test for the available-time clamp
    - **Property 10: Available time is clamped and never negative**
    - **Validates: Requirements §7**
    - `hypothesis`, min 100 iterations; assert `available = max(0, 960 - committed)` and `available >= 0` even when commitments meet or exceed the window. Tag: `Feature: flowly-mvp, Property 10: Available time is clamped and never negative`.

  - [x] 7.4 Write property test for the estimated-sum rule
    - **Property 11: Estimated minutes sum treats missing estimates as zero**
    - **Validates: Requirements §2.4, §7**
    - `hypothesis`, min 100 iterations; mix tasks with and without `estimated_time`; assert estimated equals the sum counting missing as 0. Tag: `Feature: flowly-mvp, Property 11: Estimated minutes sum treats missing estimates as zero`.

  - [x] 7.5 Write property test for the overload flag
    - **Property 12: Overload flag matches strict comparison**
    - **Validates: Requirements §7**
    - `hypothesis`, min 100 iterations; assert `overloaded` is true iff estimated strictly exceeds available. Tag: `Feature: flowly-mvp, Property 12: Overload flag matches strict comparison`.

  - [x] 7.6 Write unit tests for workload boundaries
    - Commitment exactly equal to the full window (available = 0), estimated exactly equal to available (not overloaded), and empty inputs.
    - _Requirements: §7; Design Testing Strategy (unit tests)_

- [x] 8. Implement the pure daily-plan function
  - [x] 8.1 Implement `app/planning/daily_plan.py`
    - Pure, deterministic function over target `date`, incomplete tasks, and available minutes. Candidate selection: include only incomplete tasks with a defined deadline on or before the date (no-deadline tasks excluded). Ordering: deadline ascending, then priority High>Medium>Low, then `created_at` ascending. Fitting: walk the ordered list accumulating `estimated_time` (missing = 0) and annotate each task's `fits` flag without changing the order. Return the `DailyPlan` shape.
    - _Requirements: §8; Design §9_

  - [x] 8.2 Write property test for candidate selection
    - **Property 13: Daily-plan candidate selection**
    - **Validates: Requirements §8**
    - `hypothesis`, min 100 iterations; assert the plan includes exactly the incomplete tasks with a deadline on or before the date and never includes no-deadline tasks. Tag: `Feature: flowly-mvp, Property 13: Daily-plan candidate selection`.

  - [x] 8.3 Write property test for deterministic ordering
    - **Property 14: Daily-plan deterministic ordering**
    - **Validates: Requirements §8**
    - `hypothesis`, min 100 iterations; assert every adjacent pair respects deadline, then priority, then `created_at`. Tag: `Feature: flowly-mvp, Property 14: Daily-plan deterministic ordering`.

  - [x] 8.4 Write property test for determinism
    - **Property 15: Daily plan is deterministic**
    - **Validates: Requirements §8**
    - `hypothesis`, min 100 iterations; assert generating the plan twice on identical inputs yields identical output. Tag: `Feature: flowly-mvp, Property 15: Daily plan is deterministic`.

  - [x] 8.5 Write property test for fitting within available time
    - **Property 16: Daily-plan fitting respects available time**
    - **Validates: Requirements §8**
    - `hypothesis`, min 100 iterations; assert the cumulative `estimated_time` of tasks marked fitting does not exceed available minutes (missing estimate consumes 0). Tag: `Feature: flowly-mvp, Property 16: Daily-plan fitting respects available time`.

  - [x] 8.6 Write unit tests for daily-plan edge cases
    - Tie-breaking when deadlines and priorities are equal, a plan where available time runs out partway through the ordered list, and an all-no-deadline input (empty plan).
    - _Requirements: §8; Design Testing Strategy (unit tests)_

- [x] 9. Checkpoint — pure planning core verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement service layer
  - [x] 10.1 Implement `app/services/task_service.py`
    - Orchestrate create/edit/delete/complete use cases: apply defaults, call the task repository, raise a not-found condition when an id is missing, and return stored entities.
    - _Requirements: §1.1–§1.4, §10; Design §7_

  - [x] 10.2 Write unit tests for task service CRUD and completion round-trips
    - **Property 1: Task creation round-trip with defaults**
    - **Property 2: Task edit reflects updates**
    - **Property 3: Delete removes the task**
    - **Property 4: Completion toggle round-trip**
    - **Validates: Requirements §1.1, §1.2, §1.3, §1.4, §2.2, §2.5, §2.6, §10**
    - Use `hypothesis` where practical (min 100 iterations) over a test database. Tag each with its property line, e.g. `Feature: flowly-mvp, Property 1: Task creation round-trip with defaults`.

  - [x] 10.3 Implement `app/services/commitment_service.py`
    - Orchestrate commitment create/edit/delete: apply `source=manual`, call the commitment repository, raise not-found when missing.
    - _Requirements: §3.1–§3.3, §10; Design §7_

  - [x] 10.4 Write unit tests for commitment service CRUD round-trips
    - **Property 7: Commitment creation round-trip with end-after-start validation**
    - **Property 8: Commitment edit and delete**
    - **Validates: Requirements §3.1, §3.2, §3.3, §10**
    - `hypothesis` where practical (min 100 iterations). Tag each with its property line.

  - [x] 10.5 Implement `app/services/dashboard_service.py`
    - Build the today view (incomplete tasks relevant to the date; completed stay distinguishable) and upcoming view (incomplete tasks with future deadlines, ordered by deadline ascending); load the day's incomplete tasks and relevant commitments and delegate to the pure workload and daily-plan functions.
    - _Requirements: §4, §5, §6, §7, §8; Design §7, §8, §9_

  - [x] 10.6 Write unit tests for today/upcoming selection
    - **Property 17: Today view selection**
    - **Property 18: Upcoming view selection and ordering**
    - **Validates: Requirements §5, §6**
    - `hypothesis` where practical (min 100 iterations). Tag each with its property line.

- [x] 11. Implement centralized error handling
  - [x] 11.1 Implement `app/api/errors.py`
    - Register exception handlers that serialize validation failures (`422`) and not-found conditions (`404`) into the single error envelope `{ "error": { "type", "message", "details":[{"field","issue"}] } }` from Design Error Handling.
    - _Requirements: §11; Design §6, Error Handling_

- [x] 12. Implement API routers
  - [x] 12.1 Implement `app/api/tasks.py`
    - `POST /tasks` (201), `GET /tasks` (200), `GET /tasks/{id}` (200/404), `PUT /tasks/{id}` (200/404/422), `DELETE /tasks/{id}` (204/404), `PATCH /tasks/{id}/completion` (200/404/422), wiring schemas and the task service.
    - _Requirements: §1.1–§1.4; Design §6, §7_

  - [x] 12.2 Implement `app/api/commitments.py`
    - `POST /commitments` (201), `GET /commitments` (200), `GET /commitments/{id}` (200/404), `PUT /commitments/{id}` (200/404/422), `DELETE /commitments/{id}` (204/404), wiring schemas and the commitment service.
    - _Requirements: §3.1–§3.4; Design §6, §7_

  - [x] 12.3 Implement `app/api/dashboard.py`
    - `GET /dashboard/today`, `/upcoming`, `/workload`, `/daily-plan` (all 200, optional `date`/range query params), wiring the dashboard service and response schemas.
    - _Requirements: §4, §5, §6, §7, §8; Design §6_

  - [x] 12.4 Implement `app/main.py`
    - Create the FastAPI app, register the tasks/commitments/dashboard routers and the error handlers, and ensure tables are created on startup.
    - _Requirements: §4, §9; Design §3, §4_

- [ ] 13. Write API / integration tests (FastAPI TestClient)
  - [ ] 13.1 Implement `tests/api/test_tasks_api.py`
    - **Property 5: Title validation rejects empty/whitespace/over-length, with no persistence**
    - **Property 6: Estimated-time validation**
    - **Validates: Requirements §2.1, §2.4, §10**
    - Task CRUD + completion toggle happy paths with status codes (201/200/204), 404 on missing id for GET/PUT/DELETE/PATCH, and 422 with the error envelope for invalid bodies. Use `hypothesis` for the validation properties (min 100 iterations) and tag each, e.g. `Feature: flowly-mvp, Property 5: Title validation rejects empty/whitespace/over-length, with no persistence`.

  - [ ] 13.2 Implement `tests/api/test_commitments_api.py`
    - **Property 7: Commitment creation round-trip with end-after-start validation**
    - **Validates: Requirements §3.1, §3.4, §10**
    - Commitment CRUD happy paths with status codes (201/200/204), 404 on missing id, and 422 (end_time not after start_time) with the error envelope. Tag the property test accordingly.

  - [ ] 13.3 Implement `tests/api/test_dashboard_api.py`
    - Assert `/dashboard/today`, `/upcoming`, `/workload`, `/daily-plan` return 200 and the documented response shapes, including overlapping commitments and tasks with/without deadlines.
    - _Requirements: §4, §5, §6, §7, §8; Design §6, Testing Strategy_

  - [ ] 13.4 Implement a persistence integration test
    - Create tasks and commitments via the API, read them back through a fresh database session, and assert the data survived (Requirements §9).
    - _Requirements: §9; Design Testing Strategy (persistence)_

- [ ] 14. Checkpoint — backend and tests verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Build the minimal decoupled frontend
  - [ ] 15.1 Implement the core frontend in `frontend/`
    - Static HTML + vanilla JS that talks only to the REST API: list/create/edit/delete/complete tasks, create/edit/delete commitments, and render the dashboard (today, upcoming, workload summary, daily plan). Clearly distinguish completed vs. incomplete tasks and surface validation messages from the error envelope.
    - _Requirements: §4, §5, §6, §7, §8, §11; Design §2, §3 (decoupled frontend)_

  - [ ]* 15.2 Add frontend usability polish
    - Confirmation on delete, friendly empty states, and clearer workload presentation.
    - _Requirements: §11; Design §2_

- [ ] 16. Final wiring and run
  - [ ] 16.1 Wire the app end to end and document how to run it
    - Confirm `app/main.py` serves the API and the `frontend/` is reachable (static mount or separate static serving), and add README/run notes with the uvicorn command and test command. No new business logic.
    - _Requirements: §4, §9, §12; Design §3, §4_

- [ ] 17. Final checkpoint — full MVP verified
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (extra edge-case tests and frontend polish) and can be skipped for a faster MVP; the core backend, pure planning logic, their property tests, the API/integration tests, and the minimal frontend are required.
- Each task references the specific `docs/requirements.md` and `docs/design.md` sections it implements, by their section numbers in those files.
- The pure planning core (intervals, workload, daily plan) is implemented and tested in isolation before any service or API wiring.
- Property-based tests use `hypothesis` with a minimum of 100 iterations and are tagged `Feature: flowly-mvp, Property {number}: {property_text}`. Planning-core properties (9–16) map to the pure-function tests; CRUD/view properties (1–8, 17, 18) map to the service/API tests.
- Checkpoints ensure incremental validation at the end of the planning core, the backend, and the full MVP.
- Out-of-scope features (Canvas, Google Calendar, email, transit, notifications, ML/AI, analytics, internship tracking, multi-user, auth) are deliberately excluded per `docs/requirements.md` §15.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["3.1", "6.1"] },
    { "id": 2, "tasks": ["3.2", "6.2", "6.3", "7.1"] },
    { "id": 3, "tasks": ["4.1", "4.2", "5.1", "5.2", "5.3", "7.2", "7.3", "7.4", "7.5", "7.6", "8.1"] },
    { "id": 4, "tasks": ["10.1", "10.3", "11.1", "8.2", "8.3", "8.4", "8.5", "8.6"] },
    { "id": 5, "tasks": ["10.2", "10.4", "10.5", "12.1", "12.2"] },
    { "id": 6, "tasks": ["10.6", "12.3"] },
    { "id": 7, "tasks": ["12.4"] },
    { "id": 8, "tasks": ["13.1", "13.2", "13.3", "13.4"] },
    { "id": 9, "tasks": ["15.1"] },
    { "id": 10, "tasks": ["15.2", "16.1"] }
  ]
}
```
