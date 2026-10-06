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

#: Static checks that compare repository *source* files (frontend TS/Vue, docs).
#: The runtime Docker image ships only the backend, so when the source tree is
#: absent these checks report "недоступно" (info) instead of raising — CI and the
#: dev checkout still run them fully. Paths are resolved at call time (by module
#: attribute name) so the guard sees the current values.
_SOURCE_CHECKS: dict[str, tuple[str, ...]] = {
    "check_api_route_frontend_client": ("FRONTEND",),
    "check_frontend_route_view": ("FRONTEND",),
    "check_help_catalog_usage": ("FRONTEND",),
    "check_orphan_help_ids": ("FRONTEND",),
    "check_hardcoded_ui_strings": ("FRONTEND",),
    "check_documented_endpoints": ("DOCS",),
    "check_frontend_unwired_controls": ("FRONTEND",),
}

#: Capability key -> (service module, class anchor). A capability may only be
#: ``implemented=True`` when its service module really contains the class. This
#: is a *strong* anchor: a stray string/comment named after the capability does
#: not satisfy it (D-099).
CAPABILITY_SERVICE_ANCHORS: dict[str, tuple[str, str]] = {
    "reaction": ("services/reaction_service.py", "class ReactionService"),
    "bot_only_analytics": ("services/analytics_service.py", "class AnalyticsService"),
    "audience_scan": ("services/audience_service.py", "class AudienceService"),
    "direct_invite": ("services/invite_service.py", "class InviteService"),
    "content_publish": ("services/posting_service.py", "class PostingService"),
    "ai_ru": ("services/encoder_service.py", "class EncoderService"),
    "donor_discovery": (
        "services/donor_discovery_service.py",
        "class DonorDiscoveryService",
    ),
}

#: Backup destination kinds -> module that must define a provider. A kind listed
#: in the enum without a matching provider (export-only, no delivery) is drift.
BACKUP_DESTINATION_MODULES: dict[str, str] = {
    "local": "local.py",
    "telegram": "telegram.py",
    "yandex_disk": "yandex.py",
    "google_drive": "gdrive.py",
}

#: Substrings that mark a user-visible Vue text node as a hardcoded *placeholder*
#: string (deliberately narrow, to avoid false positives; D-099). Generic Russian
#: UI text is legitimate in the current SPA and is not flagged.
_RU_UI_MARKERS = (
    "не реализован",
    "появится позже",
    "заглушка",
    "coming soon",
    "todo: ui",
    "ghost",
)

#: Vue template attributes whose literal string values are user-visible and must
#: come from the i18n catalog, not be hardcoded in the component.
_VUE_TEXT_ATTRS = ("placeholder", "label", "title")

#: SettingsService call names: a key read back by ``get_typed``/``get_raw`` is a
#: consumer; a key passed to ``set`` is a writer. Matching on the literal key (not
#: a bare string search) is what makes the write-only check (M) precise.
_SETTINGS_READ_CALLS = ("get_typed", "get_raw")
_SETTINGS_WRITE_CALLS = ("set", "upsert")
_SETTINGS_SERVICE_MARKER = "SettingsService"

#: Settings whose value is overridden by an environment variable are consumed by
#: ``backend/app/core/config.py`` through the env, not by a ``get_typed`` call, so
#: they are not "write-only" even when no module reads them from the DB.
ENV_OVERRIDABLE_PREFIXES = ("OPENHANDS_", "TCMS_")

#: Modules allowed to reference channels without a Channel Registry link:
#: the registry itself and the auditor. Everything else must use a canonical
#: channel identity (D-051/D-055).
_CHANNEL_AWARE_EXEMPT = frozenset(
    {
        "channel_service.py",  # defines the canonical registry
        "consistency.py",  # runtime channel-aware DB check
        "consistency_checks.py",  # this auditor
        "consistency_types.py",
    }
)

#: Canonical channel-identity markers (D-051/D-055). A channel-aware module must
#: use at least one so its channel references resolve to a registry row instead
#: of a private target string.
CANONICAL_CHANNEL_MARKERS = (
    "ChannelRepository",
    "ChannelService",
    "backend.app.db.models.channel",
    "registry_channel_id",
)

_CANONICAL_CHANNEL_PARAMS = frozenset({"channel_id", "registry_channel_id"})

#: ORM columns that are intentionally not referenced by application code (e.g.
#: documented extension points). Listed explicitly so the unused-column check (N)
#: stays honest instead of being silently disabled.
INTENTIONAL_UNUSED_COLUMNS: frozenset[tuple[str, str, str]] = frozenset()

#: Service classes that are intentionally not wired into production call sites
#: (test-support helpers, documented extension points). Listed explicitly so the
#: orphan-service check (O) is honest.
INTENTIONAL_ORPHAN_CLASSES: frozenset[str] = frozenset()

#: Base classes that mark a service class as *not* a callable service (interfaces,
#: value objects, exceptions, enums) and are therefore out of scope for O.
_SERVICE_CLASS_EXCLUDE_BASES = (
    "Protocol",
    "ABC",
    "Exception",
    "Error",
    "BaseModel",
    "Enum",
    "StrEnum",
    "IntEnum",
    "NamedTuple",
    "TypedDict",
)


def run_static_checks() -> list[Finding]:
    """Run every static check and return the raw findings.

    A check that raises must **not** silently disappear: it is reported as an
    ``error`` finding so CI and the Diagnostics panel can distinguish "checked
    and clean" from "could not run". A missing finding is never treated as a
    pass (D-096). A source-comparison check whose inputs are absent (the runtime
    image ships no frontend/docs source) is reported as ``info`` "недоступно",
    because that is an honest "could not check here", not drift.
    """
    findings: list[Finding] = []
    for check in (
        check_api_route_frontend_client,
        check_frontend_route_view,
        check_router_registration,
        check_model_migration,
        check_scheduler_job_handlers,
        check_provider_registry,
        check_backup_destination_registry,
        check_notification_routing,
        check_capability_registry,
        check_capability_implementation,
        check_capability_dependencies,
        check_i18n_completeness,
        check_help_catalog_usage,
        check_hardcoded_ui_strings,
        check_documented_endpoints,
        check_orphan_help_ids,
        check_write_only_settings,
        check_channel_registry_usage,
        check_unused_model_columns,
        check_orphan_service_classes,
        check_frontend_unwired_controls,
    ):
        missing = [
            globals()[name]
            for name in _SOURCE_CHECKS.get(check.__name__, ())
            if not globals()[name].exists()
        ]
        if missing:
            findings.append(
                Finding(
                    id=f"audit.source_unavailable.{check.__name__}",
                    category="integration",
                    severity=SEVERITY_INFO,
                    confidence="high",
                    title="Проверка недоступна без исходников",
                    detail=(
                        f"{check.__name__}: нет каталога {missing[0]} — "
                        "runtime-сборка без исходников frontend/docs."
                    ),
                    why=(
                        "Проверка сравнивает исходные файлы, которых нет в "
                        "runtime-образе; результат здесь неизвестен."
                    ),
                    how_to_fix="Запустите проверку в репозитории (CI) — там исходники есть.",
                    subsystem="audit",
                )
            )
            continue
        try:
            findings.extend(check())
        except Exception as exc:  # a failing check is itself a finding
            findings.append(
                Finding(
                    id=f"audit.check_failed.{check.__name__}",
                    category="integration",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Проверка целостности не выполнилась",
                    detail=f"{check.__name__}: {type(exc).__name__}: {exc}",
                    why=(
                        "Проверка не отработала, поэтому её результат неизвестен — "
                        "это не «всё в порядке»."
                    ),
                    how_to_fix="Исправьте ошибку в самой проверке (см. detail) и повторите.",
                    subsystem="audit",
                )
            )
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
# 3. API router registration (orphan/dead endpoint)
# ---------------------------------------------------------------------------
def check_router_registration() -> list[Finding]:
    """Every ``api/v1`` module that defines a router must be wired into router.py.

    A module with an ``APIRouter`` that is never ``include_router``-ed is a dead
    endpoint tree: its routes exist in source but are unreachable (D-099).
    """
    findings: list[Finding] = []
    api_dir = BACKEND / "api" / "v1"
    router_file = api_dir / "router.py"
    if not router_file.is_file():
        return findings
    router_text = router_file.read_text(encoding="utf-8")
    registered = set(re.findall(r"include_router\(\s*([a-z_]+)\.", router_text))
    for path in sorted(api_dir.glob("*.py")):
        module = path.stem
        if module in {"router", "__init__"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "APIRouter(" not in text:
            continue
        if module not in registered:
            findings.append(
                Finding(
                    id=f"api.router_unregistered.{module}",
                    category="orphan",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Модуль API не подключён к роутеру",
                    detail=f"{module}.py объявляет APIRouter, но не включён в router.py.",
                    why="Маршруты модуля недоступны — мёртвый код.",
                    how_to_fix=f"Добавьте include_router({module}.router) в api/v1/router.py.",
                    subsystem="api",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 4. DB model ↔ migration
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
    """Both a real and a fake implementation must exist for each provider kind.

    Also verifies that every provider module the *factory* imports really exists,
    so a registry mapping that points at a deleted/renamed module is caught
    (otherwise it only fails at runtime).
    """
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
    # Registry mappings must resolve to real modules.
    registry = providers / "registry.py"
    if registry.is_file():
        text = registry.read_text(encoding="utf-8")
        for module in sorted(
            set(re.findall(r"from backend\.app\.providers\.([a-z_]+) import", text))
        ):
            if not (providers / f"{module}.py").is_file():
                findings.append(
                    Finding(
                        id=f"providers.registry_missing.{module}",
                        category="providers",
                        severity=SEVERITY_ERROR,
                        confidence="high",
                        title="Реестр провайдеров ссылается на отсутствующий модуль",
                        detail=f"registry.py импортирует {module}.py, файла нет.",
                        why="Создание провайдера упадёт во время выполнения.",
                        how_to_fix="Добавьте модуль или исправьте импорт в registry.py.",
                        subsystem="providers",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 5b. Backup destination registry
# ---------------------------------------------------------------------------
def check_backup_destination_registry() -> list[Finding]:
    """Every backup destination kind must have a delivery provider module.

    A kind present in the enum but with no provider is export-only drift: the UI
    offers the destination but nothing can deliver to it (D-099).
    """
    findings: list[Finding] = []
    model = BACKEND / "db" / "models" / "backup_destination.py"
    backends = BACKEND / "services" / "backup_backends"
    if not model.is_file() or not backends.is_dir():
        return findings
    text = model.read_text(encoding="utf-8")
    enum_block = re.search(r"class DestinationKind\(.*?\n(.*?)(?=\nclass |\Z)", text, re.DOTALL)
    if not enum_block:
        return findings
    kinds = re.findall(r"^\s+([A-Z_]+)\s*=\s*\"([a-z_]+)\"", enum_block.group(1), re.MULTILINE)
    for _name, value in kinds:
        module = BACKUP_DESTINATION_MODULES.get(value)
        if module is None:
            findings.append(
                Finding(
                    id=f"backup.destination_no_module.{value}",
                    category="integration",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Назначение резервного копирования без провайдера",
                    detail=f"Вид «{value}» не привязан к модулю провайдера.",
                    why="Пользователь выберет назначение, но доставка не сработает.",
                    how_to_fix="Добавьте модуль провайдера и запись в "
                    "BACKUP_DESTINATION_MODULES.",
                    subsystem="backup",
                )
            )
            continue
        if not (backends / module).is_file():
            findings.append(
                Finding(
                    id=f"backup.destination_missing.{value}",
                    category="integration",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Провайдер назначения резервного копирования отсутствует",
                    detail=f"Вид «{value}» требует {module}, файла нет.",
                    why="Экспорт в это назначение упадёт.",
                    how_to_fix="Добавьте модуль провайдера или уберите вид из enum.",
                    subsystem="backup",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 5c. Notification routing
# ---------------------------------------------------------------------------
def check_notification_routing() -> list[Finding]:
    """Every notification category must have a routing target/handler.

    A category that can be raised but has no default routing entry is silently
    dropped — the owner never sees it (D-099).
    """
    findings: list[Finding] = []
    bus = BACKEND / "manager" / "bus.py"
    svc = BACKEND / "services" / "notification_service.py"
    if not bus.is_file() or not svc.is_file():
        return findings
    bus_text = bus.read_text(encoding="utf-8")
    svc_text = svc.read_text(encoding="utf-8")
    # Category string constants: CATEGORY_X = "value" in bus.py.
    categories = set(re.findall(r'CATEGORY_[A-Z_]+\s*=\s*"([a-z_]+)"', bus_text))
    routing_block = re.search(r"DEFAULT_ROUTING[^=]*=\s*\{(.*?)\}", svc_text, re.DOTALL)
    routed = set()
    if routing_block:
        routed = set(re.findall(r'"([a-z_]+)"\s*:', routing_block.group(1)))
    for category in sorted(categories - routed):
        findings.append(
            Finding(
                id=f"notifications.no_routing.{category}",
                category="integration",
                severity=SEVERITY_ERROR,
                confidence="high",
                title="Категория уведомлений без маршрута",
                detail=f"Категория «{category}» не имеет записи в DEFAULT_ROUTING.",
                why="Уведомление такой категории некуда доставить — оно потеряется.",
                how_to_fix="Добавьте маршрут категории в DEFAULT_ROUTING.",
                subsystem="notifications",
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


def check_capability_implementation() -> list[Finding]:
    """A capability must not claim ``implemented`` when the feature is absent.

    The registry can only mark a capability ``implemented`` if there is a real
    implementation behind it. The check requires a *class anchor* in the matching
    service module, not a loose substring somewhere in the tree: a stray comment
    or variable named after the capability must never satisfy it (the exact
    false-positive the meta-audit probes for, D-099).
    """
    findings: list[Finding] = []
    for cap in CAPABILITIES:
        if not cap.implemented:
            continue
        anchor = CAPABILITY_SERVICE_ANCHORS.get(cap.key)
        if anchor is None:
            findings.append(
                Finding(
                    id=f"capabilities.no_anchor.{cap.key}",
                    category="capabilities",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Возможность без проверяемой реализации",
                    detail=f"{cap.key}: не задан якорь реализации (класс сервиса).",
                    why="Нельзя подтвердить реализацию — возможность может оказаться ложной.",
                    how_to_fix="Добавьте якорь в CAPABILITY_SERVICE_ANCHORS или переведите "
                    "capability в implemented=False.",
                    subsystem="capabilities",
                )
            )
            continue
        rel, needle = anchor
        path = BACKEND / rel
        if not path.is_file() or needle not in path.read_text(encoding="utf-8"):
            findings.append(
                Finding(
                    id=f"capabilities.unimplemented.{cap.key}",
                    category="capabilities",
                    severity=SEVERITY_ERROR,
                    confidence="high",
                    title="Возможность помечена как реализованная без реализации",
                    detail=f"{cap.key}: в {rel} не найден «{needle}».",
                    why="Граф возможностей покажет «Доступно» для функции, которой нет.",
                    how_to_fix="Либо реализуйте функцию, либо переведите capability в "
                    "implemented=False.",
                    subsystem="capabilities",
                )
            )
    return findings


def check_capability_dependencies() -> list[Finding]:
    """A capability must not be available when a capability it depends on is not.

    A requirement may be another capability's key. If that dependency is not
    implemented, the dependent capability can never be truly available, so the
    graph must fail rather than silently reporting a working feature (D-099).
    """
    findings: list[Finding] = []
    by_key = {c.key: c for c in CAPABILITIES}
    for cap in CAPABILITIES:
        for req in cap.requires:
            dep = by_key.get(req)
            if dep is not None and not dep.implemented:
                findings.append(
                    Finding(
                        id=f"capabilities.dep_unimplemented.{cap.key}.{req}",
                        category="capabilities",
                        severity=SEVERITY_ERROR,
                        confidence="high",
                        title="Возможность зависит от нереализованной возможности",
                        detail=f"{cap.key} требует {req}, но {req} не реализована.",
                        why="Зависимая возможность не может быть доступна — пользователь "
                        "увидит рабочую функцию, которая на самом деле не работает.",
                        how_to_fix="Реализуйте зависимость или уберите требование.",
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
# 8b. Hardcoded user-facing strings (known limitation)
# ---------------------------------------------------------------------------
def check_hardcoded_ui_strings() -> list[Finding]:
    """Flag user-visible Vue strings that bypass the i18n catalog.

    Known limitation: this is a *narrow* detector. It only catches literal text
    nodes / attributes containing a marker phrase (``_RU_UI_MARKERS``), not every
    hardcoded string. Broad Cyrillic scanning is intentionally avoided because the
    current SPA keeps its Russian UI text in components (D-099). A hit is a
    warning, not an error, and the limitation is recorded in the audit report.
    """
    findings: list[Finding] = []
    if not FRONTEND.is_dir():
        return findings
    for path in sorted(FRONTEND.rglob("*.vue")):
        rel = path.relative_to(FRONTEND)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            lowered = line.lower()
            if not any(marker in lowered for marker in _RU_UI_MARKERS):
                continue
            if any(
                f"{attr}=" in line and "{{" not in line for attr in _VUE_TEXT_ATTRS
            ) or ">" in line:
                findings.append(
                    Finding(
                        id=f"ux.hardcoded_string.{rel}:{lineno}",
                        category="ux",
                        severity=SEVERITY_WARNING,
                        confidence="low",
                        title="Возможная жёстко прописанная строка в интерфейсе",
                        detail=f"{rel}:{lineno}: {line.strip()[:80]}",
                        why="Такая строка не переводится и не проходит через каталог i18n.",
                        how_to_fix="Перенесите текст в каталог i18n (или подтвердите как "
                        "намеренный).",
                        subsystem="frontend",
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
# 10. Write-only setting (M) — a setting that is stored but never consumed
# ---------------------------------------------------------------------------
def _is_settings_receiver(node: ast.AST, aliases: set[str]) -> bool:
    """True when an attribute call receiver is a SettingsService-like object.

    Matches ``SettingsService(...)``, ``self.settings``/``self.repo`` and local
    names bound to ``SettingsService`` (collected per module), so a genuine
    write/read is recognised regardless of the local variable name.
    """
    text = ast.unparse(node)
    if _SETTINGS_SERVICE_MARKER in text:
        return True
    if text in {"self.settings", "self.repo", "self.settings.repo"}:
        return True
    return isinstance(node, ast.Name) and node.id in aliases


def _settings_aliases(tree: ast.Module) -> set[str]:
    """Local names bound to a ``SettingsService(...)`` call in one module."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != _SETTINGS_SERVICE_MARKER:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                aliases.add(target.id)
    return aliases


def _settings_usage() -> tuple[set[str], set[str]]:
    """Return ``(written, read)`` setting keys from the backend source.

    A key is *written* when it is the literal first argument of ``.set(...)`` on a
    SettingsService-like receiver, and *read* when it is the literal first
    argument of ``.get_typed(...)``/``.get_raw(...)``. Keys declared in a
    ``*_SETTING_SPECS`` mapping are also treated as read, because those modules
    read every spec key back through ``effective()``.
    """
    written: set[str] = set()
    read: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        aliases = _settings_aliases(tree)
        for node in ast.walk(tree):
            # Declared specs: keys a module iterates over to read their values.
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id.endswith("_SETTING_SPECS")
                    ):
                        for key in node.value.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                read.add(key.value)
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not _is_settings_receiver(node.func.value, aliases):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            if node.func.attr in _SETTINGS_READ_CALLS:
                read.add(first.value)
            elif node.func.attr in _SETTINGS_WRITE_CALLS:
                written.add(first.value)
    return written, read


def _is_env_backed(key: str) -> bool:
    """True when a setting's value can come from an environment variable."""
    return key.upper().startswith(ENV_OVERRIDABLE_PREFIXES)


def check_write_only_settings() -> list[Finding]:
    """Flag settings the code *writes* but never *reads* (D-100 gap M).

    A write-only setting is saved (e.g. via the generic ``PATCH /settings`` or a
    service) yet no module reads it back, so changing it has no effect on the
    application — a silent trap for the owner. The check is conservative:

    * it matches the literal key on a SettingsService-like receiver, never a bare
      string occurrence;
    * it ignores keys that are read through a declared ``*_SETTING_SPECS`` map or
      that are environment-backed (``OPENHANDS_*``/``TCMS_*``).

    Confidence is ``high`` because a literal writer with no reader is a real gap;
    the severity is a ``warning`` because a dynamic (computed) reader is possible.
    """
    written, read = _settings_usage()
    findings: list[Finding] = []
    for key in sorted(written - read):
        if _is_env_backed(key):
            continue
        findings.append(
            Finding(
                id=f"settings.write_only.{key}",
                category="settings",
                severity=SEVERITY_WARNING,
                confidence="high",
                title="Настройка сохраняется, но нигде не используется",
                detail=(
                    f"Ключ «{key}» записывается через SettingsService, но ни один "
                    "модуль не читает его обратно."
                ),
                why="Значение сохраняется, но не влияет на поведение приложения — "
                "пользователь меняет настройку и не видит результата.",
                how_to_fix="Добавьте чтение настройки в модуле, который должен её "
                "использовать, или удалите сохранение.",
                subsystem="settings",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 11. Channel-aware module without canonical registry link (Q)
# ---------------------------------------------------------------------------
def _is_channel_aware(tree: ast.Module) -> bool:
    """True when a module exposes channel-aware behaviour.

    A module is channel-aware if it defines a class/function whose name mentions
    "channel", or a function that takes a channel identity parameter
    (``channel_id`` / ``registry_channel_id``). This is a structural signal, not a
    word search, so unrelated mentions do not trigger it.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and "channel" in node.name.lower():
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "channel" in node.name.lower():
                return True
            params = {a.arg for a in (*node.args.args, *node.args.kwonlyargs)}
            if params & _CANONICAL_CHANNEL_PARAMS:
                return True
    return False


def _uses_canonical_channel(tree: ast.Module) -> bool:
    """True when a module references a canonical channel identity.

    Canonical use means importing the Channel Registry (repository, service or
    model), referring to ``registry_channel_id``, or taking a canonical
    ``channel_id`` parameter. A module that touches channels without any of these
    keeps a private target string and drifts from the registry (D-051/D-055).
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if "channel" in alias.name.lower():
                    return True
            module = getattr(node, "module", None)
            if module and "channel" in module.lower():
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = {a.arg for a in (*node.args.args, *node.args.kwonlyargs)}
            if params & _CANONICAL_CHANNEL_PARAMS:
                return True
    return False


def check_channel_registry_usage() -> list[Finding]:
    """Flag channel-aware service modules that bypass the Channel Registry (gap Q).

    The runtime check (:meth:`ConsistencyAuditor._check_channel_aware`) catches
    *rows* whose ``channel_id`` is empty; this static check catches *module code*
    that is channel-aware but never uses a canonical channel identity. Together
    they cover both the data and the code side of D-051/D-055 drift.
    """
    findings: list[Finding] = []
    services = BACKEND / "services"
    if not services.is_dir():
        return findings
    for path in sorted(services.glob("*.py")):
        if path.name in _CHANNEL_AWARE_EXEMPT:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        if not _is_channel_aware(tree) or _uses_canonical_channel(tree):
            continue
        module = path.stem
        findings.append(
            Finding(
                id=f"channel-aware.module.{module}",
                category="channels",
                severity=SEVERITY_WARNING,
                confidence="medium",
                title="Модуль работает с каналами в обход реестра",
                detail=(
                    f"{path.name} учитывает каналы, но не использует каноническую "
                    "связь (ChannelRepository/ChannelService/registry_channel_id)."
                ),
                why="Приватная строка канала расходится с общим реестром: настройки "
                "канала и его проверка прав не применяются к этому модулю.",
                how_to_fix="Используйте ChannelRepository/ChannelService и канонический "
                "channel_id вместо собственной строки-цели.",
                subsystem="channels",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 12. Unused ORM column (N) — a DB field no application code reads or writes
# ---------------------------------------------------------------------------
def _model_columns() -> dict[str, dict[str, list[str]]]:
    """Return ``module -> {class name: [column names]}`` for ORM ``mapped_column``.

    A column is an ``AnnAssign`` whose value is a ``mapped_column(...)`` call.
    ``__tablename__`` / enum members are not columns and are ignored.
    """
    columns: dict[str, dict[str, list[str]]] = {}
    models = BACKEND / "db" / "models"
    if not models.is_dir():
        return columns
    for path in sorted(models.glob("*.py")):
        tree = _parse(path)
        if tree is None:
            continue
        found: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            names: list[str] = []
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(
                    stmt.value, ast.Call
                ):
                    continue
                func = stmt.value.func
                call = func.attr if isinstance(func, ast.Attribute) else getattr(
                    func, "id", ""
                )
                if call == "mapped_column" and isinstance(stmt.target, ast.Name):
                    names.append(stmt.target.id)
            if names:
                found[node.name] = names
        if found:
            columns[path.name] = found
    return columns


def _application_references() -> tuple[set[str], set[str], set[str]]:
    """Collect ``(attributes, keywords, string literals)`` used outside models.

    The model definition files themselves are skipped so a column's own
    declaration is not mistaken for a use. Attribute access (``row.meta``),
    keyword arguments (``meta=``) and string literals (a JSON key ``"meta"`` or a
    dynamic ``getattr``) all count as a reference — anything narrower would
    produce false positives.
    """
    attrs: set[str] = set()
    keywords: set[str] = set()
    strings: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.parent.name == "models":
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attrs.add(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                keywords.add(node.arg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.add(node.value)
    return attrs, keywords, strings


def check_unused_model_columns() -> list[Finding]:
    """Flag ORM columns no application code ever references (D-100 gap N).

    A column that exists in the model and the migration but is never read or
    written is dead schema: the UI cannot show it and behaviour never changes
    because of it. The check is conservative and structural:

    * it derives columns from the ORM (``mapped_column``), not from a name search;
    * a column is "used" when its name appears as an attribute, a keyword argument
      or a string literal anywhere outside the model files (covering serialisers,
      ``getattr``/``setattr`` and JSON keys);
    * intentionally-kept extension points are listed in
      :data:`INTENTIONAL_UNUSED_COLUMNS` (currently empty).

    Severity is ``info`` because a column may be a documented future extension
    point; confidence is ``medium`` because dynamic access via a computed name
    cannot be seen statically.
    """
    findings: list[Finding] = []
    columns = _model_columns()
    if not columns:
        return findings
    attrs, keywords, strings = _application_references()
    for module, classes in sorted(columns.items()):
        stem = module[:-3]
        for cls, names in sorted(classes.items()):
            for name in names:
                if name in attrs or name in keywords or name in strings:
                    continue
                if (stem, cls, name) in INTENTIONAL_UNUSED_COLUMNS:
                    continue
                findings.append(
                    Finding(
                        id=f"db.unused_column.{stem}.{cls}.{name}",
                        category="orphan",
                        severity=SEVERITY_INFO,
                        confidence="medium",
                        title="Поле модели не используется приложением",
                        detail=(
                            f"{module}: поле «{name}» класса {cls} объявлено в модели, "
                            "но ни один модуль не читает и не пишет его."
                        ),
                        why="Мёртвое поле схемы: миграция и БД его хранят, но поведение "
                        "приложения от него не зависит.",
                        how_to_fix="Используйте поле или удалите его аддитивной миграцией.",
                        subsystem="database",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 13. Backend service without caller (O) — dead functionality
# ---------------------------------------------------------------------------
def _service_classes() -> dict[str, dict[str, list[str]]]:
    """Return ``module -> {class name: method names}`` for public service classes."""
    classes: dict[str, dict[str, list[str]]] = {}
    services = BACKEND / "services"
    if not services.is_dir():
        return classes
    for path in sorted(services.glob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("_"):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        found: dict[str, list[str]] = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            bases = [ast.unparse(b) for b in node.bases]
            if any(
                any(excluded in base for excluded in _SERVICE_CLASS_EXCLUDE_BASES)
                for base in bases
            ):
                continue
            if any("dataclass" in ast.unparse(d) for d in node.decorator_list):
                continue
            found[node.name] = [
                s.name
                for s in node.body
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not s.name.startswith("__")
            ]
        if found:
            classes[path.name] = found
    return classes


def _class_references() -> tuple[set[str], set[str]]:
    """Names/attributes referenced in the backend, outside import statements.

    A bare ``import`` of a class is deliberately **not** a use: importing a name
    does not call it. Only an actual reference (instantiation, attribute, a
    passed name) counts. References *within the defining module* count too, so a
    class wired by its own factory is not mistaken for dead code.
    """
    names: set[str] = set()
    attrs: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                attrs.add(node.attr)
    return names, attrs


def check_orphan_service_classes() -> list[Finding]:
    """Flag public service classes nothing references (D-100 gap O).

    A service class that is never referenced anywhere in the backend is dead
    functionality: it exists, it may even be tested, but no production path can
    reach it. A plain ``import`` does not count — the class must be actually
    referenced (instantiated, passed, or its methods called). Classes that are
    documented extension points are listed in :data:`INTENTIONAL_ORPHAN_CLASSES`.

    Severity is ``info``: dead code does not break behaviour, it is an orphan
    signal for the owner. (A user-visible dead control is a ``warning``, see P.)
    """
    findings: list[Finding] = []
    classes = _service_classes()
    names, attrs = _class_references()
    for module, defined in sorted(classes.items()):
        stem = module[:-3]
        for cls, methods in sorted(defined.items()):
            if cls in names or cls in attrs:
                continue
            if cls in INTENTIONAL_ORPHAN_CLASSES:
                continue
            findings.append(
                Finding(
                    id=f"dead.service.{stem}.{cls}",
                    category="orphan",
                    severity=SEVERITY_INFO,
                    confidence="medium",
                    title="Сервис без вызывающего кода",
                    detail=(
                        f"{module}: класс «{cls}» не используется ни одним модулем "
                        f"(методы: {', '.join(methods) or '—'})."
                    ),
                    why="Мёртвая функциональность: код есть, но ни один сценарий его "
                    "не вызывает.",
                    how_to_fix="Подключите сервис к реальному сценарию или удалите его.",
                    subsystem="services",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 14. Frontend control without behaviour (P) — a control that does nothing
# ---------------------------------------------------------------------------
def _frontend_script(text: str) -> str:
    return "\n".join(
        match.group(1)
        for match in re.finditer(r"<script[^>]*>(.*?)</script>", text, re.DOTALL)
    )


def _vue_defined_names(script: str) -> set[str]:
    """Names a component's ``<script>`` defines or imports (template references)."""
    names: set[str] = set()
    names.update(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", script))
    names.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", script))
    for group in re.findall(r"\b(?:const|let|var)\s*\{\s*([^}]+?)\s*\}\s*=", script):
        for part in group.split(","):
            part = part.strip().split(":")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                names.add(part)
    for group in re.findall(r"import\s*\{([^}]+)\}", script):
        for part in group.split(","):
            part = part.strip().split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                names.add(part)
    return names


def _vue_function_bodies(script: str) -> dict[str, str]:
    """Body text of each function / arrow function defined in the script."""
    bodies: dict[str, str] = {}
    patterns = (
        r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?"
        r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, script):
            name = match.group(1)
            start = script.find("{", match.end() - 1)
            depth = 0
            for i in range(start, len(script)):
                if script[i] == "{":
                    depth += 1
                elif script[i] == "}":
                    depth -= 1
                    if depth == 0:
                        bodies[name] = script[start + 1 : i]
                        break
    return bodies


def check_frontend_unwired_controls() -> list[Finding]:
    """Flag ``@click``/``@change``/``@submit`` handlers that do nothing (gap P).

    A template event handler that names a function the component never defines
    (a typo) or a function with an empty body is a control with no behaviour:
    the user clicks and nothing happens. Handlers written as an inline assignment
    (``@click="x = !x"``) or an expression are out of scope, and a handler whose
    body is non-empty is trusted even if it only mutates a reactive ref.
    """
    findings: list[Finding] = []
    if not FRONTEND.is_dir():
        return findings
    for path in sorted(FRONTEND.rglob("*.vue")):
        text = path.read_text(encoding="utf-8")
        script = _frontend_script(text)
        if not script.strip():
            continue
        rel = path.relative_to(FRONTEND)
        defined = _vue_defined_names(script)
        bodies = _vue_function_bodies(script)
        for match in re.finditer(
            r'@(?:click|change|submit|input)(?:\.[a-z]+)?\s*=\s*"([^"]+)"', text
        ):
            expr = match.group(1).strip()
            simple = re.fullmatch(r"([A-Za-z_$][\w$]*)\s*(\(.*\))?", expr)
            if simple is None:
                continue  # assignment/compound expression, not a handler reference
            name = simple.group(1)
            if name in defined:
                if name in bodies and bodies[name].strip() == "":
                    findings.append(
                        _unwired_finding(rel, name, "пустое тело обработчика")
                    )
                continue
            findings.append(_unwired_finding(rel, name, "обработчик не определён"))
    return findings


def _unwired_finding(rel: Path, name: str, reason: str) -> Finding:
    return Finding(
        id=f"frontend.control_unwired.{name}",
        category="frontend",
        severity=SEVERITY_WARNING,
        confidence="medium",
        title="Элемент управления без обработчика",
        detail=f"{rel}: обработчик «{name}» — {reason}.",
        why="Пользователь нажимает кнопку/переключатель, но действие не выполняется.",
        how_to_fix="Определите обработчик или подключите его к реальному действию.",
        subsystem="frontend",
    )


# ---------------------------------------------------------------------------
# AST helpers (kept for future, more precise checks)
# ---------------------------------------------------------------------------
def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - defensive
        return None


__all__ = [
    "CAPABILITY_SERVICE_ANCHORS",
    "ROOT",
    "check_api_route_frontend_client",
    "check_backup_destination_registry",
    "check_capability_dependencies",
    "check_capability_implementation",
    "check_capability_registry",
    "check_channel_registry_usage",
    "check_documented_endpoints",
    "check_frontend_route_view",
    "check_frontend_unwired_controls",
    "check_hardcoded_ui_strings",
    "check_help_catalog_usage",
    "check_i18n_completeness",
    "check_model_migration",
    "check_notification_routing",
    "check_orphan_help_ids",
    "check_orphan_service_classes",
    "check_provider_registry",
    "check_router_registration",
    "check_scheduler_job_handlers",
    "check_unused_model_columns",
    "check_write_only_settings",
    "run_static_checks",
]
