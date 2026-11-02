"""SQLAlchemy 2.0 ORM models: ScrapeRun, OfferSnapshot, and DailyDelta."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for Tigo LATAM Competitive Radar persistence."""


class ScrapeRun(Base):
    """Audit record for a single execution of the competitive scraping pipeline."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING", nullable=False, index=True)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    countries_filter: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    operators_filter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    segments_filter: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    total_urls_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_offers_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_deltas_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    snapshots: Mapped[List[OfferSnapshot]] = relationship(
        "OfferSnapshot",
        back_populates="scrape_run",
        cascade="all, delete-orphan",
    )
    deltas: Mapped[List[DailyDelta]] = relationship(
        "DailyDelta",
        back_populates="scrape_run",
        cascade="all, delete-orphan",
    )


class OfferSnapshot(Base):
    """Normalized point-in-time snapshot of a single commercial offer on a given date."""

    __tablename__ = "offer_snapshots"
    __table_args__ = (
        Index(
            "ix_offer_snapshots_partition_date",
            "country_iso",
            "operator",
            "segment",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    offer_uid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country_iso: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    segment: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    regular_monthly_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    promo_monthly_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    download_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    normalized_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    markdown_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    scrape_run: Mapped[ScrapeRun] = relationship("ScrapeRun", back_populates="snapshots")


class DailyDelta(Base):
    """Persisted deterministic diff record comparing Day T against Day T-1."""

    __tablename__ = "daily_deltas"
    __table_args__ = (
        Index("ix_daily_deltas_date_country", "delta_date", "country_iso", "delta_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    baseline_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    country_iso: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    segment: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    offer_uid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)

    delta_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    numeric_diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentage_diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    field_changes_json: Mapped[str] = mapped_column(Text, nullable=False)
    yesterday_offer_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    today_offer_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    scrape_run: Mapped[ScrapeRun] = relationship("ScrapeRun", back_populates="deltas")
