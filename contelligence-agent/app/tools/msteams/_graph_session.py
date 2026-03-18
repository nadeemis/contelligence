"""Authenticated MS Graph session via Playwright + Edge.

Reuses the real Edge browser profile so that the user's existing Microsoft
365 SSO session carries over — no service-principal, client-secret, or
delegated-consent configuration required.

Token extraction strategies (in priority order):
  1. Playwright network interception (catches service-worker Graph calls)
  2. MSAL token cache in localStorage / sessionStorage

The session is designed to be **shared** across all MS Teams tools.  A
module-level singleton keeps the browser alive between tool invocations so
the first call pays the startup cost and subsequent calls are near-instant.

Usage::

    async with TeamsGraphSession() as session:
        data = await session.graph_get("/me/chats", params={"$top": "50"})
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import platform
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Route,
    Request,
    async_playwright,
)

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TEAMS_URL = "https://teams.microsoft.com/v2/"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

BROWSER_PROFILE_DIR = Path.home() / ".contelligence" / "teams-browser-profile"

_HEADLESS_READY_TIMEOUT = 60  # seconds
_HEADED_READY_TIMEOUT = 120

# Selector that indicates Teams has finished rendering.
_TEAMS_READY_SELECTOR = '[role="tree"] [role="treeitem"]'

# URL patterns indicating an authentication wall.
_AUTH_URL_PATTERNS = (
    "login.microsoftonline.com",
    "login.live.com",
    "adfs.",
    "/adfs/",
    "login.windows.net",
)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: TeamsGraphSession | None = None
_singleton_lock = asyncio.Lock()


async def get_session(*, headless: bool = True) -> TeamsGraphSession:
    """Return (and lazily create) the module-level singleton session."""
    global _singleton
    async with _singleton_lock:
        if _singleton is None or _singleton._closed:
            _singleton = TeamsGraphSession(headless=headless)
            await _singleton.connect()
        return _singleton


async def close_session() -> None:
    """Tear down the singleton session if it exists."""
    global _singleton
    async with _singleton_lock:
        if _singleton is not None:
            await _singleton.close()
            _singleton = None


# ---------------------------------------------------------------------------
# TeamsGraphSession
# ---------------------------------------------------------------------------

class TeamsGraphSession:
    """Persistent browser session that extracts a Graph token from Teams.

    Args:
        headless: Try headless first; fall back to headed if auth is needed.
    """

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._graph_tokens: list[str] = []  # all discovered Graph tokens
        self._token_index: int = 0  # index of the currently active token
        self._closed = True

    # ── async context manager ────────────────────────────────────────

    async def __aenter__(self) -> TeamsGraphSession:
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── connect / close ──────────────────────────────────────────────

    async def connect(self) -> None:
        """Launch Edge, navigate to Teams, extract the Graph bearer token."""
        if not self._closed:
            return

        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        if self._headless:
            ok = await self._try_connect(headless=True)
            if ok and await self._extract_graph_tokens():
                self._closed = False
                return
            # Headless failed — fall back to headed for interactive auth
            logger.info("Headless token extraction failed — retrying headed")
            await self._teardown()

        await self._try_connect(headless=False)
        if not await self._extract_graph_tokens():
            raise RuntimeError(
                "Could not extract a Graph API token from the Teams session. "
                "Ensure you are logged in to Microsoft Teams in Edge."
            )
        self._closed = False

    async def close(self) -> None:
        """Shut down browser and Playwright."""
        await self._teardown()
        self._closed = True

    # ── public API ───────────────────────────────────────────────────

    @property
    def graph_token(self) -> str | None:
        if self._graph_tokens and self._token_index < len(self._graph_tokens):
            return self._graph_tokens[self._token_index]
        return None

    async def graph_get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a GET request against the MS Graph API.

        ``path`` is appended to ``https://graph.microsoft.com/v1.0``
        (include the leading slash, e.g. ``/me/chats``).
        """
        
        logger.debug(f"Graph GET {path} with params={params} and headers={headers}")
        return await self._graph_request("GET", path, params=params, headers=headers)

    async def graph_post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a POST request against the MS Graph API."""
        
        logger.debug(f"Graph POST {path} with body={body}, params={params}, and headers={headers}")
        return await self._graph_request(
            "POST", path, body=body, params=params, headers=headers,
        )

    

    # ── internals ────────────────────────────────────────────────────

    async def _graph_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a Graph API call via the browser's fetch().

        On 401 (expired) — refreshes all tokens and retries.
        On 403 (wrong scopes) — rotates to the next available token and
        retries until all tokens have been tried.
        """
        if self._closed or self._page is None:
            raise RuntimeError("TeamsGraphSession is not connected")

        # Ensure we have at least one token
        if not self._graph_tokens:
            if not await self._extract_graph_tokens():
                raise RuntimeError("Graph token is unavailable")

        url = GRAPH_BASE + path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"

        extra_headers = {**(headers or {})}

        js_code = """
            async ([method, url, token, bodyStr, extraHeaders]) => {
                const opts = {
                    method,
                    headers: {
                        'Authorization': token,
                        'Content-Type': 'application/json',
                        ...extraHeaders,
                    },
                };
                if (bodyStr) opts.body = bodyStr;
                try {
                    const resp = await fetch(url, opts);
                    const text = await resp.text();
                    let data;
                    try { data = JSON.parse(text); } catch { data = text; }
                    if (!resp.ok) return { _error: true, status: resp.status, body: data };
                    return data;
                } catch (e) {
                    return { _error: true, message: e.message };
                }
            }
        """

        body_str = _json.dumps(body) if body else None

        async def _do_fetch(token: str) -> dict[str, Any]:
            return await self._page.evaluate(
                js_code,
                [method, url, token, body_str, extra_headers],
            )

        result = await _do_fetch(self.graph_token)

        # Handle 401 — token expired; re-extract all tokens and retry
        if isinstance(result, dict) and result.get("_error") and result.get("status") == 401:
            logger.info("Graph returned 401 — refreshing tokens and retrying")
            self._graph_tokens.clear()
            self._token_index = 0
            if await self._extract_graph_tokens():
                result = await _do_fetch(self.graph_token)

        # Handle 403 — wrong scopes; try remaining tokens
        if isinstance(result, dict) and result.get("_error") and result.get("status") == 403:
            start_index = self._token_index
            for i in range(len(self._graph_tokens)):
                candidate = (start_index + 1 + i) % len(self._graph_tokens)
                if candidate == start_index:
                    break
                self._token_index = candidate
                logger.info(
                    "Graph returned 403 — rotating to token %d/%d",
                    candidate + 1, len(self._graph_tokens),
                )
                result = await _do_fetch(self.graph_token)
                if not (isinstance(result, dict) and result.get("_error") and result.get("status") == 403):
                    break

        if isinstance(result, dict) and result.get("_error"):
            raise RuntimeError(f"Graph API error: {result}")

        return result

    # ── browser lifecycle ────────────────────────────────────────────

    async def _try_connect(self, *, headless: bool) -> bool:
        """Launch Edge, navigate to Teams, wait for the app to load."""
        try:
            self._pw = await async_playwright().start()

            # Remove stale singleton lock if present
            lock_file = BROWSER_PROFILE_DIR / "SingletonLock"
            if lock_file.exists() or lock_file.is_symlink():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

            self._context = await self._pw.chromium.launch_persistent_context(
                str(BROWSER_PROFILE_DIR),
                channel="msedge",
                headless=headless,
                viewport={"width": 1440, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    # Suppress "Open msteams?" external-protocol popups
                    "--disable-external-intent-requests",
                    "--disable-features=ExternalProtocolDialog",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )

            self._page = (
                self._context.pages[0]
                if self._context.pages
                else await self._context.new_page()
            )

            await self._page.goto(TEAMS_URL, wait_until="domcontentloaded")

            timeout = (
                _HEADLESS_READY_TIMEOUT if headless else _HEADED_READY_TIMEOUT
            ) * 1000

            # First launch can be slow; retry once on timeout.
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                try:
                    await self._page.wait_for_selector(
                        _TEAMS_READY_SELECTOR, timeout=timeout,
                    )
                    break
                except Exception:
                    if attempt < max_attempts:
                        logger.info(
                            "Teams ready selector timed out (attempt %d/%d) — "
                            "reloading and retrying",
                            attempt, max_attempts,
                        )
                        await self._page.wait_for_selector(
                            _TEAMS_READY_SELECTOR, timeout=timeout,
                        )
                    else:
                        raise

            # Let the page settle so API traffic fires
            await asyncio.sleep(4)
            return True

        except Exception as exc:
            logger.warning(f"_try_connect(headless={headless}) failed: {exc}")
            return False

    async def _teardown(self) -> None:
        """Close browser context and Playwright."""
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._pw = None

    # ── token extraction ─────────────────────────────────────────────

    async def _extract_graph_tokens(self) -> bool:
        """Extract all Graph-scoped bearer tokens from the browser session.

        Populates ``self._graph_tokens`` with every distinct Graph token
        found, sorted by scope count (broadest first).  Resets
        ``self._token_index`` to 0.

        Strategy 1: Intercept network traffic while navigating tabs.
        Strategy 2: Scan MSAL token cache in browser storage (all entries).
        """
        if self._page is None:
            return False

        seen_tokens: dict[str, int] = {}  # token → scope count

        # --- Strategy 1: network interception ---
        # Collect ALL distinct Graph tokens from traffic, not just one.
        intercepted: list[str] = []

        async def _intercept(route: Route, request: Request) -> None:
            auth = request.headers.get("authorization", "")
            if auth and "graph.microsoft.com" in request.url:
                if auth not in seen_tokens:
                    intercepted.append(auth)
                    seen_tokens[auth] = 0  # scope count unknown
            await route.continue_()

        await self._page.route("**/*graph.microsoft.com/**", _intercept)

        for tab_label in ("Chat", "Calendar", "Teams"):
            try:
                btn = self._page.locator(f'button[aria-label^="{tab_label}"]')
                await btn.click(timeout=5000)
                await asyncio.sleep(4)
            except Exception:
                pass

        await self._page.unroute("**/*graph.microsoft.com/**", _intercept)

        if intercepted:
            logger.info(
                f"Network interception found {len(intercepted)} distinct Graph token(s)"
            )

        # --- Strategy 2: MSAL cache (collect ALL Graph tokens) ---
        msal_tokens: list[dict[str, Any]] = await self._page.evaluate("""
            () => {
                const results = [];
                function scan(storage) {
                    for (let i = 0; i < storage.length; i++) {
                        const key = storage.key(i);
                        const val = storage.getItem(key);
                        if (!val) continue;
                        try {
                            const p = JSON.parse(val);
                            if (p.credentialType === 'AccessToken' || p.tokenType === 'Bearer') {
                                const secret = p.secret || p.accessToken || p.access_token;
                                const target = p.target || p.resource || '';
                                if (secret && target.includes('graph')) {
                                    results.push({
                                        token: 'Bearer ' + secret,
                                        scopes: target,
                                        scopeCount: target.split(' ').length,
                                        expiresOn: p.expiresOn || p.expires_on || '',
                                    });
                                }
                            }
                        } catch {}
                    }
                }
                try { scan(localStorage); } catch {}
                try { scan(sessionStorage); } catch {}
                return results;
            }
        """)

        if msal_tokens:
            logger.info(
                "MSAL cache found %d Graph token(s) with scope counts: %s",
                len(msal_tokens),
                [t["scopeCount"] for t in msal_tokens],
            )

        # Merge MSAL tokens into the set (prefer by scope count)
        for mt in msal_tokens:
            tok = mt["token"]
            if tok not in seen_tokens or mt["scopeCount"] > seen_tokens[tok]:
                seen_tokens[tok] = mt["scopeCount"]

        # Also include intercepted tokens that might not be in MSAL cache
        for tok in intercepted:
            seen_tokens.setdefault(tok, 0)

        if not seen_tokens:
            logger.warning("Could not extract any Graph token from the browser session")
            return False

        # Sort tokens: broadest scope count first (most likely to work)
        self._graph_tokens = sorted(
            seen_tokens.keys(),
            key=lambda t: seen_tokens[t],
            reverse=True,
        )
        self._token_index = 0

        logger.info(
            "Loaded %d Graph token(s); active token has ~%d scopes",
            len(self._graph_tokens),
            seen_tokens[self._graph_tokens[0]],
        )
        return True
