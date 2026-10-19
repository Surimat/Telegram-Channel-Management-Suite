"""Manager-bot runtime schemas (post-1.0 hardening)."""

from __future__ import annotations

from pydantic import BaseModel


class ManagerStatusOut(BaseModel):
    """Plain-language manager-bot status for the Dashboard/System page."""

    connected: bool
    runtime_running: bool
    username: str = ""
    health: str = "unknown"
    status_label: str = "не подключён"
    admin_count: int = 0
    notifications_enabled: bool = True
    pending_notifications: int = 0
    how_to_fix: str = ""
