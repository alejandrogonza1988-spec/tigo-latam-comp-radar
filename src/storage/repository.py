"""Repository handling SQLite/PostgreSQL persistence and Day T-1 historical snapshot retrieval."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine, desc, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.diff_engine.comparator import OfferDelta
from src.extractor.schemas import NormalizedOffer
from src.storage.models import Base, DailyDelta, OfferSnapshot, ScrapeRun


class RadarRepository:
    """Data access layer for normalized telecom snapshots and daily competitive deltas."""

    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        Base.metadata.create_all(bind=self.engine)

    def create_scrape_run(
        self,
        run_date: date,
        is_dry_run: bool = False,
        countries_filter: Optional[str] = None,
        operators_filter: Optional[str] = None,
        segments_filter: Optional[str] = None,
    ) -> int:
        """Insert a new ScrapeRun row in RUNNING status and return its primary key ID."""
        with self.SessionLocal() as session:
            run = ScrapeRun(
                run_date=run_date,
                started_at=datetime.now(timezone.utc),
                status="RUNNING",
                is_dry_run=is_dry_run,
                countries_filter=countries_filter,
                operators_filter=operators_filter,
                segments_filter=segments_filter,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def complete_scrape_run(
        self,
        scrape_run_id: int,
        status: str,
        total_urls_scraped: int,
        total_offers_extracted: int,
        total_deltas_detected: int,
        error_log: Optional[str] = None,
    ) -> None:
        """Finalize a ScrapeRun record with summary counters and completion timestamp."""
        with self.SessionLocal() as session:
            run = session.get(ScrapeRun, scrape_run_id)
            if run is None:
                return
            run.completed_at = datetime.now(timezone.utc)
            run.status = status
            run.total_urls_scraped = total_urls_scraped
            run.total_offers_extracted = total_offers_extracted
            run.total_deltas_detected = total_deltas_detected
            run.error_log = error_log
            session.commit()

    def save_offer_snapshots(
        self,
        scrape_run_id: int,
        snapshot_date: date,
        offers: List[NormalizedOffer],
    ) -> int:
        """
        Persist a batch of NormalizedOffer records for a given ScrapeRun and date.

        Marks earlier snapshots from the exact same `(snapshot_date, country_iso, operator, segment)`
        as superseded (`is_valid=False`) so same-day re-runs remain idempotent.
        """
        if not offers:
            return 0

        partitions = {
            (o.country_iso.upper(), o.operator.strip(), o.segment.upper())
            for o in offers
        }

        with self.SessionLocal() as session:
            for country_iso, operator, segment in partitions:
                existing_rows = session.scalars(
                    select(OfferSnapshot).where(
                        OfferSnapshot.snapshot_date == snapshot_date,
                        OfferSnapshot.country_iso == country_iso,
                        OfferSnapshot.operator == operator,
                        OfferSnapshot.segment == segment,
                        OfferSnapshot.scrape_run_id != scrape_run_id,
                        OfferSnapshot.is_valid.is_(True),
                    )
                ).all()
                for old_row in existing_rows:
                    old_row.is_valid = False

            inserted = 0
            for offer in offers:
                dl_mbps = offer.home_specs.download_mbps if offer.home_specs else None
                canonical_json = json.dumps(
                    offer.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                row = OfferSnapshot(
                    scrape_run_id=scrape_run_id,
                    snapshot_date=snapshot_date,
                    offer_uid=offer.offer_uid,
                    country_iso=offer.country_iso.upper(),
                    operator=offer.operator.strip(),
                    segment=offer.segment.upper(),
                    plan_name=offer.plan_name,
                    currency=offer.pricing.currency,
                    regular_monthly_price=offer.pricing.regular_monthly_price,
                    promo_monthly_price=offer.pricing.promo_monthly_price,
                    download_mbps=dl_mbps,
                    normalized_json=canonical_json,
                    source_url=offer.source_url,
                    screenshot_path=offer.screenshot_path,
                    markdown_path=offer.markdown_path,
                    is_valid=True,
                )
                session.add(row)
                inserted += 1

            session.commit()
            return inserted

    def get_latest_prior_snapshot_for_partition(
        self,
        country_iso: str,
        operator: str,
        segment: str,
        before_date: date,
    ) -> Tuple[Optional[date], List[NormalizedOffer]]:
        """
        Fetch the latest valid historical snapshot (`Day T-1` or most recent valid prior date)
        strictly before `before_date` for a single `(country_iso, operator, segment)`.
        """
        c_iso = country_iso.upper()
        op_name = operator.strip()
        seg_name = segment.upper()

        with self.SessionLocal() as session:
            latest_prior_date = session.scalar(
                select(func.max(OfferSnapshot.snapshot_date)).where(
                    OfferSnapshot.country_iso == c_iso,
                    OfferSnapshot.operator == op_name,
                    OfferSnapshot.segment == seg_name,
                    OfferSnapshot.snapshot_date < before_date,
                    OfferSnapshot.is_valid.is_(True),
                )
            )
            if latest_prior_date is None:
                return None, []

            latest_run_id = session.scalar(
                select(OfferSnapshot.scrape_run_id)
                .where(
                    OfferSnapshot.country_iso == c_iso,
                    OfferSnapshot.operator == op_name,
                    OfferSnapshot.segment == seg_name,
                    OfferSnapshot.snapshot_date == latest_prior_date,
                    OfferSnapshot.is_valid.is_(True),
                )
                .order_by(desc(OfferSnapshot.scrape_run_id))
                .limit(1)
            )

            rows = session.scalars(
                select(OfferSnapshot)
                .where(
                    OfferSnapshot.country_iso == c_iso,
                    OfferSnapshot.operator == op_name,
                    OfferSnapshot.segment == seg_name,
                    OfferSnapshot.snapshot_date == latest_prior_date,
                    OfferSnapshot.scrape_run_id == latest_run_id,
                    OfferSnapshot.is_valid.is_(True),
                )
                .order_by(OfferSnapshot.offer_uid)
            ).all()

            offers = [NormalizedOffer.model_validate_json(r.normalized_json) for r in rows]
            return latest_prior_date, offers

    def get_baseline_offers_for_today_batch(
        self,
        today_offers: List[NormalizedOffer],
        run_date: date,
    ) -> Tuple[List[NormalizedOffer], Dict[Tuple[str, str, str], Optional[date]]]:
        """
        For every `(country_iso, operator, segment)` represented in `today_offers`,
        fetch the latest valid prior snapshot (`Day T-1`) and return the combined baseline list.
        """
        partitions = sorted(
            {
                (o.country_iso.upper(), o.operator.strip(), o.segment.upper())
                for o in today_offers
            }
        )
        baseline_offers: List[NormalizedOffer] = []
        baseline_dates: Dict[Tuple[str, str, str], Optional[date]] = {}

        for c_iso, op_name, seg_name in partitions:
            prior_date, prior_list = self.get_latest_prior_snapshot_for_partition(
                country_iso=c_iso,
                operator=op_name,
                segment=seg_name,
                before_date=run_date,
            )
            baseline_dates[(c_iso, op_name, seg_name)] = prior_date
            baseline_offers.extend(prior_list)

        return baseline_offers, baseline_dates

    def get_all_latest_valid_offers(
        self,
        up_to_date: Optional[date] = None,
    ) -> List[NormalizedOffer]:
        """
        Retrieve the latest valid snapshot for every `(country_iso, operator, segment)` in the database
        up to `up_to_date` (inclusive) to power full regional benchmark views.
        """
        with self.SessionLocal() as session:
            stmt = select(
                OfferSnapshot.country_iso,
                OfferSnapshot.operator,
                OfferSnapshot.segment,
                func.max(OfferSnapshot.snapshot_date).label("max_date"),
            ).where(OfferSnapshot.is_valid.is_(True))

            if up_to_date is not None:
                stmt = stmt.where(OfferSnapshot.snapshot_date <= up_to_date)

            stmt = stmt.group_by(
                OfferSnapshot.country_iso,
                OfferSnapshot.operator,
                OfferSnapshot.segment,
            )
            partition_dates = session.execute(stmt).all()

            results: List[NormalizedOffer] = []
            for c_iso, op_name, seg_name, max_dt in partition_dates:
                rows = session.scalars(
                    select(OfferSnapshot)
                    .where(
                        OfferSnapshot.country_iso == c_iso,
                        OfferSnapshot.operator == op_name,
                        OfferSnapshot.segment == seg_name,
                        OfferSnapshot.snapshot_date == max_dt,
                        OfferSnapshot.is_valid.is_(True),
                    )
                    .order_by(OfferSnapshot.offer_uid)
                ).all()
                for row in rows:
                    results.append(NormalizedOffer.model_validate_json(row.normalized_json))

            return results

    def save_daily_deltas(
        self,
        scrape_run_id: int,
        delta_date: date,
        deltas: List[OfferDelta],
        baseline_dates: Optional[Dict[Tuple[str, str, str], Optional[date]]] = None,
    ) -> int:
        """Persist deterministic OfferDelta records into the `daily_deltas` table."""
        if not deltas:
            return 0

        with self.SessionLocal() as session:
            count = 0
            for delta in deltas:
                key = (delta.country_iso.upper(), delta.operator.strip(), delta.segment.upper())
                b_date = baseline_dates.get(key) if baseline_dates else None

                field_changes_str = json.dumps(
                    [fc.model_dump(mode="json") for fc in delta.field_changes],
                    ensure_ascii=False,
                    sort_keys=True,
                )
                y_json = (
                    json.dumps(delta.yesterday_offer.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                    if delta.yesterday_offer is not None
                    else None
                )
                t_json = (
                    json.dumps(delta.today_offer.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                    if delta.today_offer is not None
                    else None
                )

                row = DailyDelta(
                    scrape_run_id=scrape_run_id,
                    delta_date=delta_date,
                    baseline_date=b_date,
                    country_iso=delta.country_iso.upper(),
                    operator=delta.operator.strip(),
                    segment=delta.segment.upper(),
                    offer_uid=delta.offer_uid,
                    plan_name=delta.plan_name,
                    delta_type=delta.delta_type.value,
                    direction=delta.direction,
                    currency=delta.currency,
                    numeric_diff=delta.numeric_diff,
                    percentage_diff=delta.percentage_diff,
                    summary=delta.summary,
                    field_changes_json=field_changes_str,
                    yesterday_offer_json=y_json,
                    today_offer_json=t_json,
                )
                session.add(row)
                count += 1

            session.commit()
            return count
