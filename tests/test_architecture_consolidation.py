"""Architecture consolidation guards.

These tests lock the single-source-of-truth decisions so a later change cannot
quietly reintroduce a duplicate:

* one Telegram client implementation and one DB engine/session factory;
* one Pydantic schema per name (no two modules defining the same class);
* one canonical API route per method + full path;
* one frontend request helper (the single API client).
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend" / "app"
SCHEMAS = BACKEND / "api" / "schemas"
MODELS = BACKEND / "db" / "models"
V1 = BACKEND / "api" / "v1"
FRONTEND_API = REPO / "frontend" / "src" / "api"

_CLASS_RE = re.compile(r"^class (\w+)")
_ROUTE_RE = re.compile(r'@(\w+)\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']')
_PREFIX_RE = re.compile(r'(\w+)\s*=\s*APIRouter\(\s*prefix\s*=\s*["\']([^"\']*)["\']')
_INCLUDE_RE = re.compile(r"include_router\(\s*([\w.]+)")


def _iter_py(folder: Path):
    for path in sorted(folder.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _rel(path: Path, root: Path) -> str:
    """A readable path for a message, relative to ``root`` when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _class_names(folder: Path) -> dict[str, list[str]]:
    names: dict[str, list[str]] = defaultdict(list)
    for path in _iter_py(folder):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _CLASS_RE.match(line)
            if match:
                names[match.group(1)].append(_rel(path, folder))
    return names


def test_no_duplicate_schema_class_names() -> None:
    duplicates = {name: where for name, where in _class_names(SCHEMAS).items() if len(where) > 1}
    assert duplicates == {}, f"duplicate Pydantic schema class names: {duplicates}"


def test_no_duplicate_db_model_class_names() -> None:
    duplicates = {name: where for name, where in _class_names(MODELS).items() if len(where) > 1}
    assert duplicates == {}, f"duplicate DB model class names: {duplicates}"


def test_schema_names_do_not_shadow_service_or_gateway_names() -> None:
    """A DTO must not reuse a domain/service class name (keeps imports unambiguous)."""
    schema_names = set(_class_names(SCHEMAS))
    services = set(_class_names(BACKEND / "services"))
    gateway = set(_class_names(BACKEND / "ai" / "gateway"))
    clashes = schema_names & (services | gateway)
    assert clashes == set(), f"schema classes shadowing service/gateway names: {sorted(clashes)}"


def _registered_routes() -> dict[tuple[str, str], list[str]]:
    """Map (METHOD, full_path) -> list of defining modules, resolving router prefixes."""
    routes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in _iter_py(V1):
        if path.name == "router.py":
            continue
        text = path.read_text(encoding="utf-8")
        # Every router variable declared in this module -> its prefix.
        prefixes = dict(_PREFIX_RE.findall(text))
        for line in text.splitlines():
            match = _ROUTE_RE.search(line)
            if not match:
                continue
            router_var = match.group(1)
            if router_var not in prefixes:
                continue
            full = f"/api/v1{prefixes[router_var]}{match.group(3)}"
            routes[(match.group(2).upper(), full)].append(path.name)
    return routes


def test_no_duplicate_api_route() -> None:
    routes = _registered_routes()
    duplicates = {
        key: modules for key, modules in routes.items() if len(modules) > 1
    }
    assert duplicates == {}, f"duplicate (method, path) registrations: {duplicates}"


def test_notification_settings_have_one_canonical_route() -> None:
    routes = _registered_routes()
    assert ("GET", "/api/v1/notifications/settings") in routes
    assert ("PUT", "/api/v1/notifications/settings") in routes
    # The legacy manager duplicates were consolidated away.
    assert ("GET", "/api/v1/manager/notifications") not in routes
    assert ("PUT", "/api/v1/manager/notifications") not in routes
    assert ("GET", "/api/v1/manager/status") in routes


def test_single_telegram_client_implementation() -> None:
    """Telegram client classes are only imported inside providers/ (D-001).

    A bare ``import telethon`` availability probe (e.g. Diagnostics) is not a
    client implementation, so only ``from ... import`` is treated as a client use.
    """
    offenders: list[str] = []
    for path in _iter_py(BACKEND):
        if path.parts[-2] == "providers":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("from aiogram import", "from telethon import")):
                offenders.append(f"{_rel(path, BACKEND)}:{lineno}")
            if "TelegramClient(" in stripped:
                offenders.append(f"{_rel(path, BACKEND)}:{lineno}")
    assert offenders == [], f"Telegram clients constructed outside providers/: {offenders}"


def test_single_database_engine_factory() -> None:
    offenders: list[str] = []
    for path in _iter_py(BACKEND):
        text = path.read_text(encoding="utf-8")
        if "create_async_engine(" in text or "async_sessionmaker(" in text:
            offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == ["backend/app/db/session.py"], (
        f"database engine/session factory must live only in db/session.py: {offenders}"
    )


def test_single_frontend_api_request_helper() -> None:
    helpers: list[str] = []
    for path in sorted((REPO / "frontend" / "src").rglob("*.ts")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(async function request|function request<)", line):
                helpers.append(f"{path.relative_to(REPO)}:{lineno}")
    assert helpers == ["frontend/src/api/client.ts:20"], (
        f"the API request helper must be defined once in api/client.ts: {helpers}"
    )
    assert (FRONTEND_API / "client.ts").exists()


def _duplicate_class_names(folder: Path) -> dict[str, list[str]]:
    return {name: where for name, where in _class_names(folder).items() if len(where) > 1}


def test_no_duplicate_class_names_anywhere_in_backend() -> None:
    """One class name = one definition across the whole backend.

    A name reused by two different subsystems (e.g. a transport ``HttpResponse``
    and a provider ``ProviderInfo``) is exactly the ambiguity this consolidation
    removes: imports and tracebacks must not depend on which module you happened
    to import. Distinct concepts get distinct names (``BackupHttpResponse``,
    ``BackupProviderInfo``, ``GraphCapability``, ``NotificationDeliveryResult``).
    """
    duplicates = _duplicate_class_names(BACKEND)
    assert duplicates == {}, f"duplicate class names in backend/app: {duplicates}"


_CANONICAL_NAMES = {
    "backend/app/services/notification_destinations.py": (
        "NotificationDeliveryResult",
        "DeliveryResult",
    ),
    "backend/app/services/backup_backends/base.py": ("BackupProviderStatus", "ProviderStatus"),
    "backend/app/services/backup_backends/http.py": ("BackupHttpResponse", "HttpResponse"),
    "backend/app/services/capability_graph.py": ("GraphCapability", "Capability"),
}


def _canonical_name_violations() -> list[str]:
    offenders: list[str] = []
    for rel, (canonical, legacy) in _CANONICAL_NAMES.items():
        text = (REPO / rel).read_text(encoding="utf-8")
        if not re.search(rf"^class {canonical}\b", text, re.M):
            offenders.append(f"{rel}: missing canonical class {canonical}")
        if re.search(rf"^class {legacy}\b", text, re.M):
            offenders.append(f"{rel}: ambiguous legacy class {legacy} is back")
    return offenders


def test_consolidated_type_names_are_canonical() -> None:
    """The ambiguous duplicate names stay renamed (regression guard)."""
    assert _canonical_name_violations() == [], "; ".join(_canonical_name_violations())


def _mock_stub_classes(folder: Path) -> list[str]:
    offenders: list[str] = []
    pattern = re.compile(r"^class \w*(Mock|Stub|Dummy)\w*", re.IGNORECASE)
    for path in _iter_py(folder):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.match(line):
                offenders.append(f"{_rel(path, folder)}:{lineno}")
    return offenders


def test_no_mock_stub_or_dummy_classes_in_production() -> None:
    """Test doubles live in tests/, never in the shipped backend."""
    offenders = _mock_stub_classes(BACKEND)
    assert offenders == [], f"mock/stub/dummy classes must not ship in backend/app: {offenders}"


def _todo_markers(roots: list[Path]) -> list[str]:
    pattern = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
    offenders: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".vue"}:
                continue
            if "__pycache__" in path.parts or path.parts[-2:-1] == ("static",):
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{_rel(path, root)}:{lineno}")
    return offenders


def test_no_todo_markers_in_production() -> None:
    """No TODO/FIXME/XXX/HACK markers left in the shipped backend or SPA."""
    offenders = _todo_markers([BACKEND, REPO / "frontend" / "src"])
    assert offenders == [], f"TODO/FIXME markers must not ship: {offenders}"


def _protocol_method_ids(tree: ast.AST) -> set[int]:
    """``id()`` of every method declared directly on a Protocol/ABC class."""
    ids: set[int] = set()
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        if not any(ast.unparse(b).endswith(("Protocol", "ABC")) for b in cls.bases):
            continue
        for member in cls.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ids.add(id(member))
    return ids


def _placeholder_function_bodies(folder: Path) -> list[str]:
    """Production functions whose only statement is ``pass`` or a bare ``...``.

    ``...`` is allowed only on a Protocol/ABC interface method; a bare ``pass``
    is never allowed in the shipped backend.
    """
    offenders: list[str] = []
    for path in _iter_py(folder):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        interface_methods = _protocol_method_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [
                n
                for n in node.body
                if not (
                    isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str)
                )
            ]
            if len(body) != 1:
                continue
            only = body[0]
            if isinstance(only, ast.Pass):
                offenders.append(f"{_rel(path, folder)}:{node.lineno}: {node.name} -> pass")
            elif (
                isinstance(only, ast.Expr)
                and isinstance(only.value, ast.Constant)
                and only.value.value is Ellipsis
                and id(node) not in interface_methods
            ):
                offenders.append(f"{_rel(path, folder)}:{node.lineno}: {node.name} -> ...")
    return offenders


def test_no_placeholder_function_bodies_in_production() -> None:
    """A production function must do something (no stub masquerading as real)."""
    offenders = _placeholder_function_bodies(BACKEND)
    assert offenders == [], f"placeholder function bodies in production code: {offenders}"


def test_fake_guards_catch_injected_defects(tmp_path: Path) -> None:
    """Prove the fake/stub guards are not decorative.

    Each detector must flag a defect when one is injected — otherwise the guard
    could pass forever while a stub quietly ships. This mirrors the runtime
    meta-audit's "removing the detector flips the mutation" idea.
    """
    probe = tmp_path / "app"
    (probe / "services").mkdir(parents=True)
    (probe / "services" / "zz_dup_a.py").write_text(
        "class GraphCapability:\n    pass\n", encoding="utf-8"
    )
    (probe / "services" / "zz_dup_b.py").write_text(
        "class GraphCapability:\n    pass\n", encoding="utf-8"
    )
    assert "GraphCapability" in _duplicate_class_names(probe)

    (probe / "services" / "zz_mock.py").write_text(
        "class MockThing:\n    pass\n", encoding="utf-8"
    )
    assert _mock_stub_classes(probe), "the mock-class detector must flag MockThing"

    (probe / "services" / "zz_stub.py").write_text(
        "def compute():\n    ...\n\n\nasync def fetch():\n    pass\n", encoding="utf-8"
    )
    flagged = _placeholder_function_bodies(probe)
    assert any("compute" in line for line in flagged), flagged
    assert any("fetch" in line for line in flagged), flagged

    (probe / "services" / "zz_todo.py").write_text("# TODO: real work\n", encoding="utf-8")
    assert _todo_markers([probe]), "the TODO detector must flag a TODO marker"
