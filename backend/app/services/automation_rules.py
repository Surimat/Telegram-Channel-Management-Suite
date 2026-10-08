"""Declarative automation rules (Content Operations 2.0, requirement 14).

A rule is ``SOURCE + CONDITION → ACTION``. It is deliberately **not** a scripting
engine: conditions match on a small set of declared fields and actions come from a
fixed allow-list. This keeps the pipeline safe and explainable — the owner can
describe intent, not execute code.

Condition fields (all optional, ANDed):
* ``contains``   — list of substrings; the text must contain at least one;
* ``not_contains`` — list of substrings; the text must contain none;
* ``min_length`` / ``max_length`` — character bounds;
* ``language``   — matches the item's language tag;
* ``category``   — matches the locally classified category.

Action vocabulary (allow-list, never arbitrary):
``rewrite``, ``summarize``, ``translate``, ``classify``, ``moderation``, ``title``,
``description``, ``first_comment``, ``review``, ``approve``.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.content import ContentItem
from backend.app.db.models.content_ops import AutomationRule
from backend.app.db.repositories.content_ops import AutomationRuleRepository

#: Fixed action vocabulary. ``review``/``approve`` are moderation outcomes; the
#: rest are pipeline/AI actions.
VALID_RULE_ACTIONS = (
    "rewrite",
    "summarize",
    "translate",
    "classify",
    "moderation",
    "title",
    "description",
    "first_comment",
    "review",
    "approve",
)

RULE_ACTION_TITLES = {
    "rewrite": "Переписать",
    "summarize": "Резюме",
    "translate": "Перевести",
    "classify": "Классифицировать",
    "moderation": "Модерация",
    "title": "Заголовок",
    "description": "Описание",
    "first_comment": "Первый комментарий",
    "review": "Отправить на проверку",
    "approve": "Одобрить",
}


class RuleError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


def describe_actions(actions: list[str]) -> list[str]:
    """Return the human titles for a list of action ids."""
    return [RULE_ACTION_TITLES.get(a, a) for a in actions]


class AutomationRuleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rules = AutomationRuleRepository(session)

    async def list_rules(self) -> list[AutomationRule]:
        return await self.rules.list_all()

    async def create(
        self,
        *,
        name: str,
        source_kind: str = "",
        condition: dict[str, object] | None = None,
        actions: list[str] | None = None,
        profile_key: str = "",
        priority: int = 0,
        description: str = "",
        enabled: bool = True,
    ) -> AutomationRule:
        chosen = [a for a in (actions or []) if a in VALID_RULE_ACTIONS]
        if not chosen:
            raise RuleError(
                "Выберите хотя бы одно действие.",
                how_to_fix="Допустимо: " + ", ".join(VALID_RULE_ACTIONS) + ".",
            )
        rule = AutomationRule(
            name=(name or "").strip() or "Правило",
            source_kind=(source_kind or "").strip(),
            condition=json.dumps(_clean_condition(condition or {}), ensure_ascii=False),
            actions=json.dumps(chosen, ensure_ascii=False),
            profile_key=(profile_key or "").strip(),
            priority=int(priority or 0),
            description=description or "",
            enabled=enabled,
        )
        await self.rules.add(rule)
        await self.session.commit()
        return rule

    async def update(self, rule_id: str, **fields: object) -> AutomationRule:
        rule = await self.rules.get(rule_id)
        if rule is None:
            raise RuleError("Правило не найдено.", status_code=404)
        if fields.get("name") is not None:
            rule.name = str(fields["name"])
        if fields.get("source_kind") is not None:
            rule.source_kind = str(fields["source_kind"]).strip()
        if fields.get("condition") is not None:
            raw = fields["condition"]
            condition = raw if isinstance(raw, dict) else {}
            rule.condition = json.dumps(_clean_condition(condition), ensure_ascii=False)  # type: ignore[arg-type]
        if fields.get("actions") is not None:
            raw = fields["actions"]
            actions = [str(a) for a in raw] if isinstance(raw, list) else []  # type: ignore[union-attr]
            rule.actions = json.dumps(
                [a for a in actions if a in VALID_RULE_ACTIONS], ensure_ascii=False
            )
        if fields.get("profile_key") is not None:
            rule.profile_key = str(fields["profile_key"]).strip()
        if fields.get("priority") is not None:
            rule.priority = int(fields["priority"])  # type: ignore[arg-type]
        if fields.get("description") is not None:
            rule.description = str(fields["description"])
        if fields.get("enabled") is not None:
            rule.enabled = bool(fields["enabled"])
        await self.session.flush()
        await self.session.commit()
        return rule

    async def delete(self, rule_id: str) -> None:
        rule = await self.rules.get(rule_id)
        if rule is None:
            raise RuleError("Правило не найдено.", status_code=404)
        await self.rules.delete(rule)
        await self.session.commit()

    def actions_of(self, rule: AutomationRule) -> list[str]:
        try:
            value = json.loads(rule.actions or "[]")
        except (ValueError, TypeError):
            return []
        if not isinstance(value, list):
            return []
        return [str(a) for a in value if str(a) in VALID_RULE_ACTIONS]

    def condition_of(self, rule: AutomationRule) -> dict[str, object]:
        try:
            value = json.loads(rule.condition or "{}")
        except (ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def matches(self, rule: AutomationRule, item: ContentItem) -> bool:
        """Return True when ``item`` satisfies the rule's declarative condition."""
        cond = self.condition_of(rule)
        text = (item.cleaned_text or item.text or "").lower()
        contains = [str(c) for c in cond.get("contains", []) if str(c).strip()] if isinstance(
            cond.get("contains"), list
        ) else []
        if contains and not any(c.lower() in text for c in contains):
            return False
        not_contains = (
            [str(c) for c in cond.get("not_contains", []) if str(c).strip()]
            if isinstance(cond.get("not_contains"), list)
            else []
        )
        if not_contains and any(c.lower() in text for c in not_contains):
            return False
        if cond.get("min_length") is not None and len(text) < int(cond["min_length"]):  # type: ignore[arg-type]
            return False
        if cond.get("max_length") is not None and len(text) > int(cond["max_length"]):  # type: ignore[arg-type]
            return False
        if cond.get("language") and (item.language or "").lower() != str(cond["language"]).lower():
            return False
        return not (
            cond.get("category")
            and (item.ai_category or "").lower() != str(cond["category"]).lower()
        )

    async def match(
        self, source_kind: str, *, item: ContentItem
    ) -> AutomationRule | None:
        """Return the highest-priority active rule matching ``item`` (or None)."""
        for rule in await self.rules.list_active(source_kind):
            if self.matches(rule, item):
                return rule
        return None


def _clean_condition(condition: dict[str, object]) -> dict[str, object]:
    """Keep only declared condition fields (defensive, never arbitrary)."""
    out: dict[str, object] = {}
    for key in ("contains", "not_contains"):
        raw = condition.get(key)
        if isinstance(raw, list):
            out[key] = [str(v) for v in raw if str(v).strip()]
    for key in ("min_length", "max_length"):
        if condition.get(key) is not None:
            try:
                out[key] = int(condition[key])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
    for key in ("language", "category"):
        if condition.get(key):
            out[key] = str(condition[key])
    return out


__all__ = [
    "RULE_ACTION_TITLES",
    "VALID_RULE_ACTIONS",
    "AutomationRuleService",
    "RuleError",
    "describe_actions",
]
