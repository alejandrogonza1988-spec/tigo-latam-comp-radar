"""Browser automation and pre-scrape DOM playbook execution package."""

from src.browser.dom_actions import DEFAULT_ACCORDION_PATTERN, DOMActionRunner
from src.browser.playwright_mgr import AsyncPlaywrightManager, ScrapedPageArtifact

__all__ = [
    "AsyncPlaywrightManager",
    "DOMActionRunner",
    "DEFAULT_ACCORDION_PATTERN",
    "ScrapedPageArtifact",
]
