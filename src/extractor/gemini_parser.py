"""Gemini 2.5 Flash structured telecom offer parser enforcing temperature=0.0 and zero hallucination."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from google import genai
from google.genai import types

from config.settings import RadarSettings
from src.extractor.schemas import (
    LLMExtractionEnvelope,
    NormalizedOffer,
    PricingSpec,
    build_offer_uid,
)

logger = logging.getLogger(__name__)

STRICT_SYSTEM_INSTRUCTION = """You are a deterministic Telecom Commercial Data Extractor auditing Tigo (Millicom) and its Latin American competitors.

MANDATORY ZERO-HALLUCINATION GUARDRAILS (NO EXCEPTIONS):
1. STRICT FACTUALITY ONLY: Extract ONLY commercial plans, speeds, prices, hardware, tax flags, and Entertainment/Sports VAS addons that are EXPLICITLY written in the provided scraped DOM Markdown.
2. RETURN NULL WHEN ABSENT: If any field (`regular_monthly_price`, `promo_monthly_price`, `promo_duration_months`, `installation_fee`, `taxes_included`, `technology`, `symmetric_speed`, `download_mbps`, `upload_mbps`, `wifi_hardware`, `tv_channels_count`, `tv_deco_boxes`, `tier_or_package`, `free_months`, `promo_price`, `regular_price_after_promo`) is NOT explicitly visible in the text, you MUST return `null`.
3. NO CALCULATIONS OR INFERENCES:
   - NEVER estimate or calculate a regular price from a percentage discount unless the exact post-promo regular numeric price is literally printed in the DOM.
   - NEVER convert currencies or apply exchange rates. Always use the declared local currency code provided in the context.
   - NEVER assume `taxes_included` is true or false unless phrases like "IVA incluido" / "Impuestos incluidos" (`true`) or "+ IVA" / "más impuestos" / "sin impuestos" (`false`) appear verbatim.
   - NEVER assume `upload_mbps` equals `download_mbps` unless the upload speed number is explicitly printed OR the offer explicitly states "velocidad simétrica" / "fibra simétrica".
   - Convert "1 Gbps" / "1 Giga" to `1000` Mbps ONLY when "1 Gbps" / "1 Giga" / "1000 Mbps" is literally printed.
4. VERBATIM EVIDENCE REQUIRED:
   - `exact_terms_text` on every offer and every `EntertainmentVASAddon` MUST be copied verbatim from the scraped DOM Markdown.
5. VAS PROVIDER MAPPING:
   - Map Netflix -> NETFLIX; Disney+ / Star+ -> DISNEY_PLUS; Max / HBO Max -> MAX; Amazon Prime Video -> PRIME_VIDEO; Paramount+ -> PARAMOUNT_PLUS; ViX / ViX Premium -> VIX; Universal+ -> UNIVERSAL_PLUS; Apple TV+ -> APPLE_TV; Crunchyroll -> CRUNCHYROLL; Spotify -> SPOTIFY; Deezer -> DEEZER; Tigo Sports -> TIGO_SPORTS; Win Sports / Win+ Fútbol / Win Sports+ -> WIN_SPORTS; TNT Sports -> TNT_SPORTS; Flow / Flow Pass -> FLOW_PASS; any other explicit OTT/VAS -> OTHER.
"""


class GeminiOfferParser:
    """Calls `gemini-2.5-flash` via official `google-genai` SDK with `temperature=0.0` and strict `response_schema`."""

    def __init__(self, settings: RadarSettings, client: Optional[genai.Client] = None) -> None:
        if settings.gemini_temperature != 0.0:
            raise ValueError("Guardrail Violation: GeminiOfferParser requires temperature=0.0.")
        self.settings = settings
        self.model_name = settings.gemini_model
        self._client = client

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        if not self.settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is required for live extraction. "
                "Set GEMINI_API_KEY or run with --dry-run."
            )
        self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def build_extraction_prompt(
        self,
        markdown_text: str,
        country_iso: str,
        country_name: str,
        operator: str,
        segment: str,
        expected_currency: str,
        source_url: str,
    ) -> str:
        """Construct the context-bounded extraction prompt containing the cleaned DOM Markdown."""
        bounded_markdown = markdown_text[: self.settings.gemini_max_markdown_chars]
        return (
            f"### SCRAPE METADATA\n"
            f"- Country ISO: {country_iso} ({country_name})\n"
            f"- Operator: {operator}\n"
            f"- Target Segment: {segment}\n"
            f"- Local Currency Code (MUST USE THIS CURRENCY, DO NOT CONVERT): {expected_currency}\n"
            f"- Source URL: {source_url}\n\n"
            f"### INSTRUCTIONS\n"
            f"Extract every distinct commercial plan or standalone VAS entertainment offer visible in the "
            f"DOM Markdown below. If a field is not explicitly printed in the text, set it to `null`.\n\n"
            f"### CLEANED SCRAPED DOM MARKDOWN\n"
            f"```markdown\n{bounded_markdown}\n```"
        )

    def extract_offers_sync(
        self,
        markdown_text: str,
        country_iso: str,
        country_name: str,
        operator: str,
        segment: str,
        expected_currency: str,
        source_url: str,
        screenshot_path: Optional[str] = None,
        markdown_path: Optional[str] = None,
    ) -> List[NormalizedOffer]:
        """Synchronously invoke `client.models.generate_content` with `temperature=0.0` and `response_schema`."""
        if not markdown_text or len(markdown_text.strip()) < 20:
            logger.warning("[%s/%s/%s] Empty DOM Markdown; skipping LLM call.", country_iso, operator, segment)
            return []

        client = self._get_client()
        prompt = self.build_extraction_prompt(
            markdown_text=markdown_text,
            country_iso=country_iso,
            country_name=country_name,
            operator=operator,
            segment=segment,
            expected_currency=expected_currency,
            source_url=source_url,
        )

        gen_config = types.GenerateContentConfig(
            system_instruction=STRICT_SYSTEM_INSTRUCTION,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=LLMExtractionEnvelope,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.settings.gemini_max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=gen_config,
                )

                envelope: Optional[LLMExtractionEnvelope] = None
                if getattr(response, "parsed", None) is not None:
                    parsed_obj = response.parsed
                    if isinstance(parsed_obj, LLMExtractionEnvelope):
                        envelope = parsed_obj
                    elif isinstance(parsed_obj, dict):
                        envelope = LLMExtractionEnvelope.model_validate(parsed_obj)

                if envelope is None:
                    raw_json = (response.text or "").strip()
                    if not raw_json:
                        return []
                    envelope = LLMExtractionEnvelope.model_validate_json(raw_json)

                return self._normalize_extracted_items(
                    envelope=envelope,
                    country_iso=country_iso,
                    operator=operator,
                    segment=segment,
                    expected_currency=expected_currency,
                    source_url=source_url,
                    screenshot_path=screenshot_path,
                    markdown_path=markdown_path,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[%s/%s/%s] Gemini extraction attempt %d/%d failed: %s",
                    country_iso,
                    operator,
                    segment,
                    attempt,
                    self.settings.gemini_max_retries,
                    exc,
                )

        raise RuntimeError(
            f"Gemini extraction failed for {country_iso}/{operator}/{segment} after "
            f"{self.settings.gemini_max_retries} attempts: {last_error}"
        )

    async def extract_offers(
        self,
        markdown_text: str,
        country_iso: str,
        country_name: str,
        operator: str,
        segment: str,
        expected_currency: str,
        source_url: str,
        screenshot_path: Optional[str] = None,
        markdown_path: Optional[str] = None,
    ) -> List[NormalizedOffer]:
        """Async wrapper offloading synchronous SDK call cleanly to a worker thread."""
        return await asyncio.to_thread(
            self.extract_offers_sync,
            markdown_text=markdown_text,
            country_iso=country_iso,
            country_name=country_name,
            operator=operator,
            segment=segment,
            expected_currency=expected_currency,
            source_url=source_url,
            screenshot_path=screenshot_path,
            markdown_path=markdown_path,
        )

    @staticmethod
    def _normalize_extracted_items(
        envelope: LLMExtractionEnvelope,
        country_iso: str,
        operator: str,
        segment: str,
        expected_currency: str,
        source_url: str,
        screenshot_path: Optional[str],
        markdown_path: Optional[str],
    ) -> List[NormalizedOffer]:
        """Deterministically build Offer UIDs and deduplicate offers within the same page capture."""
        normalized_offers: List[NormalizedOffer] = []
        seen_uids: set[str] = set()

        for item in envelope.offers:
            dl_mbps = item.home_specs.download_mbps if item.home_specs else None
            deterministic_uid = build_offer_uid(
                country_iso=country_iso,
                operator=operator,
                segment=segment,
                plan_name=item.plan_name,
                download_mbps=dl_mbps,
            )
            if deterministic_uid in seen_uids:
                continue
            seen_uids.add(deterministic_uid)

            # Enforce declared market currency code without altering numeric prices
            pricing = PricingSpec(
                currency=expected_currency.upper(),
                regular_monthly_price=item.pricing.regular_monthly_price,
                promo_monthly_price=item.pricing.promo_monthly_price,
                promo_duration_months=item.pricing.promo_duration_months,
                installation_fee=item.pricing.installation_fee,
                taxes_included=item.pricing.taxes_included,
            )

            normalized_offers.append(
                NormalizedOffer(
                    offer_uid=deterministic_uid,
                    country_iso=country_iso.upper(),
                    operator=operator,
                    segment=segment.upper(),
                    plan_name=item.plan_name.strip(),
                    pricing=pricing,
                    home_specs=item.home_specs,
                    vas_addons=item.vas_addons,
                    exact_terms_text=item.exact_terms_text.strip(),
                    source_url=source_url,
                    screenshot_path=screenshot_path,
                    markdown_path=markdown_path,
                )
            )

        return normalized_offers
