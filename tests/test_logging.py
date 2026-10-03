"""Logging redaction tests."""

from __future__ import annotations

import logging

from backend.app.core.logging import RedactionFilter, register_secrets


def test_redaction_masks_registered_secret() -> None:
    register_secrets(["TOPSECRETVALUE123"])
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token is TOPSECRETVALUE123 here",
        args=(),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    assert "TOPSECRETVALUE123" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_short_values_not_registered() -> None:
    # Very short values are ignored to avoid masking ordinary words.
    from backend.app.core import logging as app_logging

    before = len(app_logging._SECRET_REGISTRY)
    register_secrets(["ab"])
    assert len(app_logging._SECRET_REGISTRY) == before
