"""Centralized API error handling.

Implements the single, consistent error envelope described in Design
"Error Handling". Every error path — request validation failures and
not-found conditions — is serialized to the same shape so the frontend can
always parse failures uniformly and no endpoint invents its own format::

    {
      "error": {
        "type": "validation_error",          # or "not_found"
        "message": "Request validation failed",
        "details": [
          { "field": "title", "issue": "must be between 1 and 200 characters" }
        ]
      }
    }

The handlers map:

* FastAPI :class:`~fastapi.exceptions.RequestValidationError` -> ``422``
  ``validation_error`` with one field-level detail per offending field.
* :class:`app.services.task_service.TaskNotFoundError` and
  :class:`app.services.commitment_service.CommitmentNotFoundError` -> ``404``
  ``not_found``.
* :class:`app.services.commitment_service.InvalidCommitmentIntervalError`
  (a service-level validation failure on partial commitment updates) -> ``422``
  ``validation_error`` with an ``end_time`` field-level detail.

The module is framework-aware (FastAPI / Starlette) but otherwise
self-contained. Call :func:`register_error_handlers` from ``app/main.py`` to
wire the handlers onto the application.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.services.commitment_service import (
    CommitmentNotFoundError,
    InvalidCommitmentIntervalError,
)
from app.services.task_service import TaskNotFoundError

# Error ``type`` discriminators used in the envelope (Design "Error Handling").
VALIDATION_ERROR = "validation_error"
NOT_FOUND = "not_found"

# Location prefixes FastAPI/Pydantic prepend to an error ``loc`` tuple. These
# identify *where* a value came from (request body, query string, ...) rather
# than naming the offending field, so they are stripped when deriving ``field``.
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def error_response(
    status_code: int,
    type: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Build the standard error envelope as a :class:`JSONResponse`.

    This is the single place the envelope shape from Design "Error Handling" is
    constructed, so every handler produces an identical structure.

    Args:
        status_code: HTTP status code for the response (e.g. ``404``, ``422``).
        type: Error discriminator — :data:`VALIDATION_ERROR` or
            :data:`NOT_FOUND`.
        message: Human-readable summary of the failure.
        details: Field-level details, each a ``{"field", "issue"}`` mapping.
            Defaults to an empty list when omitted.

    Returns:
        A :class:`JSONResponse` whose body is ``{"error": {...}}``.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": type,
                "message": message,
                "details": details if details is not None else [],
            }
        },
    )


def _field_from_loc(loc: tuple[Any, ...]) -> str:
    """Derive a human-facing field name from a Pydantic error ``loc`` tuple.

    FastAPI reports the location as a tuple such as ``("body", "title")`` or
    ``("body", "items", 0, "name")``. The leading source prefix (``body``,
    ``query`` ...) is dropped, and the remaining path segments are joined with
    dots so nested and indexed fields stay identifiable. When only the prefix is
    present, the prefix itself is returned so the detail is never blank.
    """
    parts = list(loc)
    if parts and parts[0] in _LOC_PREFIXES:
        parts = parts[1:]
    if not parts:
        # Only the prefix was present (e.g. a malformed/empty body).
        return str(loc[0]) if loc else ""
    return ".".join(str(part) for part in parts)


async def _handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Serialize a FastAPI request-validation failure to a ``422`` envelope.

    Each entry from :meth:`RequestValidationError.errors` becomes one
    ``{"field", "issue"}`` detail: ``field`` derived from the error ``loc``
    (minus the source prefix) and ``issue`` taken from the error ``msg``.
    """
    details = [
        {"field": _field_from_loc(err.get("loc", ())), "issue": err.get("msg", "")}
        for err in exc.errors()
    ]
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        type=VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
    )


async def _handle_task_not_found(
    request: Request, exc: TaskNotFoundError
) -> JSONResponse:
    """Map a missing task id to a ``404`` ``not_found`` envelope."""
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        type=NOT_FOUND,
        message=str(exc),
        details=[],
    )


async def _handle_commitment_not_found(
    request: Request, exc: CommitmentNotFoundError
) -> JSONResponse:
    """Map a missing commitment id to a ``404`` ``not_found`` envelope."""
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        type=NOT_FOUND,
        message=str(exc),
        details=[],
    )


async def _handle_invalid_commitment_interval(
    request: Request, exc: InvalidCommitmentIntervalError
) -> JSONResponse:
    """Map an invalid commitment interval to a ``422`` ``validation_error``.

    This service-level validation guards partial updates that would leave
    ``end_time`` at or before ``start_time`` — a case the per-field schema
    validation cannot catch. It is reported as a field-level detail on
    ``end_time`` so clients surface it like any other validation failure.
    """
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        type=VALIDATION_ERROR,
        message="Request validation failed",
        details=[{"field": "end_time", "issue": str(exc)}],
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register every error handler onto ``app``.

    Called once during application setup (``app/main.py``) so all error paths
    share the centralized envelope from Design "Error Handling".
    """
    app.add_exception_handler(
        RequestValidationError, _handle_request_validation_error
    )
    app.add_exception_handler(TaskNotFoundError, _handle_task_not_found)
    app.add_exception_handler(
        CommitmentNotFoundError, _handle_commitment_not_found
    )
    app.add_exception_handler(
        InvalidCommitmentIntervalError, _handle_invalid_commitment_interval
    )
