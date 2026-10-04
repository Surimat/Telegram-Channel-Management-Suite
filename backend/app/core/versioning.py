"""Version comparison and update-artifact helpers (pure, testable).

Kept free of I/O so the update logic can be unit-tested without network access.
Only ``X.Y.Z`` style versions with an optional leading ``v`` and an optional
pre-release suffix are understood; anything unparsable compares as "not newer"
rather than crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+](.*))?$")


@dataclass(frozen=True, slots=True)
class ParsedVersion:
    major: int
    minor: int
    patch: int
    pre: str = ""

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)


def parse_version(value: str) -> ParsedVersion | None:
    """Parse ``v1.2.3`` / ``1.2.3`` / ``1.2.3-rc1``; ``None`` when invalid."""
    match = _VERSION_RE.match((value or "").strip())
    if match is None:
        return None
    major, minor, patch, pre = match.groups()
    return ParsedVersion(int(major), int(minor), int(patch), pre or "")


def is_newer(candidate: str, current: str) -> bool:
    """Return True when ``candidate`` is a strictly newer stable version.

    A pre-release candidate is never considered newer than a stable current
    version (we do not auto-update users onto release candidates).
    """
    new = parse_version(candidate)
    old = parse_version(current)
    if new is None or old is None:
        return False
    if new.is_prerelease:
        return False
    return (new.major, new.minor, new.patch) > (old.major, old.minor, old.patch)


def pick_asset(
    assets: list[dict[str, object]], *, suffix: str = ".zip"
) -> dict[str, object] | None:
    """Pick the portable artifact (and its ``.sha256`` sibling) from a release.

    Prefers an asset whose name ends with ``suffix``; returns it, and the caller
    can find the checksum asset by looking for ``<name>.sha256``.
    """
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.lower().endswith(suffix.lower()):
            return asset
    return None


def find_checksum_asset(
    assets: list[dict[str, object]], artifact_name: str
) -> dict[str, object] | None:
    """Return the ``<artifact>.sha256`` asset when the release ships one."""
    wanted = f"{artifact_name}.sha256".lower()
    for asset in assets:
        if str(asset.get("name", "")).lower() == wanted:
            return asset
    return None


def parse_sha256(text: str) -> str:
    """Extract the first 64-hex-char token from a checksum file."""
    for token in re.split(r"[\s*]+", (text or "").strip()):
        if len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token):
            return token.lower()
    return ""


__all__ = [
    "ParsedVersion",
    "find_checksum_asset",
    "is_newer",
    "parse_sha256",
    "parse_version",
    "pick_asset",
]
