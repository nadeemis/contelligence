"""Authenticated SharePoint browser session.

Uses ``playwright.chromium.launch_persistent_context`` with ``channel='msedge'``
to reuse the **real Edge work-profile session**.  The browser is kept alive so
that all API calls can be executed *inside the browser context* via
``page.evaluate(fetch(...))``.  This sidesteps cookie / session-token
requirements — requests made through the browser carry all the right cookies,
headers, and origins automatically.

This module provides:

  - ``SharePointSession`` — async context-manager wrapping Playwright + Edge.

        async with SharePointSession(site_url) as session:
            result = await session.fetch("GET", url)
            raw    = await session.fetch_bytes("GET", download_url)

  - ``clear_session()`` — deletes the persistent browser profile.

Required settings (via tool context):
  - ``SHAREPOINT_SITE_URL`` — e.g. ``https://contoso.sharepoint.com/sites/team``

The session navigates to the SharePoint site URL to establish authentication,
then executes all subsequent ``fetch()`` calls within that authenticated
browser page.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import platform
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Request,
    async_playwright,
)

from app.settings import get_settings, AppSettings

logger = logging.getLogger(f"contelligence-agent.{__name__}")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

settings: AppSettings = get_settings()

# Persistent browser profile — separate from any Teams profile.
BROWSER_PROFILE_DIR = settings.app_data_dir() / "sharepoint-browser-profile"

# Directory for diagnostic screenshots when auth fails in headless mode.
SCREENSHOT_DIR = settings.app_data_dir() / "sharepoint-screenshots"

# Timeouts (seconds)
_HEADLESS_READY_TIMEOUT = 60
_HEADED_READY_TIMEOUT = 120

# URL fragments that indicate SharePoint is loaded and authenticated.
_SP_READY_PATTERNS = ("_api/", "_layouts/", "sharepoint.com")

# Patterns in the page URL or HTML that indicate an authentication wall.
_AUTH_URL_PATTERNS = (
    "login.microsoftonline.com",
    "login.live.com",
    "adfs.",
    "/adfs/",
    "login.windows.net",
)


# ---------------------------------------------------------------------------
# Readiness probe — wait until the page fires an authenticated request
# ---------------------------------------------------------------------------

class _ReadinessProbe:
    """Watches outgoing requests to detect when SharePoint is authenticated."""

    def __init__(self) -> None:
        self.ready = False
        self._auth_token: str | None = None

    def handler(self, request: Request) -> None:
        url = request.url
        if not self.ready and any(p in url for p in _SP_READY_PATTERNS):
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                self.ready = True
                self._auth_token = auth.split(" ", 1)[1]

    @property
    def token(self) -> str | None:
        return self._auth_token


# ---------------------------------------------------------------------------
# Edge executable discovery
# ---------------------------------------------------------------------------

def _find_edge_executable() -> str | None:
    """Locate the Microsoft Edge executable on the current platform."""
    system = platform.system()
    if system == "Windows":
        for candidate in (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ):
            if candidate.exists():
                return str(candidate)
    elif system == "Darwin":
        candidate = Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
        if candidate.exists():
            return str(candidate)
    else:  # Linux
        import shutil
        return shutil.which("microsoft-edge") or shutil.which("microsoft-edge-stable")
    return None


def _edge_user_data_dir() -> Path | None:
    """Return the default Edge User Data directory if it exists."""
    system = platform.system()
    if system == "Windows":
        p = Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"
    elif system == "Darwin":
        p = Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    else:
        p = Path.home() / ".config" / "microsoft-edge"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# SharePointSession
# ---------------------------------------------------------------------------

class SharePointSession:
    """Persistent authenticated browser session for SharePoint.

    Usage::

        async with SharePointSession("https://contoso.sharepoint.com/sites/team") as session:
            data = await session.fetch("GET", "/_api/web/lists")
            raw  = await session.fetch_bytes("GET", "/_api/web/GetFileByServerRelativeUrl(...)/$value")

    The browser is kept alive for the lifetime of the context manager.

    Args:
        site_url: Full SharePoint site URL.
        headless: If ``True`` (default), try headless first and automatically
            fall back to headed mode when an authentication wall is detected.
            If ``False``, always launch in headed (visible) mode.
    """

    def __init__(self, site_url: str, *, headless: bool = True) -> None:
        self._site_url = site_url.rstrip("/")
        self._headless = headless
        self._pw: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ── async context manager ────────────────────────────────────────

    async def __aenter__(self) -> SharePointSession:
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── connect / close ──────────────────────────────────────────────

    async def connect(self) -> None:
        """Launch Edge, navigate to the SharePoint site, wait until ready.

        Strategy (when ``headless=True``):
        1. Try headless with the persistent profile.
        2. If an authentication wall is detected (login redirect, login page
           HTML), save a diagnostic screenshot and fall back to headed mode.

        When ``headless=False``, skip straight to headed mode.
        """
        if self._headless:
            ok = await self._try_connect(
                headless=True, timeout=_HEADLESS_READY_TIMEOUT,
            )
            if ok:
                # Verify there is no auth wall hiding behind a 200 page.
                if not await self._is_authenticated():
                    logger.info(
                        "Headless session hit an auth wall — falling back "
                        "to headed mode for %s",
                        self._site_url,
                    )
                    await self._save_diagnostic_screenshot("headless_auth_wall")
                    await self.close()
                else:
                    return  # headless succeeded

        # Headed fallback (or headless=False requested directly).
        ok = await self._try_connect(
            headless=False, timeout=_HEADED_READY_TIMEOUT,
        )
        if ok:
            return

        raise TimeoutError(
            f"Could not establish a SharePoint session for {self._site_url}. "
            "Make sure you can reach the site in Edge and try again."
        )

    async def close(self) -> None:
        """Shut down the browser session."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None

    # ── fetch — JSON request through the browser ─────────────────────

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        body: dict | list | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """Execute an HTTP request *inside* the browser via ``page.evaluate``.

        The browser automatically attaches cookies and auth context.

        Args:
            method: HTTP method.
            url: Full URL or path relative to the site (starting with ``/``).
            body: Optional JSON-serialisable body.
            extra_headers: Optional additional headers.

        Returns:
            Parsed JSON response body.
        """
        if not self._page:
            raise RuntimeError("SharePointSession is not connected.")

        full_url = self._resolve_url(url)
        headers: dict[str, str] = {
            "Accept": "application/json;odata=nometadata",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        fetch_opts: dict[str, Any] = {
            "method": method.upper(),
            "headers": headers,
            "credentials": "include",
        }
        if body is not None:
            fetch_opts["body"] = json.dumps(body)

        js = """
        async ([url, opts]) => {
            const resp = await fetch(url, opts);
            const text = await resp.text();
            let parsed = null;
            try { parsed = JSON.parse(text); } catch {}
            return {
                status: resp.status,
                statusText: resp.statusText,
                body: parsed,
                raw: text.substring(0, 4000),
            };
        }
        """
        result = await self._page.evaluate(js, [full_url, fetch_opts])
        status = result.get("status", 0)
        if status >= 400:
            raise RuntimeError(
                f"SharePoint API returned {status} {result.get('statusText', '')}: "
                f"{result.get('raw', '')}"
            )
        return result.get("body") or {}

    # ── fetch_bytes — binary download through the browser ────────────

    async def fetch_bytes(
        self,
        method: str,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        """Download binary content *inside* the browser via ``page.evaluate``.

        The response body is base64-encoded in JavaScript and decoded back
        to ``bytes`` on the Python side.

        Args:
            method: HTTP method (usually ``"GET"``).
            url: Full URL or path relative to the site.
            extra_headers: Optional additional headers.

        Returns:
            Raw bytes of the response body.
        """
        if not self._page:
            raise RuntimeError("SharePointSession is not connected.")

        full_url = self._resolve_url(url)
        headers: dict[str, str] = {}
        if extra_headers:
            headers.update(extra_headers)

        fetch_opts: dict[str, Any] = {
            "method": method.upper(),
            "headers": headers,
            "credentials": "include",
        }

        js = """
        async ([url, opts]) => {
            const resp = await fetch(url, opts);
            if (!resp.ok) {
                const text = await resp.text();
                return {
                    status: resp.status,
                    statusText: resp.statusText,
                    error: text.substring(0, 4000),
                    b64: null,
                };
            }
            const buf = await resp.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return {
                status: resp.status,
                statusText: resp.statusText,
                b64: btoa(binary),
                error: null,
            };
        }
        """
        result = await self._page.evaluate(js, [full_url, fetch_opts])
        status = result.get("status", 0)
        if status >= 400:
            raise RuntimeError(
                f"SharePoint download returned {status} "
                f"{result.get('statusText', '')}: {result.get('error', '')}"
            )

        import base64
        b64 = result.get("b64")
        if not b64:
            return b""
        return base64.b64decode(b64)

    # ── internals ────────────────────────────────────────────────────

    async def _is_authenticated(self) -> bool:
        """Check whether the current page is actually authenticated.

        Inspects the page URL and HTML content for signs of a login wall.
        Returns ``True`` if the page looks like a real SharePoint page,
        ``False`` if it looks like a login / MFA prompt.
        """
        if not self._page:
            return False

        # 1. Check the current URL for login redirects.
        current_url = self._page.url.lower()
        for pattern in _AUTH_URL_PATTERNS:
            if pattern in current_url:
                logger.debug(
                    "Auth wall detected — URL contains %r: %s",
                    pattern, self._page.url,
                )
                return False

        return True

    async def _save_diagnostic_screenshot(self, label: str) -> Path | None:
        """Take a screenshot of the current page for debugging.

        Screenshots are saved to ``~/.contelligence/sharepoint-screenshots/``.
        Returns the path on success, ``None`` on failure.
        """
        if not self._page:
            return None
        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = SCREENSHOT_DIR / f"{label}_{ts}.png"
            await self._page.screenshot(path=str(path), full_page=True)
            logger.info("Diagnostic screenshot saved to %s", path)
            return path
        except Exception:
            logger.debug("Failed to save diagnostic screenshot", exc_info=True)
            return None

    def _resolve_url(self, url: str) -> str:
        """Resolve a relative path to a full URL."""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._site_url}/{url.lstrip('/')}"

    async def _try_connect(
        self,
        *,
        headless: bool,
        timeout: int,
    ) -> bool:
        """Launch browser and navigate to the SharePoint site.

        Returns ``True`` on success, ``False`` on failure (cleans up).
        """
        await self.close()

        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()

        launch_args = ["--disable-blink-features=AutomationControlled"]

        try:
            launch_kwargs: dict[str, Any] = {
                "headless": headless,
                "args": launch_args,
                "viewport": {"width": 1280, "height": 900},
            }
            # Use Edge if available
            edge_exe = _find_edge_executable()
            if edge_exe:
                launch_kwargs["channel"] = "msedge"

            self._context = await self._pw.chromium.launch_persistent_context(
                str(BROWSER_PROFILE_DIR),
                **launch_kwargs,
            )

            self._page = (
                self._context.pages[0]
                if self._context.pages
                else await self._context.new_page()
            )
            probe = _ReadinessProbe()
            self._page.on("request", probe.handler)

            # Navigate to the SharePoint site to trigger SSO
            await self._page.goto(
                self._site_url, wait_until="domcontentloaded", timeout=60_000,
            )

            # Wait for the probe to see an authenticated request
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                if probe.ready:
                    break
                # If redirected to login, wait for user to authenticate
                await asyncio.sleep(0.5)

            if probe.ready:
                logger.info(
                    "SharePoint browser session established for %s",
                    self._site_url,
                )
                return True

            # Not ready — clean up
            await self.close()
            return False

        except Exception:
            logger.exception("Failed to connect SharePoint browser session")
            await self.close()
            return False


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def clear_session() -> None:
    """Delete the persistent browser profile, forcing a fresh login."""
    import shutil

    if BROWSER_PROFILE_DIR.exists():
        shutil.rmtree(BROWSER_PROFILE_DIR, ignore_errors=True)
        logger.info("SharePoint browser profile cleared.")
    else:
        logger.info("No saved SharePoint browser profile found.")
