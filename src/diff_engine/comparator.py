"""Deterministic Python comparator for Day T vs Day T-1 normalized telecom offer snapshots (Guardrail #2)."""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from src.extractor.schemas import (
    EntertainmentVASAddon,
    NormalizedOffer,
    VASProviderEnum,
    normalize_slug,
)


class DeltaTypeEnum(str, Enum):
    """Canonical competitive change categories."""

    NEW_OFFER_LAUNCHED = "NEW_OFFER_LAUNCHED"
    OFFER_RETIRED = "OFFER_RETIRED"
    PRICE_CHANGE = "PRICE_CHANGE"
    SPEED_OR_HARDWARE_CHANGE = "SPEED_OR_HARDWARE_CHANGE"
    VAS_PORTFOLIO_CHANGE = "VAS_PORTFOLIO_CHANGE"


class FieldDiff(BaseModel):
    """Granular deterministic change record for a single attribute."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    old_value: Any = None
    new_value: Any = None
    numeric_diff: Optional[float] = None
    percentage_diff: Optional[float] = None
    note: Optional[str] = None


class OfferDelta(BaseModel):
    """Structured competitive delta detected between Day T-1 and Day T."""

    model_config = ConfigDict(extra="forbid")

    country_iso: str
    operator: str
    segment: str
    offer_uid: str
    previous_offer_uid: Optional[str] = None
    plan_name: str
    delta_type: DeltaTypeEnum
    direction: str
    currency: str
    numeric_diff: Optional[float] = None
    percentage_diff: Optional[float] = None
    summary: str
    field_changes: List[FieldDiff] = Field(default_factory=list)
    vas_providers_affected: List[str] = Field(default_factory=list)
    yesterday_offer: Optional[NormalizedOffer] = None
    today_offer: Optional[NormalizedOffer] = None


def _compute_numeric_and_pct_diff(
    old_val: Optional[float],
    new_val: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if old_val is None or new_val is None:
        return None, None
    num_diff = round(float(new_val) - float(old_val), 2)
    if float(old_val) == 0.0:
        return num_diff, None
    pct_diff = round((num_diff / float(old_val)) * 100.0, 2)
    return num_diff, pct_diff


def _effective_monthly_price(offer: NormalizedOffer) -> Optional[float]:
    if offer.pricing.promo_monthly_price is not None:
        return offer.pricing.promo_monthly_price
    return offer.pricing.regular_monthly_price


def _vas_key(addon: EntertainmentVASAddon) -> str:
    if addon.provider == VASProviderEnum.OTHER:
        return f"OTHER::{normalize_slug(addon.raw_provider_name)}"
    return addon.provider.value


class DeterministicComparator:
    """
    Pure Python deterministic comparator (Zero LLM involvement).

    Partitions snapshots by `(country_iso, operator, segment)` and detects:
    - `NEW_OFFER_LAUNCHED`
    - `OFFER_RETIRED`
    - `PRICE_CHANGE`
    - `SPEED_OR_HARDWARE_CHANGE`
    - `VAS_PORTFOLIO_CHANGE`
    """

    def compare_snapshots(
        self,
        yesterday_offers: List[NormalizedOffer],
        today_offers: List[NormalizedOffer],
    ) -> List[OfferDelta]:
        """Compare complete lists of Day T-1 and Day T offers partitioned by `(country_iso, operator, segment)`."""
        yesterday_groups: Dict[Tuple[str, str, str], List[NormalizedOffer]] = defaultdict(list)
        today_groups: Dict[Tuple[str, str, str], List[NormalizedOffer]] = defaultdict(list)

        for offer in yesterday_offers:
            key = (offer.country_iso.upper(), offer.operator.strip(), offer.segment.upper())
            yesterday_groups[key].append(offer)

        for offer in today_offers:
            key = (offer.country_iso.upper(), offer.operator.strip(), offer.segment.upper())
            today_groups[key].append(offer)

        all_partitions = sorted(set(yesterday_groups.keys()) | set(today_groups.keys()))
        deltas: List[OfferDelta] = []

        for partition_key in all_partitions:
            y_list = yesterday_groups.get(partition_key, [])
            t_list = today_groups.get(partition_key, [])
            deltas.extend(self.compare_partition(yesterday_offers=y_list, today_offers=t_list))

        return deltas

    def compare_partition(
        self,
        yesterday_offers: List[NormalizedOffer],
        today_offers: List[NormalizedOffer],
    ) -> List[OfferDelta]:
        """Compare Day T-1 vs Day T offers within a single `(country_iso, operator, segment)` bucket."""
        deltas: List[OfferDelta] = []

        yesterday_by_uid: Dict[str, NormalizedOffer] = {o.offer_uid: o for o in yesterday_offers}
        today_by_uid: Dict[str, NormalizedOffer] = {o.offer_uid: o for o in today_offers}

        matched_pairs: List[Tuple[NormalizedOffer, NormalizedOffer]] = []
        common_uids = sorted(set(yesterday_by_uid.keys()) & set(today_by_uid.keys()))
        for uid in common_uids:
            matched_pairs.append((yesterday_by_uid[uid], today_by_uid[uid]))

        unmatched_yesterday = {
            uid: offer for uid, offer in yesterday_by_uid.items() if uid not in today_by_uid
        }
        unmatched_today = {
            uid: offer for uid, offer in today_by_uid.items() if uid not in yesterday_by_uid
        }

        # Secondary lineage match: if an identical plan_name within the same operator & segment
        # had its download_mbps upgraded/downgraded (which shifts the `{download_mbps}` UID suffix),
        # pair uniquely matching normalized plan names as SPEED_OR_HARDWARE_CHANGE instead of retire+launch.
        y_by_plan_slug: Dict[str, List[NormalizedOffer]] = defaultdict(list)
        t_by_plan_slug: Dict[str, List[NormalizedOffer]] = defaultdict(list)
        for offer in unmatched_yesterday.values():
            y_by_plan_slug[normalize_slug(offer.plan_name)].append(offer)
        for offer in unmatched_today.values():
            t_by_plan_slug[normalize_slug(offer.plan_name)].append(offer)

        for plan_slug in sorted(set(y_by_plan_slug.keys()) & set(t_by_plan_slug.keys())):
            if len(y_by_plan_slug[plan_slug]) == 1 and len(t_by_plan_slug[plan_slug]) == 1:
                y_offer = y_by_plan_slug[plan_slug][0]
                t_offer = t_by_plan_slug[plan_slug][0]
                matched_pairs.append((y_offer, t_offer))
                unmatched_yesterday.pop(y_offer.offer_uid, None)
                unmatched_today.pop(t_offer.offer_uid, None)

        # 1. Compare all matched pairs across Pricing, Speed/Hardware, and VAS Portfolio
        for y_offer, t_offer in matched_pairs:
            price_delta = self._evaluate_price_change(y_offer, t_offer)
            if price_delta is not None:
                deltas.append(price_delta)

            speed_hw_delta = self._evaluate_speed_or_hardware_change(y_offer, t_offer)
            if speed_hw_delta is not None:
                deltas.append(speed_hw_delta)

            vas_delta = self._evaluate_vas_portfolio_change(y_offer, t_offer)
            if vas_delta is not None:
                deltas.append(vas_delta)

        # 2. Emit NEW_OFFER_LAUNCHED for unmatched today UIDs
        for uid in sorted(unmatched_today.keys()):
            t_offer = unmatched_today[uid]
            eff_price = _effective_monthly_price(t_offer)
            price_label = (
                f"{eff_price:,.2f} {t_offer.pricing.currency}" if eff_price is not None else "precio N/D"
            )
            vas_names = [a.provider.value for a in t_offer.vas_addons]
            vas_suffix = f" (VAS: {', '.join(vas_names)})" if vas_names else ""
            deltas.append(
                OfferDelta(
                    country_iso=t_offer.country_iso,
                    operator=t_offer.operator,
                    segment=t_offer.segment,
                    offer_uid=t_offer.offer_uid,
                    plan_name=t_offer.plan_name,
                    delta_type=DeltaTypeEnum.NEW_OFFER_LAUNCHED,
                    direction="NEW",
                    currency=t_offer.pricing.currency,
                    summary=f"Nuevo plan lanzado: '{t_offer.plan_name}' a {price_label}{vas_suffix}.",
                    field_changes=[
                        FieldDiff(
                            field_name="offer_uid",
                            old_value=None,
                            new_value=t_offer.offer_uid,
                        )
                    ],
                    vas_providers_affected=vas_names,
                    yesterday_offer=None,
                    today_offer=t_offer,
                )
            )

        # 3. Emit OFFER_RETIRED for unmatched yesterday UIDs
        for uid in sorted(unmatched_yesterday.keys()):
            y_offer = unmatched_yesterday[uid]
            eff_price = _effective_monthly_price(y_offer)
            price_label = (
                f"{eff_price:,.2f} {y_offer.pricing.currency}" if eff_price is not None else "precio N/D"
            )
            vas_names = [a.provider.value for a in y_offer.vas_addons]
            deltas.append(
                OfferDelta(
                    country_iso=y_offer.country_iso,
                    operator=y_offer.operator,
                    segment=y_offer.segment,
                    offer_uid=y_offer.offer_uid,
                    plan_name=y_offer.plan_name,
                    delta_type=DeltaTypeEnum.OFFER_RETIRED,
                    direction="RETIRED",
                    currency=y_offer.pricing.currency,
                    summary=f"Plan retirado del catálogo: '{y_offer.plan_name}' ({price_label}).",
                    field_changes=[
                        FieldDiff(
                            field_name="offer_uid",
                            old_value=y_offer.offer_uid,
                            new_value=None,
                        )
                    ],
                    vas_providers_affected=vas_names,
                    yesterday_offer=y_offer,
                    today_offer=None,
                )
            )

        return deltas

    def _evaluate_price_change(
        self,
        y_offer: NormalizedOffer,
        t_offer: NormalizedOffer,
    ) -> Optional[OfferDelta]:
        """Detect changes in `regular_monthly_price`, `promo_monthly_price`, or `promo_duration_months`."""
        yp = y_offer.pricing
        tp = t_offer.pricing

        field_changes: List[FieldDiff] = []

        if yp.regular_monthly_price != tp.regular_monthly_price:
            num_diff, pct_diff = _compute_numeric_and_pct_diff(
                yp.regular_monthly_price, tp.regular_monthly_price
            )
            field_changes.append(
                FieldDiff(
                    field_name="regular_monthly_price",
                    old_value=yp.regular_monthly_price,
                    new_value=tp.regular_monthly_price,
                    numeric_diff=num_diff,
                    percentage_diff=pct_diff,
                )
            )

        if yp.promo_monthly_price != tp.promo_monthly_price:
            num_diff, pct_diff = _compute_numeric_and_pct_diff(
                yp.promo_monthly_price, tp.promo_monthly_price
            )
            field_changes.append(
                FieldDiff(
                    field_name="promo_monthly_price",
                    old_value=yp.promo_monthly_price,
                    new_value=tp.promo_monthly_price,
                    numeric_diff=num_diff,
                    percentage_diff=pct_diff,
                )
            )

        if yp.promo_duration_months != tp.promo_duration_months:
            dur_num, dur_pct = _compute_numeric_and_pct_diff(
                float(yp.promo_duration_months) if yp.promo_duration_months is not None else None,
                float(tp.promo_duration_months) if tp.promo_duration_months is not None else None,
            )
            field_changes.append(
                FieldDiff(
                    field_name="promo_duration_months",
                    old_value=yp.promo_duration_months,
                    new_value=tp.promo_duration_months,
                    numeric_diff=dur_num,
                    percentage_diff=dur_pct,
                )
            )

        if not field_changes:
            return None

        # Determine primary numeric and percentage diff based on effective active customer price
        old_eff = _effective_monthly_price(y_offer)
        new_eff = _effective_monthly_price(t_offer)
        headline_num, headline_pct = _compute_numeric_and_pct_diff(old_eff, new_eff)

        # Fallback if effective price didn't change (e.g. regular price changed while promo price stayed identical)
        if headline_num is None or headline_num == 0.0:
            for fc in field_changes:
                if fc.field_name in {"promo_monthly_price", "regular_monthly_price"} and fc.numeric_diff:
                    headline_num = fc.numeric_diff
                    headline_pct = fc.percentage_diff
                    break

        currency = tp.currency or yp.currency
        if headline_num is not None and headline_num < 0:
            direction = "PRICE_DROP"
            sign_str = f"{headline_num:,.2f} {currency} ({headline_pct:+.2f}%)" if headline_pct is not None else f"{headline_num:,.2f} {currency}"
            summary = f"Baja de precio en '{t_offer.plan_name}': {old_eff:,.2f} -> {new_eff:,.2f} {currency} [{sign_str}]."
        elif headline_num is not None and headline_num > 0:
            direction = "PRICE_INCREASE"
            sign_str = f"+{headline_num:,.2f} {currency} ({headline_pct:+.2f}%)" if headline_pct is not None else f"+{headline_num:,.2f} {currency}"
            summary = f"Alza de precio en '{t_offer.plan_name}': {old_eff:,.2f} -> {new_eff:,.2f} {currency} [{sign_str}]."
        else:
            direction = "PROMO_DURATION_CHANGE"
            summary = (
                f"Ajuste de condiciones tarifarias/vigencia promo en '{t_offer.plan_name}' "
                f"(duración promo: {yp.promo_duration_months} -> {tp.promo_duration_months} meses)."
            )

        return OfferDelta(
            country_iso=t_offer.country_iso,
            operator=t_offer.operator,
            segment=t_offer.segment,
            offer_uid=t_offer.offer_uid,
            previous_offer_uid=y_offer.offer_uid if y_offer.offer_uid != t_offer.offer_uid else None,
            plan_name=t_offer.plan_name,
            delta_type=DeltaTypeEnum.PRICE_CHANGE,
            direction=direction,
            currency=currency,
            numeric_diff=headline_num,
            percentage_diff=headline_pct,
            summary=summary,
            field_changes=field_changes,
            vas_providers_affected=[a.provider.value for a in t_offer.vas_addons],
            yesterday_offer=y_offer,
            today_offer=t_offer,
        )

    def _evaluate_speed_or_hardware_change(
        self,
        y_offer: NormalizedOffer,
        t_offer: NormalizedOffer,
    ) -> Optional[OfferDelta]:
        """Detect changes in `download_mbps`, `upload_mbps`, or `wifi_hardware`."""
        yh = y_offer.home_specs
        th = t_offer.home_specs
        if yh is None and th is None:
            return None

        y_dl = yh.download_mbps if yh else None
        t_dl = th.download_mbps if th else None
        y_ul = yh.upload_mbps if yh else None
        t_ul = th.upload_mbps if th else None
        y_wifi = (yh.wifi_hardware.strip() if yh and yh.wifi_hardware else None)
        t_wifi = (th.wifi_hardware.strip() if th and th.wifi_hardware else None)

        field_changes: List[FieldDiff] = []
        headline_num: Optional[float] = None
        headline_pct: Optional[float] = None

        if y_dl != t_dl:
            dl_num, dl_pct = _compute_numeric_and_pct_diff(
                float(y_dl) if y_dl is not None else None,
                float(t_dl) if t_dl is not None else None,
            )
            headline_num, headline_pct = dl_num, dl_pct
            field_changes.append(
                FieldDiff(
                    field_name="download_mbps",
                    old_value=y_dl,
                    new_value=t_dl,
                    numeric_diff=dl_num,
                    percentage_diff=dl_pct,
                )
            )

        if y_ul != t_ul:
            ul_num, ul_pct = _compute_numeric_and_pct_diff(
                float(y_ul) if y_ul is not None else None,
                float(t_ul) if t_ul is not None else None,
            )
            if headline_num is None:
                headline_num, headline_pct = ul_num, ul_pct
            field_changes.append(
                FieldDiff(
                    field_name="upload_mbps",
                    old_value=y_ul,
                    new_value=t_ul,
                    numeric_diff=ul_num,
                    percentage_diff=ul_pct,
                )
            )

        if y_wifi != t_wifi:
            field_changes.append(
                FieldDiff(
                    field_name="wifi_hardware",
                    old_value=y_wifi,
                    new_value=t_wifi,
                )
            )

        if not field_changes:
            return None

        if headline_num is not None and headline_num > 0:
            direction = "SPEED_UPGRADE"
        elif headline_num is not None and headline_num < 0:
            direction = "SPEED_DOWNGRADE"
        else:
            direction = "HARDWARE_CHANGE"

        parts: List[str] = []
        for fc in field_changes:
            parts.append(f"{fc.field_name}: {fc.old_value} -> {fc.new_value}")

        return OfferDelta(
            country_iso=t_offer.country_iso,
            operator=t_offer.operator,
            segment=t_offer.segment,
            offer_uid=t_offer.offer_uid,
            previous_offer_uid=y_offer.offer_uid if y_offer.offer_uid != t_offer.offer_uid else None,
            plan_name=t_offer.plan_name,
            delta_type=DeltaTypeEnum.SPEED_OR_HARDWARE_CHANGE,
            direction=direction,
            currency=t_offer.pricing.currency,
            numeric_diff=headline_num,
            percentage_diff=headline_pct,
            summary=f"Cambio de velocidad/equipos en '{t_offer.plan_name}' ({'; '.join(parts)}).",
            field_changes=field_changes,
            vas_providers_affected=[a.provider.value for a in t_offer.vas_addons],
            yesterday_offer=y_offer,
            today_offer=t_offer,
        )

    def _evaluate_vas_portfolio_change(
        self,
        y_offer: NormalizedOffer,
        t_offer: NormalizedOffer,
    ) -> Optional[OfferDelta]:
        """Detect additions, removals, or commercial term modifications in streaming/sports VAS addons."""
        y_map: Dict[str, EntertainmentVASAddon] = {_vas_key(a): a for a in y_offer.vas_addons}
        t_map: Dict[str, EntertainmentVASAddon] = {_vas_key(a): a for a in t_offer.vas_addons}

        field_changes: List[FieldDiff] = []
        affected_providers: List[str] = []
        summary_fragments: List[str] = []

        added_keys = sorted(set(t_map.keys()) - set(y_map.keys()))
        removed_keys = sorted(set(y_map.keys()) - set(t_map.keys()))
        common_keys = sorted(set(y_map.keys()) & set(t_map.keys()))

        for key in added_keys:
            addon = t_map[key]
            affected_providers.append(addon.provider.value)
            promo_desc = (
                f"{addon.free_months} meses gratis"
                if addon.free_months
                else addon.commercial_model.value
            )
            summary_fragments.append(f"+{addon.provider.value} ({promo_desc})")
            field_changes.append(
                FieldDiff(
                    field_name=f"vas_addon_added:{addon.provider.value}",
                    old_value=None,
                    new_value={
                        "provider": addon.provider.value,
                        "tier_or_package": addon.tier_or_package,
                        "commercial_model": addon.commercial_model.value,
                        "free_months": addon.free_months,
                        "promo_price": addon.promo_price,
                        "regular_price_after_promo": addon.regular_price_after_promo,
                    },
                    note=f"Added {addon.raw_provider_name} ({promo_desc})",
                )
            )

        for key in removed_keys:
            addon = y_map[key]
            affected_providers.append(addon.provider.value)
            summary_fragments.append(f"-{addon.provider.value} retirado")
            field_changes.append(
                FieldDiff(
                    field_name=f"vas_addon_removed:{addon.provider.value}",
                    old_value={
                        "provider": addon.provider.value,
                        "tier_or_package": addon.tier_or_package,
                        "commercial_model": addon.commercial_model.value,
                        "free_months": addon.free_months,
                        "promo_price": addon.promo_price,
                        "regular_price_after_promo": addon.regular_price_after_promo,
                    },
                    new_value=None,
                    note=f"Removed {addon.raw_provider_name}",
                )
            )

        for key in common_keys:
            ya = y_map[key]
            ta = t_map[key]
            tracked_attrs = [
                ("free_months", ya.free_months, ta.free_months),
                ("promo_price", ya.promo_price, ta.promo_price),
                ("regular_price_after_promo", ya.regular_price_after_promo, ta.regular_price_after_promo),
                ("tier_or_package", ya.tier_or_package, ta.tier_or_package),
                ("commercial_model", ya.commercial_model.value, ta.commercial_model.value),
            ]
            addon_diffs: List[str] = []
            for attr_name, old_v, new_v in tracked_attrs:
                if old_v != new_v:
                    num_d: Optional[float] = None
                    pct_d: Optional[float] = None
                    if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
                        num_d, pct_d = _compute_numeric_and_pct_diff(float(old_v), float(new_v))
                    field_changes.append(
                        FieldDiff(
                            field_name=f"vas_addon:{ta.provider.value}.{attr_name}",
                            old_value=old_v,
                            new_value=new_v,
                            numeric_diff=num_d,
                            percentage_diff=pct_d,
                        )
                    )
                    addon_diffs.append(f"{attr_name}: {old_v} -> {new_v}")

            if addon_diffs:
                affected_providers.append(ta.provider.value)
                summary_fragments.append(f"{ta.provider.value} ({', '.join(addon_diffs)})")

        if not field_changes:
            return None

        if added_keys and not removed_keys and len(added_keys) == len(affected_providers):
            direction = "VAS_ADDED"
        elif removed_keys and not added_keys and len(removed_keys) == len(affected_providers):
            direction = "VAS_REMOVED"
        else:
            direction = "VAS_MODIFIED"

        deduped_providers = list(dict.fromkeys(affected_providers))
        return OfferDelta(
            country_iso=t_offer.country_iso,
            operator=t_offer.operator,
            segment=t_offer.segment,
            offer_uid=t_offer.offer_uid,
            previous_offer_uid=y_offer.offer_uid if y_offer.offer_uid != t_offer.offer_uid else None,
            plan_name=t_offer.plan_name,
            delta_type=DeltaTypeEnum.VAS_PORTFOLIO_CHANGE,
            direction=direction,
            currency=t_offer.pricing.currency,
            summary=f"Cambio de portafolio VAS en '{t_offer.plan_name}': {'; '.join(summary_fragments)}.",
            field_changes=field_changes,
            vas_providers_affected=deduped_providers,
            yesterday_offer=y_offer,
            today_offer=t_offer,
        )
