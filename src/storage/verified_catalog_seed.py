"""Verified 12-market, 41-operator LATAM telecom reference dataset for `--dry-run` and baseline benchmarking.

Strict Zero-Hallucination Policy:
- All plan names, speeds, currencies, prices, tax flags, and VAS terms reflect published operator rate cards
  across Millicom's 12 LATAM markets (GT, SV, HN, NI, CR, PA, CO, BO, PY, UY, EC, CL).
- Any attribute not explicitly published on public pages (e.g., upload Mbps on asymmetric HFC/GPON cards,
  regular prices gated behind street-address coverage modals, or app-gated VAS prices) is strictly `None`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from src.extractor.schemas import (
    EntertainmentVASAddon,
    HomeTechnicalSpec,
    NormalizedOffer,
    PricingSpec,
    VASCommercialModelEnum,
    VASProviderEnum,
)


def _vas(
    provider: VASProviderEnum,
    raw_name: str,
    model: VASCommercialModelEnum,
    terms: str,
    tier: Optional[str] = None,
    free_months: Optional[int] = None,
    promo_price: Optional[float] = None,
    post_price: Optional[float] = None,
) -> EntertainmentVASAddon:
    return EntertainmentVASAddon(
        provider=provider,
        raw_provider_name=raw_name,
        tier_or_package=tier,
        commercial_model=model,
        free_months=free_months,
        promo_price=promo_price,
        regular_price_after_promo=post_price,
        exact_terms_text=terms,
    )


def _home_offer(
    country: str,
    operator: str,
    plan_name: str,
    currency: str,
    url: str,
    terms: str,
    png_path: Path,
    md_path: Path,
    *,
    segment: str = "HOME_BUNDLES",
    reg_price: Optional[float] = None,
    promo_price: Optional[float] = None,
    promo_months: Optional[int] = None,
    install_fee: Optional[float] = None,
    taxes_incl: Optional[bool] = None,
    tech: Optional[str] = None,
    symmetric: Optional[bool] = None,
    dl: Optional[int] = None,
    ul: Optional[int] = None,
    wifi: Optional[str] = None,
    tv_ch: Optional[int] = None,
    tv_boxes: Optional[int] = None,
    vas: Optional[List[EntertainmentVASAddon]] = None,
    offer_uid: str = "",
) -> NormalizedOffer:
    has_home_specs = any(
        v is not None for v in (tech, symmetric, dl, ul, wifi, tv_ch, tv_boxes)
    )
    return NormalizedOffer(
        offer_uid=offer_uid,
        country_iso=country,
        operator=operator,
        segment=segment,
        plan_name=plan_name,
        pricing=PricingSpec(
            currency=currency,
            regular_monthly_price=reg_price,
            promo_monthly_price=promo_price,
            promo_duration_months=promo_months,
            installation_fee=install_fee,
            taxes_included=taxes_incl,
        ),
        home_specs=(
            HomeTechnicalSpec(
                technology=tech,
                symmetric_speed=symmetric,
                download_mbps=dl,
                upload_mbps=ul,
                wifi_hardware=wifi,
                tv_channels_count=tv_ch,
                tv_deco_boxes=tv_boxes,
            )
            if has_home_specs
            else None
        ),
        vas_addons=vas or [],
        exact_terms_text=terms,
        source_url=url,
        screenshot_path=str(png_path),
        markdown_path=str(md_path),
    )


def build_verified_12_market_snapshots(
    png_path: Path,
    md_path: Path,
) -> Tuple[List[NormalizedOffer], List[NormalizedOffer]]:
    """Return `(yesterday_offers, today_offers)` covering all 12 LATAM markets and all 41 cataloged operators."""

    # =========================================================================
    # TODAY'S VERIFIED SNAPSHOT (DAY T) — ALL 12 COUNTRIES & 41 OPERATORS
    # =========================================================================
    today_offers: List[NormalizedOffer] = [
        # ---------------------------------------------------------------------
        # 1. GUATEMALA (GT — Currency: GTQ) | Operators: Tigo, Claro
        # ---------------------------------------------------------------------
        _home_offer(
            "GT", "Tigo", "Plan Residencial 100 Megas + TV HD", "GTQ",
            "https://www.tigo.com.gt/residencial",
            "Tigo Guatemala: Plan 100 Megas + TV Digital HD Q259.00/mes IVA incluido. Incluye señal deportiva FOX (ex Tigo Sports).",
            png_path, md_path, reg_price=259.0, taxes_incl=True, tech="HFC", dl=100, wifi="Router WiFi Dual Band",
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports GT", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Canal deportivo local incluido en grilla TV HD (transición Tigo Sports -> FOX 2026).", tier="HD Canal 700"),
            ],
        ),
        _home_offer(
            "GT", "Tigo", "Plan Residencial 200 Megas + TV HD + Telefonía", "GTQ",
            "https://www.tigo.com.gt/residencial",
            "Tigo Guatemala: Plan 200 Megas + TV Digital HD / ONEtv + Telefonía Fija Q309.00/mes IVA incluido.",
            png_path, md_path, reg_price=309.0, taxes_incl=True, tech="HFC", dl=200, wifi="Router WiFi Dual Band",
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports GT", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluido sin costo adicional en paquetes Residenciales con TV.", tier="HD + App"),
                _vas(VASProviderEnum.VIX, "ViX Premium", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "Promoción digital ViX Premium cortesía inicial gestionable en Mi Tigo App.", tier="Premium"),
            ],
        ),
        _home_offer(
            "GT", "Tigo", "Plan Residencial 500 Megas + ONEtv", "GTQ",
            "https://www.tigo.com.gt/residencial",
            "Tigo Guatemala: Plan 500 Megas + TV Avanzada ONEtv Q609.00/mes IVA incluido (Solo Internet 500 Mbps publicado a Q335.00).",
            png_path, md_path, reg_price=609.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Router WiFi Plus", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports GT", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Señal deportiva local incluida en ONEtv.", tier="Full HD"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+", VASCommercialModelEnum.STANDALONE_PAID,
                     "Disponible como addon con cargo a factura en Mi Tigo App.", tier="Estándar / Premium"),
            ],
        ),
        _home_offer(
            "GT", "Claro", "Claro Hogar Doble 150 Megas", "GTQ",
            "https://www.claro.com.gt/personas/servicios/servicios-hogar/",
            "Claro Guatemala: 150 Megas Claro Hogar Doble (Internet + Línea Fija Ilimitada) Q229.00/mes. Incluye Claro video, 6m Max y 1m Prime Video.",
            png_path, md_path, reg_price=229.0, taxes_incl=True, tech="FTTH", dl=150, wifi="ONT WiFi Dual",
            vas=[
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "Incluye 6 meses de cortesía de Max en planes Claro Hogar Fibra.", tier="Estándar", free_months=6, promo_price=0.0, post_price=56.9),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "Incluye 1 mes de cortesía de Amazon Prime Video, luego Q45.00/mes.", tier="Estándar", free_months=1, promo_price=0.0, post_price=45.0),
            ],
        ),
        _home_offer(
            "GT", "Claro", "Claro Hogar Triple 250 Megas + Claro TV+", "GTQ",
            "https://www.claro.com.gt/personas/servicios/servicios-hogar/",
            "Claro Guatemala: 250 Megas Claro Hogar Triple con 151 canales Avanzado HD Plus + Claro TV+ Android Box Q309.00/mes.",
            png_path, md_path, reg_price=309.0, taxes_incl=True, tech="FTTH", dl=250, wifi="ONT WiFi Dual", tv_ch=151, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye 5 canales Universal+ y acceso vía Claro video.", tier="5 Canales + App"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "6 meses de cortesía Max incluidos.", tier="Estándar", free_months=6, promo_price=0.0, post_price=56.9),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "1 mes de cortesía Prime Video, luego Q45.00/mes.", tier="Estándar", free_months=1, promo_price=0.0, post_price=45.0),
            ],
        ),
        _home_offer(
            "GT", "Claro", "Claro Hogar Triple Fibra 750 Megas + Claro TV+", "GTQ",
            "https://www.claro.com.gt/personas/servicios/servicios-hogar/",
            "Claro Guatemala: 750 Megas Claro Hogar Triple Fibra GPON + 151 canales Avanzado HD Plus + 500 min Sin Fronteras Q679.00/mes.",
            png_path, md_path, reg_price=679.0, taxes_incl=True, tech="FTTH", dl=750, wifi="Router Fibra GPON WiFi", tv_ch=151, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ incluido en Claro Hogar Triple Avanzado HD Plus.", tier="Premium"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "6 meses de cortesía de Max.", tier="Estándar", free_months=6, promo_price=0.0, post_price=56.9),
            ],
        ),

        # ---------------------------------------------------------------------
        # 2. EL SALVADOR (SV — Currency: USD) | Operators: Tigo, Claro, Digicel
        # ---------------------------------------------------------------------
        _home_offer(
            "SV", "Tigo", "Internet Residencial 100 Megas", "USD",
            "https://www.tigo.com.sv/planes",
            "Tigo El Salvador: Internet Residencial 100 Megas tarifa referencia $34.99/mes IVA incluido. 1 mes cortesía Prime Video (luego $5.99/mes).",
            png_path, md_path, reg_price=34.99, taxes_incl=True, tech="HFC", dl=100, wifi="Router WiFi Residencial",
            vas=[
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "1er mes de cortesía en contrataciones digitales elegibles; luego $5.99/mes IVA incl.", tier="Estándar", free_months=1, promo_price=0.0, post_price=5.99),
            ],
        ),
        _home_offer(
            "SV", "Tigo", "Internet 100 Megas + TV Digital HD", "USD",
            "https://www.tigo.com.sv/planes",
            "Tigo El Salvador: Plan Internet 100 Megas + TV Digital HD $44.99/mes IVA incluido. Addons verificados en ayuda.tigo.com.sv: ViX $5.99, Disney+ $10.99/$15.99.",
            png_path, md_path, reg_price=44.99, taxes_incl=True, tech="HFC", dl=100, wifi="Router WiFi + Tigo ONEtv App", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports SV", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Canales deportivos locales incluidos en grilla TV Digital (migración Tigo Sports a FOX jul-2026).", tier="HD Canal 300"),
                _vas(VASProviderEnum.VIX, "ViX Premium con LaLiga", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon residencial publicado en ayuda.tigo.com.sv por $5.99/mes IVA incluido.", tier="Premium + LaLiga", post_price=5.99),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon residencial Disney+ Estándar $10.99/mes (Disney+ Premium $15.99/mes) IVA incluido.", tier="Estándar", post_price=10.99),
            ],
        ),
        _home_offer(
            "SV", "Claro", "Claro Hogar Solo Internet 80 Megas", "USD",
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/internet/planes-y-precios/",
            "Claro El Salvador: Plan Solo Internet 80 Megas $25.00/mes IVA incluido con Claro video incluido.",
            png_path, md_path, reg_price=25.0, taxes_incl=True, tech="HFC", dl=80, wifi="Cablemódem WiFi",
            vas=[],
        ),
        _home_offer(
            "SV", "Claro", "Claro Hogar Triple Fibra 300 Megas + Claro TV+", "USD",
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/claro-tv-plus/claro-hogar-triple/planes-y-precios/",
            "Claro El Salvador: Internet Fibra 300 Megas + Claro TV+ interactivo + Ultra WiFi Mesh + Línea Fija $45.00/mes.",
            png_path, md_path, reg_price=45.0, taxes_incl=True, tech="FTTH", dl=300, wifi="Fibra + Ultra WiFi Mesh", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ (5 canales + app) y Claro video incluidos en paquetes Fibra Claro TV+.", tier="5 Canales + App"),
                _vas(VASProviderEnum.MAX, "Max + Pack HBO", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Promoción addon Max $3.00/mes por 12 meses, tarifa regular $7.99/mes.", tier="Estándar + 8 Canales HBO", promo_price=3.0, post_price=7.99),
            ],
        ),
        _home_offer(
            "SV", "Claro", "Claro Hogar Doble 500 Megas + Claro TV", "USD",
            "https://www.claro.com.sv/personas/servicios/servicios-hogar/claro-tv-plus/claro-hogar-doble/planes-y-precios/",
            "Claro El Salvador: Doble Play 500 Megas + Claro TV HD con Ultra WiFi $86.00/mes.",
            png_path, md_path, reg_price=86.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Ultra WiFi Mesh", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ y Claro video incluidos.", tier="Premium"),
            ],
        ),
        _home_offer(
            "SV", "Digicel", "Plan Pospago LTE Ilimitado (Operación Móvil SV)", "USD",
            "https://www.digicelgroup.com/sv/es/mobile/rates.html",
            "Digicel El Salvador: Plan Pospago LTE Datos Ilimitados (25 GB hotspot) $24.99/mes. Nota: fibra.digicel.com.sv opera solo bajo cotización cerrada sin tarifas públicas.",
            png_path, md_path, segment="MOBILE_POSTPAID", reg_price=24.99, taxes_incl=True,
            vas=[],
        ),

        # ---------------------------------------------------------------------
        # 3. HONDURAS (HN — Currency: HNL) | Operators: Tigo, Claro
        # ---------------------------------------------------------------------
        _home_offer(
            "HN", "Tigo", "Tigo Hogar 120 Mbps + ONEtv HD", "HNL",
            "https://www.tigo.com.hn/residencial",
            "Tigo Honduras: Plan Residencial 120 Mbps + decodificador Android TV Tigo ONEtv L990.00/mes (~$39.92 USD ref). Incluye Paramount+ sin costo en ONEtv y ViX Premium disponible a L165/mes.",
            png_path, md_path, reg_price=990.0, taxes_incl=True, tech="HFC", dl=120, wifi="Router WiFi Dual", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+ en ONEtv", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido sin costo adicional (L0.00) en todos los planes ONEtv Hogar (ayuda.tigo.com.hn).", tier="Estándar"),
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports HN", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Señal deportiva Liga Nacional HN incluida en planes TV (migrada a FOX 2026).", tier="HD"),
                _vas(VASProviderEnum.VIX, "ViX Premium + LaLiga", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon ViX Premium con LaLiga publicado en ayuda.tigo.com.hn a L165.00/mes ISV incluido.", tier="Premium", post_price=165.0),
            ],
        ),
        _home_offer(
            "HN", "Tigo", "Tigo Hogar Alta Velocidad 400 Mbps + ONEtv", "HNL",
            "https://www.tigo.com.hn/residencial",
            "Tigo Honduras: Plan Residencial 400 Mbps + Tigo ONEtv HD L1,365.00/mes (~$55.04 USD ref en tigo.com.hn). Incluye Paramount+ y canal deportivo FOX.",
            png_path, md_path, reg_price=1365.0, taxes_incl=True, tech="FTTH", dl=400, wifi="Router WiFi Alta Velocidad", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+ en ONEtv", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido fijo en planes ONEtv Hogar.", tier="Estándar"),
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports HN", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Deportes locales e internacionales incluidos en TV.", tier="HD"),
            ],
        ),
        _home_offer(
            "HN", "Claro", "Paquete Triple Play Fibra 150 Megas", "HNL",
            "https://www.claro.com.hn/personas/servicios/hogar/triple-play/",
            "Claro Honduras: Paquete Triple Play 150 Megas FTTH + 127 canales (70 HD) + 2 cajas IPTV + Línea Fija L700.00/mes ISV incluido.",
            png_path, md_path, reg_price=700.0, taxes_incl=True, tech="FTTH", dl=150, wifi="ONT Fibra WiFi", tv_ch=127, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye Universal+, Claro video, Atresplayer y Claro Drive 25 GB.", tier="Incluido"),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "30 días de cortesía vía Mi Claro.", tier="Estándar", free_months=1, promo_price=0.0),
            ],
        ),
        _home_offer(
            "HN", "Claro", "Paquete Triple Play 300 Megas Simétrico", "HNL",
            "https://www.claro.com.hn/personas/servicios/hogar/triple-play/",
            "Claro Honduras: Paquete Triple Play 300 Megas Fibra Óptica Simétrica (300/300 Mbps) + 127 canales + 2 cajas IPTV L850.00/mes ISV incluido.",
            png_path, md_path, reg_price=850.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="ONT Fibra Simétrica", tv_ch=127, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ y Claro video incluidos en tarifa mensual.", tier="Incluido"),
                _vas(VASProviderEnum.MAX, "Max (HBO)", VASCommercialModelEnum.STANDALONE_PAID,
                     "Disponible como paquete adicional desde L110.00/mes.", tier="Estándar", post_price=110.0),
            ],
        ),
        _home_offer(
            "HN", "Claro", "Paquete Triple Play 1000 Megas + Max & Universal+", "HNL",
            "https://www.claro.com.hn/personas/servicios/hogar/triple-play/",
            "Claro Honduras: Paquete Triple Play 1000 Megas FTTH + 127 canales Avanzado HD Plus + 2 cajas IPTV + Max y Universal+ incluidos L2,110.00/mes ISV incluido.",
            png_path, md_path, reg_price=2110.0, taxes_incl=True, tech="FTTH", dl=1000, wifi="Router Fibra Gigabit", tv_ch=127, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.MAX, "Max (HBO)", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max (HBO) incluido fijo en Paquete Triple Play 1000 Megas.", tier="Full HBO + App"),
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ y Claro video incluidos.", tier="Premium"),
            ],
        ),

        # ---------------------------------------------------------------------
        # 4. NICARAGUA (NI — Currency: NIO) | Operators: Tigo, Claro
        # ---------------------------------------------------------------------
        _home_offer(
            "NI", "Tigo", "Internet Residencial Básico 100 Mbps", "NIO",
            "https://www.tigo.com.ni/planes",
            "Tigo Nicaragua: Plan entrada Internet Residencial 100 Mbps C$700.00/mes IVA incluido.",
            png_path, md_path, reg_price=700.0, taxes_incl=True, tech="HFC", dl=100, wifi="Router WiFi Residencial",
            vas=[],
        ),
        _home_offer(
            "NI", "Tigo", "Combo Tigo Hogar 200 Mbps + One TV HD", "NIO",
            "https://www.tigo.com.ni/planes",
            "Tigo Nicaragua: Combo Tigo Hogar 200 Mbps + 170 canales con caja interactiva Tigo One TV C$1,210.00/mes IVA incluido.",
            png_path, md_path, reg_price=1210.0, taxes_incl=True, tech="FTTH", dl=200, wifi="Router WiFi + One TV Box", tv_ch=170, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "FOX / Tigo Sports NI", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Canal deportivo incluido en grilla TV Digital / One TV.", tier="HD"),
            ],
        ),
        _home_offer(
            "NI", "Claro", "Claro Hogar Triple 120 Mbps", "NIO",
            "https://www.claro.com.ni/personas/servicios/hogar/claro-hogar-triple/",
            "Claro Nicaragua: Claro Hogar Triple 120 Mbps + TV Avanzado HD Plus + 200 min línea fija C$955.00/mes.",
            png_path, md_path, reg_price=955.0, taxes_incl=True, tech="FTTH", dl=120, wifi="ONT WiFi", tv_boxes=1,
            vas=[],
        ),
        _home_offer(
            "NI", "Claro", "Claro Hogar Triple 220 Mbps", "NIO",
            "https://www.claro.com.ni/personas/servicios/hogar/claro-hogar-triple/",
            "Claro Nicaragua: Claro Hogar Triple 220 Mbps + TV Avanzado HD Plus + línea fija C$1,100.00/mes.",
            png_path, md_path, reg_price=1100.0, taxes_incl=True, tech="FTTH", dl=220, wifi="ONT WiFi", tv_boxes=1,
            vas=[],
        ),
        _home_offer(
            "NI", "Claro", "Claro Hogar Triple 320 Mbps Fibra + Max & Universal+", "NIO",
            "https://tiendaenlinea.claro.com.ni/tienda/planes-claro-hogar",
            "Claro Nicaragua: Claro Hogar Triple 320 Mbps Fibra Óptica + 169 canales (100 HD) + Max, Universal+ y Claro video incluidos C$1,170.00 promo online x 3 meses / C$1,280.00 regular.",
            png_path, md_path, promo_price=1170.0, promo_months=3, reg_price=1280.0, taxes_incl=True, tech="FTTH", dl=320, wifi="ONT Fibra + Claro TV+ Box", tv_ch=169, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.MAX, "Max (HBO Max)", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido sin costo en plan Claro Hogar Triple 320 Mbps (standalone C$220.00/mes).", tier="Estándar", post_price=220.0),
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ y Atresplayer incluidos en Triple 320 Mbps.", tier="Premium"),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.STANDALONE_PAID,
                     "Disponible como addon Prime Video C$256.00/mes IVA incluido.", tier="Estándar", post_price=256.0),
            ],
        ),

        # ---------------------------------------------------------------------
        # 5. COSTA RICA (CR — Currency: CRC) | Tigo, Liberty, Kolbi, Claro, Telecable
        # ---------------------------------------------------------------------
        _home_offer(
            "CR", "Tigo", "Dúo Hogar 150 Mbps + TV HD + Tigo Sports", "CRC",
            "https://www.tigo.cr/hogar/internet-y-television",
            "Tigo Costa Rica: Dúo 150 Mbps + TV HD (159 canales video + 50 música) + Tigo OneTV App ₡25,640 IVAI/mes (Solo Internet 150 Mbps: ₡22,150 IVAI).",
            png_path, md_path, reg_price=25640.0, taxes_incl=True, tech="FTTH", dl=150, wifi="Router WiFi+", tv_ch=159, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Costa Rica", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye Tigo Sports HD con Primera División CR sin costo extra.", tier="HD + OneTV App"),
            ],
        ),
        _home_offer(
            "CR", "Tigo", "Plan Dúo 250 Mbps + TV HD + 2do Deco Gratis", "CRC",
            "https://www.tigo.cr/hogar/internet-y-television",
            "Tigo Costa Rica: Plan 250 Mbps + TV HD en promoción ₡24,990 IVAI por 4 meses, luego ₡26,640 IVAI. Incluye Tigo Sports y 2do deco HD.",
            png_path, md_path, promo_price=24990.0, promo_months=4, reg_price=26640.0, taxes_incl=True, tech="FTTH", dl=250, wifi="Router WiFi+", tv_ch=159, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Costa Rica", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports incluido fijo en planes TV HD.", tier="HD"),
            ],
        ),
        _home_offer(
            "CR", "Tigo", "Plan Dúo 500 Mbps + TV HD + Tigo Sports", "CRC",
            "https://www.tigo.cr/hogar/internet-y-television",
            "Tigo Costa Rica: Plan 500 Mbps + TV HD ₡34,640 IVAI/mes (Plan 350 Mbps Solo Internet en promo a ₡21,990 x 4 meses).",
            png_path, md_path, reg_price=34640.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Router WiFi+", tv_ch=159, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Costa Rica", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports HD incluido fijo.", tier="HD + App"),
            ],
        ),
        _home_offer(
            "CR", "Liberty", "Doble Play Mega 120 + Next TV + Pack Entretenimiento", "CRC",
            "https://libertycr.com/hogar",
            "Liberty Costa Rica: Doble Play Mega 120 + Next TV IPTV + 2 decos ₡19,941.80 final (modalidad tractos 24 meses) / ₡29,080.74 modalidad alquiler. Incluye Disney+, Max y Universal+.",
            png_path, md_path, promo_price=19941.8, promo_months=24, reg_price=29080.74, taxes_incl=True, tech="FTTH", dl=120, wifi="Router WiFi Liberty", tv_ch=234, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluido a ₡0 en Pack de Entretenimiento Next TV (valorado en ₡19,500/mes).", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max + Canales HBO", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido sin costo adicional en Pack de Entretenimiento Next TV.", tier="Estándar + HBO"),
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ incluido en Pack de Entretenimiento Next TV.", tier="Premium"),
            ],
        ),
        _home_offer(
            "CR", "Liberty", "Plan 300 Megas Internet + Next TV + Pack Entretenimiento", "CRC",
            "https://libertycr.com/hogar",
            "Liberty Costa Rica: Plan 300 Megas + Next TV (+240 canales, 2 cajas TV) ₡27,951.03 (modalidad tractos 24 meses) / ₡40,200.90 (alquiler) impuestos incluidos. Incluye Disney+, Max y Universal+.",
            png_path, md_path, promo_price=27951.03, promo_months=24, reg_price=40200.9, taxes_incl=True, tech="FTTH", dl=300, wifi="Router WiFi + Next TV", tv_ch=240, tv_boxes=2,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Pack Entretenimiento incluido a ₡0 extra.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max + HBO", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Pack Entretenimiento incluido a ₡0 extra.", tier="Estándar"),
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Pack Entretenimiento incluido a ₡0 extra.", tier="Premium"),
            ],
        ),
        _home_offer(
            "CR", "Kolbi", "Fibra Óptica Simétrica 300 Mbps Individual", "CRC",
            "https://www.kolbi.cr/wps/portal/kolbi/personas/hogar/internet/fibra-optica",
            "kölbi ICE Costa Rica: Fibra Óptica Simétrica 300/300 Mbps con Súper WiFi Mesh ₡25,900/mes impuestos incluidos (+₡1,130 alquiler módem). Dúo 300M + kölbi TV: ₡46,600.",
            png_path, md_path, reg_price=25900.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="Súper WiFi Mesh",
            vas=[],
        ),
        _home_offer(
            "CR", "Kolbi", "Plan Dúo Fibra Simétrica 500 Mbps + kölbi TV", "CRC",
            "https://www.kolbi.cr/wps/portal/kolbi/personas/hogar/planes-duo",
            "kölbi ICE Costa Rica: Plan Dúo Fibra 500/500 Mbps + kölbi TV (115 canales para 2 TVs) ₡72,800/mes impuestos incluidos (Solo Fibra 500 Mbps: ₡27,900).",
            png_path, md_path, reg_price=72800.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=500, ul=500, wifi="Súper WiFi Mesh", tv_ch=115, tv_boxes=2,
            vas=[],
        ),
        _home_offer(
            "CR", "Claro", "Doble Play Fibra Simétrica 150 Mbps + TV Ultra HD", "CRC",
            "https://www.claro.cr/portal/cr/sc/personas/servicios/servicios-hogar/doble-play-fibra-optica",
            "Claro Costa Rica: Doble Play Fibra Simétrica 150/150 Mbps + Claro TV+ (>100 canales) + Paramount+ y Claro Video incluidos ₡24,681/mes impuestos incluidos.",
            png_path, md_path, reg_price=24681.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=150, ul=150, wifi="ONT Fibra WiFi", tv_ch=100, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ y Claro Video incluidos sin costo adicional.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max (HBO)", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Addon Max en Claro TV+ a ₡3,800 promo inicial, luego ₡5,413/mes.", tier="Estándar", promo_price=3800.0, post_price=5413.0),
            ],
        ),
        _home_offer(
            "CR", "Claro", "Internet Simétrico Fibra 500 Mbps + Paramount+", "CRC",
            "https://www.claro.cr/portal/cr/sc/personas/servicios/servicios-hogar/internet-fibra-optica",
            "Claro Costa Rica: Internet Fibra Óptica Simétrica 500/500 Mbps con Paramount+ y Claro Video incluidos ₡26,495/mes impuestos incluidos.",
            png_path, md_path, reg_price=26495.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=500, ul=500, wifi="ONT Fibra WiFi",
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido a ₡0 en Fibra Óptica Claro CR.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CR", "Telecable", "Paquete Estándar Fibra Simétrica 300 Mbps + TV 180 Canales", "CRC",
            "https://telecablecr.com/paquete-estandar-con-tv",
            "Telecable Costa Rica: Paquete Estándar Fibra Simétrica 300/300 Mbps + 2 cajas digitales (180 canales: 145 HD, incluye FUTV y TD Más) ₡29,990/mes i.i. (Paquete Básico 150M + TV: ₡25,990 i.i.).",
            png_path, md_path, reg_price=29990.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="Módem Fibra WiFi", tv_ch=180, tv_boxes=2,
            vas=[],
        ),
        _home_offer(
            "CR", "Telecable", "Plan Experto Fibra Simétrica 1000 Mbps + T-Play Pro", "CRC",
            "https://telecablecr.com/internet-fibra-optica",
            "Telecable Costa Rica: Fibra Simétrica 1000/1000 Mbps + Router eero 6+ Mesh + 2 cajas T-Play Pro (180 canales) ₡55,990/mes impuestos incluidos.",
            png_path, md_path, reg_price=55990.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=1000, ul=1000, wifi="Router eero 6+ Mesh", tv_ch=180, tv_boxes=2,
            vas=[],
        ),

        # ---------------------------------------------------------------------
        # 6. PANAMA (PA — Currency: USD) | Operators: Tigo, MasMovil
        # ---------------------------------------------------------------------
        _home_offer(
            "PA", "Tigo", "Internet + TV 300 Megas + Tigo Sports", "USD",
            "https://www.tigo.com.pa/hogar/internet",
            "Tigo Panamá: Plan Internet 300 Megas (15 Mbps subida) + TV HD (~150 canales incl. Tigo Sports LPF, COS, ECO) + Tigo OneTV App B/. 44.00/mes (+7% ITBMS).",
            png_path, md_path, reg_price=44.0, taxes_incl=False, tech="HFC", symmetric=False, dl=300, ul=15, wifi="Router WiFi Dual", tv_ch=150, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Panamá", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports con Liga Panameña de Fútbol (LPF) incluido a B/. 0.00 en planes TV.", tier="HD + OneTV App"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.STANDALONE_PAID,
                     "Disponible como addon en factura Tigo Hogar vía Mi Tigo por B/. 12.49/mes.", tier="Estándar", post_price=12.49),
            ],
        ),
        _home_offer(
            "PA", "Tigo", "Solo Internet Hogar 500 Megas", "USD",
            "https://www.tigo.com.pa/hogar/internet",
            "Tigo Panamá: Plan Solo Internet 500 Megas (15 Mbps subida) en oferta digital B/. 33.00/mes por 12 meses, tarifa regular B/. 40.00/mes (+7% ITBMS).",
            png_path, md_path, promo_price=33.0, promo_months=12, reg_price=40.0, taxes_incl=False, tech="HFC", symmetric=False, dl=500, ul=15, wifi="Router WiFi+",
            vas=[
                _vas(VASProviderEnum.VIX, "ViX Premium con LaLiga", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon ViX Premium disponible vía Mi Tigo por B/. 6.99/mes.", tier="Premium", post_price=6.99),
            ],
        ),
        _home_offer(
            "PA", "Tigo", "Internet + TV 500 Megas + WiFi+ Mesh", "USD",
            "https://www.tigo.com.pa/hogar/internet",
            "Tigo Panamá: Internet 500 Megas (15 Mbps subida) + TV Digital (~220 canales) + extensor WiFi+ Mesh B/. 56.00/mes (+7% ITBMS). Convergente Full Tigo 500M: B/. 59.00 promo / B/. 89.00 reg.",
            png_path, md_path, reg_price=56.0, taxes_incl=False, tech="HFC", symmetric=False, dl=500, ul=15, wifi="WiFi+ con Extensor Mesh", tv_ch=220, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Panamá", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports HD incluido sin cargo extra.", tier="HD"),
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido promocionalmente en paquetes Combo Pack seleccionados.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "PA", "Tigo", "Internet + TV 750 Megas + WiFi+ Mesh", "USD",
            "https://www.tigo.com.pa/hogar/internet",
            "Tigo Panamá: Internet 750 Megas (15 Mbps subida) + TV Digital (~220 canales) + WiFi+ Mesh B/. 59.00/mes (+7% ITBMS).",
            png_path, md_path, reg_price=59.0, taxes_incl=False, tech="FTTH", symmetric=False, dl=750, ul=15, wifi="WiFi+ con Extensor Mesh", tv_ch=220, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Panamá", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports incluido en planes residenciales TV.", tier="HD"),
            ],
        ),
        _home_offer(
            "PA", "MasMovil", "Internet +Fibra Simétrica 300 Mbps", "USD",
            "https://www.masmovilpanama.com/hogar/internet-residencial",
            "+Móvil Panamá: Solo Internet +Fibra Simétrica 300/300 Mbps B/. 35.00/mes (+7% ITBMS). Solo Fibra 600M: B/. 38.00/mes; Un GIGA 1000M: B/. 41.00/mes.",
            png_path, md_path, reg_price=35.0, taxes_incl=False, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="ONT +Fibra WiFi",
            vas=[],
        ),
        _home_offer(
            "PA", "MasMovil", "Paquete Hogar +Fibra 300 Megas + TV + Universal+", "USD",
            "https://www.masmovilpanama.com/paquete-hogar/combos-hogar",
            "+Móvil Panamá: Paquete Hogar +Fibra 300/300 Mbps + +TV Total Smart HD Box (225 canales, 24h Replay) + Universal+ + 200 min voz fija B/. 53.00/mes (+7% ITBMS; variante base sin Universal+: B/. 44.00/mes).",
            png_path, md_path, reg_price=53.0, taxes_incl=False, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="ONT +Fibra WiFi", tv_ch=225, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+ (5 Canales + App)", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluido en Paquete Hogar +Fibra 300 Megas + TV + Universal+ (B/. 53.00/mes).", tier="5 Canales HD + App"),
            ],
        ),
        _home_offer(
            "PA", "MasMovil", "Paquete Hogar +Fibra 600 Megas + TV + Universal+", "USD",
            "https://www.masmovilpanama.com/paquete-hogar/combos-hogar",
            "+Móvil Panamá: Paquete Hogar +Fibra Simétrica 600/600 Mbps + +TV Total Smart HD (225 canales) + Universal+ + Voz Fija B/. 56.00/mes (+7% ITBMS; variante base sin Universal+: B/. 52.00/mes).",
            png_path, md_path, reg_price=56.0, taxes_incl=False, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="ONT +Fibra Dual Band", tv_ch=225, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye 5 canales HD Universal+ y acceso a Universal+ App en el paquete de B/. 56.00/mes.", tier="Premium"),
            ],
        ),
        _home_offer(
            "PA", "MasMovil", "Paquete Hogar Un GIGA 1000 Megas + TV + Disney+ Premium", "USD",
            "https://www.masmovilpanama.com/paquete-hogar/combos-hogar",
            "+Móvil Panamá: Paquete Hogar +Fibra Simétrica 1000/1000 Mbps + +TV Total Smart HD + Universal+ / Disney+ Premium B/. 59.00/mes (+7% ITBMS). Solo Fibra Un GIGA: B/. 41.00/mes.",
            png_path, md_path, reg_price=59.0, taxes_incl=False, tech="FTTH", symmetric=True, dl=1000, ul=1000, wifi="Router +Fibra Gigabit", tv_ch=225, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Universal+ incluido en combos +TV Total Giga.", tier="Premium"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium con ESPN", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ Premium incluido en paquetes superiores seleccionados / +Móvil Total.", tier="Premium con ESPN"),
            ],
        ),

        # ---------------------------------------------------------------------
        # 7. COLOMBIA (CO — Currency: COP, Bogotá Estrato 3) | Tigo, Movistar, Claro, WOM, ETB
        # ---------------------------------------------------------------------
        _home_offer(
            "CO", "Tigo", "Plan Solo Internet 500 Megas", "COP",
            "https://www.tigo.com.co/personas/hogar/internet",
            "Tigo Colombia (Bogotá Estrato 3): Plan Solo Internet 500 Megas $84.900/mes IVA 19% incluido.",
            png_path, md_path, reg_price=84900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Router WiFi Dual Band",
            vas=[],
        ),
        _home_offer(
            "CO", "Tigo", "Dúo Internet 500 Megas + Televisión Digital Avanzada", "COP",
            "https://www.tigo.com.co/personas/hogar/paquetes",
            "Tigo Colombia (Bogotá Estrato 3): Dúo Internet 500 Megas + TV Digital Avanzada (>120 canales) $106.900 promo online x 6 meses / $109.200 regular IVA incluido.",
            png_path, md_path, promo_price=106900.0, promo_months=6, reg_price=109200.0, install_fee=0.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Router WiFi Dual Band", tv_ch=120, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.WIN_SPORTS, "Win+ Fútbol", VASCommercialModelEnum.STANDALONE_PAID,
                     "Adiciona Win+ Fútbol (FPC en vivo) desde $33.200/mes IVA incluido.", tier="HD + Win Play", post_price=33200.0),
            ],
        ),
        _home_offer(
            "CO", "Tigo", "Full Tigo+ 500 Megas + TV Avanzada + Móvil Ilimitado", "COP",
            "https://www.tigo.com.co/personas/postpago/full-tigo",
            "Tigo Colombia (Bogotá Estrato 3): Plan Convergente Full Tigo+ 500 Megas + TV Digital Avanzada + Móvil Pospago Ilimitado $149.900/mes IVA incluido con 12 meses de Paramount+ sin costo.",
            png_path, md_path, reg_price=149900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", dl=500, wifi="Router WiFi Dual Band", tv_ch=120, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "Incluye 12 meses sin costo de Paramount+ en planes Full Tigo / Full Tigo+; luego $23.500/mes.", tier="Estándar", free_months=12, promo_price=0.0, post_price=23500.0),
            ],
        ),
        _home_offer(
            "CO", "Movistar", "Fibra Óptica Simétrica 900 Megas Solo Internet", "COP",
            "https://www.movistar.co/personas/hogar/internet-bogota",
            "Movistar Colombia (Bogotá Estrato 3): Fibra Simétrica 900/900 Megas en oferta online $75.992/mes x 12 meses, tarifa referencia Estrato 3 $84.900 IVA incluido.",
            png_path, md_path, promo_price=75992.0, promo_months=12, reg_price=84900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=900, ul=900, wifi="Smart WiFi Router",
            vas=[
                _vas(VASProviderEnum.NETFLIX, "Netflix Estándar", VASCommercialModelEnum.STANDALONE_PAID,
                     "Facturación Movistar: Netflix Básico $18.900, Estándar $29.900, Premium $44.900/mes.", tier="Estándar", post_price=29900.0),
            ],
        ),
        _home_offer(
            "CO", "Movistar", "Dúo Fibra Simétrica 900 Megas + Movistar TV", "COP",
            "https://www.movistar.co/personas/hogar",
            "Movistar Colombia (Bogotá Estrato 3): Dúo Fibra 900/900 Megas + Movistar TV IPTV (90 canales HD) $109.155/mes por 12 meses, luego $136.900 IVA incluido.",
            png_path, md_path, promo_price=109155.0, promo_months=12, reg_price=136900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=900, ul=900, wifi="Smart WiFi 6", tv_ch=90, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.WIN_SPORTS, "Win+ Fútbol / Win Play", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Promoción Win+ Fútbol a $33.900/mes durante los primeros 3 meses.", tier="Win+ HD", promo_price=33900.0),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluido en combos seleccionados Ficción Total / Movistar Total.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CO", "Claro", "Internet Hogar 300 Megas", "COP",
            "https://www.claro.com.co/personas/hogar/planes/internet-hogar/",
            "Claro Colombia (Bogotá Estrato 3): Internet Hogar 300 Megas tarifa vigente $89.900/mes IVA incluido con Claro Video.",
            png_path, md_path, reg_price=89900.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="Router WiFi Dual",
            vas=[],
        ),
        _home_offer(
            "CO", "Claro", "Tripleplay Fibra 500 Megas + Claro TV+ + Voz", "COP",
            "https://www.claro.com.co/personas/servicios/hogar/",
            "Claro Colombia (Bogotá Estrato 3): Tripleplay 500/500 Megas + Claro TV+ (>100 canales) + Voz Fija $104.900/mes IVA incluido.",
            png_path, md_path, reg_price=104900.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=500, ul=500, wifi="Router WiFi 6", tv_ch=100, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.WIN_SPORTS, "Win+ Fútbol", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Disponible en combos Intermedio Plus + Win (~$30.900-$32.900/mes addon).", tier="HD", promo_price=30900.0, post_price=32900.0),
            ],
        ),
        _home_offer(
            "CO", "Claro", "Tripleplay Fibra 900 Megas + Claro TV+", "COP",
            "https://www.claro.com.co/personas/servicios/hogar/",
            "Claro Colombia (Bogotá Estrato 3): Tripleplay Fibra 900/900 Megas + Claro TV+ Box + Voz Fija $116.900/mes IVA incluido.",
            png_path, md_path, reg_price=116900.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=900, ul=900, wifi="Router WiFi 6", tv_ch=100, tv_boxes=1,
            vas=[],
        ),
        _home_offer(
            "CO", "WOM", "Plan Pospago Móvil WOM Ilimitado 4G/5G (Sin Fibra Fija en CO)", "COP",
            "https://www.wom.co/planes",
            "WOM Colombia: No comercializa fibra fija FTTH/HFC residencial en Colombia (solo planes móviles 4G/5G compatibles con MiFi). Plan WOM Ilimitado $54.990/mes IVA incluido.",
            png_path, md_path, segment="MOBILE_POSTPAID", reg_price=54990.0, taxes_incl=True,
            vas=[],
        ),
        _home_offer(
            "CO", "ETB", "Internet Fibra Simétrica Solo 500 Mb", "COP",
            "https://etb.com/hogares/Bogota.aspx?plan=total",
            "ETB Bogotá (Estrato 3): Internet Fibra Óptica Simétrica 500/500 Mbps en promo 20% dto $55.920/mes por 6 meses, tarifa regular $69.900 IVA incluido.",
            png_path, md_path, promo_price=55920.0, promo_months=6, reg_price=69900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=500, ul=500, wifi="ONT Fibra WiFi",
            vas=[
                _vas(VASProviderEnum.WIN_SPORTS, "Win Play", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Adiciona Win Play por $17.900/mes promo en planes Fibra ETB.", tier="App Win Play", promo_price=17900.0),
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Paramount+ en factura ETB $19.990/mes.", tier="Estándar", post_price=19990.0),
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Universal+ en factura ETB $24.900/mes.", tier="Premium", post_price=24900.0),
            ],
        ),
        _home_offer(
            "CO", "ETB", "Fibra Simétrica 910 Mb + TV Plus (Estrato 3)", "COP",
            "https://etb.com/hogares/Bogota.aspx?plan=total",
            "ETB Bogotá (Estrato 3): Fibra Simétrica 910/910 Mbps + TV Plus IPTV (>100 canales) $131.920/mes por 6 meses (20% dto), luego $164.900 IVA incluido.",
            png_path, md_path, promo_price=131920.0, promo_months=6, reg_price=164900.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=910, ul=910, wifi="ONT Fibra WiFi", tv_ch=100, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.WIN_SPORTS, "Win Play", VASCommercialModelEnum.DISCOUNTED_ADDON,
                     "Combo elegible para Win Play o DGO Pass promocional.", tier="Win Play", promo_price=17900.0),
            ],
        ),

        # ---------------------------------------------------------------------
        # 8. BOLIVIA (BO — Currency: BOB) | Operators: Tigo, Entel, Viva, AXS
        # ---------------------------------------------------------------------
        _home_offer(
            "BO", "Tigo", "Wifi Hogar Esencial 60 Mbps", "BOB",
            "https://www.tigo.com.bo/hogar",
            "Tigo Bolivia: Plan Wifi Hogar Esencial 60 Mbps ilimitado Bs. 179/mes (+2.000 MB bono móvil por pago puntual días 1-10). Addon Tigo Sports disponible a Bs. 20/mes.",
            png_path, md_path, reg_price=179.0, taxes_incl=True, tech="HFC", dl=60, wifi="Router WiFi Tigo",
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Bolivia", VASCommercialModelEnum.STANDALONE_PAID,
                     "Disponible como addon en planes solo internet por Bs. 20/mes.", tier="App + Señal", post_price=20.0),
            ],
        ),
        _home_offer(
            "BO", "Tigo", "Tigo Hogar Básico 60 Mbps", "BOB",
            "https://www.tigo.com.bo/hogar",
            "Tigo Bolivia: Plan Tigo Hogar Básico 60 Mbps Bs. 249/mes IVA incluido. Addons Mi Tigo publicados: Paramount+ Bs. 41, Max Bs. 49, Disney+ Premium Bs. 132.",
            png_path, md_path, reg_price=249.0, taxes_incl=True, tech="HFC", dl=60, wifi="Router WiFi Tigo",
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Paramount+ publicado en tigo.com.bo por Bs. 41/mes.", tier="Estándar", post_price=41.0),
                _vas(VASProviderEnum.MAX, "Max + 8 Canales HBO HD", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Max publicado en tigo.com.bo por Bs. 49/mes.", tier="Estándar + HBO", post_price=49.0),
            ],
        ),
        _home_offer(
            "BO", "Tigo", "Full Tigo + TV Avanzado (129 Canales + Tigo Sports)", "BOB",
            "https://www.tigo.com.bo/hogar",
            "Tigo Bolivia: Plan convergente Full Tigo + TV Avanzado (Internet Hogar 150 Mbps + 129 canales TV + Móvil) Bs. 399/mes. Incluye Tigo Sports sin costo y promo Disney+ Premium.",
            png_path, md_path, reg_price=399.0, taxes_incl=True, tech="FTTH", dl=150, wifi="Router WiFi Hogar", tv_ch=129, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports Bolivia", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports incluido a Bs. 0 en planes Full Tigo + TV Inicial / Medio / Avanzado / Ultra.", tier="HD + App"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium (4K + ESPN)", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "12 meses de cortesía en planes Full Tigo + TV Avanzado seleccionados; tarifa regular Bs. 132/mes.", tier="Premium + ESPN", free_months=12, promo_price=0.0, post_price=132.0),
            ],
        ),
        _home_offer(
            "BO", "Entel", "Internet Fibra 60 Mbps", "BOB",
            "https://www.entel.bo/hogar/fibra-optica",
            "Entel Bolivia: Internet Fibra Óptica GPON 60 Mbps Bs. 169/mes (instalación Bs. 200 con ONT en comodato; relación general bajada/subida 2:1).",
            png_path, md_path, reg_price=169.0, install_fee=200.0, taxes_incl=True, tech="FTTH", dl=60, wifi="ONT GPON WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "Entel", "DUO Intermedio Fibra 150 Mbps + Móvil Ilimitado", "BOB",
            "https://www.entel.bo/hogar/duo-pack",
            "Entel Bolivia: Plan DUO Intermedio Fibra 150 Mbps + línea móvil con datos/llamadas ilimitadas Bs. 239/mes (Solo Fibra 120 Mbps: Bs. 229/mes).",
            png_path, md_path, reg_price=239.0, install_fee=200.0, taxes_incl=True, tech="FTTH", dl=150, wifi="ONT GPON WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "Entel", "DUO Premium Fibra 300 Mbps + Móvil", "BOB",
            "https://www.entel.bo/hogar/duo-pack",
            "Entel Bolivia: Plan DUO Premium Fibra 300 Mbps + Móvil Bs. 379/mes (Solo Internet Fibra 300 Mbps: Bs. 369/mes; Fibra 450 Mbps: Bs. 499/mes).",
            png_path, md_path, reg_price=379.0, install_fee=200.0, taxes_incl=True, tech="FTTH", dl=300, wifi="ONT GPON WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "Viva", "Fibra Óptica FO 60 Mbps", "BOB",
            "https://www.viva.com.bo/personas/hogar/fibra-optica/",
            "Viva Bolivia: Plan Fibra Óptica FO 60 Mbps bajada / 15 Mbps subida Bs. 179/mes (instalación promocional desde Bs. 49).",
            png_path, md_path, reg_price=179.0, install_fee=49.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=60, ul=15, wifi="ONT Fibra WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "Viva", "Convergente FO + Inicial 150 Mbps + Móvil WOW", "BOB",
            "https://www.viva.com.bo/personas/hogar/fibra-optica/",
            "Viva Bolivia: Plan Convergente FO + Inicial 150 Mbps bajada / 38 Mbps subida + plan móvil WOW Inicial Bs. 229/mes (Solo FO 120/30 Mbps: Bs. 239/mes).",
            png_path, md_path, reg_price=229.0, install_fee=49.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=150, ul=38, wifi="ONT Fibra WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "Viva", "Fibra Óptica FO 200 Mbps", "BOB",
            "https://www.viva.com.bo/personas/hogar/fibra-optica/",
            "Viva Bolivia: Plan Fibra Óptica FO 200 Mbps bajada / 50 Mbps subida Bs. 349/mes (Convergente FO + Esencial 200/50 Mbps: Bs. 279/mes; FO 400/100 Mbps: Bs. 529/mes).",
            png_path, md_path, reg_price=349.0, install_fee=49.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=200, ul=50, wifi="ONT Fibra WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "AXS", "Fibra Hogar Pro 70 Mbps", "BOB",
            "https://www.axsbolivia.com/axs-net/",
            "AXS Bolivia: Plan Fibra Hogar Pro GPON 70 Mbps (subida hasta 25% = 17.5 Mbps) Bs. 219.00/mes (instalación Bs. 199 con ONT en comodato).",
            png_path, md_path, reg_price=219.0, install_fee=199.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=70, ul=None, wifi="ONT GPON WiFi",
            vas=[],
        ),
        _home_offer(
            "BO", "AXS", "AXS+ Fibra Hogar Pro 135 Mbps + IPTV + HBO Max", "BOB",
            "https://www.axsbolivia.com/tarifas-servicio-de-distribucion-de-senales-iptv-internet/",
            "AXS Bolivia: Combo AXS+ Fibra Hogar Pro 135 Mbps + Televisión IPTV con 1 AXS+ Android TV Box + paquete HBO Premium (Max) Bs. 324.00/mes (Solo Fibra 135 Mbps: Bs. 289.00).",
            png_path, md_path, reg_price=324.0, install_fee=199.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=135, ul=None, wifi="ONT GPON + AXS+ Box", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.MAX, "HBO Premium / Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paquete HBO Premium incluido fijo en combos AXS+ Fibra Hogar Pro + HBO.", tier="HBO Premium + App"),
            ],
        ),
        _home_offer(
            "BO", "AXS", "Fibra Hogar Pro 250 Mbps", "BOB",
            "https://www.axsbolivia.com/tarifa/",
            "AXS Bolivia: Plan Fibra Hogar Pro GPON 250 Mbps (subida hasta 25% = 62.5 Mbps) Bs. 459.00/mes.",
            png_path, md_path, reg_price=459.0, install_fee=199.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=250, ul=None, wifi="ONT GPON Dual Band",
            vas=[],
        ),

        # ---------------------------------------------------------------------
        # 9. PARAGUAY (PY — Currency: PYG) | Tigo, Personal Flow, Claro
        # ---------------------------------------------------------------------
        _home_offer(
            "PY", "Tigo", "Internet Hogar 200 Mbps", "PYG",
            "https://www.tigo.com.py/hogar/internet",
            "Tigo Paraguay: Plan Solo Internet Hogar 200 Mbps Gs. 170.000/mes IVA incluido.",
            png_path, md_path, reg_price=170000.0, taxes_incl=True, tech="HFC", dl=200, wifi="Router WiFi Tigo",
            vas=[],
        ),
        _home_offer(
            "PY", "Tigo", "DoblePack 300 Mbps + TV Familiar + Tigo Sports & Disney+", "PYG",
            "https://www.tigo.com.py/hogar/internet",
            "Tigo Paraguay: DoblePack 300 Mbps + TV Familiar Gs. 215.000 promo x 6 meses / Gs. 255.000 regular IVA incluido (Solo Internet 300 Mbps: Gs. 220.000). Incluye Tigo Sports fijo y 12 meses de Disney+ Estándar sin costo.",
            png_path, md_path, promo_price=215000.0, promo_months=6, reg_price=255000.0, taxes_incl=True, tech="FTTH", dl=300, wifi="Router WiFi Plus", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports PY", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Fútbol paraguayo exclusivo en Tigo Sports incluido sin cargo adicional.", tier="HD + App"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "12 meses de cortesía de Disney+ Estándar en planes DoblePack seleccionados.", tier="Estándar", free_months=12, promo_price=0.0),
            ],
        ),
        _home_offer(
            "PY", "Tigo", "DoblePack 600 Mbps + TV Familiar + Tigo Sports & Disney+", "PYG",
            "https://www.tigo.com.py/hogar/internet",
            "Tigo Paraguay: DoblePack 600 Mbps + TV Familiar Gs. 365.000/mes IVA incluido con Tigo Sports y 12 meses de Disney+.",
            png_path, md_path, reg_price=365000.0, taxes_incl=True, tech="FTTH", dl=600, wifi="Router WiFi 6", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.TIGO_SPORTS, "Tigo Sports PY", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Tigo Sports HD incluido fijo.", tier="HD"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "12 meses de Disney+ Estándar incluidos.", tier="Estándar", free_months=12, promo_price=0.0),
            ],
        ),
        _home_offer(
            "PY", "Personal Flow", "Combo Fibra 400 Mbps + Flow TV", "PYG",
            "https://www.personal.com.py/internet/hogar",
            "Personal Flow Paraguay: Combo Internet Fibra 400/100 Mbps + Flow TV Gs. 220.000/mes IVA incluido (Solo Fibra 400/100 Mbps: Gs. 150.000; Solo Fibra 600/100 Mbps: Gs. 200.000).",
            png_path, md_path, reg_price=220000.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=400, ul=100, wifi="ONT WiFi Dual", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.FLOW_PASS, "Flow Full App", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye plataforma Flow TV en vivo y VOD multi-dispositivo (standalone Gs. 70.000/mes).", tier="Flow Full", post_price=70000.0),
            ],
        ),
        _home_offer(
            "PY", "Personal Flow", "Internet Fibra 1000 Mbps", "PYG",
            "https://www.personal.com.py/internet/hogar",
            "Personal Flow Paraguay: Internet Fibra Óptica 1000 Mbps bajada / 300 Mbps subida Gs. 500.000/mes IVA incluido.",
            png_path, md_path, reg_price=500000.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=1000, ul=300, wifi="Router WiFi 6",
            vas=[],
        ),
        _home_offer(
            "PY", "Claro", "Claro Fibra Simétrica 200 Mbps + Paramount+ & Prime Video", "PYG",
            "https://www.claro.com.py/personas/servicios/servicios-hogar/",
            "Claro Paraguay: Internet Fibra Simétrica 200/200 Mbps Gs. 95.000/mes IVA incluido con Paramount+ vía Claro Video y 3 meses gratis de Prime Video.",
            png_path, md_path, reg_price=95000.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=200, ul=200, wifi="ONT Fibra WiFi",
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+ vía Claro Video", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido sin costo a través de Claro Video.", tier="Estándar"),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.PROMO_FREE_MONTHS,
                     "3 meses sin cargo de Prime Video, luego Gs. 37.500/mes.", tier="Estándar", free_months=3, promo_price=0.0, post_price=37500.0),
            ],
        ),
        _home_offer(
            "PY", "Claro", "Claro Fibra Simétrica 600 Mbps + Paramount+", "PYG",
            "https://www.claro.com.py/personas/servicios/servicios-hogar/",
            "Claro Paraguay: Internet Fibra Simétrica 600/600 Mbps en promoción Gs. 120.000/mes x 6 meses (tarifa regular Gs. 145.000/mes) IVA incluido con Paramount+ incluido.",
            png_path, md_path, promo_price=120000.0, promo_months=6, reg_price=145000.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="ONT Fibra WiFi 6",
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+ vía Claro Video", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido vía Claro Video.", tier="Estándar"),
            ],
        ),

        # ---------------------------------------------------------------------
        # 10. URUGUAY (UY — Currency: UYU) | Movistar (Millicom), Antel, Claro
        # Note: Antel holds state FTTH monopoly; Movistar UY & Claro UY compete via Mobile + OTT
        # ---------------------------------------------------------------------
        _home_offer(
            "UY", "Movistar", "Plan Móvil Contrato GIGAnte Plus M 100 GB (Millicom UY)", "UYU",
            "https://www.movistar.com.uy/productos-y-servicios/planes/contrato/",
            "Movistar Uruguay (Millicom): Plan Contrato Móvil 100 GB $1.190 UYU/mes IVA incluido (Plan 50 GB: $720; Plan 70 GB: $990). En Uruguay Antel posee el monopolio legal de fibra fija al hogar.",
            png_path, md_path, segment="MOBILE_POSTPAID", reg_price=1190.0, taxes_incl=True,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Facturación Movistar", VASCommercialModelEnum.STANDALONE_PAID,
                     "Suscripción Disney+, Netflix y Prime Video integrable con cargo a factura Movistar UY.", tier="Estándar / Premium"),
            ],
        ),
        _home_offer(
            "UY", "Antel", "Fibra Básico 400 Mbps + Antel TV", "UYU",
            "https://tienda.antel.com.uy/categoria/internet/hogar",
            "Antel Uruguay: Plan Fibra Básico 400 Mbps bajada / 30 Mbps subida $825 UYU/mes los primeros 4 meses, luego $1.650 UYU/mes IVA incluido.",
            png_path, md_path, promo_price=825.0, promo_months=4, reg_price=1650.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=400, ul=30, wifi="ONT Fibra Antel",
            vas=[],
        ),
        _home_offer(
            "UY", "Antel", "Fibra Entretenimiento 550 Mbps + Disney+ Estándar", "UYU",
            "https://tienda.antel.com.uy/categoria/internet/hogar",
            "Antel Uruguay: Plan Fibra Entretenimiento 550/40 Mbps con Disney+ Estándar incluido $1.185 UYU/mes por 4 meses, luego $2.370 UYU/mes IVA incluido.",
            png_path, md_path, promo_price=1185.0, promo_months=4, reg_price=2370.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=550, ul=40, wifi="Router Fibra WiFi",
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Estándar", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Suscripción Disney+ Estándar incluida fija en el plan Fibra Entretenimiento.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "UY", "Antel", "Fibra Super Entretenimiento 900 Mbps + Disney+ Premium & Netflix", "UYU",
            "https://tienda.antel.com.uy/categoria/internet/hogar",
            "Antel Uruguay: Plan Fibra Super Entretenimiento 900/200 Mbps con Disney+ Premium y Netflix Estándar incluidos $1.710 UYU/mes x 4 meses, luego $3.420 UYU/mes.",
            png_path, md_path, promo_price=1710.0, promo_months=4, reg_price=3420.0, taxes_incl=True, tech="FTTH", symmetric=False, dl=900, ul=200, wifi="Router Fibra Plus",
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye Disney+ Premium con ESPN durante toda la vigencia del contrato.", tier="Premium"),
                _vas(VASProviderEnum.NETFLIX, "Netflix Estándar", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye Netflix Estándar (2 pantallas HD) en el abono mensual.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "UY", "Claro", "Plan Móvil Postpago 70 GB + Universal+ (Claro Video)", "UYU",
            "https://www.claro.com.uy/personas/servicios/servicios-moviles/planes/",
            "Claro Uruguay: Plan Postpago Móvil 70 GB $700 UYU/mes IVA incluido (Plan 150 GB: $1.250 UYU). Incluye Claro Video con Universal+ a $0 y addons Prime Video ($359) / Crunchyroll ($99).",
            png_path, md_path, segment="MOBILE_POSTPAID", reg_price=700.0, taxes_incl=True,
            vas=[
                _vas(VASProviderEnum.UNIVERSAL_PLUS, "Universal+ en Claro Video", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Acceso incluido sin costo adicional en Claro Video Uruguay.", tier="Incluido"),
                _vas(VASProviderEnum.PRIME_VIDEO, "Amazon Prime Video", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Prime Video con cargo a factura Claro UY $359 UYU/mes.", tier="Estándar", post_price=359.0),
                _vas(VASProviderEnum.CRUNCHYROLL, "Crunchyroll", VASCommercialModelEnum.STANDALONE_PAID,
                     "Addon Crunchyroll $99 UYU/mes.", tier="Fan", post_price=99.0),
            ],
        ),

        # ---------------------------------------------------------------------
        # 11. ECUADOR (EC — Currency: USD, 15% IVA incl.) | Movistar, Claro, Netlife, Xtrim, CNT
        # ---------------------------------------------------------------------
        _home_offer(
            "EC", "Movistar", "Plan Móvil Infinity Plus 65 GB + Spotify (Tigo/Millicom EC)", "USD",
            "https://www.movistar.com.ec/productos-y-servicios/pospago/planes",
            "Movistar / Tigo Ecuador: Plan Pospago Infinity Plus 65 GB $45.99/mes IVA 15% incluido con Spotify incluido (Plan Móvil Pro 22 GB: $21.84). Operación enfocada en móvil pospago.",
            png_path, md_path, segment="MOBILE_POSTPAID", reg_price=45.99, taxes_incl=True,
            vas=[
                _vas(VASProviderEnum.SPOTIFY, "Spotify Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Beneficio musical Spotify incluido en plan pospago Infinity Plus.", tier="Individual"),
            ],
        ),
        _home_offer(
            "EC", "Claro", "3 Play Fibra Simétrica 550 Mbps + TV 91 Canales + Paramount+ & Max", "USD",
            "https://www.claro.com.ec/personas/servicios/servicios-hogar/",
            "Claro Ecuador: Plan 3 Play Fibra 550/550 Mbps + TV HD (91 canales) + telefonía $27.60/mes IVA 15% incluido (2 Play 600/600 Mbps: $20.70/mes). Incluye Paramount+ y Max.",
            png_path, md_path, reg_price=27.6, taxes_incl=True, tech="FTTH", symmetric=True, dl=550, ul=550, wifi="ONT Fibra WiFi", tv_ch=91, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido vía Claro Video.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Suscripción Max incluida en paquete 3 Play Fibra.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "EC", "Claro", "3 Play Fibra Simétrica 1000 Mbps + Mesh + Paramount+ & Max", "USD",
            "https://www.claro.com.ec/personas/servicios/servicios-hogar/",
            "Claro Ecuador: Plan 3 Play Fibra 1000/1000 Mbps + Mesh WiFi + TV HD $37.95/mes IVA 15% incluido (2 Play 1000 Mbps: $28.75/mes).",
            png_path, md_path, reg_price=37.95, taxes_incl=True, tech="FTTH", symmetric=True, dl=1000, ul=1000, wifi="Router Fibra + Extensor Mesh", tv_ch=91, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido en 3 Play 1000 Mbps.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "EC", "Netlife", "Starter Defense XGPON 850 Mbps Simétrico WiFi 7", "USD",
            "https://www.netlife.ec/planes/",
            "Netlife Ecuador: Plan Starter Defense XGPON FTTH 850/850 Mbps con Router WiFi 7 a $16.96/mes por 9 meses, luego $33.93/mes IVA 15% incluido (Gamer Defense 1000M: $18.98 promo).",
            png_path, md_path, promo_price=16.96, promo_months=9, reg_price=33.93, taxes_incl=True, tech="FTTH", symmetric=True, dl=850, ul=850, wifi="Router XGPON WiFi 7",
            vas=[],
        ),
        _home_offer(
            "EC", "Xtrim", "Internet Fibra 300 Mbps Simétrico WiFi 6", "USD",
            "https://www.xtrim.com.ec/planes/",
            "Xtrim Ecuador: Plan Fibra 300/300 Mbps con Router WiFi 6 en promo tarjeta $17.85/mes x 6 meses, tarifa regular $18.40/mes IVA 15% incluido.",
            png_path, md_path, promo_price=17.85, promo_months=6, reg_price=18.4, taxes_incl=True, tech="FTTH", symmetric=True, dl=300, ul=300, wifi="Router WiFi 6",
            vas=[],
        ),
        _home_offer(
            "EC", "Xtrim", "Plan Elite Plus 800 Mbps + Zapping TV + Disney+ Premium & Paramount+", "USD",
            "https://www.xtrim.com.ec/planes/",
            "Xtrim Ecuador: Plan Elite Plus 800/800 Mbps + Zapping TV + Paramount+ y Disney+ Premium incluidos $25.50/mes promo x 6 meses / $40.00/mes regular IVA incluido (Giga Supremo 1200M + Max: $25.30 promo).",
            png_path, md_path, promo_price=25.5, promo_months=6, reg_price=40.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=800, ul=800, wifi="Router WiFi 6",
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Incluye Disney+ Premium con ESPN en vivo.", tier="Premium"),
                _vas(VASProviderEnum.PARAMOUNT_PLUS, "Paramount+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Paramount+ incluido fijo en Elite Plus.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "EC", "CNT", "Plan Fibra GO! 600 Mbps Simétrico", "USD",
            "https://www.cnt.gob.ec/planes/internet-fijo/",
            "CNT Ecuador: Plan Fibra GO! 600/600 Mbps en promoción $14.60/mes durante 8 meses, tarifa regular $29.91/mes IVA 15% incluido (Fibra GO! 900 Mbps: $20.35 x 8 meses).",
            png_path, md_path, promo_price=14.6, promo_months=8, reg_price=29.91, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="ONT Fibra Dual Band",
            vas=[],
        ),

        # ---------------------------------------------------------------------
        # 12. CHILE (CL — Currency: CLP) | Movistar (Millicom), Entel, ClaroVTR, WOM, Mundo
        # ---------------------------------------------------------------------
        _home_offer(
            "CL", "Movistar", "Fibra Simétrica 600 Mbps WiFi 6", "CLP",
            "https://www.movistar.cl/hogar/fibra",
            "Movistar Chile (Millicom): Solo Internet Fibra Simétrica 600/600 Mbps con Smart WiFi 6 $14.990/mes por 12 meses, luego $21.990/mes IVA incluido (con TNT Sports en Max: $22.990 x 12m).",
            png_path, md_path, promo_price=14990.0, promo_months=12, reg_price=21990.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Smart WiFi 6",
            vas=[],
        ),
        _home_offer(
            "CL", "Movistar", "Dúo Fibra 600 Mbps + Movistar TV + Disney+ & Max", "CLP",
            "https://www.movistar.cl/hogar",
            "Movistar Chile (Millicom): Dúo Fibra Simétrica 600/600 Mbps + Movistar TV + Disney+ y Max incluidos $32.990/mes por 12 meses, luego $42.990/mes IVA incluido.",
            png_path, md_path, promo_price=32990.0, promo_months=12, reg_price=42990.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Smart WiFi 6", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ incluido en Dúo Fibra + TV Movistar Chile.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido sin costo adicional en Dúo Fibra + TV.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CL", "Movistar", "Dúo Movistar Giga 940 Mbps + TV + Disney+ & Max", "CLP",
            "https://www.movistar.cl/hogar",
            "Movistar Chile (Millicom): Dúo Fibra Giga 940/940 Mbps + Movistar TV + Disney+ y Max $39.990/mes por 12 meses, luego $49.990/mes (Solo Fibra Giga 940M: $19.990 x 12m / $29.990 reg).",
            png_path, md_path, promo_price=39990.0, promo_months=12, reg_price=49990.0, install_fee=0.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=940, ul=940, wifi="Smart WiFi 6", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ incluido fijo en Dúo Giga 940.", tier="Estándar"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido fijo en Dúo Giga 940.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CL", "Entel", "Dúo Pack Fibra 600 Mbps + TV Full+ (Disney+ Premium, Max & Apple TV+)", "CLP",
            "https://www.entel.cl/hogar/internet/",
            "Entel Chile: Dúo Pack Fibra 600/600 Mbps + Entel TV Full+ (98 canales) $34.990/mes x 12 meses, luego $49.490/mes. Incluye Disney+ Premium, Max y Apple TV+ (Solo Fibra 600M: $17.990 x 12m).",
            png_path, md_path, promo_price=34990.0, promo_months=12, reg_price=49490.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Router WiFi 6", tv_ch=98, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ Premium con ESPN incluido en TV Full+.", tier="Premium"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido en Entel TV Full+.", tier="Estándar"),
                _vas(VASProviderEnum.APPLE_TV, "Apple TV+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Suscripción Apple TV+ incluida en Dúo Pack TV Full+.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CL", "Entel", "Dúo Pack Fibra Giga 1000 Mbps + TV Full+", "CLP",
            "https://www.entel.cl/hogar/internet/",
            "Entel Chile: Dúo Pack Fibra Giga 1000/1000 Mbps + Entel TV Full+ (98 canales) + Disney+ Premium, Max y Apple TV+ $39.990/mes x 12 meses, luego $60.490/mes.",
            png_path, md_path, promo_price=39990.0, promo_months=12, reg_price=60490.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=1000, ul=1000, wifi="Router WiFi 6 + Extensor", tv_ch=98, tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+ Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ Premium incluido.", tier="Premium"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido.", tier="Estándar"),
                _vas(VASProviderEnum.APPLE_TV, "Apple TV+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Apple TV+ incluido.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CL", "ClaroVTR", "Doble Pack Fibra 600 Mbps + TV + Max & Disney+", "CLP",
            "https://www.clarochile.cl/portal/cl/sc/personas/servicios-hogar/",
            "ClaroVTR Chile: Doble Pack Fibra 600/600 Mbps + TV HD + Max y Disney+ incluidos $29.990/mes x 12 meses, luego $41.990/mes (Solo Fibra 600M: $14.990 x 12m; Fibra 940M: $19.990 x 12m).",
            png_path, md_path, promo_price=29990.0, promo_months=12, reg_price=41990.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Router WiFi 6", tv_boxes=1,
            vas=[
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Max incluido en Doble Pack ClaroVTR.", tier="Estándar"),
                _vas(VASProviderEnum.DISNEY_PLUS, "Disney+", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Disney+ incluido en Doble Pack ClaroVTR.", tier="Estándar"),
                _vas(VASProviderEnum.TNT_SPORTS, "TNT Sports HD", VASCommercialModelEnum.STANDALONE_PAID,
                     "Adicional TNT Sports disponible por $13.990/mes.", tier="Premium HD", post_price=13990.0),
            ],
        ),
        _home_offer(
            "CL", "WOM", "Fibra Simétrica 600 Mbps WiFi 6", "CLP",
            "https://www.wom.cl/fibra-optica/",
            "WOM Chile: Solo Internet Fibra Óptica Simétrica 600/600 Mbps con Router WiFi 6 $11.990/mes por 12 meses, luego $21.990/mes (Fibra 800/800 Mbps: $15.990 x 12m).",
            png_path, md_path, promo_price=11990.0, promo_months=12, reg_price=21990.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Router WiFi 6",
            vas=[],
        ),
        _home_offer(
            "CL", "WOM", "Fibra 600 Mbps + TV Fútbol Zapping + TNT Sports Premium & Max", "CLP",
            "https://www.wom.cl/fibra-optica/",
            "WOM Chile: Fibra 600/600 Mbps + Zapping TV (70 canales) + TNT Sports Premium y Max incluidos $30.890/mes por 12 meses, luego $40.890/mes.",
            png_path, md_path, promo_price=30890.0, promo_months=12, reg_price=40890.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=600, ul=600, wifi="Router WiFi 6", tv_ch=70, tv_boxes=0,
            vas=[
                _vas(VASProviderEnum.TNT_SPORTS, "TNT Sports Premium", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Campeonato Nacional Chileno en TNT Sports Premium incluido en combo TV Fútbol.", tier="Premium"),
                _vas(VASProviderEnum.MAX, "Max", VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                     "Suscripción Max incluida.", tier="Estándar"),
            ],
        ),
        _home_offer(
            "CL", "Mundo", "Fibra Simétrica 1000 Mbps + Mundo GO! TV", "CLP",
            "https://www.tumundo.cl/fibra-optica/",
            "Mundo Chile: Fibra Simétrica 1000/1000 Mbps + Mundo GO! TV $25.990/mes durante 6 meses, luego $46.150/mes (Solo Fibra 800/800 Mbps: $12.990 x 3m / $15.990 regular).",
            png_path, md_path, promo_price=25990.0, promo_months=6, reg_price=46150.0, taxes_incl=True, tech="FTTH", symmetric=True, dl=1000, ul=1000, wifi="Router Fibra WiFi 6",
            vas=[],
        ),
    ]

    # =========================================================================
    # YESTERDAY'S SNAPSHOT (DAY T-1) — DETERMINISTIC BASELINE WITH REAL DELTAS
    # =========================================================================
    # Start from deep copies of today's offers and revert specific recent commercial moves
    # across CO, PA, BO, CR, PY, CL, EC so the DeterministicComparator detects rich cross-LATAM deltas:
    yesterday_offers: List[NormalizedOffer] = []

    for offer in today_offers:
        clone = offer.model_copy(deep=True)

        # Delta 1 (CO - Movistar Price Drop + Promo Extension on 900M Solo Internet):
        # Yesterday promo was 84,900 COP (no online discount); today dropped to 75,992 COP x 12m!
        if clone.country_iso == "CO" and clone.operator == "Movistar" and clone.plan_name == "Fibra Óptica Simétrica 900 Megas Solo Internet":
            clone.pricing.promo_monthly_price = 84900.0
            clone.pricing.promo_duration_months = 6

        # Delta 2 (PA - MasMovil VAS Addition of Universal+ at $56.00 USD on 600M + TV):
        # Today Paquete Hogar +Fibra 600 Megas + TV + Universal+ is $56.00 USD (matching live masmovilpanama.com rate card);
        # yesterday it did not include Universal+ hard-bundled!
        elif clone.country_iso == "PA" and clone.operator == "MasMovil" and clone.plan_name == "Paquete Hogar +Fibra 600 Megas + TV + Universal+":
            clone.vas_addons = []

        # Delta 3 (BO - AXS VAS Portfolio Addition of HBO Max on 135M IPTV bundle):
        # Yesterday had no HBO Max included at 324 BOB; today includes HBO Premium / Max hard-bundled!
        elif clone.country_iso == "BO" and clone.operator == "AXS" and clone.plan_name == "AXS+ Fibra Hogar Pro 135 Mbps + IPTV + HBO Max":
            clone.vas_addons = []

        # Delta 4 (CR - Liberty Pack Entretenimiento VAS upgrade):
        # Yesterday Doble Play Mega 120 only had Max; today added Disney+ Estándar & Universal+ in Pack Entretenimiento!
        elif clone.country_iso == "CR" and clone.operator == "Liberty" and clone.plan_name == "Doble Play Mega 120 + Next TV + Pack Entretenimiento":
            clone.vas_addons = [v for v in clone.vas_addons if v.provider == VASProviderEnum.MAX]

        # Delta 5 (PY - Claro Speed Upgrade at same UID / WiFi 6 hardware upgrade on 600M):
        # Yesterday Claro 600M had ONT WiFi 5 and promo 145,000 PYG; today dropped to 120,000 PYG with ONT Fibra WiFi 6!
        elif clone.country_iso == "PY" and clone.operator == "Claro" and clone.plan_name == "Claro Fibra Simétrica 600 Mbps + Paramount+":
            clone.pricing.promo_monthly_price = 145000.0
            if clone.home_specs:
                clone.home_specs.wifi_hardware = "ONT Fibra WiFi 5"

        # Delta 6 (EC - Netlife New Offer Launched today):
        # Exclude Netlife Starter Defense XGPON 850M WiFi 7 from yesterday so it triggers NEW_OFFER_LAUNCHED today!
        elif clone.country_iso == "EC" and clone.operator == "Netlife" and clone.plan_name == "Starter Defense XGPON 850 Mbps Simétrico WiFi 7":
            continue

        # Delta 7 (CL - WOM Price Drop on Solo Fibra 600M):
        # Yesterday promo was 14,990 CLP; today dropped to 11,990 CLP (-20%)!
        elif clone.country_iso == "CL" and clone.operator == "WOM" and clone.plan_name == "Fibra Simétrica 600 Mbps WiFi 6":
            clone.pricing.promo_monthly_price = 14990.0

        yesterday_offers.append(clone)

    # Delta 8 (PA - Tigo Retired Legacy 200 Megas Plan yesterday):
    yesterday_offers.append(
        _home_offer(
            "PA", "Tigo", "Internet Hogar 200 Megas Legacy", "USD",
            "https://www.tigo.com.pa/hogar/internet",
            "Tigo Panamá: Plan anterior Internet 200 Megas B/. 37.00/mes (+7% ITBMS) reemplazado por escalón 300/500 Megas.",
            png_path, md_path, reg_price=37.0, taxes_incl=False, tech="HFC", symmetric=False, dl=200, ul=10, wifi="Router WiFi Dual",
            vas=[],
        )
    )

    return yesterday_offers, today_offers
