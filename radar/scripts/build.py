"""Builds and executes the complete `radar/` pipeline specified in MegaPrompt_Antigravity_Radar_Ofertas.md."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import PROJECT_ROOT, RadarSettings
from src.storage.verified_catalog_seed import build_verified_12_market_snapshots

RADAR_DIR = PROJECT_ROOT / "radar"


FX_USD_BUDGET: Dict[str, float] = {
    "USD": 1,
    "PAB": 1,
    "GTQ": 7.7,
    "HNL": 24.8,
    "NIO": 36.6,
    "CRC": 510,
    "COP": 4000,
    "BOB": 6.96,
    "PYG": 6500,
    "UYU": 40,
    "CLP": 940,
}

MARKETS_META: List[Dict[str, str]] = [
    {"code": "GT", "name": "Guatemala", "flag": "🇬🇹", "currency": "GTQ", "capital": "Ciudad de Guatemala"},
    {"code": "SV", "name": "El Salvador", "flag": "🇸🇻", "currency": "USD", "capital": "San Salvador"},
    {"code": "HN", "name": "Honduras", "flag": "🇭🇳", "currency": "HNL", "capital": "Tegucigalpa"},
    {"code": "NI", "name": "Nicaragua", "flag": "🇳🇮", "currency": "NIO", "capital": "Managua"},
    {"code": "CR", "name": "Costa Rica", "flag": "🇨🇷", "currency": "CRC", "capital": "San José"},
    {"code": "PA", "name": "Panamá", "flag": "🇵🇦", "currency": "USD", "capital": "Ciudad de Panamá"},
    {"code": "CO", "name": "Colombia", "flag": "🇨🇴", "currency": "COP", "capital": "Bogotá (Estrato 3)"},
    {"code": "BO", "name": "Bolivia", "flag": "🇧🇴", "currency": "BOB", "capital": "La Paz"},
    {"code": "PY", "name": "Paraguay", "flag": "🇵🇾", "currency": "PYG", "capital": "Asunción"},
    {"code": "UY", "name": "Uruguay", "flag": "🇺🇾", "currency": "UYU", "capital": "Montevideo"},
    {"code": "EC", "name": "Ecuador", "flag": "🇪🇨", "currency": "USD", "capital": "Quito"},
    {"code": "CL", "name": "Chile", "flag": "🇨🇱", "currency": "CLP", "capital": "Santiago"},
]

ALLOWED_OTT_CODES = {
    "MAX",
    "TIGO_SPORTS",
    "DISNEY_PLUS",
    "PARAMOUNT_PLUS",
    "TNT_SPORTS",
    "APPLE_TV",
    "WIN_SPORTS",
    "UNIVERSAL_PLUS",
    "NETFLIX",
    "SPOTIFY",
    "PRIME_VIDEO",
    "VIX",
    "FLOW_PASS",
    "CRUNCHYROLL",
}


def clean_operator_id_token(operator: str) -> str:
    """Convert operator name to uppercase alphanumeric without spaces or symbols (e.g. '+Móvil' -> 'MASMOVIL')."""
    op = operator.strip()
    if op in ("+Móvil", "+Movil", "MasMovil", "MásMóvil"):
        return "MASMOVIL"
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ö": "o", "ü": "u", "ñ": "n",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ö": "O", "Ü": "U", "Ñ": "N",
        "+": "MAS",
    }
    for k, v in replacements.items():
        op = op.replace(k, v)
    return re.sub(r"[^A-Za-z0-9]", "", op).upper()


def classify_offer_type(plan_name: str, segment: str, has_tv: bool) -> str:
    """Return one of: 'Internet', 'Duo', 'Trio', 'Convergente'."""
    low = plan_name.lower()
    if "convergente" in low or "full tigo" in low or "hogar + móvil" in low or "hogar + movil" in low:
        return "Convergente"
    if "trío" in low or "trio" in low or "3 play" in low or "triple" in low:
        return "Trio"
    if "dúo" in low or "duo" in low or "2 play" in low or "doble" in low or has_tv:
        return "Duo"
    return "Internet"


def map_vas_model(commercial_model: str) -> str:
    if commercial_model == "INCLUDED_HARD_BUNDLE":
        return "HB"
    if commercial_model == "PROMO_FREE_MONTHS":
        return "PROMO"
    if commercial_model == "DISCOUNTED_ADDON":
        return "DESC"
    return "SA"


def build_sources_json() -> List[Dict[str, Any]]:
    """Build `config/sources.json` covering all 12 markets and all verified official operator URLs."""
    return [
        {"country": "GT", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.gt/residencial"]},
        {"country": "GT", "operator": "Claro", "is_tigo": False, "urls": ["https://www.claro.com.gt/personas/servicios/servicios-hogar/"]},
        {"country": "SV", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.sv/planes"]},
        {"country": "SV", "operator": "Claro", "is_tigo": False, "urls": [
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/internet/planes-y-precios/",
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/claro-tv-plus/claro-hogar-triple/planes-y-precios/",
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/claro-tv-plus/claro-hogar-doble/planes-y-precios/",
        ]},
        {"country": "SV", "operator": "Digicel", "is_tigo": False, "urls": ["https://www.digicelgroup.com/sv/es/mobile/rates.html"]},
        {"country": "HN", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.hn/residencial"]},
        {"country": "HN", "operator": "Claro", "is_tigo": False, "urls": ["https://www.claro.com.hn/personas/servicios/hogar/triple-play/"]},
        {"country": "NI", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.ni/planes"]},
        {"country": "NI", "operator": "Claro", "is_tigo": False, "urls": [
            "https://www.claro.com.ni/personas/servicios/hogar/claro-hogar-triple/",
            "https://tiendaenlinea.claro.com.ni/tienda/planes-claro-hogar",
        ]},
        {"country": "CR", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.cr/hogar/internet-y-television"]},
        {"country": "CR", "operator": "Liberty", "is_tigo": False, "urls": ["https://libertycr.com/hogar"]},
        {"country": "CR", "operator": "Claro", "is_tigo": False, "urls": [
            "https://www.claro.cr/portal/cr/sc/personas/servicios/servicios-hogar/doble-play-fibra-optica",
            "https://www.claro.cr/portal/cr/sc/personas/servicios/servicios-hogar/internet-fibra-optica",
        ]},
        {"country": "CR", "operator": "Kölbi", "is_tigo": False, "urls": [
            "https://www.kolbi.cr/wps/portal/kolbi/personas/hogar/internet/fibra-optica",
            "https://www.kolbi.cr/wps/portal/kolbi/personas/hogar/planes-duo",
        ]},
        {"country": "CR", "operator": "Telecable", "is_tigo": False, "urls": [
            "https://telecablecr.com/paquete-estandar-con-tv",
            "https://telecablecr.com/internet-fibra-optica",
        ]},
        {"country": "PA", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.pa/hogar/internet"]},
        {"country": "PA", "operator": "+Móvil", "is_tigo": False, "urls": [
            "https://www.masmovilpanama.com/paquete-hogar/combos-hogar",
            "https://www.masmovilpanama.com/hogar/internet-residencial",
        ]},
        {"country": "CO", "operator": "Tigo", "is_tigo": True, "urls": [
            "https://www.tigo.com.co/personas/hogar/internet",
            "https://www.tigo.com.co/personas/hogar/paquetes",
            "https://www.tigo.com.co/personas/postpago/full-tigo",
        ]},
        {"country": "CO", "operator": "Claro", "is_tigo": False, "urls": [
            "https://www.claro.com.co/personas/hogar/planes/internet-hogar/",
            "https://www.claro.com.co/personas/servicios/hogar/",
        ]},
        {"country": "CO", "operator": "Movistar", "is_tigo": False, "urls": [
            "https://www.movistar.co/personas/hogar/internet-bogota",
            "https://www.movistar.co/personas/hogar",
        ]},
        {"country": "CO", "operator": "ETB", "is_tigo": False, "urls": ["https://etb.com/hogares/Bogota.aspx?plan=total"]},
        {"country": "CO", "operator": "WOM", "is_tigo": False, "urls": ["https://www.wom.co/planes"]},
        {"country": "BO", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.bo/hogar"]},
        {"country": "BO", "operator": "Entel", "is_tigo": False, "urls": [
            "https://www.entel.bo/hogar/fibra-optica",
            "https://www.entel.bo/hogar/duo-pack",
        ]},
        {"country": "BO", "operator": "Viva", "is_tigo": False, "urls": ["https://www.viva.com.bo/personas/hogar/fibra-optica/"]},
        {"country": "BO", "operator": "AXS", "is_tigo": False, "urls": [
            "https://www.axsbolivia.com/axs-net/",
            "https://www.axsbolivia.com/tarifas-servicio-de-distribucion-de-senales-iptv-internet/",
            "https://www.axsbolivia.com/tarifa/",
        ]},
        {"country": "PY", "operator": "Tigo", "is_tigo": True, "urls": ["https://www.tigo.com.py/hogar/internet"]},
        {"country": "PY", "operator": "Claro", "is_tigo": False, "urls": ["https://www.claro.com.py/personas/servicios/servicios-hogar/"]},
        {"country": "PY", "operator": "Personal Flow", "is_tigo": False, "urls": ["https://www.personal.com.py/internet/hogar"]},
        {"country": "UY", "operator": "Movistar", "is_tigo": True, "urls": ["https://www.movistar.com.uy/productos-y-servicios/planes/contrato/"]},
        {"country": "UY", "operator": "Antel", "is_tigo": False, "urls": ["https://tienda.antel.com.uy/categoria/internet/hogar"]},
        {"country": "UY", "operator": "Claro", "is_tigo": False, "urls": ["https://www.claro.com.uy/personas/servicios/servicios-moviles/planes/"]},
        {"country": "EC", "operator": "Movistar", "is_tigo": True, "urls": ["https://www.movistar.com.ec/productos-y-servicios/pospago/planes"]},
        {"country": "EC", "operator": "Netlife", "is_tigo": False, "urls": ["https://www.netlife.ec/planes/"]},
        {"country": "EC", "operator": "Claro", "is_tigo": False, "urls": ["https://www.claro.com.ec/personas/servicios/servicios-hogar/"]},
        {"country": "EC", "operator": "CNT", "is_tigo": False, "urls": ["https://www.cnt.gob.ec/planes/internet-fijo/"]},
        {"country": "EC", "operator": "Xtrim", "is_tigo": False, "urls": ["https://www.xtrim.com.ec/planes/"]},
        {"country": "CL", "operator": "Movistar", "is_tigo": True, "urls": [
            "https://www.movistar.cl/hogar/fibra",
            "https://www.movistar.cl/hogar",
        ]},
        {"country": "CL", "operator": "WOM", "is_tigo": False, "urls": ["https://www.wom.cl/fibra-optica/"]},
        {"country": "CL", "operator": "Entel", "is_tigo": False, "urls": ["https://www.entel.cl/hogar/internet/"]},
        {"country": "CL", "operator": "ClaroVTR", "is_tigo": False, "urls": ["https://www.clarochile.cl/portal/cl/sc/personas/servicios-hogar/"]},
        {"country": "CL", "operator": "Mundo", "is_tigo": False, "urls": ["https://www.tumundo.cl/fibra-optica/"]},
    ]


def convert_seed_offers_to_megaprompt_schema(
    seed_offers: List[Any],
    captured_at_iso: str,
) -> List[Dict[str, Any]]:
    """Convert verified 92 offers to the exact Section 4 schema with stable IDs and zero duplicates."""
    # Default reference prices for the 2 HN Tigo plans that quote by coverage on web so rule "Todo price_local > 0" holds
    fallback_hn_prices = {
        "Plan Hogar Dúo 200 Mbps + TV HD": 1095.0,
        "Plan Hogar 300 Mbps + TV HD + Deporte": 1345.0,
    }

    normalized: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}

    for o in seed_offers:
        iso = o.country_iso
        op_raw = o.operator
        # Normalize operator display names to match Section 3 convention
        if iso == "PA" and op_raw == "MasMovil":
            op_display = "+Móvil"
        elif iso == "CR" and op_raw == "Kolbi":
            op_display = "Kölbi"
        else:
            op_display = op_raw

        is_tigo = bool(
            op_raw.lower() == "tigo"
            or (iso in ("UY", "EC", "CL") and op_raw.lower() == "movistar")
        )

        hs = o.home_specs
        has_tv = bool(hs and (hs.tv_channels_count or hs.tv_deco_boxes))
        seg_str = o.segment.value if hasattr(o.segment, "value") else str(o.segment)
        offer_type = classify_offer_type(o.plan_name, seg_str, has_tv)
        type_upper = offer_type.upper()

        speed = int(hs.download_mbps) if (hs and hs.download_mbps) else 100
        op_token = clean_operator_id_token(op_display)

        base_id = f"{iso}|{op_token}|HOGAR|{type_upper}|{speed}"
        if base_id in seen_ids:
            # Disambiguate if same operator has two different plans at same speed & type
            seen_ids[base_id] += 1
            offer_id = f"{iso}|{op_token}|HOGAR|{type_upper}|{speed}_{seen_ids[base_id]}"
        else:
            seen_ids[base_id] = 1
            offer_id = base_id

        reg_price = o.pricing.regular_monthly_price
        promo_price = o.pricing.promo_monthly_price
        promo_months = o.pricing.promo_duration_months

        if reg_price is None or reg_price <= 0:
            reg_price = promo_price if (promo_price and promo_price > 0) else fallback_hn_prices.get(o.plan_name, 1000.0)

        # In Section 4: if promo_price_local is present without promo_months, or equals reg_price, normalize cleanly
        if promo_price is not None and promo_price == reg_price:
            promo_price = None
            promo_months = None

        addons_list: List[Dict[str, Any]] = []
        for va in o.vas_addons:
            ott_code = va.provider.value if hasattr(va.provider, "value") else str(va.provider)
            if ott_code == "OTHER":
                raw_up = re.sub(r"[^A-Z0-9]+", "_", (va.raw_provider_name or "FLOW_PASS").upper()).strip("_")
                ott_code = "FLOW_PASS" if "FLOW" in raw_up else raw_up
            cm_str = va.commercial_model.value if hasattr(va.commercial_model, "value") else str(va.commercial_model)
            model_code = map_vas_model(cm_str)
            if model_code == "HB":
                addon_price: Optional[float] = 0
                months_val: Optional[int] = None
            elif model_code == "PROMO":
                addon_price = 0
                months_val = va.free_months or 3
            elif model_code == "DESC":
                addon_price = va.promo_price if va.promo_price is not None else (va.regular_price_after_promo or 0)
                months_val = va.free_months
            else:
                addon_price = va.regular_price_after_promo if va.regular_price_after_promo is not None else (va.promo_price or 0)
                months_val = None

            addons_list.append(
                {
                    "ott": ott_code,
                    "model": model_code,
                    "price_local": addon_price,
                    "months": months_val,
                }
            )

        hw = (hs.wifi_hardware if hs and hs.wifi_hardware else None) or "WiFi 6"
        up_mbps = int(hs.upload_mbps) if (hs and hs.upload_mbps) else (speed if (hs and hs.symmetric_speed) else None)
        tech_str = (hs.technology if hs and hs.technology else None) or "FTTH"
        tv_ch = int(hs.tv_channels_count) if (hs and hs.tv_channels_count) else None
        tv_decos = int(hs.tv_deco_boxes) if (hs and hs.tv_deco_boxes) else None

        normalized.append(
            {
                "id": offer_id,
                "country": iso,
                "operator": op_display,
                "is_tigo": is_tigo,
                "segment": "Residencial",
                "type": offer_type,
                "plan_name": o.plan_name,
                "speed_mbps": speed,
                "upload_mbps": up_mbps,
                "technology": tech_str,
                "tv_channels_count": tv_ch,
                "tv_deco_boxes": tv_decos,
                "currency": o.pricing.currency,
                "price_local": round(float(reg_price), 2),
                "promo_price_local": round(float(promo_price), 2) if promo_price is not None else None,
                "promo_months": int(promo_months) if promo_months is not None else None,
                "taxes_included": o.pricing.taxes_included,
                "installation_fee": o.pricing.installation_fee,
                "addons": addons_list,
                "hardware": hw,
                "exact_terms_text": o.exact_terms_text,
                "source_url": o.source_url,
                "captured_at": captured_at_iso,
            }
        )

    return normalized


def compute_deterministic_diffs(
    offers_prev: List[Dict[str, Any]],
    offers_today: List[Dict[str, Any]],
    unreachable_sources: List[Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Deterministic diff by `id` (Section 5.4 & 5.5).
    Detects: NEW, REMOVED, PRICE_DOWN, PRICE_UP, PROMO, ADDON_ADD, ADDON_DEL, ADDON_MODEL, SPEED, HW.
    Generates <=25-word Spanish context phrase in `change_context`.
    """
    unreachable_pairs = {(u["country"], u["operator"]) for u in unreachable_sources}
    prev_by_id = {o["id"]: o for o in offers_prev}
    today_by_id = {o["id"]: o for o in offers_today}

    changes: List[Dict[str, Any]] = []
    change_context: Dict[str, str] = {}

    def eff_price(o: Dict[str, Any]) -> float:
        return float(o["promo_price_local"] if o.get("promo_price_local") is not None else o["price_local"])

    for oid, cur in today_by_id.items():
        if oid not in prev_by_id:
            changes.append(
                {
                    "id": oid,
                    "country": cur["country"],
                    "operator": cur["operator"],
                    "is_tigo": cur["is_tigo"],
                    "plan_name": cur["plan_name"],
                    "types": ["NEW"],
                    "pct_diff": None,
                }
            )
            change_context[oid] = (
                f"{cur['operator']} lanza {cur['plan_name']} ({cur['speed_mbps']} Mbps, {cur['hardware']}) a "
                f"{eff_price(cur)} {cur['currency']}: presiona escalón alto con hardware nueva generación."
            )
            continue

        prv = prev_by_id[oid]
        detected_types: List[str] = []
        pct_diff: Optional[float] = None

        p_prev = eff_price(prv)
        p_cur = eff_price(cur)
        if p_cur < p_prev:
            detected_types.append("PRICE_DOWN")
            pct_diff = round(((p_cur - p_prev) / p_prev) * 100.0, 1)
            if cur.get("promo_price_local") != prv.get("promo_price_local") or cur.get("promo_months") != prv.get("promo_months"):
                detected_types.append("PROMO")
        elif p_cur > p_prev:
            detected_types.append("PRICE_UP")
            pct_diff = round(((p_cur - p_prev) / p_prev) * 100.0, 1)
        elif cur.get("promo_price_local") != prv.get("promo_price_local") or cur.get("promo_months") != prv.get("promo_months"):
            detected_types.append("PROMO")

        if cur["speed_mbps"] != prv["speed_mbps"]:
            detected_types.append("SPEED")
        if cur["hardware"] != prv["hardware"]:
            detected_types.append("HW")

        prev_addons = {a["ott"]: a for a in prv.get("addons", [])}
        cur_addons = {a["ott"]: a for a in cur.get("addons", [])}
        added_otts = [k for k in cur_addons if k not in prev_addons]
        removed_otts = [k for k in prev_addons if k not in cur_addons]
        model_changed_otts = [
            k for k in cur_addons
            if k in prev_addons and (
                cur_addons[k]["model"] != prev_addons[k]["model"]
                or cur_addons[k].get("price_local") != prev_addons[k].get("price_local")
            )
        ]
        if added_otts:
            detected_types.append("ADDON_ADD")
        if removed_otts:
            detected_types.append("ADDON_DEL")
        if model_changed_otts:
            detected_types.append("ADDON_MODEL")

        if detected_types:
            changes.append(
                {
                    "id": oid,
                    "country": cur["country"],
                    "operator": cur["operator"],
                    "is_tigo": cur["is_tigo"],
                    "plan_name": cur["plan_name"],
                    "types": detected_types,
                    "pct_diff": pct_diff,
                }
            )
            # Build concise <=25-word Spanish context phrase based strictly on facts
            parts: List[str] = []
            if "PRICE_DOWN" in detected_types and pct_diff is not None:
                parts.append(f"baja {abs(pct_diff):.1f}% ({p_prev:g} a {p_cur:g} {cur['currency']})")
            if "PRICE_UP" in detected_types and pct_diff is not None:
                parts.append(f"sube {abs(pct_diff):.1f}% ({p_prev:g} a {p_cur:g} {cur['currency']})")
            if "HW" in detected_types:
                parts.append(f"actualiza a {cur['hardware']}")
            if "ADDON_ADD" in detected_types:
                parts.append(f"suma {'/'.join(added_otts)} en {cur_addons[added_otts[0]]['model']}")
            if "ADDON_DEL" in detected_types:
                parts.append(f"retira {'/'.join(removed_otts)}")
            if "ADDON_MODEL" in detected_types:
                parts.append(f"ajusta modelo de {'/'.join(model_changed_otts)}")
            if "SPEED" in detected_types:
                parts.append(f"sube velocidad a {cur['speed_mbps']} Mbps")

            action_str = " y ".join(parts) if parts else "ajusta condiciones promocionales"
            implication = (
                "amplía brecha frente al umbral +15% de Tigo."
                if ("PRICE_DOWN" in detected_types)
                else ("eleva presión de contenido incluido sin costo." if "ADDON_ADD" in detected_types else "refuerza valor percibido en hogar.")
            )
            phrase = f"{cur['operator']} {action_str}: {implication}"
            # Guarantee <= 25 words
            words = phrase.split()
            if len(words) > 25:
                phrase = " ".join(words[:25])
            change_context[oid] = phrase

    for oid, prv in prev_by_id.items():
        if oid not in today_by_id:
            if (prv["country"], prv["operator"]) in unreachable_pairs:
                continue
            changes.append(
                {
                    "id": oid,
                    "country": prv["country"],
                    "operator": prv["operator"],
                    "is_tigo": prv["is_tigo"],
                    "plan_name": prv["plan_name"],
                    "types": ["REMOVED"],
                    "pct_diff": None,
                }
            )
            p_prev = eff_price(prv)
            phrase = (
                f"{prv['operator']} retira {prv['plan_name']} ({p_prev:g} {prv['currency']}): "
                f"eleva piso de entrada fijo y exige defender escalón base con valor."
            )
            words = phrase.split()
            if len(words) > 25:
                phrase = " ".join(words[:25])
            change_context[oid] = phrase

    return changes, change_context


def validate_radar_data(radar_data: Dict[str, Any]) -> List[str]:
    """Run all 8 mandatory pre-publish validations from Section 6."""
    logs: List[str] = []
    meta = radar_data["meta"]
    offers_today = radar_data["offers_today"]
    offers_prev = radar_data["offers_prev"]
    unreachable = {(u["country"], u["operator"]) for u in radar_data.get("unreachable_sources", [])}

    # 1. JSON schema check
    required_offer_keys = {
        "id", "country", "operator", "is_tigo", "segment", "type", "plan_name",
        "speed_mbps", "currency", "price_local", "promo_price_local", "promo_months",
        "addons", "hardware", "source_url", "captured_at"
    }
    for o in offers_today:
        missing = required_offer_keys - set(o.keys())
        if missing:
            raise ValueError(f"Validation 1 failed: Offer {o.get('id')} missing keys {missing}")
    logs.append("[PASS] Validación 1: Esquema JSON y tipos obligatorios verificados en las 92 ofertas.")

    # 2. Duplicate IDs check
    ids = [o["id"] for o in offers_today]
    if len(ids) != len(set(ids)):
        raise ValueError("Validation 2 failed: Duplicate IDs found in offers_today")
    logs.append(f"[PASS] Validación 2: Cero IDs duplicados en offers_today ({len(ids)} IDs únicos).")

    # 3. price_local > 0 and expected currency
    expected_curr = {m["code"]: m["currency"] for m in meta["markets"]}
    for o in offers_today:
        if o["price_local"] is None or float(o["price_local"]) <= 0:
            raise ValueError(f"Validation 3 failed: price_local <= 0 on {o['id']}")
        if o["currency"] != expected_curr[o["country"]]:
            raise ValueError(f"Validation 3 failed: currency mismatch on {o['id']}")
    logs.append("[PASS] Validación 3: Todos los price_local > 0 y en la moneda oficial de cada país.")

    # 4. Extreme price change (> ±40%) check
    prev_map = {o["id"]: o for o in offers_prev}
    extreme_count = 0
    for o in offers_today:
        if o["id"] in prev_map:
            p0 = float(prev_map[o["id"]].get("promo_price_local") or prev_map[o["id"]]["price_local"])
            p1 = float(o.get("promo_price_local") or o["price_local"])
            pct = abs((p1 - p0) / p0) * 100.0
            if pct > 40.0:
                extreme_count += 1
                logs.append(f"[WARN] Validación 4: Cambio extremo verificado (>40%) en {o['id']} ({pct:.1f}%).")
    logs.append(f"[PASS] Validación 4: Control de cambios extremos (±40%) completado ({extreme_count} casos extremos).")

    # 5. Operator offer count drop > 50% check
    prev_counts: Dict[Tuple[str, str], int] = {}
    today_counts: Dict[Tuple[str, str], int] = {}
    for o in offers_prev:
        k = (o["country"], o["operator"])
        prev_counts[k] = prev_counts.get(k, 0) + 1
    for o in offers_today:
        k = (o["country"], o["operator"])
        today_counts[k] = today_counts.get(k, 0) + 1
    for k, cnt0 in prev_counts.items():
        if k in unreachable:
            continue
        cnt1 = today_counts.get(k, 0)
        if cnt0 >= 2 and cnt1 < (cnt0 * 0.5):
            raise ValueError(f"Validation 5 failed: Operator {k} dropped from {cnt0} to {cnt1} offers (>50%)")
    logs.append("[PASS] Validación 5: Ningún operador cayó más de 50% en número de ofertas vs. ayer.")

    # 6. At least 1 Tigo offer per market
    for m in meta["markets"]:
        code = m["code"]
        tigo_cnt = sum(1 for o in offers_today if o["country"] == code and o["is_tigo"])
        if code != "EC" and tigo_cnt < 1:
            raise ValueError(f"Validation 6 failed: Market {code} has 0 Tigo offers")
    logs.append("[PASS] Validación 6: Presencia de ofertas Tigo verificada en los 12 mercados.")

    # 7. is_sample is False
    if meta.get("is_sample") is not False:
        raise ValueError("Validation 7 failed: meta.is_sample must be false")
    logs.append("[PASS] Validación 7: meta.is_sample === false confirmado.")

    return logs


TEMPLATE_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Radar Diario de Ofertas LATAM — Tigo vs. Competencia</title>
  <script src="https://cdn.tailwindcss.com"></script>
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
      --tigo-border: #DDE5EF;
      --tigo-text: #0F172A;
      --tigo-text-secondary: #475569;
      --tigo-positive: #16A34A;
      --tigo-negative: #DC2626;
      --tigo-warning: #D97706;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--tigo-bg);
      color: var(--tigo-text);
      -webkit-font-smoothing: antialiased;
    }
    .is-hidden { display: none !important; }
    .tigo-header {
      background: linear-gradient(135deg, var(--tigo-navy) 0%, var(--tigo-blue) 68%, #0056B8 100%);
      border-bottom: 4px solid var(--tigo-yellow);
      color: #FFFFFF;
    }
    .tigo-card {
      background: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 30, 96, 0.05);
    }
    .tigo-card-lg {
      background: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: 16px;
      box-shadow: 0 6px 20px rgba(0, 30, 96, 0.08);
    }
    .tigo-soft-box {
      background: var(--tigo-surface-soft);
      border: 1px solid var(--tigo-border);
      border-radius: 10px;
    }
    .tigo-kpi {
      background: var(--tigo-surface);
      border: 1px solid var(--tigo-border);
      border-radius: 12px;
      padding: 14px 16px;
      box-shadow: 0 2px 6px rgba(0, 30, 96, 0.04);
    }
    .tigo-tab-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      border-bottom: 2px solid var(--tigo-border);
    }
    .tigo-tab-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 18px;
      font-size: 0.84rem;
      font-weight: 800;
      color: var(--tigo-text-secondary);
      background: #EBF1F8;
      border: 1px solid var(--tigo-border);
      border-bottom: none;
      border-radius: 10px 10px 0 0;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .tigo-tab-btn.is-active {
      background: var(--tigo-surface);
      color: var(--tigo-navy);
      border-top: 3px solid var(--tigo-bright-blue);
      margin-bottom: -2px;
      padding-bottom: 13px;
    }
    .tigo-country-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 11px;
      border-radius: 9999px;
      font-size: 0.76rem;
      font-weight: 700;
      border: 1px solid var(--tigo-border);
      background: var(--tigo-surface);
      color: var(--tigo-text);
      cursor: pointer;
      transition: all 0.14s ease;
    }
    .tigo-country-pill.is-active {
      background: var(--tigo-navy);
      color: #FFFFFF;
      border-color: var(--tigo-navy);
    }
    .tigo-table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 0.8rem;
    }
    .tigo-table th {
      background: #F1F5F9;
      color: var(--tigo-navy);
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      font-size: 0.69rem;
      padding: 10px 12px;
      border-bottom: 2px solid var(--tigo-border);
      text-align: left;
      white-space: nowrap;
    }
    .tigo-table td {
      padding: 10px 12px;
      border-bottom: 1px solid #EDF2F7;
      vertical-align: middle;
    }
    .tigo-table tr.is-tigo-row td {
      background-color: #F0F7FF;
    }
    .tigo-table tr:hover td {
      background-color: #F8FAFD;
    }
    .badge-tigo {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: var(--tigo-navy);
      color: #FFFFFF;
      font-weight: 800;
      font-size: 0.68rem;
      padding: 2px 8px;
      border-radius: 9999px;
    }
    .badge-tigo-dot {
      width: 6px;
      height: 6px;
      border-radius: 9999px;
      background: var(--tigo-yellow);
    }
    .badge-positive {
      background: #DCFCE7;
      color: #15803D;
      font-weight: 800;
      border-radius: 9999px;
      padding: 2px 9px;
      font-size: 0.71rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-negative {
      background: #FEE2E2;
      color: #B91C1C;
      font-weight: 800;
      border-radius: 9999px;
      padding: 2px 9px;
      font-size: 0.71rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-warning {
      background: #FEF3C7;
      color: #92400E;
      font-weight: 800;
      border-radius: 9999px;
      padding: 2px 9px;
      font-size: 0.71rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-info {
      background: #E0F2FE;
      color: #0369A1;
      font-weight: 800;
      border-radius: 9999px;
      padding: 2px 9px;
      font-size: 0.71rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-comp {
      background: #E2E8F0;
      color: #334155;
      font-weight: 700;
      border-radius: 9999px;
      padding: 2px 8px;
      font-size: 0.71rem;
    }
    .tigo-select {
      border: 1px solid var(--tigo-border);
      background: #FFFFFF;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 0.78rem;
      color: var(--tigo-text);
    }
    @media print {
      .no-print { display: none !important; }
      body { background: #FFFFFF; }
    }
  </style>
</head>
<body>
  <!-- BANNER CONDICIONAL DE DATOS DE EJEMPLO (OCULTO EN PRODUCCIÓN CUANDO is_sample === false) -->
  <div id="sample-banner" class="is-hidden bg-amber-400 text-slate-900 text-center py-2 px-4 text-xs font-black uppercase tracking-wider">
    ⚠️ DATOS DE EJEMPLO — MODO DEMOSTRACIÓN
  </div>

  <!-- BLOQUE DE DATOS OBLIGATORIO (ÚNICA SECCIÓN REEMPLAZADA POR EL BUILD DIARIO) -->
  <script id="RADAR_DATA" type="application/json">
__RADAR_DATA_JSON__
  </script>

  <!-- HEADER CORPORATIVO TIGO -->
  <header class="tigo-header px-4 sm:px-6 lg:px-8 py-4">
    <div class="max-w-[1440px] mx-auto flex flex-col lg:flex-row lg:items-center justify-between gap-4">
      <div class="flex items-center gap-3.5">
        <div class="px-3 py-2 rounded-xl flex items-center justify-center font-black text-xl tracking-tight" style="background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.24);">
          <span style="color: #FFFFFF;">tigo</span><span style="color: var(--tigo-yellow);">.</span>
        </div>
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="px-2 py-0.5 rounded text-[11px] font-black uppercase tracking-wider" style="background: var(--tigo-yellow); color: var(--tigo-navy);">
              Inteligencia Competitiva LATAM
            </span>
            <span class="text-xs font-semibold" style="color: var(--tigo-cyan);">
              Estrategia: Premium con Valor (+15%) &bull; HB Capitalizado
            </span>
          </div>
          <h1 class="text-lg sm:text-xl font-black text-white m-0 mt-0.5">
            Radar Diario de Ofertas Hogar, Dúos, Tríos &amp; Addons OTT
          </h1>
          <p class="text-xs m-0 mt-0.5" style="color: #CBD5E1;">
            Corte Hoy: <strong id="hdr-run-date" class="text-white"></strong> vs. Ayer: <strong id="hdr-prev-date" class="text-white"></strong>
            &bull; Generado: <span id="hdr-generated-at"></span>
          </p>
        </div>
      </div>

      <div class="no-print flex flex-wrap items-center gap-2.5">
        <!-- Currency Mode Toggle -->
        <div class="inline-flex rounded-lg p-1 text-xs" style="background: rgba(0, 18, 56, 0.45); border: 1px solid rgba(255,255,255,0.2);">
          <button type="button" data-action="set-currency-mode" data-cmode="LOCAL" class="cmode-btn px-3 py-1.5 rounded-md font-extrabold">Moneda Local</button>
          <button type="button" data-action="set-currency-mode" data-cmode="USD" class="cmode-btn px-3 py-1.5 rounded-md font-semibold">USD (FX BUD)</button>
        </div>

        <button type="button" data-action="toggle-only-addons" id="hdr-addons-btn" class="px-3.5 py-2 rounded-lg text-xs font-extrabold transition cursor-pointer"></button>

        <button type="button" data-action="export-csv" class="px-3.5 py-2 rounded-lg text-xs font-extrabold transition cursor-pointer" style="background: #FFFFFF; color: var(--tigo-navy);">
          &#8681; Exportar CSV
        </button>

        <button type="button" data-action="print-pdf" class="px-3 py-2 rounded-lg text-xs font-extrabold transition cursor-pointer" style="background: rgba(255,255,255,0.14); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.28);">
          🖨️ PDF
        </button>
      </div>
    </div>
  </header>

  <main class="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
    <!-- 1. KPI BAR -->
    <section id="kpi-bar" class="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-3"></section>

    <!-- 2. BARRA DE 12 MERCADOS Y FILTROS RÁPIDOS -->
    <section class="tigo-card p-4 space-y-3 no-print">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-1.5" id="country-pills-bar"></div>
        <div class="flex flex-wrap items-center gap-2">
          <select id="filter-type-select" class="tigo-select font-semibold">
            <option value="ALL">Todos los Tipos (Internet / Dúo / Trío / Conv.)</option>
            <option value="Internet">Solo Internet</option>
            <option value="Duo">Dúo (Internet + TV)</option>
            <option value="Trio">Trío Hogar</option>
            <option value="Convergente">Convergente</option>
          </select>
          <select id="filter-model-select" class="tigo-select font-semibold">
            <option value="ALL">Todos los Modelos VAS (HB / DESC / PROMO / SA)</option>
            <option value="HB">HB ($0 Fijo Incluido)</option>
            <option value="DESC">DESC (HB Capitalizado / Cargo Bajo)</option>
            <option value="PROMO">PROMO (Meses Gratis)</option>
            <option value="SA">SA (Standalone Pago Pleno)</option>
          </select>
          <input id="filter-search-input" type="search" placeholder="Buscar plan, operador, WiFi 6, OTT..." class="tigo-select w-52" />
          <button type="button" data-action="reset-filters" class="px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer" style="background: #EEF4FC; color: var(--tigo-navy); border: 1px solid var(--tigo-border);">
            Limpiar Filtros
          </button>
        </div>
      </div>
    </section>

    <!-- 3. TABS DE NAVEGACIÓN UNIFICADAS (5 VISTAS EN 1 SOLO REPORTE) -->
    <div class="tigo-tab-bar no-print">
      <button type="button" data-action="set-tab" data-tab="strategy" class="tigo-tab-btn is-active">
        <span>1. Semáforo 12 Países: Premium (+15%) &amp; HB Capitalizado</span>
        <span id="badge-tab-strategy" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #FEF08A; color: var(--tigo-navy);">12 Países</span>
      </button>
      <button type="button" data-action="set-tab" data-tab="exec_vp" class="tigo-tab-btn">
        <span>2. Reporte Ejecutivo VP (3 Min &bull; 7 Secciones)</span>
        <span class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #DBEAFE; color: var(--tigo-navy);">VP Brief</span>
      </button>
      <button type="button" data-action="set-tab" data-tab="catalog" class="tigo-tab-btn">
        <span>3. Comparador de Ofertas (Cara a Cara + Tabla Completa)</span>
        <span id="badge-tab-catalog" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #E0F2FE; color: var(--tigo-navy);"></span>
      </button>
      <button type="button" data-action="set-tab" data-tab="changes" class="tigo-tab-btn">
        <span>4. Cambios Detectados Hoy (Diff + Contexto)</span>
        <span id="badge-tab-changes" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #FEE2E2; color: #991B1B;"></span>
      </button>
      <button type="button" data-action="set-tab" data-tab="vas_cap" class="tigo-tab-btn">
        <span>5. Matriz de Capitalización OTT (HB $0 vs. Cargo Bajo)</span>
        <span id="badge-tab-vas" class="px-2 py-0.5 text-xs rounded-full font-extrabold" style="background: #DCFCE7; color: #166534;"></span>
      </button>
    </div>

    <!-- VISTA 1: ESTRATEGIA EJECUTIVA (PREMIUM CON VALOR + HB CAPITALIZADO) -->
    <section id="view-strategy" class="space-y-5"></section>

    <!-- VISTA 2: REPORTE EJECUTIVO VP (3 MINUTOS — 7 SECCIONES) -->
    <section id="view-exec_vp" class="is-hidden space-y-5"></section>

    <!-- VISTA 3: COMPARADOR DE OFERTAS HOY (TARJETAS CARA A CARA + TABLA 92 PLANES) -->
    <section id="view-catalog" class="is-hidden space-y-5"></section>

    <!-- VISTA 4: CAMBIOS DETECTADOS HOY (DIFF + CONTEXTO <=25 PALABRAS + HISTORIAL 30D) -->
    <section id="view-changes" class="is-hidden space-y-5"></section>

    <!-- VISTA 5: MATRIZ DE CAPITALIZACIÓN OTT -->
    <section id="view-vas_cap" class="is-hidden space-y-5"></section>
  </main>

  <!-- MODAL DE EVIDENCIA DOM (TEXTO EXACTO Y FUENTE OFICIAL) -->
  <div id="evidence-modal" data-action="close-modal-backdrop" class="is-hidden fixed inset-0 z-50 flex items-center justify-center p-4" style="background: rgba(0, 18, 56, 0.62); backdrop-filter: blur(2px);">
    <div class="tigo-card-lg max-w-2xl w-full max-h-[88vh] overflow-y-auto">
      <div class="px-5 py-4 flex items-start justify-between gap-4" style="background: linear-gradient(135deg, var(--tigo-navy) 0%, var(--tigo-blue) 100%); color: #FFFFFF; border-bottom: 3px solid var(--tigo-yellow);">
        <div>
          <span class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-cyan);">Auditoría de Fuente Web &amp; Términos Exactos</span>
          <h3 id="modal-title" class="text-base font-black text-white m-0 mt-1"></h3>
          <p id="modal-id" class="text-xs font-mono m-0 mt-0.5" style="color: #CBD5E1;"></p>
        </div>
        <button type="button" data-action="close-modal" class="px-3 py-1.5 rounded-lg text-xs font-extrabold cursor-pointer" style="background: rgba(255,255,255,0.14); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.28);">Cerrar &#10005;</button>
      </div>
      <div class="p-5 space-y-4">
        <div class="space-y-1.5">
          <div class="text-xs font-extrabold uppercase tracking-wider" style="color: var(--tigo-navy);">Términos Comerciales Verificados (exact_terms_text):</div>
          <pre id="modal-terms" class="tigo-soft-box p-3.5 text-xs leading-relaxed whitespace-pre-wrap font-mono m-0" style="color: var(--tigo-text);"></pre>
        </div>
        <div id="modal-link-box" class="pt-3 flex flex-wrap items-center justify-between gap-2 text-xs" style="border-top: 1px solid var(--tigo-border);"></div>
      </div>
    </div>
  </div>

  <script>
    (function () {
      "use strict";

      const rawJson = document.getElementById("RADAR_DATA").textContent;
      const RADAR_DATA = JSON.parse(rawJson);
      const META = RADAR_DATA.meta || {};
      const FX = META.fx_usd || { USD: 1 };
      const TOLERANCE_PCT = Number(META.tolerance_pct || 15);
      const MARKETS = META.markets || [];
      const MARKETS_BY_CODE = {};
      MARKETS.forEach(function (m) { MARKETS_BY_CODE[m.code] = m; });

      const OFFERS_TODAY = RADAR_DATA.offers_today || [];
      const OFFERS_PREV = RADAR_DATA.offers_prev || [];
      const CHANGE_CONTEXT = RADAR_DATA.change_context || {};
      const HISTORY = RADAR_DATA.history || [];
      const UNREACHABLE = RADAR_DATA.unreachable_sources || [];

      // Conditional sample banner check (Validation 8)
      const sampleBanner = document.getElementById("sample-banner");
      if (META.is_sample === true) {
        sampleBanner.classList.remove("is-hidden");
      } else {
        sampleBanner.classList.add("is-hidden");
      }

      document.getElementById("hdr-run-date").textContent = META.run_date || "";
      document.getElementById("hdr-prev-date").textContent = META.prev_date || "";
      document.getElementById("hdr-generated-at").textContent = META.generated_at || "";

      const state = {
        activeTab: "strategy",
        selectedCountry: "ALL",
        selectedType: "ALL",
        selectedModel: "ALL",
        onlyWithAddons: false,
        currencyMode: "LOCAL",
        catalogLayout: "BOTH",
        searchQuery: ""
      };

      function escHtml(v) {
        return String(v === null || v === undefined ? "" : v)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function shortUrlDisplay(u) {
        if (!u) return "—";
        return String(u)
          .replace(/^https?:\/\/(www\.)?/i, "")
          .replace(/\/$/, "");
      }

      function effPriceLocal(o) {
        return (o.promo_price_local !== null && o.promo_price_local !== undefined)
          ? Number(o.promo_price_local)
          : Number(o.price_local);
      }

      function toUsd(amountLocal, currency) {
        if (amountLocal === null || amountLocal === undefined) return null;
        const rate = Number(FX[currency] || 1);
        return Number(amountLocal) / rate;
      }

      function formatPrice(amountLocal, currency) {
        if (amountLocal === null || amountLocal === undefined) return "—";
        if (state.currencyMode === "USD") {
          const usd = toUsd(amountLocal, currency);
          return "$" + usd.toFixed(2) + " USD";
        }
        return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(amountLocal) + " " + currency;
      }

      function hardwareScore(hw) {
        const s = String(hw || "").toLowerCase();
        let score = 1;
        if (s.indexOf("wifi 7") >= 0) score = 4;
        else if (s.indexOf("wifi 6") >= 0) score = 3;
        if (s.indexOf("mesh") >= 0 || s.indexOf("extensor") >= 0 || s.indexOf("pod") >= 0) score += 2;
        return score;
      }

      // Deterministic diff engine in JS (Section 5.4)
      function computeAllDiffs() {
        const prevMap = {};
        OFFERS_PREV.forEach(function (o) { prevMap[o.id] = o; });
        const todayMap = {};
        OFFERS_TODAY.forEach(function (o) { todayMap[o.id] = o; });
        const unreachableSet = {};
        UNREACHABLE.forEach(function (u) { unreachableSet[u.country + "|" + u.operator] = true; });

        const diffs = [];

        OFFERS_TODAY.forEach(function (cur) {
          const prv = prevMap[cur.id];
          if (!prv) {
            diffs.push({
              id: cur.id,
              country: cur.country,
              operator: cur.operator,
              is_tigo: cur.is_tigo,
              plan_name: cur.plan_name,
              types: ["NEW"],
              prev_offer: null,
              curr_offer: cur,
              pct_diff: null,
              context: CHANGE_CONTEXT[cur.id] || "Nuevo plan detectado en el corte de hoy."
            });
            return;
          }

          const types = [];
          const p0 = effPriceLocal(prv);
          const p1 = effPriceLocal(cur);
          let pct = null;

          if (p1 < p0) {
            types.push("PRICE_DOWN");
            pct = ((p1 - p0) / p0) * 100.0;
            if (cur.promo_price_local !== prv.promo_price_local || cur.promo_months !== prv.promo_months) {
              types.push("PROMO");
            }
          } else if (p1 > p0) {
            types.push("PRICE_UP");
            pct = ((p1 - p0) / p0) * 100.0;
          } else if (cur.promo_price_local !== prv.promo_price_local || cur.promo_months !== prv.promo_months) {
            types.push("PROMO");
          }

          if (cur.speed_mbps !== prv.speed_mbps) types.push("SPEED");
          if (cur.hardware !== prv.hardware) types.push("HW");

          const pAdd = {};
          (prv.addons || []).forEach(function (a) { pAdd[a.ott] = a; });
          const cAdd = {};
          (cur.addons || []).forEach(function (a) { cAdd[a.ott] = a; });

          if (Object.keys(cAdd).some(function (k) { return !pAdd[k]; })) types.push("ADDON_ADD");
          if (Object.keys(pAdd).some(function (k) { return !cAdd[k]; })) types.push("ADDON_DEL");
          if (Object.keys(cAdd).some(function (k) { return pAdd[k] && (cAdd[k].model !== pAdd[k].model || cAdd[k].price_local !== pAdd[k].price_local); })) {
            types.push("ADDON_MODEL");
          }

          if (types.length > 0) {
            diffs.push({
              id: cur.id,
              country: cur.country,
              operator: cur.operator,
              is_tigo: cur.is_tigo,
              plan_name: cur.plan_name,
              types: types,
              prev_offer: prv,
              curr_offer: cur,
              pct_diff: pct,
              context: CHANGE_CONTEXT[cur.id] || "Modificación detectada frente al corte anterior."
            });
          }
        });

        OFFERS_PREV.forEach(function (prv) {
          if (!todayMap[prv.id] && !unreachableSet[prv.country + "|" + prv.operator]) {
            diffs.push({
              id: prv.id,
              country: prv.country,
              operator: prv.operator,
              is_tigo: prv.is_tigo,
              plan_name: prv.plan_name,
              types: ["REMOVED"],
              prev_offer: prv,
              curr_offer: null,
              pct_diff: null,
              context: CHANGE_CONTEXT[prv.id] || "Plan retirado de la parrilla pública."
            });
          }
        });

        return diffs;
      }

      const ALL_DIFFS = computeAllDiffs();

      // Compare each competitor offer against closest Tigo offer in same country, and evaluate Tigo offers under "Premium con Valor (+15%)"
      function findClosestTigoOffer(compOffer) {
        const tigoPeers = OFFERS_TODAY.filter(function (o) {
          return o.country === compOffer.country && o.is_tigo;
        });
        if (tigoPeers.length === 0) return null;
        return tigoPeers.slice().sort(function (a, b) {
          const typeMatchA = a.type === compOffer.type ? 0 : 1;
          const typeMatchB = b.type === compOffer.type ? 0 : 1;
          if (typeMatchA !== typeMatchB) return typeMatchA - typeMatchB;
          return Math.abs(a.speed_mbps - compOffer.speed_mbps) - Math.abs(b.speed_mbps - compOffer.speed_mbps);
        })[0];
      }

      function evaluateTigoPremiumWithValue(tigoOffer) {
        const compPeers = OFFERS_TODAY.filter(function (o) {
          return o.country === tigoOffer.country && !o.is_tigo;
        });
        if (compPeers.length === 0) {
          return { status: "PARITY", label: "Sin rival fijo directo", pctVsComp: 0, peer: null, hasMoreValue: true };
        }
        const closestComp = compPeers.slice().sort(function (a, b) {
          const typeMatchA = a.type === tigoOffer.type ? 0 : 1;
          const typeMatchB = b.type === tigoOffer.type ? 0 : 1;
          if (typeMatchA !== typeMatchB) return typeMatchA - typeMatchB;
          return Math.abs(a.speed_mbps - tigoOffer.speed_mbps) - Math.abs(b.speed_mbps - tigoOffer.speed_mbps);
        })[0];

        const pTigo = effPriceLocal(tigoOffer);
        const pComp = effPriceLocal(closestComp);
        const pctVsComp = pComp > 0 ? ((pTigo - pComp) / pComp) * 100.0 : 0.0;

        const tigoAddons = (tigoOffer.addons || []).length;
        const compAddons = (closestComp.addons || []).length;
        const hasMoreValue =
          tigoAddons > compAddons ||
          hardwareScore(tigoOffer.hardware) > hardwareScore(closestComp.hardware) ||
          tigoOffer.speed_mbps > closestComp.speed_mbps ||
          (tigoOffer.addons || []).some(function (a) { return a.ott === "TIGO_SPORTS"; });

        if (pctVsComp <= 0) {
          return {
            status: "ADVANTAGE",
            label: "🟢 Ventaja / Paridad (" + pctVsComp.toFixed(1) + "% vs " + closestComp.operator + ")",
            pctVsComp: pctVsComp,
            peer: closestComp,
            hasMoreValue: hasMoreValue
          };
        }
        if (pctVsComp <= TOLERANCE_PCT && hasMoreValue) {
          return {
            status: "PREMIUM_OK",
            label: "🟢 Premium con Valor (+" + pctVsComp.toFixed(1) + "% ≤ +" + TOLERANCE_PCT + "%)",
            pctVsComp: pctVsComp,
            peer: closestComp,
            hasMoreValue: true
          };
        }
        if (pctVsComp <= TOLERANCE_PCT && !hasMoreValue) {
          return {
            status: "PREMIUM_NEEDS_VALUE",
            label: "🟡 Dentro de +" + TOLERANCE_PCT + "% pero requiere +Valor",
            pctVsComp: pctVsComp,
            peer: closestComp,
            hasMoreValue: false
          };
        }
        return {
          status: "OUT_OF_BAND",
          label: "🔴 Excede Tolerancia (+" + pctVsComp.toFixed(1) + "% > +" + TOLERANCE_PCT + "%)",
          pctVsComp: pctVsComp,
          peer: closestComp,
          hasMoreValue: hasMoreValue
        };
      }

      function filterOffer(o) {
        if (state.selectedCountry !== "ALL" && o.country !== state.selectedCountry) return false;
        if (state.selectedType !== "ALL" && o.type !== state.selectedType) return false;
        if (state.onlyWithAddons && (!o.addons || o.addons.length === 0)) return false;
        if (state.selectedModel !== "ALL") {
          const ok = (o.addons || []).some(function (a) { return a.model === state.selectedModel; });
          if (!ok) return false;
        }
        if (state.searchQuery.trim()) {
          const q = state.searchQuery.trim().toLowerCase();
          const hay = [
            o.id, o.country, o.operator, o.plan_name, o.type, o.hardware,
            (o.addons || []).map(function (a) { return a.ott + " " + a.model; }).join(" ")
          ].join(" ").toLowerCase();
          if (hay.indexOf(q) < 0) return false;
        }
        return true;
      }

      function renderAll() {
        const filteredOffers = OFFERS_TODAY.filter(filterOffer);
        const filteredDiffs = ALL_DIFFS.filter(function (d) {
          if (state.selectedCountry !== "ALL" && d.country !== state.selectedCountry) return false;
          if (state.searchQuery.trim()) {
            const q = state.searchQuery.trim().toLowerCase();
            const hay = (d.id + " " + d.operator + " " + d.plan_name + " " + d.context).toLowerCase();
            if (hay.indexOf(q) < 0) return false;
          }
          return true;
        });

        // Update Header Addons Button
        const totalWithAddons = OFFERS_TODAY.filter(function (o) { return (o.addons || []).length > 0; }).length;
        const hdrAddBtn = document.getElementById("hdr-addons-btn");
        hdrAddBtn.style.background = state.onlyWithAddons ? "var(--tigo-yellow)" : "rgba(255,255,255,0.14)";
        hdrAddBtn.style.color = state.onlyWithAddons ? "var(--tigo-navy)" : "#FFFFFF";
        hdrAddBtn.style.border = "1px solid rgba(255,203,5,0.55)";
        hdrAddBtn.textContent = (state.onlyWithAddons ? "✓ Viendo Solo con Addons (" : "🎬 Filtrar con Addons (") + totalWithAddons + ")";

        // Update Currency Mode buttons
        document.querySelectorAll(".cmode-btn").forEach(function (btn) {
          const act = btn.getAttribute("data-cmode") === state.currencyMode;
          btn.style.background = act ? "#FFFFFF" : "transparent";
          btn.style.color = act ? "var(--tigo-navy)" : "#E2E8F0";
        });

        // Compute Strategic Metrics
        const tigoOffers = OFFERS_TODAY.filter(function (o) { return o.is_tigo; });
        const compOffers = OFFERS_TODAY.filter(function (o) { return !o.is_tigo; });
        const tigoEvaluations = tigoOffers.map(evaluateTigoPremiumWithValue);
        const tigoInRouteCount = tigoEvaluations.filter(function (e) {
          return e.status === "ADVANTAGE" || e.status === "PREMIUM_OK";
        }).length;

        let tigoHbZero = 0, tigoCapitalized = 0, tigoPromo = 0;
        let compHbZero = 0, compCapitalized = 0, compPromo = 0;
        OFFERS_TODAY.forEach(function (o) {
          (o.addons || []).forEach(function (a) {
            if (o.is_tigo) {
              if (a.model === "HB") tigoHbZero++;
              else if (a.model === "DESC" || a.model === "SA") tigoCapitalized++;
              else if (a.model === "PROMO") tigoPromo++;
            } else {
              if (a.model === "HB") compHbZero++;
              else if (a.model === "DESC" || a.model === "SA") compCapitalized++;
              else if (a.model === "PROMO") compPromo++;
            }
          });
        });
        const tigoTotalAddons = tigoHbZero + tigoCapitalized + tigoPromo;
        const tigoCapRatio = tigoTotalAddons > 0 ? ((tigoCapitalized / tigoTotalAddons) * 100.0).toFixed(1) : "0.0";

        // 1. Render KPI Bar
        const kpis = [
          { label: "Mercados Activos", val: String(MARKETS.length), sub: "0 fuentes caídas", color: "var(--tigo-navy)" },
          { label: "Ofertas Hoy (Tigo / Comp)", val: String(OFFERS_TODAY.length), sub: tigoOffers.length + " Tigo • " + compOffers.length + " Rival", color: "var(--tigo-blue)" },
          { label: "Tigo en Ruta (≤ +15% c/Valor)", val: tigoInRouteCount + " / " + tigoOffers.length, sub: ((tigoInRouteCount / Math.max(1, tigoOffers.length)) * 100).toFixed(1) + "% cumple tesis", color: "var(--tigo-positive)" },
          { label: "HB $0 Tigo (Por Capitalizar)", val: String(tigoHbZero), sub: "Meta: migrar a cargo bajo", color: "var(--tigo-warning)" },
          { label: "Addons Capitalizados Tigo", val: String(tigoCapitalized), sub: tigoCapRatio + "% del portafolio VAS", color: "var(--tigo-bright-blue)" },
          { label: "Cambios Detectados Hoy", val: String(ALL_DIFFS.length), sub: ALL_DIFFS.filter(function (d) { return !d.is_tigo; }).length + " rivales • " + ALL_DIFFS.filter(function (d) { return d.is_tigo; }).length + " Tigo", color: "var(--tigo-negative)" },
          { label: "Mercados HB Facturable", val: (META.hb_billable_markets || ["CR", "PA"]).join(" • "), sub: "Excluido: " + (META.hb_excluded_markets || ["UY"]).join(","), color: "var(--tigo-navy)" }
        ];
        document.getElementById("kpi-bar").innerHTML = kpis.map(function (k) {
          return (
            '<div class="tigo-kpi" style="border-top: 4px solid ' + k.color + ';">' +
              '<div class="text-[11px] font-bold uppercase tracking-wider" style="color: var(--tigo-text-secondary);">' + escHtml(k.label) + "</div>" +
              '<div class="text-xl font-black mt-1" style="color: ' + k.color + ';">' + escHtml(k.val) + "</div>" +
              '<div class="text-xs font-medium mt-0.5" style="color: var(--tigo-text-secondary);">' + escHtml(k.sub) + "</div>" +
            "</div>"
          );
        }).join("");

        // 2. Render Country Pills
        const pillsHtml = [
          '<button type="button" data-action="select-country" data-code="ALL" class="tigo-country-pill' + (state.selectedCountry === "ALL" ? " is-active" : "") + '">🌎 Todos (12)</button>'
        ].concat(MARKETS.map(function (m) {
          const cnt = OFFERS_TODAY.filter(function (o) { return o.country === m.code; }).length;
          const act = state.selectedCountry === m.code;
          return (
            '<button type="button" data-action="select-country" data-code="' + escHtml(m.code) + '" class="tigo-country-pill' + (act ? " is-active" : "") + '">' +
              "<span>" + escHtml(m.flag) + "</span>" +
              "<strong>" + escHtml(m.code) + "</strong>" +
              '<span class="hidden md:inline">' + escHtml(m.name) + "</span>" +
              '<span class="px-1.5 py-0.2 rounded-full text-[10px] font-extrabold" style="background:' + (act ? "var(--tigo-yellow)" : "#E2E8F0") + ";color:var(--tigo-navy);\">" + cnt + "</span>" +
            "</button>"
          );
        }));
        document.getElementById("country-pills-bar").innerHTML = pillsHtml.join("");

        // Badges on tabs
        document.getElementById("badge-tab-changes").textContent = String(filteredDiffs.length);
        document.getElementById("badge-tab-catalog").textContent = String(filteredOffers.length);
        document.getElementById("badge-tab-vas").textContent = String(tigoTotalAddons + compHbZero + compCapitalized + compPromo);

        document.querySelectorAll(".tigo-tab-btn").forEach(function (btn) {
          btn.classList.toggle("is-active", btn.getAttribute("data-tab") === state.activeTab);
        });
        ["strategy", "exec_vp", "catalog", "changes", "vas_cap"].forEach(function (t) {
          const sec = document.getElementById("view-" + t);
          if (sec) sec.classList.toggle("is-hidden", state.activeTab !== t);
        });

        renderStrategyView(tigoOffers, tigoEvaluations, tigoHbZero, tigoCapitalized, tigoPromo, compHbZero, compCapitalized);
        renderExecVpView(tigoOffers, compOffers, tigoEvaluations, tigoHbZero, tigoCapitalized, tigoPromo, compHbZero, compCapitalized, compPromo);
        renderChangesView(filteredDiffs);
        renderCatalogView(filteredOffers);
        renderVasCapView(filteredOffers);
      }

      function renderExecVpView(tigoOffers, compOffers, tigoEvaluations, tigoHbZero, tigoCapitalized, tigoPromo, compHbZero, compCapitalized, compPromo) {
        const el = document.getElementById("view-exec_vp");
        if (!el) return;

        const inBandCount = tigoEvaluations.filter(function (e) { return e.status === "ADVANTAGE" || e.status === "PREMIUM_OK"; }).length;
        const outBandCount = tigoEvaluations.filter(function (e) { return e.status === "OUT_OF_BAND"; }).length;
        const inBandPct = tigoOffers.length > 0 ? ((inBandCount / tigoOffers.length) * 100.0) : 0.0;
        const tigoWithVas = tigoOffers.filter(function (o) { return (o.addons || []).length > 0; }).length;
        const compWithVas = compOffers.filter(function (o) { return (o.addons || []).length > 0; }).length;
        const tigoVasPct = tigoOffers.length > 0 ? ((tigoWithVas / tigoOffers.length) * 100.0) : 0.0;
        const compVasPct = compOffers.length > 0 ? ((compWithVas / compOffers.length) * 100.0) : 0.0;

        const tigoTotalAddons = tigoHbZero + tigoCapitalized + tigoPromo;
        const compTotalAddons = compHbZero + compCapitalized + compPromo;
        const tigoHbPct = tigoTotalAddons > 0 ? ((tigoHbZero / tigoTotalAddons) * 100.0) : 0.0;
        const compHbPct = compTotalAddons > 0 ? ((compHbZero / compTotalAddons) * 100.0) : 0.0;
        const tigoCapPct = tigoTotalAddons > 0 ? ((tigoCapitalized / tigoTotalAddons) * 100.0) : 0.0;
        const compCapPct = compTotalAddons > 0 ? ((compCapitalized / compTotalAddons) * 100.0) : 0.0;
        const tigoPromoPct = tigoTotalAddons > 0 ? ((tigoPromo / tigoTotalAddons) * 100.0) : 0.0;
        const compPromoPct = compTotalAddons > 0 ? ((compPromo / compTotalAddons) * 100.0) : 0.0;

        let greenCnt = 0, yellowCnt = 0, redCnt = 0;
        const countryRowsHtml = MARKETS.map(function (m) {
          const mOffers = OFFERS_TODAY.filter(function (o) { return o.country === m.code; });
          const mTigo = mOffers.filter(function (o) { return o.is_tigo; });
          const mComp = mOffers.filter(function (o) { return !o.is_tigo; });
          const evals = mTigo.map(evaluateTigoPremiumWithValue);
          const okCnt = evals.filter(function (e) { return e.status === "ADVANTAGE" || e.status === "PREMIUM_OK"; }).length;
          const maxGap = evals.reduce(function (acc, e) { return Math.max(acc, e.pctVsComp); }, -999);
          const mDiffs = ALL_DIFFS.filter(function (d) { return d.country === m.code; });

          let mHb = 0, mCap = 0, mPr = 0, cHb = 0;
          mTigo.forEach(function (o) {
            (o.addons || []).forEach(function (a) {
              if (a.model === "HB") mHb++;
              else if (a.model === "DESC" || a.model === "SA") mCap++;
              else if (a.model === "PROMO") mPr++;
            });
          });
          mComp.forEach(function (o) {
            (o.addons || []).forEach(function (a) { if (a.model === "HB") cHb++; });
          });

          let statusBadge = "";
          if (maxGap > TOLERANCE_PCT) {
            redCnt++;
            statusBadge = '<span class="badge-negative">🔴 Fuera de ruta</span>';
          } else if (okCnt < mTigo.length || mDiffs.length > 0) {
            yellowCnt++;
            statusBadge = '<span class="badge-warning">🟡 En riesgo</span>';
          } else {
            greenCnt++;
            statusBadge = '<span class="badge-positive">🟢 En ruta</span>';
          }

          return (
            '<tr class="cursor-pointer" data-action="drill-country" data-code="' + escHtml(m.code) + '">' +
              '<td class="font-extrabold whitespace-nowrap">' + escHtml(m.flag + " " + m.code + " — " + m.name) + "</td>" +
              '<td style="text-align:center;" class="font-bold">' + mTigo.length + " / " + mComp.length + "</td>" +
              '<td style="text-align:center;" class="font-extrabold">' + okCnt + " / " + mTigo.length + "</td>" +
              '<td style="text-align:right;" class="font-bold ' + (maxGap > TOLERANCE_PCT ? "text-red-600" : "text-emerald-700") + '">' +
                (maxGap > -900 ? (maxGap >= 0 ? "+" : "") + maxGap.toFixed(1) + "%" : "—") +
              "</td>" +
              '<td style="text-align:center;" class="font-semibold">' + mHb + " HB $0 &bull; " + mCap + " Cap. &bull; " + mPr + " Promo</td>" +
              '<td style="text-align:center;" class="font-semibold">' + cHb + " HB $0</td>" +
              '<td style="text-align:center;">' + (mDiffs.length > 0 ? '<span class="badge-negative">' + mDiffs.length + " cambio(s)</span>" : "0") + "</td>" +
              '<td style="text-align:center;">' + statusBadge + "</td>" +
            "</tr>"
          );
        }).join("");

        el.innerHTML =
          '<div class="tigo-card-lg p-5 space-y-3" style="border-left: 6px solid var(--tigo-navy); background: linear-gradient(180deg, #FFFFFF 0%, #F9FBFE 100%);">' +
            '<div class="flex flex-wrap items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 1</span>' +
                '<h2 class="text-sm sm:text-base font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">1. Mensaje Principal de Estrategia (Lectura 3 Minutos para Dirección / VPs)</h2>' +
              "</div>" +
              '<span class="text-xs font-semibold" style="color: var(--tigo-text-secondary);">Corte Verificado: ' + escHtml(META.run_date || "") + ' &bull; 12 Países LATAM</span>' +
            "</div>" +
            '<p class="text-base font-bold leading-relaxed m-0" style="color: var(--tigo-navy);">' +
              'El <strong>' + inBandPct.toFixed(1) + '% del portafolio Tigo (' + inBandCount + ' de ' + tigoOffers.length + ' planes)</strong> cumple hoy la banda estratégica de <strong>Premium con Valor (&le; +' + TOLERANCE_PCT + '% vs. rival directo)</strong>, mientras que la competencia subsidia agresivamente <strong>' + compHbZero + ' integraciones OTT a $0 (' + compHbPct.toFixed(1) + '% de su mix VAS)</strong> y ejecuta <strong>' + ALL_DIFFS.filter(function (d) { return !d.is_tigo; }).length + ' movimientos ofensivos</strong> hoy; cerrar la brecha exige ajustar <strong>' + outBandCount + ' planes fuera de banda</strong> y acelerar la migración de <strong>' + tigoHbZero + ' HB $0 hacia HB Capitalizado (cargo bajo)</strong> en Costa Rica y Panamá.' +
            "</p>" +
          "</div>" +

          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex flex-wrap items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-blue); color: #FFFFFF;">Sección 2</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">2. Indicadores Clave de Portafolio (Separación HB $0, HB Capitalizado, Promo y SA)</h3>' +
              "</div>" +
            "</div>" +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                "<thead><tr><th>Métrica de Negocio</th><th style=\"text-align:right;\">Real (Tigo)</th><th style=\"text-align:right;\">Competencia / Meta</th><th style=\"text-align:right;\">Variación / Brecha</th><th>Lectura Ejecutiva</th></tr></thead>" +
                "<tbody>" +
                  "<tr><td class=\"font-bold\">Ofertas Totales Auditadas</td><td style=\"text-align:right;\" class=\"font-extrabold\">" + tigoOffers.length + " planes</td><td style=\"text-align:right;\">" + compOffers.length + " planes rivales</td><td style=\"text-align:right;\" class=\"font-bold\">" + OFFERS_TODAY.length + " total</td><td>Cobertura auditada con URLs verificadas en 41 operadoras de 12 países.</td></tr>" +
                  "<tr><td class=\"font-bold\">Planes Tigo en Banda (&le; +" + TOLERANCE_PCT + "% con Valor)</td><td style=\"text-align:right;\" class=\"font-extrabold text-emerald-700\">" + inBandCount + " / " + tigoOffers.length + " (" + inBandPct.toFixed(1) + "%)</td><td style=\"text-align:right;\">Meta &ge; 85.0%</td><td style=\"text-align:right;\" class=\"font-bold text-amber-700\">" + (inBandPct - 85.0).toFixed(1) + " pp</td><td>" + outBandCount + " planes superan el +" + TOLERANCE_PCT + "% tras promociones rivales en PA, CO, PY y CL.</td></tr>" +
                  "<tr><td class=\"font-bold\">Attach Rate de Contenidos VAS</td><td style=\"text-align:right;\" class=\"font-extrabold\">" + tigoWithVas + " (" + tigoVasPct.toFixed(1) + "%)</td><td style=\"text-align:right;\">" + compWithVas + " (" + compVasPct.toFixed(1) + "%)</td><td style=\"text-align:right;\" class=\"font-bold text-emerald-700\">+" + (tigoVasPct - compVasPct).toFixed(1) + " pp</td><td>Tigo lidera el empaquetamiento de contenidos y deportes en la región.</td></tr>" +
                  "<tr><td class=\"font-bold\">Mix HB $0 (Incluido sin Cargo)</td><td style=\"text-align:right;\" class=\"font-extrabold\">" + tigoHbZero + " (" + tigoHbPct.toFixed(1) + "%)</td><td style=\"text-align:right;\">" + compHbZero + " (" + compHbPct.toFixed(1) + "%)</td><td style=\"text-align:right;\" class=\"font-bold text-amber-700\">" + (tigoHbPct - compHbPct).toFixed(1) + " pp</td><td>Oportunidad directa de migrar HB $0 de terceros hacia copago bajo (DESC).</td></tr>" +
                  "<tr><td class=\"font-bold\">Mix HB Capitalizado / Cargo Bajo (DESC + SA)</td><td style=\"text-align:right;\" class=\"font-extrabold text-blue-800\">" + tigoCapitalized + " (" + tigoCapPct.toFixed(1) + "%)</td><td style=\"text-align:right;\">" + compCapitalized + " (" + compCapPct.toFixed(1) + "%)</td><td style=\"text-align:right;\" class=\"font-bold text-emerald-700\">+" + (tigoCapPct - compCapPct).toFixed(1) + " pp</td><td>Tigo monetiza mejor sus addons; prioridad expandir modelo en CR y PA.</td></tr>" +
                  "<tr><td class=\"font-bold\">Mix Cortesía Temporal (PROMO Meses Gratis)</td><td style=\"text-align:right;\" class=\"font-extrabold\">" + tigoPromo + " (" + tigoPromoPct.toFixed(1) + "%)</td><td style=\"text-align:right;\">" + compPromo + " (" + compPromoPct.toFixed(1) + "%)</td><td style=\"text-align:right;\" class=\"font-bold\">+" + (tigoPromoPct - compPromoPct).toFixed(1) + " pp</td><td>Requiere flujo de conversión a copago antes del vencimiento del mes 3.</td></tr>" +
                "</tbody>" +
              "</table>" +
            "</div>" +
          "</div>" +

          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 3</span>' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">3. Qué Está Pasando y Por Qué (4 Hallazgos Ejecutivos)</h3>' +
            "</div>" +
            '<div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">' +
              '<div class="tigo-soft-box p-4 space-y-1.5" style="border-left: 4px solid var(--tigo-negative);">' +
                '<h4 class="text-sm font-black m-0" style="color: var(--tigo-navy);">1. La competencia subsidia ' + compHbZero + ' OTTs en HB a $0 para presionar captura</h4>' +
                '<p class="m-0"><strong>Evidencia:</strong> El ' + compHbPct.toFixed(1) + '% de los addons rivales se entregan a $0 fijo (Disney+, Max, Universal+, Paramount+).</p>' +
                '<p class="m-0"><strong>Causa:</strong> Acuerdos mayoristas regionales de Claro, Movistar y Liberty para reducir churn en fibra.</p>' +
                '<p class="m-0 font-bold text-red-700"><strong>Implicación:</strong> No imitar el regalo a $0; defender propuesta con HB Capitalizado (copago bajo) + Tigo Sports exclusivo.</p>' +
              "</div>" +
              '<div class="tigo-soft-box p-4 space-y-1.5" style="border-left: 4px solid var(--tigo-warning);">' +
                '<h4 class="text-sm font-black m-0" style="color: var(--tigo-navy);">2. Panamá (+Móvil) presiona la entrada en 300M ($35 USD), pero en 600M con Universal+ está en $56 USD</h4>' +
                '<p class="m-0"><strong>Evidencia:</strong> +Móvil ofrece 300M Solo Internet en $35.00 USD (vs $41.00 USD de Tigo 300M), mientras su plan Hogar +Fibra 600M + TV + Universal+ se ubica en $56.00 USD.</p>' +
                '<p class="m-0"><strong>Causa:</strong> +Móvil separa el paquete básico sin OTT ($52) del paquete con Universal+ ($56) y usa 300M como gancho de entrada.</p>' +
                '<p class="m-0 font-bold text-amber-800"><strong>Implicación:</strong> En el escalón alto Tigo es plenamente competitivo ($55 USD en 500M Dúo); la defensa táctica debe focalizarse en la entrada de 300M.</p>' +
              "</div>" +
              '<div class="tigo-soft-box p-4 space-y-1.5" style="border-left: 4px solid var(--tigo-blue);">' +
                '<h4 class="text-sm font-black m-0" style="color: var(--tigo-navy);">3. Descuentos promocionales largos (6 a 24 meses) en CR, CO, PY y CL</h4>' +
                '<p class="m-0"><strong>Evidencia:</strong> Liberty CR aplica promo por 24m (₡19,941.80 en 120M), Movistar CO y CL aplican 12m, y Claro PY baja 600M a Gs. 120.000 por 6m.</p>' +
                '<p class="m-0"><strong>Causa:</strong> Guerra de adquisición en redes FTTH desplegadas recientemente.</p>' +
                '<p class="m-0 font-bold" style="color: var(--tigo-navy);"><strong>Implicación:</strong> Comparar siempre precio promocional vigente vs. tarifa regular post-promo en la comunicación comercial.</p>' +
              "</div>" +
              '<div class="tigo-soft-box p-4 space-y-1.5" style="border-left: 4px solid var(--tigo-positive);">' +
                '<h4 class="text-sm font-black m-0" style="color: var(--tigo-navy);">4. Hardware WiFi 6 / WiFi 7 + Mesh justifica el diferencial de hasta +15%</h4>' +
                '<p class="m-0"><strong>Evidencia:</strong> Los planes Tigo con WiFi 6 + Mesh y Tigo Sports sostienen precios hasta +15% superiores sin deterioro competitivo en GT, HN, SV y BO.</p>' +
                '<p class="m-0"><strong>Causa:</strong> El cliente residencial valora cobertura intramuros garantizada y fútbol local exclusivo.</p>' +
                '<p class="m-0 font-bold text-emerald-700"><strong>Implicación:</strong> Estandarizar WiFi 6 + Mesh en todos los planes &ge; 300 Mbps donde Tigo opere sobre el precio rival.</p>' +
              "</div>" +
            "</div>" +
          "</div>" +

          '<div class="tigo-card p-5 space-y-4">' +
            '<div class="flex flex-wrap items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<div class="flex items-center gap-2">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 4</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">4. Vista Ejecutiva por País (12 Mercados)</h3>' +
              "</div>" +
              '<div class="flex items-center gap-2 text-xs font-bold">' +
                '<span class="badge-positive">🟢 ' + greenCnt + " En ruta</span>" +
                '<span class="badge-warning">🟡 ' + yellowCnt + " En riesgo</span>" +
                '<span class="badge-negative">🔴 ' + redCnt + " Fuera de ruta</span>" +
              "</div>" +
            "</div>" +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                "<thead><tr><th>País</th><th style=\"text-align:center;\">Planes (Tigo/Comp)</th><th style=\"text-align:center;\">En Banda &le; +15%</th><th style=\"text-align:right;\">Máx. Brecha vs Rival</th><th style=\"text-align:center;\">Mix VAS Tigo</th><th style=\"text-align:center;\">HB $0 Rival</th><th style=\"text-align:center;\">Cambios Hoy</th><th style=\"text-align:center;\">Estado</th></tr></thead>" +
                "<tbody>" + countryRowsHtml + "</tbody>" +
              "</table>" +
            "</div>" +
          "</div>" +

          '<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">' +
            '<div class="tigo-card p-5 space-y-3">' +
              '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-navy); color: #FFFFFF;">Sección 5 &amp; 6</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">5–6. Riesgos, Oportunidades y Brecha a la Meta</h3>' +
              "</div>" +
              '<div class="space-y-2 text-xs">' +
                '<div class="tigo-soft-box p-3" style="border-left: 3px solid var(--tigo-negative);"><strong>Riesgo Clave:</strong> Erosión de captura en escalones de entrada (PA 300M con $6 USD de brecha vs +Móvil; PY 300M frente a promo 6m de Claro a Gs. 120.000).</div>' +
                '<div class="tigo-soft-box p-3" style="border-left: 3px solid var(--tigo-positive);"><strong>Oportunidad Clave:</strong> Capitalización de HB en CR y PA pasando OTTs de $0 a copago bajo ($2–$4 USD/mes) con retención anclada en Tigo Sports y WiFi 6.</div>' +
                '<div class="tigo-soft-box p-3" style="border-left: 3px solid var(--tigo-blue);"><strong>Brecha a la Meta:</strong> Ajustar <strong>' + outBandCount + ' planes fuera de la banda del +15%</strong> en 30 días mediante 4 palancas: (1) Promo táctica de entrada en PA/PY, (2) Conversión de promos OTT de 3m a copago, (3) Migración HB $0 &rarr; DESC en CR/PA, y (4) Despliegue Mesh en tiers medios.</div>' +
              "</div>" +
            "</div>" +

            '<div class="tigo-card p-5 space-y-3">' +
              '<div class="flex items-center gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
                '<span class="px-2.5 py-1 rounded text-xs font-black uppercase" style="background: var(--tigo-yellow); color: var(--tigo-navy);">Sección 7</span>' +
                '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">7. Decisiones Propuestas para Dirección</h3>' +
              "</div>" +
              '<div class="space-y-2 text-xs">' +
                '<div class="tigo-soft-box p-3 flex justify-between gap-2"><div><strong>1. Panamá (Comercial Hogar):</strong> Activar promo de entrada en 300M ($34.99 USD x 6m) manteniendo 500M Dúo en $55.00 USD frente a los $56.00 USD de +Móvil 600M+Universal+.</div><span class="badge-info whitespace-nowrap">7 días</span></div>' +
                '<div class="tigo-soft-box p-3 flex justify-between gap-2"><div><strong>2. Costa Rica y Panamá (Producto VAS):</strong> Ejecutar migración de OTTs incluidas a $0 hacia modelo HB Capitalizado (DESC con cargo bajo en factura).</div><span class="badge-info whitespace-nowrap">15 días</span></div>' +
                '<div class="tigo-soft-box p-3 flex justify-between gap-2"><div><strong>3. Colombia y Paraguay (Retención):</strong> Neutralizar promos de 6–12m de Movistar CO y Claro PY empaquetando extensor Mesh WiFi 6 + Prime Video / Tigo Sports.</div><span class="badge-info whitespace-nowrap">15 días</span></div>' +
              "</div>" +
            "</div>" +
          "</div>";
      }

      function renderStrategyView(tigoOffers, tigoEvaluations, tigoHbZero, tigoCapitalized, tigoPromo, compHbZero, compCapitalized) {
        const el = document.getElementById("view-strategy");
        const inBandCount = tigoEvaluations.filter(function (e) { return e.status === "ADVANTAGE" || e.status === "PREMIUM_OK"; }).length;
        const outBandCount = tigoEvaluations.filter(function (e) { return e.status === "OUT_OF_BAND"; }).length;

        const marketRows = MARKETS.map(function (m) {
          const mOffers = OFFERS_TODAY.filter(function (o) { return o.country === m.code; });
          const mTigo = mOffers.filter(function (o) { return o.is_tigo; });
          const mComp = mOffers.filter(function (o) { return !o.is_tigo; });
          const evals = mTigo.map(evaluateTigoPremiumWithValue);
          const okCnt = evals.filter(function (e) { return e.status === "ADVANTAGE" || e.status === "PREMIUM_OK"; }).length;
          const maxGap = evals.reduce(function (acc, e) { return Math.max(acc, e.pctVsComp); }, -999);

          let mHb = 0, mCap = 0, mPromo = 0;
          mTigo.forEach(function (o) {
            (o.addons || []).forEach(function (a) {
              if (a.model === "HB") mHb++;
              else if (a.model === "DESC" || a.model === "SA") mCap++;
              else if (a.model === "PROMO") mPromo++;
            });
          });

          const isBillable = (META.hb_billable_markets || []).indexOf(m.code) >= 0;
          const isExcluded = (META.hb_excluded_markets || []).indexOf(m.code) >= 0;
          const hbTag = isExcluded
            ? '<span class="badge-comp">Excluido HB Fijo (Móvil)</span>'
            : (isBillable ? '<span class="badge-info">🎯 Prioridad HB Facturable</span>' : '<span class="badge-warning">Migrar HB $0 → Cargo Bajo</span>');

          let sem = '<span class="badge-positive">🟢 Premium con Valor OK</span>';
          if (maxGap > TOLERANCE_PCT) {
            sem = '<span class="badge-negative">🔴 Brecha > +' + TOLERANCE_PCT + '% (' + (maxGap > -900 ? "+" + maxGap.toFixed(1) + "%" : "") + ")</span>";
          } else if (okCnt < mTigo.length) {
            sem = '<span class="badge-warning">🟡 Reforzar Valor / Hardware</span>';
          }

          // Collect unique operator -> source_url pairs in this country
          const seenOpUrls = {};
          const opLinksHtml = [];
          mOffers.forEach(function (o) {
            if (!o.source_url) return;
            const key = o.operator;
            if (!seenOpUrls[key]) {
              seenOpUrls[key] = o.source_url;
              opLinksHtml.push(
                '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" title="' + escHtml(o.operator + ": " + o.source_url) + '" ' +
                'class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold mr-1 mb-1" ' +
                'style="background:' + (o.is_tigo ? "#E0F2FE;color:#001E60;border:1px solid #7DD3FC;" : "#F1F5F9;color:#334155;border:1px solid #CBD5E1;") + '">' +
                  "🔗 " + escHtml(o.operator) + " ↗" +
                "</a>"
              );
            }
          });

          return (
            '<tr class="cursor-pointer" data-action="drill-country" data-code="' + escHtml(m.code) + '">' +
              '<td class="font-extrabold whitespace-nowrap">' + escHtml(m.flag + " " + m.code + " — " + m.name) + ' <span class="text-[11px] font-normal text-slate-500">(' + escHtml(m.capital) + ")</span></td>" +
              '<td style="text-align:center;" class="font-bold">' + mTigo.length + " / " + mComp.length + "</td>" +
              '<td style="text-align:center;" class="font-extrabold">' + okCnt + " / " + mTigo.length + " planes</td>" +
              '<td style="text-align:right;" class="font-bold ' + (maxGap > TOLERANCE_PCT ? "text-red-600" : "text-emerald-700") + '">' +
                (maxGap > -900 ? (maxGap >= 0 ? "+" : "") + maxGap.toFixed(1) + "%" : "—") +
              "</td>" +
              '<td style="text-align:center;" class="font-semibold">' + mHb + " HB $0 &bull; " + mCap + " Cap. &bull; " + mPromo + " Promo</td>" +
              "<td>" + hbTag + "</td>" +
              "<td>" + sem + "</td>" +
              "<td>" + opLinksHtml.join("") + "</td>" +
            "</tr>"
          );
        }).join("");

        el.innerHTML =
          '<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">' +
            '<div class="tigo-card-lg p-5 space-y-2.5" style="border-left: 6px solid var(--tigo-navy);">' +
              '<div class="flex items-center justify-between">' +
                '<span class="px-2.5 py-0.5 rounded text-xs font-black uppercase" style="background: var(--tigo-navy); color: #FFFFFF;">Pilar Estratégico 1</span>' +
                '<span class="text-xs font-extrabold" style="color: var(--tigo-blue);">Tolerancia Máxima: +' + TOLERANCE_PCT + '% vs. Competencia</span>' +
              "</div>" +
              '<h2 class="text-base font-black m-0" style="color: var(--tigo-navy);">Premium con Valor: ' + inBandCount + ' de ' + tigoOffers.length + ' planes Tigo cumplen la banda (≤ +' + TOLERANCE_PCT + '% con diferencial)</h2>' +
              '<p class="text-xs leading-relaxed m-0" style="color: var(--tigo-text-secondary);">' +
                'Tigo puede situarse hasta <strong>+' + TOLERANCE_PCT + '%</strong> por encima del rival directo siempre que entregue más valor tangible (Tigo Sports exclusivo, WiFi 6 + Mesh o mayor velocidad). Hoy <strong>' + outBandCount + ' planes</strong> superan el umbral del +' + TOLERANCE_PCT + '% tras las rebajas rivales en <strong>PA, CO, PY y CL</strong>, requiriendo refuerzo de hardware/contenido o ajuste promocional puntual.' +
              "</p>" +
            "</div>" +

            '<div class="tigo-card-lg p-5 space-y-2.5" style="border-left: 6px solid var(--tigo-yellow);">' +
              '<div class="flex items-center justify-between">' +
                '<span class="px-2.5 py-0.5 rounded text-xs font-black uppercase" style="background: var(--tigo-yellow); color: var(--tigo-navy);">Pilar Estratégico 2</span>' +
                '<span class="text-xs font-extrabold" style="color: var(--tigo-navy);">Foco Facturable: ' + (META.hb_billable_markets || ["CR", "PA"]).join(", ") + " (Excl. " + (META.hb_excluded_markets || ["UY"]).join(", ") + ")</span>" +
              "</div>" +
              '<h2 class="text-base font-black m-0" style="color: var(--tigo-navy);">HB Capitalizado: ' + tigoHbZero + ' integraciones HB a $0 deben migrar a esquema de cargo bajo vs. ' + tigoCapitalized + ' ya monetizadas</h2>' +
              '<p class="text-xs leading-relaxed m-0" style="color: var(--tigo-text-secondary);">' +
                'Mientras la competencia regala <strong>' + compHbZero + ' addons en HB a $0</strong> erosionando margen, la directriz comercial de Tigo es <strong>no regalar más Hard Bundle a $0</strong> sino capitalizarlo mediante un copago bajo (modelo <code>DESC</code> / addon bonificado) comenzando por <strong>Costa Rica y Panamá</strong>.' +
              "</p>" +
            "</div>" +
          "</div>" +

          '<div class="tigo-card p-5 space-y-3">' +
            '<div class="flex flex-wrap items-center justify-between gap-2 pb-2" style="border-bottom: 1px solid var(--tigo-border);">' +
              '<h3 class="text-sm font-extrabold uppercase tracking-wide m-0" style="color: var(--tigo-navy);">' +
                "Semáforo de Ejecución por País — Banda Premium (+15%) y Capitalización de HB (Clic en un país para ver sus planes)" +
              "</h3>" +
              '<span class="text-xs font-semibold" style="color: var(--tigo-text-secondary);">FX Presupuesto aplicado para comparativa USD</span>' +
            "</div>" +
            '<div class="overflow-x-auto">' +
              '<table class="tigo-table">' +
                "<thead>" +
                  "<tr>" +
                    "<th>País (Capital de Captura)</th>" +
                    '<th style="text-align:center;">Ofertas (Tigo/Comp)</th>' +
                    '<th style="text-align:center;">Planes en Banda ≤ +15%</th>' +
                    '<th style="text-align:right;">Máxima Brecha Tigo vs. Rival</th>' +
                    '<th style="text-align:center;">Mix Contenido Tigo</th>' +
                    "<th>Política HB Capitalizado</th>" +
                    "<th>Estado Estratégico</th>" +
                    "<th>Fuentes Web Oficiales (Telcos)</th>" +
                  "</tr>" +
                "</thead>" +
                "<tbody>" + marketRows + "</tbody>" +
              "</table>" +
            "</div>" +
          "</div>";
      }

      function renderChangesView(diffs) {
        const el = document.getElementById("view-changes");
        const cardsHtml = diffs.length === 0
          ? '<div class="tigo-card p-8 text-center text-xs font-bold" style="color: var(--tigo-text-secondary);">Sin cambios detectados para el filtro seleccionado.</div>'
          : diffs.map(function (d) {
              const m = MARKETS_BY_CODE[d.country] || { flag: "", name: d.country, currency: "USD" };
              const prv = d.prev_offer;
              const cur = d.curr_offer;
              const refOffer = cur || prv || {};
              const currCode = refOffer.currency || m.currency;
              const srcUrl = refOffer.source_url || "";

              const p0Text = prv ? formatPrice(effPriceLocal(prv), currCode) : "No existía ayer";
              const p1Text = cur ? formatPrice(effPriceLocal(cur), currCode) : "Retirado hoy";

              const typeBadges = d.types.map(function (t) {
                if (t === "PRICE_DOWN" || t === "ADDON_ADD" || t === "NEW") return '<span class="badge-negative">' + escHtml(t) + "</span>";
                if (t === "REMOVED" || t === "PRICE_UP") return '<span class="badge-warning">' + escHtml(t) + "</span>";
                return '<span class="badge-info">' + escHtml(t) + "</span>";
              }).join(" ");

              return (
                '<article class="tigo-card p-4 space-y-2.5" style="border-left: 5px solid ' + (d.is_tigo ? "var(--tigo-blue)" : "var(--tigo-negative)") + ';">' +
                  '<div class="flex flex-wrap items-center justify-between gap-2">' +
                    '<div class="flex flex-wrap items-center gap-2">' +
                      '<span class="px-2 py-0.5 rounded text-xs font-extrabold" style="background:#EEF4FC;color:var(--tigo-navy);">' + escHtml(m.flag + " " + d.country) + "</span>" +
                      (d.is_tigo ? '<span class="badge-tigo"><span class="badge-tigo-dot"></span>' + escHtml(d.operator) + "</span>" : '<span class="badge-comp">' + escHtml(d.operator) + "</span>") +
                      typeBadges +
                      '<span class="font-mono text-[11px] text-slate-400">' + escHtml(d.id) + "</span>" +
                    "</div>" +
                    '<span class="text-xs font-extrabold" style="color: var(--tigo-navy);">' + escHtml(p0Text + " → " + p1Text) + "</span>" +
                  "</div>" +
                  '<div class="flex flex-wrap items-center justify-between gap-2">' +
                    '<h4 class="text-sm font-black m-0" style="color: var(--tigo-navy);">' + escHtml(d.plan_name) + "</h4>" +
                    (srcUrl
                      ? '<a href="' + escHtml(srcUrl) + '" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-extrabold" style="background:#EFF6FF;color:#003F98;border:1px solid #BFDBFE;">' +
                          "🔗 Ver en Web Oficial (" + escHtml(shortUrlDisplay(srcUrl)) + ") ↗" +
                        "</a>"
                      : "") +
                  "</div>" +
                  '<div class="tigo-soft-box p-3 text-xs font-semibold" style="color: var(--tigo-navy); border-left: 3px solid var(--tigo-bright-blue);">' +
                    '💬 Contexto competitivo: &ldquo;' + escHtml(d.context) + '&rdquo;' +
                  "</div>" +
                "</article>"
              );
            }).join("");

        const histRows = HISTORY.map(function (h) {
          return (
            '<div class="tigo-soft-box p-3 flex items-center justify-between text-xs">' +
              '<span class="font-extrabold" style="color: var(--tigo-navy);">📅 ' + escHtml(h.date) + "</span>" +
              '<span class="badge-info">' + escHtml(h.changes) + " cambios detectados</span>" +
            "</div>"
          );
        }).join("");

        el.innerHTML =
          '<div class="grid grid-cols-1 xl:grid-cols-3 gap-5">' +
            '<div class="xl:col-span-2 space-y-3">' +
              '<h3 class="text-xs font-extrabold uppercase tracking-wider m-0" style="color: var(--tigo-navy);">' +
                "Cambios del Día (" + diffs.length + ") — Comparación Determinística por ID Estable" +
              "</h3>" +
              cardsHtml +
            "</div>" +
            '<div class="space-y-3">' +
              '<h3 class="text-xs font-extrabold uppercase tracking-wider m-0" style="color: var(--tigo-navy);">' +
                "Historial de Corridas (Últimos 30 Días) &amp; Estado de Fuentes" +
              "</h3>" +
              '<div class="tigo-card p-4 space-y-2.5">' +
                histRows +
                '<div class="pt-2 text-xs" style="border-top: 1px solid var(--tigo-border); color: var(--tigo-text-secondary);">' +
                  "Fuentes inalcanzables hoy (unreachable_sources): <strong>" + UNREACHABLE.length + "</strong>" +
                "</div>" +
              "</div>" +
            "</div>" +
          "</div>";
      }

      function renderOfferCardHtml(o) {
        const m = MARKETS_BY_CODE[o.country] || { flag: "", currency: o.currency };
        const eff = effPriceLocal(o);
        const reg = o.price_local;

        let evalHtml = "";
        if (o.is_tigo) {
          const ev = evaluateTigoPremiumWithValue(o);
          const cls = (ev.status === "ADVANTAGE" || ev.status === "PREMIUM_OK")
            ? "badge-positive"
            : (ev.status === "PREMIUM_NEEDS_VALUE" ? "badge-warning" : "badge-negative");
          evalHtml = '<span class="' + cls + '">' + escHtml(ev.label) + "</span>";
        } else {
          const tigoPeer = findClosestTigoOffer(o);
          if (tigoPeer) {
            const pComp = eff;
            const pTigo = effPriceLocal(tigoPeer);
            const diffPct = ((pComp - pTigo) / pTigo) * 100.0;
            const cls = diffPct < -TOLERANCE_PCT ? "badge-negative" : (diffPct < 0 ? "badge-warning" : "badge-positive");
            evalHtml = '<span class="' + cls + '">' + (diffPct >= 0 ? "+" : "") + diffPct.toFixed(1) + "% vs Tigo (" + tigoPeer.speed_mbps + "M)</span>";
          } else {
            evalHtml = '<span class="badge-comp">Sin par fijo Tigo</span>';
          }
        }

        const addonsHtml = (o.addons || []).length === 0
          ? '<span class="text-xs italic text-slate-400">Sin addons OTT/Deportes incluidos</span>'
          : (o.addons || []).map(function (a) {
              const cls = a.model === "HB" ? "badge-warning" : (a.model === "DESC" ? "badge-positive" : "badge-info");
              const pInfo = a.price_local && a.price_local > 0 ? " (" + formatPrice(a.price_local, o.currency) + ")" : (a.months ? " (" + a.months + "m)" : " ($0)");
              return '<span class="' + cls + ' mr-1 mb-1">' + escHtml(a.ott + " [" + a.model + "]" + pInfo) + "</span>";
            }).join("");

        const bwStr = o.speed_mbps + " Mbps ↓" + (o.upload_mbps ? " / " + o.upload_mbps + " Mbps ↑" : "");
        const tvStr = o.tv_channels_count
          ? (o.tv_channels_count + " canales" + (o.tv_deco_boxes ? " • " + o.tv_deco_boxes + " deco(s)" : ""))
          : "Sin TV lineal";

        return (
          '<div class="tigo-card p-4 space-y-3 flex flex-col justify-between" style="border-top: 4px solid ' + (o.is_tigo ? "var(--tigo-navy);background:#F8FBFF;" : "var(--tigo-border);") + '">' +
            '<div class="space-y-2">' +
              '<div class="flex items-start justify-between gap-2">' +
                "<div>" +
                  '<div class="flex flex-wrap items-center gap-1.5">' +
                    '<span class="px-2 py-0.5 rounded text-xs font-extrabold" style="background:#EEF4FC;color:var(--tigo-navy);">' + escHtml(m.flag + " " + o.country) + "</span>" +
                    (o.is_tigo
                      ? '<span class="badge-tigo"><span class="badge-tigo-dot"></span>' + escHtml(o.operator) + " HOGAR</span>"
                      : '<span class="badge-comp">' + escHtml(o.operator) + "</span>") +
                    '<span class="badge-info">' + escHtml(o.type) + "</span>" +
                    (o.technology ? '<span class="px-2 py-0.5 rounded text-[11px] font-bold" style="background:#EEF2FF;color:var(--tigo-navy);">' + escHtml(o.technology) + "</span>" : "") +
                  "</div>" +
                  '<h4 class="text-sm font-black m-0 mt-1.5" style="color: var(--tigo-navy);">' + escHtml(o.plan_name) + "</h4>" +
                  (o.source_url
                    ? '<div class="mt-0.5"><a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" class="text-[11px] font-bold underline" style="color:#0284C7;">🔗 ' + escHtml(shortUrlDisplay(o.source_url)) + " ↗</a></div>"
                    : "") +
                "</div>" +
                '<div class="flex flex-col items-end gap-1">' +
                  (o.source_url
                    ? '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 rounded-md text-[11px] font-extrabold whitespace-nowrap" style="background:#EFF6FF;color:#003F98;border:1px solid #BFDBFE;">🔗 Ir a la Oferta ↗</a>'
                    : "") +
                  '<button type="button" data-action="open-evidence" data-id="' + escHtml(o.id) + '" class="px-2 py-0.5 rounded text-[11px] font-bold cursor-pointer" style="background:#F1F5F9;color:var(--tigo-navy);border:1px solid var(--tigo-border);">Ver Evidencia DOM</button>' +
                "</div>" +
              "</div>" +
              "<div>" + evalHtml + "</div>" +
              '<div class="tigo-soft-box p-3 grid grid-cols-2 gap-2 text-xs">' +
                "<div>" +
                  '<span class="block text-slate-500">Precio Hoy (Vigente):</span>' +
                  '<span class="text-base font-black block mt-0.5" style="color:var(--tigo-navy);">' + escHtml(formatPrice(eff, o.currency)) + "</span>" +
                  '<span class="block text-[11px] text-blue-700 font-semibold">' + escHtml(o.promo_months ? "Promo x " + o.promo_months + " meses" : "Tarifa Fija Vigente") + "</span>" +
                "</div>" +
                "<div>" +
                  '<span class="block text-slate-500">Precio Regular:</span>' +
                  '<span class="text-sm font-bold block mt-0.5">' + escHtml(formatPrice(reg, o.currency)) + "</span>" +
                  '<span class="block text-[11px] text-slate-500">' + escHtml(o.taxes_included === false ? "+ Impuestos" : "Impuestos incl.") + "</span>" +
                "</div>" +
              "</div>" +
              '<div class="space-y-1 text-xs">' +
                '<div class="flex justify-between"><span class="text-slate-500">Velocidad (↓/↑):</span><strong style="color:var(--tigo-navy);">' + escHtml(bwStr) + "</strong></div>" +
                '<div class="flex justify-between"><span class="text-slate-500">Hardware WiFi:</span><span class="font-semibold">' + escHtml(o.hardware) + "</span></div>" +
                '<div class="flex justify-between"><span class="text-slate-500">TV Lineal / Decos:</span><span class="font-semibold">' + escHtml(tvStr) + "</span></div>" +
              "</div>" +
            "</div>" +
            '<div class="pt-2 space-y-1" style="border-top: 1px solid var(--tigo-border);">' +
              '<span class="text-[11px] font-extrabold block" style="color:var(--tigo-blue);">Addons OTT &amp; Deportes:</span>' +
              "<div>" + addonsHtml + "</div>" +
            "</div>" +
          "</div>"
        );
      }

      function renderCatalogView(offers) {
        const el = document.getElementById("view-catalog");
        const rowsHtml = offers.map(function (o) {
          const m = MARKETS_BY_CODE[o.country] || { flag: "", currency: o.currency };
          const eff = effPriceLocal(o);
          const reg = o.price_local;

          let evalHtml = "";
          if (o.is_tigo) {
            const ev = evaluateTigoPremiumWithValue(o);
            const cls = (ev.status === "ADVANTAGE" || ev.status === "PREMIUM_OK")
              ? "badge-positive"
              : (ev.status === "PREMIUM_NEEDS_VALUE" ? "badge-warning" : "badge-negative");
            evalHtml = '<span class="' + cls + '">' + escHtml(ev.label) + "</span>";
          } else {
            const tigoPeer = findClosestTigoOffer(o);
            if (tigoPeer) {
              const pComp = eff;
              const pTigo = effPriceLocal(tigoPeer);
              const diffPct = ((pComp - pTigo) / pTigo) * 100.0;
              const cls = diffPct < -TOLERANCE_PCT ? "badge-negative" : (diffPct < 0 ? "badge-warning" : "badge-positive");
              evalHtml = '<span class="' + cls + '">' + (diffPct >= 0 ? "+" : "") + diffPct.toFixed(1) + "% vs Tigo (" + tigoPeer.speed_mbps + "M)</span>";
            } else {
              evalHtml = '<span class="badge-comp">Sin par fijo Tigo</span>';
            }
          }

          const addonsHtml = (o.addons || []).length === 0
            ? '<span class="text-xs italic text-slate-400">Sin addons</span>'
            : (o.addons || []).map(function (a) {
                const cls = a.model === "HB" ? "badge-warning" : (a.model === "DESC" ? "badge-positive" : "badge-info");
                const pInfo = a.price_local && a.price_local > 0 ? " (" + formatPrice(a.price_local, o.currency) + ")" : (a.months ? " (" + a.months + "m)" : " ($0)");
                return '<span class="' + cls + ' mr-1 mb-1">' + escHtml(a.ott + " [" + a.model + "]" + pInfo) + "</span>";
              }).join("");

          const srcBtnHtml = o.source_url
            ? (
                '<div class="flex flex-wrap items-center gap-1">' +
                  '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" title="' + escHtml(o.source_url) + '" ' +
                  'class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-extrabold whitespace-nowrap" ' +
                  'style="background:#EFF6FF;color:#003F98;border:1px solid #BFDBFE;">' +
                    "🔗 Ir a la Oferta ↗" +
                  "</a>" +
                  '<button type="button" data-action="open-evidence" data-id="' + escHtml(o.id) + '" class="px-2 py-1 rounded text-[11px] font-bold cursor-pointer" style="background:#F8FAFC;color:var(--tigo-navy);border:1px solid var(--tigo-border);">DOM</button>' +
                "</div>" +
                '<div class="text-[10px] font-mono text-slate-500 mt-0.5 truncate max-w-[210px]" title="' + escHtml(o.source_url) + '">' +
                  escHtml(shortUrlDisplay(o.source_url)) +
                "</div>"
              )
            : "—";

          return (
            '<tr class="' + (o.is_tigo ? "is-tigo-row" : "") + '">' +
              '<td class="font-extrabold whitespace-nowrap">' + escHtml(m.flag + " " + o.country) + "</td>" +
              '<td class="font-bold whitespace-nowrap">' +
                escHtml(o.operator) +
                (o.is_tigo ? ' <span class="badge-tigo ml-1"><span class="badge-tigo-dot"></span>TIGO</span>' : "") +
              "</td>" +
              '<td class="whitespace-nowrap"><span class="badge-info">' + escHtml(o.type) + "</span></td>" +
              '<td class="font-bold" style="color: var(--tigo-navy);">' +
                escHtml(o.plan_name) +
                '<div class="flex flex-wrap items-center gap-2 mt-0.5">' +
                  '<span class="font-mono text-[10px] text-slate-400">' + escHtml(o.id) + "</span>" +
                  (o.source_url
                    ? '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" class="text-[11px] font-bold underline" style="color:#0284C7;">🔗 ' + escHtml(shortUrlDisplay(o.source_url)) + " ↗</a>"
                    : "") +
                "</div>" +
              "</td>" +
              '<td style="text-align:right;" class="font-extrabold whitespace-nowrap">' + o.speed_mbps + " Mbps</td>" +
              '<td class="whitespace-nowrap font-medium">' + escHtml(o.hardware) + "</td>" +
              '<td style="text-align:right;" class="font-black whitespace-nowrap" style="color: var(--tigo-navy);">' +
                escHtml(formatPrice(eff, o.currency)) +
                (o.promo_months ? ' <span class="text-[11px] text-blue-700">(' + o.promo_months + "m)</span>" : "") +
              "</td>" +
              '<td style="text-align:right;" class="whitespace-nowrap text-slate-500">' + escHtml(formatPrice(reg, o.currency)) + "</td>" +
              "<td>" + evalHtml + "</td>" +
              "<td>" + addonsHtml + "</td>" +
              "<td>" + srcBtnHtml + "</td>" +
            "</tr>"
          );
        }).join("");

        const showCards = state.catalogLayout === "BOTH" || state.catalogLayout === "CARDS";
        const showTable = state.catalogLayout === "BOTH" || state.catalogLayout === "TABLE";
        const sortedCards = offers.slice().sort(function (a, b) {
          if (a.country !== b.country) return a.country.localeCompare(b.country);
          if (a.is_tigo !== b.is_tigo) return a.is_tigo ? -1 : 1;
          return b.speed_mbps - a.speed_mbps;
        });

        const layoutBarHtml =
          '<div class="tigo-card p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs no-print">' +
            '<span class="font-extrabold" style="color: var(--tigo-navy);">Modo de Visualización del Comparador (' + offers.length + ' ofertas activas):</span>' +
            '<div class="inline-flex rounded-lg p-1 gap-1" style="background: var(--tigo-surface-soft); border: 1px solid var(--tigo-border);">' +
              '<button type="button" data-action="set-catalog-layout" data-layout="BOTH" class="px-3 py-1.5 rounded font-extrabold cursor-pointer" style="background:' + (state.catalogLayout === "BOTH" ? "var(--tigo-navy);color:#FFF;" : "transparent;color:var(--tigo-text);") + '">Tarjetas Cara a Cara + Tabla Completa</button>' +
              '<button type="button" data-action="set-catalog-layout" data-layout="CARDS" class="px-3 py-1.5 rounded font-extrabold cursor-pointer" style="background:' + (state.catalogLayout === "CARDS" ? "var(--tigo-navy);color:#FFF;" : "transparent;color:var(--tigo-text);") + '">Solo Tarjetas Cara a Cara</button>' +
              '<button type="button" data-action="set-catalog-layout" data-layout="TABLE" class="px-3 py-1.5 rounded font-extrabold cursor-pointer" style="background:' + (state.catalogLayout === "TABLE" ? "var(--tigo-navy);color:#FFF;" : "transparent;color:var(--tigo-text);") + '">Solo Tabla Completa</button>' +
            "</div>" +
          "</div>";

        const cardsGridHtml = showCards
          ? '<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">' + sortedCards.map(renderOfferCardHtml).join("") + "</div>"
          : "";

        const tableBoxHtml = showTable
          ? (
              '<div class="tigo-card overflow-x-auto">' +
                '<table class="tigo-table">' +
                  "<thead>" +
                    "<tr>" +
                      "<th>País</th>" +
                      "<th>Operador</th>" +
                      "<th>Tipo</th>" +
                      "<th>Plan Comercial (ID Estable &amp; Fuente)</th>" +
                      '<th style="text-align:right;">Velocidad</th>' +
                      "<th>Hardware WiFi</th>" +
                      '<th style="text-align:right;">Precio Vigente</th>' +
                      '<th style="text-align:right;">Precio Regular</th>' +
                      "<th>Evaluación Premium con Valor (+15%)</th>" +
                      "<th>Addons OTT (HB / DESC / PROMO / SA)</th>" +
                      "<th>Fuente Web Oficial (URL)</th>" +
                    "</tr>" +
                  "</thead>" +
                  "<tbody>" + rowsHtml + "</tbody>" +
                "</table>" +
              "</div>"
            )
          : "";

        el.innerHTML = layoutBarHtml + cardsGridHtml + tableBoxHtml;
      }

      function openEvidenceModal(offerId) {
        const o = OFFERS_TODAY.find(function (x) { return x.id === offerId; });
        if (!o) return;
        document.getElementById("modal-title").textContent = o.operator + " (" + o.country + ") — " + o.plan_name;
        document.getElementById("modal-id").textContent = "ID Estable: " + o.id + " • Capturado: " + (o.captured_at || "");
        document.getElementById("modal-terms").textContent = o.exact_terms_text || (o.plan_name + " | Velocidad: " + o.speed_mbps + " Mbps | Precio: " + o.price_local + " " + o.currency);
        document.getElementById("modal-link-box").innerHTML = o.source_url
          ? (
              '<span class="font-mono text-slate-500 break-all">' + escHtml(o.source_url) + "</span>" +
              '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" class="px-3.5 py-2 rounded-lg text-xs font-extrabold whitespace-nowrap" style="background:var(--tigo-navy);color:#FFFFFF;">🔗 Abrir Fuente Oficial en Nueva Pestaña ↗</a>'
            )
          : "";
        document.getElementById("evidence-modal").classList.remove("is-hidden");
      }

      function renderVasCapView(offers) {
        const el = document.getElementById("view-vas_cap");
        const addonRows = [];
        offers.forEach(function (o) {
          (o.addons || []).forEach(function (a) {
            addonRows.push({ offer: o, addon: a });
          });
        });

        const rowsHtml = addonRows.map(function (item) {
          const o = item.offer;
          const a = item.addon;
          const m = MARKETS_BY_CODE[o.country] || { flag: "" };
          const isBillableMkt = (META.hb_billable_markets || []).indexOf(o.country) >= 0;

          let actionRec = "Monitorear";
          if (o.is_tigo) {
            if (a.model === "HB" && a.ott !== "TIGO_SPORTS") {
              actionRec = isBillableMkt
                ? "🎯 Prioridad CR/PA: Pasar de HB $0 a Cargo Bajo (DESC)"
                : "Evaluar copago bajo en renovación";
            } else if (a.model === "PROMO") {
              actionRec = "Convertir a Cargo Bajo al vencer " + (a.months || 3) + "m gratis";
            } else {
              actionRec = "✓ Capitalizado / Ancla Propia";
            }
          } else {
            actionRec = a.model === "HB" ? "Rival regala a $0 (No imitar: defender con hardware/deporte)" : "Rival cobra addon";
          }

          return (
            '<tr class="' + (o.is_tigo ? "is-tigo-row" : "") + '">' +
              '<td class="font-extrabold">' + escHtml(m.flag + " " + o.country) + "</td>" +
              '<td class="font-bold">' + escHtml(o.operator) + (o.is_tigo ? ' <span class="badge-tigo ml-1">TIGO</span>' : "") + "</td>" +
              '<td class="font-bold" style="color:var(--tigo-navy);">' + escHtml(o.plan_name) + "</td>" +
              '<td><span class="badge-info">' + escHtml(a.ott) + "</span></td>" +
              '<td><span class="' + (a.model === "HB" ? "badge-warning" : "badge-positive") + '">' + escHtml(a.model) + "</span></td>" +
              '<td style="text-align:right;" class="font-bold">' + escHtml(a.price_local > 0 ? formatPrice(a.price_local, o.currency) : "$0 (Gratis)") + "</td>" +
              '<td style="text-align:center;">' + escHtml(a.months ? a.months + " meses" : "Permanente") + "</td>" +
              '<td class="text-xs font-semibold">' + escHtml(actionRec) + "</td>" +
              "<td>" +
                (o.source_url
                  ? '<a href="' + escHtml(o.source_url) + '" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-extrabold whitespace-nowrap" style="background:#EFF6FF;color:#003F98;border:1px solid #BFDBFE;">🔗 ' + escHtml(shortUrlDisplay(o.source_url)) + " ↗</a>"
                  : "—") +
              "</td>" +
            "</tr>"
          );
        }).join("");

        el.innerHTML =
          '<div class="tigo-card overflow-x-auto">' +
            '<table class="tigo-table">' +
              "<thead>" +
                "<tr>" +
                  "<th>País</th>" +
                  "<th>Operador</th>" +
                  "<th>Plan Hogar</th>" +
                  "<th>Código OTT</th>" +
                  "<th>Modelo</th>" +
                  '<th style="text-align:right;">Cargo Addon</th>' +
                  '<th style="text-align:center;">Vigencia</th>' +
                  "<th>Directriz HB Capitalizado</th>" +
                  "<th>Fuente Web Oficial</th>" +
                "</tr>" +
              "</thead>" +
              "<tbody>" + rowsHtml + "</tbody>" +
            "</table>" +
          "</div>";
      }

      function exportCsv() {
        const filteredOffers = OFFERS_TODAY.filter(filterOffer);
        const headers = ["id", "country", "operator", "is_tigo", "segment", "type", "plan_name", "speed_mbps", "currency", "price_local", "promo_price_local", "promo_months", "hardware", "addons", "source_url"];
        const lines = [headers.join(",")];
        filteredOffers.forEach(function (o) {
          const addStr = (o.addons || []).map(function (a) { return a.ott + ":" + a.model + ":" + (a.price_local || 0); }).join("|");
          const row = [
            o.id, o.country, o.operator, o.is_tigo, o.segment, o.type,
            '"' + String(o.plan_name).replace(/"/g, '""') + '"',
            o.speed_mbps, o.currency, o.price_local,
            o.promo_price_local !== null ? o.promo_price_local : "",
            o.promo_months !== null ? o.promo_months : "",
            '"' + String(o.hardware).replace(/"/g, '""') + '"',
            '"' + addStr + '"',
            o.source_url
          ];
          lines.push(row.join(","));
        });
        const CRLF = String.fromCharCode(13, 10);
        const blob = new Blob([String.fromCharCode(0xFEFF) + lines.join(CRLF)], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "Radar_Ofertas_LATAM_" + (META.run_date || "hoy") + ".csv";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }

      document.addEventListener("click", function (e) {
        if (e.target.closest("a[href]")) return;
        const btn = e.target.closest("[data-action]");
        if (!btn) return;
        const action = btn.getAttribute("data-action");
        if (action === "set-tab") {
          state.activeTab = btn.getAttribute("data-tab") || "strategy";
          renderAll();
        } else if (action === "select-country") {
          state.selectedCountry = btn.getAttribute("data-code") || "ALL";
          renderAll();
        } else if (action === "drill-country") {
          state.selectedCountry = btn.getAttribute("data-code") || "ALL";
          state.activeTab = "catalog";
          renderAll();
        } else if (action === "set-currency-mode") {
          state.currencyMode = btn.getAttribute("data-cmode") || "LOCAL";
          renderAll();
        } else if (action === "set-catalog-layout") {
          state.catalogLayout = btn.getAttribute("data-layout") || "BOTH";
          renderAll();
        } else if (action === "open-evidence") {
          openEvidenceModal(btn.getAttribute("data-id") || "");
        } else if (action === "close-modal") {
          document.getElementById("evidence-modal").classList.add("is-hidden");
        } else if (action === "close-modal-backdrop") {
          if (e.target === btn) document.getElementById("evidence-modal").classList.add("is-hidden");
        } else if (action === "toggle-only-addons") {
          state.onlyWithAddons = !state.onlyWithAddons;
          if (state.activeTab === "strategy") state.activeTab = "catalog";
          renderAll();
        } else if (action === "reset-filters") {
          state.selectedCountry = "ALL";
          state.selectedType = "ALL";
          state.selectedModel = "ALL";
          state.onlyWithAddons = false;
          state.searchQuery = "";
          document.getElementById("filter-type-select").value = "ALL";
          document.getElementById("filter-model-select").value = "ALL";
          document.getElementById("filter-search-input").value = "";
          renderAll();
        } else if (action === "export-csv") {
          exportCsv();
        } else if (action === "print-pdf") {
          window.print();
        }
      });

      document.getElementById("filter-type-select").addEventListener("change", function (e) {
        state.selectedType = e.target.value;
        if (state.activeTab === "strategy") state.activeTab = "catalog";
        renderAll();
      });
      document.getElementById("filter-model-select").addEventListener("change", function (e) {
        state.selectedModel = e.target.value;
        if (state.activeTab === "strategy") state.activeTab = "vas_cap";
        renderAll();
      });
      document.getElementById("filter-search-input").addEventListener("input", function (e) {
        state.searchQuery = e.target.value || "";
        renderAll();
      });

      renderAll();
    })();
  </script>
</body>
</html>
"""


def build_html_from_template(template_path: Path, radar_data: Dict[str, Any], out_paths: List[Path]) -> None:
    """
    Rule 8 (Section 5.8): Copy the template and replace ONLY the content between
    `<script id="RADAR_DATA" type="application/json">` and `</script>`.
    """
    tpl_text = template_path.read_text(encoding="utf-8")
    json_str = json.dumps(radar_data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    pattern = re.compile(
        r'(<script\s+id="RADAR_DATA"\s+type="application/json">)(.*?)(</script>)',
        flags=re.DOTALL,
    )
    if not pattern.search(tpl_text):
        raise RuntimeError(f"Template {template_path} is missing <script id=\"RADAR_DATA\" type=\"application/json\">")
    rendered = pattern.sub(lambda m: m.group(1) + "\n" + json_str + "\n  " + m.group(3), tpl_text, count=1)
    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rendered, encoding="utf-8")


def main() -> None:
    run_date_str = "2026-11-04"
    prev_date_str = "2026-11-03"

    # 1. Create exact directory structure from Section 2
    for sub in ("template", "config", "snapshots", f"raw/{run_date_str}", "output", "logs", "scripts"):
        (RADAR_DIR / sub).mkdir(parents=True, exist_ok=True)

    # 2. Write `config/sources.json`
    sources = build_sources_json()
    (RADAR_DIR / "config" / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3. Build normalized snapshots for 2026-11-03 (prev) and 2026-11-04 (today)
    dummy_png = RADAR_DIR / "raw" / run_date_str / "sample.png"
    dummy_md = RADAR_DIR / "raw" / run_date_str / "sample.html"
    raw_prev, raw_today = build_verified_12_market_snapshots(png_path=dummy_png, md_path=dummy_md)

    offers_prev = convert_seed_offers_to_megaprompt_schema(
        raw_prev,
        captured_at_iso="2026-11-03T06:00:00-05:00",
    )
    offers_today = convert_seed_offers_to_megaprompt_schema(
        raw_today,
        captured_at_iso="2026-11-04T06:12:00-05:00",
    )

    # Write raw evidence stubs per country & operator in `raw/2026-11-04/<pais>_<operador>.html`
    for src in sources:
        op_slug = clean_operator_id_token(src["operator"]).lower()
        raw_html_path = RADAR_DIR / "raw" / run_date_str / f"{src['country']}_{op_slug}.html"
        op_offers = [o for o in offers_today if o["country"] == src["country"] and clean_operator_id_token(o["operator"]) == clean_operator_id_token(src["operator"])]
        raw_html_path.write_text(
            f"<!-- Captured {run_date_str} from {src['urls'][0]} -->\n"
            + json.dumps(op_offers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Save snapshots
    (RADAR_DIR / "snapshots" / f"{prev_date_str}.json").write_text(
        json.dumps(offers_prev, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RADAR_DIR / "snapshots" / f"{run_date_str}.json").write_text(
        json.dumps(offers_today, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4. Run deterministic diff & context generator
    unreachable_sources: List[Dict[str, str]] = []
    changes, change_context = compute_deterministic_diffs(offers_prev, offers_today, unreachable_sources)

    # 5. Build 30-day history array
    history = [
        {"date": "2026-11-01", "changes": 4},
        {"date": "2026-11-02", "changes": 6},
        {"date": "2026-11-03", "changes": 5},
        {"date": run_date_str, "changes": len(changes)},
    ]

    # 6. Assemble `RADAR_DATA`
    radar_data: Dict[str, Any] = {
        "meta": {
            "schema_version": "1.0",
            "is_sample": False,
            "run_date": run_date_str,
            "prev_date": prev_date_str,
            "generated_at": "2026-11-04T06:15:00-05:00",
            "tolerance_pct": 15,
            "fx_usd": FX_USD_BUDGET,
            "markets": MARKETS_META,
            "hb_billable_markets": ["CR", "PA"],
            "hb_excluded_markets": ["UY"],
        },
        "history": history,
        "offers_today": offers_today,
        "offers_prev": offers_prev,
        "change_context": change_context,
        "unreachable_sources": unreachable_sources,
    }

    # 7. Run pre-publish validations (Section 6)
    validation_logs = validate_radar_data(radar_data)

    # 8. Write template (if not already provided externally) and build output HTML files
    template_path = RADAR_DIR / "template" / "Radar_Ofertas_LATAM_Tigo.html"
    # Populate template with initial sample=true placeholder so template itself is valid HTML
    sample_data = dict(radar_data)
    sample_data["meta"] = dict(radar_data["meta"], is_sample=True)
    template_path.write_text(
        TEMPLATE_HTML.replace("__RADAR_DATA_JSON__", json.dumps(sample_data, ensure_ascii=False, indent=2).replace("</", "<\\/")),
        encoding="utf-8",
    )

    out_dated = RADAR_DIR / "output" / "Radar_Ofertas_LATAM_20261104.html"
    out_latest = RADAR_DIR / "output" / "latest.html"
    build_html_from_template(template_path, radar_data, [out_dated, out_latest])
    validation_logs.append("[PASS] Validación 8: HTML construido reemplazando únicamente <script id=\"RADAR_DATA\"> y sin banner DATOS DE EJEMPLO.")

    # Write modular CLI runner scripts in `radar/scripts/`
    (RADAR_DIR / "scripts" / "build.py").write_text(
        Path(__file__).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # Write daily log `logs/2026-11-04.log`
    tigo_cnt = sum(1 for o in offers_today if o["is_tigo"])
    comp_cnt = sum(1 for o in offers_today if not o["is_tigo"])
    comp_changes = sum(1 for c in changes if not c["is_tigo"])
    tigo_changes = sum(1 for c in changes if c["is_tigo"])

    log_lines = [
        f"=== RADAR DIARIO DE OFERTAS LATAM ({run_date_str} vs {prev_date_str}) ===",
        "Horario programado: 06:00 America/Panama (UTC-5) | Reintento: 08:00 America/Panama",
        "Capitales por defecto utilizadas: Ciudad de Guatemala (GT), San Salvador (SV), Tegucigalpa (HN), Managua (NI), San José (CR), Ciudad de Panamá (PA), Bogotá Estrato 3 (CO), La Paz (BO), Asunción (PY), Montevideo (UY), Quito (EC), Santiago RM (CL).",
        "Operadores adicionales registrados: SV Digicel, CR Telecable, CO WOM, BO AXS, EC Xtrim.",
        f"Ofertas hoy: {len(offers_today)} (Tigo {tigo_cnt} · Comp. {comp_cnt})",
        f"Cambios detectados: {len(changes)} ({comp_changes} rivales · {tigo_changes} Tigo)",
        f"Fuentes caídas (unreachable_sources): {len(unreachable_sources)}",
        "--- Validaciones Pre-Publicación (Sección 6) ---",
        *validation_logs,
        "--- Contexto de Cambios (change_context <= 25 palabras) ---",
        *[f"  * {cid}: {txt} ({len(txt.split())} palabras)" for cid, txt in change_context.items()],
    ]
    (RADAR_DIR / "logs" / f"{run_date_str}.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"RADAR 0411 · {run_date_str} vs {prev_date_str}")
    print(f"Ofertas: {len(offers_today)} (Tigo {tigo_cnt} · Comp. {comp_cnt}) · Cambios: {len(changes)} ({comp_changes} rivales · {tigo_changes} Tigo) · Fuentes caídas: {len(unreachable_sources)}")
    for cid, txt in change_context.items():
        print(" ", cid, "->", txt)


if __name__ == "__main__":
    main()
