"""Browser runtime abstraction for Web UI wrappers (v1.8, requirements 4/23/24).

The engine never talks to Playwright directly: it uses a :class:`BrowserRuntime`
implementation. This keeps a hard browser dependency **optional**:

* :class:`PlaywrightBrowserRuntime` — the real runtime, imported lazily. If the
  ``playwright`` package or its Chromium build is missing it reports itself
  unavailable with a clear message instead of breaking the app.
* :class:`FakeBrowserRuntime` — a deterministic in-memory runtime for tests.

Docker and a Windows PC without Chromium keep working: API providers do not need
any of this (requirement 24). The runtime uses the owner's **own** browser
profile; it never imports or copies someone else's cookies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class PageSnapshot:
    """What a runtime saw after an interaction (text only; never a secret)."""

    url: str = ""
    title: str = ""
    text: str = ""
    #: The last matching response node's text, when a selector was given.
    response_text: str = ""
    #: Structured records read by :meth:`BrowserRuntime.extract` (tag/text/href/
    #: attributes). It is page content the owner asked for, never a credential.
    items: list[dict[str, object]] = field(default_factory=list)
    login_detected: bool = False
    error: str = ""


@runtime_checkable
class BrowserRuntime(Protocol):
    """Minimal browser control surface used by wrappers."""

    @property
    def name(self) -> str:
        ...

    @property
    def available(self) -> bool:
        """True only when a real browser can be launched right now."""
        ...

    def availability_detail(self) -> str:
        """Human RU explanation when :attr:`available` is False."""
        ...

    async def open(self, url: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        ...

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        ...

    async def click(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        ...

    async def press(self, selector: str, key: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        ...

    async def wait_for(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        ...

    async def read(self, selector: str, *, take_last: bool = True) -> PageSnapshot:
        ...

    async def extract(
        self, selector: str, *, attrs: tuple[str, ...] = ("href",)
    ) -> PageSnapshot:
        """Read structured records (tag/text/href/attributes) from all matches."""
        ...

    async def close(self) -> None:
        ...


class PlaywrightBrowserRuntime:
    """Real Chromium runtime via Playwright (optional, lazy import).

    Uses a persistent profile directory the owner controls. ``headless`` is on by
    default so it works on a server/Docker; a desktop build may turn it off.
    """

    name = "playwright"

    def __init__(self, *, user_data_dir: str = "", headless: bool = True) -> None:
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._pw = None
        self._context = None
        self._page = None

    # -- availability ----------------------------------------------------
    @property
    def available(self) -> bool:
        try:
            import playwright  # noqa: F401
            from playwright.async_api import async_playwright  # noqa: F401
        except Exception:
            return False
        return True

    def availability_detail(self) -> str:
        if self.available:
            return "Браузерный движок Playwright доступен."
        return (
            "Браузерный движок не установлен. Установите его в разделе "
            "«Центр ИИ» → «Web Wrappers». Обычные API-провайдеры работают и без него."
        )

    async def _ensure_page(self):
        if self._page is not None:
            return self._page
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            self.user_data_dir or "",
            headless=self.headless,
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        return self._page

    async def open(self, url: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        page = await self._ensure_page()
        await page.goto(url, timeout=timeout_ms)
        return await self._snapshot(page)

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        page = await self._ensure_page()
        await page.fill(selector, value, timeout=timeout_ms)
        return await self._snapshot(page)

    async def click(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        page = await self._ensure_page()
        await page.click(selector, timeout=timeout_ms)
        return await self._snapshot(page)

    async def press(self, selector: str, key: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        page = await self._ensure_page()
        await page.press(selector, key, timeout=timeout_ms)
        return await self._snapshot(page)

    async def wait_for(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        page = await self._ensure_page()
        await page.wait_for_selector(selector, timeout=timeout_ms)
        return await self._snapshot(page)

    async def read(self, selector: str, *, take_last: bool = True) -> PageSnapshot:
        page = await self._ensure_page()
        nodes = await page.query_selector_all(selector)
        text = ""
        if nodes:
            node = nodes[-1] if take_last else nodes[0]
            text = (await node.inner_text()) or ""
        snap = await self._snapshot(page)
        snap.response_text = text
        return snap

    async def extract(
        self, selector: str, *, attrs: tuple[str, ...] = ("href",)
    ) -> PageSnapshot:
        page = await self._ensure_page()
        wanted = list(attrs or ())
        items = await page.eval_on_selector_all(
            selector,
            """(nodes, attrs) => nodes.map((n) => {
                const link = n.querySelector('a');
                const src = link || n;
                const rec = {
                    tag: src.tagName ? src.tagName.toLowerCase() : '',
                    text: (src.innerText || src.textContent || '').trim(),
                    href: src.getAttribute('href') || '',
                    attributes: {},
                };
                for (const a of attrs) {
                    const v = n.getAttribute(a);
                    if (v !== null) rec.attributes[a] = v;
                }
                return rec;
            })""",
            wanted,
        )
        snap = await self._snapshot(page)
        snap.items = list(items or [])
        return snap

    async def _snapshot(self, page) -> PageSnapshot:
        try:
            text = await page.inner_text("body")
        except Exception:
            text = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        return PageSnapshot(url=page.url, title=title, text=text)

    async def close(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._context = None
            self._pw = None
            self._page = None


@dataclass
class FakeBrowserRuntime:
    """Scriptable runtime: queue of snapshots, records every action."""

    name: str = "fake"
    _available: bool = True
    detail: str = "Тестовый браузерный движок."
    queue: list[PageSnapshot] = field(default_factory=list)
    actions: list[tuple[str, str, str]] = field(default_factory=list)
    fail_on: str = ""
    current: PageSnapshot = field(default_factory=PageSnapshot)

    @property
    def available(self) -> bool:
        return self._available

    def availability_detail(self) -> str:
        return self.detail

    def _next(self) -> PageSnapshot:
        if self.queue:
            self.current = self.queue.pop(0)
        return self.current

    def _maybe_fail(self, action: str) -> None:
        if self.fail_on and self.fail_on == action:
            raise RuntimeError(f"fake browser failure on {action}")

    async def open(self, url: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("open", url, ""))
        self._maybe_fail("open")
        return self._next()

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("fill", selector, value))
        self._maybe_fail("fill")
        return self._next()

    async def click(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("click", selector, ""))
        self._maybe_fail("click")
        return self._next()

    async def press(self, selector: str, key: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("press", selector, key))
        self._maybe_fail("press")
        return self._next()

    async def wait_for(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("wait_for", selector, ""))
        self._maybe_fail("wait_for")
        return self._next()

    async def read(self, selector: str, *, take_last: bool = True) -> PageSnapshot:
        self.actions.append(("read", selector, "last" if take_last else "first"))
        self._maybe_fail("read")
        return self._next()

    async def extract(
        self, selector: str, *, attrs: tuple[str, ...] = ("href",)
    ) -> PageSnapshot:
        self.actions.append(("extract", selector, ",".join(attrs)))
        self._maybe_fail("extract")
        return self._next()

    async def close(self) -> None:
        self.actions.append(("close", "", ""))


__all__ = [
    "BrowserRuntime",
    "FakeBrowserRuntime",
    "PageSnapshot",
    "PlaywrightBrowserRuntime",
]
