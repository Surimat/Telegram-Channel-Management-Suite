"""Static consistency checks (v1.5).

Pure, deterministic checks over the codebase itself — no database, no network.
They run both in the runtime auditor (:mod:`backend.app.services.consistency`)
and in CI (``tests/test_architecture_consistency.py``), so drift is caught on
every pull request (D-092/D-093).

Everything here is intentionally tolerant: heuristic checks emit ``info`` /
``warning`` rather than ``error`` and never depend on source line ordering.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.app.core import i18n
from backend.app.services.capability_graph import (
    ALL_REQUIREMENTS,
    CAPABILITIES,
)
from backend.app.services.consistency_types import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Finding,
)

# Repository root: .../backend/app/services/consistency_checks.py -> parents[3]
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend" / "app"
FRONTEND = ROOT / "frontend" / "src"
MIGRATIONS = ROOT / "migrations" / "versions"
DOCS = ROOT / "docs"

#: Modules whose user-facing strings are localized by the central catalog.
LOCALIZED_MODULES = ("i18n.py", "help_topics.py")


def run_static_checks() -> list[Finding]:
    """Run every static check and return the raw findings."""
    findings: list[Finding] = []
    for check in (
        check_api_route_frontend_client,
        check_frontend_route_view,
        check_model_migration,
        check_scheduler_job_handlers,
        check_provider_registry,
        check_capability_registry,
        check_i18n_completeness,
        check_help_catalog_usage,
        check_documented_endpoints,
        check_orphan_help_ids,
    ):
        try:
            findings.extend(check())
        except Exception:  # pragma: no cover - a check must never crash the page
            continue
    return findings


# ---------------------------------------------------------------------------
# 1. API route ↔ frontend client
# ---------------------------------------------------------------------------
def _api_prefixes() -> set[str]:
    """Return every API path segment the backend exposes (prefixes + routes).

    Combines ``APIRouter(prefix=...)`` declarations with the paths on route
    decorators, so routers without a prefix (e.g. ``product`` → ``/promotion``,
    ``/update``) are detected too.
    """
    prefixes = set(_router_prefixes())
    for path in (BACKEND / "api" / "v1").glob("*.py"):
        if path.name == "router.py":
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r'@router\.(?:get|post|put|patch|delete)\(\s*"([^"]*)"', text
        ):
            seg = match.group(1).strip("/").split("/")[0]
            if seg and seg not in {"api", "v1"}:
                prefixes.add(seg)
    return prefixes


def _router_prefixes() -> set[str]:
    """Return only the declared ``APIRouter(prefix=...)`` names."""
    prefixes: set[str] = set()
    for path in (BACKEND / "api" / "v1").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'APIRouter\(prefix="([^"]+)"', text):
            prefixes.add(match.group(1).strip("/").split("/")[0])
    return prefixes


def _frontend_api_prefixes() -> set[str]:
    client = FRONTEND / "api" / "client.ts"
    text = client.read_text(encoding="utf-8")
    prefixes: set[str] = set()
    for match in re.finditer(r"/api/v1/([A-Za-z0-9_\-]+)", text):
        prefixes.add(match.group(1))
    return prefixes


def check_api_route_frontend_client() -> list[Finding]:
    """Every backend API area the frontend calls must exist (and vice versa)."""
    findings: list[Finding] = []
    backend = _api_prefixes()
    frontend = _frontend_api_prefixes()
    unknown = sorted(frontend - backend)
    if unknown:
        findings.append(
            Finding(
                id="api.frontend_unknown",
                category="api",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="Frontend вызывает несуществующий API-раздел",
                detail="Разделы: " + ", ".join(unknown) + ".",
                why="Вызов несуществующего маршрута всегда завершится ошибкой.",
                how_to_fix="Исправьте путь в frontend/src/api/client.ts или добавьте роутер.",
                subsystem="api",
            )
        )
    # Informational: backend routers the frontend does not call yet (some are
    # intentionally API-only, e.g. mesh/queue). Uses declared router prefixes
    # only, so sub-route segments do not create noise.
    unused = sorted(_router_prefixes() - frontend - {"health"})
    if unused:
        findings.append(
            Finding(
                id="api.backend_unused",
                category="orphan",
                severity=SEVERITY_INFO,
                confidence="low",
                title="API-разделы без вызовов из frontend",
                detail="Разделы: " + ", ".join(unused) + ".",
                why="Может быть намеренно API-only, но иногда указывает на мёртвый код.",
                how_to_fix=(
                    "Проверьте, нужен ли раздел в UI, "
                    "или задокументируйте его как API-only."
                ),
                subsystem="api",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 2. Frontend route ↔ actual view
# ---------------------------------------------------------------------------
def check_frontend_route_view() -> list[Finding]:
    """Every lazy route import must point at a real .vue file."""
    findings: list[Finding] = []
    router = FRONTEND / "router.ts"
    if not router.is_file():
        return findings
    text = router.read_text(encoding="utf-8")
    for match in re.finditer(r"import\('(@/views/[^']+)'\)", text):
        rel = match.group(1).replace("@/", "")
        target = FRONTEND / rel
        if not target.is_file():
            findings.append(
                Finding(
                    id=f"frontend.route.{rel}",
                    category="frontend",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Маршрут указывает на отсутствующий экран",
                    detail=f"Не найден файл: {rel}.",
                    why="Открытие такого маршрута покажет пустую страницу.",
                    how_to_fix="Создайте экран или исправьте путь в router.ts.",
                    subsystem="frontend",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 3. DB model ↔ migration
# ---------------------------------------------------------------------------
def _model_tables() -> set[str]:
    tables: set[str] = set()
    for path in (BACKEND / "db" / "models").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'__tablename__\s*=\s*"([^"]+)"', text):
            tables.add(match.group(1))
    return tables


def _migration_created_tables() -> set[str]:
    tables: set[str] = set()
    for path in MIGRATIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""create_table\(\s*["']([^"']+)["']""", text):
            tables.add(match.group(1))
    return tables


def check_model_migration() -> list[Finding]:
    """Every ORM table must be created by some migration."""
    findings: list[Finding] = []
    models = _model_tables()
    migrations = _migration_created_tables()
    missing = sorted(models - migrations)
    if missing:
        findings.append(
            Finding(
                id="db.model_without_migration",
                category="database",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="Модель без миграции",
                detail="Таблицы: " + ", ".join(missing) + ".",
                why="На существующей базе таблица не появится — приложение упадёт при запросе.",
                how_to_fix="Добавьте аддитивную Alembic-миграцию для этих таблиц.",
                subsystem="database",
            )
        )
    orphan = sorted(migrations - models)
    if orphan:
        findings.append(
            Finding(
                id="db.migration_without_model",
                category="database",
                severity=SEVERITY_INFO,
                confidence="medium",
                title="Миграция создаёт таблицу без модели",
                detail="Таблицы: " + ", ".join(orphan) + ".",
                why="Возможно, таблица устарела или модель переименована.",
                how_to_fix="Проверьте, не осталась ли таблица от старой версии.",
                subsystem="database",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 4. Scheduler job ↔ handler
# ---------------------------------------------------------------------------
def _job_kinds() -> set[str]:
    kinds: set[str] = set()
    for path in (BACKEND / "services").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'_JOB_KIND\s*=\s*"([^"]+)"', text):
            kinds.add(match.group(1))
    return kinds


def _registered_handlers() -> set[str]:
    handlers = ROOT / "backend" / "app" / "scheduler" / "handlers.py"
    text = handlers.read_text(encoding="utf-8")
    registered: set[str] = set()
    for match in re.finditer(r"scheduler\.register\(\s*([A-Z_]+)", text):
        registered.add(match.group(1))
    # Resolve the constant names to their string values, including the values
    # imported from the service modules (SCAN_JOB_KIND, ...).
    values = dict(re.findall(r'([A-Z_]+)\s*=\s*"([^"]+)"', text))
    for _module_name, module_path in (
        ("audience_service", "audience_service.py"),
        ("invite_service", "invite_service.py"),
        ("posting_service", "posting_service.py"),
        ("reaction_service", "reaction_service.py"),
    ):
        module_text = (BACKEND / "services" / module_path).read_text(encoding="utf-8")
        for name, value in re.findall(r'([A-Z_]+)\s*=\s*"([^"]+)"', module_text):
            values.setdefault(name, value)
    return {values.get(name, name) for name in registered}


def check_scheduler_job_handlers() -> list[Finding]:
    """Every job kind a service enqueues must have a registered handler."""
    findings: list[Finding] = []
    kinds = _job_kinds()
    handlers = _registered_handlers()
    missing = sorted(kinds - handlers)
    if missing:
        findings.append(
            Finding(
                id="scheduler.job_without_handler",
                category="scheduler",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="Задача планировщика без обработчика",
                detail="Виды задач: " + ", ".join(missing) + ".",
                why="Такая задача навсегда останется в очереди и не выполнится.",
                how_to_fix="Зарегистрируйте обработчик в scheduler/handlers.py.",
                subsystem="scheduler",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 5. Provider registry ↔ implementations
# ---------------------------------------------------------------------------
def check_provider_registry() -> list[Finding]:
    """Both a real and a fake implementation must exist for each provider kind."""
    findings: list[Finding] = []
    providers = BACKEND / "providers"
    required = {
        "bot": ("aiogram_bot.py", "fake_bot.py"),
        "session": ("telethon_session.py", "fake_session.py"),
        "audience": ("session_audience.py", "fake_audience.py"),
    }
    for kind, (real, fake) in required.items():
        for filename in (real, fake):
            if not (providers / filename).is_file():
                findings.append(
                    Finding(
                        id=f"providers.{kind}.{filename}",
                        category="providers",
                        severity=SEVERITY_ERROR,
                        confidence="high",
                        title="Провайдер отсутствует",
                        detail=f"Не найден {filename}.",
                        why="Тесты и офлайн-режим требуют пару «реальный + тестовый».",
                        how_to_fix="Добавьте недостающую реализацию провайдера.",
                        subsystem="providers",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 6. Capability registry
# ---------------------------------------------------------------------------
def check_capability_registry() -> list[Finding]:
    """Every capability requirement must be a known, described requirement."""
    findings: list[Finding] = []
    for cap in CAPABILITIES:
        for req in (*cap.requires, *cap.minimal):
            if req not in ALL_REQUIREMENTS:
                findings.append(
                    Finding(
                        id=f"capabilities.unknown_req.{cap.key}.{req}",
                        category="capabilities",
                        severity=SEVERITY_ERROR,
                        confidence="high",
                        title="Неизвестное требование в графе возможностей",
                        detail=f"Возможность {cap.key} ссылается на {req}.",
                        why="Граф возможностей и UI разойдутся.",
                        how_to_fix="Добавьте требование в ALL_REQUIREMENTS.",
                        subsystem="capabilities",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 7. i18n completeness
# ---------------------------------------------------------------------------
def check_i18n_completeness() -> list[Finding]:
    """Every message key must have both RU and EN text."""
    findings: list[Finding] = []
    for key, langs in i18n.missing_keys().items():
        findings.append(
            Finding(
                id=f"i18n.missing.{key}",
                category="i18n",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="Неполный перевод",
                detail=f"Ключ {key}: нет {', '.join(langs)}.",
                why="Пользователь увидит английский/русский текст вперемешку.",
                how_to_fix="Добавьте недостающий перевод в core/i18n.py.",
                subsystem="i18n",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 8. Help catalog ↔ UI usage
# ---------------------------------------------------------------------------
def _help_catalog_keys() -> set[str]:
    text = (BACKEND / "services" / "help_topics.py").read_text(encoding="utf-8")
    return set(re.findall(r'key="([a-z0-9_]+)"', text))


def _ui_help_topic_refs() -> set[str]:
    refs: set[str] = set()
    for path in FRONTEND.rglob("*.vue"):
        text = path.read_text(encoding="utf-8")
        refs.update(re.findall(r'<InfoHint\s+topic="([a-z0-9_]+)"', text))
        refs.update(re.findall(r'topic="([a-z0-9_]+)"', text))
    return refs


def check_help_catalog_usage() -> list[Finding]:
    """Every help topic the UI references must exist in the catalog."""
    findings: list[Finding] = []
    catalog = _help_catalog_keys()
    refs = _ui_help_topic_refs()
    missing = sorted(refs - catalog)
    if missing:
        findings.append(
            Finding(
                id="help.missing_topic",
                category="help",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="UI ссылается на несуществующую подсказку",
                detail="Ключи: " + ", ".join(missing) + ".",
                why="Пользователь не увидит пояснение рядом с элементом.",
                how_to_fix="Добавьте тему в help_topics.py или исправьте ключ в Vue.",
                subsystem="help",
            )
        )
    return findings


def check_orphan_help_ids() -> list[Finding]:
    """Report catalog topics no UI hint references (informational)."""
    findings: list[Finding] = []
    catalog = _help_catalog_keys()
    refs = _ui_help_topic_refs()
    orphans = sorted(catalog - refs)
    if orphans:
        findings.append(
            Finding(
                id="help.orphan_topics",
                category="orphan",
                severity=SEVERITY_INFO,
                confidence="low",
                title="Темы справки без использования в UI",
                detail="Ключи: " + ", ".join(orphans) + ".",
                why="Тема может быть задумана для Mini App или документации.",
                how_to_fix="Используйте тему в InfoHint или задокументируйте её назначение.",
                subsystem="help",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 9. Documented endpoint ↔ actual endpoint
# ---------------------------------------------------------------------------
def check_documented_endpoints() -> list[Finding]:
    """Endpoints listed in docs/API.md should exist in the router tree."""
    findings: list[Finding] = []
    api_doc = DOCS / "API.md"
    if not api_doc.is_file():
        return findings
    text = api_doc.read_text(encoding="utf-8")
    documented = set(re.findall(r"/api/v1/([A-Za-z0-9_\-]+)", text))
    known = _api_prefixes()
    # Prefixes the docs mention that are not real routers.
    unknown = sorted(p for p in documented if p not in known and p not in {"v1"})
    if unknown:
        findings.append(
            Finding(
                id="docs.api_unknown_prefix",
                category="docs",
                severity=SEVERITY_WARNING,
                confidence="medium",
                title="Документация упоминает неизвестный API-раздел",
                detail="Разделы: " + ", ".join(unknown) + ".",
                why="Документация расходится с реальными маршрутами.",
                how_to_fix="Обновите docs/API.md или добавьте роутер.",
                subsystem="docs",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# AST helpers (kept for future, more precise checks)
# ---------------------------------------------------------------------------
def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - defensive
        return None


__all__ = [
    "ROOT",
    "check_api_route_frontend_client",
    "check_capability_registry",
    "check_documented_endpoints",
    "check_frontend_route_view",
    "check_help_catalog_usage",
    "check_i18n_completeness",
    "check_model_migration",
    "check_orphan_help_ids",
    "check_provider_registry",
    "check_scheduler_job_handlers",
    "run_static_checks",
]
