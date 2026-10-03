"""Rules Engine tests: deterministic classification, exclusions, priorities."""

from __future__ import annotations

from backend.app.rules.engine import (
    Category,
    RulesEngine,
    RuleSpec,
    detect_language,
)


def _rules() -> list[RuleSpec]:
    return [
        RuleSpec(
            category=Category.DONATION,
            id="don",
            keywords=["донат"],
            phrases=["спасибо за донат"],
            allowed_reactions=["❤️", "🙏", "👍"],
            preferred_reactions=["❤️"],
            forbidden_reactions=["😂", "💩", "🤡", "😡"],
            priority=5,
        ),
        RuleSpec(
            category=Category.FUNNY,
            id="fun",
            keywords=["смешно", "прикол"],
            priority=1,
        ),
        RuleSpec(
            category=Category.NEWS,
            id="news",
            keywords=["новость", "релиз"],
            exclusions=["не новость"],
            priority=2,
        ),
    ]


def test_classify_donation_by_phrase() -> None:
    match = RulesEngine(_rules()).classify("Друзья, спасибо за донат!")
    assert match.category is Category.DONATION
    assert match.confidence > 0.5
    assert "❤️" in match.allowed_reactions
    assert "😂" not in match.allowed_reactions


def test_forbidden_reactions_excluded_from_policy() -> None:
    match = RulesEngine(_rules()).classify("спасибо за донат")
    for bad in ("😂", "💩", "🤡", "😡"):
        assert bad not in match.allowed_reactions
        assert bad not in match.preferred_reactions


def test_exclusions_disable_a_rule() -> None:
    engine = RulesEngine(_rules())
    assert engine.classify("Это не новость, а слух.").category is not Category.NEWS


def test_higher_priority_wins_on_equal_score() -> None:
    # "новость" (priority 2) beats "прикол" (priority 1) when both match once.
    match = RulesEngine(_rules()).classify("прикол и новость")
    assert match.category is Category.NEWS


def test_unknown_text_is_neutral() -> None:
    match = RulesEngine(_rules()).classify("совершенно нейтральный текст")
    assert match.category is Category.NEUTRAL
    assert match.source == "default"
    assert match.confidence == 0.0


def test_manual_override_beats_score() -> None:
    rules = [
        *_rules(),
        RuleSpec(
            category=Category.ANNOUNCEMENT, id="pin", keywords=["донат"], manual_override=True
        ),
    ]
    match = RulesEngine(rules).classify("спасибо за донат")
    assert match.category is Category.ANNOUNCEMENT
    assert match.source == "manual"


def test_deterministic_output() -> None:
    engine = RulesEngine(_rules())
    text = "смешно, прикол, спасибо за донат"
    first = engine.classify(text)
    second = engine.classify(text)
    assert (first.category, first.confidence) == (second.category, second.confidence)


def test_regex_match_and_broken_regex_ignored() -> None:
    rules = [RuleSpec(category=Category.NEWS, id="re", regexes=["rel[ea]ase", "("])]
    match = RulesEngine(rules).classify("new release available")
    assert match.category is Category.NEWS


def test_language_gate() -> None:
    rules = [RuleSpec(category=Category.NEWS, id="en", keywords=["news"], language="en")]
    engine = RulesEngine(rules)
    assert engine.classify("news").category is Category.NEWS
    # Russian text is not English → the rule is skipped.
    assert engine.classify("новости news").category is Category.NEUTRAL


def test_min_confidence_filters_weak_matches() -> None:
    rules = [RuleSpec(category=Category.NEWS, id="strict", keywords=["news"], min_confidence=0.99)]
    assert RulesEngine(rules).classify("news").category is Category.NEUTRAL


def test_detect_language() -> None:
    assert detect_language("привет") == "ru"
    assert detect_language("hello") == "en"
