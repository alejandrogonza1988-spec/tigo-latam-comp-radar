"""Strict Pydantic v2 schemas for telecom offers, home broadband specs, pricing, and VAS addons."""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_HOME_TECHNOLOGIES = {"FTTH", "HFC", "DTH", "FWA"}


def normalize_slug(value: str) -> str:
    """Deterministically convert arbitrary Spanish/Portuguese/English text into an ASCII snake_case slug."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or "na"


def build_offer_uid(
    country_iso: str,
    operator: str,
    segment: str,
    plan_name: str,
    download_mbps: Optional[int] = None,
) -> str:
    """
    Build the canonical deterministic Offer UID:
    `{country}_{operator}_{segment}_{normalized_plan_name}_{download_mbps}`
    """
    country_part = normalize_slug(country_iso)
    operator_part = normalize_slug(operator)
    segment_part = normalize_slug(segment)
    plan_part = normalize_slug(plan_name)
    speed_part = str(download_mbps) if download_mbps is not None else "na"
    return f"{country_part}_{operator_part}_{segment_part}_{plan_part}_{speed_part}"


class VASProviderEnum(str, Enum):
    """Normalized catalog of OTT streaming and sports VAS providers across LATAM."""

    NETFLIX = "NETFLIX"
    DISNEY_PLUS = "DISNEY_PLUS"
    MAX = "MAX"
    PRIME_VIDEO = "PRIME_VIDEO"
    PARAMOUNT_PLUS = "PARAMOUNT_PLUS"
    VIX = "VIX"
    UNIVERSAL_PLUS = "UNIVERSAL_PLUS"
    APPLE_TV = "APPLE_TV"
    CRUNCHYROLL = "CRUNCHYROLL"
    SPOTIFY = "SPOTIFY"
    DEEZER = "DEEZER"
    TIGO_SPORTS = "TIGO_SPORTS"
    WIN_SPORTS = "WIN_SPORTS"
    TNT_SPORTS = "TNT_SPORTS"
    FLOW_PASS = "FLOW_PASS"
    OTHER = "OTHER"


class VASCommercialModelEnum(str, Enum):
    """Commercialization structure of an entertainment or sports VAS addon."""

    INCLUDED_HARD_BUNDLE = "INCLUDED_HARD_BUNDLE"
    PROMO_FREE_MONTHS = "PROMO_FREE_MONTHS"
    DISCOUNTED_ADDON = "DISCOUNTED_ADDON"
    STANDALONE_PAID = "STANDALONE_PAID"
    UNKNOWN = "UNKNOWN"


class EntertainmentVASAddon(BaseModel):
    """Strict factual schema for a single streaming/music/sports VAS addon attached to or sold as an offer."""

    model_config = ConfigDict(extra="forbid")

    provider: VASProviderEnum = Field(
        description="Normalized OTT or sports VAS provider enum."
    )
    raw_provider_name: str = Field(
        description="Exact provider name as written in the scraped DOM (e.g., 'HBO Max', 'Disney+ Premium', 'Win+ Fútbol')."
    )
    tier_or_package: Optional[str] = Field(
        default=None,
        description="Explicit tier/plan name if visible in DOM (e.g., 'Estándar con anuncios', 'Disney+ Premium'), otherwise null.",
    )
    commercial_model: VASCommercialModelEnum = Field(
        description="Commercialization model explicitly stated in DOM; use UNKNOWN if ambiguous."
    )
    free_months: Optional[int] = Field(
        default=None,
        description="Number of promotional free/courtesy months explicitly stated in DOM (e.g. 3 for '3 meses sin costo'), otherwise null.",
    )
    promo_price: Optional[float] = Field(
        default=None,
        description="Explicit promotional monthly price in local currency during promo period (0.0 ONLY if explicitly stated gratis/sin costo/$0), otherwise null.",
    )
    regular_price_after_promo: Optional[float] = Field(
        default=None,
        description="Explicit regular monthly price charged after the promo ends, otherwise null. NEVER infer from market standard.",
    )
    exact_terms_text: str = Field(
        description="Verbatim substring copied directly from the scraped DOM describing this VAS addon and its conditions."
    )


class PricingSpec(BaseModel):
    """Strict factual pricing breakdown in local market currency. Never convert or infer missing prices."""

    model_config = ConfigDict(extra="forbid")

    currency: str = Field(
        description="3-letter ISO currency code (e.g., COP, GTQ, USD, CLP, CRC, PYG, BOB, HNL, NIO, UYU)."
    )
    regular_monthly_price: Optional[float] = Field(
        default=None,
        description="Explicit regular/full monthly fee without promotional discount, or null if not explicitly shown.",
    )
    promo_monthly_price: Optional[float] = Field(
        default=None,
        description="Explicit discounted promotional monthly fee, or null if no promo price is shown.",
    )
    promo_duration_months: Optional[int] = Field(
        default=None,
        description="Explicit number of months the promo_monthly_price applies, or null if not stated.",
    )
    installation_fee: Optional[float] = Field(
        default=None,
        description="Explicit one-time installation/activation fee (0.0 if explicitly 'Instalación Gratis'), or null if unstated.",
    )
    taxes_included: Optional[bool] = Field(
        default=None,
        description="True ONLY if DOM explicitly states IVA/impuestos incluidos; False ONLY if DOM explicitly states '+ IVA' / 'sin impuestos'; null otherwise.",
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.strip().upper()


class HomeTechnicalSpec(BaseModel):
    """Technical specification for Fixed Home Broadband, TV, Dúo, and Trío offers."""

    model_config = ConfigDict(extra="forbid")

    technology: Optional[str] = Field(
        default=None,
        description="Access technology ONLY if explicitly stated in DOM: 'FTTH', 'HFC', 'DTH', 'FWA', or null.",
    )
    symmetric_speed: Optional[bool] = Field(
        default=None,
        description="True if DOM explicitly states 'velocidad simétrica' or equal download/upload speeds; False if asymmetric speeds are explicitly shown; null otherwise.",
    )
    download_mbps: Optional[int] = Field(
        default=None,
        description="Explicit download bandwidth in Mbps (convert '1 Gbps' -> 1000 ONLY when '1 Gbps' / '1000 Megas' is literally written), or null.",
    )
    upload_mbps: Optional[int] = Field(
        default=None,
        description="Explicit upload bandwidth in Mbps if written in DOM (or equal to download_mbps ONLY if 'velocidad simétrica' is explicitly written on the card), else null.",
    )
    wifi_hardware: Optional[str] = Field(
        default=None,
        description="Verbatim WiFi router / mesh hardware mention (e.g., 'WiFi 6 + 1 Extensor Mesh'), or null.",
    )
    tv_channels_count: Optional[int] = Field(
        default=None,
        description="Total TV channels count ONLY if explicitly stated (e.g. 140 for '140 canales'), or null.",
    )
    tv_deco_boxes: Optional[int] = Field(
        default=None,
        description="Number of TV set-top decoder boxes ONLY if explicitly stated, or null.",
    )

    @field_validator("technology")
    @classmethod
    def validate_technology(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned or cleaned in {"NULL", "NONE", "UNKNOWN"}:
            return None
        if cleaned in ALLOWED_HOME_TECHNOLOGIES:
            return cleaned
        return None


class LLMExtractedOfferItem(BaseModel):
    """Schema passed to Gemini `response_schema` for each commercial plan/offer visible in the cleaned DOM."""

    model_config = ConfigDict(extra="forbid")

    plan_name: str = Field(
        description="Exact commercial name of the plan or standalone addon as displayed on the offer card."
    )
    pricing: PricingSpec = Field(
        description="Factual pricing fields extracted strictly from the offer card; null for any missing field."
    )
    home_specs: Optional[HomeTechnicalSpec] = Field(
        default=None,
        description="Home broadband/TV technical specs if applicable to the offer; null for pure mobile or standalone VAS offers.",
    )
    vas_addons: List[EntertainmentVASAddon] = Field(
        default_factory=list,
        description="List of entertainment/sports OTT VAS addons explicitly bundled with, discounted on, or sold in this offer.",
    )
    exact_terms_text: str = Field(
        description="Verbatim text snippet copied directly from the offer card and its expanded terms/conditions in the DOM."
    )


class LLMExtractionEnvelope(BaseModel):
    """Top-level response_schema envelope returned by Gemini 2.5 Flash."""

    model_config = ConfigDict(extra="forbid")

    offers: List[LLMExtractedOfferItem] = Field(
        default_factory=list,
        description="All distinct commercial offers/plans explicitly visible in the provided DOM Markdown.",
    )


class NormalizedOffer(BaseModel):
    """Canonical normalized telecom offer persisted in snapshots and compared by the deterministic diff engine."""

    model_config = ConfigDict(extra="forbid")

    offer_uid: str = Field(
        default="",
        description="Deterministic slug: {country}_{operator}_{segment}_{normalized_plan_name}_{download_mbps}",
    )
    country_iso: str = Field(description="2-letter ISO country code (e.g., CO, GT, CL).")
    operator: str = Field(description="Operator commercial name (e.g., Tigo, Claro, Movistar).")
    segment: str = Field(description="Commercial segment: HOME_BUNDLES, MOBILE_POSTPAID, or VAS_ENTERTAINMENT.")
    plan_name: str = Field(description="Commercial plan name.")
    pricing: PricingSpec
    home_specs: Optional[HomeTechnicalSpec] = None
    vas_addons: List[EntertainmentVASAddon] = Field(default_factory=list)

    # Optional visual audit trail & verbatim evidence metadata
    exact_terms_text: Optional[str] = Field(
        default=None,
        description="Verbatim DOM text evidence for the plan card and legal conditions.",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Exact URL from which this offer snapshot was captured.",
    )
    screenshot_path: Optional[str] = Field(
        default=None,
        description="Path to the full-page PNG screenshot audit artifact.",
    )
    markdown_path: Optional[str] = Field(
        default=None,
        description="Path to the cleaned Markdown DOM snapshot artifact.",
    )

    @field_validator("country_iso")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("segment")
    @classmethod
    def uppercase_segment(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def populate_deterministic_offer_uid(self) -> "NormalizedOffer":
        """Auto-compute deterministic offer_uid when not explicitly provided."""
        if not self.offer_uid or not self.offer_uid.strip():
            dl_mbps = self.home_specs.download_mbps if self.home_specs else None
            self.offer_uid = build_offer_uid(
                country_iso=self.country_iso,
                operator=self.operator,
                segment=self.segment,
                plan_name=self.plan_name,
                download_mbps=dl_mbps,
            )
        return self
