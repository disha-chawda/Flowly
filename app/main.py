"""FLOWLY application entry point.

Assembles the FastAPI application described in Design §3–§4: it creates the app
instance, wires the three feature routers (tasks, commitments, dashboard), and
registers the centralized error handlers (`app/api/errors.py`) so every failure
path shares the single error envelope. It also ensures the SQLite schema exists
before the app serves traffic.

This module is deliberately wiring-only — it contains no business logic. The
ORM models (`app/data/models.py`) are imported for their side effect of
registering the ``Task`` and ``Commitment`` tables on the declarative metadata,
so that the ``create_all`` helper (`app/data/database.py`) has every table to
create at startup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

# Imported for the registration side effect: binding the ORM models to the
# declarative ``Base.metadata`` so ``create_all`` can create their tables.
from app.data import models  # noqa: F401
from app.data.database import create_all
from app.api.errors import register_error_handlers
from app.api.tasks import router as tasks_router
from app.api.commitments import router as commitments_router
from app.api.dashboard import router as dashboard_router

@asynccontextmanager
async def lifespan(app):
    create_all()
    yield


def create_app() -> FastAPI:
    """Build and return the fully wired FLOWLY FastAPI application.

    Registers the feature routers and the centralized error handlers, and
    ensures the database tables exist on startup via the ``startup`` event so
    the schema is created once when the application boots.
    """
    app = FastAPI(title="FLOWLY", lifespan = lifespan)

    register_error_handlers(app)

    app.include_router(tasks_router)
    app.include_router(commitments_router)
    app.include_router(dashboard_router)



    return app


app = create_app()
