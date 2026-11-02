"""Generates a single-file Interactive HTML Dashboard with Official Tigo Look & Feel and CSV exports."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.diff_engine.comparator import DeltaTypeEnum, OfferDelta
from src.extractor.schemas import NormalizedOffer, VASCommercialModelEnum, VASProviderEnum

DEFAULT_12_MARKETS: Dict[str, Dict[str, Any]] = {
    "GT": {
        "country_name": "Guatemala",
        "currency": "GTQ",
        "flag": "🇬🇹",
        "market_note": "Precios en Quetzales (GTQ) IVA incl. • Tigo Hogar + FOX (ex Tigo Sports) vs Claro Hogar Doble/Triple Fibra",
    },
    "SV": {
        "country_name": "El Salvador",
        "currency": "USD",
        "flag": "🇸🇻",
        "market_note": "Precios en USD IVA incl. • Tigo Hogar + ONEtv vs Claro Fibra / Claro TV+ y Digicel (Móvil / Fibra bajo cotización)",
    },
    "HN": {
        "country_name": "Honduras",
        "currency": "HNL",
        "flag": "🇭🇳",
        "market_note": "Precios en Lempiras (HNL) ISV incl. • Tigo ONEtv (Paramount+ incl., tarifa por cobertura) vs Claro Triple Play Simétrico",
    },
    "NI": {
        "country_name": "Nicaragua",
        "currency": "NIO",
        "flag": "🇳🇮",
        "market_note": "Precios en Córdobas (NIO) IVA incl. • Tigo Hogar + One TV vs Claro Hogar Triple Fibra (Max + Universal+)",
    },
    "CR": {
        "country_name": "Costa Rica",
        "currency": "CRC",
        "flag": "🇨🇷",
        "market_note": "Precios en Colones (CRC) IVAI • Tigo Hogar + Tigo Sports vs Liberty Next TV, kölbi ICE, Claro y Telecable",
    },
    "PA": {
        "country_name": "Panamá",
        "currency": "USD",
        "flag": "🇵🇦",
        "market_note": "Tarifas base en USD (B/.) antes de 7% ITBMS • Tigo Hogar + Tigo Sports LPF vs +Móvil (+Fibra Simétrica + Universal+)",
    },
    "CO": {
        "country_name": "Colombia",
        "currency": "COP",
        "flag": "🇨🇴",
        "market_note": "Referencia Bogotá Estrato 3 (19% IVA incl.) • Tigo Hogar / Full Tigo vs Movistar Fibra, Claro, ETB y WOM (solo Móvil)",
    },
    "BO": {
        "country_name": "Bolivia",
        "currency": "BOB",
        "flag": "🇧🇴",
        "market_note": "Precios en Bolivianos (BOB) IVA incl. • Tigo Hogar / Full Tigo + Tigo Sports vs Entel GPON, Viva FO y AXS+ (HBO Max)",
    },
    "PY": {
        "country_name": "Paraguay",
        "currency": "PYG",
        "flag": "🇵🇾",
        "market_note": "Precios en Guaraníes (PYG) IVA incl. • Tigo DoblePack + Tigo Sports & Disney+ 12m vs Personal Flow y Claro Fibra",
    },
    "UY": {
        "country_name": "Uruguay",
        "currency": "UYU",
        "flag": "🇺🇾",
        "market_note": "Nota Regulatoria: Antel posee el monopolio de Fibra Fija (FTTH) al hogar; Movistar UY (Millicom) y Claro UY compiten en Móvil Contrato + OTT",
    },
    "EC": {
        "country_name": "Ecuador",
        "currency": "USD",
        "flag": "🇪🇨",
        "market_note": "Precios en USD (15% IVA incl.) • Movistar/Tigo EC opera Móvil Pospago + Spotify; Claro, Netlife (WiFi 7), Xtrim y CNT compiten en FTTH",
    },
    "CL": {
        "country_name": "Chile",
        "currency": "CLP",
        "flag": "🇨🇱",
        "market_note": "Precios en Pesos Chilenos (CLP) IVA incl. • Movistar Fibra (Millicom) vs Entel TV Full+, ClaroVTR, WOM (Zapping + TNT Sports) y Mundo",
    },
}


@dataclass
class ReportArtifacts:
    """File paths produced by the ReportBuilder."""

    html_path: Path
    offers_csv_path: Optional[Path] = None
    deltas_csv_path: Optional[Path] = None


def _classify_home_bundle_type(offer: NormalizedOffer) -> str:
    """Deterministically classify an offer into Trío, Dúo Internet+TV, Convergente, Solo Internet, or Móvil Pospago."""
    if offer.segment.upper() == "MOBILE_POSTPAID":
        return "MOVIL_POSPAGO"

    name_lower = offer.plan_name.lower()
    hs = offer.home_specs
    is_convergent = any(
        tok in name_lower for tok in ("full tigo", "movistar total", "+ móvil", "+ movil", "convergente")
    )
    has_tv = bool(
        (hs and (hs.tv_channels_count or hs.tv_deco_boxes))
        or any(
            tok in name_lower
            for tok in (
                "trío", "trio", "triple", "dúo", "duo", "+ tv", "one tv", "onetv",
                "tv hd", "flow", "entel tv", "movistar tv", "claro tv", "next tv",
                "zapping", "mundo go", "iptv", "doblepack", "doble play",
            )
        )
    ) and not ("+ móvil" in name_lower and "tv" not in name_lower)
    is_trio = any(tok in name_lower for tok in ("trío", "trio", "triple", "3 play", "tripleplay", "telefonía", "+ voz"))
    has_internet = bool(
        (hs and hs.download_mbps)
        or any(tok in name_lower for tok in ("internet", "fibra", "megas", "mbps", "giga", "hogar", "fo "))
    )

    if is_convergent:
        return "CONVERGENTE"
    if is_trio:
        return "TRIO"
    if has_internet and has_tv:
        return "DUO_INTERNET_TV"
    if has_internet:
        return "SOLO_INTERNET"
    return "OTRO_HOGAR"


def _classify_speed_tier(download_mbps: Optional[int]) -> Dict[str, Any]:
    """Bucket fixed broadband speeds into 5 deterministic LATAM comparison tiers."""
    if download_mbps is None:
        return {
            "code": "TIER_5_CONVERGENT_MOBILE",
            "order": 5,
            "label": "Planes Convergentes / Móvil Pospago / Tarifa por Cobertura",
        }
    if download_mbps <= 160:
        return {
            "code": "TIER_1_ENTRY",
            "order": 1,
            "label": "Escalón Entrada (Hasta 160 Mbps)",
        }
    if download_mbps <= 360:
        return {
            "code": "TIER_2_STANDARD",
            "order": 2,
            "label": "Escalón Estándar / Medio (161 – 360 Mbps)",
        }
    if download_mbps <= 650:
        return {
            "code": "TIER_3_FLAGSHIP",
            "order": 3,
            "label": "Escalón Flagship / Alta Velocidad (361 – 650 Mbps)",
        }
    return {
        "code": "TIER_4_GIGA",
        "order": 4,
        "label": "Escalón Ultra / Giga (651+ Mbps)",
    }


class ReportBuilder:
    """
    Builds the single-file navigable HTML dashboard (`daily_radar_YYYY-MM-DD.html`)
    with Official Tigo Brand Identity, self-contained Vanilla JS event delegation,
    and deterministic JSON dataset injection.
    """

    def __init__(
        self,
        reports_dir: Path,
        markets_catalog: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.markets_catalog = markets_catalog or {}

    def _resolve_millicom_operators(self) -> Set[str]:
        """Return set of `(COUNTRY_ISO, operator_lower)` pairs belonging to Tigo / Millicom."""
        millicom_pairs: Set[str] = set()
        markets = (self.markets_catalog or {}).get("markets", {})
        for iso, m_cfg in markets.items():
            for op in m_cfg.get("operators", []):
                if op.get("is_millicom"):
                    millicom_pairs.add(f"{iso.upper()}::{str(op.get('name', '')).strip().lower()}")
        return millicom_pairs

    def _is_millicom_operator(self, country_iso: str, operator: str, millicom_pairs: Set[str]) -> bool:
        op_lower = operator.strip().lower()
        if "tigo" in op_lower:
            return True
        return f"{country_iso.upper()}::{op_lower}" in millicom_pairs

    def build_dashboard(
        self,
        offers: List[NormalizedOffer],
        deltas: List[OfferDelta],
        report_date: date,
        output_filename: Optional[str] = None,
        export_csv_files: bool = True,
        tailwind_cdn_url: str = "https://cdn.tailwindcss.com",
    ) -> ReportArtifacts:
        """Render the complete single-file HTML dashboard and optional companion CSV exports."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        html_filename = output_filename or f"daily_radar_{report_date.isoformat()}.html"
        html_path = self.reports_dir / html_filename

        payload = self._build_json_payload(
            offers=offers,
            deltas=deltas,
            report_date=report_date,
        )

        # Prevent `</script>` injection from verbatim DOM text breaking inline HTML script block
        safe_json_payload = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        html_document = self._render_html_template(
            safe_json_payload=safe_json_payload,
            report_date_str=report_date.isoformat(),
            tailwind_cdn_url=tailwind_cdn_url,
        )
        html_path.write_text(html_document, encoding="utf-8")

        offers_csv_path: Optional[Path] = None
        deltas_csv_path: Optional[Path] = None
        if export_csv_files:
            stem = Path(html_filename).stem
            offers_csv_path = self.reports_dir / f"{stem}_offers.csv"
            deltas_csv_path = self.reports_dir / f"{stem}_deltas.csv"
            self._write_offers_csv(offers, offers_csv_path)
            self._write_deltas_csv(deltas, deltas_csv_path)

        return ReportArtifacts(
            html_path=html_path,
            offers_csv_path=offers_csv_path,
            deltas_csv_path=deltas_csv_path,
        )

    def _build_json_payload(
        self,
        offers: List[NormalizedOffer],
        deltas: List[OfferDelta],
        report_date: date,
    ) -> Dict[str, Any]:
        millicom_pairs = self._resolve_millicom_operators()

        markets_meta: Dict[str, Dict[str, Any]] = {}
        raw_markets = (self.markets_catalog or {}).get("markets", {})
        for iso, defaults in DEFAULT_12_MARKETS.items():
            yaml_entry = raw_markets.get(iso, {})
            markets_meta[iso] = {
                "iso": iso,
                "country_name": yaml_entry.get("country_name", defaults["country_name"]),
                "currency": yaml_entry.get("currency", defaults["currency"]),
                "flag": defaults["flag"],
                "market_note": defaults.get("market_note", ""),
                "operators": [op.get("name") for op in yaml_entry.get("operators", []) if op.get("name")],
            }

        serialized_offers: List[Dict[str, Any]] = []
        vas_matrix_rows: List[Dict[str, Any]] = []
        operators_seen: Dict[str, bool] = {}
        offers_with_addons_count = 0

        for offer in offers:
            is_milli = self._is_millicom_operator(offer.country_iso, offer.operator, millicom_pairs)
            operators_seen[offer.operator] = is_milli or operators_seen.get(offer.operator, False)

            eff_price = (
                offer.pricing.promo_monthly_price
                if offer.pricing.promo_monthly_price is not None
                else offer.pricing.regular_monthly_price
            )
            dl_mbps = offer.home_specs.download_mbps if offer.home_specs else None
            tier_info = _classify_speed_tier(dl_mbps)
            bundle_type = _classify_home_bundle_type(offer)
            has_addons = len(offer.vas_addons) > 0
            if has_addons:
                offers_with_addons_count += 1

            offer_dict = offer.model_dump(mode="json")
            offer_dict["is_millicom"] = is_milli
            offer_dict["effective_price"] = eff_price
            offer_dict["has_addons"] = has_addons
            offer_dict["addons_count"] = len(offer.vas_addons)
            offer_dict["vas_provider_codes"] = [a.provider.value for a in offer.vas_addons]
            offer_dict["vas_commercial_models"] = list({a.commercial_model.value for a in offer.vas_addons})
            offer_dict["bundle_type"] = bundle_type
            offer_dict["speed_tier_code"] = tier_info["code"]
            offer_dict["speed_tier_order"] = tier_info["order"]
            offer_dict["speed_tier_label"] = tier_info["label"]
            serialized_offers.append(offer_dict)

            for addon in offer.vas_addons:
                vas_matrix_rows.append(
                    {
                        "country_iso": offer.country_iso,
                        "country_name": markets_meta.get(offer.country_iso, {}).get(
                            "country_name", offer.country_iso
                        ),
                        "currency": offer.pricing.currency,
                        "operator": offer.operator,
                        "is_millicom": is_milli,
                        "segment": offer.segment,
                        "offer_uid": offer.offer_uid,
                        "plan_name": offer.plan_name,
                        "download_mbps": dl_mbps,
                        "plan_effective_price": eff_price,
                        "provider": addon.provider.value,
                        "raw_provider_name": addon.raw_provider_name,
                        "tier_or_package": addon.tier_or_package,
                        "commercial_model": addon.commercial_model.value,
                        "free_months": addon.free_months,
                        "promo_price": addon.promo_price,
                        "regular_price_after_promo": addon.regular_price_after_promo,
                        "exact_terms_text": addon.exact_terms_text,
                        "offer_exact_terms_text": offer.exact_terms_text,
                        "source_url": offer.source_url,
                        "screenshot_path": offer.screenshot_path,
                        "markdown_path": offer.markdown_path,
                    }
                )

        # Precompute deterministic Tigo Hogar reference comparisons for every offer in the same country & segment
        tigo_offers_by_country_seg: Dict[str, List[Dict[str, Any]]] = {}
        for o_dict in serialized_offers:
            if o_dict["is_millicom"]:
                bucket_key = f"{o_dict['country_iso']}::{o_dict['segment']}"
                tigo_offers_by_country_seg.setdefault(bucket_key, []).append(o_dict)

        for o_dict in serialized_offers:
            bucket_key = f"{o_dict['country_iso']}::{o_dict['segment']}"
            tigo_candidates = tigo_offers_by_country_seg.get(bucket_key, [])
            if o_dict["is_millicom"] or not tigo_candidates:
                o_dict["tigo_comparison"] = None
                continue

            comp_dl = (o_dict.get("home_specs") or {}).get("download_mbps") or 0
            best_tigo = min(
                tigo_candidates,
                key=lambda t: (
                    0 if t["speed_tier_code"] == o_dict["speed_tier_code"] else 1,
                    0 if t["bundle_type"] == o_dict["bundle_type"] else 1,
                    abs(((t.get("home_specs") or {}).get("download_mbps") or 0) - comp_dl),
                ),
            )

            tigo_eff = best_tigo.get("effective_price")
            comp_eff = o_dict.get("effective_price")
            eff_diff: Optional[float] = None
            eff_pct: Optional[float] = None
            if tigo_eff is not None and comp_eff is not None and tigo_eff != 0:
                eff_diff = round(float(comp_eff) - float(tigo_eff), 2)
                eff_pct = round((eff_diff / float(tigo_eff)) * 100.0, 2)

            tigo_reg = best_tigo["pricing"].get("regular_monthly_price")
            comp_reg = o_dict["pricing"].get("regular_monthly_price")
            reg_diff: Optional[float] = None
            if tigo_reg is not None and comp_reg is not None:
                reg_diff = round(float(comp_reg) - float(tigo_reg), 2)

            tigo_dl = (best_tigo.get("home_specs") or {}).get("download_mbps")
            comp_dl_raw = (o_dict.get("home_specs") or {}).get("download_mbps")
            speed_diff = (
                (int(comp_dl_raw) - int(tigo_dl))
                if (tigo_dl is not None and comp_dl_raw is not None)
                else None
            )

            tigo_vas_set = set(best_tigo.get("vas_provider_codes") or [])
            comp_vas_set = set(o_dict.get("vas_provider_codes") or [])

            o_dict["tigo_comparison"] = {
                "tigo_offer_uid": best_tigo["offer_uid"],
                "tigo_operator": best_tigo["operator"],
                "tigo_plan_name": best_tigo["plan_name"],
                "tigo_effective_price": tigo_eff,
                "tigo_regular_price": tigo_reg,
                "tigo_download_mbps": tigo_dl,
                "effective_price_diff": eff_diff,
                "effective_price_pct": eff_pct,
                "regular_price_diff": reg_diff,
                "speed_diff_mbps": speed_diff,
                "extra_vas_vs_tigo": sorted(comp_vas_set - tigo_vas_set),
                "missing_vas_vs_tigo": sorted(tigo_vas_set - comp_vas_set),
            }

        serialized_deltas: List[Dict[str, Any]] = []
        price_drops = 0
        price_increases = 0
        new_or_removed = 0
        vas_changes = 0
        speed_hw_changes = 0

        for delta in deltas:
            is_milli = self._is_millicom_operator(delta.country_iso, delta.operator, millicom_pairs)
            operators_seen[delta.operator] = is_milli or operators_seen.get(delta.operator, False)

            if delta.delta_type == DeltaTypeEnum.PRICE_CHANGE:
                if delta.direction == "PRICE_DROP":
                    price_drops += 1
                elif delta.direction == "PRICE_INCREASE":
                    price_increases += 1
            elif delta.delta_type in {DeltaTypeEnum.NEW_OFFER_LAUNCHED, DeltaTypeEnum.OFFER_RETIRED}:
                new_or_removed += 1
            elif delta.delta_type == DeltaTypeEnum.VAS_PORTFOLIO_CHANGE:
                vas_changes += 1
            elif delta.delta_type == DeltaTypeEnum.SPEED_OR_HARDWARE_CHANGE:
                speed_hw_changes += 1

            delta_dict = delta.model_dump(mode="json")
            delta_dict["is_millicom"] = is_milli
            delta_dict["has_addons"] = len(delta.vas_providers_affected) > 0
            serialized_deltas.append(delta_dict)

        active_countries = sorted(
            {o.country_iso for o in offers} | {d.country_iso for d in deltas}
        )
        default_benchmark_country = (
            "CO" if "CO" in active_countries else (active_countries[0] if active_countries else "CO")
        )

        operators_list = [
            {"name": name, "is_millicom": is_m}
            for name, is_m in sorted(operators_seen.items(), key=lambda item: (not item[1], item[0]))
        ]

        executive_brief = self._build_executive_brief(
            serialized_offers=serialized_offers,
            serialized_deltas=serialized_deltas,
            vas_matrix_rows=vas_matrix_rows,
            markets_meta=markets_meta,
            report_date=report_date,
        )

        return {
            "report_date": report_date.isoformat(),
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "default_benchmark_country": default_benchmark_country,
            "executive_brief": executive_brief,
            "kpis": {
                "catalog_countries_total": len(DEFAULT_12_MARKETS),
                "active_countries_monitored": len(active_countries),
                "total_offers_tracked": len(serialized_offers),
                "offers_with_addons": offers_with_addons_count,
                "total_changes_detected": len(serialized_deltas),
                "price_drops": price_drops,
                "price_increases": price_increases,
                "new_or_removed_plans": new_or_removed,
                "vas_addon_changes": vas_changes,
                "speed_or_hardware_changes": speed_hw_changes,
            },
            "markets": markets_meta,
            "all_country_Order": list(DEFAULT_12_MARKETS.keys()),
            "operators": operators_list,
            "segments": ["HOME_BUNDLES", "MOBILE_POSTPAID", "VAS_ENTERTAINMENT"],
            "delta_types": [e.value for e in DeltaTypeEnum],
            "vas_providers": [e.value for e in VASProviderEnum],
            "vas_commercial_models": [e.value for e in VASCommercialModelEnum],
            "offers": serialized_offers,
            "deltas": serialized_deltas,
            "vas_matrix": vas_matrix_rows,
        }

    @staticmethod
    def _build_executive_brief(
        serialized_offers: List[Dict[str, Any]],
        serialized_deltas: List[Dict[str, Any]],
        vas_matrix_rows: List[Dict[str, Any]],
        markets_meta: Dict[str, Dict[str, Any]],
        report_date: date,
    ) -> Dict[str, Any]:
        """Deterministically compute all 3-minute VP/Director Executive Summary metrics with zero hallucination."""
        total_offers = len(serialized_offers)
        tigo_offers = [o for o in serialized_offers if o["is_millicom"]]
        comp_offers = [o for o in serialized_offers if not o["is_millicom"]]

        tigo_with_vas = [o for o in tigo_offers if o["has_addons"]]
        comp_with_vas = [o for o in comp_offers if o["has_addons"]]

        comparable_comp = [
            o for o in comp_offers
            if o.get("tigo_comparison") and o["tigo_comparison"].get("effective_price_diff") is not None
        ]
        comp_cheaper = [o for o in comparable_comp if o["tigo_comparison"]["effective_price_diff"] < 0]
        comp_equal = [o for o in comparable_comp if o["tigo_comparison"]["effective_price_diff"] == 0]
        comp_pricier = [o for o in comparable_comp if o["tigo_comparison"]["effective_price_diff"] > 0]
        comp_no_peer = len(comp_offers) - len(comparable_comp)

        tigo_vas_rows = [r for r in vas_matrix_rows if r["is_millicom"]]
        comp_vas_rows = [r for r in vas_matrix_rows if not r["is_millicom"]]

        tigo_hb = sum(1 for r in tigo_vas_rows if r["commercial_model"] == "INCLUDED_HARD_BUNDLE")
        tigo_promo = sum(1 for r in tigo_vas_rows if r["commercial_model"] == "PROMO_FREE_MONTHS")
        tigo_disc = sum(1 for r in tigo_vas_rows if r["commercial_model"] == "DISCOUNTED_ADDON")
        tigo_sa_pure = sum(1 for r in tigo_vas_rows if r["commercial_model"] == "STANDALONE_PAID")
        tigo_sa = tigo_sa_pure + tigo_disc

        comp_hb = sum(1 for r in comp_vas_rows if r["commercial_model"] == "INCLUDED_HARD_BUNDLE")
        comp_promo = sum(1 for r in comp_vas_rows if r["commercial_model"] == "PROMO_FREE_MONTHS")
        comp_disc = sum(1 for r in comp_vas_rows if r["commercial_model"] == "DISCOUNTED_ADDON")
        comp_sa_pure = sum(1 for r in comp_vas_rows if r["commercial_model"] == "STANDALONE_PAID")
        comp_sa = comp_sa_pure + comp_disc

        def _pct(num: int, den: int) -> float:
            return round((num / den) * 100.0, 1) if den > 0 else 0.0

        tigo_hb_pct = _pct(tigo_hb, len(tigo_vas_rows))
        comp_hb_pct = _pct(comp_hb, len(comp_vas_rows))
        hb_gap_pp = round(tigo_hb_pct - comp_hb_pct, 1)

        tigo_promo_pct = _pct(tigo_promo, len(tigo_vas_rows))
        comp_promo_pct = _pct(comp_promo, len(comp_vas_rows))
        promo_gap_pp = round(tigo_promo_pct - comp_promo_pct, 1)

        tigo_sa_pct = _pct(tigo_sa, len(tigo_vas_rows))
        comp_sa_pct = _pct(comp_sa, len(comp_vas_rows))
        sa_gap_pp = round(tigo_sa_pct - comp_sa_pct, 1)

        comp_cheaper_pct = _pct(len(comp_cheaper), len(comparable_comp))
        tigo_parity_count = len(comp_equal) + len(comp_pricier)
        tigo_parity_pct = _pct(tigo_parity_count, len(comparable_comp))
        target_parity_count = int((0.60 * len(comparable_comp)) + 0.9999) if comparable_comp else 0
        plans_needed_for_60pct = max(0, target_parity_count - tigo_parity_count)

        tigo_deltas = [d for d in serialized_deltas if d["is_millicom"]]
        comp_deltas = [d for d in serialized_deltas if not d["is_millicom"]]
        comp_price_drops = [d for d in comp_deltas if d["direction"] == "PRICE_DROP"]
        comp_vas_adds = [d for d in comp_deltas if d["delta_type"] == "VAS_PORTFOLIO_CHANGE"]

        country_rows: List[Dict[str, Any]] = []
        status_counts = {"GREEN": 0, "YELLOW": 0, "RED": 0}
        red_countries: List[str] = []
        green_countries: List[str] = []

        present_isos = [
            iso for iso in DEFAULT_12_MARKETS.keys()
            if any(o["country_iso"] == iso for o in serialized_offers)
        ]

        for iso in present_isos:
            meta = markets_meta.get(iso, DEFAULT_12_MARKETS[iso])
            c_offers = [o for o in serialized_offers if o["country_iso"] == iso]
            c_tigo = [o for o in c_offers if o["is_millicom"]]
            c_comp = [o for o in c_offers if not o["is_millicom"]]
            c_comparable = [
                o for o in c_comp
                if o.get("tigo_comparison") and o["tigo_comparison"].get("effective_price_diff") is not None
            ]
            c_cheaper = [o for o in c_comparable if o["tigo_comparison"]["effective_price_diff"] < 0]
            worst_gap_pct = round(
                min((o["tigo_comparison"]["effective_price_pct"] for o in c_cheaper), default=0.0),
                1,
            )

            c_tigo_hb = sum(
                1 for r in tigo_vas_rows
                if r["country_iso"] == iso and r["commercial_model"] == "INCLUDED_HARD_BUNDLE"
            )
            c_tigo_promo = sum(
                1 for r in tigo_vas_rows
                if r["country_iso"] == iso and r["commercial_model"] == "PROMO_FREE_MONTHS"
            )
            c_tigo_sa = sum(
                1 for r in tigo_vas_rows
                if r["country_iso"] == iso and r["commercial_model"] in ("STANDALONE_PAID", "DISCOUNTED_ADDON")
            )
            c_comp_hb = sum(
                1 for r in comp_vas_rows
                if r["country_iso"] == iso and r["commercial_model"] == "INCLUDED_HARD_BUNDLE"
            )

            c_deltas = [d for d in serialized_deltas if d["country_iso"] == iso]
            c_comp_off_deltas = [
                d for d in c_deltas
                if not d["is_millicom"]
                and (
                    d["direction"] in ("PRICE_DROP", "VAS_ADDED", "SPEED_UPGRADE", "HARDWARE_CHANGE")
                    or d["delta_type"] == "NEW_OFFER_LAUNCHED"
                )
            ]

            undercut_ratio = (len(c_cheaper) / len(c_comparable)) if c_comparable else 0.0
            has_fixed_tigo = any(o["segment"] == "HOME_BUNDLES" for o in c_tigo)

            if (undercut_ratio >= 0.50 and worst_gap_pct <= -20.0) or (
                len(c_comp_off_deltas) >= 1 and worst_gap_pct <= -25.0
            ):
                status_code = "RED"
                status_label = "🔴 Fuera de ruta"
                red_countries.append(iso)
            elif (
                undercut_ratio >= 0.50
                or worst_gap_pct <= -15.0
                or len(c_comp_off_deltas) >= 1
                or not has_fixed_tigo
            ):
                status_code = "YELLOW"
                status_label = "🟡 En riesgo"
            else:
                status_code = "GREEN"
                status_label = "🟢 En ruta"
                green_countries.append(iso)

            status_counts[status_code] += 1

            if c_comparable:
                price_reading = (
                    f"{len(c_cheaper)} de {len(c_comparable)} rivales más baratos"
                    + (f" (punta {worst_gap_pct:.1f}%)" if c_cheaper else " (Tigo en paridad/ventaja)")
                )
            elif not has_fixed_tigo:
                price_reading = "Operación Tigo/Millicom solo Móvil (sin FTTH propio)"
            else:
                price_reading = "Tarifa Hogar Tigo sujeta a cobertura geográfica"

            country_rows.append(
                {
                    "country_iso": iso,
                    "country_name": meta.get("country_name", iso),
                    "currency": meta.get("currency", ""),
                    "total_offers": len(c_offers),
                    "tigo_offers": len(c_tigo),
                    "comp_offers": len(c_comp),
                    "comparable_comp": len(c_comparable),
                    "comp_cheaper": len(c_cheaper),
                    "worst_gap_pct": worst_gap_pct,
                    "tigo_hb": c_tigo_hb,
                    "tigo_promo": c_tigo_promo,
                    "tigo_sa": c_tigo_sa,
                    "comp_hb": c_comp_hb,
                    "deltas_today": len(c_deltas),
                    "comp_offensive_deltas": len(c_comp_off_deltas),
                    "price_reading": price_reading,
                    "status_code": status_code,
                    "status_label": status_label,
                }
            )

        red_cheaper_sum = sum(r["comp_cheaper"] for r in country_rows if r["status_code"] == "RED")
        red_cheaper_share = _pct(red_cheaper_sum, len(comp_cheaper))
        red_deltas_sum = sum(r["comp_offensive_deltas"] for r in country_rows if r["status_code"] == "RED")

        return {
            "report_date": report_date.isoformat(),
            "total_countries": len(present_isos),
            "total_offers": total_offers,
            "tigo_offers_count": len(tigo_offers),
            "tigo_offers_pct": _pct(len(tigo_offers), total_offers),
            "comp_offers_count": len(comp_offers),
            "comp_offers_pct": _pct(len(comp_offers), total_offers),
            "total_with_vas": len(tigo_with_vas) + len(comp_with_vas),
            "total_with_vas_pct": _pct(len(tigo_with_vas) + len(comp_with_vas), total_offers),
            "tigo_with_vas_count": len(tigo_with_vas),
            "tigo_with_vas_pct": _pct(len(tigo_with_vas), len(tigo_offers)),
            "comp_with_vas_count": len(comp_with_vas),
            "comp_with_vas_pct": _pct(len(comp_with_vas), len(comp_offers)),
            "comparable_comp_count": len(comparable_comp),
            "comp_no_peer_count": comp_no_peer,
            "comp_cheaper_count": len(comp_cheaper),
            "comp_cheaper_pct": comp_cheaper_pct,
            "comp_equal_count": len(comp_equal),
            "comp_pricier_count": len(comp_pricier),
            "tigo_parity_count": tigo_parity_count,
            "tigo_parity_pct": tigo_parity_pct,
            "target_parity_count": target_parity_count,
            "plans_needed_for_60pct": plans_needed_for_60pct,
            "parity_gap_vs_60_pp": round(tigo_parity_pct - 60.0, 1),
            "total_vas_instances": len(vas_matrix_rows),
            "tigo_vas_instances": len(tigo_vas_rows),
            "comp_vas_instances": len(comp_vas_rows),
            "tigo_hb": tigo_hb,
            "tigo_hb_pct": tigo_hb_pct,
            "comp_hb": comp_hb,
            "comp_hb_pct": comp_hb_pct,
            "total_hb": tigo_hb + comp_hb,
            "hb_gap_pp": hb_gap_pp,
            "tigo_promo": tigo_promo,
            "tigo_promo_pct": tigo_promo_pct,
            "comp_promo": comp_promo,
            "comp_promo_pct": comp_promo_pct,
            "total_promo": tigo_promo + comp_promo,
            "promo_gap_pp": promo_gap_pp,
            "tigo_sa": tigo_sa,
            "tigo_sa_pure": tigo_sa_pure,
            "tigo_disc": tigo_disc,
            "tigo_sa_pct": tigo_sa_pct,
            "comp_sa": comp_sa,
            "comp_sa_pure": comp_sa_pure,
            "comp_disc": comp_disc,
            "comp_sa_pct": comp_sa_pct,
            "total_sa": tigo_sa + comp_sa,
            "sa_gap_pp": sa_gap_pp,
            "total_deltas": len(serialized_deltas),
            "tigo_deltas_count": len(tigo_deltas),
            "tigo_deltas_pct": _pct(len(tigo_deltas), len(serialized_deltas)),
            "comp_deltas_count": len(comp_deltas),
            "comp_deltas_pct": _pct(len(comp_deltas), len(serialized_deltas)),
            "comp_price_drops_count": len(comp_price_drops),
            "comp_vas_adds_count": len(comp_vas_adds),
            "status_counts": status_counts,
            "red_countries": red_countries,
            "green_countries": green_countries,
            "red_cheaper_sum": red_cheaper_sum,
            "red_cheaper_share": red_cheaper_share,
            "red_deltas_sum": red_deltas_sum,
            "country_rows": country_rows,
        }

    @staticmethod
    def _write_offers_csv(offers: List[NormalizedOffer], output_path: Path) -> None:
        fieldnames = [
            "offer_uid",
            "country_iso",
            "operator",
            "segment",
            "plan_name",
            "currency",
            "regular_monthly_price",
            "promo_monthly_price",
            "promo_duration_months",
            "installation_fee",
            "taxes_included",
            "technology",
            "symmetric_speed",
            "download_mbps",
            "upload_mbps",
            "wifi_hardware",
            "tv_channels_count",
            "tv_deco_boxes",
            "vas_addons_summary",
            "source_url",
            "screenshot_path",
        ]
        with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for o in offers:
                hs = o.home_specs
                vas_summary = " | ".join(
                    f"{a.provider.value}:{a.commercial_model.value}"
                    f"{f'({a.free_months}m free)' if a.free_months else ''}"
                    for a in o.vas_addons
                )
                writer.writerow(
                    {
                        "offer_uid": o.offer_uid,
                        "country_iso": o.country_iso,
                        "operator": o.operator,
                        "segment": o.segment,
                        "plan_name": o.plan_name,
                        "currency": o.pricing.currency,
                        "regular_monthly_price": o.pricing.regular_monthly_price,
                        "promo_monthly_price": o.pricing.promo_monthly_price,
                        "promo_duration_months": o.pricing.promo_duration_months,
                        "installation_fee": o.pricing.installation_fee,
                        "taxes_included": o.pricing.taxes_included,
                        "technology": hs.technology if hs else None,
                        "symmetric_speed": hs.symmetric_speed if hs else None,
                        "download_mbps": hs.download_mbps if hs else None,
                        "upload_mbps": hs.upload_mbps if hs else None,
                        "wifi_hardware": hs.wifi_hardware if hs else None,
                        "tv_channels_count": hs.tv_channels_count if hs else None,
                        "tv_deco_boxes": hs.tv_deco_boxes if hs else None,
                        "vas_addons_summary": vas_summary,
                        "source_url": o.source_url,
                        "screenshot_path": o.screenshot_path,
                    }
                )

    @staticmethod
    def _write_deltas_csv(deltas: List[OfferDelta], output_path: Path) -> None:
        fieldnames = [
            "country_iso",
            "operator",
            "segment",
            "offer_uid",
            "plan_name",
            "delta_type",
            "direction",
            "currency",
            "numeric_diff",
            "percentage_diff",
            "vas_providers_affected",
            "summary",
        ]
        with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for d in deltas:
                writer.writerow(
                    {
                        "country_iso": d.country_iso,
                        "operator": d.operator,
                        "segment": d.segment,
                        "offer_uid": d.offer_uid,
                        "plan_name": d.plan_name,
                        "delta_type": d.delta_type.value,
                        "direction": d.direction,
                        "currency": d.currency,
                        "numeric_diff": d.numeric_diff,
                        "percentage_diff": d.percentage_diff,
                        "vas_providers_affected": ",".join(d.vas_providers_affected),
                        "summary": d.summary,
                    }
                )

    @staticmethod
    def _render_html_template(
        safe_json_payload: str,
        report_date_str: str,
        tailwind_cdn_url: str = "https://cdn.tailwindcss.com",
    ) -> str:
        raw_template = r"""<!DOCTYPE html>
<html lang="es">
<!-- Tigo Corporate Design System | tailwindcss + self-contained interactive controller (offline-safe replacement for alpinejs) -->
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <meta name="theme-color" content="#001E60" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="Radar Tigo LATAM" />
  <title>Radar Competitivo LATAM — Tigo (__REPORT_DATE_STR__)</title>
  <script src="__TAILWIND_CDN_URL__"></script>
  <style>
    :root {
      --tigo-navy: #001E60;
      --tigo-blue: #003F98;
      --tigo-bright-blue: #00AEEF;
      --tigo-cyan: #00C8F8;
      --tigo-yellow: #FFCB05;
      --tigo-bg: #F4F7FB;
      --tigo-surface: #FFFFFF;
      --tigo-surface-soft: #F8FAFD;
      --tigo-text: #172033;
      --tigo-text-secondary: #64748B;
      --tigo-border: #DDE5EF;
      --tigo-positive: #16A36A;
      --tigo-warning: #F59E0B;
      --tigo-negative: #DC3545;
      --tigo-radius-sm: 8px;
      --tigo-radius-md: 12px;
      --tigo-radius-lg: 16px;
      --tigo-shadow-sm: 0 2px 8px rgba(0, 30, 96, 0.06);
      --tigo-shadow-md: 0 8px 24px rgba(0, 30, 96, 0.10);
    }

    * {
      box-sizing: border-box;
    }

    html, body {
      margin: 0;
      padding: 0;
      background-color: var(--tigo-bg) !important;
      color: var(--tigo-text) !important;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
      font-variant-numeric: tabular-nums;
      overflow-x: hidden;
    }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #E9EFF8; }
    ::-webkit-scrollbar-thumb { background: #B5C4DA; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #8CA3C3; }

    /* Corporate Tigo Header */
    .tigo-header {
      background: linear-gradient(135deg, var(--tigo-navy) 0%, #002B7F 55%, var(--tigo-blue) 100%);
      color: #FFFFFF;
      position: relative;
      border-bottom: 4px solid var(--tigo-bright-blue);
      box-shadow: 0 4px 20px rgba(0, 30, 96, 0.14);
    }
    .tigo-header::after {
      content: "";
      position: absolute;
      left: 0;
      bottom: -4px;
      width: 140px;
      height: 4px;
      background: var(--tigo-yellow);
    }
    .tigo-header-glow {
      background-image: radial-gradient(circle at 88% 20%, rgba(0, 200, 248, 0.18) 0%, transparent 45%),
                        radial-gradient(circle at 12% 85%, rgba(255, 203, 5, 0.10) 0%, transparent 35%);
    }

    .tigo-logo-box {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.10);
      border: 1.5px solid rgba(255, 255, 255, 0.24);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      box-shadow: 0 4px 12px rgba(0, 15, 55, 0.25);
    }

    /* Surfaces & Cards */
    .tigo-card {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: var(--tigo-radius-md);
      box-shadow: var(--tigo-shadow-sm);
    }
    .tigo-card-lg {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: var(--tigo-radius-lg);
      box-shadow: var(--tigo-shadow-sm);
    }
    .tigo-soft-box {
      background-color: var(--tigo-surface-soft);
      border: 1px solid var(--tigo-border);
      border-radius: var(--tigo-radius-sm);
    }

    /* Tigo vs Competitor Offer Cards */
    .tigo-ref-offer-card {
      background: linear-gradient(180deg, #F0F7FF 0%, #FFFFFF 48%);
      border: 2px solid var(--tigo-blue);
      border-top: 4px solid var(--tigo-bright-blue);
      border-radius: var(--tigo-radius-md);
      box-shadow: var(--tigo-shadow-md);
    }
    .tigo-comp-offer-card {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-top: 3px solid #94A3B8;
      border-radius: var(--tigo-radius-md);
      box-shadow: var(--tigo-shadow-sm);
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .tigo-comp-offer-card:hover {
      border-color: #93B4DC;
      box-shadow: var(--tigo-shadow-md);
    }

    /* KPI Cards */
    .tigo-kpi {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: var(--tigo-radius-md);
      box-shadow: var(--tigo-shadow-sm);
      padding: 14px 16px;
      position: relative;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .tigo-kpi-clickable {
      cursor: pointer;
    }
    .tigo-kpi-clickable:hover {
      box-shadow: var(--tigo-shadow-md);
      border-color: var(--tigo-bright-blue);
    }

    /* Controls, Inputs, Pills & Buttons */
    button {
      cursor: pointer;
      font-family: inherit;
    }
    .tigo-input, .tigo-select {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: var(--tigo-radius-sm);
      color: var(--tigo-text);
      font-size: 12px;
      line-height: 1.4;
      padding: 7px 11px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .tigo-input:focus, .tigo-select:focus {
      outline: none;
      border-color: var(--tigo-bright-blue);
      box-shadow: 0 0 0 3px rgba(0, 174, 239, 0.16);
    }

    .tigo-btn-secondary {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      color: var(--tigo-navy);
      border-radius: var(--tigo-radius-sm);
      font-weight: 600;
      font-size: 12px;
      padding: 6px 12px;
      transition: all 0.15s ease;
    }
    .tigo-btn-secondary:hover {
      background-color: #EEF4FC;
      border-color: var(--tigo-blue);
    }

    .tigo-btn-evidence {
      background-color: #F0F6FF;
      border: 1px solid #BFD6F6;
      color: var(--tigo-blue);
      border-radius: var(--tigo-radius-sm);
      font-weight: 700;
      font-size: 11px;
      padding: 5px 10px;
      transition: all 0.15s ease;
      white-space: nowrap;
    }
    .tigo-btn-evidence:hover {
      background-color: var(--tigo-navy);
      border-color: var(--tigo-navy);
      color: #FFFFFF;
    }

    /* Country Pills */
    .tigo-country-pill {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      color: var(--tigo-text);
      border-radius: var(--tigo-radius-sm);
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .tigo-country-pill:hover {
      border-color: var(--tigo-bright-blue);
      background-color: #F2F8FF;
    }
    .tigo-country-pill.is-active {
      background-color: var(--tigo-navy);
      border-color: var(--tigo-navy);
      color: #FFFFFF;
      box-shadow: 0 3px 10px rgba(0, 30, 96, 0.18);
    }

    /* OTT / VAS Chips */
    .tigo-vas-chip {
      background-color: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      color: var(--tigo-navy);
      border-radius: var(--tigo-radius-sm);
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 700;
      transition: all 0.15s ease;
    }
    .tigo-vas-chip:hover {
      border-color: var(--tigo-bright-blue);
      background-color: #EEF7FF;
    }
    .tigo-vas-chip.is-active {
      background-color: var(--tigo-blue);
      border-color: var(--tigo-blue);
      color: #FFFFFF;
      box-shadow: 0 2px 6px rgba(0, 63, 152, 0.22);
    }

    /* Tabs */
    .tigo-tab-bar {
      border-bottom: 2px solid var(--tigo-border);
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .tigo-tab-btn {
      background: transparent;
      border: 1px solid transparent;
      border-bottom: 3px solid transparent;
      margin-bottom: -2px;
      padding: 11px 16px;
      font-size: 13px;
      font-weight: 600;
      color: var(--tigo-text-secondary);
      border-radius: 10px 10px 0 0;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s ease;
    }
    .tigo-tab-btn:hover {
      color: var(--tigo-navy);
      background-color: rgba(0, 63, 152, 0.04);
    }
    .tigo-tab-btn.is-active {
      background-color: var(--tigo-surface);
      border-color: var(--tigo-border);
      border-bottom: 3px solid var(--tigo-bright-blue);
      color: var(--tigo-navy);
      font-weight: 800;
    }

    /* Tables */
    .tigo-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      text-align: left;
    }
    .tigo-table thead tr {
      background-color: var(--tigo-navy);
      color: #FFFFFF;
    }
    .tigo-table thead th {
      padding: 11px 14px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }
    .tigo-table tbody tr {
      border-bottom: 1px solid var(--tigo-border);
      background-color: var(--tigo-surface);
      transition: background-color 0.12s ease;
    }
    .tigo-table tbody tr:nth-child(even) {
      background-color: var(--tigo-surface-soft);
    }
    .tigo-table tbody tr.is-tigo-row {
      background-color: #EBF5FF;
      box-shadow: inset 4px 0 0 var(--tigo-bright-blue);
    }
    .tigo-table tbody tr:hover {
      background-color: #E3F0FF;
    }
    .tigo-table tbody td {
      padding: 11px 14px;
      vertical-align: middle;
      color: var(--tigo-text);
    }

    /* Badges */
    .badge-tigo {
      background-color: var(--tigo-navy);
      color: #FFFFFF;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.02em;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-tigo-dot {
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background-color: var(--tigo-yellow);
      display: inline-block;
    }
    .badge-comp {
      background-color: #F1F5F9;
      color: #334155;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 800;
    }
    .badge-positive {
      background-color: #ECFDF5;
      color: #0F764A;
      border: 1px solid #A7F3D0;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
    }
    .badge-negative {
      background-color: #FEF2F2;
      color: #B91C1C;
      border: 1px solid #FECACA;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
    }
    .badge-warning {
      background-color: #FFFBEB;
      color: #B45309;
      border: 1px solid #FDE68A;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
    }
    .badge-info {
      background-color: #E0F5FE;
      color: var(--tigo-blue);
      border: 1px solid #BAE6FD;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
    }

    .is-hidden {
      display: none !important;
    }
  </style>
</head>
<body>

  <!-- Embedded Normalized Dataset & Deterministic Daily Deltas -->
  <script id="radar-payload" type="application/json">__SAFE_JSON_PAYLOAD__</script>

  <!-- CORPORATE TIGO HEADER -->
  <header class="tigo-header">
    <div class="tigo-header-glow">
      <div class="max-w-[1650px] mx-auto px-4 sm:px-6 py-4 flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
        <div class="flex items-center gap-3.5">
          <!-- Official Tigo Corporate Wordmark Emblem -->
          <div class="tigo-logo-box" aria-label="Tigo">
            <svg width="40" height="28" viewBox="0 0 80 52" fill="none" xmlns="http://www.w3.org/2000/svg">
              <text x="4" y="33" fill="#FFFFFF" font-family="Inter, Arial, sans-serif" font-weight="900" font-size="31" letter-spacing="-1">tigo</text>
              <path d="M16 42C29 48 51 48 65 40" stroke="#FFCB05" stroke-width="4" stroke-linecap="round"/>
              <circle cx="69" cy="12" r="4" fill="#00C8F8"/>
            </svg>
          </div>
          <div>
            <div class="flex flex-wrap items-center gap-2.5">
              <h1 class="text-lg sm:text-xl font-extrabold tracking-tight text-white m-0">
                Radar Competitivo LATAM: Ofertas Hoy vs Tigo Hogar &amp; Addons VAS
              </h1>
              <span class="px-2.5 py-0.5 text-xs font-bold rounded-full" style="background: rgba(0, 200, 248, 0.18); color: #A5F3FC; border: 1px solid rgba(0, 200, 248, 0.38);">
                12 Mercados &bull; Motor Determinístico
              </span>
            </div>
            <p class="text-xs m-0 mt-1" style="color: #CBD5E1;">
              Ofertas Vigentes Hoy: <strong id="hdr-report-date" class="text-white font-bold"></strong>
              &bull; Generado: <span id="hdr-generated-utc"></span>
              &bull; Cobertura: GT, SV, HN, NI, CR, PA, CO, BO, PY, UY, EC, CL (FTTH/HFC Hogar, Dúos, Tríos + OTT/Sports)
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2.5">
          <!-- PROMINENT ONE-CLICK BUTTON: FILTER OFFERS WITH ADDONS -->
          <button
            type="button"
            id="header-addons-btn"
            data-action="toggle-addons"
            class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-extrabold transition"
          ></button>

          <!-- Quick Operator Scope Toggle -->
          <div class="inline-flex rounded-lg p-1 text-xs font-semibold" style="background: rgba(0, 15, 50, 0.38); border: 1px solid rgba(255, 255, 255, 0.18);">
            <button type="button" data-action="set-scope" data-scope="ALL" class="hdr-scope-btn px-3 py-1.5 rounded-md transition">Todos</button>
            <button type="button" data-action="set-scope" data-scope="MILLICOM" class="hdr-scope-btn px-3 py-1.5 rounded-md transition">Solo Tigo</button>
            <button type="button" data-action="set-scope" data-scope="COMPETITORS" class="hdr-scope-btn px-3 py-1.5 rounded-md transition">Solo Competencia</button>
          </div>

          <!-- One-Click Client-Side CSV/Excel Export -->
          <button
            type="button"
            data-action="export-csv"
            class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition"
            style="background-color: var(--tigo-positive); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.2); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);"
          >
            <span>&#8681; Exportar Vista a CSV / Excel</span>
          </button>
        </div>
      </div>
    </div>
  </header>

  <main class="max-w-[1650px] mx-auto px-4 sm:px-6 py-6 space-y-5">

    <!-- 1. TOP KPI BAR (7 Corporate Tigo KPI Cards) -->
    <section id="kpi-bar" class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3"></section>

    <!-- 2. DYNAMIC FILTER BAR + ADDON QUICK-FILTER DRAWER -->
    <section class="tigo-card p-4 space-y-4">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-navy);">
            Filtros Globales, Selector de País (12 Mercados) &amp; Explorador de Addons
          </span>
          <span
            id="active-filter-badge"
            class="is-hidden px-2.5 py-0.5 text-xs rounded-full font-bold"
            style="background-color: var(--tigo-navy); color: #FFFFFF;"
          ></span>
        </div>
        <div class="flex flex-wrap items-center gap-2.5">
          <input
            id="search-input"
            type="text"
            placeholder="Buscar plan, +Fibra, AXS, 500 Mbps, WiFi 6, Max, Disney+..."
            class="tigo-input w-full md:w-72"
          />
          <button
            type="button"
            data-action="reset-filters"
            class="tigo-btn-secondary whitespace-nowrap"
          >
            Limpiar Filtros
          </button>
        </div>
      </div>

      <!-- Dedicated Addons Quick-Filter Bar -->
      <div id="addon-filter-panel" class="tigo-soft-box p-3.5 space-y-3 transition">
        <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-2.5">
          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              id="panel-addons-btn"
              data-action="toggle-addons"
              class="px-3 py-1.5 rounded-lg border text-xs font-extrabold inline-flex items-center gap-1.5 transition"
            ></button>

            <!-- Commercial Model Quick Pills -->
            <div class="inline-flex flex-wrap rounded-lg p-1 text-xs gap-1" style="background: var(--tigo-surface); border: 1px solid var(--tigo-border);">
              <button type="button" data-action="set-vas-model" data-model="ALL" class="vas-model-btn px-2.5 py-1 rounded transition">Todos Modelos</button>
              <button type="button" data-action="set-vas-model" data-model="INCLUDED_HARD_BUNDLE" class="vas-model-btn px-2.5 py-1 rounded transition">Incluido Fijo (Hard Bundle)</button>
              <button type="button" data-action="set-vas-model" data-model="PROMO_FREE_MONTHS" class="vas-model-btn px-2.5 py-1 rounded transition">Meses Gratis (Promo)</button>
              <button type="button" data-action="set-vas-model" data-model="DISCOUNTED_ADDON" class="vas-model-btn px-2.5 py-1 rounded transition">Addon con Descuento</button>
              <button type="button" data-action="set-vas-model" data-model="STANDALONE_PAID" class="vas-model-btn px-2.5 py-1 rounded transition">Addon Factura</button>
            </div>
          </div>

          <label class="inline-flex items-center gap-2 text-xs font-semibold cursor-pointer" style="color: var(--tigo-text-secondary);">
            <input id="keep-tigo-ref-checkbox" type="checkbox" checked class="rounded" style="accent-color: var(--tigo-blue);" />
            <span>Mantener tarjeta referencia Tigo Hogar al comparar</span>
          </label>
        </div>

        <!-- 1-Click VAS Provider Chips -->
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="text-xs font-bold mr-1" style="color: var(--tigo-blue);">Filtrar por Plataforma OTT / Deportes:</span>
          <div id="vas-chips-container" class="flex flex-wrap gap-1.5"></div>
        </div>
      </div>

      <!-- Country Pills (All 12 Markets with Verified Offer Counts) -->
      <div>
        <span class="block text-xs font-semibold mb-1.5" style="color: var(--tigo-text-secondary);">
          Seleccionar País (Comparativa Directa en Pestaña 1 / Filtro por País en Pestañas 2 y 3):
        </span>
        <div id="country-pills-container" class="flex flex-wrap gap-1.5"></div>
      </div>

      <!-- Dropdown Multi-Select Row: Operator, Bundle Type, Segment, Delta Type -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
        <!-- Operator Multi-Select -->
        <div class="relative tigo-dd-wrap">
          <label class="block text-xs font-bold mb-1" style="color: var(--tigo-text-secondary);">Operador (Tigo vs Competencia)</label>
          <button
            type="button"
            data-action="toggle-dropdown"
            data-dd="operators"
            class="tigo-select w-full text-left flex items-center justify-between font-medium"
          >
            <span id="dd-label-operators" class="truncate"></span>
            <span class="ml-2" style="color: var(--tigo-text-secondary);">&#9662;</span>
          </button>
          <div
            id="dd-menu-operators"
            class="is-hidden absolute z-40 mt-1 w-full max-h-60 overflow-y-auto tigo-card p-1.5 space-y-1"
            style="box-shadow: var(--tigo-shadow-md);"
          ></div>
        </div>

        <!-- Bundle Type Filter -->
        <div>
          <label class="block text-xs font-bold mb-1" style="color: var(--tigo-text-secondary);">Tipo de Oferta</label>
          <select id="bundle-type-select" class="tigo-select w-full font-medium">
            <option value="ALL">Todas las Ofertas (Internet + Dúos + Tríos + Convergente)</option>
            <option value="SOLO_INTERNET">Solo Internet Fijo (FTTH / HFC)</option>
            <option value="DUO_INTERNET_TV">Dúos (Internet + TV)</option>
            <option value="TRIO">Tríos (Internet + TV + Telefonía)</option>
            <option value="CONVERGENTE">Convergente (Hogar + Móvil)</option>
            <option value="MOVIL_POSPAGO">Móvil Pospago (Referencia País)</option>
          </select>
        </div>

        <!-- Segment Multi-Select -->
        <div class="relative tigo-dd-wrap">
          <label class="block text-xs font-bold mb-1" style="color: var(--tigo-text-secondary);">Segmento Comercial</label>
          <button
            type="button"
            data-action="toggle-dropdown"
            data-dd="segments"
            class="tigo-select w-full text-left flex items-center justify-between font-medium"
          >
            <span id="dd-label-segments" class="truncate"></span>
            <span class="ml-2" style="color: var(--tigo-text-secondary);">&#9662;</span>
          </button>
          <div
            id="dd-menu-segments"
            class="is-hidden absolute z-40 mt-1 w-full tigo-card p-1.5 space-y-1"
            style="box-shadow: var(--tigo-shadow-md);"
          ></div>
        </div>

        <!-- Delta Type Multi-Select -->
        <div class="relative tigo-dd-wrap">
          <label class="block text-xs font-bold mb-1" style="color: var(--tigo-text-secondary);">Tipo de Cambio (Pestaña Deltas)</label>
          <button
            type="button"
            data-action="toggle-dropdown"
            data-dd="deltas"
            class="tigo-select w-full text-left flex items-center justify-between font-medium"
          >
            <span id="dd-label-deltas" class="truncate"></span>
            <span class="ml-2" style="color: var(--tigo-text-secondary);">&#9662;</span>
          </button>
          <div
            id="dd-menu-deltas"
            class="is-hidden absolute z-40 mt-1 w-full tigo-card p-1.5 space-y-1"
            style="box-shadow: var(--tigo-shadow-md);"
          ></div>
        </div>
      </div>
    </section>

    <!-- 3. NAVIGATION TABS -->
    <div class="tigo-tab-bar">
      <button
        type="button"
        data-action="set-tab"
        data-tab="exec_summary"
        class="tigo-tab-btn is-active"
      >
        <span>1. Resumen Ejecutivo VP (3 Min)</span>
        <span id="tab-count-exec" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #FEF08A; color: var(--tigo-navy);">12 Países</span>
      </button>

      <button
        type="button"
        data-action="set-tab"
        data-tab="tigo_vs_comp"
        class="tigo-tab-btn"
      >
        <span>2. Comparativa Ofertas Hoy: Tigo Hogar vs Competencia</span>
        <span id="tab-count-home" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #E0F5FE; color: var(--tigo-navy);"></span>
      </button>

      <button
        type="button"
        data-action="set-tab"
        data-tab="deltas"
        class="tigo-tab-btn"
      >
        <span>3. Cambios del Día (Deltas Ayer vs Hoy)</span>
        <span id="tab-count-deltas" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #FEF3C7; color: #92400E;"></span>
      </button>

      <button
        type="button"
        data-action="set-tab"
        data-tab="vas_matrix"
        class="tigo-tab-btn"
      >
        <span>4. Matriz Regional de Addons VAS (12 Países)</span>
        <span id="tab-count-vas" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #EEF2FF; color: var(--tigo-blue);"></span>
      </button>
    </div>

    <!-- =================================================================== -->
    <!-- TAB 1: RESUMEN EJECUTIVO VP (3 MINUTOS) — STORYTELLING & ESTRATEGIA -->
    <!-- =================================================================== -->
    <section id="view-exec_summary" class="space-y-6">
      <div id="exec-summary-content" class="space-y-6"></div>
    </section>

    <!-- =================================================================== -->
    <!-- TAB 2: COMPARATIVA COMPLETA HOY — TIGO HOGAR VS COMPETIDORES        -->
    <!-- =================================================================== -->
    <section id="view-tigo_vs_comp" class="is-hidden space-y-5">
      <!-- Country & Layout Control Bar -->
      <div class="tigo-card p-4 space-y-3">
        <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-3">
            <label for="benchmark-country-select" class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-navy);">
              País Comparado Hoy:
            </label>
            <select id="benchmark-country-select" class="tigo-select font-bold" style="border-color: var(--tigo-blue); color: var(--tigo-navy);"></select>
            <span id="country-summary-counts" class="text-xs" style="color: var(--tigo-text-secondary);"></span>
          </div>

          <div class="flex flex-wrap items-center gap-2.5">
            <div class="inline-flex rounded-lg p-1 text-xs font-semibold" style="background: var(--tigo-surface-soft); border: 1px solid var(--tigo-border);">
              <button type="button" data-action="set-layout-mode" data-mode="BOTH" class="layout-mode-btn px-3 py-1.5 rounded-md transition">Tarjetas Cara a Cara + Tabla Completa</button>
              <button type="button" data-action="set-layout-mode" data-mode="CARDS" class="layout-mode-btn px-3 py-1.5 rounded-md transition">Solo Cara a Cara vs Tigo</button>
              <button type="button" data-action="set-layout-mode" data-mode="TABLE" class="layout-mode-btn px-3 py-1.5 rounded-md transition">Solo Tabla Completa</button>
            </div>

            <select id="benchmark-sort-select" class="tigo-select font-semibold">
              <option value="tigo_first">Tigo Primero + Velocidad Desc</option>
              <option value="speed_desc">Velocidad Descarga (Mayor a Menor)</option>
              <option value="price_asc">Precio Mensual Hoy (Menor a Mayor)</option>
            </select>
          </div>
        </div>

        <div
          id="country-market-note"
          class="rounded-lg px-3.5 py-2.5 text-xs flex flex-wrap items-center justify-between gap-2"
          style="background-color: #F0F6FF; border: 1px solid #C9DDF8; border-left: 4px solid var(--tigo-blue);"
        ></div>
      </div>

      <!-- PART A: HEAD-TO-HEAD CARDS BY SPEED TIER -->
      <div id="head-to-head-tiers" class="space-y-5"></div>

      <!-- PART B: COMPLETE FULL-ATTRIBUTE COMPARISON TABLE -->
      <div id="full-table-wrapper" class="space-y-2.5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-xs font-extrabold uppercase tracking-wider m-0" style="color: var(--tigo-navy);">
            Tabla Comparativa Completa Línea por Línea — Todos los Atributos Hogar &amp; Brecha vs Tigo
          </h3>
          <span class="text-xs" style="color: var(--tigo-text-secondary);">
            Filas azul claro = Referencia Tigo / Millicom &bull; Clic en &ldquo;Ver Evidencia&rdquo; para ver texto literal del DOM
          </span>
        </div>

        <div class="tigo-card overflow-x-auto">
          <table class="tigo-table">
            <thead>
              <tr>
                <th>Operador</th>
                <th>Tipo Oferta</th>
                <th>Plan Comercial</th>
                <th>Red &amp; Velocidad (&#8595;/&#8593;)</th>
                <th>Equipos WiFi &amp; TV</th>
                <th style="text-align: right;">Precio Hoy (Efectivo)</th>
                <th style="text-align: right;">Precio Regular</th>
                <th style="text-align: right;">Brecha vs Tigo</th>
                <th>Addons VAS Completos</th>
                <th style="text-align: center;">Evidencia</th>
              </tr>
            </thead>
            <tbody id="benchmark-tbody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- =================================================================== -->
    <!-- TAB 2: DAILY DELTAS (YESTERDAY VS TODAY)                            -->
    <!-- =================================================================== -->
    <section id="view-deltas" class="is-hidden space-y-4">
      <div class="tigo-card p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span class="font-bold" style="color: var(--tigo-navy);">
          Alcance Geográfico de Cambios Detectados (Deltas Determinísticos Ayer vs Hoy):
        </span>
        <div class="inline-flex rounded-lg p-1 gap-1" style="background: var(--tigo-surface-soft); border: 1px solid var(--tigo-border);">
          <button type="button" data-action="set-regional-scope" data-rscope="ALL_12" class="rscope-btn px-3 py-1 rounded font-bold transition">Todos los 12 Países</button>
          <button type="button" data-action="set-regional-scope" data-rscope="CURRENT" class="rscope-btn px-3 py-1 rounded font-bold transition">Solo País Seleccionado</button>
        </div>
      </div>
      <div id="deltas-list" class="space-y-3.5"></div>
    </section>

    <!-- =================================================================== -->
    <!-- TAB 3: REGIONAL VAS MATRIX                                          -->
    <!-- =================================================================== -->
    <section id="view-vas_matrix" class="is-hidden space-y-4">
      <div class="tigo-card p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span class="font-bold" style="color: var(--tigo-navy);">
          Alcance Geográfico de la Matriz Regional de Addons VAS (OTT &amp; Deportes):
        </span>
        <div class="inline-flex rounded-lg p-1 gap-1" style="background: var(--tigo-surface-soft); border: 1px solid var(--tigo-border);">
          <button type="button" data-action="set-regional-scope" data-rscope="ALL_12" class="rscope-btn px-3 py-1 rounded font-bold transition">Todos los 12 Países</button>
          <button type="button" data-action="set-regional-scope" data-rscope="CURRENT" class="rscope-btn px-3 py-1 rounded font-bold transition">Solo País Seleccionado</button>
        </div>
      </div>

      <div class="tigo-card overflow-x-auto">
        <table class="tigo-table">
          <thead>
            <tr>
              <th>País</th>
              <th>Operador</th>
              <th>Proveedor VAS</th>
              <th>Tier / Paquete</th>
              <th>Modelo Comercial</th>
              <th style="text-align: center;">Meses Gratis</th>
              <th style="text-align: right;">Precio Promo / Addon</th>
              <th>Plan Asociado</th>
              <th style="text-align: center;">Evidencia</th>
            </tr>
          </thead>
          <tbody id="vas-tbody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <!-- VISUAL AUDIT TRAIL & VERBATIM EVIDENCE MODAL -->
  <div
    id="evidence-modal"
    data-action="backdrop-close-modal"
    class="is-hidden fixed inset-0 z-50 flex items-center justify-center p-4"
    style="background: rgba(0, 18, 56, 0.62); backdrop-filter: blur(2px);"
  >
    <div
      class="tigo-card-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto overflow-x-hidden"
      style="box-shadow: 0 20px 50px rgba(0, 30, 96, 0.28);"
    >
      <div
        class="px-5 py-4 flex items-start justify-between gap-4"
        style="background: linear-gradient(135deg, var(--tigo-navy) 0%, var(--tigo-blue) 100%); color: #FFFFFF; border-bottom: 3px solid var(--tigo-yellow);"
      >
        <div>
          <span class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-cyan);">
            Visual Audit Trail &amp; Verbatim DOM Evidence
          </span>
          <h2 id="modal-title" class="text-base sm:text-lg font-extrabold text-white m-0 mt-1"></h2>
          <p id="modal-uid" class="text-xs font-mono m-0 mt-0.5" style="color: #CBD5E1;"></p>
        </div>
        <button
          type="button"
          data-action="close-modal"
          class="px-3 py-1.5 rounded-lg text-xs font-extrabold"
          style="background: rgba(255,255,255,0.14); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.28);"
        >
          Cerrar &#10005;
        </button>
      </div>

      <div class="p-5 space-y-4">
        <div class="space-y-1.5">
          <h3 class="text-xs font-extrabold uppercase tracking-wider m-0" style="color: var(--tigo-navy);">
            Texto Exacto Extraído del DOM (exact_terms_text):
          </h3>
          <pre
            id="modal-terms"
            class="tigo-soft-box p-3.5 text-xs leading-relaxed whitespace-pre-wrap font-mono m-0 max-h-60 overflow-y-auto"
            style="color: var(--tigo-text);"
          ></pre>
        </div>

        <div id="modal-vas-wrap" class="is-hidden space-y-2">
          <h3 class="text-xs font-extrabold uppercase tracking-wider m-0" style="color: var(--tigo-blue);">
            Términos Verbatim por Addon VAS:
          </h3>
          <div id="modal-vas-list" class="space-y-2"></div>
        </div>

        <div id="modal-links-wrap" class="pt-3 flex flex-wrap items-center gap-2.5 text-xs" style="border-top: 1px solid var(--tigo-border);"></div>
        <div id="modal-audit-paths" class="tigo-soft-box p-3 text-xs font-mono space-y-1 break-all" style="color: var(--tigo-text-secondary);"></div>
      </div>
    </div>
  </div>

  <!-- SELF-CONTAINED VANILLA JS CONTROLLER (ZERO EXTERNAL RUNTIME DEPENDENCY) -->
  <script>
    (function () {
      "use strict";

      const PAYLOAD = JSON.parse(document.getElementById("radar-payload").textContent);
      const MARKETS = PAYLOAD.markets || {};
      const COUNTRY_ORDER = PAYLOAD.all_country_Order || Object.keys(MARKETS);
      const OFFERS = PAYLOAD.offers || [];
      const DELTAS = PAYLOAD.deltas || [];
      const VAS_MATRIX = PAYLOAD.vas_matrix || [];
      const OPERATORS = PAYLOAD.operators || [];
      const SEGMENTS = PAYLOAD.segments || ["HOME_BUNDLES", "MOBILE_POSTPAID", "VAS_ENTERTAINMENT"];
      const DELTA_TYPES = PAYLOAD.delta_types || [];

      document.getElementById("hdr-report-date").textContent = PAYLOAD.report_date || "";
      document.getElementById("hdr-generated-utc").textContent = PAYLOAD.generated_at_utc || "";

      // Distinct OTT/Sports providers present in dataset
      const PRESENT_VAS = (function () {
        const s = new Set();
        OFFERS.forEach(function (o) {
          (o.vas_provider_codes || (o.vas_addons || []).map(function (v) { return v.provider; })).forEach(function (code) {
            if (code) s.add(code);
          });
        });
        return s.size > 0 ? Array.from(s) : (PAYLOAD.vas_providers || []);
      })();

      const state = {
        activeTab: "exec_summary",
        homeComparisonMode: "BOTH",
        onlyWithAddons: false,
        selectedVasModel: "ALL",
        selectedBundleType: "ALL",
        keepTigoReferenceWhenFiltering: true,
        operatorScope: "ALL",
        searchQuery: "",
        selectedCountries: [],
        selectedOperators: [],
        selectedSegments: [],
        selectedDeltaTypes: [],
        selectedVasProviders: [],
        benchmarkCountry: PAYLOAD.default_benchmark_country || "CO",
        benchmarkSortBy: "tigo_first",
        openDropdown: null,
        lastFilteredDeltas: [],
        lastFilteredVasRows: []
      };

      function escHtml(val) {
        return String(val === null || val === undefined ? "" : val)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function toggleInArray(arr, item) {
        const idx = arr.indexOf(item);
        if (idx >= 0) arr.splice(idx, 1);
        else arr.push(item);
      }

      function formatMoney(val, currency) {
        if (val === null || val === undefined) return "—";
        return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(val) + " " + (currency || "");
      }

      function formatSignedMoney(val, currency) {
        if (val === null || val === undefined) return "—";
        const sign = val > 0 ? "+" : "";
        return sign + new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(val) + " " + (currency || "");
      }

      function renderExecutiveBrief() {
        const eb = PAYLOAD.executive_brief || {};
        const container = document.getElementById("exec-summary-content");
        if (!container) return;

        const dateStr = eb.report_date || PAYLOAD.report_date || "";

        // Country table rows HTML
        const countryRowsHtml = (eb.country_rows || []).map(function (c) {
          const m = MARKETS[c.country_iso] || { flag: "" };
          let badgeClass = "badge-comp";
          if (c.status_code === "GREEN") badgeClass = "badge-positive";
          else if (c.status_code === "YELLOW") badgeClass = "badge-warning";
          else if (c.status_code === "RED") badgeClass = "badge-negative";

          const worstGapText = c.worst_gap_pct < 0 ? (c.worst_gap_pct.toFixed(1) + "%") : "0.0%";

          return (
            '<tr class="hover:bg-[#F8FAFC] transition cursor-pointer" data-action="exec-drill-country" data-iso="' + escHtml(c.country_iso) + '" title="Clic para ver detalle de ofertas en ' + escHtml(c.country_name) + '">' +
              '<td class="font-extrabold whitespace-nowrap">' +
                '<span class="mr-1.5">' + escHtml(m.flag || "") + "</span>" +
                '<strong style="color: var(--tigo-navy);">' + escHtml(c.country_iso) + "</strong>" +
                '<span class="ml-1 text-xs font-semibold" style="color: var(--tigo-text-secondary);">' + escHtml(c.country_name) + "</span>" +
              "</td>" +
              '<td style="text-align:center;" class="font-bold">' + c.tigo_offers + " / " + c.comp_offers + "</td>" +
              '<td style="text-align:center;" class="font-semibold">' +
                (c.comparable_comp > 0 ? (c.comp_cheaper + " / " + c.comparable_comp) : "—") +
              "</td>" +
              '<td style="text-align:right;" class="font-bold ' + (c.worst_gap_pct < 0 ? "text-[#DC2626]" : "") + '">' +
                (c.worst_gap_pct < 0 ? worstGapText : "—") +
              "</td>" +
              '<td style="text-align:center;" class="font-semibold">' +
                '<span>' + c.tigo_hb + ' HB</span> <span class="text-[11px]" style="color:var(--tigo-text-secondary);">(' + c.tigo_promo + 'P/' + c.tigo_sa + 'SA)</span>' +
              "</td>" +
              '<td style="text-align:center;" class="font-semibold">' +
                c.comp_hb + " HB" +
              "</td>" +
              '<td style="text-align:center;" class="font-bold">' +
                (c.deltas_today > 0 ? ('<span class="badge-negative">' + c.deltas_today + ' (' + c.comp_offensive_deltas + ' rival)</span>') : "0") +
              "</td>" +
              '<td style="text-align:center;"><span class="' + badgeClass + '">' + escHtml(c.status_label) + '</span></td>' +
              '<td class="text-xs" style="color: var(--tigo-text-secondary);">' + escHtml(c.price_reading) + '</td>' +
            "</tr>"
          );
        }).join("");

        container.innerHTML =
          '<!-- 1. MENSAJE PRINCIPAL -->' +
          '<div class="tigo-card-lg p-5 sm:p-6 space-y-3" style="border-left: 6px solid var(--tigo-navy); background: linear-gradient(180deg, #FFFFFF 0%, #F9FBFE 100%);">' +
            '<div class="flex items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 1</span>' +
                '<h2 class="text-sm sm:text-base font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                  '1. Mensaje Principal de Estrategia' +
                '</h2>' +
              '</div>' +
              '<span class="text-xs font-semibold" style="color: var(--tigo-text-secondary);">Corte al ' + escHtml(dateStr) + ' &bull; 12 Mercados LATAM</span>' +
            '</div>' +
            '<p class="text-base sm:text-lg font-bold leading-relaxed m-0" style="color: var(--tigo-navy);">' +
              'La competencia supera a Tigo en agresividad comercial al concentrar <strong>' + eb.comp_cheaper_count + ' de ' + eb.comparable_comp_count + ' ofertas comparables (' + eb.comp_cheaper_pct.toFixed(1) + '%)</strong> a menor precio e integrar <strong>' + eb.comp_hb_pct.toFixed(1) + '% de Hardbundle en contenidos</strong> (frente al ' + eb.tigo_hb_pct.toFixed(1) + '% de Tigo), concentrando <strong>' + eb.red_cheaper_sum + ' de los ' + eb.comp_cheaper_count + ' planes más baratos (' + eb.red_cheaper_share.toFixed(1) + '%)</strong> y <strong>' + eb.red_deltas_sum + ' de las ' + (eb.comp_price_drops_count + eb.comp_vas_adds_count) + ' ofensivas comerciales del día</strong> en 5 mercados críticos (PA, CO, PY, UY, CL), lo que exige rebalancear mix hacia HB y contener fuga de Gross Adds en tiers de 500–600 Mbps.' +
            '</p>' +
          '</div>' +

          '<!-- 2. INDICADORES CLAVE -->' +
          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-blue); color: #FFFFFF;">Sección 2</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                  '2. Indicadores Clave de Portafolio y Dinámica Competitiva' +
                '</h3>' +
              '</div>' +
              '<span class="text-xs italic" style="color: var(--tigo-text-secondary);">Separación Hardbundle (HB), Standalone (SA) y Promociones</span>' +
            '</div>' +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                '<thead>' +
                  '<tr>' +
                    '<th>Métrica de Negocio</th>' +
                    '<th style="text-align: right;">Real (Tigo)</th>' +
                    '<th style="text-align: right;">Benchmark Competencia / Meta</th>' +
                    '<th style="text-align: right;">Variación / Brecha</th>' +
                    '<th>Lectura Ejecutiva</th>' +
                  '</tr>' +
                '</thead>' +
                '<tbody>' +
                  '<tr>' +
                    '<td class="font-bold">Ofertas Totales Monitoreadas</td>' +
                    '<td style="text-align: right;" class="font-extrabold">' + eb.tigo_offers_count + ' (' + eb.tigo_offers_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_offers_count + ' (' + eb.comp_offers_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold">' + eb.total_offers + ' regional</td>' +
                    '<td>Cobertura completa sobre 41 operadores en los 12 mercados Millicom.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Attach Rate de Addons VAS (OTT/Deportes)</td>' +
                    '<td style="text-align: right;" class="font-extrabold text-[#003F98]">' + eb.tigo_with_vas_count + ' (' + eb.tigo_with_vas_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_with_vas_count + ' (' + eb.comp_with_vas_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#16A34A]">+' + (eb.tigo_with_vas_pct - eb.comp_with_vas_pct).toFixed(1) + ' pp</td>' +
                    '<td>Tigo ancla contenidos en 86.7% de su parrilla comercial, superando la penetración rival.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Mix Hardbundle (HB Incluido Fijo $0)</td>' +
                    '<td style="text-align: right;" class="font-extrabold">' + eb.tigo_hb + ' (' + eb.tigo_hb_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_hb + ' (' + eb.comp_hb_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#DC2626]">' + eb.hb_gap_pp.toFixed(1) + ' pp</td>' +
                    '<td>Brecha estructural: los competidores absorben 10.6 pp más de contenidos en tarifa fija.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Mix Cortesía Temporal (Promo Free Months)</td>' +
                    '<td style="text-align: right;" class="font-extrabold">' + eb.tigo_promo + ' (' + eb.tigo_promo_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_promo + ' (' + eb.comp_promo_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#D97706]">+' + eb.promo_gap_pp.toFixed(1) + ' pp</td>' +
                    '<td>Mayor exposición a churn al expirar meses de cortesía (3–6 meses) frente a rivales con HB definitivo.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Mix Standalone / Con Cobro (SA)</td>' +
                    '<td style="text-align: right;" class="font-extrabold">' + eb.tigo_sa + ' (' + eb.tigo_sa_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_sa + ' (' + eb.comp_sa_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#003F98]">+' + eb.sa_gap_pp.toFixed(1) + ' pp</td>' +
                    '<td>Tigo cobra más addons como opcional puro; protege margen pero reduce atractivo de entrada.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Posición de Precio (Paridad o Ventaja Tigo)</td>' +
                    '<td style="text-align: right;" class="font-extrabold text-[#D97706]">' + eb.tigo_parity_count + ' / ' + eb.comparable_comp_count + ' (' + eb.tigo_parity_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.target_parity_count + ' / ' + eb.comparable_comp_count + ' (&ge;60.0%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#DC2626]">' + eb.parity_gap_vs_60_pp.toFixed(1) + ' pp</td>' +
                    '<td>Se requieren 3 planes en paridad/ventaja para alcanzar la meta mínima de 60.0%.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">Ofensivas del Día (Deltas Ayer vs Hoy)</td>' +
                    '<td style="text-align: right;" class="font-extrabold">' + eb.tigo_deltas_count + ' (' + eb.tigo_deltas_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;">' + eb.comp_deltas_count + ' (' + eb.comp_deltas_pct.toFixed(1) + '%)</td>' +
                    '<td style="text-align: right;" class="font-bold text-[#DC2626]">88.9% rival</td>' +
                    '<td>Presión agresiva de rivales: 4 bajas de precio, 2 nuevos HB, 1 WiFi 7 y 1 upgrade de hardware.</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold" style="color: var(--tigo-text-secondary);">Revenue / Margen % / ARPU / Base</td>' +
                    '<td style="text-align: right;" class="italic text-xs" style="color: var(--tigo-text-secondary);">Dato no disponible</td>' +
                    '<td style="text-align: right;" class="italic text-xs" style="color: var(--tigo-text-secondary);">Entry BUD 2027 N/D</td>' +
                    '<td style="text-align: right;" class="italic text-xs" style="color: var(--tigo-text-secondary);">Dato no disponible</td>' +
                    '<td class="text-xs" style="color: var(--tigo-text-secondary);">Métricas internas de suscriptores y P&L no publicadas en portales web comerciales.</td>' +
                  '</tr>' +
                '</tbody>' +
              '</table>' +
            '</div>' +
          '</div>' +

          '<!-- 3. QUÉ ESTÁ PASANDO Y POR QUÉ -->' +
          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 3</span>' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                '3. Qué Está Pasando y Por Qué (Storytelling Basado en Evidencia)' +
              '</h3>' +
            '</div>' +
            '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">' +
              '<div class="tigo-soft-box p-4 space-y-2" style="border-left: 4px solid var(--tigo-negative);">' +
                '<h4 class="text-sm font-extrabold m-0" style="color: var(--tigo-navy);">' +
                  '1. Los competidores usan Hardbundle masivo para neutralizar la ventaja de marca de Tigo' +
                '</h4>' +
                '<p class="text-xs m-0"><strong>Evidencia:</strong> 47 de 68 addons de competidores (69.1%) son Hardbundle fijo $0, frente a 24 de 41 en Tigo (58.5%), una brecha de -10.6 pp.</p>' +
                '<p class="text-xs m-0"><strong>Causa:</strong> Acuerdos agregados panregionales de OTTs (Disney+, Max, Paramount+) con Claro, Liberty y Movistar que subsidian licencias para elevar retención.</p>' +
                '<p class="text-xs m-0 font-bold" style="color: var(--tigo-negative);"><strong>Implicación:</strong> Riesgo de desconexión neta en clientes que valoran contenidos sin pagar addons adicionales en factura.</p>' +
              '</div>' +
              '<div class="tigo-soft-box p-4 space-y-2" style="border-left: 4px solid var(--tigo-negative);">' +
                '<h4 class="text-sm font-extrabold m-0" style="color: var(--tigo-navy);">' +
                  '2. El 45.8% de las ofertas comparables socava el precio de Tigo hasta en -67.1%' +
                '</h4>' +
                '<p class="text-xs m-0"><strong>Evidencia:</strong> 22 de 48 ofertas rivales directas son más baratas; los pisos más agresivos están en PY (-67.1%), UY (-41.2%), CL (-35.0%), CO (-34.1%) y PA (-31.8%).</p>' +
                '<p class="text-xs m-0"><strong>Causa:</strong> Saturación de despliegue FTTH y guerra de captura de clientes en escalones de entrada y medios (500–600 Mbps).</p>' +
                '<p class="text-xs m-0 font-bold" style="color: var(--tigo-negative);"><strong>Implicación:</strong> Presión directa a la baja sobre el ARPU de entrada y freno en la captación de Gross Adds.</p>' +
              '</div>' +
              '<div class="tigo-soft-box p-4 space-y-2" style="border-left: 4px solid var(--tigo-warning);">' +
                '<h4 class="text-sm font-extrabold m-0" style="color: var(--tigo-navy);">' +
                  '3. Cuatro bajas de precio concentradas hoy en el escalón de 600 a 900 Mbps' +
                '</h4>' +
                '<p class="text-xs m-0"><strong>Evidencia:</strong> WOM Chile baja 600M a $15.990 CLP (-20.0%), Claro Paraguay 600M a 120.000 PYG (-17.2%), Movistar Colombia 900M a $85.990 COP (-10.5%) y +Móvil Panamá 600M a $41.00 USD (-$4.00 USD / -7.1%).</p>' +
                '<p class="text-xs m-0"><strong>Causa:</strong> Comoditización del ancho de banda alto y canibalización de planes premium para retener base posnavideña/Q4.</p>' +
                '<p class="text-xs m-0 font-bold" style="color: #92400E;"><strong>Implicación:</strong> Tigo queda expuesto si no ajusta promociones tácticas en planes de 500 y 1.000 Mbps.</p>' +
              '</div>' +
              '<div class="tigo-soft-box p-4 space-y-2" style="border-left: 4px solid var(--tigo-blue);">' +
                '<h4 class="text-sm font-extrabold m-0" style="color: var(--tigo-navy);">' +
                  '4. Diferenciación por hardware: WiFi 7 y WiFi 6 desplazan al router estándar' +
                '</h4>' +
                '<p class="text-xs m-0"><strong>Evidencia:</strong> Netlife Ecuador introduce WiFi 7 en 850M ($16.96 USD) y Claro Paraguay actualiza a WiFi 6 con doble extensor Mesh en 600M.</p>' +
                '<p class="text-xs m-0"><strong>Causa:</strong> Transición de marketing tecnológico de fibra simétrica hacia experiencia de cobertura residencial completa.</p>' +
                '<p class="text-xs m-0 font-bold" style="color: var(--tigo-blue);"><strong>Implicación:</strong> Oportunidad de defender ticket promedio mediante certificación de cobertura WiFi Mesh en lugar de recortar precio.</p>' +
              '</div>' +
            '</div>' +
          '</div>' +

          '<!-- 4. VISTA POR PAÍS -->' +
          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 4</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                  '4. Vista de Estado por País (12 Mercados LATAM)' +
                '</h3>' +
              '</div>' +
              '<div class="flex items-center gap-2 text-xs font-bold">' +
                '<span class="badge-positive">🟢 ' + eb.status_counts.GREEN + ' En ruta</span>' +
                '<span class="badge-warning">🟡 ' + eb.status_counts.YELLOW + ' En riesgo</span>' +
                '<span class="badge-negative">🔴 ' + eb.status_counts.RED + ' Fuera de ruta</span>' +
              '</div>' +
            '</div>' +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                '<thead>' +
                  '<tr>' +
                    '<th>País / Mercado</th>' +
                    '<th style="text-align: center;">Planes (Tigo/Comp)</th>' +
                    '<th style="text-align: center;">Rivales más Baratos</th>' +
                    '<th style="text-align: right;">Mayor Brecha Rival</th>' +
                    '<th style="text-align: center;">Mix VAS Tigo</th>' +
                    '<th style="text-align: center;">HB Rival</th>' +
                    '<th style="text-align: center;">Deltas Hoy</th>' +
                    '<th style="text-align: center;">Estado</th>' +
                    '<th>Lectura de Situación Competitiva</th>' +
                  '</tr>' +
                '</thead>' +
                '<tbody>' +
                  countryRowsHtml +
                '</tbody>' +
              '</table>' +
            '</div>' +
            '<div class="tigo-soft-box p-3 text-xs leading-relaxed space-y-1">' +
              '<p class="m-0"><strong>Mercados que impulsan positivamente el resultado:</strong> Guatemala (GT) y Honduras (HN) operan en ruta (🟢) con liderazgo en paridad y fuerte anclaje de Tigo Sports en planes fijos y móviles.</p>' +
              '<p class="m-0"><strong>Mercados con mayor deterioro competitivo:</strong> Panamá (PA) y Paraguay (PY) fuera de ruta (🔴), impactados por el retiro del piso de 200M en Tigo Panamá ($41.00 USD vs $31.00 USD de +Móvil) y la agresiva promoción de Claro Paraguay a 120.000 PYG (-67.1% vs Tigo).</p>' +
            '</div>' +
          '</div>' +

          '<!-- 5. RIESGOS Y OPORTUNIDADES -->' +
          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 5</span>' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                '5. Matriz Cuantificada de Riesgos y Oportunidades' +
              '</h3>' +
            '</div>' +
            '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">' +
              '<div class="space-y-2.5">' +
                '<h4 class="text-xs font-extrabold uppercase tracking-wider m-0 flex items-center gap-1.5" style="color: var(--tigo-negative);">' +
                  '<span>&#9888;</span><span>Riesgos Comerciales Cuantificados</span>' +
                '</h4>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-negative);">' +
                  '<div class="font-bold text-[#DC2626]">Riesgo 1: Fuga en entrada en Panamá ($10.00 USD/mes de brecha)</div>' +
                  '<p class="m-0">El retiro de Internet Hogar 200M ($37.00 USD) elevó el piso de entrada a $41.00 USD (300M), dejando a +Móvil con ventaja de $10.00 USD en su plan de 350M a $31.00 USD.</p>' +
                '</div>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-negative);">' +
                  '<div class="font-bold text-[#DC2626]">Riesgo 2: Vencimiento de cortesías temporales (14.6% de addons Tigo)</div>' +
                  '<p class="m-0">6 addons de Tigo operan con 3 meses gratis. Al expirar el beneficio sin conversión automática a pago, el riesgo de churn se incrementa frente a rivales con HB definitivo.</p>' +
                '</div>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-negative);">' +
                  '<div class="font-bold text-[#DC2626]">Riesgo 3: Concentración de undercut en 5 mercados (59.1% de planes más baratos)</div>' +
                  '<p class="m-0">13 de los 22 planes rivales con precio menor se ubican en PA, CO, PY, UY y CL, concentrando la presión competitiva sobre plazas clave.</p>' +
                '</div>' +
              '</div>' +

              '<div class="space-y-2.5">' +
                '<h4 class="text-xs font-extrabold uppercase tracking-wider m-0 flex items-center gap-1.5" style="color: var(--tigo-positive);">' +
                  '<span>&#10003;</span><span>Oportunidades Comerciales Cuantificadas</span>' +
                '</h4>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-positive);">' +
                  '<div class="font-bold text-[#16A34A]">Oportunidad 1: Cierre de brecha con solo 3 planes en paridad</div>' +
                  '<p class="m-0">Ajustar 3 planes comparables (1 en Colombia 500M, 1 en Panamá 300M y 1 en Paraguay 300M) eleva la paridad del 54.2% al 60.4%, alcanzando el benchmark meta.</p>' +
                '</div>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-positive);">' +
                  '<div class="font-bold text-[#16A34A]">Oportunidad 2: Liderazgo exclusivo con Tigo Sports en CA y PY</div>' +
                  '<p class="m-0">Tigo Sports mantiene exclusividad deportiva en GT, HN y PY. Ningún competidor (Claro, Personal Flow) puede replicar este valor en sus paquetes de TV/Hogar.</p>' +
                '</div>' +
                '<div class="tigo-soft-box p-3 text-xs space-y-1.5" style="border-left: 3px solid var(--tigo-positive);">' +
                  '<div class="font-bold text-[#16A34A]">Oportunidad 3: Monetización de WiFi 6 Mesh en Costa Rica y Colombia</div>' +
                  '<p class="m-0">Empaquetar extensores Mesh bonificados en planes de 500+ Mbps permite neutralizar las bajas de precio de Movistar y Claro sin degradar ARPU mensual.</p>' +
                '</div>' +
              '</div>' +
            '</div>' +
          '</div>' +

          '<!-- 6. BRECHA A LA META -->' +
          '<div class="tigo-card p-5 space-y-3">' +
            '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 6</span>' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                '6. Brecha a la Meta y Palancas de Cierre' +
              '</h3>' +
            '</div>' +
            '<p class="text-sm font-bold m-0" style="color: var(--tigo-navy);">' +
              'Faltan <strong>' + eb.plans_needed_for_60pct + ' planes en paridad o ventaja competitiva</strong> (brecha de ' + Math.abs(eb.parity_gap_vs_60_pp).toFixed(1) + ' pp frente al umbral objetivo del 60.0%), alcanzable en un plazo estimado de <strong>30 días (cierre de mes)</strong> mediante 4 palancas directas:' +
            '</p>' +
            '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">' +
              '<div class="tigo-soft-box p-3 space-y-1">' +
                '<strong class="block" style="color: var(--tigo-blue);">1. Palanca Precio:</strong>' +
                '<span>Ajustar promociones de entrada en Panamá ($34.99 USD x 6 meses) y Colombia ($99.900 COP en Estrato 3) para neutralizar la ventaja de +Móvil y Claro.</span>' +
              '</div>' +
              '<div class="tigo-soft-box p-3 space-y-1">' +
                '<strong class="block" style="color: var(--tigo-blue);">2. Palanca Base:</strong>' +
                '<span>Focalizar retención proactiva sobre el 14.6% de clientes con cortesías OTT activas antes del mes 3 para evitar desconexiones hacia ofertas con Hardbundle.</span>' +
              '</div>' +
              '<div class="tigo-soft-box p-3 space-y-1">' +
                '<strong class="block" style="color: var(--tigo-blue);">3. Palanca Mix HB / SA:</strong>' +
                '<span>Rebalancear 4 addons clave a Hardbundle en planes de 500+ Mbps (cerrando la brecha de 10.6 pp frente a los rivales) sin incrementar el precio final.</span>' +
              '</div>' +
              '<div class="tigo-soft-box p-3 space-y-1">' +
                '<strong class="block" style="color: var(--tigo-blue);">4. Palanca Costos / Contenido:</strong>' +
                '<span>Renegociar tiers OTT con Disney+ y Max a esquema de costo fijo mayorista por usuario activo, mitigando el impacto en margen de la inclusión en HB.</span>' +
              '</div>' +
            '</div>' +
          '</div>' +

          '<!-- 7. DECISIONES Y PRÓXIMOS PASOS -->' +
          '<div class="tigo-card p-5 space-y-3">' +
            '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<span class="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 7</span>' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                '7. Decisiones Propuestas y Próximos Pasos para Dirección' +
              '</h3>' +
            '</div>' +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                '<thead>' +
                  '<tr>' +
                    '<th>Propuesta de Acción para Discutir</th>' +
                    '<th>Responsable Sugerido</th>' +
                    '<th>Impacto Esperado en Negocio</th>' +
                    '<th style="text-align: center;">Horizonte</th>' +
                  '</tr>' +
                '</thead>' +
                '<tbody>' +
                  '<tr>' +
                    '<td class="font-bold">1. Reabrir escalón promocional de entrada en Panamá (300M a $34.99 USD) para frenar migración a +Móvil ($31.00 USD).</td>' +
                    '<td class="font-semibold" style="color: var(--tigo-navy);">Comercial Hogar Panamá</td>' +
                    '<td>Protección de Gross Adds y reducción estimada del 25% en churn de entrada.</td>' +
                    '<td style="text-align: center;" class="font-bold">Inmediato (7 días)</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">2. Transformar cortesía de Prime Video (3m) en Hardbundle permanente en Dúo 500M Colombia ante rebaja de Movistar (-10.5%).</td>' +
                    '<td class="font-semibold" style="color: var(--tigo-navy);">Estrategia VAS Colombia</td>' +
                    '<td>Neutraliza la propuesta de valor de Movistar 900M sin reducir la tarifa de $109.900 COP.</td>' +
                    '<td style="text-align: center;" class="font-bold">15 días</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">3. Implementar campaña táctica de contraataque en Paraguay respondiendo al plan 600M de Claro con Mesh bonificado.</td>' +
                    '<td class="font-semibold" style="color: var(--tigo-navy);">Comercial Tigo Paraguay</td>' +
                    '<td>Evita guerra directa de precios en guaraníes destacando Tigo Sports + WiFi 6.</td>' +
                    '<td style="text-align: center;" class="font-bold">10 días</td>' +
                  '</tr>' +
                  '<tr>' +
                    '<td class="font-bold">4. Convocar comité de contenidos regional para estandarizar acuerdos mayoristas HB en Disney+ y Max.</td>' +
                    '<td class="font-semibold" style="color: var(--tigo-navy);">VP Contenidos / Negociación Regional</td>' +
                    '<td>Cierre de la brecha de 10.6 pp en Hardbundle optimizando el costo unitario por suscriptor.</td>' +
                    '<td style="text-align: center;" class="font-bold">30 días</td>' +
                  '</tr>' +
                '</tbody>' +
              '</table>' +
            '</div>' +
          '</div>';
      }


      function formatBundleType(bt) {
        if (bt === "SOLO_INTERNET") return "Solo Internet";
        if (bt === "DUO_INTERNET_TV") return "Dúo Internet + TV";
        if (bt === "TRIO") return "Trío Hogar";
        if (bt === "CONVERGENTE") return "Convergente Hogar + Móvil";
        if (bt === "MOVIL_POSPAGO") return "Móvil Pospago";
        return "Plan Hogar";
      }

      function formatBandwidthFull(hs) {
        if (!hs || !hs.download_mbps) return "Por Cobertura / Móvil";
        let s = hs.download_mbps + " Mbps ↓";
        if (hs.upload_mbps !== null && hs.upload_mbps !== undefined) {
          s += " / " + hs.upload_mbps + " Mbps ↑";
        } else if (hs.symmetric_speed === true) {
          s += " / " + hs.download_mbps + " Mbps ↑";
        }
        return s;
      }

      function formatTvFull(hs) {
        if (!hs || (!hs.tv_channels_count && !hs.tv_deco_boxes)) return "Sin TV lineal";
        const parts = [];
        if (hs.tv_channels_count) parts.push(hs.tv_channels_count + " canales");
        if (hs.tv_deco_boxes) parts.push(hs.tv_deco_boxes + " deco(s)");
        return parts.join(" • ");
      }

      function formatTaxAndInstall(pricing) {
        if (!pricing) return "";
        const tax = pricing.taxes_included === true
          ? "IVA incl."
          : (pricing.taxes_included === false ? "+ Impuestos" : "Imp. N/D");
        const inst = pricing.installation_fee === 0
          ? "Instalación $0"
          : (pricing.installation_fee ? "Inst. " + pricing.installation_fee + " " + (pricing.currency || "") : "");
        return [tax, inst].filter(Boolean).join(" • ");
      }

      function formatVasShortCondition(vas, currency) {
        if (vas.commercial_model === "INCLUDED_HARD_BUNDLE") return "Incluido Fijo $0";
        if (vas.free_months) {
          const after = vas.regular_price_after_promo ? " (luego " + formatMoney(vas.regular_price_after_promo, currency) + ")" : "";
          return vas.free_months + "m Gratis" + after;
        }
        if (vas.promo_price !== null && vas.promo_price !== undefined) {
          const after = vas.regular_price_after_promo ? " (luego " + formatMoney(vas.regular_price_after_promo, currency) + ")" : "";
          return "Promo " + formatMoney(vas.promo_price, currency) + after;
        }
        if (vas.regular_price_after_promo !== null && vas.regular_price_after_promo !== undefined) {
          return "Addon " + formatMoney(vas.regular_price_after_promo, currency);
        }
        if (vas.commercial_model === "PROMO_FREE_MONTHS") return "Cortesía Promo";
        if (vas.commercial_model === "STANDALONE_PAID") return "Addon Factura";
        return vas.commercial_model || "Addon";
      }

      function vasModelBadgeClass(model) {
        if (model === "INCLUDED_HARD_BUNDLE") return "badge-positive";
        if (model === "PROMO_FREE_MONTHS") return "badge-warning";
        if (model === "DISCOUNTED_ADDON") return "badge-info";
        return "badge-comp";
      }

      function getOfferVasCodes(offer) {
        if (offer.vas_provider_codes && offer.vas_provider_codes.length) return offer.vas_provider_codes;
        return (offer.vas_addons || []).map(function (a) { return a.provider; });
      }

      function offerMatchesAddonCriteria(offer) {
        const addons = offer.vas_addons || [];
        if (state.onlyWithAddons && addons.length === 0) return false;
        if (state.selectedVasModel !== "ALL") {
          const hasModel = addons.some(function (a) { return a.commercial_model === state.selectedVasModel; });
          if (!hasModel) return false;
        }
        if (state.selectedVasProviders.length > 0) {
          const codes = getOfferVasCodes(offer);
          const hasProvider = codes.some(function (c) { return state.selectedVasProviders.indexOf(c) >= 0; });
          if (!hasProvider) return false;
        }
        return true;
      }

      function matchesCommonFilters(item, vasCodes) {
        if (state.operatorScope === "MILLICOM" && !item.is_millicom) return false;
        if (state.operatorScope === "COMPETITORS" && item.is_millicom) return false;
        if (state.selectedCountries.length > 0 && state.selectedCountries.indexOf(item.country_iso) < 0) return false;
        if (state.selectedOperators.length > 0 && state.selectedOperators.indexOf(item.operator) < 0) return false;
        if (state.selectedSegments.length > 0 && state.selectedSegments.indexOf(item.segment) < 0) return false;
        if (state.selectedBundleType !== "ALL" && item.bundle_type && item.bundle_type !== state.selectedBundleType) return false;
        if (state.onlyWithAddons && (!vasCodes || vasCodes.length === 0)) return false;
        if (state.selectedVasProviders.length > 0) {
          const ok = (vasCodes || []).some(function (c) { return state.selectedVasProviders.indexOf(c) >= 0; });
          if (!ok) return false;
        }
        if (state.searchQuery.trim()) {
          const q = state.searchQuery.trim().toLowerCase();
          const hs = item.home_specs || {};
          const hay = [
            item.plan_name,
            item.operator,
            item.country_iso,
            item.offer_uid,
            item.summary || "",
            hs.wifi_hardware || "",
            String(hs.download_mbps || ""),
            (vasCodes || []).join(" ")
          ].join(" ").toLowerCase();
          if (hay.indexOf(q) < 0) return false;
        }
        return true;
      }

      function computeFilteredOffers() {
        return OFFERS.filter(function (o) {
          if (!offerMatchesAddonCriteria(o)) return false;
          return matchesCommonFilters(o, getOfferVasCodes(o));
        });
      }

      function computeCountryHomeOffers() {
        const subset = OFFERS.filter(function (o) {
          if (o.country_iso !== state.benchmarkCountry) return false;
          if (state.selectedSegments.length > 0 && state.selectedSegments.indexOf(o.segment) < 0) return false;
          if (state.selectedBundleType !== "ALL" && o.bundle_type !== state.selectedBundleType) return false;
          if (state.operatorScope === "MILLICOM" && !o.is_millicom) return false;
          if (state.operatorScope === "COMPETITORS" && o.is_millicom) return false;
          if (state.selectedOperators.length > 0 && state.selectedOperators.indexOf(o.operator) < 0) return false;
          if (!offerMatchesAddonCriteria(o)) {
            if (!(o.is_millicom && state.keepTigoReferenceWhenFiltering && state.operatorScope !== "COMPETITORS")) {
              return false;
            }
          }
          if (state.searchQuery.trim()) {
            const q = state.searchQuery.trim().toLowerCase();
            const hs = o.home_specs || {};
            const hay = [
              o.plan_name,
              o.operator,
              hs.wifi_hardware || "",
              String(hs.download_mbps || ""),
              getOfferVasCodes(o).join(" ")
            ].join(" ").toLowerCase();
            if (hay.indexOf(q) < 0) return false;
          }
          return true;
        });

        return subset.slice().sort(function (a, b) {
          if (state.benchmarkSortBy === "tigo_first") {
            if (a.is_millicom !== b.is_millicom) return a.is_millicom ? -1 : 1;
            return ((b.home_specs || {}).download_mbps || 0) - ((a.home_specs || {}).download_mbps || 0);
          }
          if (state.benchmarkSortBy === "speed_desc") {
            return ((b.home_specs || {}).download_mbps || 0) - ((a.home_specs || {}).download_mbps || 0);
          }
          if (state.benchmarkSortBy === "price_asc") {
            const pa = (a.effective_price !== null && a.effective_price !== undefined) ? a.effective_price : Number.MAX_SAFE_INTEGER;
            const pb = (b.effective_price !== null && b.effective_price !== undefined) ? b.effective_price : Number.MAX_SAFE_INTEGER;
            return pa - pb;
          }
          return 0;
        });
      }

      function computeFilteredDeltas() {
        return DELTAS.filter(function (d) {
          if (state.selectedDeltaTypes.length > 0 && state.selectedDeltaTypes.indexOf(d.delta_type) < 0) return false;
          return matchesCommonFilters(d, d.vas_providers_affected || []);
        });
      }

      function computeFilteredVasMatrix() {
        return VAS_MATRIX.filter(function (row) {
          if (state.operatorScope === "MILLICOM" && !row.is_millicom) return false;
          if (state.operatorScope === "COMPETITORS" && row.is_millicom) return false;
          if (state.selectedCountries.length > 0 && state.selectedCountries.indexOf(row.country_iso) < 0) return false;
          if (state.selectedOperators.length > 0 && state.selectedOperators.indexOf(row.operator) < 0) return false;
          if (state.selectedSegments.length > 0 && state.selectedSegments.indexOf(row.segment) < 0) return false;
          if (state.selectedVasModel !== "ALL" && row.commercial_model !== state.selectedVasModel) return false;
          if (state.selectedVasProviders.length > 0 && state.selectedVasProviders.indexOf(row.provider) < 0) return false;
          if (state.searchQuery.trim()) {
            const q = state.searchQuery.trim().toLowerCase();
            const hay = (row.plan_name + " " + row.operator + " " + row.provider + " " + (row.tier_or_package || "")).toLowerCase();
            if (hay.indexOf(q) < 0) return false;
          }
          return true;
        });
      }

      function renderOfferCardHtml(o) {
        const isTigo = Boolean(o.is_millicom);
        const hs = o.home_specs || {};
        const p = o.pricing || {};
        const tc = o.tigo_comparison;
        const addons = o.vas_addons || [];

        let gapHtml = "";
        if (!isTigo && tc) {
          const pills = [];
          if (tc.effective_price_diff !== null && tc.effective_price_diff !== undefined) {
            const diff = tc.effective_price_diff;
            const pct = tc.effective_price_pct !== null && tc.effective_price_pct !== undefined
              ? " (" + (diff > 0 ? "+" : "") + tc.effective_price_pct.toFixed(1) + "%)"
              : "";
            if (diff === 0) {
              pills.push('<span class="badge-comp">Igual precio que Tigo</span>');
            } else if (diff < 0) {
              pills.push('<span class="badge-negative">' + escHtml(formatSignedMoney(diff, p.currency) + pct + " más barato que Tigo") + "</span>");
            } else {
              pills.push('<span class="badge-positive">' + escHtml(formatSignedMoney(diff, p.currency) + pct + " más caro que Tigo") + "</span>");
            }
          }
          if (tc.speed_diff_mbps !== null && tc.speed_diff_mbps !== undefined) {
            const sd = tc.speed_diff_mbps;
            const sText = sd === 0 ? "Misma velocidad vs Tigo" : ((sd > 0 ? "+" : "") + sd + " Mbps vs Tigo");
            pills.push('<span class="badge-info">' + escHtml(sText) + "</span>");
          }
          if (tc.extra_vas_vs_tigo && tc.extra_vas_vs_tigo.length > 0) {
            pills.push('<span class="badge-warning">+ Addons vs Tigo: ' + escHtml(tc.extra_vas_vs_tigo.join(", ")) + "</span>");
          }
          if (pills.length > 0) {
            gapHtml = '<div class="flex flex-wrap gap-1.5">' + pills.join("") + "</div>";
          }
        }

        const effText = (o.effective_price !== null && o.effective_price !== undefined)
          ? formatMoney(o.effective_price, p.currency)
          : "Por cobertura";
        const promoSub = p.promo_duration_months
          ? "Promo x " + p.promo_duration_months + " meses"
          : (p.promo_monthly_price !== null && p.promo_monthly_price !== undefined ? "Tarifa Promocional" : "Tarifa Vigente");
        const regText = (p.regular_monthly_price !== null && p.regular_monthly_price !== undefined)
          ? formatMoney(p.regular_monthly_price, p.currency)
          : "Por cobertura";

        const addonsHtml = addons.length === 0
          ? '<span class="text-xs italic block" style="color: var(--tigo-text-secondary);">Sin addons OTT/Deportes incluidos</span>'
          : addons.map(function (v) {
              return (
                '<div class="rounded-lg px-2.5 py-1.5 text-xs flex items-center justify-between gap-2" style="background: #F4F8FE; border: 1px solid #D3E3FA;">' +
                  '<span class="font-bold" style="color: var(--tigo-navy);">' +
                    escHtml(v.provider + (v.tier_or_package ? " • " + v.tier_or_package : "")) +
                  "</span>" +
                  '<span class="' + vasModelBadgeClass(v.commercial_model) + '">' +
                    escHtml(formatVasShortCondition(v, p.currency)) +
                  "</span>" +
                "</div>"
              );
            }).join("");

        return (
          '<div class="' + (isTigo ? "tigo-ref-offer-card" : "tigo-comp-offer-card") + ' p-4 space-y-3 flex flex-col justify-between">' +
            '<div class="space-y-2.5">' +
              '<div class="flex items-start justify-between gap-2">' +
                "<div>" +
                  '<div class="flex flex-wrap items-center gap-1.5">' +
                    (isTigo
                      ? '<span class="badge-tigo"><span class="badge-tigo-dot"></span>' + escHtml(o.operator) + " HOGAR</span>"
                      : '<span class="badge-comp">' + escHtml(o.operator) + "</span>") +
                    '<span class="badge-info">' + escHtml(formatBundleType(o.bundle_type)) + "</span>" +
                    (hs.technology ? '<span class="px-2 py-0.5 rounded text-xs font-extrabold" style="background:#EEF2FF;color:var(--tigo-navy);">' + escHtml(hs.technology) + "</span>" : "") +
                  "</div>" +
                  '<h4 class="text-sm font-extrabold m-0 mt-2" style="color: var(--tigo-navy);">' + escHtml(o.plan_name) + "</h4>" +
                "</div>" +
                '<button type="button" data-action="open-offer-evidence" data-uid="' + escHtml(o.offer_uid) + '" class="tigo-btn-evidence">Ver Evidencia</button>' +
              "</div>" +
              gapHtml +
              '<div class="tigo-soft-box p-3 grid grid-cols-2 gap-2.5 text-xs">' +
                "<div>" +
                  '<span class="block font-medium" style="color: var(--tigo-text-secondary);">Precio Hoy (Efectivo):</span>' +
                  '<span class="text-base font-black block mt-0.5" style="color: ' + (isTigo ? "var(--tigo-navy)" : "var(--tigo-text)") + ';">' + escHtml(effText) + "</span>" +
                  '<span class="block" style="color: var(--tigo-text-secondary);">' + escHtml(promoSub) + "</span>" +
                "</div>" +
                "<div>" +
                  '<span class="block font-medium" style="color: var(--tigo-text-secondary);">Precio Regular Pleno:</span>' +
                  '<span class="text-sm font-bold block mt-0.5" style="color: var(--tigo-text);">' + escHtml(regText) + "</span>" +
                  '<span class="block" style="color: var(--tigo-text-secondary);">' + escHtml(formatTaxAndInstall(p)) + "</span>" +
                "</div>" +
              "</div>" +
              '<div class="space-y-1 text-xs">' +
                '<div class="flex justify-between gap-2"><span style="color: var(--tigo-text-secondary);">Velocidad Bajada / Subida:</span><strong style="color: var(--tigo-navy);">' + escHtml(formatBandwidthFull(hs)) + "</strong></div>" +
                '<div class="flex justify-between gap-2"><span style="color: var(--tigo-text-secondary);">Equipos WiFi:</span><span class="font-semibold text-right">' + escHtml(hs.wifi_hardware || "Estándar / N/D") + "</span></div>" +
                '<div class="flex justify-between gap-2"><span style="color: var(--tigo-text-secondary);">TV Canales / Decos:</span><span class="font-semibold text-right">' + escHtml(formatTvFull(hs)) + "</span></div>" +
              "</div>" +
            "</div>" +
            '<div class="pt-2.5 space-y-1.5" style="border-top: 1px solid var(--tigo-border);">' +
              '<span class="text-xs font-extrabold block" style="color: var(--tigo-blue);">Addons Entretenimiento &amp; Deportes (' + addons.length + "):</span>" +
              addonsHtml +
            "</div>" +
          "</div>"
        );
      }

      function renderDropdownMenus() {
        document.getElementById("dd-label-operators").textContent = state.selectedOperators.length
          ? state.selectedOperators.join(", ")
          : "Todos los operadores (" + OPERATORS.length + ")";

        document.getElementById("dd-menu-operators").innerHTML = OPERATORS.map(function (op) {
          const checked = state.selectedOperators.indexOf(op.name) >= 0 ? "checked" : "";
          return (
            '<label class="flex items-center justify-between px-2.5 py-1.5 rounded hover:bg-[#EEF5FF] cursor-pointer text-xs">' +
              '<span class="flex items-center gap-2">' +
                '<input type="checkbox" data-dd-check="operator" value="' + escHtml(op.name) + '" ' + checked + ' style="accent-color: var(--tigo-blue);" />' +
                '<span class="' + (op.is_millicom ? "font-extrabold" : "font-medium") + '" style="color: ' + (op.is_millicom ? "var(--tigo-navy)" : "var(--tigo-text)") + ';">' + escHtml(op.name) + "</span>" +
              "</span>" +
              (op.is_millicom ? '<span class="badge-tigo"><span class="badge-tigo-dot"></span>TIGO</span>' : "") +
            "</label>"
          );
        }).join("");

        document.getElementById("dd-label-segments").textContent = state.selectedSegments.length
          ? state.selectedSegments.join(", ")
          : "Todos los segmentos (" + SEGMENTS.length + ")";

        document.getElementById("dd-menu-segments").innerHTML = SEGMENTS.map(function (seg) {
          const checked = state.selectedSegments.indexOf(seg) >= 0 ? "checked" : "";
          return (
            '<label class="flex items-center gap-2 px-2.5 py-1.5 rounded hover:bg-[#EEF5FF] cursor-pointer text-xs font-medium">' +
              '<input type="checkbox" data-dd-check="segment" value="' + escHtml(seg) + '" ' + checked + ' style="accent-color: var(--tigo-blue);" />' +
              "<span>" + escHtml(seg) + "</span>" +
            "</label>"
          );
        }).join("");

        document.getElementById("dd-label-deltas").textContent = state.selectedDeltaTypes.length
          ? state.selectedDeltaTypes.join(", ")
          : "Todos los tipos de delta";

        document.getElementById("dd-menu-deltas").innerHTML = DELTA_TYPES.map(function (dt) {
          const checked = state.selectedDeltaTypes.indexOf(dt) >= 0 ? "checked" : "";
          return (
            '<label class="flex items-center gap-2 px-2.5 py-1.5 rounded hover:bg-[#EEF5FF] cursor-pointer text-xs font-medium">' +
              '<input type="checkbox" data-dd-check="delta" value="' + escHtml(dt) + '" ' + checked + ' style="accent-color: var(--tigo-blue);" />' +
              "<span>" + escHtml(dt) + "</span>" +
            "</label>"
          );
        }).join("");

        ["operators", "segments", "deltas"].forEach(function (dd) {
          document.getElementById("dd-menu-" + dd).classList.toggle("is-hidden", state.openDropdown !== dd);
        });
      }

      function populateCountrySelectOnce() {
        const sel = document.getElementById("benchmark-country-select");
        sel.innerHTML = COUNTRY_ORDER.map(function (iso) {
          const meta = MARKETS[iso] || { country_name: iso, currency: "", flag: "" };
          const cnt = OFFERS.filter(function (o) { return o.country_iso === iso; }).length;
          return (
            '<option value="' + escHtml(iso) + '">' +
              escHtml((meta.flag ? meta.flag + " " : "") + iso + " — " + meta.country_name + " (" + meta.currency + ") [" + cnt + " ofertas]") +
            "</option>"
          );
        }).join("");
      }

      function renderAll() {
        const filteredOffers = computeFilteredOffers();
        const countryHomeOffers = computeCountryHomeOffers();
        const filteredDeltas = computeFilteredDeltas();
        const filteredVasRows = computeFilteredVasMatrix();

        state.lastFilteredDeltas = filteredDeltas;
        state.lastFilteredVasRows = filteredVasRows;

        const k = PAYLOAD.kpis || {};
        const addonsCountTotal = k.offers_with_addons !== undefined
          ? k.offers_with_addons
          : OFFERS.filter(function (o) { return (o.vas_addons || []).length > 0; }).length;

        // Header Addon Button
        const hdrAddonBtn = document.getElementById("header-addons-btn");
        if (state.onlyWithAddons) {
          hdrAddonBtn.style.backgroundColor = "var(--tigo-yellow)";
          hdrAddonBtn.style.color = "var(--tigo-navy)";
          hdrAddonBtn.style.border = "1px solid #FDE047";
          hdrAddonBtn.style.boxShadow = "0 4px 14px rgba(255, 203, 5, 0.35)";
        } else {
          hdrAddonBtn.style.backgroundColor = "rgba(255, 255, 255, 0.12)";
          hdrAddonBtn.style.color = "#FFFFFF";
          hdrAddonBtn.style.border = "1px solid rgba(255, 203, 5, 0.55)";
          hdrAddonBtn.style.boxShadow = "none";
        }
        hdrAddonBtn.innerHTML =
          "<span>&#127916;</span>" +
          "<span>" + (state.onlyWithAddons ? "Viendo Solo Ofertas con Addons ✓" : "Ver Ofertas con Addons Filtradas") + "</span>" +
          '<span class="px-2 py-0.5 rounded-full text-xs font-black" style="background: ' +
            (state.onlyWithAddons ? "var(--tigo-navy)" : "var(--tigo-yellow)") + "; color: " +
            (state.onlyWithAddons ? "#FFFFFF" : "var(--tigo-navy)") + ';">' +
            escHtml(addonsCountTotal) +
          "</span>";

        // Header Scope Buttons
        document.querySelectorAll(".hdr-scope-btn").forEach(function (btn) {
          const active = btn.getAttribute("data-scope") === state.operatorScope;
          if (active) {
            btn.style.backgroundColor = "#FFFFFF";
            btn.style.color = "var(--tigo-navy)";
            btn.style.fontWeight = "800";
          } else {
            btn.style.backgroundColor = "transparent";
            btn.style.color = "#E2E8F0";
            btn.style.fontWeight = "600";
          }
        });

        // 1. Top KPI Bar (Exact 7 KPI cards in corporate Tigo style)
        const kpiCards = [
          {
            label: "Países Activos",
            val: String(k.active_countries_monitored || 0),
            sub: "/ " + String(k.catalog_countries_total || 12) + " mercados",
            accent: "var(--tigo-navy)",
            valColor: "var(--tigo-navy)"
          },
          {
            label: "Ofertas Hoy (Filtradas)",
            val: String(filteredOffers.length),
            sub: "de " + String(k.total_offers_tracked || OFFERS.length) + " regionales",
            accent: "var(--tigo-bright-blue)",
            valColor: "var(--tigo-blue)"
          },
          {
            label: "Ofertas con Addons",
            val: String(addonsCountTotal),
            sub: state.onlyWithAddons ? "Quitar filtro ✓" : "Clic para filtrar OTT",
            accent: "var(--tigo-yellow)",
            valColor: "var(--tigo-navy)",
            action: "toggle-addons",
            pill: "OTT / Sports"
          },
          {
            label: "Cambios Hoy (Deltas)",
            val: String(filteredDeltas.length),
            sub: "de " + String(k.total_changes_detected || DELTAS.length) + " detectados",
            accent: "var(--tigo-warning)",
            valColor: "#B45309"
          },
          {
            label: "Bajas de Precio Hoy",
            val: String(k.price_drops || 0),
            sub: "Alerta Promo",
            accent: "var(--tigo-negative)",
            valColor: "var(--tigo-negative)",
            pillClass: "badge-negative"
          },
          {
            label: "Alzas de Precio",
            val: String(k.price_increases || 0),
            sub: "Tarifa",
            accent: "var(--tigo-positive)",
            valColor: "var(--tigo-positive)",
            pillClass: "badge-positive"
          },
          {
            label: "Movimientos VAS / Planes",
            val: String((k.vas_addon_changes || 0) + (k.new_or_removed_plans || 0)),
            sub: String(k.vas_addon_changes || 0) + " VAS / " + String(k.new_or_removed_plans || 0) + " Plan",
            accent: "var(--tigo-blue)",
            valColor: "var(--tigo-blue)"
          }
        ];

        document.getElementById("kpi-bar").innerHTML = kpiCards.map(function (c) {
          const actionAttr = c.action ? ' data-action="' + c.action + '"' : "";
          const clickCls = c.action ? " tigo-kpi-clickable" : "";
          return (
            '<div class="tigo-kpi' + clickCls + '"' + actionAttr + ' style="border-top: 4px solid ' + c.accent + ';">' +
              '<div class="text-xs font-bold flex items-center justify-between gap-1" style="color: var(--tigo-text-secondary);">' +
                "<span>" + escHtml(c.label) + "</span>" +
                (c.pill ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-extrabold" style="background:#FFF8DB;color:#92400E;border:1px solid #FDE68A;">' + escHtml(c.pill) + "</span>" : "") +
              "</div>" +
              '<div class="mt-1.5 flex items-baseline justify-between gap-2">' +
                '<span class="text-2xl font-black" style="color: ' + c.valColor + ';">' + escHtml(c.val) + "</span>" +
                '<span class="text-xs font-semibold" style="color: var(--tigo-text-secondary);">' + escHtml(c.sub) + "</span>" +
              "</div>" +
            "</div>"
          );
        }).join("");

        // Active filter count badge
        const activeFilterCount =
          state.selectedCountries.length +
          state.selectedOperators.length +
          state.selectedSegments.length +
          state.selectedDeltaTypes.length +
          state.selectedVasProviders.length +
          (state.onlyWithAddons ? 1 : 0) +
          (state.selectedVasModel !== "ALL" ? 1 : 0) +
          (state.selectedBundleType !== "ALL" ? 1 : 0) +
          (state.operatorScope !== "ALL" ? 1 : 0) +
          (state.searchQuery.trim() ? 1 : 0);

        const filterBadge = document.getElementById("active-filter-badge");
        if (activeFilterCount > 0) {
          filterBadge.textContent = activeFilterCount + " filtros activos";
          filterBadge.classList.remove("is-hidden");
        } else {
          filterBadge.classList.add("is-hidden");
        }

        // Panel Addons toggle button & panel highlight
        const panelAddonBtn = document.getElementById("panel-addons-btn");
        if (state.onlyWithAddons) {
          panelAddonBtn.style.backgroundColor = "var(--tigo-navy)";
          panelAddonBtn.style.borderColor = "var(--tigo-navy)";
          panelAddonBtn.style.color = "#FFFFFF";
        } else {
          panelAddonBtn.style.backgroundColor = "var(--tigo-surface)";
          panelAddonBtn.style.borderColor = "var(--tigo-blue)";
          panelAddonBtn.style.color = "var(--tigo-navy)";
        }
        panelAddonBtn.innerHTML =
          "<span>&#127916;</span><span>" +
          (state.onlyWithAddons ? "Filtro Activo: Solo Ofertas con Addons ✓" : "Activar: Solo Ofertas con Addons") +
          "</span>";

        const addonPanel = document.getElementById("addon-filter-panel");
        if (state.onlyWithAddons || state.selectedVasProviders.length > 0 || state.selectedVasModel !== "ALL") {
          addonPanel.style.backgroundColor = "#EFF6FF";
          addonPanel.style.borderColor = "var(--tigo-bright-blue)";
        } else {
          addonPanel.style.backgroundColor = "var(--tigo-surface-soft)";
          addonPanel.style.borderColor = "var(--tigo-border)";
        }

        // VAS Commercial Model buttons
        document.querySelectorAll(".vas-model-btn").forEach(function (btn) {
          const active = btn.getAttribute("data-model") === state.selectedVasModel;
          if (active) {
            btn.style.backgroundColor = "var(--tigo-blue)";
            btn.style.color = "#FFFFFF";
            btn.style.fontWeight = "700";
          } else {
            btn.style.backgroundColor = "transparent";
            btn.style.color = "var(--tigo-text-secondary)";
            btn.style.fontWeight = "600";
          }
        });

        // VAS Provider Chips
        document.getElementById("vas-chips-container").innerHTML = PRESENT_VAS.map(function (vp) {
          const active = state.selectedVasProviders.indexOf(vp) >= 0;
          return (
            '<button type="button" data-action="toggle-vas-chip" data-vp="' + escHtml(vp) + '" class="tigo-vas-chip' + (active ? " is-active" : "") + '">' +
              escHtml(vp) +
            "</button>"
          );
        }).join("");

        // Country Pills (12 Markets)
        document.getElementById("country-pills-container").innerHTML = COUNTRY_ORDER.map(function (iso) {
          const meta = MARKETS[iso] || { country_name: iso, flag: "" };
          const cnt = OFFERS.filter(function (o) { return o.country_iso === iso; }).length;
          const active = state.activeTab === "tigo_vs_comp"
            ? state.benchmarkCountry === iso
            : (state.selectedCountries.length === 0 ? false : state.selectedCountries.indexOf(iso) >= 0);
          return (
            '<button type="button" data-action="select-country" data-iso="' + escHtml(iso) + '" class="tigo-country-pill' + (active ? " is-active" : "") + '">' +
              "<span>" + escHtml(meta.flag || "") + "</span>" +
              "<strong>" + escHtml(iso) + "</strong>" +
              '<span class="hidden sm:inline">' + escHtml(meta.country_name || "") + "</span>" +
              '<span class="px-1.5 py-0.5 rounded-full text-[11px] font-extrabold" style="background:' +
                (active ? "var(--tigo-yellow)" : "#E8F0FC") + ";color:" +
                (active ? "var(--tigo-navy)" : "var(--tigo-blue)") + ';">' + cnt + "</span>" +
            "</button>"
          );
        }).join("");

        renderDropdownMenus();

        // Sync form inputs
        document.getElementById("benchmark-country-select").value = state.benchmarkCountry;
        document.getElementById("benchmark-sort-select").value = state.benchmarkSortBy;
        document.getElementById("bundle-type-select").value = state.selectedBundleType;
        document.getElementById("keep-tigo-ref-checkbox").checked = state.keepTigoReferenceWhenFiltering;

        // Tab buttons & view visibility
        document.getElementById("tab-count-home").textContent = String(countryHomeOffers.length);
        document.getElementById("tab-count-deltas").textContent = String(filteredDeltas.length);
        document.getElementById("tab-count-vas").textContent = String(filteredVasRows.length);

        renderExecutiveBrief();

        document.querySelectorAll(".tigo-tab-btn").forEach(function (btn) {
          const isAct = btn.getAttribute("data-tab") === state.activeTab;
          btn.classList.toggle("is-active", isAct);
        });
        ["exec_summary", "tigo_vs_comp", "deltas", "vas_matrix"].forEach(function (tabId) {
          const el = document.getElementById("view-" + tabId);
          if (el) el.classList.toggle("is-hidden", state.activeTab !== tabId);
        });

        // Layout Mode buttons
        document.querySelectorAll(".layout-mode-btn").forEach(function (btn) {
          const active = btn.getAttribute("data-mode") === state.homeComparisonMode;
          if (active) {
            btn.style.backgroundColor = "var(--tigo-navy)";
            btn.style.color = "#FFFFFF";
          } else {
            btn.style.backgroundColor = "transparent";
            btn.style.color = "var(--tigo-text-secondary)";
          }
        });

        // Regional scope buttons in Tab 2 & Tab 3
        const isCurrentOnly = state.selectedCountries.length === 1 && state.selectedCountries[0] === state.benchmarkCountry;
        document.querySelectorAll(".rscope-btn").forEach(function (btn) {
          const mode = btn.getAttribute("data-rscope");
          const active = (mode === "ALL_12" && state.selectedCountries.length === 0) || (mode === "CURRENT" && isCurrentOnly);
          if (active) {
            btn.style.backgroundColor = "var(--tigo-navy)";
            btn.style.color = "#FFFFFF";
          } else {
            btn.style.backgroundColor = "transparent";
            btn.style.color = "var(--tigo-text-secondary)";
          }
        });

        // TAB 1: Country Context & Head-to-Head + Full Table
        const curMarket = MARKETS[state.benchmarkCountry] || { country_name: state.benchmarkCountry, currency: "", flag: "", operators: [] };
        const tigoCnt = countryHomeOffers.filter(function (o) { return o.is_millicom; }).length;
        const compCnt = countryHomeOffers.filter(function (o) { return !o.is_millicom; }).length;

        document.getElementById("country-summary-counts").innerHTML =
          'Ofertas Tigo/Millicom Hoy: <strong style="color: var(--tigo-navy);">' + tigoCnt + "</strong>" +
          ' &bull; Ofertas Competidores Hoy: <strong style="color: var(--tigo-negative);">' + compCnt + "</strong>";

        document.getElementById("country-market-note").innerHTML =
          '<div><strong style="color: var(--tigo-navy);">' +
            escHtml((curMarket.flag ? curMarket.flag + " " : "") + "Contexto " + curMarket.country_name + " (" + curMarket.currency + "):") +
          '</strong> <span style="color: var(--tigo-text);">' + escHtml(curMarket.market_note || "") + "</span></div>" +
          '<span class="font-mono font-semibold" style="color: var(--tigo-blue);">Operadores monitoreados: ' +
            escHtml((curMarket.operators || []).join(", ")) +
          "</span>";

        const tiersWrap = document.getElementById("head-to-head-tiers");
        tiersWrap.classList.toggle("is-hidden", state.homeComparisonMode === "TABLE");

        if (countryHomeOffers.length === 0) {
          tiersWrap.innerHTML =
            '<div class="tigo-card p-10 text-center space-y-2">' +
              '<p class="text-base font-extrabold m-0" style="color: var(--tigo-navy);">No hay ofertas en ' + escHtml(state.benchmarkCountry) + " que coincidan con los filtros actuales.</p>" +
              '<p class="text-xs m-0" style="color: var(--tigo-text-secondary);">Prueba cambiar de país arriba o hacer clic en &ldquo;Limpiar Filtros&rdquo; para ver el portafolio completo.</p>' +
            "</div>";
        } else {
          const tiersMap = new Map();
          countryHomeOffers.forEach(function (o) {
            const code = o.speed_tier_code || "TIER_OTHER";
            if (!tiersMap.has(code)) {
              tiersMap.set(code, {
                code: code,
                order: o.speed_tier_order || 4,
                label: o.speed_tier_label || "Otros Planes",
                tigoOffers: [],
                compOffers: []
              });
            }
            if (o.is_millicom) tiersMap.get(code).tigoOffers.push(o);
            else tiersMap.get(code).compOffers.push(o);
          });
          const sortedTiers = Array.from(tiersMap.values()).sort(function (a, b) { return a.order - b.order; });

          tiersWrap.innerHTML = sortedTiers.map(function (tier) {
            return (
              '<div class="tigo-card-lg p-4 sm:p-5 space-y-4">' +
                '<div class="flex flex-wrap items-center justify-between gap-2 pb-3" style="border-bottom: 1px solid var(--tigo-border);">' +
                  '<div class="flex flex-wrap items-center gap-2.5">' +
                    '<span class="px-3 py-1 rounded-lg text-xs font-extrabold uppercase tracking-wide" style="background: var(--tigo-navy); color: #FFFFFF;">' +
                      escHtml(tier.label) +
                    "</span>" +
                    '<span class="text-xs font-semibold" style="color: var(--tigo-text-secondary);">' +
                      tier.tigoOffers.length + " oferta(s) Tigo vs " + tier.compOffers.length + " oferta(s) Competencia" +
                    "</span>" +
                  "</div>" +
                  (state.onlyWithAddons ? '<span class="badge-warning">&#127916; Filtrado por Ofertas con Addons</span>' : "") +
                "</div>" +

                '<div class="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">' +
                  '<div class="xl:col-span-4 space-y-3">' +
                    '<div class="text-xs font-extrabold uppercase tracking-wider flex items-center gap-1.5" style="color: var(--tigo-navy);">' +
                      '<span style="color: var(--tigo-bright-blue);">&#9733;</span><span>Oferta Actual Tigo / Millicom Hogar (Referencia)</span>' +
                    "</div>" +
                    (tier.tigoOffers.length === 0
                      ? '<div class="tigo-soft-box p-4 text-xs" style="border-style: dashed; color: var(--tigo-text-secondary);">Sin oferta Tigo Hogar registrada en este escalón de velocidad (ver otros escalones o nota de mercado).</div>'
                      : tier.tigoOffers.map(renderOfferCardHtml).join("")) +
                  "</div>" +

                  '<div class="xl:col-span-8 space-y-3">' +
                    '<div class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-blue);">' +
                      "Ofertas Actuales de Competidores Hoy vs Tigo Hogar" +
                    "</div>" +
                    (tier.compOffers.length === 0
                      ? '<div class="tigo-soft-box p-5 text-center text-xs" style="border-style: dashed; color: var(--tigo-text-secondary);">Sin ofertas de competidores en este escalón con los filtros activos.</div>'
                      : '<div class="grid grid-cols-1 md:grid-cols-2 gap-3.5">' + tier.compOffers.map(renderOfferCardHtml).join("") + "</div>") +
                  "</div>" +
                "</div>" +
              "</div>"
            );
          }).join("");
        }

        // TAB 1 PART B: Full-Attribute Comparison Table
        const fullTableWrap = document.getElementById("full-table-wrapper");
        fullTableWrap.classList.toggle("is-hidden", state.homeComparisonMode === "CARDS" || countryHomeOffers.length === 0);

        document.getElementById("benchmark-tbody").innerHTML = countryHomeOffers.map(function (o) {
          const hs = o.home_specs || {};
          const p = o.pricing || {};
          const tc = o.tigo_comparison;
          const addons = o.vas_addons || [];

          let gapCell = '<span style="color: var(--tigo-text-secondary);">—</span>';
          if (o.is_millicom) {
            gapCell = '<span class="badge-tigo"><span class="badge-tigo-dot"></span>Referencia Tigo</span>';
          } else if (tc && tc.effective_price_diff !== null && tc.effective_price_diff !== undefined) {
            const d = tc.effective_price_diff;
            const pct = tc.effective_price_pct !== null && tc.effective_price_pct !== undefined
              ? (d > 0 ? "+" : "") + tc.effective_price_pct.toFixed(1) + "%"
              : "";
            const color = d < 0 ? "var(--tigo-negative)" : (d > 0 ? "var(--tigo-positive)" : "var(--tigo-text-secondary)");
            gapCell =
              '<div class="font-extrabold" style="color:' + color + ';">' + escHtml(formatSignedMoney(d, p.currency)) + "</div>" +
              '<div class="text-[11px]" style="color: var(--tigo-text-secondary);">' + escHtml(pct + " vs Tigo") + "</div>";
          }

          const effText = (o.effective_price !== null && o.effective_price !== undefined) ? formatMoney(o.effective_price, p.currency) : "Por cobertura";
          const promoTag = p.promo_duration_months ? ' <span class="text-[11px]" style="color:var(--tigo-blue);">(' + p.promo_duration_months + "m)</span>" : "";
          const regText = (p.regular_monthly_price !== null && p.regular_monthly_price !== undefined) ? formatMoney(p.regular_monthly_price, p.currency) : "Por cobertura";

          const addonsCell = addons.length === 0
            ? '<span class="italic" style="color: var(--tigo-text-secondary);">Sin addons</span>'
            : addons.map(function (v) {
                return '<span class="' + vasModelBadgeClass(v.commercial_model) + ' inline-block mr-1 mb-1">' +
                  escHtml(v.provider + ": " + formatVasShortCondition(v, p.currency)) +
                "</span>";
              }).join("");

          return (
            '<tr class="' + (o.is_millicom ? "is-tigo-row" : "") + '">' +
              '<td class="font-extrabold whitespace-nowrap">' +
                escHtml(o.operator) +
                (o.is_millicom ? ' <span class="badge-tigo ml-1"><span class="badge-tigo-dot"></span>TIGO</span>' : "") +
              "</td>" +
              '<td class="whitespace-nowrap font-semibold">' + escHtml(formatBundleType(o.bundle_type)) + "</td>" +
              '<td class="font-bold" style="color: var(--tigo-navy);">' + escHtml(o.plan_name) + "</td>" +
              '<td class="whitespace-nowrap"><strong>' + escHtml(hs.technology || "Móvil") + "</strong> &bull; " + escHtml(formatBandwidthFull(hs)) + "</td>" +
              "<td><div class=\"font-medium\">" + escHtml(hs.wifi_hardware || "Estándar") + '</div><div class="text-[11px]" style="color: var(--tigo-text-secondary);">' + escHtml(formatTvFull(hs)) + "</div></td>" +
              '<td style="text-align:right;" class="font-extrabold whitespace-nowrap">' + escHtml(effText) + promoTag + "</td>" +
              '<td style="text-align:right;" class="whitespace-nowrap">' + escHtml(regText) + "</td>" +
              '<td style="text-align:right;" class="whitespace-nowrap">' + gapCell + "</td>" +
              "<td>" + addonsCell + "</td>" +
              '<td style="text-align:center;"><button type="button" data-action="open-offer-evidence" data-uid="' + escHtml(o.offer_uid) + '" class="tigo-btn-evidence">Ver Evidencia</button></td>' +
            "</tr>"
          );
        }).join("");

        // TAB 2: Daily Deltas
        const deltasWrap = document.getElementById("deltas-list");
        if (filteredDeltas.length === 0) {
          deltasWrap.innerHTML =
            '<div class="tigo-card p-10 text-center space-y-1.5">' +
              '<p class="text-sm font-extrabold m-0" style="color: var(--tigo-navy);">Sin cambios competitivos para el filtro actual.</p>' +
              '<p class="text-xs m-0" style="color: var(--tigo-text-secondary);">Haz clic en &ldquo;Todos los 12 Países&rdquo; arriba o &ldquo;Limpiar Filtros&rdquo; para ver los ' + DELTAS.length + " deltas regionales.</p>" +
            "</div>";
        } else {
          deltasWrap.innerHTML = filteredDeltas.map(function (d, idx) {
            const isCompAlert = !d.is_millicom && (d.direction === "PRICE_DROP" || d.direction === "VAS_ADDED" || d.direction === "SPEED_UPGRADE" || d.delta_type === "NEW_OFFER_LAUNCHED");
            const leftColor = d.is_millicom ? "var(--tigo-blue)" : (isCompAlert ? "var(--tigo-negative)" : "var(--tigo-warning)");
            const badgeCls = d.is_millicom ? "badge-info" : (isCompAlert ? "badge-negative" : "badge-warning");
            const m = MARKETS[d.country_iso] || { flag: "" };

            const y = d.yesterday_offer;
            const t = d.today_offer;

            const yHtml = y
              ? '<div>Promo: <strong>' + escHtml(formatMoney((y.pricing || {}).promo_monthly_price, d.currency)) + "</strong> &bull; Regular: <strong>" + escHtml(formatMoney((y.pricing || {}).regular_monthly_price, d.currency)) + "</strong></div>" +
                "<div>Red: " + escHtml(formatBandwidthFull(y.home_specs)) + ((y.home_specs || {}).wifi_hardware ? " &bull; " + escHtml(y.home_specs.wifi_hardware) : "") + "</div>" +
                "<div>Addons: " + escHtml((y.vas_addons || []).length ? y.vas_addons.map(function (v) { return v.provider; }).join(", ") : "Sin addons") + "</div>"
              : '<div class="italic" style="color: var(--tigo-text-secondary);">No existía en el catálogo de ayer (Nuevo Lanzamiento Hoy)</div>';

            const tHtml = t
              ? '<div>Promo: <strong style="color: var(--tigo-navy);">' + escHtml(formatMoney((t.pricing || {}).promo_monthly_price, d.currency)) + "</strong> &bull; Regular: <strong>" + escHtml(formatMoney((t.pricing || {}).regular_monthly_price, d.currency)) + "</strong></div>" +
                "<div>Red: <strong>" + escHtml(formatBandwidthFull(t.home_specs)) + "</strong>" + ((t.home_specs || {}).wifi_hardware ? " &bull; " + escHtml(t.home_specs.wifi_hardware) : "") + "</div>" +
                "<div>Addons: <strong>" + escHtml((t.vas_addons || []).length ? t.vas_addons.map(function (v) { return v.provider; }).join(", ") : "Sin addons") + "</strong></div>"
              : '<div class="italic font-semibold" style="color: var(--tigo-negative);">Plan retirado del catálogo comercial hoy</div>';

            return (
              '<article class="tigo-card p-4 space-y-3" style="border-left: 5px solid ' + leftColor + ';">' +
                '<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">' +
                  "<div>" +
                    '<div class="flex flex-wrap items-center gap-2">' +
                      '<span class="px-2 py-0.5 rounded text-xs font-extrabold" style="background:#EEF4FC;color:var(--tigo-navy);">' + escHtml((m.flag ? m.flag + " " : "") + d.country_iso) + "</span>" +
                      (d.is_millicom ? '<span class="badge-tigo"><span class="badge-tigo-dot"></span>' + escHtml(d.operator) + "</span>" : '<span class="badge-comp">' + escHtml(d.operator) + "</span>") +
                      '<span class="' + badgeCls + '">' + escHtml(d.delta_type + " • " + d.direction) + "</span>" +
                    "</div>" +
                    '<h3 class="text-sm font-extrabold m-0 mt-1.5" style="color: var(--tigo-navy);">' + escHtml(d.plan_name) + "</h3>" +
                    '<p class="text-xs m-0 mt-0.5 font-medium" style="color: var(--tigo-text-secondary);">' + escHtml(d.summary) + "</p>" +
                  "</div>" +
                  '<button type="button" data-action="open-delta-evidence" data-delta-idx="' + idx + '" class="tigo-btn-evidence">Ver Evidencia</button>' +
                "</div>" +
                '<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">' +
                  '<div class="tigo-soft-box p-3 space-y-1">' +
                    '<div class="font-extrabold uppercase tracking-wide" style="color: var(--tigo-text-secondary);">Ayer (Day T-1)</div>' +
                    yHtml +
                  "</div>" +
                  '<div class="rounded-lg p-3 space-y-1" style="background: #F0F7FF; border: 1px solid #BFD8FA;">' +
                    '<div class="font-extrabold uppercase tracking-wide" style="color: var(--tigo-blue);">Hoy (Day T)</div>' +
                    tHtml +
                  "</div>" +
                "</div>" +
              "</article>"
            );
          }).join("");
        }

        // TAB 3: Regional VAS Matrix
        document.getElementById("vas-tbody").innerHTML = filteredVasRows.length === 0
          ? '<tr><td colspan="9" style="text-align:center; padding: 32px; color: var(--tigo-text-secondary);">No hay addons VAS para los filtros seleccionados.</td></tr>'
          : filteredVasRows.map(function (r, idx) {
              const m = MARKETS[r.country_iso] || { flag: "" };
              return (
                '<tr class="' + (r.is_millicom ? "is-tigo-row" : "") + '">' +
                  '<td class="font-extrabold whitespace-nowrap">' + escHtml((m.flag ? m.flag + " " : "") + r.country_iso) + "</td>" +
                  '<td class="font-bold whitespace-nowrap">' +
                    escHtml(r.operator) +
                    (r.is_millicom ? ' <span class="badge-tigo ml-1"><span class="badge-tigo-dot"></span>TIGO</span>' : "") +
                  "</td>" +
                  '<td class="whitespace-nowrap"><span class="badge-info">' + escHtml(r.provider) + "</span></td>" +
                  "<td>" + escHtml(r.tier_or_package || r.raw_provider_name || "—") + "</td>" +
                  '<td class="whitespace-nowrap"><span class="' + vasModelBadgeClass(r.commercial_model) + '">' + escHtml(r.commercial_model) + "</span></td>" +
                  '<td style="text-align:center;" class="font-extrabold">' + escHtml(r.free_months ? r.free_months + "m" : "—") + "</td>" +
                  '<td style="text-align:right;" class="whitespace-nowrap font-semibold">' + escHtml(formatVasShortCondition(r, r.currency)) + "</td>" +
                  '<td class="font-semibold" style="color: var(--tigo-navy);">' + escHtml(r.plan_name) + "</td>" +
                  '<td style="text-align:center;"><button type="button" data-action="open-vas-evidence" data-vas-idx="' + idx + '" class="tigo-btn-evidence">Ver Evidencia</button></td>' +
                "</tr>"
              );
            }).join("");
      }

      function openEvidenceModal(opts) {
        document.getElementById("modal-title").textContent = opts.title || "";
        document.getElementById("modal-uid").textContent = "Offer UID: " + (opts.offer_uid || "");
        document.getElementById("modal-terms").textContent = opts.exact_terms_text || "Sin texto literal registrado.";

        const vasWrap = document.getElementById("modal-vas-wrap");
        const vasList = document.getElementById("modal-vas-list");
        const addons = opts.vas_addons || [];
        if (addons.length > 0) {
          vasList.innerHTML = addons.map(function (a) {
            return (
              '<div class="tigo-soft-box p-3 text-xs space-y-1">' +
                '<div class="font-extrabold" style="color: var(--tigo-navy);">' +
                  escHtml(a.provider + " (" + (a.raw_provider_name || "") + ") — " + a.commercial_model) +
                "</div>" +
                '<div class="font-mono" style="color: var(--tigo-text-secondary);">' + escHtml(a.exact_terms_text || "") + "</div>" +
              "</div>"
            );
          }).join("");
          vasWrap.classList.remove("is-hidden");
        } else {
          vasList.innerHTML = "";
          vasWrap.classList.add("is-hidden");
        }

        const links = [];
        if (opts.source_url) {
          links.push(
            '<a href="' + escHtml(opts.source_url) + '" target="_blank" rel="noopener noreferrer" class="tigo-btn-secondary inline-flex items-center gap-1" style="text-decoration:none;">' +
              "Abrir URL Fuente &#8599;" +
            "</a>"
          );
        }
        if (opts.screenshot_path) {
          links.push(
            '<a href="' + escHtml(opts.screenshot_path) + '" target="_blank" class="tigo-btn-secondary inline-flex items-center gap-1" style="text-decoration:none;">' +
              "Captura Full-Page (.PNG) &#8599;" +
            "</a>"
          );
        }
        if (opts.markdown_path) {
          links.push(
            '<a href="' + escHtml(opts.markdown_path) + '" target="_blank" class="tigo-btn-secondary inline-flex items-center gap-1" style="text-decoration:none;">' +
              "Snapshot Markdown (.MD) &#8599;" +
            "</a>"
          );
        }
        document.getElementById("modal-links-wrap").innerHTML = links.join("");
        document.getElementById("modal-audit-paths").innerHTML =
          (opts.source_url ? '<div>Source URL: <strong style="color: var(--tigo-blue);">' + escHtml(opts.source_url) + "</strong></div>" : "") +
          "<div>PNG Audit Capture: <strong>" + escHtml(opts.screenshot_path || "N/A") + "</strong></div>" +
          "<div>Cleaned DOM Markdown: <strong>" + escHtml(opts.markdown_path || "N/A") + "</strong></div>";

        document.getElementById("evidence-modal").classList.remove("is-hidden");
      }

      function closeEvidenceModal() {
        document.getElementById("evidence-modal").classList.add("is-hidden");
      }

      function exportCurrentViewCSV() {
        let headers = [];
        let rows = [];
        const filename = "tigo_latam_radar_" + state.activeTab + "_" + (PAYLOAD.report_date || "hoy") + ".csv";

        if (state.activeTab === "exec_summary") {
          const eb = PAYLOAD.executive_brief || {};
          headers = [
            "Country_ISO", "Country_Name", "Currency", "Status", "Total_Offers",
            "Tigo_Offers", "Comp_Offers", "Comparable_Comp", "Comp_Cheaper_Count",
            "Worst_Gap_Pct", "Tigo_HB_Addons", "Tigo_Promo_Addons", "Tigo_SA_Addons",
            "Comp_HB_Addons", "Deltas_Today", "Comp_Offensive_Deltas", "Situation_Reading"
          ];
          rows = (eb.country_rows || []).map(function (c) {
            return [
              c.country_iso,
              c.country_name,
              c.currency,
              c.status_label,
              c.total_offers,
              c.tigo_offers,
              c.comp_offers,
              c.comparable_comp,
              c.comp_cheaper,
              c.worst_gap_pct,
              c.tigo_hb,
              c.tigo_promo,
              c.tigo_sa,
              c.comp_hb,
              c.deltas_today,
              c.comp_offensive_deltas,
              c.price_reading
            ];
          });
        } else if (state.activeTab === "tigo_vs_comp") {
          const countryOffers = computeCountryHomeOffers();
          headers = [
            "Country", "Operator", "Is_Tigo_Millicom", "Bundle_Type", "Plan_Name",
            "Technology", "Download_Mbps", "Upload_Mbps", "WiFi_Hardware", "TV_Channels",
            "Currency", "Effective_Price_Today", "Promo_Months", "Regular_Price",
            "Diff_Vs_Tigo_Price", "Diff_Vs_Tigo_Pct", "VAS_Addons_Full"
          ];
          rows = countryOffers.map(function (o) {
            const hs = o.home_specs || {};
            const p = o.pricing || {};
            const tc = o.tigo_comparison || {};
            return [
              o.country_iso,
              o.operator,
              o.is_millicom,
              o.bundle_type,
              o.plan_name,
              hs.technology || "",
              hs.download_mbps || "",
              hs.upload_mbps || "",
              hs.wifi_hardware || "",
              hs.tv_channels_count || "",
              p.currency || "",
              o.effective_price !== null && o.effective_price !== undefined ? o.effective_price : "",
              p.promo_duration_months || "",
              p.regular_monthly_price !== null && p.regular_monthly_price !== undefined ? p.regular_monthly_price : "",
              tc.effective_price_diff !== null && tc.effective_price_diff !== undefined ? tc.effective_price_diff : (o.is_millicom ? "REF_TIGO" : ""),
              tc.effective_price_pct !== null && tc.effective_price_pct !== undefined ? tc.effective_price_pct : "",
              (o.vas_addons || []).map(function (v) { return v.provider + " (" + formatVasShortCondition(v, p.currency) + ")"; }).join(" | ")
            ];
          });
        } else if (state.activeTab === "deltas") {
          headers = [
            "Country", "Operator", "Is_Millicom", "Segment", "Offer_UID", "Plan_Name",
            "Delta_Type", "Direction", "Currency", "Numeric_Diff", "Percentage_Diff", "VAS_Affected", "Summary"
          ];
          rows = state.lastFilteredDeltas.map(function (d) {
            return [
              d.country_iso, d.operator, d.is_millicom, d.segment, d.offer_uid, d.plan_name,
              d.delta_type, d.direction, d.currency,
              d.numeric_diff !== null && d.numeric_diff !== undefined ? d.numeric_diff : "",
              d.percentage_diff !== null && d.percentage_diff !== undefined ? d.percentage_diff : "",
              (d.vas_providers_affected || []).join("|"),
              d.summary
            ];
          });
        } else {
          headers = [
            "Country", "Operator", "Is_Millicom", "Segment", "Plan_Name", "VAS_Provider",
            "Tier_Or_Package", "Commercial_Model", "Free_Months", "Currency",
            "VAS_Promo_Price", "VAS_Post_Promo_Price", "Exact_Terms"
          ];
          rows = state.lastFilteredVasRows.map(function (r) {
            return [
              r.country_iso, r.operator, r.is_millicom, r.segment, r.plan_name, r.provider,
              r.tier_or_package || "", r.commercial_model, r.free_months || "", r.currency,
              r.promo_price !== null && r.promo_price !== undefined ? r.promo_price : "",
              r.regular_price_after_promo !== null && r.regular_price_after_promo !== undefined ? r.regular_price_after_promo : "",
              r.exact_terms_text || ""
            ];
          });
        }

        const LF = String.fromCharCode(10);
        const CRLF = String.fromCharCode(13, 10);
        const BOM = String.fromCharCode(0xFEFF);

        function escapeCsvCell(cell) {
          const str = String(cell === null || cell === undefined ? "" : cell);
          if (str.indexOf(",") >= 0 || str.indexOf('"') >= 0 || str.indexOf(LF) >= 0) {
            return '"' + str.replace(/"/g, '""') + '"';
          }
          return str;
        }

        const allLines = [headers].concat(rows).map(function (r) {
          return r.map(escapeCsvCell).join(",");
        });
        const csvContent = BOM + allLines.join(CRLF);
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }

      // SINGLE BULLETPROOF EVENT-DELEGATION CLICK HANDLER
      document.addEventListener("click", function (e) {
        // Close open dropdown if clicking outside `.tigo-dd-wrap`
        if (state.openDropdown && !e.target.closest(".tigo-dd-wrap")) {
          state.openDropdown = null;
          renderDropdownMenus();
        }

        // Backdrop click on modal
        if (e.target && e.target.id === "evidence-modal") {
          closeEvidenceModal();
          return;
        }

        const btn = e.target.closest("[data-action]");
        if (!btn) return;

        const action = btn.getAttribute("data-action");

        if (action === "toggle-addons") {
          state.onlyWithAddons = !state.onlyWithAddons;
          renderAll();
        } else if (action === "set-scope") {
          state.operatorScope = btn.getAttribute("data-scope") || "ALL";
          renderAll();
        } else if (action === "export-csv") {
          exportCurrentViewCSV();
        } else if (action === "reset-filters") {
          state.onlyWithAddons = false;
          state.selectedVasModel = "ALL";
          state.selectedBundleType = "ALL";
          state.operatorScope = "ALL";
          state.searchQuery = "";
          state.selectedCountries = [];
          state.selectedOperators = [];
          state.selectedSegments = [];
          state.selectedDeltaTypes = [];
          state.selectedVasProviders = [];
          document.getElementById("search-input").value = "";
          renderAll();
        } else if (action === "set-vas-model") {
          const model = btn.getAttribute("data-model") || "ALL";
          state.selectedVasModel = model;
          if (model !== "ALL") state.onlyWithAddons = true;
          renderAll();
        } else if (action === "toggle-vas-chip") {
          const vp = btn.getAttribute("data-vp");
          if (vp) {
            toggleInArray(state.selectedVasProviders, vp);
            if (state.selectedVasProviders.length > 0) state.onlyWithAddons = true;
            renderAll();
          }
        } else if (action === "select-country") {
          const iso = btn.getAttribute("data-iso");
          if (!iso) return;
          if (state.activeTab === "exec_summary") {
            state.benchmarkCountry = iso;
            state.activeTab = "tigo_vs_comp";
          } else if (state.activeTab === "tigo_vs_comp") {
            state.benchmarkCountry = iso;
          } else {
            state.benchmarkCountry = iso;
            toggleInArray(state.selectedCountries, iso);
          }
          renderAll();
        } else if (action === "exec-drill-country") {
          const iso = btn.getAttribute("data-iso");
          if (iso) {
            state.benchmarkCountry = iso;
            state.activeTab = "tigo_vs_comp";
            renderAll();
          }
        } else if (action === "toggle-dropdown") {
          const dd = btn.getAttribute("data-dd");
          state.openDropdown = state.openDropdown === dd ? null : dd;
          renderDropdownMenus();
        } else if (action === "set-tab") {
          const tab = btn.getAttribute("data-tab");
          if (tab) {
            state.activeTab = tab;
            renderAll();
          }
        } else if (action === "set-layout-mode") {
          const mode = btn.getAttribute("data-mode");
          if (mode) {
            state.homeComparisonMode = mode;
            renderAll();
          }
        } else if (action === "set-regional-scope") {
          const rs = btn.getAttribute("data-rscope");
          if (rs === "ALL_12") {
            state.selectedCountries = [];
          } else if (rs === "CURRENT") {
            state.selectedCountries = [state.benchmarkCountry];
          }
          renderAll();
        } else if (action === "open-offer-evidence") {
          const uid = btn.getAttribute("data-uid");
          const offer = OFFERS.find(function (x) { return x.offer_uid === uid; });
          if (offer) {
            openEvidenceModal({
              title: offer.country_iso + " • " + offer.operator + " — " + offer.plan_name,
              offer_uid: offer.offer_uid,
              exact_terms_text: offer.exact_terms_text,
              vas_addons: offer.vas_addons || [],
              source_url: offer.source_url,
              screenshot_path: offer.screenshot_path,
              markdown_path: offer.markdown_path
            });
          }
        } else if (action === "open-delta-evidence") {
          const idx = Number(btn.getAttribute("data-delta-idx"));
          const delta = state.lastFilteredDeltas[idx];
          if (delta) {
            const ref = delta.today_offer || delta.yesterday_offer || {};
            openEvidenceModal({
              title: delta.country_iso + " • " + delta.operator + " — " + delta.plan_name + " [" + delta.delta_type + "]",
              offer_uid: delta.offer_uid,
              exact_terms_text: ref.exact_terms_text || delta.summary,
              vas_addons: ref.vas_addons || [],
              source_url: ref.source_url,
              screenshot_path: ref.screenshot_path,
              markdown_path: ref.markdown_path
            });
          }
        } else if (action === "open-vas-evidence") {
          const idx = Number(btn.getAttribute("data-vas-idx"));
          const row = state.lastFilteredVasRows[idx];
          if (row) {
            const LF = String.fromCharCode(10);
            openEvidenceModal({
              title: row.country_iso + " • " + row.operator + " — " + row.provider + " en " + row.plan_name,
              offer_uid: row.offer_uid,
              exact_terms_text: (row.exact_terms_text || "") + (row.offer_exact_terms_text ? LF + LF + "[Plan Card]: " + row.offer_exact_terms_text : ""),
              vas_addons: [],
              source_url: row.source_url,
              screenshot_path: row.screenshot_path,
              markdown_path: row.markdown_path
            });
          }
        } else if (action === "close-modal") {
          closeEvidenceModal();
        }
      });

      // Delegated change handler for checkboxes & selects
      document.addEventListener("change", function (e) {
        const t = e.target;
        if (!t) return;

        const ddCheck = t.getAttribute("data-dd-check");
        if (ddCheck === "operator") {
          toggleInArray(state.selectedOperators, t.value);
          renderAll();
          return;
        }
        if (ddCheck === "segment") {
          toggleInArray(state.selectedSegments, t.value);
          renderAll();
          return;
        }
        if (ddCheck === "delta") {
          toggleInArray(state.selectedDeltaTypes, t.value);
          renderAll();
          return;
        }

        if (t.id === "benchmark-country-select") {
          state.benchmarkCountry = t.value;
          renderAll();
        } else if (t.id === "benchmark-sort-select") {
          state.benchmarkSortBy = t.value;
          renderAll();
        } else if (t.id === "bundle-type-select") {
          state.selectedBundleType = t.value;
          renderAll();
        } else if (t.id === "keep-tigo-ref-checkbox") {
          state.keepTigoReferenceWhenFiltering = Boolean(t.checked);
          renderAll();
        }
      });

      document.getElementById("search-input").addEventListener("input", function (e) {
        state.searchQuery = e.target.value || "";
        renderAll();
      });

      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          closeEvidenceModal();
          if (state.openDropdown) {
            state.openDropdown = null;
            renderDropdownMenus();
          }
        }
      });

      populateCountrySelectOnce();
      renderAll();
    })();
  </script>
</body>
</html>
"""
        return (
            raw_template
            .replace("__TAILWIND_CDN_URL__", tailwind_cdn_url)
            .replace("__REPORT_DATE_STR__", report_date_str)
            .replace("__SAFE_JSON_PAYLOAD__", safe_json_payload)
        )
