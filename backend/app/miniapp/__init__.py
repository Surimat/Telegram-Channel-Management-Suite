"""Telegram Mini App support (PHASE 9).

The Mini App reuses the *same* SPA and the *same* API (decision D-003). This
package only adds authentication: Telegram hands the client a signed ``initData``
string, which we verify server-side before trusting the caller's Telegram user id.

Nothing here imports FastAPI or Telegram libraries, so the verification logic is
unit-testable in isolation and free of Telegram implementation details (D-001).
"""

from __future__ import annotations

from backend.app.miniapp.auth import (
    MiniAppAuthError,
    MiniAppUser,
    verify_init_data,
)

__all__ = ["MiniAppAuthError", "MiniAppUser", "verify_init_data"]
