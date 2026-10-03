"""Setting model: UI-editable configuration persisted in the database.

Values are stored as strings with a declared type so the UI can render the right
control and validate input. Secrets are NOT stored here; they live in ``.env`` /
the OS secret store (see ``docs/SECURITY.md``).
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VALUE_TYPES = ("string", "int", "float", "bool", "json")


class Setting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), default="string", nullable=False)

    # Presentation metadata for the UI (so settings are self-documenting).
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Setting key={self.key!r} type={self.value_type!r}>"
