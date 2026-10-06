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
    "check_documented_endpoints",
    "check_frontend_route_view",
    "check_hardcoded_ui_strings",
    "check_help_catalog_usage",
    "check_i18n_completeness",
    "check_model_migration",
    "check_notification_routing",
    "check_orphan_help_ids",
    "check_provider_registry",
    "check_router_registration",
    "check_scheduler_job_handlers",
    "run_static_checks",
]
