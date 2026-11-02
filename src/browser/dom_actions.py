"""Pre-scrape DOM playbooks: Colombia Bogotá Estrato 3 selector, cookie banners, and accordion expansion."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Mandatory regex for automatic expansion of offer details, VAS terms, and legal conditions
DEFAULT_ACCORDION_PATTERN = r"(ver detalle|más info|mas info|términos|terminos|incluye|beneficios|condiciones)"


class DOMActionRunner:
    """Executes declarative pre-scrape DOM playbooks before HTML & screenshot capture."""

    COOKIE_SELECTORS: List[str] = [
        "#onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button[id*='accept-cookie' i]",
        "button[class*='cookie-accept' i]",
        "button:has-text('Aceptar todas')",
        "button:has-text('Aceptar cookies')",
        "button:has-text('Aceptar')",
        "button:has-text('Entendido')",
    ]

    CONFIRM_CTA_SELECTORS: List[str] = [
        "button:has-text('Confirmar')",
        "button:has-text('Continuar')",
        "button:has-text('Guardar')",
        "button:has-text('Ver planes')",
        "button:has-text('Ver ofertas')",
        "button:has-text('Aplicar')",
        "button:has-text('Consultar')",
    ]

    def __init__(self, max_accordion_clicks: int = 35) -> None:
        self.max_accordion_clicks = max_accordion_clicks

    async def run_playbook(
        self,
        page: "Page",
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Execute an ordered list of DOM actions on a loaded Playwright page.

        Always guarantees accordion/detail expansion runs if no explicit actions are supplied.
        Returns an execution audit log of actions performed.
        """
        executed_steps: List[str] = []
        playbook = actions if actions else [
            {"action": "dismiss_cookies"},
            {"action": "scroll_lazy_content"},
            {"action": "expand_accordions", "regex_pattern": DEFAULT_ACCORDION_PATTERN},
        ]

        has_accordion_step = any(step.get("action") == "expand_accordions" for step in playbook)
        if not has_accordion_step:
            playbook = list(playbook) + [
                {"action": "expand_accordions", "regex_pattern": DEFAULT_ACCORDION_PATTERN}
            ]

        for step in playbook:
            action_name = str(step.get("action", "")).strip().lower()
            try:
                if action_name == "dismiss_cookies":
                    dismissed = await self.dismiss_cookie_banners(page)
                    executed_steps.append(f"dismiss_cookies(clicked={dismissed})")

                elif action_name == "select_colombia_city_stratum":
                    city = str(step.get("city", "Bogotá"))
                    stratum = str(step.get("stratum", "Estrato 3"))
                    applied = await self.select_colombia_city_stratum(page, city=city, stratum=stratum)
                    executed_steps.append(
                        f"select_colombia_city_stratum(city={city}, stratum={stratum}, applied={applied})"
                    )

                elif action_name == "scroll_lazy_content":
                    await self.scroll_lazy_content(page)
                    executed_steps.append("scroll_lazy_content(done)")

                elif action_name == "expand_accordions":
                    pattern = str(step.get("regex_pattern") or DEFAULT_ACCORDION_PATTERN)
                    expanded_count = await self.expand_accordions(page, regex_pattern=pattern)
                    executed_steps.append(f"expand_accordions(expanded={expanded_count})")

                elif action_name == "click_selector":
                    selector = step.get("selector")
                    if selector:
                        locator = page.locator(str(selector)).first
                        if await locator.count() > 0 and await locator.is_visible():
                            await locator.click(timeout=3000)
                            await page.wait_for_timeout(500)
                            executed_steps.append(f"click_selector({selector})")

                elif action_name == "select_option":
                    selector = step.get("selector")
                    label = step.get("label")
                    if selector and label:
                        locator = page.locator(str(selector)).first
                        if await locator.count() > 0:
                            await locator.select_option(label=str(label), timeout=3000)
                            await page.wait_for_timeout(500)
                            executed_steps.append(f"select_option({selector}={label})")

                elif action_name == "wait_ms":
                    duration = int(step.get("duration_ms", 1000))
                    await page.wait_for_timeout(duration)
                    executed_steps.append(f"wait_ms({duration})")

            except Exception as exc:
                logger.debug("Non-fatal pre-scrape DOM action '%s' warning: %s", action_name, exc)
                executed_steps.append(f"{action_name}(skipped:{type(exc).__name__})")

        return executed_steps

    async def dismiss_cookie_banners(self, page: "Page") -> bool:
        """Attempt to dismiss cookie consent overlays so they do not obscure screenshots or modals."""
        for selector in self.COOKIE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.click(timeout=2000)
                    await page.wait_for_timeout(350)
                    return True
            except Exception:
                continue
        return False

    async def select_colombia_city_stratum(
        self,
        page: "Page",
        city: str = "Bogotá",
        stratum: str = "Estrato 3",
    ) -> bool:
        """
        Handle Colombian telco location & socioeconomic stratum gating (Tigo CO, Claro CO, Movistar CO, ETB, WOM).

        Selects Bogotá / Bogotá D.C. and Estrato 3 when a location modal or inline selector is rendered.
        """
        interacted = False
        stratum_digit_match = re.search(r"(\d+)", stratum)
        stratum_digit = stratum_digit_match.group(1) if stratum_digit_match else "3"
        city_variants = [city, "Bogotá D.C.", "BOGOTA", "Bogota", "Bogotá, D.C."]
        stratum_variants = [stratum, f"Estrato {stratum_digit}", stratum_digit]

        # 1. Check if there is a city/location trigger button in header/banner that opens the modal
        location_triggers = [
            "button[class*='city' i]",
            "button[class*='ubicacion' i]",
            "button[class*='location' i]",
            "[data-testid*='city' i]",
            "a:has-text('Cambiar ciudad')",
            "button:has-text('Selecciona tu ciudad')",
        ]
        for trigger_sel in location_triggers:
            try:
                trig = page.locator(trigger_sel).first
                if await trig.count() > 0 and await trig.is_visible():
                    text_val = (await trig.inner_text()).strip()
                    if city.lower() not in text_val.lower():
                        await trig.click(timeout=2000)
                        await page.wait_for_timeout(500)
                        break
            except Exception:
                continue

        # 2. Try native <select> elements for City / Municipio
        city_select_selectors = [
            "select[name*='ciudad' i]",
            "select[id*='ciudad' i]",
            "select[name*='city' i]",
            "select[id*='city' i]",
            "select[name*='municipio' i]",
            "select[aria-label*='ciudad' i]",
        ]
        for sel in city_select_selectors:
            try:
                select_loc = page.locator(sel).first
                if await select_loc.count() > 0 and await select_loc.is_visible():
                    for variant in city_variants:
                        try:
                            await select_loc.select_option(label=variant, timeout=1500)
                            interacted = True
                            await page.wait_for_timeout(400)
                            break
                        except Exception:
                            continue
                    if interacted:
                        break
            except Exception:
                continue

        # 3. Try autocomplete text inputs for City / Municipio
        if not interacted:
            city_input_selectors = [
                "input[placeholder*='ciudad' i]",
                "input[placeholder*='municipio' i]",
                "input[aria-label*='ciudad' i]",
                "input[name*='ciudad' i]",
                "input[id*='city' i]",
            ]
            for sel in city_input_selectors:
                try:
                    inp = page.locator(sel).first
                    if await inp.count() > 0 and await inp.is_visible():
                        await inp.click(timeout=1500)
                        await inp.fill(city, timeout=1500)
                        await page.wait_for_timeout(600)
                        suggestion = page.locator(
                            f"[role='option']:has-text('{city}'), li:has-text('{city}')"
                        ).first
                        if await suggestion.count() > 0 and await suggestion.is_visible():
                            await suggestion.click(timeout=1500)
                        else:
                            await inp.press("Enter")
                        interacted = True
                        await page.wait_for_timeout(400)
                        break
                except Exception:
                    continue

        # 4. Try native <select> elements for Estrato
        stratum_selected = False
        stratum_select_selectors = [
            "select[name*='estrato' i]",
            "select[id*='estrato' i]",
            "select[aria-label*='estrato' i]",
            "select[name*='stratum' i]",
        ]
        for sel in stratum_select_selectors:
            try:
                select_loc = page.locator(sel).first
                if await select_loc.count() > 0 and await select_loc.is_visible():
                    for variant in stratum_variants:
                        try:
                            await select_loc.select_option(label=variant, timeout=1500)
                            stratum_selected = True
                            interacted = True
                            await page.wait_for_timeout(400)
                            break
                        except Exception:
                            try:
                                await select_loc.select_option(value=stratum_digit, timeout=1500)
                                stratum_selected = True
                                interacted = True
                                await page.wait_for_timeout(400)
                                break
                            except Exception:
                                continue
                    if stratum_selected:
                        break
            except Exception:
                continue

        # 5. Try clickable Estrato pills / radio buttons (e.g. "Estrato 3" or button "3" inside estrato group)
        if not stratum_selected:
            pill_selectors = [
                f"button:has-text('{stratum}')",
                f"label:has-text('{stratum}')",
                f"[role='radio']:has-text('{stratum}')",
                f"[class*='estrato' i] button:text-is('{stratum_digit}')",
                f"[class*='stratum' i] button:text-is('{stratum_digit}')",
                f"[id*='estrato' i] label:text-is('{stratum_digit}')",
            ]
            for sel in pill_selectors:
                try:
                    pill = page.locator(sel).first
                    if await pill.count() > 0 and await pill.is_visible():
                        await pill.click(timeout=1500)
                        interacted = True
                        await page.wait_for_timeout(350)
                        break
                except Exception:
                    continue

        # 6. Confirm / Submit location modal if we interacted with city or stratum controls
        if interacted:
            for cta_sel in self.CONFIRM_CTA_SELECTORS:
                try:
                    cta = page.locator(cta_sel).first
                    if await cta.count() > 0 and await cta.is_visible():
                        await cta.click(timeout=2000)
                        await page.wait_for_timeout(900)
                        break
                except Exception:
                    continue

        return interacted

    async def scroll_lazy_content(self, page: "Page", step_px: int = 750, max_steps: int = 12) -> None:
        """Scroll incrementally through the page to trigger lazy-loaded plan cards and OTT icons."""
        try:
            total_height = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
            current_y = 0
            steps = 0
            while current_y < total_height and steps < max_steps:
                current_y += step_px
                await page.evaluate(f"window.scrollTo(0, {current_y})")
                await page.wait_for_timeout(200)
                total_height = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
                steps += 1
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(250)
        except Exception as exc:
            logger.debug("Scroll lazy content warning: %s", exc)

    async def expand_accordions(
        self,
        page: "Page",
        regex_pattern: str = DEFAULT_ACCORDION_PATTERN,
    ) -> int:
        """
        Automatically expand buttons, accordions, `<details>`, and non-navigating toggles
        whose visible text or aria-label matches `(ver detalle|más info|términos|incluye|beneficios|condiciones)`.
        """
        compiled_regex = re.compile(regex_pattern, re.IGNORECASE)
        expanded_total = 0

        # 1. Force open native <details> elements directly in DOM
        try:
            native_opened = await page.evaluate(
                """() => {
                    let count = 0;
                    document.querySelectorAll('details:not([open])').forEach(el => {
                        el.setAttribute('open', 'true');
                        count += 1;
                    });
                    return count;
                }"""
            )
            expanded_total += int(native_opened or 0)
        except Exception:
            pass

        # 2. Locate interactive elements matching the target regex without navigating away
        candidate_locator = page.locator(
            "button, summary, [role='button'], [aria-expanded='false'], "
            "a[href='#'], a[href^='javascript:'], a:not([href]), "
            "[class*='accordion' i], [class*='toggle' i], [data-bs-toggle='collapse']"
        )

        try:
            total_candidates = await candidate_locator.count()
        except Exception:
            total_candidates = 0

        clicks_performed = 0
        for idx in range(min(total_candidates, 150)):
            if clicks_performed >= self.max_accordion_clicks:
                break
            try:
                element = candidate_locator.nth(idx)
                if not await element.is_visible():
                    continue

                aria_expanded = await element.get_attribute("aria-expanded")
                if aria_expanded and aria_expanded.lower() == "true":
                    continue

                text_content = ((await element.inner_text()) or "").strip()
                aria_label = ((await element.get_attribute("aria-label")) or "").strip()
                combined_label = f"{text_content} {aria_label}".strip()

                # Avoid clicking huge wrapper containers; target concise CTA/accordion labels
                if not combined_label or len(combined_label) > 120:
                    continue

                if not compiled_regex.search(combined_label):
                    continue

                # Extra safety: skip anchors pointing to external URLs or different pages
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "a":
                    href = ((await element.get_attribute("href")) or "").strip()
                    if href and not href.startswith("#") and not href.lower().startswith("javascript:"):
                        continue

                await element.scroll_into_view_if_needed(timeout=1500)
                await element.click(timeout=1800)
                clicks_performed += 1
                expanded_total += 1
                await page.wait_for_timeout(200)
            except Exception:
                continue

        # 3. Unhide CSS-collapsed accordion bodies that already exist in DOM so screenshots & HTML show terms
        try:
            await page.evaluate(
                """() => {
                    const selectors = [
                        '.accordion-collapse.collapse',
                        '[class*="accordion-content"]',
                        '[class*="plan-details"][style*="display: none"]'
                    ];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            el.classList.add('show');
                        });
                    });
                }"""
            )
        except Exception:
            pass

        return expanded_total
