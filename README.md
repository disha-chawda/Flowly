# FLOWLY | Student's Pulse

An intelligent student life management platform designed to bring academic, work, personal, career, and transportation responsibilities into one personalized planning system.

This repository contains the **FLOWLY MVP**: task and commitment management, a dashboard (today, upcoming, workload summary), and a deterministic daily plan. See `docs/requirements.md` and `docs/design.md` for the full scope.

## Setup

Requires Python 3.12 (3.10+ should work).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run

From the repository root:

```powershell
uvicorn app.main:app --reload
```

Then open:

- Frontend: http://127.0.0.1:8000/app/ (http://127.0.0.1:8000/ redirects there)
- Interactive API docs: http://127.0.0.1:8000/docs

The frontend is served by the same FastAPI app, so it talks to the API on the same origin and no CORS setup is needed. To point the page at a different API server, add `?api=http://host:port` to the page URL or set the `flowly-api-base` meta tag in `frontend/index.html`. A separately hosted frontend would need CORS enabled on the API, which the MVP does not do.

Data is stored in a local SQLite file, `flowly.db`, in the directory you start uvicorn from. Tables are created on startup. The database URL is set in `app/config.py`.

## Test

```powershell
python -m pytest
```

`pytest.ini` points discovery at `tests/unit` and `tests/api`. Tests use temporary SQLite databases and FastAPI's `TestClient`, so they need no running server and no network access. Property-based tests use `hypothesis`.

## Architecture

A three-layer FastAPI backend with a pure planning core and a decoupled static frontend (Design §3–§4).

| Path | Responsibility |
|---|---|
| `app/main.py` | Builds the FastAPI app: registers routers and error handlers, creates tables on startup, serves `frontend/` at `/app/`. Wiring only. |
| `app/config.py` | Settings, including `DATABASE_URL` (SQLite now, swappable to PostgreSQL). |
| `app/api/` | HTTP layer. `tasks.py`, `commitments.py`, `dashboard.py` routers; `errors.py` maps validation (422) and not-found (404) errors to one error envelope. |
| `app/schemas/` | Pydantic request/response models and boundary validation. |
| `app/services/` | Use cases: task and commitment CRUD/completion, today/upcoming views, workload and daily-plan orchestration. |
| `app/planning/` | Pure, side-effect-free functions: interval union, workload calculation, daily-plan ordering and fitting. |
| `app/data/` | SQLAlchemy engine/session, ORM models, and repositories. |
| `app/domain/` | Shared enums (`Priority`, `Category`, `Completion`, `Source`). |
| `frontend/` | Static HTML + vanilla JS + CSS that uses only the REST API. |
| `tests/unit/`, `tests/api/` | Pure-function, service, and API/integration tests. |

Main API routes: `/tasks`, `/tasks/{id}`, `/tasks/{id}/completion`, `/commitments`, `/commitments/{id}`, and `/dashboard/today`, `/dashboard/upcoming`, `/dashboard/workload`, `/dashboard/daily-plan`.

## Security note

The MVP is a single-user, local app with **no authentication or authorization**. Anyone who can reach the server can read and change all data. Keep uvicorn bound to localhost (the default, `127.0.0.1`) and don't expose it with `--host 0.0.0.0` or on a shared network.
