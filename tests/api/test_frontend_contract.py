"""Contract checks between the static frontend and the REST API.

The frontend (`frontend/`) is vanilla JS with no build or JS test runner, so
these tests guard the integration points that can drift silently:

* every API path the frontend calls exists as a route on the FastAPI app;
* the priority/category options offered in the forms are exactly the values
  the API accepts;
* status messages are announced through an aria-live region.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.enums import Category, Priority
from app.main import app

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")

_PARAM = re.compile(r"\$\{[^}]+\}|\{[^}]+\}")


def _normalize(path: str) -> str:
    """Replace JS template params and FastAPI path params with one placeholder."""
    return _PARAM.sub("{param}", path)


def _api_routes() -> set[tuple[str, str]]:
    """(METHOD, path) pairs exposed by the API, read from its OpenAPI schema."""
    return {
        (method.upper(), _normalize(path))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def _frontend_calls() -> set[tuple[str, str]]:
    """Extract (METHOD, path) pairs from the `api(...)` calls in app.js."""
    calls = set()
    pattern = re.compile(
        r"api\(\s*[`\"](/[^`\"?]*)[^`\"]*[`\"]\s*(?:,\s*\{\s*method:\s*\"(\w+)\")?"
    )
    for path, method in pattern.findall(APP_JS):
        calls.add((method or "GET", _normalize(path)))
    return calls


def _select_options(select_id: str) -> set[str]:
    match = re.search(
        rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', INDEX_HTML, re.S
    )
    assert match, f"select #{select_id} missing from index.html"
    return set(re.findall(r'<option value="([^"]+)"', match.group(1)))


def test_frontend_files_exist():
    for name in ("index.html", "app.js", "styles.css"):
        assert (FRONTEND / name).is_file(), name


def test_every_frontend_api_call_matches_a_backend_route():
    calls = _frontend_calls()
    # Sanity: the frontend covers task CRUD + completion, commitment CRUD, and
    # all four dashboard views.
    assert len(calls) == 13, sorted(calls)
    missing = calls - _api_routes()
    assert not missing, f"frontend calls endpoints the API does not expose: {sorted(missing)}"


def test_form_options_match_api_enums():
    assert _select_options("task-priority") == {p.value for p in Priority}
    assert _select_options("task-category") == {c.value for c in Category}


def test_status_region_is_announced():
    assert re.search(r'id="status"[^>]*aria-live="polite"', INDEX_HTML)
