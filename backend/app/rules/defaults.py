"""Default, editable classification rules seeded on first run (PHASE 3).

These are ordinary :class:`RuleSpec` values: the UI can edit or delete them.
They give a beginner a working Rules Engine out of the box. Keywords are
lower-cased substrings; matching is done on the lower-cased post text.
"""

from __future__ import annotations

from backend.app.rules.engine import Category, RuleSpec


def default_rule_specs() -> list[RuleSpec]:
    """Return the seed rule set (RU + EN keywords)."""
    return [
        RuleSpec(
            category=Category.DONATION,
            name="Донат",
            keywords=["донат", "донатик", "donate", "donation", "пожертв", "чаевые"],
            phrases=["спасибо за донат", "поддержать канал", "thank you for donating"],
            allowed_reactions=["❤️", "🙏", "👍"],
            preferred_reactions=["❤️", "🙏"],
            forbidden_reactions=["😂", "💩", "🤡", "😡"],
            priority=5,
        ),
        RuleSpec(
            category=Category.NEWS,
            name="Новость",
            keywords=["новость", "новости", "news", "анонс", "релиз", "обновление", "update"],
            phrases=["важная новость", "breaking news"],
            # A "грустная новость" is sad, not a celebratory news item.
            exclusions=["грустн", "печальн", "траур", "потеряли", "умер", "погиб", "скорб"],
            forbidden_reactions=["🤡", "💩"],
            priority=2,
        ),
        RuleSpec(
            category=Category.ANNOUNCEMENT,
            name="Анонс",
            keywords=["анонс", "старт", "запуск", "announce", "announcement", "скоро"],
            phrases=["уже скоро", "не пропустите"],
            priority=1,
        ),
        RuleSpec(
            category=Category.FUNNY,
            name="Смешное",
            keywords=["смешно", "юмор", "прикол", "шутка", "funny", "joke", "мем", "meme"],
            phrases=["ха-ха", "lol", "ржу не могу"],
            priority=1,
        ),
        RuleSpec(
            category=Category.SAD,
            name="Грустное",
            keywords=["грусть", "печаль", "жаль", "траур", "sad", "rip", "потеря", "утрата"],
            phrases=["светлая память", "очень жаль"],
            forbidden_reactions=["😂", "🤣", "🎉", "🔥"],
            priority=2,
        ),
        RuleSpec(
            category=Category.ANGRY,
            name="Возмущение",
            keywords=[
                "возмут", "негодя", "злость", "обман", "возмущён",
                "angry", "outrage", "scam",
            ],
            phrases=["это возмутительно", "как так можно"],
            forbidden_reactions=["😂", "🤣", "🎉", "❤️"],
            priority=2,
        ),
        RuleSpec(
            category=Category.CUTE,
            name="Милое",
            keywords=["мило", "милашка", "cute", "котик", "котёнок", "щенок", "kitten", "puppy"],
            phrases=["такой милый"],
            priority=1,
        ),
        RuleSpec(
            category=Category.SUPPORT,
            name="Поддержка",
            keywords=["поддержк", "помощь", "support", "help", "не оставляйте", "поддержите"],
            phrases=["нужна помощь", "просим поддержки"],
            priority=2,
        ),
    ]


__all__ = ["default_rule_specs"]
