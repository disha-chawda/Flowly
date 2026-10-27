"""Static boundary checks for the pure ``app.ics`` parsing core.

Every ``.py`` file under ``app/ics`` is parsed with ``ast`` (never imported), so
modules added later are covered automatically. The checks enforce that the core
stays free of the database, web framework, service layers, ``dateutil``, the
clock, environment state, and direct file access.

Reading the time zone database through ``importlib.resources`` (for example
``files("tzdata.zoneinfo").joinpath(key).open("rb")``) is allowed by
Requirement 12.2, so only the builtin ``open`` and ``io.open`` are banned, not
``.open`` methods on resource objects.

Validates: Requirements 12.1, 12.2, 15.3
"""

import ast
from pathlib import Path

import pytest

ICS_DIR = Path(__file__).resolve().parents[2] / "app" / "ics"

FORBIDDEN_MODULES = (
    "sqlalchemy",
    "fastapi",
    "starlette",
    "app.data",
    "app.services",
    "app.api",
    "dateutil",
)

# Dotted attribute chains that read the clock or the environment.
FORBIDDEN_ATTRIBUTES = (
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "date.today",
    "time.time",
    "os.environ",
    "os.getenv",
)

# Names that would bypass FORBIDDEN_ATTRIBUTES through ``from X import Y``.
FORBIDDEN_FROM_IMPORTS = {
    "time": {"time", "time_ns"},
    "os": {"environ", "getenv"},
}

FORBIDDEN_OPEN = ("open", "io.open", "builtins.open")


def _module_files():
    return sorted(ICS_DIR.rglob("*.py"))


def _package_of(path: Path) -> str:
    # Both ``pkg/mod.py`` and ``pkg/__init__.py`` resolve relative imports against ``pkg``.
    relative = path.relative_to(ICS_DIR.parents[1]).with_suffix("")
    return ".".join(relative.parts[:-1])


def _resolve_from(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    base = package.split(".")
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _matches(name: str, pattern: str) -> bool:
    return name == pattern or name.endswith("." + pattern)


def _is_forbidden_module(name: str) -> bool:
    return any(name == m or name.startswith(m + ".") for m in FORBIDDEN_MODULES)


def find_violations(source: str, package: str = "app.ics") -> list[str]:
    """Return a description of every boundary violation in ``source``."""
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    violations.append(f"line {line}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from(node, package)
            if _is_forbidden_module(module):
                violations.append(f"line {line}: from {module} import ...")
            for alias in node.names:
                if _is_forbidden_module(f"{module}.{alias.name}"):
                    violations.append(f"line {line}: from {module} import {alias.name}")
                if alias.name in FORBIDDEN_FROM_IMPORTS.get(module, ()):
                    violations.append(f"line {line}: from {module} import {alias.name}")
                if module in ("builtins", "io") and alias.name == "open":
                    violations.append(f"line {line}: from {module} import open")
        elif isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted is None:
                continue
            for pattern in FORBIDDEN_ATTRIBUTES:
                if _matches(dotted, pattern):
                    violations.append(f"line {line}: uses {dotted}")
            if dotted in FORBIDDEN_OPEN:
                violations.append(f"line {line}: uses {dotted}")
        elif isinstance(node, ast.Name) and node.id == "open":
            violations.append(f"line {line}: uses builtin open")
    return violations


def test_package_has_modules():
    names = {path.name for path in _module_files()}
    assert {"__init__.py", "types.py"} <= names


@pytest.mark.parametrize(
    "path", _module_files(), ids=lambda p: p.relative_to(ICS_DIR).as_posix()
)
def test_module_respects_boundary(path):
    source = path.read_text(encoding="utf-8")
    assert find_violations(source, _package_of(path)) == []


@pytest.mark.parametrize(
    "source",
    [
        "import sqlalchemy",
        "from sqlalchemy.orm import Session",
        "import fastapi",
        "from starlette.requests import Request",
        "from app.data.models import Commitment",
        "from app.data import models",
        "from app import data",
        "from app.services.task_service import TaskService",
        "import app.api.errors",
        "from dateutil import rrule",
        "from ..data import models",
        "from datetime import datetime\nx = datetime.now()",
        "import datetime\nx = datetime.datetime.utcnow()",
        "from datetime import date\nx = date.today()",
        "import time\nx = time.time()",
        "from time import time",
        "import os\nx = os.environ['TZ']",
        "from os import environ",
        "f = open('x.ics')",
        "import io\nf = io.open('x.ics')",
    ],
)
def test_checker_detects_violations(source):
    """The checker itself must flag each banned pattern, so the boundary test is not vacuous."""
    assert find_violations(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "from datetime import datetime, timedelta, timezone",
        "from zoneinfo import ZoneInfo",
        "from importlib.resources import files\n"
        "f = files('tzdata.zoneinfo').joinpath('UTC').open('rb')",
        "from app.ics.types import SkipReason",
        "from .types import SkipReason",
    ],
)
def test_checker_allows_permitted_code(source):
    assert find_violations(source) == []
