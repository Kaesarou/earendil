import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping

from app.market.models import MarketSnapshot


class MarketDataStatus(StrEnum):
    ACCEPTED = 'accepted'
    QUARANTINED = 'quarantined'
    REJECTED = 'rejected'


@dataclass(frozen=True)
class MarketDataQualityConfig:
    max_snapshot_age_seconds: int = 120
    max_future_skew_seconds: int = 10
    max_out_of_order_seconds: int = 2
    max_data_spread_percent: float = 5.0
    max_last_quote_deviation_percent: float = 2.0
    max_jump_percent: float = 5.0
    jump_confirmation_tolerance_percent: float = 0.35
    reset_baseline_after_seconds: int = 900


@dataclass(frozen=True)
class MarketDataValidationResult:
    symbol: str
    status: MarketDataStatus
    snapshot: MarketSnapshot | None
    reasons: tuple[str, ...] = ()
    spread_percent: float | None = None
    price_change_percent: float | None = None
    previous_snapshot_timestamp: datetime | None = None


@dataclass(frozen=True)
class ValidatedMarketBatch:
    loop_id: int
    as_of: datetime
    requested_symbols: tuple[str, ...]
    accepted: dict[str, MarketSnapshot] = field(default_factory=dict)
    quarantined: dict[str, MarketDataValidationResult] = field(default_factory=dict)
    rejected: dict[str, MarketDataValidationResult] = field(default_factory=dict)
    missing_symbols: tuple[str, ...] = ()
    results: dict[str, MarketDataValidationResult] = field(default_factory=dict)


class MarketDataValidator:
    def __init__(self) -> None:
        self._last_accepted: dict[str, MarketSnapshot] = {}
        self._quarantined: dict[str, MarketSnapshot] = {}

    def reset_symbol(self, symbol: str) -> None:
        normalized = symbol.strip().upper()
        self._last_accepted.pop(normalized, None)
        self._quarantined.pop(normalized, None)

    def validate(
        self,
        snapshot: MarketSnapshot,
        config: MarketDataQualityConfig,
        *,
        now: datetime | None = None,
    ) -> MarketDataValidationResult:
        actual_now = _as_utc(now or datetime.now(timezone.utc))
        normalized_symbol = snapshot.symbol.strip().upper()
        timestamp = _as_utc(snapshot.timestamp)
        previous = self._last_accepted.get(normalized_symbol)
        spread = _spread_percent(snapshot)
        reasons = self._basic_rejection_reasons(
            snapshot=snapshot,
            timestamp=timestamp,
            now=actual_now,
            spread=spread,
            previous=previous,
            config=config,
        )
        change = _price_change_percent(previous.last, snapshot.last) if previous else None
        if reasons:
            return MarketDataValidationResult(
                symbol=normalized_symbol,
                status=MarketDataStatus.REJECTED,
                snapshot=snapshot,
                reasons=tuple(reasons),
                spread_percent=_round_optional(spread),
                price_change_percent=_round_optional(change),
                previous_snapshot_timestamp=previous.timestamp if previous else None,
            )

        if previous is not None and self._baseline_is_stale(previous, timestamp, config):
            previous = None
            change = None
            self._quarantined.pop(normalized_symbol, None)

        if previous is not None and change is not None and abs(change) > config.max_jump_percent:
            pending = self._quarantined.get(normalized_symbol)
            if pending is not None and self._confirms_quarantined_level(
                snapshot=snapshot,
                quarantined=pending,
                config=config,
            ):
                self._quarantined.pop(normalized_symbol, None)
                self._last_accepted[normalized_symbol] = snapshot
                return MarketDataValidationResult(
                    symbol=normalized_symbol,
                    status=MarketDataStatus.ACCEPTED,
                    snapshot=snapshot,
                    reasons=('price_jump_confirmed',),
                    spread_percent=_round_optional(spread),
                    price_change_percent=_round_optional(change),
                    previous_snapshot_timestamp=previous.timestamp,
                )
            self._quarantined[normalized_symbol] = snapshot
            return MarketDataValidationResult(
                symbol=normalized_symbol,
                status=MarketDataStatus.QUARANTINED,
                snapshot=snapshot,
                reasons=('unconfirmed_price_jump',),
                spread_percent=_round_optional(spread),
                price_change_percent=_round_optional(change),
                previous_snapshot_timestamp=previous.timestamp,
            )

        self._quarantined.pop(normalized_symbol, None)
        self._last_accepted[normalized_symbol] = snapshot
        return MarketDataValidationResult(
            symbol=normalized_symbol,
            status=MarketDataStatus.ACCEPTED,
            snapshot=snapshot,
            spread_percent=_round_optional(spread),
            price_change_percent=_round_optional(change),
            previous_snapshot_timestamp=previous.timestamp if previous else None,
        )

    def validate_batch(
        self,
        *,
        loop_id: int,
        requested_symbols: list[str],
        snapshots: Mapping[str, MarketSnapshot],
        configs: Mapping[str, MarketDataQualityConfig],
        now: datetime | None = None,
    ) -> ValidatedMarketBatch:
        actual_now = _as_utc(now or datetime.now(timezone.utc))
        accepted: dict[str, MarketSnapshot] = {}
        quarantined: dict[str, MarketDataValidationResult] = {}
        rejected: dict[str, MarketDataValidationResult] = {}
        results: dict[str, MarketDataValidationResult] = {}
        missing: list[str] = []

        for raw_symbol in requested_symbols:
            symbol = raw_symbol.strip().upper()
            snapshot = snapshots.get(symbol)
            if snapshot is None:
                missing.append(symbol)
                result = MarketDataValidationResult(
                    symbol=symbol,
                    status=MarketDataStatus.REJECTED,
                    snapshot=None,
                    reasons=('missing_snapshot',),
                )
                rejected[symbol] = result
                results[symbol] = result
                continue
            result = self.validate(snapshot, configs[symbol], now=actual_now)
            results[symbol] = result
            if result.status == MarketDataStatus.ACCEPTED:
                accepted[symbol] = snapshot
            elif result.status == MarketDataStatus.QUARANTINED:
                quarantined[symbol] = result
            else:
                rejected[symbol] = result

        return ValidatedMarketBatch(
            loop_id=loop_id,
            as_of=actual_now,
            requested_symbols=tuple(symbol.strip().upper() for symbol in requested_symbols),
            accepted=accepted,
            quarantined=quarantined,
            rejected=rejected,
            missing_symbols=tuple(missing),
            results=results,
        )

    def _basic_rejection_reasons(
        self,
        *,
        snapshot: MarketSnapshot,
        timestamp: datetime,
        now: datetime,
        spread: float | None,
        previous: MarketSnapshot | None,
        config: MarketDataQualityConfig,
    ) -> list[str]:
        reasons: list[str] = []
        for name, value in (
            ('bid', snapshot.bid),
            ('ask', snapshot.ask),
            ('last', snapshot.last),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                reasons.append(f'non_finite_{name}')
            elif float(value) <= 0:
                reasons.append(f'non_positive_{name}')
        if reasons:
            return reasons
        if snapshot.ask < snapshot.bid:
            reasons.append('inverted_quote')
        if spread is None or spread < 0 or spread > config.max_data_spread_percent:
            reasons.append('data_spread_abnormal')
        age_seconds = (now - timestamp).total_seconds()
        if age_seconds > config.max_snapshot_age_seconds:
            reasons.append('snapshot_too_old')
        if age_seconds < -config.max_future_skew_seconds:
            reasons.append('snapshot_from_future')
        if previous is not None:
            previous_timestamp = _as_utc(previous.timestamp)
            if (previous_timestamp - timestamp).total_seconds() > config.max_out_of_order_seconds:
                reasons.append('snapshot_out_of_order')
        if _last_quote_deviation_percent(snapshot) > config.max_last_quote_deviation_percent:
            reasons.append('last_too_far_from_quote')
        return reasons

    def _baseline_is_stale(
        self,
        previous: MarketSnapshot,
        timestamp: datetime,
        config: MarketDataQualityConfig,
    ) -> bool:
        return (
            timestamp - _as_utc(previous.timestamp)
        ).total_seconds() > config.reset_baseline_after_seconds

    def _confirms_quarantined_level(
        self,
        *,
        snapshot: MarketSnapshot,
        quarantined: MarketSnapshot,
        config: MarketDataQualityConfig,
    ) -> bool:
        confirmation_distance = abs(
            _price_change_percent(quarantined.last, snapshot.last) or 0.0
        )
        return confirmation_distance <= config.jump_confirmation_tolerance_percent


def _spread_percent(snapshot: MarketSnapshot) -> float | None:
    midpoint = (snapshot.bid + snapshot.ask) / 2
    if midpoint <= 0:
        return None
    return ((snapshot.ask - snapshot.bid) / midpoint) * 100


def _last_quote_deviation_percent(snapshot: MarketSnapshot) -> float:
    if snapshot.bid <= snapshot.last <= snapshot.ask:
        return 0.0
    midpoint = (snapshot.bid + snapshot.ask) / 2
    if midpoint <= 0:
        return float('inf')
    nearest = snapshot.bid if snapshot.last < snapshot.bid else snapshot.ask
    return abs(snapshot.last - nearest) / midpoint * 100


def _price_change_percent(previous: float, current: float) -> float | None:
    if previous <= 0:
        return None
    return ((current - previous) / previous) * 100


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
