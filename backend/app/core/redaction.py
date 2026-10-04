"""Secret redaction for user-facing diagnostics reports.

The diagnostics report is meant to be *shared* (attached to a bug report), so it
must never contain credentials or personal data. This module is the single place
that decides what counts as a secret and replaces it with a fixed placeholder.

Design:
* ``redact_text`` masks the live configured secrets (the same registry the
  logging filter uses) and then applies conservative pattern rules for values
  that look like secrets even if they are not in the registry (bot tokens,
  ``api_hash``/``api_id``, session strings, phone numbers).
* ``scan`` reports *whether* a text still looks like it contains a secret
  (used as a final safety gate before an export is written).
* ``redact_mapping`` walks nested structures (dict/list) for report payloads.

Nothing here logs or returns a secret; it only ever returns the placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED = "***REDACTED***"

# Telegram bot token: <numeric id>:<35-char base64url-ish secret>.
_BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,40}\b")
# Telethon StringSession (long base64url) and session file references.
_SESSION_RE = re.compile(r"\b1[A-Za-z0-9_-]{40,}\b")
# Phone numbers in E.164 form (require the leading ``+`` so compact numeric
# timestamps/ids are not mistaken for a phone number).
_PHONE_RE = re.compile(r"\+\d[\d\s\-()]{8,}\d")
# Common secret-bearing key/value pairs (api_hash, api_id, token, password).
# The value must not already be the redaction placeholder, otherwise a redacted
# report would keep flagging itself during the safety scan.
_KV_RE = re.compile(
    r"(?i)\b(api_hash|api_id|token|password|passwd|secret|session)\b"
    r"\s*[:=]\s*(?!\*{3}REDACTED\*{3})[^\s,;\"']+"
)
# Long hex/base64 blobs (hashes, keys) of 32+ characters.
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")

# Fields that must never appear in a report payload at all.
_FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "token_encrypted",
        "api_hash",
        "api_id",
        "phone",
        "phone_masked",
        "phone_encrypted",
        "password",
        "session",
        "session_ref",
        "session_file",
        "session_path",
        "secret",
        "app_secret_key",
        "manager_bot_token",
    }
)


def _registry_values(extra: list[str] | None) -> list[str]:
    """Return the currently registered secret strings (and any extras)."""
    values: list[str] = []
    if extra:
        values.extend(extra)
    try:
        from backend.app.core.config import get_settings, secret_values

        values.extend(secret_values(get_settings()))
    except Exception:  # pragma: no cover - settings unavailable in some contexts
        pass
    # Longest first so a token that contains a shorter secret is fully masked.
    return sorted({v for v in values if v and len(v) >= 4}, key=len, reverse=True)


def redact_text(text: str, *, extra_secrets: list[str] | None = None) -> str:
    """Return ``text`` with every configured/pattern-matched secret masked."""
    if not text:
        return text
    redacted = text
    for secret in _registry_values(extra_secrets):
        redacted = redacted.replace(secret, REDACTED)
    redacted = _BOT_TOKEN_RE.sub(REDACTED, redacted)
    redacted = _SESSION_RE.sub(REDACTED, redacted)
    redacted = _KV_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", redacted)
    redacted = _PHONE_RE.sub(REDACTED, redacted)
    redacted = _HEX_RE.sub(REDACTED, redacted)
    redacted = _B64_RE.sub(REDACTED, redacted)
    return redacted


def scan(text: str, *, extra_secrets: list[str] | None = None) -> list[str]:
    """Return human-readable findings for anything that still looks secret.

    An empty list means the text passed the safety scan.
    """
    findings: list[str] = []
    if not text:
        return findings
    for secret in _registry_values(extra_secrets):
        if secret in text:
            findings.append("configured secret value")
    if _BOT_TOKEN_RE.search(text):
        findings.append("bot token pattern")
    if _SESSION_RE.search(text):
        findings.append("session string pattern")
    if _KV_RE.search(text):
        findings.append("secret key/value pattern")
    if _HEX_RE.search(text):
        findings.append("long hex value")
    return findings


def redact_mapping(value: object, *, extra_secrets: list[str] | None = None) -> object:
    """Recursively redact a JSON-like structure.

    Forbidden keys are dropped entirely; other string values are redacted with
    :func:`redact_text`.
    """
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                continue
            result[str(key)] = redact_mapping(item, extra_secrets=extra_secrets)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_mapping(item, extra_secrets=extra_secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, extra_secrets=extra_secrets)
    return value


@dataclass
class RedactionResult:
    """Outcome of redacting + scanning a report payload."""

    payload: object
    clean: bool
    findings: list[str]


def redact_and_verify(
    payload: object, *, extra_secrets: list[str] | None = None
) -> RedactionResult:
    """Redact ``payload`` then re-scan the serialised result as a safety gate."""
    import json

    redacted = redact_mapping(payload, extra_secrets=extra_secrets)
    try:
        serialised = json.dumps(redacted, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialised = str(redacted)
    findings = scan(serialised, extra_secrets=extra_secrets)
    return RedactionResult(payload=redacted, clean=not findings, findings=findings)
