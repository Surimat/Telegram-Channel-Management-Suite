"""Lightweight encoder model installer (v1.1: AI Level 1.5 install experience).

The owner should never have to understand Hugging Face, PyTorch or ONNX. This
service turns "install the light model" into one honest action:

* **status** — is the runtime present? is the model downloaded? is it ready?
* **install** — download the official, MIT-licensed ``cointegrated/rubert-tiny2``
  files, verify every file's SHA-256, and store them under ``models/`` (which is
  git-ignored and never shipped in the portable ZIP);
* **check** — try a real load and report the truth;
* **remove** — delete the downloaded model directory (the app keeps working with
  the dependency-free hashing encoder).

Only the official model repository is used; nothing else is downloaded and no
large model is fetched by default. The transport is injectable, so the whole flow
is unit-testable without network access.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.backends.rubert import NAME as ENCODER_NAME
from backend.app.ai.backends.rubert import RuBertEncoderBackend
from backend.app.ai.errors import AiError
from backend.app.core.config import Settings, get_settings
from backend.app.services.backup_backends.http import Transport, urllib_transport
from backend.app.services.events_service import EventsService

MODULE = "encoder"

#: The official model repository (MIT). Only this repo is ever fetched.
MODEL_REPO = "cointegrated/rubert-tiny2"
MODEL_LICENSE = "MIT"
MODEL_URL_BASE = f"https://huggingface.co/{MODEL_REPO}/resolve/main"

#: Per-file safety cap (the largest file is ~118 MB; refuse anything huge).
MAX_FILE_BYTES = 400 * 1024 * 1024

#: Official files with their published size and SHA-256. Weights are content
#: addressed on Hugging Face, so the LFS digest is the exact file hash. The
#: smaller JSON/text files are hashed by us from the official repo.
@dataclass(frozen=True, slots=True)
class ModelAsset:
    name: str
    size: int
    sha256: str


OFFICIAL_ASSETS: tuple[ModelAsset, ...] = (
    ModelAsset(
        "config.json",
        693,
        "adee8b3e344bcb8379f44d0b3577c267d52881341e05d973c43e49974778dfff",
    ),
    ModelAsset(
        "tokenizer_config.json",
        401,
        "74aab51b71a8d116c035464df96c600770f9844696b8965e397b2b1649010686",
    ),
    ModelAsset(
        "special_tokens_map.json",
        112,
        "303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3",
    ),
    ModelAsset(
        "vocab.txt",
        1080667,
        "f056a69b097422652053bf87565c35543e5d81540ca4b7dddd28de4157a969e0",
    ),
    ModelAsset(
        "tokenizer.json",
        1741842,
        "45cc9f974145661db6bc020795839d1dc371adc19a9c78b910393209b4fe5efc",
    ),
    ModelAsset(
        "model.safetensors",
        117529600,
        "26ebb6db2a68593c54c74902d7a74f332da66297693f965cc9f1b0af4abf3894",
    ),
)


@dataclass(slots=True)
class EncoderStatus:
    runtime_available: bool
    installed: bool
    ready: bool
    model_dir: str
    size_bytes: int
    size_human: str
    missing: list[str] = field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""


@dataclass(slots=True)
class EncoderInstallResult:
    ok: bool
    status: EncoderStatus
    message: str
    how_to_fix: str = ""
    downloaded: int = 0


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


class EncoderService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        transport: Transport = urllib_transport,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.events = EventsService(session)
        self._transport = transport

    # --- paths ---------------------------------------------------------------
    @property
    def model_dir(self) -> Path:
        return self.settings.resolve_models_dir() / ENCODER_NAME

    def _backend(self) -> RuBertEncoderBackend:
        return RuBertEncoderBackend(str(self.model_dir))

    # --- status --------------------------------------------------------------
    def _missing_files(self) -> list[str]:
        return [
            asset.name
            for asset in OFFICIAL_ASSETS
            if not (self.model_dir / asset.name).is_file()
        ]

    def _dir_size(self) -> int:
        if not self.model_dir.is_dir():
            return 0
        return sum(p.stat().st_size for p in self.model_dir.rglob("*") if p.is_file())

    async def status(self) -> EncoderStatus:
        backend = self._backend()
        runtime = backend.runtime_available
        missing = self._missing_files()
        installed = self.model_dir.is_dir() and not missing
        size = self._dir_size()
        ready = runtime and installed
        if ready:
            message = "Лёгкая модель установлена и готова."
            fix = ""
        elif not runtime:
            message = "Не установлена библиотека для лёгкой модели."
            fix = "Нажмите «Установить лёгкую модель» — это небольшая загрузка."
        elif missing:
            message = "Модель скачана не полностью."
            fix = "Нажмите «Установить лёгкую модель», чтобы докачать файлы."
        else:
            message = "Лёгкая модель не установлена."
            fix = (
                "Нажмите «Установить лёгкую модель». Без неё работает "
                "лёгкий встроенный распознаватель."
            )
        return EncoderStatus(
            runtime_available=runtime,
            installed=installed,
            ready=ready,
            model_dir=str(self.model_dir),
            size_bytes=size,
            size_human=human_size(size),
            missing=missing,
            message=message,
            how_to_fix=fix,
        )

    # --- install -------------------------------------------------------------
    async def install(self) -> EncoderInstallResult:
        """Download + verify the official files, then try a real load."""
        self.model_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        for asset in OFFICIAL_ASSETS:
            target = self.model_dir / asset.name
            if target.is_file() and self._verify(target, asset):
                continue
            try:
                body = self._download(asset)
            except AiError as exc:
                return EncoderInstallResult(
                    ok=False,
                    status=await self.status(),
                    message=exc.message,
                    how_to_fix=exc.how_to_fix,
                    downloaded=downloaded,
                )
            digest = hashlib.sha256(body).hexdigest()
            if digest != asset.sha256:
                return EncoderInstallResult(
                    ok=False,
                    status=await self.status(),
                    message=f"Файл {asset.name} не прошёл проверку целостности.",
                    how_to_fix="Повторите установку: возможно, загрузка прервалась.",
                    downloaded=downloaded,
                )
            part = target.with_suffix(target.suffix + ".part")
            part.write_bytes(body)
            part.replace(target)
            downloaded += 1

        status = await self.status()
        if not status.installed:
            return EncoderInstallResult(
                ok=False,
                status=status,
                message="Не все файлы модели на месте.",
                how_to_fix=status.how_to_fix,
                downloaded=downloaded,
            )
        # A real load is the only honest proof that the model is usable.
        try:
            self._backend().load()
            self._backend().unload()
        except AiError as exc:
            return EncoderInstallResult(
                ok=False,
                status=status,
                message="Файлы скачаны, но модель не запускается.",
                how_to_fix=exc.how_to_fix or "Попробуйте установить ещё раз.",
                downloaded=downloaded,
            )
        await self.events.info(
            MODULE,
            "Лёгкая модель установлена.",
            explanation=(
                "Она используется как дополнительный распознаватель, "
                "когда правил не хватает."
            ),
            operation="install",
            status="ok",
        )
        await self.session.commit()
        return EncoderInstallResult(
            ok=True,
            status=await self.status(),
            message="Лёгкая модель установлена и проверена.",
            downloaded=downloaded,
        )

    def _download(self, asset: ModelAsset) -> bytes:
        response = self._transport(
            "GET",
            f"{MODEL_URL_BASE}/{asset.name}",
            {"User-Agent": "tcms-ai-encoder", "Accept": "application/octet-stream"},
            None,
        )
        if response.status != 200:
            raise AiError(
                f"Не удалось скачать {asset.name}.",
                how_to_fix="Проверьте подключение к интернету и повторите.",
            )
        if len(response.body) > MAX_FILE_BYTES:
            raise AiError(
                f"Файл {asset.name} слишком большой.",
                how_to_fix="Установка отменена ради безопасности.",
            )
        return response.body

    @staticmethod
    def _verify(path: Path, asset: ModelAsset) -> bool:
        try:
            if path.stat().st_size != asset.size:
                return False
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return False
        return digest == asset.sha256

    # --- check / remove ------------------------------------------------------
    async def check(self) -> EncoderInstallResult:
        status = await self.status()
        if not status.installed:
            return EncoderInstallResult(
                ok=False, status=status, message=status.message, how_to_fix=status.how_to_fix
            )
        try:
            backend = self._backend()
            backend.load()
            backend.unload()
        except AiError as exc:
            return EncoderInstallResult(
                ok=False, status=status, message=exc.message, how_to_fix=exc.how_to_fix
            )
        return EncoderInstallResult(
            ok=True, status=status, message="Лёгкая модель загружается и работает."
        )

    async def remove(self) -> EncoderStatus:
        if self.model_dir.is_dir():
            shutil.rmtree(self.model_dir, ignore_errors=True)
        await self.events.info(
            MODULE,
            "Лёгкая модель удалена.",
            explanation="Встроенный лёгкий распознаватель продолжает работать.",
            operation="remove",
            status="ok",
        )
        await self.session.commit()
        return await self.status()


__all__ = [
    "MODEL_LICENSE",
    "MODEL_REPO",
    "MODULE",
    "OFFICIAL_ASSETS",
    "EncoderInstallResult",
    "EncoderService",
    "EncoderStatus",
    "ModelAsset",
    "human_size",
]
