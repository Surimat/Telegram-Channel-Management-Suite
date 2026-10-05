"""Real MTProto user-account provider backed by Telethon.

This is the **only** module that imports Telethon (decision D-001). It translates
library exceptions into :mod:`backend.app.providers.errors`, never logs or
returns session contents / api_hash, and uses **lazy connections**: a client is
created and connected only for the duration of one operation, then closed. This
keeps background work minimal — important for weak Windows machines and the
future portable runtime (decision D-023).

Session storage: a Telethon SQLite session file inside the configured sessions
directory (outside git, excluded from the Docker image). The API hash is sealed
at rest by the service layer and only ever passed in here as a plain string.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from backend.app.core.config import Settings, get_settings
from backend.app.providers.errors import (
    AlreadyParticipantError,
    ApiCredentialsInvalidError,
    AuthCodeExpiredError,
    AuthCodeInvalidError,
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    NetworkError,
    PasswordInvalidError,
    PasswordRequiredError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    PrivacyRestrictedError,
    SessionInvalidError,
    TelegramProviderError,
    UnsupportedOperationError,
)
from backend.app.providers.types import (
    ChannelFetchResult,
    ChannelMessage,
    EntityRef,
    ParticipantPage,
    PermissionReport,
    SendCodeResult,
    SignInResult,
    UserIdentity,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from telethon import TelegramClient


def _normalize_path(session_path: Path | None) -> str:
    """Return a Telethon session file path (Telethon appends ``.session``)."""
    if session_path is None:
        raise SessionInvalidError(
            "Не задан файл сессии.",
            how_to_fix="Добавьте аккаунт заново через мастер.",
            technical="TelethonSessionProvider:no_path",
        )
    path = str(session_path)
    if path.endswith(".session"):
        path = path[: -len(".session")]
    return path


class TelethonSessionProvider:
    """Concrete :class:`SessionProvider` using Telethon (lazy per-operation)."""

    def __init__(
        self,
        *,
        api_id: str = "",
        api_hash: str = "",
        session_path: Path | None = None,
        provider_name: str = "auto",
        settings: Settings | None = None,
        proxy: dict[str, object] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._api_id_raw = str(api_id or "").strip()
        self._api_hash = api_hash or ""
        self._session_path = session_path
        self._provider_name = provider_name
        #: Telethon proxy dict (never contains a secret we log). ``None`` = direct.
        self._proxy = proxy
        self._client: TelegramClient | None = None
        self._connected = False

    # --- lifecycle -----------------------------------------------------------
    def _build_client(self) -> TelegramClient:
        if not self._api_id_raw.isdigit():
            raise ApiCredentialsInvalidError(
                technical="TelethonSessionProvider:api_id_not_numeric"
            )
        if not self._api_hash:
            raise ApiCredentialsInvalidError(technical="TelethonSessionProvider:no_api_hash")
        from telethon import TelegramClient

        return TelegramClient(
            _normalize_path(self._session_path),
            int(self._api_id_raw),
            self._api_hash,
            proxy=self._proxy,
        )

    async def connect(self) -> None:
        if self._connected:
            return
        self._client = self._build_client()
        try:
            await self._client.connect()
        except Exception as exc:
            await self._safe_disconnect()
            raise self._translate(exc) from exc
        self._connected = True

    async def aclose(self) -> None:
        await self._safe_disconnect()

    async def _safe_disconnect(self) -> None:
        self._connected = False
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            self._client = None

    async def __aenter__(self) -> TelethonSessionProvider:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # --- error translation ---------------------------------------------------
    def _translate(self, exc: Exception) -> TelegramProviderError:
        from telethon.errors import (
            ApiIdInvalidError,
            AuthKeyUnregisteredError,
            ChannelPrivateError,
            PasswordHashInvalidError,
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            SessionPasswordNeededError,
            SessionRevokedError,
            UserAlreadyParticipantError,
        )
        from telethon.errors import (
            ChatAdminRequiredError as TelethonAdminRequired,
        )
        from telethon.errors import (
            FloodWaitError as TelethonFloodWait,
        )
        from telethon.errors import (
            PhoneNumberBannedError as TelethonPhoneBanned,
        )
        from telethon.errors import (
            PhoneNumberInvalidError as TelethonPhoneInvalid,
        )
        from telethon.errors import (
            UsernameInvalidError as TelethonUsernameInvalid,
        )
        from telethon.errors import (
            UsernameNotOccupiedError as TelethonUsernameNotOccupied,
        )

        if isinstance(exc, TelethonFloodWait):
            return FloodWaitError(int(exc.seconds), technical=type(exc).__name__)
        if isinstance(exc, SessionPasswordNeededError):
            return PasswordRequiredError(technical=type(exc).__name__)
        if isinstance(exc, PasswordHashInvalidError):
            return PasswordInvalidError(technical=type(exc).__name__)
        if isinstance(exc, PhoneCodeInvalidError):
            return AuthCodeInvalidError(technical=type(exc).__name__)
        if isinstance(exc, PhoneCodeExpiredError):
            return AuthCodeExpiredError(technical=type(exc).__name__)
        if isinstance(exc, TelethonPhoneInvalid):
            return PhoneNumberInvalidError(technical=type(exc).__name__)
        if isinstance(exc, TelethonPhoneBanned):
            return PhoneNumberBannedError(technical=type(exc).__name__)
        if isinstance(exc, ApiIdInvalidError):
            return ApiCredentialsInvalidError(technical=type(exc).__name__)
        if isinstance(exc, (TelethonUsernameInvalid, TelethonUsernameNotOccupied)):
            return EntityNotFoundError(technical=type(exc).__name__)
        if isinstance(exc, ChannelPrivateError):
            return PrivacyRestrictedError(technical=type(exc).__name__)
        if isinstance(exc, TelethonAdminRequired):
            return ChatAdminRequiredError(technical=type(exc).__name__)
        if isinstance(exc, UserAlreadyParticipantError):
            return AlreadyParticipantError(technical=type(exc).__name__)
        if isinstance(exc, (AuthKeyUnregisteredError, SessionRevokedError)):
            return SessionInvalidError(technical=type(exc).__name__)
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return NetworkError(
                "Не удалось связаться с Telegram.",
                how_to_fix="Проверьте интернет-соединение и повторите попытку.",
                technical=type(exc).__name__,
            )
        return TelegramProviderError(
            "Непредвиденная ошибка при работе с аккаунтом.",
            technical=type(exc).__name__,
        )

    async def _call(self, factory):  # type: ignore[no-untyped-def]
        """Run ``factory(client)`` on a lazily connected client, then close."""
        await self.connect()
        try:
            return await factory(self._client)
        except TelegramProviderError:
            raise
        except Exception as exc:
            raise self._translate(exc) from exc
        finally:
            await self.aclose()

    # --- identity ------------------------------------------------------------
    @staticmethod
    def _identity(me: object) -> UserIdentity:
        return UserIdentity(
            id=int(getattr(me, "id", 0)),
            username=str(getattr(me, "username", "") or ""),
            first_name=str(getattr(me, "first_name", "") or ""),
            last_name=str(getattr(me, "last_name", "") or ""),
            phone=str(getattr(me, "phone", "") or ""),
            is_premium=getattr(me, "premium", None),
            is_bot=bool(getattr(me, "bot", False)),
        )

    async def get_me(self) -> UserIdentity:
        async def _run(client):  # type: ignore[no-untyped-def]
            me = await client.get_me()
            if me is None:
                raise SessionInvalidError(technical="TelethonSessionProvider:no_me")
            return self._identity(me)

        return await self._call(_run)

    async def health(self) -> UserIdentity:
        return await self.get_me()

    # --- authorization flow --------------------------------------------------
    async def send_code(self, phone: str) -> SendCodeResult:
        async def _run(client):  # type: ignore[no-untyped-def]
            sent = await client.send_code_request(phone)
            code_type = type(getattr(sent, "type", None)).__name__
            return SendCodeResult(
                phone_code_hash=str(sent.phone_code_hash),
                code_type=code_type,
                next_step="code",
                timeout=getattr(sent, "timeout", None),
            )

        return await self._call(_run)

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> SignInResult:
        async def _run(client):  # type: ignore[no-untyped-def]
            try:
                await client.sign_in(
                    phone=phone, code=code, phone_code_hash=phone_code_hash
                )
            except Exception as exc:
                from telethon.errors import SessionPasswordNeededError

                if isinstance(exc, SessionPasswordNeededError):
                    return SignInResult(ok=False, needs_password=True)
                raise
            me = await client.get_me()
            return SignInResult(ok=True, identity=self._identity(me) if me else None)

        return await self._call(_run)

    async def sign_in_password(self, password: str) -> SignInResult:
        async def _run(client):  # type: ignore[no-untyped-def]
            await client.sign_in(password=password)
            me = await client.get_me()
            return SignInResult(ok=True, identity=self._identity(me) if me else None)

        return await self._call(_run)

    # --- session file --------------------------------------------------------
    async def export_session(self) -> None:
        async def _run(client):  # type: ignore[no-untyped-def]
            # Telethon persists the SQLite session on write; saving is a no-op
            # for file sessions but guarantees the auth key is flushed.
            save = getattr(client.session, "save", None)
            if callable(save):
                save()

        await self._call(_run)

    async def import_string_session(self, value: str, target_path: Path) -> None:
        """Convert a Telethon StringSession into a local SQLite session file.

        The raw string is used only in memory; it is never logged or returned.
        Telethon's ``StringSession`` shares the same auth key, so copying it into
        a ``SQLiteSession`` at ``target_path`` yields a normal file session the
        rest of the app already understands.
        """
        if not value:
            raise SessionInvalidError(
                "Пустая строка сессии.",
                how_to_fix="Скопируйте строку StringSession целиком.",
                technical="TelethonSessionProvider:empty_string_session",
            )
        from telethon.sessions import SQLiteSession, StringSession

        parsed = StringSession(value)
        target = target_path
        if target.suffix == ".session":
            target = target.with_suffix("")
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = SQLiteSession(str(target))
        try:
            destination.set_dc(
                parsed.dc_id,
                parsed.server_address,
                parsed.port,
            )
            destination.auth_key = parsed.auth_key
            save = getattr(destination, "save", None)
            if callable(save):
                save()
        finally:
            destination.close()

    # --- extension points for PHASE 5 / PHASE 6 ------------------------------
    async def resolve_entity(self, username_or_id: str | int) -> EntityRef:
        async def _run(client):  # type: ignore[no-untyped-def]
            entity = await client.get_entity(username_or_id)
            kind = "user"
            if getattr(entity, "megagroup", False):
                kind = "group"
            elif getattr(entity, "broadcast", False):
                kind = "channel"
            # Channels/groups may hide their member list; report that instead of
            # letting an empty scan look like "no participants" (SETUP/UI D-00x).
            hidden = bool(
                getattr(entity, "participants_hidden", False)
                or getattr(entity, "join_to_send", False)
            )
            is_admin = bool(
                getattr(getattr(entity, "admin_rights", None), "is_admin", False)
                or getattr(entity, "creator", False)
            )
            return EntityRef(
                id=int(getattr(entity, "id", 0)),
                username=str(getattr(entity, "username", "") or ""),
                title=str(getattr(entity, "title", "") or getattr(entity, "first_name", "") or ""),
                kind=kind,
                participants_count=getattr(entity, "participants_count", None),
                is_admin=is_admin,
                participants_hidden=hidden,
            )

        return await self._call(_run)

    async def search_public(self, query: str, *, limit: int = 20) -> list[EntityRef]:
        """Search public channels/groups via Telegram's official search.

        Uses ``messages.searchGlobal`` when the installed Telethon exposes it.
        Only public broadcast/megagroup results are returned; whatever Telegram
        returns is passed through unchanged (possibly empty). Limits are never
        bypassed: a FloodWait/other error is translated to a provider error.
        """
        query = (query or "").strip()
        if not query:
            return []
        try:
            from telethon import functions
        except Exception:  # pragma: no cover - telethon always present here
            raise UnsupportedOperationError(
                "Поиск Telegram недоступен в этой версии.",
                how_to_fix="Обновите библиотеку telethon.",
            ) from None
        request_cls = getattr(getattr(functions, "messages", None), "SearchGlobalRequest", None)
        if request_cls is None:
            raise UnsupportedOperationError(
                "Поиск Telegram недоступен в этой версии.",
                how_to_fix="Обновите библиотеку telethon.",
            )

        async def _run(client):  # type: ignore[no-untyped-def]
            result = await client(request_cls(q=query, limit=max(1, limit)))
            refs: list[EntityRef] = []
            seen: set[int] = set()
            for chat in list(getattr(result, "chats", []) or []):
                if not (getattr(chat, "broadcast", False) or getattr(chat, "megagroup", False)):
                    continue
                cid = int(getattr(chat, "id", 0))
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                refs.append(
                    EntityRef(
                        id=cid,
                        username=str(getattr(chat, "username", "") or ""),
                        title=str(getattr(chat, "title", "") or ""),
                        kind="group" if getattr(chat, "megagroup", False) else "channel",
                        participants_count=getattr(chat, "participants_count", None),
                        subscribers=int(getattr(chat, "participants_count", 0) or 0),
                    )
                )
            return refs

        return await self._call(_run)

    async def get_channel_recommendations(
        self, channel: str | int, *, limit: int = 20
    ) -> list[EntityRef]:
        """Return channels Telegram recommends as similar to ``channel`` (v1.1).

        Uses ``channels.getChannelRecommendations`` when the installed Telethon
        exposes it; otherwise raises ``UnsupportedOperationError``. Whatever
        Telegram returns is passed through unchanged (possibly empty). Limits are
        never bypassed.
        """
        try:
            from telethon import functions
        except Exception:  # pragma: no cover - telethon always present here
            raise UnsupportedOperationError(
                "Рекомендации Telegram недоступны в этой версии.",
                how_to_fix="Обновите библиотеку telethon.",
            ) from None
        request_cls = getattr(
            getattr(functions, "channels", None), "GetChannelRecommendationsRequest", None
        )
        if request_cls is None:
            raise UnsupportedOperationError(
                "Рекомендации Telegram недоступны в этой версии.",
                how_to_fix="Обновите библиотеку telethon.",
            )

        async def _run(client):  # type: ignore[no-untyped-def]
            entity = await client.get_entity(channel)
            result = await client(request_cls(channel=entity))
            refs: list[EntityRef] = []
            seen: set[int] = set()
            for chat in list(getattr(result, "chats", []) or []):
                if not (getattr(chat, "broadcast", False) or getattr(chat, "megagroup", False)):
                    continue
                cid = int(getattr(chat, "id", 0))
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                refs.append(
                    EntityRef(
                        id=cid,
                        username=str(getattr(chat, "username", "") or ""),
                        title=str(getattr(chat, "title", "") or ""),
                        kind="group" if getattr(chat, "megagroup", False) else "channel",
                        participants_count=getattr(chat, "participants_count", None),
                        subscribers=int(getattr(chat, "participants_count", 0) or 0),
                    )
                )
                if len(refs) >= max(1, limit):
                    break
            return refs

        return await self._call(_run)

    async def get_participants(
        self, entity: str | int, *, limit: int = 0
    ) -> list[UserIdentity]:
        async def _run(client):  # type: ignore[no-untyped-def]
            result: list[UserIdentity] = []
            kwargs = {} if limit <= 0 else {"limit": limit}
            async for user in client.iter_participants(entity, **kwargs):
                result.append(self._identity(user))
            return result

        return await self._call(_run)

    async def iter_participant_pages(
        self,
        entity: str | int,
        *,
        batch_size: int = 100,
        offset: int = 0,
        limit: int = 0,
    ) -> list[ParticipantPage]:
        """Return up to one in-memory page of participants starting at ``offset``.

        The caller (AudienceService) drives the scan one page at a time so the
        full member list is never held in RAM on a weak machine. ``exhausted``
        marks the final page; ``truncated`` is set when Telegram reported more
        participants than it was willing to expose (partial result, never hidden
        from the user — decision D-026).
        """

        async def _run(client):  # type: ignore[no-untyped-def]
            resolved = await client.get_entity(entity)
            total: int | None = getattr(resolved, "participants_count", None)
            taken: list[UserIdentity] = []
            exhausted = True
            batch = max(1, batch_size)
            # Fetch a bounded window so a single call cannot grow without limit.
            fetch_limit = batch
            if limit > 0:
                remaining = limit - offset
                if remaining <= 0:
                    return [
                        ParticipantPage(users=[], total=total, exhausted=True)
                    ]
                fetch_limit = min(batch, remaining)
            seen = 0
            async for user in client.iter_participants(resolved):
                if seen < offset:
                    seen += 1
                    continue
                taken.append(self._identity(user))
                seen += 1
                if len(taken) >= fetch_limit:
                    exhausted = False
                    break
            return [
                ParticipantPage(
                    users=taken,
                    total=total,
                    exhausted=exhausted,
                    truncated=bool(total and len(taken) < total and exhausted),
                )
            ]

        return await self._call(_run)

    async def invite_to_channel(self, entity: str | int, user_id: int) -> None:
        async def _run(client):
            await client.invite_to_channel(entity, user_id)

        await self._call(_run)

    # --- permission probe (post-1.0 hardening) -------------------------------
    async def probe_permissions(self, entity: str | int) -> PermissionReport:
        """Probe real access to ``entity`` with a sequence of bounded API calls.

        Nothing is assumed: each capability flag is set only when Telegram
        confirms it. A failure in one step does not abort the others, so the
        report shows the full picture (e.g. channel found but participants
        hidden). Never returns secrets or session contents.
        """

        async def _run(client):  # type: ignore[no-untyped-def]
            report = PermissionReport(status="error")

            # 1) Account authorized?
            try:
                me = await client.get_me()
            except Exception as exc:
                raise self._translate(exc) from exc
            if me is None:
                report.status = "auth_required"
                report.message = "Аккаунт не авторизован."
                report.how_to_fix = "Авторизуйте аккаунт в разделе «Аккаунты»."
                return report
            report.authorized = True
            report.session_ok = True

            # 2) Resolve the channel.
            try:
                resolved = await client.get_entity(entity)
            except Exception as exc:
                raise self._translate(exc) from exc
            report.channel_found = True
            report.can_read_info = True
            report.channel_id = int(getattr(resolved, "id", 0)) or None
            report.channel_title = str(
                getattr(resolved, "title", "") or getattr(resolved, "first_name", "") or ""
            )
            report.channel_username = str(getattr(resolved, "username", "") or "")
            if getattr(resolved, "megagroup", False):
                report.channel_kind = "group"
            elif getattr(resolved, "broadcast", False):
                report.channel_kind = "channel"
            else:
                report.channel_kind = "user"
            report.participants_count = getattr(resolved, "participants_count", None)

            # 3) Participants (only what Telegram actually exposes).
            hidden = bool(
                getattr(resolved, "participants_hidden", False)
                or getattr(resolved, "join_to_send", False)
            )
            if hidden:
                report.can_read_participants = False
            else:
                try:
                    async for _user in client.iter_participants(resolved, limit=1):
                        report.can_read_participants = True
                        break
                except Exception:
                    report.can_read_participants = False

            # 4) Invite capability: confirm admin rights that allow inviting.
            try:
                perms = await client.get_permissions(resolved, me)
                is_admin = bool(getattr(perms, "is_admin", False))
                invite_users = bool(getattr(perms, "invite_users", False))
                report.can_invite = bool(
                    getattr(resolved, "creator", False) or (is_admin and invite_users)
                )
            except Exception:
                report.can_invite = False

            # 5) Summarize honestly.
            if report.can_invite:
                report.status = "ok"
                report.message = "Канал доступен, приглашения разрешены."
                report.how_to_fix = ""
            elif report.can_read_participants:
                report.status = "partial"
                report.message = (
                    "Канал доступен и список участников виден, но приглашать "
                    "может только администратор."
                )
                report.how_to_fix = "Выдайте аккаунту права администратора с правом приглашать."
            else:
                report.status = "privacy_restricted"
                report.message = (
                    "Канал доступен, но Telegram не предоставляет список участников "
                    "этому аккаунту."
                )
                report.how_to_fix = "Используйте публичный источник или аккаунт с доступом."
            return report

        return await self._call(_run)

    # --- content grabber (v1.2) ----------------------------------------------
    async def fetch_channel_messages(
        self, channel: str | int, *, limit: int = 20, min_id: int = 0
    ) -> ChannelFetchResult:
        """Read recent channel messages, respecting content protection (D-006).

        A channel with ``noforwards`` set is reported as ``protected`` and only
        its link is returned — the grabber never attempts to bypass it.
        """

        async def _run(client):  # type: ignore[no-untyped-def]
            resolved = await client.get_entity(channel)
            username = str(getattr(resolved, "username", "") or "")
            title = str(getattr(resolved, "title", "") or username)
            source_url = f"https://t.me/{username}" if username else ""
            if bool(getattr(resolved, "noforwards", False)):
                return ChannelFetchResult(
                    ok=True,
                    protected=True,
                    source_channel=title or str(channel),
                    source_url=source_url,
                    message="Контент нельзя автоматически получить из этого источника.",
                    how_to_fix=(
                        "Источник запрещает копирование. Сохраните только ссылку "
                        "на источник и опубликуйте материал вручную."
                    ),
                )
            items: list[ChannelMessage] = []
            kwargs: dict[str, object] = {"limit": max(1, limit)}
            if min_id:
                kwargs["min_id"] = int(min_id)
            async for message in client.iter_messages(resolved, **kwargs):
                text = str(getattr(message, "message", "") or "")
                entities: list[dict[str, object]] = []
                for ent in getattr(message, "entities", None) or []:
                    entities.append(self._entity_dict(ent))
                media_urls: list[str] = []
                if getattr(message, "media", None) is not None:
                    # A reference, never a download: the grabber only records it.
                    media_urls.append(source_url or str(channel))
                msg_id = int(getattr(message, "id", 0) or 0)
                items.append(
                    ChannelMessage(
                        message_id=msg_id,
                        text=text,
                        url=f"{source_url}/{msg_id}" if source_url else "",
                        date=str(getattr(message, "date", "") or ""),
                        entities=entities,
                        media_urls=media_urls,
                    )
                )
            return ChannelFetchResult(
                ok=True,
                source_channel=title or str(channel),
                source_url=source_url,
                items=items,
                message=f"Найдено сообщений: {len(items)}.",
            )

        return await self._call(_run)

    @staticmethod
    def _entity_dict(entity: object) -> dict[str, object]:
        """Translate a Telethon message entity into a plain, display-safe dict."""
        name = type(entity).__name__
        mapping = {
            "MessageEntityBold": "bold",
            "MessageEntityItalic": "italic",
            "MessageEntityUnderline": "underline",
            "MessageEntityStrike": "strikethrough",
            "MessageEntityCode": "code",
            "MessageEntityPre": "pre",
            "MessageEntityTextUrl": "text_link",
            "MessageEntityUrl": "url",
            "MessageEntityMention": "mention",
            "MessageEntityMentionName": "text_mention",
            "MessageEntitySpoiler": "spoiler",
            "MessageEntityBlockquote": "blockquote",
        }
        out: dict[str, object] = {
            "type": mapping.get(name, "unknown"),
            "offset": int(getattr(entity, "offset", 0) or 0),
            "length": int(getattr(entity, "length", 0) or 0),
        }
        url = getattr(entity, "url", None)
        if url:
            out["url"] = str(url)
        return out


__all__ = ["TelethonSessionProvider"]
