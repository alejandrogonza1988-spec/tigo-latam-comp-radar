"""DOM cleaning, strict Pydantic v2 schemas, and Gemini 2.5 Flash structured extraction."""

from src.extractor.dom_cleaner import CleanedDOMArtifact, DOMCleaner
from src.extractor.gemini_parser import GeminiOfferParser
from src.extractor.schemas import (
    EntertainmentVASAddon,
    HomeTechnicalSpec,
    LLMExtractedOfferItem,
    LLMExtractionEnvelope,
    NormalizedOffer,
    PricingSpec,
    VASCommercialModelEnum,
    VASProviderEnum,
    build_offer_uid,
    normalize_slug,
)

__all__ = [
    "CleanedDOMArtifact",
    "DOMCleaner",
    "EntertainmentVASAddon",
    "GeminiOfferParser",
    "HomeTechnicalSpec",
    "LLMExtractedOfferItem",
    "LLMExtractionEnvelope",
    "NormalizedOffer",
    "PricingSpec",
    "VASCommercialModelEnum",
    "VASProviderEnum",
    "build_offer_uid",
    "normalize_slug",
]
