"""AI service: model lifecycle, routing, metrics and safe diagnostics (PHASE 7).

The service is the business-logic entry point for the Tiny AI. It owns:

* reading effective AI configuration (DB settings override env defaults);
* building the optional :class:`LlmClassifier` (lazy, model-agnostic);
* per-request routing via :class:`RoutingClassifier` (rules-first, D-032);
* model management (check / load / unload, listing ``.gguf`` assets);
* aggregate performance metrics.

It never imports Telegram or FastAPI, and it must never raise for an ordinary AI
problem — those become recorded events plus a fallback classification.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.backends import BACKEND_FAKE, BACKEND_LLAMA_CPP, build_backend
from backend.app.ai.classifiers import LlmClassifier, RulesClassifier
from backend.app.ai.errors import AiError
from backend.app.ai.router import RoutingClassifier, RoutingOutcome
from backend.app.ai.types import (
    MODE_AI,
    MODE_AUTO,
    MODE_ENCODER,
    SOURCE_AI,
    ClassificationContext,
    Classifier,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.db.repositories.ai import AiRepository
from backend.app.rules.engine import Category
from backend.app.services.events_service import EventsService
from backend.app.services.reaction_service import ReactionService

logger = get_logger(__name__)

AI_MODULE = "ai.classifier"

#: UI-editable AI settings: key → (title, type, default-from-Settings attr).
#: Titles are plain-language; complex fields carry help text in the schema layer.
AI_SETTING_SPECS: dict[str, tuple[str, str, str]] = {
    "ai_enabled": ("Включить мини-ИИ", "bool", "ai_enabled"),
    "ai_backend": ("Движок ИИ", "string", "ai_backend"),
    "ai_model_path": ("Путь к модели (.gguf)", "string", "ai_model_path"),
    "ai_model_threads": ("Потоки процессора", "int", "ai_model_threads"),
    "ai_context_size": ("Размер контекста", "int", "ai_context_size"),
    "ai_temperature": ("Температура", "float", "ai_temperature"),
    "ai_max_tokens": ("Максимум токенов ответа", "int", "ai_max_tokens"),
    "ai_timeout_seconds": ("Максимальное время анализа", "float", "ai_timeout_seconds"),
    "ai_keep_loaded": ("Держать модель в памяти", "bool", "ai_keep_loaded"),
    "ai_rules_threshold": ("Порог уверенности правил", "float", "ai_rules_threshold"),
    "ai_confidence_threshold": ("Порог уверенности ИИ", "float", "ai_confidence_threshold"),
    "ai_history_limit": ("Сколько последних записей хранить", "int", "ai_history_limit"),
    # v1.1: lightweight encoder level (no model download, weak-PC friendly).
    "ai_encoder_enabled": ("Лёгкий распознаватель (без модели)", "bool", "ai_encoder_enabled"),
    "ai_encoder_model_enabled": (
        "Использовать модель ruBERT-tiny2",
        "bool",
        "ai_encoder_model_enabled",
    ),
    "ai_encoder_keep_loaded": ("Держать лёгкую модель в памяти", "bool", "ai_encoder_keep_loaded"),
}


@dataclass(slots=True)
class AiStatus:
    enabled: bool
    backend: str
    runtime_available: bool
    model_path: str
    model_exists: bool
    model_size_bytes: int
    model_loaded: bool
    effective: bool  # True when AI can actually be used right now
    reason: str
    how_to_fix: str


@dataclass(slots=True)
class ModelCheck:
    ok: bool
    runtime_available: bool
    model_exists: bool
    message: str
    how_to_fix: str
    size_bytes: int = 0
    load_ms: int = 0


class AiService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = AiRepository(session)
        self.events = EventsService(session)
        self._backend_cache: dict[str, object] = {}

    # ======================================================================
    # Effective configuration
    # ======================================================================
    async def _setting(self, key: str) -> object:
        """Return the effective value for an AI setting (DB override > env)."""
        from backend.app.services.settings_service import SettingsService

        spec = AI_SETTING_SPECS[key]
        default = getattr(self.settings, spec[2])
        value = await SettingsService(self.session).get_typed(key, default)
        return value

    async def effective(self) -> dict[str, object]:
        out: dict[str, object] = {}
        for key in AI_SETTING_SPECS:
            out[key] = await self._setting(key)
        return out

    async def set_setting(self, key: str, value: object) -> None:
        if key not in AI_SETTING_SPECS:
            raise AiError("Неизвестная настройка ИИ.", how_to_fix="Выберите параметр из списка.")
        self._validate_setting(key, value)
        from backend.app.services.settings_service import SettingsService

        await SettingsService(self.session).set(key, value)

    @staticmethod
    def _validate_setting(key: str, value: object) -> None:
        def _num() -> float:
            try:
                return float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                raise AiError("Значение должно быть числом.") from None

        if key in ("ai_model_threads", "ai_context_size", "ai_max_tokens", "ai_history_limit"):
            n = _num()
            if n < 0 or n > 100000:
                raise AiError("Недопустимое значение.", how_to_fix="Укажите положительное число.")
        if key == "ai_temperature" and not 0.0 <= _num() <= 2.0:
            raise AiError("Температура должна быть от 0 до 2.")
        if key == "ai_timeout_seconds" and not 1.0 <= _num() <= 600.0:
            raise AiError(
                "Время анализа должно быть от 1 до 600 секунд.",
                how_to_fix="Для слабого компьютера достаточно 30 секунд.",
            )
        if key in ("ai_rules_threshold", "ai_confidence_threshold") and not 0.0 <= _num() <= 1.0:
            raise AiError("Порог должен быть от 0 до 1.")
        if key == "ai_model_path":
            raw = str(value or "").strip()
            if raw and not raw.lower().endswith(".gguf"):
                raise AiError(
                    "Поддерживаются только файлы модели .gguf.",
                    how_to_fix="Выберите файл модели с расширением .gguf.",
                )

    # ======================================================================
    # Backend / classifier construction
    # ======================================================================
    def backend(self):
        """Return a (cached) backend instance for the configured backend name."""
        name = self._sync_backend_name()
        if name not in self._backend_cache:
            self._backend_cache[name] = build_backend(self.settings, name=name)
        return self._backend_cache[name]

    async def _backend(self):
        """Return the backend for the *effective* backend name (DB override aware)."""
        name = str(await self._setting("ai_backend") or "").strip()
        if name not in self._backend_cache:
            self._backend_cache[name] = build_backend(self.settings, name=name)
        return self._backend_cache[name]

    def _sync_backend_name(self) -> str:
        # Backend name rarely changes; env/default value is authoritative here.
        return (self.settings.ai_backend or "").strip() or (
            BACKEND_FAKE if self.settings.offline_mode else BACKEND_LLAMA_CPP
        )

    async def classifier(self, *, force: bool = False) -> Classifier | None:
        """Return the optional AI classifier, or ``None`` when it must not run.

        ``force=True`` builds the classifier whenever a runtime + model are usable,
        regardless of the global toggle (manual request path).
        """
        effective = await self.effective()
        enabled = bool(effective["ai_enabled"])
        model_path = str(effective["ai_model_path"] or "").strip()
        if not force and not enabled:
            return None
        if not model_path:
            return None
        backend = await self._backend()
        if not getattr(backend, "available", False):
            return None
        model_label = Path(model_path).name
        return LlmClassifier(
            backend,
            model_label=model_label,
            timeout=float(effective["ai_timeout_seconds"]),
            max_tokens=int(effective["ai_max_tokens"]),
        )

    async def router(self, mode: str = MODE_AUTO) -> RoutingClassifier:
        """Build a rules-first router for the requested mode."""
        from backend.app.ai.encoder import EncoderClassifier

        specs = await ReactionService(self.session, settings=self.settings)._rule_specs()
        rules = RulesClassifier(specs)
        ai = await self.classifier(force=(mode == MODE_AI))
        effective = await self.effective()
        encoder: Classifier | None = None
        if mode in (MODE_AUTO, MODE_ENCODER) and bool(effective["ai_encoder_enabled"]):
            encoder = EncoderClassifier(backend=self._encoder_backend(effective))
        return RoutingClassifier(
            rules=rules,
            ai=ai,
            encoder=encoder,
            rules_threshold=float(effective["ai_rules_threshold"]),
            ai_threshold=float(effective["ai_confidence_threshold"]),
            mode=mode,
        )

    def _encoder_backend(self, effective: dict[str, object]) -> object | None:
        """Return the optional ruBERT backend when installed and enabled.

        The heavy runtime is only reached when the owner explicitly enabled the
        model; otherwise the dependency-free hashing encoder is used. A missing
        model simply means ``None`` (the encoder falls back to hashing).
        """
        if not bool(effective.get("ai_encoder_model_enabled")):
            return None
        from backend.app.ai.backends.rubert import RuBertEncoderBackend
        from backend.app.services.encoder_service import EncoderService

        service = EncoderService(self.session, settings=self.settings)
        if not (service.model_dir / "config.json").is_file():
            return None
        backend = RuBertEncoderBackend(str(service.model_dir))
        return backend if backend.available else None

    async def encoder_available(self) -> bool:
        """True when the lightweight encoder level is enabled."""
        try:
            return bool((await self.effective())["ai_encoder_enabled"])
        except Exception:  # pragma: no cover - settings always readable here
            return bool(self.settings.ai_encoder_enabled)

    # ======================================================================
    # Classification
    # ======================================================================
    async def classify(self, text: str, *, mode: str = MODE_AUTO) -> RoutingOutcome:
        """Classify ``text`` with metrics recording; never raises for AI errors."""
        router = await self.router(mode)
        context = ClassificationContext(known_categories=tuple(c.value for c in Category))
        outcome = router.route(text, context)
        await self._record(outcome)
        return outcome

    async def _record(self, outcome: RoutingOutcome) -> None:
        from backend.app.db.models.ai import AiRecord

        result = outcome.result
        is_ai = result.source == SOURCE_AI
        try:
            await self.repo.bump(
                rules=1,
                ai=1 if is_ai else 0,
                fallback=1 if outcome.fallback_used and not is_ai else 0,
                ai_error=1 if outcome.ai_error and not is_ai else 0,
                latency_ms=result.processing_time_ms,
            )
            limit = int(await self._setting("ai_history_limit"))
            if limit > 0:
                await self.repo.add_record(
                    AiRecord(
                        source=result.source,
                        category=str(result.category),
                        tone=str(result.tone),
                        confidence=result.confidence,
                        model=result.model,
                        latency_ms=result.processing_time_ms,
                        mode=outcome.mode,
                        ok=not outcome.ai_error,
                        detail=outcome.ai_error[:200],
                    )
                )
                await self.repo.trim_records(limit)
        except Exception:  # pragma: no cover - metrics must never break flow
            pass
        if outcome.ai_error:
            await self.events.warning(
                AI_MODULE,
                "ИИ не смог классифицировать пост — использованы обычные правила.",
                explanation=outcome.ai_error,
                how_to_fix="Проверьте модель в разделе «AI» или выключите ИИ.",
                operation="classify",
                status="fallback",
            )

    # ======================================================================
    # Status / model management
    # ======================================================================
    async def status(self) -> AiStatus:
        effective = await self.effective()
        enabled = bool(effective["ai_enabled"])
        backend_name = str(effective["ai_backend"] or "").strip() or self._sync_backend_name()
        backend = await self._backend()
        runtime_available = bool(getattr(backend, "available", False))
        model_path = str(effective["ai_model_path"] or "").strip()
        size = 0
        model_exists = False
        if model_path:
            path = Path(model_path)
            try:
                if path.is_file():
                    model_exists = True
                    size = path.stat().st_size
            except OSError:
                model_exists = False
        loaded = bool(getattr(backend, "loaded", False))
        effective_ok = enabled and runtime_available and model_exists
        reason, fix = self._status_reason(enabled, runtime_available, model_exists, model_path)
        return AiStatus(
            enabled=enabled,
            backend=backend_name,
            runtime_available=runtime_available,
            model_path=model_path,
            model_exists=model_exists,
            model_size_bytes=size,
            model_loaded=loaded,
            effective=effective_ok,
            reason=reason,
            how_to_fix=fix,
        )

    @staticmethod
    def _status_reason(
        enabled: bool, runtime: bool, model: bool, model_path: str
    ) -> tuple[str, str]:
        if not enabled:
            return (
                "AI выключен — это нормально. Система работает на обычных правилах.",
                "Включите ИИ, если хотите использовать локальную модель.",
            )
        if not runtime:
            return (
                "Локальный движок ИИ (llama.cpp) недоступен.",
                "Установите llama-cpp-python или выключите ИИ.",
            )
        if not model_path:
            return (
                "AI включён, но модель не выбрана.",
                "Укажите путь к файлу модели .gguf в разделе «AI».",
            )
        if not model:
            return (
                "AI включён, но модель не найдена.",
                f"Проверьте путь к модели: {model_path}",
            )
        return ("Модель найдена, но ещё не проверена.", "Нажмите «Проверить модель».")

    async def list_models(self) -> list[dict[str, object]]:
        """List ``.gguf`` files available in the models directory."""
        directory = self.settings.resolve_models_dir()
        found: list[dict[str, object]] = []
        try:
            for path in sorted(directory.glob("*.gguf")):
                try:
                    found.append(
                        {"name": path.name, "path": str(path), "size_bytes": path.stat().st_size}
                    )
                except OSError:
                    continue
        except OSError:  # pragma: no cover - directory should exist
            return []
        return found

    async def check_model(self) -> ModelCheck:
        """Validate runtime + model readability and try a real load."""
        status = await self.status()
        if not status.runtime_available:
            await self._event_warning("Движок ИИ недоступен.", "Установите llama-cpp-python.")
            return ModelCheck(
                ok=False,
                runtime_available=False,
                model_exists=status.model_exists,
                message="Движок ИИ не установлен.",
                how_to_fix="Установите llama-cpp-python или выключите ИИ.",
            )
        if not status.model_exists:
            await self._event_warning("Модель ИИ не найдена.", "Проверьте путь к модели.")
            return ModelCheck(
                ok=False,
                runtime_available=True,
                model_exists=False,
                message="Файл модели не найден.",
                how_to_fix=f"Проверьте путь к модели: {status.model_path or '(не задан)'}",
            )
        backend = await self._backend()
        started = time.monotonic()
        try:
            backend.load()
        except AiError as exc:
            await self._event_warning("Не удалось загрузить модель ИИ.", exc.how_to_fix)
            return ModelCheck(
                ok=False,
                runtime_available=True,
                model_exists=True,
                message=exc.message,
                how_to_fix=exc.how_to_fix,
                size_bytes=status.model_size_bytes,
            )
        load_ms = int((time.monotonic() - started) * 1000)
        await self.repo.bump(model_load_ms=load_ms)
        return ModelCheck(
            ok=True,
            runtime_available=True,
            model_exists=True,
            message="Модель успешно загружена и готова к работе.",
            how_to_fix="",
            size_bytes=status.model_size_bytes,
            load_ms=load_ms,
        )

    async def load_model(self) -> ModelCheck:
        return await self.check_model()

    async def unload_model(self) -> AiStatus:
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            (await self._backend()).unload()
        return await self.status()

    async def _event_warning(self, message: str, fix: str) -> None:
        await self.events.warning(
            AI_MODULE,
            message,
            explanation="Система продолжит работу на обычных правилах.",
            how_to_fix=fix,
            operation="model_check",
            status="warning",
            notify=True,
        )

    # ======================================================================
    # Metrics
    # ======================================================================
    async def metrics(self) -> dict[str, object]:
        metric = await self.repo.get_metric()
        total = metric.rules_count or 0
        avg = int(metric.total_latency_ms / metric.ai_count) if metric.ai_count else 0
        return {
            "rules_count": metric.rules_count,
            "ai_count": metric.ai_count,
            "fallback_count": metric.fallback_count,
            "manual_count": metric.manual_count,
            "ai_error_count": metric.ai_error_count,
            "average_latency_ms": avg,
            "last_latency_ms": metric.last_latency_ms,
            "model_load_ms": metric.model_load_ms,
            "total_classifications": total,
        }

    async def metrics_since(self, since) -> dict[str, object]:
        """Counters derived from recent records at/after ``since`` (today's view)."""
        records, _ = await self.repo.list_records(limit=100000, offset=0)
        rules = ai = fallback = errors = 0
        for rec in records:
            if rec.created_at < since:
                continue
            if rec.source == SOURCE_AI:
                ai += 1
            elif rec.source == "fallback":
                fallback += 1
            else:
                rules += 1
            if not rec.ok:
                errors += 1
        return {
            "rules_count": rules,
            "ai_count": ai,
            "fallback_count": fallback,
            "ai_error_count": errors,
        }

    async def history(self, *, limit: int = 20, offset: int = 0) -> tuple[list[object], int]:
        records, total = await self.repo.list_records(limit=limit, offset=offset)
        return records, total


__all__ = ["AI_MODULE", "AI_SETTING_SPECS", "AiService", "AiStatus", "ModelCheck"]
