"""Tool for browsing the web and interacting with pages using Playwright.

Launches Microsoft Edge with a dedicated browser profile so that the tool
works even when Edge is already running.  On first launch, cookies and
local-storage are copied from the real Edge profile so that existing logins
carry over.  The browser stays open between calls so calling code can
inspect the page; use action='close' to shut it down explicitly.

Supports navigating to URLs, clicking elements, filling form fields,
selecting options, checking checkboxes, taking screenshots, and extracting
page content.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistent browser session state
# ---------------------------------------------------------------------------

_playwright_instance: Any = None
_browser_context: Any = None
_active_page: Any = None


# ---------------------------------------------------------------------------
# Edge profile directory helpers
# ---------------------------------------------------------------------------

def _edge_source_profile_dir() -> Path:
    """Return the real Edge user-data directory for the current OS."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Microsoft Edge"
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data"
    return Path.home() / ".config/microsoft-edge"


def _contelligence_profile_dir() -> Path:
    """Return the dedicated profile directory used by this tool.

    Lives under ``~/.contelligence/browser-profile`` so it never
    conflicts with a running Edge instance.
    """
    return Path.home() / ".contelligence" / "browser-profile"


def _seed_profile_from_edge(dest: Path) -> None:
    """Copy cookies, local-storage, and login-state from the real Edge profile.

    Only the files needed to preserve authentication are copied — the full
    profile (caches, GPUCache, extensions, etc.) is intentionally skipped to
    keep the dedicated profile lightweight and avoid lock-file conflicts.
    """
    source = _edge_source_profile_dir()
    # Edge stores per-profile data under a sub-folder, typically "Default".
    source_default = source / "Default"
    dest_default = dest / "Default"

    if not source_default.exists():
        logger.warning("Edge source profile not found at %s — skipping seed", source_default)
        return

    dest_default.mkdir(parents=True, exist_ok=True)

    # Files/directories that carry authentication state.
    targets = [
        "Cookies",
        "Cookies-journal",
        "Login Data",
        "Login Data-journal",
        "Local Storage",
        "Session Storage",
        "Web Data",
        "Web Data-journal",
        "Preferences",
    ]

    for name in targets:
        src = source_default / name
        dst = dest_default / name
        if not src.exists():
            continue
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            logger.debug("Seeded %s from Edge profile", name)
        except OSError as exc:
            # Non-fatal — Edge may hold a lock on some journal files.
            logger.debug("Could not copy %s: %s", name, exc)

    # Copy top-level "Local State" (encryption keys for cookies, etc.).
    local_state = source / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, dest / "Local State")
        except OSError as exc:
            logger.debug("Could not copy Local State: %s", exc)

    logger.info("Seeded browser profile from Edge at %s", source)


def _default_edge_executable() -> str | None:
    """Return the default Edge executable path, or None to let Playwright find it."""
    system = platform.system()
    if system == "Darwin":
        path = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        return path if Path(path).exists() else None
    if system == "Windows":
        for candidate in (
            Path(os.environ.get("PROGRAMFILES(X86)", ""))
            / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", ""))
            / "Microsoft/Edge/Application/msedge.exe",
        ):
            if candidate.exists():
                return str(candidate)
        return None
    # Linux
    for name in ("microsoft-edge-stable", "microsoft-edge"):
        import shutil
        if shutil.which(name):
            return name
    return None


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

class BrowseWebParams(BaseModel):
    """Parameters for the browse_web tool."""

    action: Literal[
        "navigate",
        "click",
        "fill",
        "select",
        "check",
        "uncheck",
        "screenshot",
        "get_text",
        "get_html",
        "wait",
        "hover",
        "press_key",
        "scroll",
        "close",
    ] = Field(
        description=(
            "Action to perform on the page:\n"
            "- 'navigate': go to a URL\n"
            "- 'click': click an element matched by selector\n"
            "- 'fill': type text into an input/textarea\n"
            "- 'select': choose an option from a <select> dropdown\n"
            "- 'check': check a checkbox or radio button\n"
            "- 'uncheck': uncheck a checkbox\n"
            "- 'screenshot': capture a screenshot of the page or element\n"
            "- 'get_text': extract visible text from the page or element\n"
            "- 'get_html': extract the HTML of the page or element\n"
            "- 'wait': wait for a selector to appear\n"
            "- 'hover': hover over an element\n"
            "- 'press_key': press a keyboard key (e.g. 'Enter', 'Tab')\n"
            "- 'scroll': scroll the page (direction: 'up' or 'down')\n"
            "- 'close': close the browser session"
        ),
    )
    url: str | None = Field(
        default=None,
        description="URL to navigate to. Required for action='navigate'.",
    )
    selector: str | None = Field(
        default=None,
        description=(
            "CSS or Playwright selector targeting the element to interact with. "
            "Required for click, fill, select, check, uncheck, hover, and optional "
            "for screenshot/get_text/get_html (omit to target the full page). "
            "Supports Playwright selectors like 'text=Submit', 'role=button[name=\"Save\"]', "
            "'label=Email', '#id', '.class', etc."
        ),
    )
    value: str | None = Field(
        default=None,
        description=(
            "Value to use for the action. "
            "For 'fill': the text to type. "
            "For 'select': the option value or label. "
            "For 'press_key': the key to press (e.g. 'Enter', 'Tab', 'Escape'). "
            "For 'scroll': direction 'up' or 'down'."
        ),
    )
    timeout: int = Field(
        default=60000,
        description="Timeout in milliseconds for the action.",
    )
    headless: bool = Field(
        default=False,
        description=(
            "Whether to run Edge in headless mode. Defaults to False "
            "(visible browser) for interactive user-profile sessions."
        ),
    )
    user_data_dir: str | None = Field(
        default=None,
        description=(
            "Path to a custom user-data directory for the browser session. "
            "Omit to use the dedicated contelligence profile at "
            "~/.contelligence/browser-profile (seeded from Edge on first run)."
        ),
    )

async def _ensure_browser(params: BrowseWebParams) -> None:
    """Start the persistent browser session if not already running."""
    global _playwright_instance, _browser_context, _active_page

    if _browser_context is not None and _active_page is not None:
        # Session already alive — check the page is still usable.
        try:
            await _active_page.title()
            return
        except Exception:
            logger.warning("Existing browser page is stale, relaunching")
            await _close_browser()

    from playwright.async_api import async_playwright

    # Use a dedicated profile directory so the tool works even when
    # Edge is already running (Edge locks its own profile directory).
    if params.user_data_dir:
        profile_dir = Path(params.user_data_dir)
    else:
        profile_dir = _contelligence_profile_dir()

    # Seed the profile from the real Edge profile on first run.
    if not profile_dir.exists():
        profile_dir.mkdir(parents=True, exist_ok=True)
        _seed_profile_from_edge(profile_dir)

    # Remove stale Chromium singleton lock files left by a previous
    # session that didn't shut down cleanly.
    for lock_file in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        lock_path = profile_dir / lock_file
        if lock_path.exists() or lock_path.is_symlink():
            try:
                lock_path.unlink()
                logger.debug("Removed stale lock file: %s", lock_path)
            except OSError as exc:
                logger.debug("Could not remove %s: %s", lock_path, exc)

    edge_exec = _default_edge_executable()

    pw = await async_playwright().start()
    _playwright_instance = pw

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--hide-crash-restore-bubble",
    ]

    _browser_context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=params.headless,
        executable_path=edge_exec,
        channel="msedge",
        args=launch_args,
        timeout=params.timeout,
        ignore_default_args=["--enable-automation"],
    )

    # Close every about:blank / startup-restored tab that Edge
    # opens automatically, then create one clean page.
    for extra in _browser_context.pages:
        await extra.close()
    _active_page = await _browser_context.new_page()
    logger.info("Browser session started (profile: %s)", profile_dir)


async def _close_browser() -> dict[str, Any]:
    """Tear down the persistent browser session."""
    global _playwright_instance, _browser_context, _active_page
    try:
        if _browser_context is not None:
            await _browser_context.close()
    except Exception as exc:
        logger.debug("Error closing browser context: %s", exc)
    try:
        if _playwright_instance is not None:
            await _playwright_instance.stop()
    except Exception as exc:
        logger.debug("Error stopping playwright: %s", exc)
    _active_page = None
    _browser_context = None
    _playwright_instance = None
    logger.info("Browser session closed")
    return {"action": "close", "status": "closed"}

# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@define_tool(
    name="browse_web",
    description=(
        "Browse the web interactively using Microsoft Edge with the user's "
        "profile preserved (logins, cookies, extensions). "
        "Supports multiple actions: navigate to a URL, click buttons and "
        "links, fill form fields, select dropdown options, check/uncheck "
        "checkboxes, hover over elements, press keyboard keys, scroll the "
        "page, wait for dynamic content, take screenshots, and extract "
        "text or HTML from the page. "
        "Use Playwright selectors to target elements: CSS selectors, "
        "text=, role=, label=, placeholder=, etc. "
        "Call this tool multiple times in sequence to perform multi-step "
        "browser workflows."
    ),
    parameters_model=BrowseWebParams,
)
async def browse_web(params: BrowseWebParams, context: dict) -> dict[str, Any]:
    """Launch Edge (or reuse the existing session) and perform the requested action."""
    try:
        if params.action == "close":
            return await _close_browser()

        await _ensure_browser(params)
        return await _execute_action(_active_page, params)

    except Exception as exc:
        logger.exception("browse_web action=%s failed", params.action)
        return {"error": str(exc), "action": params.action}


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

async def _execute_action(page: Any, params: BrowseWebParams) -> dict[str, Any]:
    """Dispatch and execute the requested browser action."""

    if params.action == "navigate":
        if not params.url:
            return {"error": "The 'url' parameter is required for action='navigate'."}
        response = await page.goto(params.url, wait_until="commit", timeout=params.timeout)
        # Wait for a reasonable loaded state, but don't fail if the page
        # is still loading background resources after the commit.
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=params.timeout)
        except Exception:
            logger.debug("domcontentloaded not reached for %s, continuing", params.url)
        title = await page.title()
        content = await page.content()
        return {
            "action": "navigate",
            "url": page.url,
            "title": title,
            "content": content,
            "status": response.status if response else None,
        }

    if params.action == "click":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='click'."}
        await page.click(params.selector, timeout=params.timeout)
        await page.wait_for_load_state("domcontentloaded")
        title = await page.title()
        return {
            "action": "click",
            "selector": params.selector,
            "title": title,
            "url": page.url,
        }

    if params.action == "fill":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='fill'."}
        if params.value is None:
            return {"error": "The 'value' parameter is required for action='fill'."}
        await page.fill(params.selector, params.value, timeout=params.timeout)
        return {
            "action": "fill",
            "selector": params.selector,
            "value": params.value,
        }

    if params.action == "select":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='select'."}
        if params.value is None:
            return {"error": "The 'value' parameter is required for action='select'."}
        selected = await page.select_option(params.selector, params.value, timeout=params.timeout)
        return {
            "action": "select",
            "selector": params.selector,
            "selected": selected,
        }

    if params.action == "check":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='check'."}
        await page.check(params.selector, timeout=params.timeout)
        return {"action": "check", "selector": params.selector}

    if params.action == "uncheck":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='uncheck'."}
        await page.uncheck(params.selector, timeout=params.timeout)
        return {"action": "uncheck", "selector": params.selector}

    if params.action == "hover":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='hover'."}
        await page.hover(params.selector, timeout=params.timeout)
        return {"action": "hover", "selector": params.selector}

    if params.action == "press_key":
        if params.value is None:
            return {"error": "The 'value' parameter is required for action='press_key'."}
        if params.selector:
            await page.press(params.selector, params.value, timeout=params.timeout)
        else:
            await page.keyboard.press(params.value)
        return {
            "action": "press_key",
            "key": params.value,
            "selector": params.selector,
        }

    if params.action == "scroll":
        direction = (params.value or "down").lower()
        delta = -500 if direction == "up" else 500
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(0.3)
        return {"action": "scroll", "direction": direction}

    if params.action == "wait":
        if not params.selector:
            return {"error": "The 'selector' parameter is required for action='wait'."}
        await page.wait_for_selector(params.selector, timeout=params.timeout)
        return {"action": "wait", "selector": params.selector, "found": True}

    if params.action == "screenshot":
        if params.selector:
            element = await page.query_selector(params.selector)
            if not element:
                return {"error": f"Element not found: {params.selector}"}
            screenshot_bytes = await element.screenshot()
        else:
            screenshot_bytes = await page.screenshot(full_page=True)

        import base64
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("ascii")
        return {
            "action": "screenshot",
            "selector": params.selector,
            "format": "png",
            "encoding": "base64",
            "size_bytes": len(screenshot_bytes),
            "data": screenshot_b64,
        }

    if params.action == "get_text":
        if params.selector:
            element = await page.query_selector(params.selector)
            if not element:
                return {"error": f"Element not found: {params.selector}"}
            text = await element.inner_text()
        else:
            text = await page.evaluate("() => document.body.innerText")
        title = await page.title()
        return {
            "action": "get_text",
            "selector": params.selector,
            "title": title,
            "url": page.url,
            "text": text,
        }

    if params.action == "get_html":
        if params.selector:
            element = await page.query_selector(params.selector)
            if not element:
                return {"error": f"Element not found: {params.selector}"}
            html = await element.inner_html()
        else:
            html = await page.content()
        return {
            "action": "get_html",
            "selector": params.selector,
            "url": page.url,
            "html": html,
        }

    return {"error": f"Unknown action: {params.action}"}
