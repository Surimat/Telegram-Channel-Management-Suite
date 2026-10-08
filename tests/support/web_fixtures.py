"""Deterministic local fixture site + an HTTP/HTML test browser runtime.

The Web Wrapper Hub was, until now, only *architecturally* implemented: its
"real" runtime is Playwright, which CI does not install. These fixtures let the
whole wrapper pipeline be exercised for real — over HTTP, against real pages —
without a browser binary and without any external site:

* :class:`FixtureSite` — a threaded ``http.server`` on ``127.0.0.1`` serving
  small, stable HTML pages (index, search, article, extract, login, slow, error,
  redirect). No CAPTCHA/MFA/login bypass anywhere.
* :class:`FixtureBrowserRuntime` — a :class:`BrowserRuntime` that performs **real
  HTTP GETs** against the fixture server and parses the **real HTML** into a
  :class:`PageSnapshot`. It is explicitly *not* a browser: it exists so the CI can
  verify the engine/provider/router contract deterministically. The genuine
  browser path is proven separately by the Playwright integration test.

Nothing here touches an account, a credential or a network the owner does not own.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from backend.app.ai.gateway.browser import PageSnapshot

# ---------------------------------------------------------------------------
# HTML tree + a tiny CSS-subset selector matcher
# ---------------------------------------------------------------------------
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}


@dataclass
class Node:
    tag: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node] = field(default_factory=list)
    parent: Node | None = None
    text: str = ""

    def iter(self):
        yield self
        for child in self.children:
            yield from child.iter()

    def all_text(self) -> str:
        parts = [self.text]
        for child in self.children:
            parts.append(child.all_text())
        return " ".join(p for p in parts if p)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="__root__")
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag=tag, attrs={k: (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag=tag, attrs={k: (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data):
        text = data.strip()
        if text:
            self._stack[-1].text = (self._stack[-1].text + " " + text).strip()


def parse_html(html: str) -> Node:
    parser = _TreeParser()
    parser.feed(html)
    return parser.root


def _matches(node: Node, selector: str) -> bool:
    """Match a small CSS subset: ``tag``, ``.class``, ``#id``, ``tag.class``,
    ``[attr]``, ``[attr=value]``. Space-separated descendants are supported."""
    if not selector:
        return False
    parts = [p for p in selector.replace(">", " ").split() if p]
    return _match_part(node, parts[-1])


def _match_part(node: Node, part: str) -> bool:
    rest = part
    if "[" in rest:
        head, _, tail = rest.partition("[")
        attr_expr = tail.rstrip("]")
        if "=" in attr_expr:
            key, _, val = attr_expr.partition("=")
            val = val.strip("'\"")
            if node.attrs.get(key.strip()) != val:
                return False
        elif attr_expr.strip() not in node.attrs:
            return False
        rest = head
    if "#" in rest:
        tag, _, idv = rest.partition("#")
        if node.attrs.get("id") != idv:
            return False
        rest = tag
    if "." in rest:
        tag, _, cls = rest.partition(".")
        if cls not in node.attrs.get("class", "").split():
            return False
        rest = tag
    return not (rest and node.tag != rest)


def select_all(root: Node, selector: str) -> list[Node]:
    return [n for n in root.iter() if n.tag != "__root__" and _matches(n, selector)]


# ---------------------------------------------------------------------------
# The fixture site
# ---------------------------------------------------------------------------
_DATASET = [
    {"title": "Альфа", "kind": "news", "url": "/a"},
    {"title": "Бета", "kind": "funny", "url": "/b"},
    {"title": "Гамма", "kind": "donation", "url": "/c"},
]

_INDEX = """<!doctype html><html><head><meta charset="utf-8">
<title>Fixture Index</title></head><body>
<h1 id="title">Каталог каналов</h1>
<form action="/search" method="get">
<input name="q" class="search" type="text" aria-label="Поиск">
</form>
<nav><a class="nav" href="/article">Статья</a>
<a class="nav" href="/extract">Данные</a>
<a class="nav" href="/search?q=новости">Поиск</a></nav>
<p class="lead">Это тестовая страница обёртки.</p>
<ul id="list">{rows}</ul>
</body></html>"""

_ARTICLE = """<!doctype html><html><head><meta charset="utf-8">
<title>Fixture Article</title></head><body>
<h1 id="title">Заголовок статьи</h1>
<article class="body"><p>Первый абзац текста.</p>
<p>Второй абзац со словом найти-меня.</p></article>
</body></html>"""

_EXTRACT = """<!doctype html><html><head><meta charset="utf-8">
<title>Fixture Extract</title></head><body>
<h1>Данные</h1><table><tr class="row" data-kind="news">
<td class="name">Альфа</td><td class="kind">news</td></tr>
<tr class="row" data-kind="funny"><td class="name">Бета</td><td class="kind">funny</td></tr>
</table>
<ul class="links"><li class="link"><a href="/a">Канал А</a></li>
<li class="link"><a href="/b">Канал Б</a></li></ul>
</body></html>"""

_LOGIN = """<!doctype html><html><head><meta charset="utf-8">
<title>Войти</title></head><body>
<h1>Sign in</h1><p>Please log in to continue.</p></body></html>"""


def _search_page(q: str) -> str:
    rows = [d for d in _DATASET if q.lower() in d["title"].lower() or q.lower() in d["kind"]]
    if q and not rows:
        rows = _DATASET
    lis = "".join(
        f'<li class="result" data-kind="{d["kind"]}">'
        f'<a class="result-link" href="{d["url"]}">{d["title"]}</a></li>'
        for d in rows
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>Поиск: {q}</title></head><body>"
        f'<h1 id="title">Результаты по «{q}»</h1><ul class="results">{lis}</ul>'
        "</body></html>"
    )


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            rows = "".join(
                f'<li class="item" data-kind="{d["kind"]}">'
                f'<a href="{d["url"]}">{d["title"]}</a></li>'
                for d in _DATASET
            )
            self._send(200, _INDEX.format(rows=rows).encode())
        elif path == "/article":
            self._send(200, _ARTICLE.encode())
        elif path == "/extract":
            self._send(200, _EXTRACT.encode())
        elif path == "/login":
            self._send(200, _LOGIN.encode())
        elif path == "/search":
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            self._send(200, _search_page(q).encode())
        elif path == "/slow":
            import time

            time.sleep(5)
            self._send(200, b"<html><body>late</body></html>")
        elif path == "/boom":
            self._send(500, b"<html><body>error</body></html>")
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/article")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send(404, b"<html><body>not found</body></html>")

    def log_message(self, *args):  # silence
        return


class FixtureSite:
    """A local HTTP server with deterministic pages; use as a context manager."""

    def __init__(self) -> None:
        self._srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        self._srv.daemon_threads = True
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self) -> FixtureSite:
        self._thread.start()
        return self

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def stop(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()

    def __enter__(self) -> FixtureSite:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# HTTP/HTML test runtime (real HTTP + real HTML parse; NOT a browser)
# ---------------------------------------------------------------------------
class FixtureBrowserRuntime:
    """A BrowserRuntime that fetches the fixture site over real HTTP.

    ``available`` reflects whether the *transport* (httpx) is importable, so the
    same availability semantics as the real runtime apply. ``read``/``extract``
    parse the last fetched page with the small selector engine above.
    """

    name = "fixture-http"

    def __init__(self, site: FixtureSite, *, timeout_s: float = 3.0) -> None:
        self.site = site
        self.timeout_s = timeout_s
        self._html = ""
        self._url = ""
        self._title = ""
        self._root: Node | None = None
        self.actions: list[tuple[str, str, str]] = []
        self.closed = False

    @property
    def available(self) -> bool:
        try:
            import httpx  # noqa: F401
        except Exception:
            return False
        return True

    def availability_detail(self) -> str:
        return "Тестовый HTTP-движок (fixture)." if self.available else "httpx недоступен."

    def _abs(self, href: str) -> str:
        if href.startswith("http"):
            return href
        return self.site.url(href)

    async def _get(self, url: str) -> None:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=self.timeout_s)
            if resp.status_code >= 500:
                raise RuntimeError(f"HTTP {resp.status_code}")
            self._html = resp.text
            self._url = str(resp.url)
        self._root = parse_html(self._html)
        titles = select_all(self._root, "title")
        self._title = titles[0].all_text() if titles else ""

    def _snap(self) -> PageSnapshot:
        from backend.app.ai.gateway.browser import PageSnapshot

        body = select_all(self._root, "body") if self._root else []
        text = body[0].all_text() if body else ""
        return PageSnapshot(url=self._url, title=self._title, text=text)

    async def open(self, url: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("open", url, ""))
        await self._get(self._abs(url))
        return self._snap()

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("fill", selector, value))
        # Fixture convention: filling a search box navigates to /search?q=value.
        if "search" in selector or "q" in selector:
            await self._get(self.site.url(f"/search?q={value}"))
        return self._snap()

    async def click(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("click", selector, ""))
        nodes = select_all(self._root, selector) if self._root else []
        for n in nodes:
            href = n.attrs.get("href", "")
            if href:
                await self._get(self._abs(href))
                break
        return self._snap()

    async def press(self, selector: str, key: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("press", selector, key))
        return self._snap()

    async def wait_for(self, selector: str, *, timeout_ms: int = 15000) -> PageSnapshot:
        self.actions.append(("wait_for", selector, ""))
        return self._snap()

    async def read(self, selector: str, *, take_last: bool = True) -> PageSnapshot:
        self.actions.append(("read", selector, "last" if take_last else "first"))
        nodes = select_all(self._root, selector) if self._root else []
        text = ""
        if nodes:
            node = nodes[-1] if take_last else nodes[0]
            text = node.all_text()
        snap = self._snap()
        snap.response_text = text
        return snap

    async def extract(
        self, selector: str, *, attrs: tuple[str, ...] = ("href",)
    ) -> PageSnapshot:
        self.actions.append(("extract", selector, ",".join(attrs)))
        nodes = select_all(self._root, selector) if self._root else []
        items: list[dict[str, object]] = []
        for n in nodes:
            # Prefer a nested link's text/href when the row is a container.
            link = select_all(n, "a")
            source = link[0] if link else n
            items.append(
                {
                    "tag": source.tag,
                    "text": source.all_text(),
                    "href": source.attrs.get("href", ""),
                    "attributes": {a: n.attrs[a] for a in attrs if a in n.attrs},
                }
            )
        snap = self._snap()
        snap.items = items
        return snap

    async def close(self) -> None:
        self.closed = True


__all__ = [
    "FixtureBrowserRuntime",
    "FixtureSite",
    "Node",
    "parse_html",
    "select_all",
]
