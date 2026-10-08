"""Content Operations 2.0 processing pipeline (v1.9).

Extends the existing Content Studio with an AI processing stage and explicit
human moderation, without a second studio. One item flows:

```
text → classify (encoder, local, always available)
     → transform (existing AI Gateway; rewrite/summarize/translate/...)
     → moderation state (AI_PROCESSED / NEEDS_REVIEW / APPROVED / REJECTED)
```

The generative step uses the **existing** AI Gateway, so provider selection,
bounded retries and automatic failover are exactly the v1.8 behaviour. When every
provider is unavailable the item is **never lost**: it moves to ``NEEDS_REVIEW``
with ``ai_status = ai_unavailable`` and a plain-language note. The AI only narrows
(intent/category); it never picks an emoji directly (D-033/D-076).
"""

from __future__ import annotations

import contextlib
import time

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.content import (
    ContentItem,
    ContentItemStatus,
)
from backend.app.db.models.content_ops import (
    AI_STATUS_NONE,
    AI_STATUS_OK,
    AI_STATUS_UNAVAILABLE,
)
from backend.app.db.repositories.content import ContentItemRepository
from backend.app.db.repositories.content_ops import (
    AiProfileRepository,
    ContentOperationRepository,
)
from backend.app.services.ai_gateway_service import AiGatewayService
from backend.app.services.ai_profiles import AiProfileService, ProfileError
from backend.app.services.content_service import ContentError, content_hash
from backend.app.services.events_service import EventsService

MODULE = "content"

#: Fallback instruction per action, used when a profile gives no instructions.
ACTION_INSTRUCTIONS = {
    "rewrite": "Перепиши текст канала своими словами, сохранив смысл.",
    "summarize": "Сделай краткое резюме в 2–3 предложениях.",
    "translate": "Переведи текст на русский язык, сохранив смысл.",
    "title": "Придумай короткий цепкий заголовок (одну строку).",
    "description": "Напиши короткое описание материала.",
    "first_comment": "Напиши первый комментарий к посту от лица канала.",
}


class PipelineError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


class ContentPipelineService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        gateway: AiGatewayService | None = None,
        profiles: AiProfileService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.items = ContentItemRepository(session)
        self.profiles = profiles or AiProfileService(session)
        self.profile_repo = AiProfileRepository(session)
        self.operations = ContentOperationRepository(session)
        self.events = EventsService(session)
        self._gateway = gateway

    def _gateway_service(self) -> AiGatewayService:
        if self._gateway is None:
            self._gateway = AiGatewayService(self.session, settings=self.settings)
        return self._gateway

    # --- audit helpers -------------------------------------------------------
    async def record(
        self,
        *,
        stage: str,
        status: str,
        item_id: str = "",
        publication_id: str = "",
        source_kind: str = "",
        channel_id: str = "",
        provider: str = "",
        model: str = "",
        fallback_used: bool = False,
        latency_ms: int = 0,
        attempts: int = 0,
        detail: str = "",
    ) -> None:
        """Append one secret-free pipeline record (analytics/audit)."""
        from backend.app.db.models.content_ops import ContentOperation

        await self.operations.add(
            ContentOperation(
                item_id=item_id,
                publication_id=publication_id,
                stage=stage,
                status=status,
                source_kind=source_kind,
                channel_id=channel_id,
                provider=provider,
                model=model,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                attempts=attempts,
                detail=detail,
                occurred_at=utcnow(),
            )
        )

    # --- classification (local encoder) -------------------------------------
    async def classify(self, item_id: str) -> ContentItem:
        """Assign category/intent with the lightweight local encoder (advisory)."""
        from backend.app.services.ai_service import AiService

        item = await self._require_item(item_id)
        text = item.cleaned_text or item.text
        if not text.strip():
            raise PipelineError("Нет текста для анализа.", status_code=409)
        service = AiService(self.session, settings=self.settings)
        outcome = await service.classify(text)
        result = outcome.result
        item.ai_category = result.category.value
        item.ai_intent = result.intent.value
        item.ai_note = result.error or f"Источник: {result.source}."
        if item.ai_status == AI_STATUS_NONE:
            item.ai_status = AI_STATUS_OK
        await self.record(
            stage="ai",
            status="classify",
            item_id=item.id,
            provider="encoder",
            model=result.model,
            fallback_used=outcome.fallback_used,
            latency_ms=result.processing_time_ms,
            detail=f"{result.category.value}/{result.intent.value}",
        )
        await self.session.commit()
        return item

    # --- generation (existing AI Gateway) -----------------------------------
    async def process(self, item_id: str, *, profile_key: str = "") -> ContentItem:
        """Apply the profile's actions through the AI Gateway with failover.

        Never loses the material: if the gateway fails, the item moves to
        ``NEEDS_REVIEW`` with ``ai_status = ai_unavailable`` and a clear note.
        """
        item = await self._require_item(item_id)
        profile = await self.profiles.get_by_key(profile_key) if profile_key else None
        if profile_key and profile is None:
            raise PipelineError("Профиль ИИ не найден.", status_code=404)
        actions = self.profiles.actions_of(profile) or ["rewrite"]
        # Keep a copy of the origin so the human can see exactly what changed.
        if not item.original_text:
            item.original_text = item.text

        text = item.cleaned_text or item.text
        if not text.strip():
            raise PipelineError("Нет текста для обработки.", status_code=409)

        system = profile.system_instructions if profile else ""
        strategy = profile.provider_policy if profile else ""
        gateway = self._gateway_service()

        output = text
        provider_used = ""
        model_used = ""
        fallback_used = False
        attempts = 0
        latency_total = 0
        failures: list[str] = []

        for action in actions:
            if action in ("classify", "moderation"):
                # Classification is handled locally; moderation is a separate step.
                continue
            instruction = ACTION_INSTRUCTIONS.get(action, "")
            if profile and profile.system_instructions:
                instruction = f"{instruction}\n{system}" if instruction else system
            started = time.perf_counter()
            response = await gateway.transform(
                task=action,
                text=output,
                instruction=instruction,
                strategy=strategy,
            )
            latency_total += int((time.perf_counter() - started) * 1000)
            attempts += len(response.attempts) or 1
            if response.ok and response.text.strip():
                output = response.text.strip()
                provider_used = response.provider_used
                model_used = response.model_used
                fallback_used = fallback_used or response.fallback_used
            else:
                failures.append(f"{action}: {response.error or 'нет ответа'}")

        item.ai_profile = profile.key if profile else ""
        if not output.strip() or output == text:
            # Every generative action failed → do not lose the material.
            item.ai_status = AI_STATUS_UNAVAILABLE
            item.ai_note = (
                "ИИ недоступен: не удалось обработать материал. "
                "Проверьте его вручную." + (f" ({failures[0]})" if failures else "")
            )
            if item.status in (ContentItemStatus.IMPORTED, ContentItemStatus.DRAFT):
                item.status = ContentItemStatus.NEEDS_REVIEW
            await self.record(
                stage="ai",
                status=AI_STATUS_UNAVAILABLE,
                item_id=item.id,
                provider=provider_used,
                model=model_used,
                attempts=attempts,
                latency_ms=latency_total,
                detail=failures[0] if failures else "нет провайдера",
            )
            await self.events.record(
                level="warning",
                module=MODULE,
                operation="ai_process",
                message="ИИ недоступен — материал отправлен на ручную проверку.",
                how_to_fix=(
                    "Проверьте провайдеров ИИ в разделе «AI» или обработайте материал вручную."
                ),
                status=AI_STATUS_UNAVAILABLE,
            )
            await self.session.commit()
            return item

        item.cleaned_text = output
        item.content_hash = content_hash(output)
        item.ai_status = AI_STATUS_OK
        item.ai_note = (
            f"Провайдер: {provider_used or '—'}"
            + (" (резервный)" if fallback_used else "")
        )
        if item.status in (
            ContentItemStatus.IMPORTED,
            ContentItemStatus.DRAFT,
            ContentItemStatus.NEEDS_REVIEW,
        ):
            item.status = ContentItemStatus.AI_PROCESSED
        await self.record(
            stage="ai",
            status=AI_STATUS_OK,
            item_id=item.id,
            provider=provider_used,
            model=model_used,
            fallback_used=fallback_used,
            attempts=attempts,
            latency_ms=latency_total,
            detail=", ".join(actions),
        )
        await self.events.info(
            MODULE,
            "Материал обработан ИИ.",
            explanation=f"Профиль: {profile.title if profile else '—'}.",
            operation="ai_process",
        )
        await self.session.commit()
        return item

    # --- human moderation ----------------------------------------------------
    async def moderate(self, item_id: str, *, decision: str, note: str = "") -> ContentItem:
        """Apply a human moderation decision (approve/reject/review)."""
        item = await self._require_item(item_id)
        mapping = {
            "approve": ContentItemStatus.APPROVED,
            "reject": ContentItemStatus.REJECTED,
            "review": ContentItemStatus.NEEDS_REVIEW,
        }
        target = mapping.get((decision or "").strip().lower())
        if target is None:
            raise PipelineError(
                "Неизвестное решение модерации.",
                how_to_fix="Допустимо: approve, reject, review.",
            )
        item.status = target
        if note:
            item.moderation_note = note
        await self.record(
            stage="moderation",
            status=target.value,
            item_id=item.id,
            detail=(note or "")[:200],
        )
        await self.events.info(
            MODULE,
            f"Модерация: {target.value}.",
            operation="moderate",
        )
        await self.session.commit()
        return item

    async def apply_rule_actions(self, item_id: str, *, source_kind: str = "") -> list[str]:
        """Apply matching declarative automation rules to an item (requirement 14).

        Returns the list of actions applied. A rule whose actions include
        ``summarize``/``rewrite``/... runs the pipeline; ``review`` moves the item
        to ``NEEDS_REVIEW``. Never arbitrary scripting.
        """
        from backend.app.services.automation_rules import (
            AutomationRuleService,
            describe_actions,
        )

        item = await self._require_item(item_id)
        service = AutomationRuleService(self.session)
        rule = await service.match(source_kind, item=item)
        if rule is None:
            return []
        actions = service.actions_of(rule)
        await self.record(
            stage="moderation",
            status="rule",
            item_id=item_id,
            source_kind=source_kind,
            detail=f"Правило: {rule.name}",
        )
        generative = [
            a for a in actions if a in ("rewrite", "summarize", "translate", "title")
        ]
        if generative:
            with contextlib.suppress(PipelineError, ProfileError, ContentError):
                await self.process(item_id, profile_key=rule.profile_key)
        if "review" in actions:
            await self.moderate(item_id, decision="review", note="Правило автоматизации.")
        elif "approve" in actions:
            await self.moderate(item_id, decision="approve", note="Правило автоматизации.")
        return describe_actions(actions)

    # --- helpers -------------------------------------------------------------
    async def _require_item(self, item_id: str) -> ContentItem:
        item = await self.items.get(item_id)
        if item is None:
            raise PipelineError("Материал не найден.", status_code=404)
        return item


__all__ = [
    "ACTION_INSTRUCTIONS",
    "ContentPipelineService",
    "PipelineError",
]
