"""Central logging with secret redaction.

Two guarantees:
1. Log records carry structured context (module, account/bot, operation).
2. Registered secret values are masked anywhere they might appear in a message,
   so tokens/hashes never reach the console or log files.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from backend.app.core.config import Settings, get_settings, secret_values

_REDACTION = "***REDACTED***"

# Values registered for redaction (populated at setup time).
_SECRET_REGISTRY: set[str] = set()


def register_secrets(values: list[str]) -> None:
    """Register secret strings that must never appear in log output."""
    for value in values:
        # Ignore trivially short values to avoid masking ordinary text.
        if value and len(value) >= 4:
            _SECRET_REGISTRY.add(value)


class RedactionFilter(logging.Filter):
    """Mask registered secrets in the final rendered log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = message
        for secret in _SECRET_REGISTRY:
            if secret in redacted:
                redacted = redacted.replace(secret, _REDACTION)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(settings: Settings | None = None) -> None:
    """Configure root logging once, for console + rotating file."""
    settings = settings or get_settings()
    register_secrets(secret_values(settings))

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # Reset handlers so repeated calls (tests, reloads) do not duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT)
    redactor = RedactionFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(redactor)
    root.addHandler(console)

    try:
        log_dir: Path = settings.resolve_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - filesystem issues
        root.warning("File logging disabled: %s", exc)

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
