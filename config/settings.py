"""Application configuration, environment settings, geo-proxy routing, and DB URI setup."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


COUNTRY_BROWSER_PROFILES: Dict[str, Dict[str, Any]] = {
    "GT": {
        "locale": "es-GT",
        "accept_language": "es-GT,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Guatemala",
        "geolocation": {"latitude": 14.6349, "longitude": -90.5069},
    },
    "SV": {
        "locale": "es-SV",
        "accept_language": "es-SV,es;q=0.9,en;q=0.7",
        "timezone_id": "America/El_Salvador",
        "geolocation": {"latitude": 13.6929, "longitude": -89.2182},
    },
    "HN": {
        "locale": "es-HN",
        "accept_language": "es-HN,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Tegucigalpa",
        "geolocation": {"latitude": 14.0723, "longitude": -87.1921},
    },
    "NI": {
        "locale": "es-NI",
        "accept_language": "es-NI,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Managua",
        "geolocation": {"latitude": 12.1150, "longitude": -86.2362},
    },
    "CR": {
        "locale": "es-CR",
        "accept_language": "es-CR,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Costa_Rica",
        "geolocation": {"latitude": 9.9281, "longitude": -84.0907},
    },
    "PA": {
        "locale": "es-PA",
        "accept_language": "es-PA,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Panama",
        "geolocation": {"latitude": 8.9824, "longitude": -79.5199},
    },
    "CO": {
        "locale": "es-CO",
        "accept_language": "es-CO,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Bogota",
        "geolocation": {"latitude": 4.7110, "longitude": -74.0721},
    },
    "BO": {
        "locale": "es-BO",
        "accept_language": "es-BO,es;q=0.9,en;q=0.7",
        "timezone_id": "America/La_Paz",
        "geolocation": {"latitude": -16.4897, "longitude": -68.1193},
    },
    "PY": {
        "locale": "es-PY",
        "accept_language": "es-PY,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Asuncion",
        "geolocation": {"latitude": -25.2637, "longitude": -57.5759},
    },
    "UY": {
        "locale": "es-UY",
        "accept_language": "es-UY,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Montevideo",
        "geolocation": {"latitude": -34.9011, "longitude": -56.1645},
    },
    "EC": {
        "locale": "es-EC",
        "accept_language": "es-EC,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Guayaquil",
        "geolocation": {"latitude": -0.1807, "longitude": -78.4678},
    },
    "CL": {
        "locale": "es-CL",
        "accept_language": "es-CL,es;q=0.9,en;q=0.7",
        "timezone_id": "America/Santiago",
        "geolocation": {"latitude": -33.4489, "longitude": -70.6693},
    },
}


class RadarSettings(BaseModel):
    """Centralized validated configuration for the Tigo LATAM Competitive Radar."""

    project_root: Path = Field(default=PROJECT_ROOT)
    markets_config_path: Path = Field(
        default_factory=lambda: Path(
            os.getenv("MARKETS_CONFIG_PATH", str(PROJECT_ROOT / "config" / "markets_targets.yaml"))
        )
    )
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(PROJECT_ROOT / 'data' / 'tigo_comp_radar.db').as_posix()}",
        )
    )
    audit_trail_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("AUDIT_TRAIL_DIR", str(PROJECT_ROOT / "data" / "audit_trail"))
        )
    )
    reports_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("REPORTS_DIR", str(PROJECT_ROOT / "data" / "reports"))
        )
    )

    # Gemini LLM extraction configuration (Guardrail #1: temperature MUST be 0.0)
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    gemini_temperature: float = Field(default=0.0)
    gemini_max_retries: int = Field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    )
    gemini_max_markdown_chars: int = Field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_MARKDOWN_CHARS", "120000"))
    )

    # Playwright & Geo-Proxy configuration
    playwright_headless: bool = Field(
        default_factory=lambda: os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    )
    playwright_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "45000"))
    )
    playwright_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("PLAYWRIGHT_CONCURRENCY", "3"))
    )
    proxy_server_template: Optional[str] = Field(
        default_factory=lambda: os.getenv("PROXY_SERVER_TEMPLATE")
    )
    proxy_username_template: Optional[str] = Field(
        default_factory=lambda: os.getenv("PROXY_USERNAME_TEMPLATE")
    )
    proxy_password: Optional[str] = Field(
        default_factory=lambda: os.getenv("PROXY_PASSWORD")
    )

    @field_validator("gemini_temperature")
    @classmethod
    def enforce_zero_temperature(cls, value: float) -> float:
        """Strictly enforce temperature=0.0 to comply with Zero Hallucination guardrail."""
        if value != 0.0:
            raise ValueError("Guardrail Violation: GEMINI_TEMPERATURE must strictly equal 0.0.")
        return 0.0

    def ensure_directories(self) -> None:
        """Ensure local data, audit trail, and report directories exist."""
        self.audit_trail_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            sqlite_path = Path(self.database_url.replace("sqlite:///", "", 1))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    def get_proxy_for_country(self, country_iso: str) -> Optional[Dict[str, str]]:
        """
        Resolve Playwright proxy dictionary for a target LATAM market.

        Supports:
        1. Explicit per-country env var `PROXY_URL_<ISO>` (e.g. `PROXY_URL_CO=http://user:pass@host:port`)
        2. Template-based residential geo-proxy routing (`PROXY_SERVER_TEMPLATE`,
           `PROXY_USERNAME_TEMPLATE` supporting `{country_iso}` and `{country_iso_lower}`,
           and `PROXY_PASSWORD`).
        """
        iso_upper = country_iso.upper().strip()
        iso_lower = iso_upper.lower()

        country_override = os.getenv(f"PROXY_URL_{iso_upper}")
        if country_override:
            return {"server": country_override}

        if self.proxy_server_template:
            proxy_cfg: Dict[str, str] = {
                "server": self.proxy_server_template.format(
                    country_iso=iso_upper,
                    country_iso_lower=iso_lower,
                )
            }
            if self.proxy_username_template:
                proxy_cfg["username"] = self.proxy_username_template.format(
                    country_iso=iso_upper,
                    country_iso_lower=iso_lower,
                )
            if self.proxy_password:
                proxy_cfg["password"] = self.proxy_password
            return proxy_cfg

        return None

    def get_browser_profile(self, country_iso: str) -> Dict[str, Any]:
        """Return locale, timezone, and geolocation coordinates for a country ISO."""
        iso = country_iso.upper().strip()
        return COUNTRY_BROWSER_PROFILES.get(
            iso,
            {
                "locale": "es-419",
                "accept_language": "es-419,es;q=0.9,en;q=0.7",
                "timezone_id": "America/Bogota",
                "geolocation": {"latitude": 4.7110, "longitude": -74.0721},
            },
        )

    def load_markets_catalog(self) -> Dict[str, Any]:
        """Load and validate the YAML catalog of all 12 LATAM markets and operators."""
        if not self.markets_config_path.exists():
            raise FileNotFoundError(
                f"Markets catalog YAML not found at: {self.markets_config_path}"
            )
        with self.markets_config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict) or "markets" not in data:
            raise ValueError("Invalid markets_targets.yaml format: top-level 'markets' key missing.")
        return data


def get_settings() -> RadarSettings:
    """Return a validated RadarSettings instance."""
    settings = RadarSettings()
    settings.ensure_directories()
    return settings
