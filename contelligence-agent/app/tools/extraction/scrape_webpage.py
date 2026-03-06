"""Tool for scraping and extracting content from web pages."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.tool_registry import define_tool

logger = logging.getLogger(__name__)


class ScrapeWebpageParams(BaseModel):
    """Parameters for the scrape_webpage tool."""

    url: str = Field(..., description="The URL to scrape.")
    wait_for: str | None = Field(
        None,
        description=(
            "CSS selector to wait for before scraping. "
            "Use if the page loads content dynamically."
        ),
    )
    extract_links: bool = Field(
        False,
        description="Whether to extract all links on the page.",
    )


@define_tool(
    name="scrape_webpage",
    description=(
        "Scrape and extract content from a web page. Returns the page text, "
        "title, metadata, and optionally all links. Use wait_for with a CSS "
        "selector if the page loads content dynamically."
    ),
    parameters_model=ScrapeWebpageParams,
)
async def scrape_webpage(
    params: ScrapeWebpageParams, context: dict
) -> dict[str, Any]:
    """Launch a headless browser, navigate to the URL, and extract content."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            logger.info("Navigating to %s", params.url)
            await page.goto(params.url, wait_until="domcontentloaded", timeout=30_000)

            if params.wait_for:
                logger.info("Waiting for selector: %s", params.wait_for)
                await page.wait_for_selector(params.wait_for, timeout=15_000)

            title = await page.title()
            text = await page.evaluate("() => document.body.innerText")

            # Metadata
            description = await page.evaluate(
                '() => document.querySelector(\'meta[name="description"]\')?.content || ""'
            )
            keywords = await page.evaluate(
                '() => document.querySelector(\'meta[name="keywords"]\')?.content || ""'
            )

            # Links
            links: list[dict[str, str]] = []
            if params.extract_links:
                raw_links = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    }))"""
                )
                links = [lnk for lnk in raw_links if lnk.get("href")]

            await browser.close()

            return {
                "url": params.url,
                "title": title,
                "text": text,
                "links": links,
                "metadata": {
                    "description": description,
                    "keywords": keywords,
                },
            }

    except Exception as exc:
        logger.exception("scrape_webpage failed for %s", params.url)
        return {"error": str(exc), "url": params.url}
