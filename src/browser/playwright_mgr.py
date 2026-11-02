"""Async Playwright browser manager with per-country geo-proxy routing, stealth headers, and visual audit capture."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import RadarSettings
from src.browser.dom_actions import DOMActionRunner

logger = logging.getLogger(__name__)

STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4] });
"""

BLOCKED_TRACKER_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "connect.facebook.net",
    "hotjar.com",
    "clarity.ms",
    "tiktok.com/i18n/pixel",
)


def _slugify_token(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_") or "unknown"


@dataclass
class ScrapedPageArtifact:
    """Container for raw scraped DOM HTML and visual audit trail paths."""

    country_iso: str
    operator: str
    segment: str
    requested_url: str
    final_url: str
    http_status: Optional[int]
    html_content: str
    screenshot_path: Path
    captured_at: datetime
    executed_actions: List[str] = field(default_factory=list)


class AsyncPlaywrightManager:
    """Manages headless Chromium lifecycle, per-country geo-proxy contexts, and full-page screenshot audit captures."""

    def __init__(
        self,
        settings: RadarSettings,
        action_runner: Optional[DOMActionRunner] = None,
    ) -> None:
        self.settings = settings
        self.action_runner = action_runner or DOMActionRunner()
        self._playwright: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> "AsyncPlaywrightManager":
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.playwright_headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1440,900",
            ],
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def build_audit_file_stem(
        self,
        run_date: date,
        country_iso: str,
        operator: str,
        segment: str,
        url: str,
    ) -> Path:
        """Build deterministic directory and file stem for visual audit trail (.png and .md)."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        target_dir = (
            self.settings.audit_trail_dir
            / run_date.isoformat()
            / country_iso.upper()
            / _slugify_token(operator)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{_slugify_token(segment)}_{url_hash}"

    async def scrape_url(
        self,
        url: str,
        country_iso: str,
        operator: str,
        segment: str,
        run_date: date,
        pre_scrape_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> ScrapedPageArtifact:
        """
        Scrape a single telecom URL using a geo-routed stealth browser context,
        run pre-scrape DOM playbooks, and save a full-page PNG screenshot.
        """
        if self._browser is None:
            raise RuntimeError("AsyncPlaywrightManager must be entered via 'async with' before scraping.")

        profile = self.settings.get_browser_profile(country_iso)
        proxy_config = self.settings.get_proxy_for_country(country_iso)

        context_kwargs: Dict[str, Any] = {
            "user_agent": STEALTH_USER_AGENT,
            "viewport": {"width": 1440, "height": 900},
            "locale": profile["locale"],
            "timezone_id": profile["timezone_id"],
            "geolocation": profile["geolocation"],
            "permissions": ["geolocation"],
            "ignore_https_errors": True,
            "extra_http_headers": {
                "Accept-Language": profile["accept_language"],
                "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
            },
        }
        if proxy_config:
            context_kwargs["proxy"] = proxy_config
            logger.info(
                "[%s/%s] Using geo-proxy server %s",
                country_iso,
                operator,
                proxy_config.get("server"),
            )

        context = await self._browser.new_context(**context_kwargs)
        await context.add_init_script(STEALTH_INIT_SCRIPT)

        async def _route_interceptor(route: Any) -> None:
            req_url = route.request.url.lower()
            if any(domain in req_url for domain in BLOCKED_TRACKER_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _route_interceptor)
        page = await context.new_page()

        http_status: Optional[int] = None
        try:
            logger.info("[%s | %s | %s] Navigating to %s", country_iso, operator, segment, url)
            try:
                response = await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=self.settings.playwright_timeout_ms,
                )
            except Exception:
                # Telecom SPAs frequently keep live-chat sockets open; gracefully fall back to domcontentloaded
                logger.debug(
                    "[%s/%s] networkidle timed out on %s; retrying with domcontentloaded + settle.",
                    country_iso,
                    operator,
                    url,
                )
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.playwright_timeout_ms,
                )
                await page.wait_for_timeout(3500)

            if response is not None:
                http_status = response.status

            # Allow client-side React/Angular/Vue offer cards to hydrate
            await page.wait_for_timeout(1800)

            executed_actions = await self.action_runner.run_playbook(
                page=page,
                actions=pre_scrape_actions,
            )

            audit_stem = self.build_audit_file_stem(
                run_date=run_date,
                country_iso=country_iso,
                operator=operator,
                segment=segment,
                url=url,
            )
            screenshot_path = audit_stem.with_suffix(".png")
            await page.screenshot(path=str(screenshot_path), full_page=True, type="png")

            html_content = await page.content()
            final_url = page.url

            return ScrapedPageArtifact(
                country_iso=country_iso.upper(),
                operator=operator,
                segment=segment,
                requested_url=url,
                final_url=final_url,
                http_status=http_status,
                html_content=html_content,
                screenshot_path=screenshot_path,
                captured_at=datetime.now(timezone.utc),
                executed_actions=executed_actions,
            )
        finally:
            await context.close()
