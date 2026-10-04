"""User Session Manager service (PHASE 4).

Coordinates the user-session repository, the MTProto :class:`SessionProvider`
abstraction, the durable event log, secret sealing and on-disk session files.

Guarantees:
- No Telethon types and no secrets (session contents, api_hash, full phone) ever
  leave this layer except the sealed forms written to the database.
- Provider connections are **lazy**: a client is built for a single operation
  and closed immediately after (D-023) — vital for weak Windows machines.
- Telegram server limits (FloodWait, privacy, authorization) are handled as
  status, never bypassed (D-006).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret, seal_secret
from backend.app.db.base import new_id, utcnow
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.repositories.sessions import SessionRepository
from backend.app.providers.errors import FloodWaitError, SessionInvalidError, TelegramProviderError
from backend.app.providers.registry import build_session_provider
from backend.app.providers.session_base import SessionProvider
from backend.app.providers.types import SessionFileInfo, UserIdentity
from backend.app.services.events_service import EventsService
from backend.app.services.session_import import (
    FORMAT_STRING_SESSION,
    FORMAT_TITLES,
    DetectionResult,
    SessionImportProvider,
    SessionImportRequest,
    SessionImportResult,
    detect_format,
    select_provider,
)

SessionProviderFactory = Callable[..., SessionProvider]

# Wizard steps.
STEP_IDLE = "idle"
STEP_CODE = "code"
STEP_PASSWORD = "password"
STEP_DONE = "done"

MODULE = "sessions.session_service"


class SessionServiceError(Exception):
    """A session operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class AuthStartResult:
    account_id: str | None
    next_step: str
    message: str
    how_to_fix: str = ""
    phone_masked: str = ""


@dataclass(slots=True)
class AuthStepResult:
    account_id: str
    next_step: str
    done: bool
    message: str
    how_to_fix: str = ""
    identity: UserIdentity | None = None


def mask_phone(phone: str) -> str:
    """Return a display-safe phone mask like ``+7999***4567``.

    Never returns the full number; used for storage and API responses.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return ""
    prefix = "+" if (phone or "").strip().startswith("+") else ""
    if len(digits) <= 7:
        return f"{prefix}{digits[:2]}***{digits[-2:]}"
    return f"{prefix}{digits[:4]}***{digits[-4:]}"


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to digits with an optional leading ``+``."""
    phone = (
        (phone or "")
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if not phone:
        return ""
    has_plus = phone.startswith("+")
    digits = "".join(ch for ch in phone if ch.isdigit())
    return ("+" + digits) if has_plus else digits


class SessionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: SessionProviderFactory = build_session_provider,
        sessions_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = SessionRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory
        self._sessions_dir = sessions_dir or self.settings.resolve_sessions_dir()

    # --- session file helpers ------------------------------------------------
    @property
    def sessions_dir(self) -> Path:
        return self._sessions_dir

    def _session_path(self, account: UserSession) -> Path:
        ref = account.session_ref or new_id()
        return self.sessions_dir / f"{ref}.session"

    def _new_session_ref(self) -> str:
        return new_id()

    def session_file_info(self, account: UserSession) -> SessionFileInfo:
        """Return diagnostics about a session file (never its contents)."""
        path = self._session_path(account)
        try:
            exists = path.is_file()
            size = path.stat().st_size if exists else 0
            readable = exists and path.is_file()
        except OSError:
            return SessionFileInfo(exists=False)
        return SessionFileInfo(exists=exists, size_bytes=size, is_readable=readable)

    def delete_session_file(self, account: UserSession) -> None:
        """Delete the on-disk session file (best effort)."""
        path = self._session_path(account)
        for candidate in (path, Path(str(path) + "-journal")):
            with contextlib.suppress(OSError):
                candidate.unlink(missing_ok=True)

    # --- provider helpers ----------------------------------------------------
    def provider_for(
        self,
        account: UserSession,
        provider_name: str | None = None,
        *,
        proxy: dict[str, object] | None = None,
    ) -> SessionProvider:
        """Public wrapper: build a provider for ``account`` (PHASE 5 reuses this).

        ``proxy`` (an optional Telethon proxy dict) is passed through unchanged;
        callers that need the account's bound proxy should use
        :meth:`provider_for_with_proxy`.
        """
        return self._provider_for(account, provider_name, proxy=proxy)

    async def provider_for_with_proxy(
        self,
        account: UserSession,
        provider_name: str | None = None,
    ) -> SessionProvider:
        """Build a provider, resolving the account's bound proxy profile first."""
        proxy = await self.resolve_proxy(account)
        return self._provider_for(account, provider_name, proxy=proxy)

    async def resolve_proxy(
        self, account: UserSession
    ) -> dict[str, object] | None:
        """Return the Telethon proxy dict for the account's bound profile.

        ``None`` means a direct connection (no proxy, or the profile is disabled).
        A proxy is an ordinary network route; the suite never rotates it to evade
        Telegram limits (D-066).
        """
        proxy_id = getattr(account, "proxy_id", "")
        if not proxy_id:
            return None
        from backend.app.db.repositories.proxies import ProxyRepository
        from backend.app.services.proxy_service import ProxyService

        profile = await ProxyRepository(self.session).get(proxy_id)
        if profile is None or not profile.enabled:
            return None
        return ProxyService(self.session, settings=self.settings).telethon_proxy_for(profile)

    def _provider_for(
        self,
        account: UserSession,
        provider_name: str | None = None,
        *,
        proxy: dict[str, object] | None = None,
    ) -> SessionProvider:
        api_hash = ""
        if account.api_hash_encrypted:
            try:
                api_hash = open_secret(account.api_hash_encrypted, self.settings)
            except ValueError as exc:
                raise SessionServiceError(
                    "Не удалось прочитать сохранённый API Hash.",
                    how_to_fix="Проверьте, что APP_SECRET_KEY не менялся. Добавьте аккаунт заново.",
                ) from exc
        kwargs: dict[str, object] = {
            "api_id": account.api_id,
            "api_hash": api_hash,
            "session_path": self._session_path(account),
            "provider_name": provider_name or self.settings.telegram_provider,
            "settings": self.settings,
        }
        # Only pass ``proxy`` when set so custom test factories stay compatible.
        if proxy is not None:
            kwargs["proxy"] = proxy
        return self._provider_factory(**kwargs)  # type: ignore[arg-type]

    # --- inventory -----------------------------------------------------------
    async def list_accounts(
        self, *, status: SessionStatus | None = None, enabled: bool | None = None
    ) -> list[UserSession]:
        accounts, _ = await self.repo.list(status=status, enabled=enabled)
        return accounts

    async def get(self, account_id: str) -> UserSession | None:
        return await self.repo.get(account_id)

    async def summary(self) -> dict[str, object]:
        counts = await self.repo.count_by_status()
        total = await self.repo.count()
        active = sum(
            counts.get(s, 0)
            for s in (SessionStatus.ONLINE.value, SessionStatus.AUTH_REQUIRED.value)
        )
        return {
            "total": total,
            "active": active,
            "online": counts.get(SessionStatus.ONLINE.value, 0),
            "auth_required": counts.get(SessionStatus.AUTH_REQUIRED.value, 0),
            "disabled": counts.get(SessionStatus.DISABLED.value, 0),
            "error": counts.get(SessionStatus.ERROR.value, 0),
            "by_status": counts,
        }

    # --- account risk (v1.1: honest limits UX) -------------------------------
    @staticmethod
    def risk_for(account: UserSession) -> dict[str, str]:
        """Return the account's restriction-risk band (never a safe number).

        The suite never promises a safe invite count: Telegram publishes no
        universal limit and using a user account for mass invites can lead to
        restrictions or a block. This maps the observable state onto a band.
        """
        status = account.status
        if status is SessionStatus.FLOOD_WAIT:
            return {
                "level": "flood_wait",
                "title": "Ожидание Telegram",
                "message": (
                    "Telegram ограничил частоту действий для этого аккаунта. "
                    "Дождитесь окончания паузы — обходить её нельзя."
                ),
            }
        if status is SessionStatus.DISABLED:
            return {
                "level": "disabled",
                "title": "Выключен",
                "message": "Аккаунт выключен и не выполняет действия.",
            }
        if status is SessionStatus.AUTH_REQUIRED:
            return {
                "level": "auth_required",
                "title": "Нужна авторизация",
                "message": "Аккаунт не авторизован; действия невозможны до входа.",
            }
        if status is SessionStatus.ERROR:
            return {
                "level": "restricted",
                "title": "Ограничение или ошибка",
                "message": (
                    "Последняя проверка завершилась ошибкой или ограничением. "
                    "Проверьте статус и повторите позже."
                ),
            }
        if status is SessionStatus.ONLINE:
            return {
                "level": "healthy",
                "title": "Без активных ограничений",
                "message": (
                    "Активных ограничений не видно. Использование аккаунта для "
                    "массовых приглашений всё равно может привести к ограничениям: "
                    "Telegram не публикует универсальный безопасный лимит."
                ),
            }
        return {
            "level": "unknown",
            "title": "Не проверялся",
            "message": "Выполните проверку, чтобы увидеть состояние аккаунта.",
        }

    # --- authorization wizard ------------------------------------------------
    async def start_auth(
        self,
        *,
        api_id: str,
        api_hash: str,
        phone: str,
        display_name: str = "",
    ) -> AuthStartResult:
        """Begin the wizard: request a Telegram login code for ``phone``.

        Creates (or reuses) a local account record and returns the next step.
        """
        api_id = (api_id or "").strip()
        api_hash = (api_hash or "").strip()
        phone_norm = normalize_phone(phone)
        if not api_id.isdigit():
            raise SessionServiceError(
                "API ID должен состоять только из цифр.",
                how_to_fix="Скопируйте API ID из https://my.telegram.org "
                "(раздел API development tools).",
            )
        if not api_hash:
            raise SessionServiceError(
                "Не указан API Hash.",
                how_to_fix="Скопируйте API Hash из https://my.telegram.org.",
            )
        if not phone_norm:
            raise SessionServiceError(
                "Не указан номер телефона.",
                how_to_fix="Укажите номер в международном формате, например +79991234567.",
            )

        # Reuse an in-progress account for this phone (idempotent re-request).
        account = await self._find_by_phone(phone_norm)
        if account is None:
            account = UserSession(
                api_id=api_id,
                phone_encrypted=seal_secret(phone_norm, self.settings),
                phone_masked=mask_phone(phone_norm),
                session_ref=self._new_session_ref(),
                display_name=display_name,
                status=SessionStatus.DISCONNECTED,
                enabled=True,
            )
            await self.repo.add(account)
        else:
            account.api_id = api_id
            account.phone_encrypted = seal_secret(phone_norm, self.settings)
            account.phone_masked = mask_phone(phone_norm)
        account.api_hash_encrypted = seal_secret(api_hash, self.settings)
        account.enabled = True

        provider = self._provider_for(account)
        try:
            result = await provider.send_code(phone_norm)
        except TelegramProviderError as exc:
            await self._apply_error(account, exc)
            await self.session.commit()
            raise SessionServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.aclose()

        account.phone_code_hash = result.phone_code_hash
        account.auth_step = STEP_CODE
        account.status = SessionStatus.AUTH_REQUIRED
        account.status_message = "Код отправлен. Введите его из Telegram."
        account.status_hint = ""
        account.last_error = ""
        account.last_checked_at = utcnow()
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Запрошен код подтверждения для {account.phone_masked}.",
            operation="start_auth",
            status="ok",
        )
        await self.session.commit()
        return AuthStartResult(
            account_id=account.id,
            next_step=STEP_CODE,
            message="Код подтверждения отправлен в Telegram.",
            how_to_fix="Откройте Telegram и введите полученный код.",
            phone_masked=account.phone_masked,
        )

    async def submit_code(self, account_id: str, code: str) -> AuthStepResult:
        """Submit the login code; may advance to the 2FA password step."""
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        code = (code or "").strip()
        if not code:
            raise SessionServiceError(
                "Не указан код подтверждения.",
                how_to_fix="Введите код, который прислал Telegram.",
            )
        phone = self._phone_of(account)
        provider = self._provider_for(account)
        try:
            result = await provider.sign_in(phone, code, account.phone_code_hash)
            if result.ok:
                await provider.export_session()
        except TelegramProviderError as exc:
            await self._apply_error(account, exc)
            await self.session.commit()
            raise SessionServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.aclose()

        if result.needs_password:
            account.auth_step = STEP_PASSWORD
            account.status = SessionStatus.AUTH_REQUIRED
            account.status_message = "Требуется пароль двухэтапной аутентификации."
            account.status_hint = ""
            account.last_error = ""
            account.last_checked_at = utcnow()
            await self.session.flush()
            await self.session.commit()
            return AuthStepResult(
                account_id=account.id,
                next_step=STEP_PASSWORD,
                done=False,
                message="Введите пароль двухэтапной аутентификации.",
                how_to_fix="Это облачный пароль Telegram, заданный в настройках аккаунта.",
            )

        await self._finish_auth(account, result.identity)
        return AuthStepResult(
            account_id=account.id,
            next_step=STEP_DONE,
            done=True,
            message="Аккаунт успешно добавлен.",
            identity=result.identity,
        )

    async def submit_password(self, account_id: str, password: str) -> AuthStepResult:
        """Submit the 2FA password and complete sign-in."""
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        if not password:
            raise SessionServiceError(
                "Не указан пароль двухэтапной аутентификации.",
                how_to_fix="Введите облачный пароль Telegram.",
            )
        provider = self._provider_for(account)
        try:
            result = await provider.sign_in_password(password)
            await provider.export_session()
        except TelegramProviderError as exc:
            await self._apply_error(account, exc)
            await self.session.commit()
            raise SessionServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.aclose()

        await self._finish_auth(account, result.identity)
        return AuthStepResult(
            account_id=account.id,
            next_step=STEP_DONE,
            done=True,
            message="Аккаунт успешно добавлен.",
            identity=result.identity,
        )

    async def import_session(
        self,
        *,
        api_id: str,
        api_hash: str,
        phone: str = "",
        session_file: Path,
        display_name: str = "",
    ) -> UserSession:
        """Import an existing Telethon ``.session`` file and verify it.

        The file is copied into the sessions directory under a UUID name; its
        contents are never read, returned or logged. Identity is fetched via the
        provider and the account is registered in the database.
        """
        api_id = (api_id or "").strip()
        api_hash = (api_hash or "").strip()
        if not api_id.isdigit():
            raise SessionServiceError(
                "API ID должен состоять только из цифр.",
                how_to_fix="Скопируйте API ID из https://my.telegram.org.",
            )
        if not api_hash:
            raise SessionServiceError(
                "Не указан API Hash.",
                how_to_fix="Скопируйте API Hash из https://my.telegram.org.",
            )
        if not session_file.is_file():
            raise SessionServiceError(
                "Файл сессии не найден.",
                how_to_fix="Выберите существующий файл .session, созданный ранее.",
            )

        ref = self._new_session_ref()
        target = self.sessions_dir / f"{ref}.session"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Copy bytes only; never inspect or log the content.
        target.write_bytes(session_file.read_bytes())

        phone_norm = normalize_phone(phone)
        account = UserSession(
            api_id=api_id,
            api_hash_encrypted=seal_secret(api_hash, self.settings),
            phone_encrypted=seal_secret(phone_norm, self.settings) if phone_norm else "",
            phone_masked=mask_phone(phone_norm) if phone_norm else "",
            session_ref=ref,
            display_name=display_name,
            status=SessionStatus.DISCONNECTED,
            enabled=True,
        )
        await self.repo.add(account)

        try:
            identity = await self._verify_and_identify(account)
        except SessionServiceError:
            # Roll back: remove the copied file and the unfinished record.
            self.delete_session_file(account)
            await self.repo.delete(account)
            await self.session.commit()
            raise
        await self._finish_auth(account, identity)
        await self.events.info(
            MODULE,
            f"Импортирован аккаунт @{account.username or account.telegram_user_id}.",
            operation="import_session",
            status="ok",
        )
        await self.session.commit()
        return account

    # --- multi-format import (v1.1 Account Hub) ------------------------------
    async def detect_import(self, request: SessionImportRequest) -> DetectionResult:
        """Detect the artifact format/state without importing (safe preview)."""
        return detect_format(request)

    async def import_artifact(
        self,
        request: SessionImportRequest,
        *,
        providers: list[SessionImportProvider] | None = None,
    ) -> tuple[UserSession, SessionImportResult]:
        """Import a local ``.session`` / ``+JSON`` / StringSession / TDATA artifact.

        The chosen provider is asked to inspect the artifact (no secrets leave the
        process). A StringSession is materialised into a local ``.session`` file
        via the provider abstraction; every other format is copied as bytes. On
        failure nothing is left behind. The raw StringSession value never reaches
        the API, logs or git.
        """
        provider = select_provider(request, providers=providers)
        if provider is None:
            raise SessionServiceError(
                "Не удалось определить формат файла или папки.",
                how_to_fix=(
                    "Поддерживаются: .session, .session + JSON, строка StringSession "
                    "и папка TDATA."
                ),
            )
        result = provider.inspect(request)
        if not result.ok:
            raise SessionServiceError(
                result.message or "Импорт не удался.", how_to_fix=result.how_to_fix
            )

        api_id = (result.api_id or request.api_id or "").strip()
        api_hash = (result.api_hash or request.api_hash or "").strip()
        if not api_id.isdigit():
            raise SessionServiceError(
                "Не указан API ID (и его не удалось прочитать из файла).",
                how_to_fix="Скопируйте API ID из https://my.telegram.org.",
            )
        if not api_hash:
            raise SessionServiceError(
                "Не указан API Hash (и его не удалось прочитать из файла).",
                how_to_fix="Скопируйте API Hash из https://my.telegram.org.",
            )

        ref = self._new_session_ref()
        target = self.sessions_dir / f"{ref}.session"
        target.parent.mkdir(parents=True, exist_ok=True)

        if result.format == FORMAT_STRING_SESSION:
            # Materialise the StringSession into a local SQLite session file.
            provider_impl = self._provider_factory(
                api_id=api_id,
                api_hash=api_hash,
                session_path=target,
                provider_name=self.settings.telegram_provider,
                settings=self.settings,
            )
            try:
                await provider_impl.import_string_session(result.string_session, target)
            except TelegramProviderError as exc:
                raise SessionServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
            finally:
                await provider_impl.aclose()
        else:
            target.write_bytes(result.session_bytes)

        phone_norm = normalize_phone(result.phone or request.phone or "")
        account = UserSession(
            api_id=api_id,
            api_hash_encrypted=seal_secret(api_hash, self.settings),
            phone_encrypted=seal_secret(phone_norm, self.settings) if phone_norm else "",
            phone_masked=mask_phone(phone_norm) if phone_norm else "",
            session_ref=ref,
            display_name=result.display_name or request.display_name,
            status=SessionStatus.DISCONNECTED,
            enabled=True,
        )
        await self.repo.add(account)
        try:
            identity = await self._verify_and_identify(account)
        except SessionServiceError:
            self.delete_session_file(account)
            await self.repo.delete(account)
            await self.session.commit()
            raise
        await self._finish_auth(account, identity)
        await self.events.info(
            MODULE,
            f"Импортирован аккаунт @{account.username or account.telegram_user_id} "
            f"({FORMAT_TITLES.get(result.format, result.format)}).",
            operation="import_artifact",
            status="ok",
        )
        await self.session.commit()
        return account, result

    # --- health / lifecycle --------------------------------------------------
    async def health_check(self, account_id: str) -> UserSession:
        """Verify a session is still authorized and update its status."""
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        if not account.enabled:
            account.status = SessionStatus.DISABLED
            account.status_message = "Аккаунт выключен."
            account.last_checked_at = utcnow()
            await self.session.commit()
            return account

        info = self.session_file_info(account)
        if not info.exists:
            account.status = SessionStatus.DISCONNECTED
            account.status_message = "Файл сессии не найден."
            account.status_hint = "Добавьте аккаунт заново или импортируйте session-файл."
            account.last_error = ""
            account.last_checked_at = utcnow()
            await self.session.flush()
            await self.session.commit()
            return account

        provider = self._provider_for(account)
        try:
            identity = await provider.health()
        except TelegramProviderError as exc:
            await self._apply_error(account, exc)
            await self.session.commit()
            return account
        finally:
            await provider.aclose()

        self._apply_identity(account, identity)
        account.status = SessionStatus.ONLINE
        account.status_message = "Аккаунт авторизован и доступен."
        account.status_hint = ""
        account.last_error = ""
        account.auth_step = STEP_DONE
        account.last_checked_at = utcnow()
        await self.session.flush()
        await self.session.commit()
        return account

    async def set_enabled(self, account_id: str, enabled: bool) -> UserSession:
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        account.enabled = enabled
        if enabled:
            if account.status == SessionStatus.DISABLED:
                account.status = SessionStatus.DISCONNECTED
                account.status_message = "Аккаунт включён. Выполните проверку."
                account.status_hint = ""
        else:
            account.status = SessionStatus.DISABLED
            account.status_message = "Аккаунт выключен."
            account.status_hint = ""
        await self.session.flush()
        await self.session.commit()
        return account

    async def delete_account(self, account_id: str) -> None:
        """Delete an account record and its on-disk session file."""
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        label = account.username or account.phone_masked or account.id
        self.delete_session_file(account)
        await self.repo.delete(account)
        await self.events.warning(
            MODULE,
            f"Аккаунт {label} удалён.",
            operation="delete_account",
            status="ok",
        )
        await self.session.commit()

    async def logout(self, account_id: str) -> UserSession:
        """Re-authorize: clear local session state so the wizard can restart.

        This does not call Telegram's ``logOut`` (which would revoke the session
        everywhere); it only resets the local account to require a fresh sign-in.
        """
        account = await self.repo.get(account_id)
        if account is None:
            raise SessionServiceError("Аккаунт не найден.", status_code=404)
        self.delete_session_file(account)
        account.session_ref = self._new_session_ref()
        account.phone_code_hash = ""
        account.auth_step = STEP_IDLE
        account.status = SessionStatus.AUTH_REQUIRED
        account.status_message = "Требуется повторная авторизация."
        account.status_hint = "Запустите мастер добавления аккаунта заново."
        account.last_error = ""
        await self.session.flush()
        await self.session.commit()
        return account

    async def recover(self) -> int:
        """Reset accounts stuck mid-wizard after a restart.

        Accounts left in the ``code``/``password`` step are reset to
        ``auth_required`` so the operator can retry through the UI (D-024).
        """
        accounts = await self.list_accounts()
        reset = 0
        for account in accounts:
            if account.auth_step in (STEP_CODE, STEP_PASSWORD):
                account.auth_step = STEP_IDLE
                account.phone_code_hash = ""
                if account.status != SessionStatus.ONLINE:
                    account.status = SessionStatus.AUTH_REQUIRED
                    account.status_message = "Авторизация не завершена. Запустите мастер заново."
                reset += 1
        if reset:
            await self.session.flush()
            await self.session.commit()
        return reset

    # --- internal helpers ----------------------------------------------------
    async def _find_by_phone(self, phone_norm: str) -> UserSession | None:
        accounts = await self.list_accounts()
        for account in accounts:
            existing = ""
            if account.phone_encrypted:
                try:
                    existing = open_secret(account.phone_encrypted, self.settings)
                except ValueError:
                    existing = ""
            if existing and existing == phone_norm:
                return account
        return None

    def _phone_of(self, account: UserSession) -> str:
        if not account.phone_encrypted:
            return ""
        try:
            return open_secret(account.phone_encrypted, self.settings)
        except ValueError as exc:
            raise SessionServiceError(
                "Не удалось прочитать сохранённый номер телефона.",
                how_to_fix="Добавьте аккаунт заново.",
            ) from exc

    async def _verify_and_identify(self, account: UserSession) -> UserIdentity:
        provider = self._provider_for(account)
        try:
            return await provider.health()
        except TelegramProviderError as exc:
            await self._apply_error(account, exc)
            await self.session.commit()
            raise SessionServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.aclose()

    def _apply_identity(self, account: UserSession, identity: UserIdentity) -> None:
        if identity.id:
            account.telegram_user_id = identity.id
        if identity.username:
            account.username = identity.username
        account.display_name = identity.display_name or account.display_name
        if identity.phone and not account.phone_masked:
            account.phone_masked = mask_phone(identity.phone)

    async def _finish_auth(
        self, account: UserSession, identity: UserIdentity | None
    ) -> None:
        if identity is not None:
            self._apply_identity(account, identity)
        account.auth_step = STEP_DONE
        account.phone_code_hash = ""
        account.status = SessionStatus.ONLINE
        account.status_message = "Аккаунт авторизован и готов к работе."
        account.status_hint = ""
        account.last_error = ""
        account.last_checked_at = utcnow()
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Аккаунт @{account.username or account.telegram_user_id} готов к работе.",
            operation="authorize",
            status="ok",
            actor=f"@{account.username}" if account.username else account.phone_masked,
        )
        await self.session.commit()

    async def _apply_error(self, account: UserSession, exc: TelegramProviderError) -> None:
        """Map a provider error onto the account status (never bypassing limits)."""
        if isinstance(exc, FloodWaitError):
            account.status = SessionStatus.FLOOD_WAIT
            wait = f" Осталось ждать ~{exc.retry_after} сек." if exc.retry_after else ""
            account.status_message = f"Telegram просит подождать.{wait}"
        elif isinstance(exc, SessionInvalidError):
            account.status = SessionStatus.AUTH_REQUIRED
            account.status_message = "Требуется авторизация."
        else:
            account.status = SessionStatus.ERROR
            account.status_message = exc.message
        account.status_hint = exc.how_to_fix
        account.last_error = exc.technical or exc.message
        account.last_checked_at = utcnow()
        await self.session.flush()
        await self.events.error(
            MODULE,
            f"Ошибка аккаунта {account.phone_masked or account.id}.",
            explanation=exc.message,
            how_to_fix=exc.how_to_fix,
            operation="account_error",
            status="error",
        )


__all__ = [
    "AuthStartResult",
    "AuthStepResult",
    "SessionProviderFactory",
    "SessionService",
    "SessionServiceError",
    "mask_phone",
    "normalize_phone",
]
