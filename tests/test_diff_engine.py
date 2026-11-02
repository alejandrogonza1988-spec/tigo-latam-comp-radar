"""Pytest suite validating deterministic diffs (price drops, speed upgrades, VAS changes), guardrails, and HTML report generation."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import PROJECT_ROOT, RadarSettings
from src.diff_engine.comparator import DeltaTypeEnum, DeterministicComparator
from src.extractor.dom_cleaner import DOMCleaner
from src.extractor.schemas import (
    EntertainmentVASAddon,
    HomeTechnicalSpec,
    NormalizedOffer,
    PricingSpec,
    VASCommercialModelEnum,
    VASProviderEnum,
)
from src.reporting.report_builder import ReportBuilder
from src.storage.repository import RadarRepository


def test_colombia_competitor_500mbps_price_drop_and_max_3_free_months_and_html_report(
    tmp_path: Path,
) -> None:
    """
    End-to-end simulation:
    - Tigo Colombia holds its 500 Mbps Home Bundle steady between Day T-1 and Day T.
    - Claro Colombia (competitor in Bogotá Estrato 3) drops its 500 Mbps Fiber promo price
      from 109,900 COP to 89,900 COP (-20,000 COP / -18.20%) AND adds 3 free months of Max.
    - Persists snapshots in SQLite, runs DeterministicComparator, verifies exact deltas,
      and generates `daily_radar_test.html` without errors.
    """
    db_file = tmp_path / "test_radar.db"
    repo = RadarRepository(database_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    day_t_minus_1 = date(2026, 11, 1)
    day_t = date(2026, 11, 2)

    tigo_co_500 = NormalizedOffer(
        country_iso="CO",
        operator="Tigo",
        segment="HOME_BUNDLES",
        plan_name="Dúo Fibra 500 Megas + TV Avanzada",
        pricing=PricingSpec(
            currency="COP",
            regular_monthly_price=134900.0,
            promo_monthly_price=109900.0,
            promo_duration_months=6,
            installation_fee=0.0,
            taxes_included=True,
        ),
        home_specs=HomeTechnicalSpec(
            technology="FTTH",
            symmetric_speed=True,
            download_mbps=500,
            upload_mbps=500,
            wifi_hardware="WiFi 6 Dual Band",
            tv_channels_count=135,
            tv_deco_boxes=1,
        ),
        vas_addons=[
            EntertainmentVASAddon(
                provider=VASProviderEnum.PRIME_VIDEO,
                raw_provider_name="Amazon Prime Video",
                tier_or_package="Estándar",
                commercial_model=VASCommercialModelEnum.PROMO_FREE_MONTHS,
                free_months=3,
                promo_price=0.0,
                regular_price_after_promo=22900.0,
                exact_terms_text="Incluye 3 meses sin costo de Amazon Prime Video; luego $22.900/mes IVA incluido.",
            )
        ],
        exact_terms_text="Bogotá Estrato 3: Plan Dúo 500 Mbps $109.900/mes x 6 meses, luego $134.900/mes IVA incluido.",
        source_url="https://www.tigo.com.co/hogar",
        screenshot_path="data/audit_trail/2026-11-02/CO/tigo/home_bundles_sample.png",
        markdown_path="data/audit_trail/2026-11-02/CO/tigo/home_bundles_sample.md",
    )

    claro_co_500_yesterday = NormalizedOffer(
        country_iso="CO",
        operator="Claro",
        segment="HOME_BUNDLES",
        plan_name="Internet Fibra 500 Mbps Hogar",
        pricing=PricingSpec(
            currency="COP",
            regular_monthly_price=129900.0,
            promo_monthly_price=109900.0,
            promo_duration_months=6,
            installation_fee=0.0,
            taxes_included=True,
        ),
        home_specs=HomeTechnicalSpec(
            technology="FTTH",
            symmetric_speed=True,
            download_mbps=500,
            upload_mbps=500,
            wifi_hardware="Router WiFi 6",
        ),
        vas_addons=[],
        exact_terms_text="Bogotá Estrato 3: Internet Fibra 500 Mbps simétricos $109.900/mes por 6 meses, tarifa regular $129.900 IVA incluido.",
        source_url="https://www.claro.com.co/personas/servicios/servicios-hogar/",
        screenshot_path="data/audit_trail/2026-11-01/CO/claro/home_bundles_sample.png",
        markdown_path="data/audit_trail/2026-11-01/CO/claro/home_bundles_sample.md",
    )

    # Persist Day T-1 snapshots in SQLite
    run_y_id = repo.create_scrape_run(run_date=day_t_minus_1, countries_filter="CO")
    repo.save_offer_snapshots(
        scrape_run_id=run_y_id,
        snapshot_date=day_t_minus_1,
        offers=[tigo_co_500, claro_co_500_yesterday],
    )
    repo.complete_scrape_run(
        scrape_run_id=run_y_id,
        status="SUCCESS",
        total_urls_scraped=2,
        total_offers_extracted=2,
        total_deltas_detected=0,
    )

    # Day T: Competitor Claro drops 500 Mbps promo price to 89,900 COP and adds 3 free months of Max
    claro_co_500_today = NormalizedOffer(
        country_iso="CO",
        operator="Claro",
        segment="HOME_BUNDLES",
        plan_name="Internet Fibra 500 Mbps Hogar",
        pricing=PricingSpec(
            currency="COP",
            regular_monthly_price=129900.0,
            promo_monthly_price=89900.0,
            promo_duration_months=6,
            installation_fee=0.0,
            taxes_included=True,
        ),
        home_specs=HomeTechnicalSpec(
            technology="FTTH",
            symmetric_speed=True,
            download_mbps=500,
            upload_mbps=500,
            wifi_hardware="Router WiFi 6",
        ),
        vas_addons=[
            EntertainmentVASAddon(
                provider=VASProviderEnum.MAX,
                raw_provider_name="Max Estándar",
                tier_or_package="Plan Estándar",
                commercial_model=VASCommercialModelEnum.PROMO_FREE_MONTHS,
                free_months=3,
                promo_price=0.0,
                regular_price_after_promo=24900.0,
                exact_terms_text="Nuevo beneficio: Incluye 3 meses gratis de Max Estándar ($0); desde el mes 4 $24.900/mes IVA incluido.",
            )
        ],
        exact_terms_text="Bogotá Estrato 3: Internet Fibra 500 Mbps simétricos $89.900/mes por 6 meses (tarifa plena $129.900) + 3 meses gratis de Max.",
        source_url="https://www.claro.com.co/personas/servicios/servicios-hogar/",
        screenshot_path="data/audit_trail/2026-11-02/CO/claro/home_bundles_sample.png",
        markdown_path="data/audit_trail/2026-11-02/CO/claro/home_bundles_sample.md",
    )

    today_offers = [tigo_co_500, claro_co_500_today]
    run_t_id = repo.create_scrape_run(run_date=day_t, countries_filter="CO")
    repo.save_offer_snapshots(scrape_run_id=run_t_id, snapshot_date=day_t, offers=today_offers)

    # Fetch historical Day T-1 baseline deterministically from SQLite
    baseline_offers, baseline_dates = repo.get_baseline_offers_for_today_batch(
        today_offers=today_offers,
        run_date=day_t,
    )
    assert len(baseline_offers) == 2
    assert baseline_dates[("CO", "Claro", "HOME_BUNDLES")] == day_t_minus_1

    comparator = DeterministicComparator()
    deltas = comparator.compare_snapshots(yesterday_offers=baseline_offers, today_offers=today_offers)
    repo.save_daily_deltas(
        scrape_run_id=run_t_id,
        delta_date=day_t,
        deltas=deltas,
        baseline_dates=baseline_dates,
    )
    repo.complete_scrape_run(
        scrape_run_id=run_t_id,
        status="SUCCESS",
        total_urls_scraped=2,
        total_offers_extracted=2,
        total_deltas_detected=len(deltas),
    )

    # Verify exact deterministic deltas: 1 PRICE_CHANGE (drop) + 1 VAS_PORTFOLIO_CHANGE (Max 3m free)
    assert len(deltas) == 2
    deltas_by_type = {d.delta_type: d for d in deltas}
    assert DeltaTypeEnum.PRICE_CHANGE in deltas_by_type
    assert DeltaTypeEnum.VAS_PORTFOLIO_CHANGE in deltas_by_type

    price_delta = deltas_by_type[DeltaTypeEnum.PRICE_CHANGE]
    assert price_delta.operator == "Claro"
    assert price_delta.country_iso == "CO"
    assert price_delta.direction == "PRICE_DROP"
    assert price_delta.numeric_diff == -20000.0
    assert price_delta.percentage_diff == -18.2

    vas_delta = deltas_by_type[DeltaTypeEnum.VAS_PORTFOLIO_CHANGE]
    assert vas_delta.operator == "Claro"
    assert vas_delta.direction == "VAS_ADDED"
    assert vas_delta.vas_providers_affected == ["MAX"]
    assert vas_delta.field_changes[0].new_value["free_months"] == 3

    # Build sample `daily_radar_test.html` dashboard in both tmp_path and project data/reports/
    settings = RadarSettings()
    catalog = settings.load_markets_catalog()

    for target_reports_dir in (tmp_path, PROJECT_ROOT / "data" / "reports"):
        builder = ReportBuilder(reports_dir=target_reports_dir, markets_catalog=catalog)
        artifacts = builder.build_dashboard(
            offers=today_offers,
            deltas=deltas,
            report_date=day_t,
            output_filename="daily_radar_test.html",
            export_csv_files=True,
        )
        assert artifacts.html_path.exists()
        assert artifacts.offers_csv_path is not None and artifacts.offers_csv_path.exists()
        assert artifacts.deltas_csv_path is not None and artifacts.deltas_csv_path.exists()

        html_text = artifacts.html_path.read_text(encoding="utf-8")
        assert "tailwindcss" in html_text
        assert "--tigo-navy: #001E60;" in html_text
        assert "--tigo-yellow: #FFCB05;" in html_text
        assert "Ver Evidencia" in html_text
        assert "Ver Ofertas con Addons Filtradas" in html_text
        assert "Comparativa Ofertas Hoy: Tigo Hogar vs Competencia" in html_text
        assert "Exportar Vista a CSV / Excel" in html_text

        # Guarantee zero unescaped literal newlines inside JS string literals
        inline_scripts = re.findall(
            r"<script(?![^>]*src=)(?![^>]*application/json)[^>]*>(.*?)</script>",
            html_text,
            re.DOTALL,
        )
        assert len(inline_scripts) == 1
        assert 'join("\n")' not in inline_scripts[0]
        assert 'join("\r\n")' not in inline_scripts[0]

        match = re.search(
            r'<script id="radar-payload" type="application/json">(.*?)</script>',
            html_text,
            re.DOTALL,
        )
        assert match is not None
        embedded_payload = json.loads(match.group(1).replace("<\\/", "</"))
        assert embedded_payload["kpis"]["total_offers_tracked"] == 2
        assert embedded_payload["kpis"]["offers_with_addons"] == 2
        assert embedded_payload["kpis"]["total_changes_detected"] == 2
        assert embedded_payload["kpis"]["price_drops"] == 1
        assert embedded_payload["kpis"]["vas_addon_changes"] == 1
        assert len(embedded_payload["markets"]) == 12

        # Verify deterministic head-to-head Tigo Hogar vs Competitor gap calculation in JSON payload
        claro_offer_payload = next(o for o in embedded_payload["offers"] if o["operator"] == "Claro")
        assert claro_offer_payload["tigo_comparison"] is not None
        assert claro_offer_payload["tigo_comparison"]["tigo_operator"] == "Tigo"
        assert claro_offer_payload["tigo_comparison"]["effective_price_diff"] == -20000.0
        assert claro_offer_payload["tigo_comparison"]["extra_vas_vs_tigo"] == ["MAX"]


def test_speed_and_wifi_hardware_upgrade_detection() -> None:
    """Validate SPEED_OR_HARDWARE_CHANGE when an operator upgrades Mbps and WiFi router hardware."""
    yesterday = [
        NormalizedOffer(
            country_iso="CR",
            operator="Liberty",
            segment="HOME_BUNDLES",
            plan_name="Plan Hogar Fibra Ultra",
            pricing=PricingSpec(currency="CRC", regular_monthly_price=29900.0),
            home_specs=HomeTechnicalSpec(
                technology="FTTH",
                symmetric_speed=False,
                download_mbps=300,
                upload_mbps=150,
                wifi_hardware="Router WiFi 5",
            ),
            vas_addons=[],
        )
    ]
    today = [
        NormalizedOffer(
            country_iso="CR",
            operator="Liberty",
            segment="HOME_BUNDLES",
            plan_name="Plan Hogar Fibra Ultra",
            pricing=PricingSpec(currency="CRC", regular_monthly_price=29900.0),
            home_specs=HomeTechnicalSpec(
                technology="FTTH",
                symmetric_speed=True,
                download_mbps=600,
                upload_mbps=600,
                wifi_hardware="WiFi 6 + 1 Extensor Mesh",
            ),
            vas_addons=[],
        )
    ]

    deltas = DeterministicComparator().compare_snapshots(yesterday, today)
    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.delta_type == DeltaTypeEnum.SPEED_OR_HARDWARE_CHANGE
    assert delta.direction == "SPEED_UPGRADE"
    assert delta.numeric_diff == 300.0
    assert delta.percentage_diff == 100.0
    changed_fields = {fc.field_name for fc in delta.field_changes}
    assert changed_fields == {"download_mbps", "upload_mbps", "wifi_hardware"}


def test_vas_addon_modification_and_removal() -> None:
    """Validate VAS_PORTFOLIO_CHANGE when free months/tier change and another OTT provider is removed."""
    yesterday = [
        NormalizedOffer(
            country_iso="CL",
            operator="Movistar",
            segment="HOME_BUNDLES",
            plan_name="Dúo Fibra 800 Mbps + TV",
            pricing=PricingSpec(currency="CLP", regular_monthly_price=36990.0),
            home_specs=HomeTechnicalSpec(technology="FTTH", download_mbps=800, upload_mbps=800),
            vas_addons=[
                EntertainmentVASAddon(
                    provider=VASProviderEnum.DISNEY_PLUS,
                    raw_provider_name="Disney+ Premium",
                    tier_or_package="Disney+ Premium",
                    commercial_model=VASCommercialModelEnum.PROMO_FREE_MONTHS,
                    free_months=6,
                    promo_price=0.0,
                    regular_price_after_promo=13500.0,
                    exact_terms_text="6 meses sin costo Disney+ Premium.",
                ),
                EntertainmentVASAddon(
                    provider=VASProviderEnum.TNT_SPORTS,
                    raw_provider_name="TNT Sports HD",
                    commercial_model=VASCommercialModelEnum.INCLUDED_HARD_BUNDLE,
                    exact_terms_text="TNT Sports HD incluido.",
                ),
            ],
        )
    ]
    today = [
        NormalizedOffer(
            country_iso="CL",
            operator="Movistar",
            segment="HOME_BUNDLES",
            plan_name="Dúo Fibra 800 Mbps + TV",
            pricing=PricingSpec(currency="CLP", regular_monthly_price=36990.0),
            home_specs=HomeTechnicalSpec(technology="FTTH", download_mbps=800, upload_mbps=800),
            vas_addons=[
                EntertainmentVASAddon(
                    provider=VASProviderEnum.DISNEY_PLUS,
                    raw_provider_name="Disney+ Estándar",
                    tier_or_package="Disney+ Estándar con anuncios",
                    commercial_model=VASCommercialModelEnum.PROMO_FREE_MONTHS,
                    free_months=3,
                    promo_price=0.0,
                    regular_price_after_promo=9900.0,
                    exact_terms_text="3 meses sin costo Disney+ Estándar con anuncios.",
                )
            ],
        )
    ]

    deltas = DeterministicComparator().compare_snapshots(yesterday, today)
    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.delta_type == DeltaTypeEnum.VAS_PORTFOLIO_CHANGE
    assert delta.direction == "VAS_MODIFIED"
    assert set(delta.vas_providers_affected) == {"DISNEY_PLUS", "TNT_SPORTS"}


def test_new_offer_launched_and_offer_retired() -> None:
    """Validate NEW_OFFER_LAUNCHED and OFFER_RETIRED classification."""
    yesterday = [
        NormalizedOffer(
            country_iso="PY",
            operator="Personal Flow",
            segment="HOME_BUNDLES",
            plan_name="Internet Fibra 150 Mbps",
            pricing=PricingSpec(currency="PYG", regular_monthly_price=160000.0),
            home_specs=HomeTechnicalSpec(technology="FTTH", download_mbps=150),
        )
    ]
    today = [
        NormalizedOffer(
            country_iso="PY",
            operator="Personal Flow",
            segment="HOME_BUNDLES",
            plan_name="Internet Fibra 1000 Mbps Gamer",
            pricing=PricingSpec(currency="PYG", regular_monthly_price=290000.0),
            home_specs=HomeTechnicalSpec(technology="FTTH", download_mbps=1000),
        )
    ]

    deltas = DeterministicComparator().compare_snapshots(yesterday, today)
    types = {d.delta_type for d in deltas}
    assert types == {DeltaTypeEnum.NEW_OFFER_LAUNCHED, DeltaTypeEnum.OFFER_RETIRED}


def test_guardrails_zero_temp_12_markets_catalog_and_dom_cleaner() -> None:
    """Verify temperature=0.0 enforcement, 12-market YAML completeness, null preservation, and DOMCleaner."""
    with pytest.raises(ValidationError):
        RadarSettings(gemini_temperature=0.3)

    settings = RadarSettings()
    catalog = settings.load_markets_catalog()
    expected_12_isos = {"GT", "SV", "HN", "NI", "CR", "PA", "CO", "BO", "PY", "UY", "EC", "CL"}
    assert set(catalog["markets"].keys()) == expected_12_isos

    # Verify Colombia operators include Bogotá + Estrato 3 pre-scrape playbook
    co_operators = catalog["markets"]["CO"]["operators"]
    assert {op["name"] for op in co_operators} == {"Tigo", "Movistar", "Claro", "WOM", "ETB"}
    tigo_co_actions = co_operators[0]["pre_scrape_actions"]
    assert any(
        a.get("action") == "select_colombia_city_stratum"
        and a.get("city") == "Bogotá"
        and a.get("stratum") == "Estrato 3"
        for a in tigo_co_actions
    )

    # Verify missing prices/speeds remain strictly None (never 0)
    sparse_offer = NormalizedOffer(
        country_iso="BO",
        operator="Entel",
        segment="MOBILE_POSTPAID",
        plan_name="Plan Pospago Ilimitado",
        pricing=PricingSpec(currency="BOB"),
    )
    assert sparse_offer.pricing.regular_monthly_price is None
    assert sparse_offer.pricing.promo_monthly_price is None
    assert sparse_offer.pricing.taxes_included is None
    assert sparse_offer.home_specs is None

    # Verify DOMCleaner strips scripts/SVGs/nav/footer while surfacing hidden modal VAS terms
    sample_html = """
    <html>
      <body>
        <nav>Menu Superior Ignorado</nav>
        <script>window.secretTracker = 123;</script>
        <svg><path d="M0 0"/></svg>
        <div class="plan-card">
          <h2>Fibra 500 Mbps</h2>
          <p>$89.900 / mes</p>
          <img alt="Max Estándar 3 meses sin costo" src="/max.png" />
        </div>
        <div class="modal-tyc hidden" aria-hidden="true">
          Promoción válida en Bogotá Estrato 3: tarifa plena después del mes 6 es $129.900 IVA incluido.
        </div>
        <footer>Copyright Footer Ignorado</footer>
      </body>
    </html>
    """
    cleaned = DOMCleaner().clean_html_to_markdown(sample_html)
    assert "secretTracker" not in cleaned.markdown_text
    assert "Menu Superior Ignorado" not in cleaned.markdown_text
    assert "Copyright Footer Ignorado" not in cleaned.markdown_text
    assert "[IMG_ALT: Max Estándar 3 meses sin costo]" in cleaned.markdown_text
    assert "Bogotá Estrato 3: tarifa plena después del mes 6 es $129.900 IVA incluido." in cleaned.markdown_text


def test_gemini_parser_enforces_zero_temperature_and_response_schema() -> None:
    """Verify GeminiOfferParser calls `client.models.generate_content` with `gemini-2.5-flash`, `temperature=0.0`, and `response_schema`."""
    from src.browser.dom_actions import DEFAULT_ACCORDION_PATTERN
    from src.extractor.gemini_parser import GeminiOfferParser
    from src.extractor.schemas import LLMExtractedOfferItem, LLMExtractionEnvelope

    # Validate mandatory Playwright accordion regex matches all required Spanish triggers
    accordion_re = re.compile(DEFAULT_ACCORDION_PATTERN, re.IGNORECASE)
    for phrase in ("Ver detalle", "Más info", "Términos y condiciones", "Qué incluye", "Beneficios"):
        assert accordion_re.search(phrase) is not None

    captured_call: dict = {}

    class _FakeModelsAPI:
        def generate_content(self, *, model: str, contents: str, config: object) -> object:
            captured_call["model"] = model
            captured_call["contents"] = contents
            captured_call["config"] = config

            class _Resp:
                parsed = LLMExtractionEnvelope(
                    offers=[
                        LLMExtractedOfferItem(
                            plan_name="Fibra 500 Mbps",
                            pricing=PricingSpec(
                                currency="COP",
                                promo_monthly_price=89900.0,
                                regular_monthly_price=129900.0,
                                promo_duration_months=6,
                                taxes_included=True,
                            ),
                            home_specs=HomeTechnicalSpec(
                                technology="FTTH",
                                symmetric_speed=True,
                                download_mbps=500,
                                upload_mbps=500,
                            ),
                            vas_addons=[],
                            exact_terms_text="Fibra 500 Mbps $89.900 x 6 meses IVA incluido.",
                        )
                    ]
                )
                text = ""

            return _Resp()

    class _FakeGenAIClient:
        def __init__(self) -> None:
            self.models = _FakeModelsAPI()

    settings = RadarSettings(gemini_api_key="test-key-not-used-over-network")
    parser = GeminiOfferParser(settings=settings, client=_FakeGenAIClient())  # type: ignore[arg-type]

    offers = parser.extract_offers_sync(
        markdown_text="## Fibra 500 Mbps\n- $89.900 x 6 meses, tarifa regular $129.900 IVA incluido.",
        country_iso="CO",
        country_name="Colombia",
        operator="Claro",
        segment="HOME_BUNDLES",
        expected_currency="COP",
        source_url="https://www.claro.com.co/personas/servicios/servicios-hogar/",
    )

    assert captured_call["model"] == "gemini-2.5-flash"
    assert captured_call["config"].temperature == 0.0
    assert captured_call["config"].response_mime_type == "application/json"
    assert captured_call["config"].response_schema is LLMExtractionEnvelope
    assert len(offers) == 1
    assert offers[0].offer_uid == "co_claro_home_bundles_fibra_500_mbps_500"


def test_all_12_markets_and_41_operators_populated_including_panama_and_bolivia(
    tmp_path: Path,
) -> None:
    """Verify the verified 12-market dataset covers every single country (incl. PA & BO) and every cataloged operator."""
    from src.storage.verified_catalog_seed import build_verified_12_market_snapshots

    settings = RadarSettings()
    catalog = settings.load_markets_catalog()
    expected_12_isos = {"GT", "SV", "HN", "NI", "CR", "PA", "CO", "BO", "PY", "UY", "EC", "CL"}

    png_path = tmp_path / "audit.png"
    md_path = tmp_path / "audit.md"
    png_path.write_bytes(b"png")
    md_path.write_text("# Snapshot\n", encoding="utf-8")

    yesterday_offers, today_offers = build_verified_12_market_snapshots(
        png_path=png_path,
        md_path=md_path,
    )

    present_countries = {o.country_iso for o in today_offers}
    assert present_countries == expected_12_isos

    # Verify every single operator defined in markets_targets.yaml has >= 1 offer in today_offers
    for iso, market_cfg in catalog["markets"].items():
        expected_ops = {op["name"] for op in market_cfg["operators"]}
        actual_ops = {o.operator for o in today_offers if o.country_iso == iso}
        assert actual_ops == expected_ops, f"Mismatch in {iso}: expected {expected_ops}, got {actual_ops}"

    # Explicit checks for Panama (PA) and Bolivia (BO)
    pa_offers = [o for o in today_offers if o.country_iso == "PA"]
    bo_offers = [o for o in today_offers if o.country_iso == "BO"]
    assert len(pa_offers) >= 6
    assert {o.operator for o in pa_offers} == {"Tigo", "MasMovil"}
    assert len(bo_offers) >= 10
    assert {o.operator for o in bo_offers} == {"Tigo", "Entel", "Viva", "AXS"}

    # Verify deterministic deltas across multiple LATAM markets and full 12-country dashboard KPI
    deltas = DeterministicComparator().compare_snapshots(yesterday_offers, today_offers)
    assert len(deltas) >= 7
    builder = ReportBuilder(reports_dir=tmp_path, markets_catalog=catalog)
    artifacts = builder.build_dashboard(
        offers=today_offers,
        deltas=deltas,
        report_date=date(2026, 11, 2),
        output_filename="full_12_markets_test.html",
    )
    html_text = artifacts.html_path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="radar-payload" type="application/json">(.*?)</script>',
        html_text,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    assert payload["kpis"]["active_countries_monitored"] == 12
    assert payload["kpis"]["total_offers_tracked"] == len(today_offers)
