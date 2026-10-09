"""Browser-runtime preflight and preparation (v2.0).

The Web Wrapper Hub needs a real browser, but the browser is deliberately an
**optional** component: API providers (including the keyless free one) work with
no browser at all. This module makes the state legible instead of binary:

* :func:`preflight` inspects the environment **without** launching anything and
  returns an ordered list of preparation steps with an honest status
  (``ok`` / ``missing`` / ``optional`` / ``unknown``).
* :func:`probe` actually tries to launch Chromium once and reports whether it
  worked — a real verification, not a claim from a README.

No step ever downloads anything implicitly and no step defeats CAPTCHA/MFA.
"""

from __future__ import annotations

import glob
import importlib.util
import os
from dataclasses import dataclass, field

#: Statuses for a preparation step.
STEP_OK = "ok"
STEP_MISSING = "missing"
STEP_OPTIONAL = "optional"
STEP_UNKNOWN = "unknown"

_INSTALL_HINT = (
    "pip install playwright\n"
    "playwright install chromium\n"
    "Примечание: браузер необязателен — обычные API-провайдеры, включая "
    "бесплатный без ключа, работают и без него."
)


@dataclass(slots=True)
class PrepStep:
    id: str
    title: str
    status: str = STEP_UNKNOWN
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(slots=True)
class BrowserPreflight:
    available: bool = False
    runtime: str = "playwright"
    steps: list[PrepStep] = field(default_factory=list)
    install_hint: str = _INSTALL_HINT
    api_works_without_browser: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "runtime": self.runtime,
            "steps": [s.as_dict() for s in self.steps],
            "install_hint": self.install_hint,
            "api_works_without_browser": self.api_works_without_browser,
            "detail": self.detail(),
        }

    def detail(self) -> str:
        if self.available:
            return "Браузерный движок готов к работе."
        failing = [s.title for s in self.steps if s.status == STEP_MISSING]
        if failing:
            return "Браузер недоступен: " + ", ".join(failing) + "."
        return "Браузерный движок не установлен."


def _package_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _browser_binary_present() -> str:
    """Return a path when a Chromium build looks present, else ''."""
    candidates: list[str] = []
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        candidates.append(os.path.join(env, "chromium-*"))
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".cache", "ms-playwright", "chromium-*"),
        os.path.join(home, "AppData", "Local", "ms-playwright", "chromium-*"),
    ]
    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return ""


def preflight() -> BrowserPreflight:
    """Inspect the environment without launching a browser."""
    steps: list[PrepStep] = []

    pw = _package_present("playwright")
    steps.append(
        PrepStep(
            id="package",
            title="Пакет Playwright",
            status=STEP_OK if pw else STEP_MISSING,
            detail="Установлен." if pw else "Не установлен (pip install playwright).",
        )
    )

    binary = _browser_binary_present()
    if binary:
        steps.append(
            PrepStep(
                id="chromium",
                title="Сборка Chromium",
                status=STEP_OK,
                detail=f"Найдена: {os.path.basename(binary)}.",
            )
        )
    elif pw:
        steps.append(
            PrepStep(
                id="chromium",
                title="Сборка Chromium",
                status=STEP_MISSING,
                detail="Пакет есть, браузер не установлен (playwright install chromium).",
            )
        )
    else:
        steps.append(
            PrepStep(
                id="chromium",
                title="Сборка Chromium",
                status=STEP_UNKNOWN,
                detail="Пока неизвестно — сначала нужен пакет Playwright.",
            )
        )

    steps.append(
        PrepStep(
            id="api",
            title="API-провайдеры без браузера",
            status=STEP_OK,
            detail="Работают независимо от браузера.",
        )
    )

    available = pw and bool(binary)
    return BrowserPreflight(available=available, steps=steps)


async def probe(*, headless: bool = True) -> BrowserPreflight:
    """Actually launch Chromium once and report whether it worked.

    This is a real verification. It never downloads anything and closes what it
    opens. A failure is reported, never raised.
    """
    result = preflight()
    if not result.available:
        return result

    launcher = PrepStep(
        id="launch",
        title="Пробный запуск браузера",
        status=STEP_UNKNOWN,
        detail="Проверяется…",
    )
    result.steps.append(launcher)
    try:
        from backend.app.ai.gateway.browser import PlaywrightBrowserRuntime

        runtime = PlaywrightBrowserRuntime(headless=headless)
        # A navigation to a blank page exercises the real launch path.
        await runtime.open("about:blank")
        await runtime.close()
        launcher.status = STEP_OK
        launcher.detail = "Браузер успешно запущен."
        result.available = True
    except Exception as exc:  # pragma: no cover - depends on the local machine
        launcher.status = STEP_MISSING
        launcher.detail = f"Не удалось запустить: {type(exc).__name__}."
        result.available = False
    return result


__all__ = [
    "STEP_MISSING",
    "STEP_OK",
    "STEP_OPTIONAL",
    "STEP_UNKNOWN",
    "BrowserPreflight",
    "PrepStep",
    "preflight",
    "probe",
]
