"""CLI entrypoint for the Tigo LATAM Competitive & VAS Intelligence Radar."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from config.settings import PROJECT_ROOT, RadarSettings, get_settings
from src.browser.playwright_mgr import AsyncPlaywrightManager
from src.diff_engine.comparator import DeterministicComparator
from src.extractor.dom_cleaner import DOMCleaner
from src.extractor.gemini_parser import GeminiOfferParser
from src.extractor.schemas import NormalizedOffer
from src.reporting.report_builder import ReportArtifacts, ReportBuilder
from src.storage.repository import RadarRepository
from src.storage.verified_catalog_seed import build_verified_12_market_snapshots

logger = logging.getLogger("tigo_comp_radar")

# Minimal valid 1x1 PNG used exclusively for --dry-run visual audit trail verification
_MINIMAL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def parse_csv_filter(raw_value: Optional[str], uppercase: bool = True) -> Optional[Set[str]]:
    """Parse a comma-separated CLI filter string into a normalized set."""
    if not raw_value:
        return None
    tokens = {
        (tok.strip().upper() if uppercase else tok.strip().lower())
        for tok in raw_value.split(",")
        if tok.strip()
    }
    return tokens or None


def collect_scrape_jobs(
    catalog: Dict[str, Any],
    countries_filter: Optional[Set[str]],
    operators_filter: Optional[Set[str]],
    segments_filter: Optional[Set[str]],
) -> List[Dict[str, Any]]:
    """Expand `markets_targets.yaml` into concrete URL scrape tasks applying CLI filters."""
    jobs: List[Dict[str, Any]] = []
    default_actions = catalog.get("default_pre_scrape_actions", [])
    markets: Dict[str, Any] = catalog.get("markets", {})

    for country_iso, market_cfg in markets.items():
        iso_upper = country_iso.upper()
        if countries_filter and iso_upper not in countries_filter:
            continue

        country_name = market_cfg.get("country_name", iso_upper)
        currency = market_cfg.get("currency", "USD")

        for op_cfg in market_cfg.get("operators", []):
            op_name = str(op_cfg.get("name", "")).strip()
            if not op_name:
                continue
            if operators_filter and op_name.lower() not in operators_filter:
                continue

            actions = op_cfg.get("pre_scrape_actions") or default_actions
            targets_by_segment: Dict[str, List[Dict[str, Any]]] = op_cfg.get("targets", {})

            for seg_name, url_entries in targets_by_segment.items():
                seg_upper = seg_name.upper()
                if segments_filter and seg_upper not in segments_filter:
                    continue

                for entry in url_entries or []:
                    target_url = entry.get("url") if isinstance(entry, dict) else str(entry)
                    if not target_url:
                        continue
                    jobs.append(
                        {
                            "country_iso": iso_upper,
                            "country_name": country_name,
                            "currency": currency,
                            "operator": op_name,
                            "is_millicom": bool(op_cfg.get("is_millicom", False)),
                            "segment": seg_upper,
                            "url": target_url,
                            "label": entry.get("label", "") if isinstance(entry, dict) else "",
                            "pre_scrape_actions": actions,
                        }
                    )

    return jobs


async def execute_live_pipeline(
    settings: RadarSettings,
    jobs: List[Dict[str, Any]],
    run_date: date,
) -> Tuple[List[NormalizedOffer], List[str]]:
    """Run live Playwright browser scrapes, clean DOM to Markdown, and parse via Gemini 2.5 Flash."""
    cleaner = DOMCleaner()
    parser = GeminiOfferParser(settings=settings)
    semaphore = asyncio.Semaphore(max(1, settings.playwright_concurrency))

    extracted_offers: List[NormalizedOffer] = []
    errors: List[str] = []

    async with AsyncPlaywrightManager(settings=settings) as browser_mgr:

        async def _process_job(job: Dict[str, Any]) -> List[NormalizedOffer]:
            async with semaphore:
                artifact = await browser_mgr.scrape_url(
                    url=job["url"],
                    country_iso=job["country_iso"],
                    operator=job["operator"],
                    segment=job["segment"],
                    run_date=run_date,
                    pre_scrape_actions=job["pre_scrape_actions"],
                )
                md_path = artifact.screenshot_path.with_suffix(".md")
                cleaned = cleaner.clean_html_to_markdown(
                    raw_html=artifact.html_content,
                    output_md_path=md_path,
                    metadata_header={
                        "country_iso": job["country_iso"],
                        "operator": job["operator"],
                        "segment": job["segment"],
                        "source_url": artifact.final_url,
                        "captured_at": artifact.captured_at.isoformat(),
                    },
                )
                return await parser.extract_offers(
                    markdown_text=cleaned.markdown_text,
                    country_iso=job["country_iso"],
                    country_name=job["country_name"],
                    operator=job["operator"],
                    segment=job["segment"],
                    expected_currency=job["currency"],
                    source_url=artifact.final_url,
                    screenshot_path=str(artifact.screenshot_path),
                    markdown_path=str(md_path),
                )

        tasks = [asyncio.create_task(_process_job(job)) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_uids: Set[str] = set()
        for job, res in zip(jobs, results):
            if isinstance(res, Exception):
                err_msg = f"[{job['country_iso']}/{job['operator']}/{job['segment']}] {job['url']} -> {res}"
                logger.error(err_msg)
                errors.append(err_msg)
                continue
            for offer in res:
                if offer.offer_uid not in seen_uids:
                    seen_uids.add(offer.offer_uid)
                    extracted_offers.append(offer)

    return extracted_offers, errors


def build_dry_run_simulation_snapshots(
    settings: RadarSettings,
    run_date: date,
    countries_filter: Optional[Set[str]],
    operators_filter: Optional[Set[str]],
    segments_filter: Optional[Set[str]],
) -> Tuple[List[NormalizedOffer], List[NormalizedOffer]]:
    """
    Generate deterministic Day T-1 and Day T snapshots across all 12 LATAM markets
    and all 41 cataloged operators with audit trail files for `--dry-run` verification.
    """
    audit_root = settings.audit_trail_dir / run_date.isoformat() / "dry_run"
    audit_root.mkdir(parents=True, exist_ok=True)
    png_path = audit_root / "dry_run_audit_capture.png"
    md_path = audit_root / "dry_run_audit_snapshot.md"
    png_path.write_bytes(_MINIMAL_PNG_BYTES)
    md_path.write_text(
        "# Dry-Run Cleaned DOM Snapshot (12 LATAM Markets)\n\n"
        "- Verified baseline across GT, SV, HN, NI, CR, PA, CO, BO, PY, UY, EC, CL.\n",
        encoding="utf-8",
    )

    yesterday_seed, today_seed = build_verified_12_market_snapshots(
        png_path=png_path,
        md_path=md_path,
    )

    def _apply_filters(items: List[NormalizedOffer]) -> List[NormalizedOffer]:
        out: List[NormalizedOffer] = []
        for item in items:
            if countries_filter and item.country_iso.upper() not in countries_filter:
                continue
            if operators_filter and item.operator.lower() not in operators_filter:
                continue
            if segments_filter and item.segment.upper() not in segments_filter:
                continue
            out.append(item)
        return out

    return _apply_filters(yesterday_seed), _apply_filters(today_seed)


def run_cli(argv: Optional[List[str]] = None) -> ReportArtifacts:
    """Main CLI orchestration entrypoint."""
    arg_parser = argparse.ArgumentParser(
        prog="tigo-latam-comp-radar",
        description="Automated Daily Competitive & VAS Intelligence Scraper for Tigo (Millicom) across 12 LATAM Markets.",
    )
    arg_parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Comma-separated 2-letter country ISO codes (e.g. CO,PA,BO,GT,CL). Defaults to all 12 markets.",
    )
    arg_parser.add_argument(
        "--operator",
        type=str,
        default=None,
        help="Comma-separated operator names (e.g. Tigo,Claro,Movistar,MasMovil). Defaults to all operators.",
    )
    arg_parser.add_argument(
        "--segment",
        type=str,
        default=None,
        help="Comma-separated segments: HOME_BUNDLES, MOBILE_POSTPAID, VAS_ENTERTAINMENT.",
    )
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute deterministic end-to-end pipeline simulation without hitting live websites or Gemini API.",
    )
    arg_parser.add_argument(
        "--run-date",
        type=str,
        default=None,
        help="Logical YYYY-MM-DD run date (defaults to today).",
    )
    arg_parser.add_argument(
        "--publish-docs",
        action="store_true",
        help="Publish latest HTML dashboard and CSVs to docs/index.html for GitHub Pages HTTPS hosting.",
    )
    arg_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )

    args = arg_parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    settings = get_settings()
    catalog = settings.load_markets_catalog()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()

    countries_filter = parse_csv_filter(args.country, uppercase=True)
    operators_filter = parse_csv_filter(args.operator, uppercase=False)
    segments_filter = parse_csv_filter(args.segment, uppercase=True)

    repository = RadarRepository(database_url=settings.database_url)
    repository.init_db()
    comparator = DeterministicComparator()

    if args.dry_run:
        logger.info("Running in --dry-run mode for date %s...", run_date.isoformat())
        yesterday_date = run_date - timedelta(days=1)
        y_offers, t_offers = build_dry_run_simulation_snapshots(
            settings=settings,
            run_date=run_date,
            countries_filter=countries_filter,
            operators_filter=operators_filter,
            segments_filter=segments_filter,
        )

        # Seed Day T-1 baseline run
        y_run_id = repository.create_scrape_run(
            run_date=yesterday_date,
            is_dry_run=True,
            countries_filter=args.country,
            operators_filter=args.operator,
            segments_filter=args.segment,
        )
        repository.save_offer_snapshots(y_run_id, yesterday_date, y_offers)
        repository.complete_scrape_run(
            scrape_run_id=y_run_id,
            status="SUCCESS",
            total_urls_scraped=len(y_offers),
            total_offers_extracted=len(y_offers),
            total_deltas_detected=0,
        )

        today_run_id = repository.create_scrape_run(
            run_date=run_date,
            is_dry_run=True,
            countries_filter=args.country,
            operators_filter=args.operator,
            segments_filter=args.segment,
        )
        today_offers = t_offers
        urls_scraped_count = len(today_offers)
        errors: List[str] = []
    else:
        if not settings.gemini_api_key:
            logger.error("GEMINI_API_KEY is not set. Configure GEMINI_API_KEY in .env or pass --dry-run.")
            sys.exit(1)

        jobs = collect_scrape_jobs(
            catalog=catalog,
            countries_filter=countries_filter,
            operators_filter=operators_filter,
            segments_filter=segments_filter,
        )
        if not jobs:
            logger.warning("No target URLs matched the provided --country/--operator/--segment filters.")
            sys.exit(0)

        logger.info("Scheduled %d target URL scrapes for run date %s.", len(jobs), run_date.isoformat())

        # Bootstrap Day T-1 baseline from data/latest_snapshot.json on stateless CI runners (e.g. GitHub Actions)
        snapshot_json_path = PROJECT_ROOT / "data" / "latest_snapshot.json"
        if snapshot_json_path.exists():
            try:
                raw_snap = json.loads(snapshot_json_path.read_text(encoding="utf-8"))
                snap_date = date.fromisoformat(raw_snap["snapshot_date"])
                if snap_date < run_date and not repository.get_all_latest_valid_offers(up_to_date=snap_date):
                    prior_offers = [NormalizedOffer.model_validate(item) for item in raw_snap.get("offers", [])]
                    if prior_offers:
                        seed_run_id = repository.create_scrape_run(run_date=snap_date, is_dry_run=False)
                        repository.save_offer_snapshots(seed_run_id, snap_date, prior_offers)
                        repository.complete_scrape_run(
                            scrape_run_id=seed_run_id,
                            status="SUCCESS",
                            total_urls_scraped=len(prior_offers),
                            total_offers_extracted=len(prior_offers),
                            total_deltas_detected=0,
                        )
                        logger.info(
                            "Restored %d baseline offers from data/latest_snapshot.json (%s).",
                            len(prior_offers),
                            snap_date.isoformat(),
                        )
            except Exception as exc:
                logger.warning("Could not restore baseline from latest_snapshot.json: %s", exc)

        today_run_id = repository.create_scrape_run(
            run_date=run_date,
            is_dry_run=False,
            countries_filter=args.country,
            operators_filter=args.operator,
            segments_filter=args.segment,
        )
        today_offers, errors = asyncio.run(
            execute_live_pipeline(settings=settings, jobs=jobs, run_date=run_date)
        )
        urls_scraped_count = len(jobs)

    # Persist Day T snapshots
    repository.save_offer_snapshots(
        scrape_run_id=today_run_id,
        snapshot_date=run_date,
        offers=today_offers,
    )

    # Fetch Day T-1 baseline snapshots deterministically from SQLite/PostgreSQL
    baseline_offers, baseline_dates = repository.get_baseline_offers_for_today_batch(
        today_offers=today_offers,
        run_date=run_date,
    )

    deltas = comparator.compare_snapshots(
        yesterday_offers=baseline_offers,
        today_offers=today_offers,
    )

    repository.save_daily_deltas(
        scrape_run_id=today_run_id,
        delta_date=run_date,
        deltas=deltas,
        baseline_dates=baseline_dates,
    )

    run_status = "PARTIAL_SUCCESS" if (errors and today_offers) else ("FAILED" if errors and not today_offers else "SUCCESS")
    repository.complete_scrape_run(
        scrape_run_id=today_run_id,
        status=run_status,
        total_urls_scraped=urls_scraped_count,
        total_offers_extracted=len(today_offers),
        total_deltas_detected=len(deltas),
        error_log="\n".join(errors) if errors else None,
    )

    # Build navigable HTML dashboard with all latest valid regional offers + today's deltas
    regional_offers = repository.get_all_latest_valid_offers(up_to_date=run_date)
    report_builder = ReportBuilder(
        reports_dir=settings.reports_dir,
        markets_catalog=catalog,
    )
    report_artifacts = report_builder.build_dashboard(
        offers=regional_offers,
        deltas=deltas,
        report_date=run_date,
    )

    if args.publish_docs:
        docs_dir: Path = PROJECT_ROOT / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
        shutil.copy2(report_artifacts.html_path, docs_dir / "index.html")
        if report_artifacts.offers_csv_path and report_artifacts.offers_csv_path.exists():
            shutil.copy2(report_artifacts.offers_csv_path, docs_dir / "latest_offers.csv")
        if report_artifacts.deltas_csv_path and report_artifacts.deltas_csv_path.exists():
            shutil.copy2(report_artifacts.deltas_csv_path, docs_dir / "latest_deltas.csv")

        snapshot_out = PROJECT_ROOT / "data" / "latest_snapshot.json"
        snapshot_out.parent.mkdir(parents=True, exist_ok=True)
        snapshot_out.write_text(
            json.dumps(
                {
                    "snapshot_date": run_date.isoformat(),
                    "offers": [o.model_dump(mode="json") for o in regional_offers],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("Published GitHub Pages static site to %s", docs_dir / "index.html")

    logger.info(
        "Completed run #%d (%s): %d offers extracted, %d deltas detected. HTML Dashboard: %s",
        today_run_id,
        run_status,
        len(today_offers),
        len(deltas),
        report_artifacts.html_path,
    )
    return report_artifacts


if __name__ == "__main__":
    run_cli()
