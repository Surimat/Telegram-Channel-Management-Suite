"""Central localization catalog (RU/EN).

One source of truth for backend-produced user-facing strings. The UI has its own
catalog (``frontend/src/i18n``); this one covers messages the backend returns
(owner auth, config sync, the consistency auditor, capability explanations and
the help catalog). Keys are stable identifiers; every key must have both a
Russian and an English string (enforced by ``tests/test_i18n.py``).

The default language follows the app preference: Russian when the system/owner
language is Russian, otherwise Russian as the safe fallback (D-101).
"""

from __future__ import annotations

LANGUAGES = ("ru", "en")
DEFAULT_LANGUAGE = "ru"


# Message catalog: key -> {"ru": ..., "en": ...}. Never put secrets here.
MESSAGES: dict[str, dict[str, str]] = {
    # --- Capability graph requirement labels --------------------------------
    "cap.channel": {"ru": "Канал", "en": "Channel"},
    "cap.channel.fix": {
        "ru": "Добавьте канал в разделе «Каналы».",
        "en": "Add a channel in the Channels section.",
    },
    "cap.bot_binding": {"ru": "Подключённый бот", "en": "Bound bot"},
    "cap.bot_binding.fix": {
        "ru": "Подключите бота к каналу в разделе «Боты».",
        "en": "Bind a bot to the channel in the Bots section.",
    },
    "cap.user_session": {"ru": "Пользовательский аккаунт", "en": "User account"},
    "cap.user_session.fix": {
        "ru": "Подключите аккаунт в разделе «Аккаунты».",
        "en": "Connect an account in the Account Hub.",
    },
    "cap.permission": {"ru": "Проверенные права", "en": "Verified rights"},
    "cap.permission.fix": {
        "ru": "Проверьте права аккаунта на канал.",
        "en": "Verify the account's rights on the channel.",
    },
    "cap.posting_capability": {"ru": "Возможность публикации", "en": "Posting capability"},
    "cap.posting_capability.fix": {
        "ru": "Подключите бота с правом публикации в канал.",
        "en": "Bind a bot with posting rights to the channel.",
    },
    "cap.encoder_model": {"ru": "Модель мини-ИИ", "en": "Mini-AI model"},
    "cap.encoder_model.fix": {
        "ru": "Установите лёгкую модель в разделе «Мини-ИИ».",
        "en": "Install the lightweight model in the Mini-AI section.",
    },
    "cap.ffmpeg": {"ru": "Компонент обработки медиа", "en": "Media tooling"},
    "cap.ffmpeg.fix": {
        "ru": "Установите ffmpeg для работы с медиа.",
        "en": "Install ffmpeg to work with media.",
    },
    "cap.owner_auth": {"ru": "Владелец", "en": "Owner"},
    "cap.owner_auth.fix": {
        "ru": "Создайте профиль владельца в разделе «Владелец».",
        "en": "Create the owner profile in the Owner section.",
    },
    "cap.google_drive": {"ru": "Google Drive", "en": "Google Drive"},
    "cap.google_drive.fix": {
        "ru": "Подключите Google Drive в разделе «Владелец» → «Синхронизация».",
        "en": "Connect Google Drive in Owner → Configuration Sync.",
    },
    "cap.state.available": {"ru": "Доступно", "en": "Available"},
    "cap.state.partial": {"ru": "Частично доступно", "en": "Partially available"},
    "cap.state.needs_setup": {"ru": "Требуется настройка", "en": "Needs setup"},
    "cap.state.unavailable": {"ru": "Недоступно", "en": "Unavailable"},
    "cap.state.not_implemented": {"ru": "Не реализовано", "en": "Not implemented"},

    # --- Consistency auditor severity ---------------------------------------
    "consistency.ok": {"ru": "Всё согласовано", "en": "Everything is consistent"},
    "consistency.warnings": {"ru": "предупреждений", "en": "warnings"},
    "consistency.errors": {"ru": "ошибок", "en": "errors"},
    "consistency.health.ok": {"ru": "В порядке", "en": "OK"},
    "consistency.health.warning": {"ru": "Предупреждение", "en": "Warning"},
    "consistency.health.fail": {"ru": "Ошибка", "en": "Fail"},
    "consistency.health.not_tested": {"ru": "Не проверено", "en": "Not tested"},

    # --- Owner auth ---------------------------------------------------------
    "owner.title": {"ru": "Владелец Suite", "en": "Suite Owner"},
    "owner.disabled": {"ru": "Защита приложения выключена", "en": "App protection is off"},
    "owner.enabled": {"ru": "Защита приложения включена", "en": "App protection is on"},
    "owner.locked": {"ru": "Приложение заблокировано", "en": "The app is locked"},
    "owner.unlocked": {"ru": "Доступ разрешён", "en": "Access granted"},
    "owner.bad_password": {"ru": "Неверный пароль.", "en": "Wrong password."},
    "owner.no_profile": {"ru": "Профиль владельца ещё не создан.", "en": "No owner profile yet."},
    "owner.already_exists": {
        "ru": "Профиль владельца уже создан.",
        "en": "An owner profile already exists.",
    },
    "owner.recovery_hint": {
        "ru": "Пароль восстановления не хранится. Если вы его забудете, восстановить "
        "зашифрованную конфигурацию не получится.",
        "en": "The recovery password is not stored. If you forget it, the encrypted "
        "configuration cannot be recovered.",
    },
    "owner.local_only": {
        "ru": "Это локальная учётная запись для защиты настроек. Она не связана с "
        "вашим Telegram-аккаунтом и работает полностью офлайн.",
        "en": "This is a local identity that protects your configuration. It is not "
        "linked to your Telegram account and works fully offline.",
    },
    "owner.secret_too_short": {
        "ru": "Пароль слишком короткий.",
        "en": "The password is too short.",
    },
    "owner.logout": {"ru": "Владелец вышел.", "en": "The owner has logged out."},
    "owner.auth_required": {
        "ru": "Для этого действия нужно войти как владелец.",
        "en": "You must sign in as the owner to do this.",
    },
    "owner.disabled_note": {
        "ru": "Пока защита выключена, панель открыта без входа. Включите защиту, "
        "если компьютером пользуются другие.",
        "en": "While protection is off the panel is open without a login. Turn it on "
        "if other people use this computer.",
    },
    "owner.google_separate": {
        "ru": "Пароль владельца и вход в Google — разные вещи. Google нужен только для "
        "синхронизации настроек.",
        "en": "The owner password and the Google sign-in are separate. Google is used "
        "only to sync settings.",
    },
    "owner.pin_note": {
        "ru": "PIN-код короче пароля и подходит для быстрого входа на личном ПК.",
        "en": "A PIN is shorter than a password and is convenient on a personal PC.",
    },

    # --- Config sync (v1.6) -------------------------------------------------
    "sync.state.unavailable": {"ru": "Недоступно", "en": "Unavailable"},
    "sync.state.needs_setup": {"ru": "Требуется настройка", "en": "Needs setup"},
    "sync.state.available": {"ru": "Доступно", "en": "Available"},
    "sync.state.error": {"ru": "Ошибка", "en": "Error"},
    "sync.provider.none": {"ru": "Не выбран", "en": "Not selected"},
    "sync.provider.local": {"ru": "Локальная папка", "en": "Local folder"},
    "sync.provider.google_drive": {"ru": "Google Drive", "en": "Google Drive"},
    "sync.uploaded": {"ru": "Конфигурация выгружена.", "en": "Configuration uploaded."},
    "sync.applied": {"ru": "Конфигурация восстановлена.", "en": "Configuration restored."},
    "sync.no_bundle": {
        "ru": "В облаке нет файла конфигурации.",
        "en": "There is no configuration bundle in the cloud.",
    },
    "sync.upload": {"ru": "Выгрузить конфигурацию", "en": "Upload configuration"},
    "sync.download": {"ru": "Скачать конфигурацию", "en": "Download configuration"},
    "sync.sync_now": {"ru": "Синхронизировать", "en": "Sync now"},
    "sync.connect_google": {"ru": "Подключить Google Drive", "en": "Connect Google Drive"},
    "sync.disconnect": {"ru": "Отключить Google Drive", "en": "Disconnect Google Drive"},
    "sync.keep_local": {"ru": "Оставить локальные", "en": "Keep local"},
    "sync.keep_cloud": {"ru": "Оставить облачные", "en": "Keep cloud"},
    "sync.cancel": {"ru": "Отмена", "en": "Cancel"},
    "sync.owner_required": {
        "ru": "Сначала создайте профиль владельца: он нужен для шифрования.",
        "en": "Create the owner profile first: it is needed for encryption.",
    },
    "sync.no_live_db": {
        "ru": "Синхронизируется только конфигурация. Файлы сессий Telegram, TDATA и "
        "сама база данных не копируются.",
        "en": "Only configuration is synced. Telegram session files, TDATA and the "
        "database itself are never copied.",
    },
    "sync.appdata_scope": {
        "ru": "Приложение получает доступ только к своей скрытой папке в Google Drive.",
        "en": "The app only gets access to its own hidden folder in Google Drive.",
    },

    # --- Config sync --------------------------------------------------------
    "sync.title": {"ru": "Синхронизация", "en": "Configuration Sync"},
    "sync.off": {"ru": "Синхронизация выключена.", "en": "Sync is off."},
    "sync.never": {"ru": "Ещё не синхронизировалось.", "en": "Never synced yet."},
    "sync.need_owner": {
        "ru": "Сначала создайте профиль владельца — он нужен для шифрования.",
        "en": "Create the owner profile first — it is needed for encryption.",
    },
    "sync.category.safe": {"ru": "Обычные настройки", "en": "Safe configuration"},
    "sync.category.sensitive": {"ru": "Чувствительные настройки", "en": "Sensitive configuration"},
    "sync.category.highly_sensitive": {
        "ru": "Особо чувствительные данные",
        "en": "Highly sensitive data",
    },
    "sync.policy.sync": {"ru": "Синхронизируется", "en": "Synced"},
    "sync.policy.encrypted": {
        "ru": "Синхронизируется в зашифрованном виде",
        "en": "Synced encrypted",
    },
    "sync.policy.never": {"ru": "Никогда не синхронизируется", "en": "Never synced"},
    "sync.highly_sensitive_warning": {
        "ru": "Файлы авторизации Telegram — особо чувствительные данные. Включайте их "
        "синхронизацию только осознанно: они дают полный доступ к аккаунту.",
        "en": "Telegram authorization files are highly sensitive. Only sync them "
        "deliberately: they grant full account access.",
    },
    "sync.conflict": {
        "ru": "На другом компьютере настройки изменились.",
        "en": "The configuration changed on another computer.",
    },
    "sync.wrong_password": {
        "ru": "Не удалось расшифровать конфигурацию: неверный пароль.",
        "en": "Could not decrypt the configuration: wrong password.",
    },
    "sync.corrupt_bundle": {
        "ru": "Файл конфигурации повреждён или не читается.",
        "en": "The configuration bundle is corrupt or unreadable.",
    },
    "sync.provider_unavailable": {
        "ru": "Провайдер синхронизации недоступен. Программа продолжает работать.",
        "en": "The sync provider is unavailable. The app keeps working.",
    },
    "sync.not_configured": {"ru": "Провайдер не настроен.", "en": "No provider configured."},

    # --- Session risk (single unified wording) ------------------------------
    "risk.user_account": {
        "ru": "Пользовательский Telegram-аккаунт даёт Suite расширенные возможности, "
        "но использование его для массовых действий может привести к ограничениям "
        "или блокировке. Telegram не предоставляет универсального безопасного лимита.",
        "en": "A user Telegram account gives the Suite expanded capabilities, but using "
        "it for bulk actions can lead to restrictions or a ban. Telegram does not "
        "provide a universal safe limit.",
    },
    "risk.reaction_no_account": {
        "ru": "Для реакций пользовательский аккаунт не нужен. Достаточно подключённого бота.",
        "en": "Reactions do not need a user account. A bound bot is enough.",
    },
}


def available_languages() -> list[str]:
    return list(LANGUAGES)


def normalize_language(language: str | None) -> str:
    """Return a supported language, defaulting to Russian."""
    if not language:
        return DEFAULT_LANGUAGE
    code = language.strip().lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def translate(key: str, language: str | None = None, *, default: str | None = None) -> str:
    """Translate ``key`` into ``language`` (falls back to RU, then ``default``)."""
    entry = MESSAGES.get(key)
    if entry is None:
        return default if default is not None else key
    lang = normalize_language(language)
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or (default or key)


def missing_keys() -> dict[str, list[str]]:
    """Return keys missing a language (used by the i18n test)."""
    missing: dict[str, list[str]] = {}
    for key, entry in MESSAGES.items():
        gaps = [lang for lang in LANGUAGES if not entry.get(lang, "").strip()]
        if gaps:
            missing[key] = gaps
    return missing


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "MESSAGES",
    "available_languages",
    "missing_keys",
    "normalize_language",
    "translate",
]
