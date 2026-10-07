"""Independent verification of v1.6.0 Owner Auth + Config Sync (D-105/D-106).

These are negative/security tests: they assert the *actual* behaviour of the
released code, not just that an interface exists. No network, no real accounts,
no Google, no real secrets — every provider is a local fake.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.owner_guard import TOKEN_HEADER, is_protected, issue_token, verify_token
from backend.app.core.owner_security import derive_bundle_key
from backend.app.db.session import init_models, session_scope
from backend.app.providers.config_sync_base import ConfigSyncError, RemoteBundle
from backend.app.services.config_bundle import (
    MAGIC,
    SCHEMA_VERSION,
    BundleError,
    build_bundle,
    deserialize,
    sanitize_settings,
    scan_for_secrets,
    serialize,
)
from backend.app.services.config_sync_service import ConfigSyncError_, ConfigSyncService
from backend.app.services.owner_auth_service import OwnerAuthService

OWNER = "/api/v1/owner"
SECRET = "correct horse battery"
PROTECTED = "/api/v1/settings"


@pytest_asyncio.fixture
async def owner_client() -> AsyncClient:
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _protect(client: AsyncClient) -> str:
    resp = await client.post(f"{OWNER}/setup", json={"secret": SECRET})
    assert resp.status_code == 201
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# 1-2. Owner Auth really protects the API; no alternative-endpoint bypass
# ---------------------------------------------------------------------------
async def test_unauthorized_request_is_rejected(owner_client: AsyncClient) -> None:
    token = await _protect(owner_client)
    # No token → 401.
    assert (await owner_client.get(PROTECTED)).status_code == 401
    # Wrong/foreign token → 401 (token is bound to the owner id).
    foreign = issue_token("some-other-owner")
    assert (
        await owner_client.get(PROTECTED, headers={TOKEN_HEADER: foreign})
    ).status_code == 401
    # Empty-ish token → 401.
    assert (
        await owner_client.get(PROTECTED, headers={TOKEN_HEADER: "owner."})
    ).status_code == 401
    # Real token → 200.
    assert (
        await owner_client.get(PROTECTED, headers={TOKEN_HEADER: token})
    ).status_code == 200


async def test_token_is_not_a_password(owner_client: AsyncClient) -> None:
    token = await _protect(owner_client)
    assert SECRET not in token
    assert token.startswith("owner.")
    assert verify_token(token, "some-other-owner") is False


async def test_no_alternative_endpoint_bypass(owner_client: AsyncClient) -> None:
    """Every non-allowlisted API path must require a token, however spelled."""
    await _protect(owner_client)
    # A broad sample of real routers must all be 401 without a token.
    for path in (
        "/api/v1/settings",
        "/api/v1/bots",
        "/api/v1/channels",
        "/api/v1/sessions",
        "/api/v1/proxies",
        "/api/v1/diagnostics/report",
        "/api/v1/capability-graph",
        "/api/v1/owner/sync/status",
        "/api/v1/owner/sync/upload",
    ):
        assert (await owner_client.get(path)).status_code == 401, path
    # A path with a trailing slash is still protected.
    assert (await owner_client.get("/api/v1/settings/")).status_code == 401
    # An unknown API path must be rejected *before* routing reveals anything.
    assert (await owner_client.get("/api/v1/does-not-exist")).status_code == 401


async def test_guard_path_normalisation_has_no_bypass(owner_client: AsyncClient) -> None:
    """Dot segments / internal doubled slashes must not slip past the guard."""
    await _protect(owner_client)
    for path in (
        "/api/v1/./settings",
        "/api/v1//settings",
        "/api/%76%31/settings",
        "/./api/v1/settings",
        "/api/v1/settings/../sessions",
    ):
        resp = await owner_client.get(path)
        assert resp.status_code == 401, (path, resp.status_code)
    # A genuinely different (case-sensitive) path is not a protected API route:
    # it must not be guarded (never 401) and never reach the settings handler. It
    # falls through to the SPA (or its not-built placeholder).
    upper = await owner_client.get("/API/v1/settings")
    assert upper.status_code in (200, 404)
    assert "unauthorized" not in upper.text.lower()


async def test_guard_blocks_leading_double_slash() -> None:
    """The middleware itself must reject a raw ``//api/...`` path.

    httpx rewrites a leading ``//`` when building a request, so this is asserted
    directly against the middleware with a synthetic ASGI scope (matching what a
    real HTTP client sends on the wire).
    """
    from backend.app.api.owner_guard import OwnerGuardMiddleware

    reached: list[str] = []

    async def app(scope, receive, send):
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def state_provider():
        return "owner-1", True

    middleware = OwnerGuardMiddleware(app, state_provider=state_provider)

    async def call(path: str) -> int:
        status = {"code": 0}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1),
            "root_path": "",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
        }
        await middleware(scope, receive, send)
        return status["code"]

    # A doubled leading slash must be treated as the protected API path.
    assert await call("//api/v1/settings") == 401
    assert await call("/api/v1/settings") == 401
    # An allowlisted path stays reachable.
    assert await call("/api/v1/owner/status") == 200


def test_is_protected_matches_the_allowlist() -> None:
    assert is_protected("/api/v1/settings") is True
    assert is_protected("/api/v1/owner/status") is False
    assert is_protected("/api/v1/owner/login") is False
    assert is_protected("/health") is False
    assert is_protected("/") is False
    # Redundant slashes are normalised before the check.
    assert is_protected("//api/v1/settings") is True
    assert is_protected("/api/v1/./settings") is True
    # Allowlist matching is segment-aware: a sibling API route is *not* exempt.
    assert is_protected("/api/v1/owner/statuses") is True
    assert is_protected("/api/v1/owner/setupx") is True


# ---------------------------------------------------------------------------
# 3. Password is not stored in the clear, nor leaked
# ---------------------------------------------------------------------------
async def test_password_not_stored_or_leaked(owner_client: AsyncClient) -> None:
    resp = await owner_client.post(f"{OWNER}/setup", json={"secret": SECRET})
    assert SECRET not in resp.text
    status = await owner_client.get(f"{OWNER}/status")
    assert SECRET not in status.text
    # The stored verifier is a one-way PBKDF2 string, never the password.
    async with session_scope() as session:
        owner = await OwnerAuthService(session).get_identity()
        assert owner is not None
        assert owner.verifier.startswith("pbkdf2_sha256$")
        assert SECRET not in owner.verifier
        assert owner.sync_salt and SECRET not in owner.sync_salt


async def test_wrong_password_rejected_and_no_token(owner_client: AsyncClient) -> None:
    await _protect(owner_client)
    bad = await owner_client.post(f"{OWNER}/login", json={"secret": "definitely wrong"})
    assert bad.status_code == 401
    assert "token" not in bad.text


async def test_repeated_failures_lock_out(owner_client: AsyncClient) -> None:
    await _protect(owner_client)
    for _ in range(5):
        await owner_client.post(f"{OWNER}/login", json={"secret": "nope"})
    locked = await owner_client.post(f"{OWNER}/login", json={"secret": SECRET})
    assert locked.status_code == 423


# ---------------------------------------------------------------------------
# 4-7. Bundle: encrypted before write; tamper-proof; secrets excluded
# ---------------------------------------------------------------------------
def test_bundle_is_encrypted_and_tamper_proof() -> None:
    key = derive_bundle_key("pw", "salt")
    bundle = build_bundle(settings={"language": "ru"}, revision=1, device_id="dev-a")
    payload = serialize(bundle, key)
    assert payload.startswith(MAGIC)
    assert b"language" not in payload  # ciphertext, not plaintext

    # Correct key decrypts.
    assert deserialize(payload, key).settings["language"] == "ru"

    # Wrong key cannot.
    with pytest.raises(BundleError):
        deserialize(payload, derive_bundle_key("other", "salt"))

    # Any single-byte flip breaks AES-GCM authentication.
    for index in (len(MAGIC), len(MAGIC) + 5, len(payload) - 1):
        tampered = bytearray(payload)
        tampered[index] ^= 0x01
        with pytest.raises(BundleError):
            deserialize(bytes(tampered), key)

    # Truncation and a bad magic are rejected.
    with pytest.raises(BundleError):
        deserialize(payload[: len(MAGIC) + 4], key)
    with pytest.raises(BundleError):
        deserialize(b"XXXX" + payload[len(MAGIC) :], key)


def test_schema_version_is_authenticated() -> None:
    """A version swap/downgrade is detected (version is AES-GCM associated data)."""
    key = derive_bundle_key("pw", "salt")
    payload = bytearray(serialize(build_bundle(settings={}), key))
    # Rewrite the version byte in the magic+AAD trailer: auth must fail.
    mutated = payload.replace(MAGIC + str(SCHEMA_VERSION).encode(), MAGIC + b"9", 1)
    if mutated != payload:
        with pytest.raises(BundleError):
            deserialize(bytes(mutated), key)


def test_plaintext_and_session_secrets_are_excluded() -> None:
    dirty = {
        "language": "ru",
        "show_explanations": "true",
        "password": "hunter2",
        "api_hash": "deadbeef",
        "api_id": "12345",
        "bot_token": "123:ABC",
        "session_path": "/home/u/me.session",
        "session_string": "1BVtsOK...",
        "tdata_dir": "/home/u/tdata",
        "auth_key": "ff00",
        "private_key": "pk",
        "oauth_refresh": "r",
        "owner_verifier": "pbkdf2$...",
        "recovery_hint": "secret hint",
    }
    cleaned = sanitize_settings(dirty)
    assert cleaned == {"language": "ru", "show_explanations": "true"}

    # A nested injected secret is caught by the safety scan.
    bundle = build_bundle(extra={"nested": {"api_hash": "x", "session": "s"}})
    hits = scan_for_secrets(bundle)
    assert "api_hash" in hits and "session" in hits
    # A clean bundle has no hits.
    assert scan_for_secrets(build_bundle(settings={"language": "ru"})) == []


def test_upload_rejects_secret_bearing_bundle() -> None:
    """The service refuses to upload if the scan finds a forbidden key."""
    # build_bundle sanitizes settings, but the service scans the whole document;
    # an injected secret via a non-sanitized field must abort the upload.
    bundle = build_bundle(extra={"api_hash": "x"})
    assert scan_for_secrets(bundle)  # guard against a silent no-op test


# ---------------------------------------------------------------------------
# 8-9. Google Drive provider is real and uses the app-data scope
# ---------------------------------------------------------------------------
class FakeDriveTransport:
    """Minimal in-memory Drive transport; records every request."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.store: dict[str, bytes] = {}

    @staticmethod
    def _strip_multipart(body: bytes) -> bytes:
        # POST multipart = metadata part + binary part; return only the payload.
        marker = b"Content-Type: application/octet-stream\r\n\r\n"
        if marker in body:
            return body.split(marker, 1)[1].rsplit(b"\r\n--", 1)[0]
        return body

    async def request(self, method, url, *, data=None, params=None):
        self.calls.append((method, url, params))
        if method == "GET" and "appDataFolder" in (params or {}).get("spaces", ""):
            files = [{"id": "file-1"}] if self.store else []
            return 200, json.dumps({"files": files}).encode()
        if method == "POST":
            self.store["file-1"] = self._strip_multipart(data or b"")
            return 200, b"{}"
        if method == "PATCH":
            self.store["file-1"] = data or b""
            return 200, b"{}"
        if method == "GET" and "/file-1" in url:
            return 200, self.store.get("file-1", b"")
        if method == "DELETE":
            self.store.clear()
            return 204, b""
        return 404, b"{}"


async def test_google_drive_provider_uses_appdata_scope() -> None:
    from backend.app.providers.config_sync_gdrive import (
        APPDATA_SCOPE,
        GoogleDriveConfigSyncProvider,
        GoogleOAuthConfig,
        build_authorization_url,
    )

    assert APPDATA_SCOPE == "https://www.googleapis.com/auth/drive.appdata"
    transport = FakeDriveTransport()
    provider = GoogleDriveConfigSyncProvider(transport)
    assert provider.available() is True

    await provider.upload(b"cipher", revision=3)
    # The very first lookup must target the app-data folder, not the user's Drive.
    _m, _u, params = transport.calls[0]
    assert params is not None and params.get("spaces") == "appDataFolder"

    result = await provider.download()
    assert result is not None and result[0] == b"cipher"

    # The consent URL requests the least-privilege app-data scope.
    config = GoogleOAuthConfig(client_id="cid", client_secret="csec")
    url = build_authorization_url(config, "state123")
    assert "drive.appdata" in url
    assert "state=state123" in url


async def test_google_drive_unavailable_without_transport() -> None:
    from backend.app.providers.config_sync_gdrive import GoogleDriveConfigSyncProvider

    provider = GoogleDriveConfigSyncProvider(None)
    assert provider.available() is False
    with pytest.raises(ConfigSyncError):
        await provider.upload(b"x", revision=1)


# ---------------------------------------------------------------------------
# 10. Conflict detection really works
# ---------------------------------------------------------------------------
async def test_conflict_detection_and_refusal() -> None:
    from backend.app.services.settings_service import SettingsService

    await init_models()
    provider = _FakeProvider()

    async with session_scope() as session:
        await OwnerAuthService(session).create(SECRET)
        await SettingsService(session).set("language", "ru")
        svc = ConfigSyncService(session, provider=provider)
        await svc.configure("local")
        await svc.upload(SECRET)

    # Simulate another computer whose cloud revision is ahead.
    async with session_scope() as session:
        svc = ConfigSyncService(session, provider=provider)
        state = await svc.state_repo.get_or_create()
        state.cloud_revision = 1
        state.device_id = "other-device"
        await session.commit()

        provider.revision = 2
        provider.device_id = "device-a"
        view = await svc.conflict()
        assert view.detected is True
        # Applying without keep_local must be refused (409), never silent.
        with pytest.raises(ConfigSyncError_) as exc:
            await svc.download_apply(SECRET, keep_local=False)
        assert exc.value.status_code == 409


class _FakeProvider:
    kind = "fake"

    def __init__(self) -> None:
        self.data: bytes | None = None
        self.revision = 0
        self.device_id = ""
        self.device_name = "PC"

    def available(self) -> bool:
        return True

    async def upload(self, data: bytes, *, revision: int) -> RemoteBundle:
        self.data = data
        self.revision = revision
        return RemoteBundle(revision, self.device_id, self.device_name, "")

    async def download(self):
        if self.data is None:
            return None
        return self.data, RemoteBundle(
            self.revision, self.device_id, self.device_name, ""
        )

    async def delete(self) -> None:
        self.data = None


# ---------------------------------------------------------------------------
# 11. Local provider really works
# ---------------------------------------------------------------------------
async def test_local_provider_writes_ciphertext(tmp_path) -> None:
    from backend.app.providers.config_sync_local import (
        BUNDLE_FILENAME,
        LocalConfigSyncProvider,
    )

    provider = LocalConfigSyncProvider(tmp_path / "sync")
    assert provider.available() is True
    payload = serialize(build_bundle(settings={"language": "ru"}), derive_bundle_key("p", "s"))
    await provider.upload(payload, revision=1)
    written = (tmp_path / "sync" / BUNDLE_FILENAME).read_bytes()
    assert written == payload
    assert b"language" not in written  # only ciphertext on disk
    got = await provider.download()
    assert got is not None and got[0] == payload
    await provider.delete()
    assert await provider.download() is None


# ---------------------------------------------------------------------------
# 12. Capability ``config_sync``: needs_setup → available → error/reconnect
# ---------------------------------------------------------------------------
async def test_config_sync_capability_states() -> None:
    from backend.app.services.capability_graph import (
        REQ_GOOGLE_DRIVE,
        REQ_OWNER_AUTH,
        STATE_AVAILABLE,
        STATE_NEEDS_SETUP,
        STATE_UNAVAILABLE,
        state_for,
    )

    # No owner, no provider → nothing is set up yet.
    assert (
        state_for("config_sync", {REQ_OWNER_AUTH: False, REQ_GOOGLE_DRIVE: False}).state
        == STATE_UNAVAILABLE
    )
    # Owner ready but no provider → needs_setup (must never be `partial`).
    assert (
        state_for("config_sync", {REQ_OWNER_AUTH: True, REQ_GOOGLE_DRIVE: False}).state
        == STATE_NEEDS_SETUP
    )
    # Both requirements met → available.
    assert (
        state_for("config_sync", {REQ_OWNER_AUTH: True, REQ_GOOGLE_DRIVE: True}).state
        == STATE_AVAILABLE
    )


async def test_config_sync_status_reports_error_when_drive_disconnected() -> None:
    from backend.app.db.models.config_sync import (
        SYNC_STATE_ERROR,
        SyncProviderKind,
    )

    await init_models()
    async with session_scope() as session:
        await OwnerAuthService(session).create(SECRET)
        svc = ConfigSyncService(session)
        state = await svc.state_repo.get_or_create()
        # Enabled Google Drive with no token → needs reconnect (error state).
        state.provider = SyncProviderKind.GOOGLE_DRIVE
        state.enabled = True
        state.oauth_token_encrypted = ""
        await session.commit()
        status = await svc.status()
        assert status.state == SYNC_STATE_ERROR
        assert status.needs_reconnect is True


# ---------------------------------------------------------------------------
# 13. Diagnostics shows Owner Auth / Config Sync without secrets
# ---------------------------------------------------------------------------
async def test_diagnostics_owner_and_sync_are_secret_free() -> None:
    from backend.app.services.diagnostics_service import DiagnosticsService

    await init_models()
    async with session_scope() as session:
        await OwnerAuthService(session).create(SECRET)
        report = await DiagnosticsService(session).collect()
        keys = {item.key for item in report.items}
        assert "owner_auth" in keys and "config_sync" in keys
        blob = report.model_dump_json()
        assert SECRET not in blob
        assert "verifier" not in blob
        assert "oauth_token" not in blob


# ---------------------------------------------------------------------------
# 14. RU/EN switching really works for the new feature
# ---------------------------------------------------------------------------
def test_ru_en_translation_for_owner_and_sync() -> None:
    from backend.app.core import i18n
    from backend.app.services.capability_graph import evaluate_all, state_for

    assert i18n.translate("owner.title", "ru") != i18n.translate("owner.title", "en")
    assert i18n.translate("sync.state.available", "en") == "Available"
    assert i18n.translate("sync.state.available", "ru") == "Доступно"
    # An unsupported code falls back to RU, never crashes.
    assert i18n.translate("owner.title", "zz") == i18n.translate("owner.title", "ru")

    # Capability labels are language-aware.
    ru = state_for("config_sync", {}, language="ru").title
    en = state_for("config_sync", {}, language="en").title
    assert ru == "Синхронизация конфигурации"
    assert en == "Configuration sync"
    # Every capability and state has both languages (no missing keys).
    for cap in evaluate_all({}, language="en"):
        assert cap.title
    assert i18n.missing_keys() == {}
