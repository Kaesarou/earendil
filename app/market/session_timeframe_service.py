from collections import defaultdict
from dataclasses import replace
from typing import Any

from app.market.multi_timeframe import (
    MultiTimeframeCandleEngine,
    MultiTimeframeConfig,
    MultiTimeframeService,
    MultiTimeframeUpdate,
    TimeframeSeriesStore,
)
from app.market.timeframes import BarCompleteness, Timeframe


class FullSessionTimeframeSeriesStore(TimeframeSeriesStore):
    """Retain enough closed bars to preserve session-level features all day."""

    _DEFAULT_LIMITS = {
        Timeframe.M1: 1440,
        Timeframe.M5: 288,
        Timeframe.M15: 192,
        Timeframe.M30: 96,
        Timeframe.H1: 72,
    }


class QualityAwareMultiTimeframeCandleEngine(MultiTimeframeCandleEngine):
    def _finalize_bucket(self, bucket, forced=None):
        bar = super()._finalize_bucket(bucket, forced=forced)
        source_candles = list(bucket.base_candles)
        degraded = any(
            candle.quality_degraded for candle in source_candles
        )
        carried_count = sum(
            1 for candle in source_candles if candle.carried_forward
        )
        ages = [
            candle.source_price_age_seconds
            for candle in source_candles
            if candle.source_price_age_seconds is not None
        ]
        completeness = bar.completeness
        if forced is None and degraded:
            completeness = BarCompleteness.INCOMPLETE
        aggregated = replace(
            bar.candle,
            carried_forward=carried_count > 0,
            source_price_age_seconds=max(ages) if ages else None,
            quality_degraded=degraded,
        )
        return replace(
            bar,
            candle=aggregated,
            completeness=completeness,
        )


class FullSessionMultiTimeframeService(MultiTimeframeService):
    """Runtime service whose M1 history covers a complete 24-hour session."""

    def __init__(
        self,
        configs: dict[str, MultiTimeframeConfig] | None = None,
    ) -> None:
        super().__init__(configs)
        self._stores = defaultdict(FullSessionTimeframeSeriesStore)

    def on_base_candle(
        self,
        *,
        symbol: str,
        candle,
        session_decision: Any,
    ) -> MultiTimeframeUpdate:
        normalized = symbol.strip().upper()
        session_key = (
            getattr(session_decision, 'session_key', None)
            or 'unknown_session'
        )
        engine = self._engines.setdefault(
            normalized,
            QualityAwareMultiTimeframeCandleEngine(normalized),
        )
        update = engine.on_base_candle(
            candle,
            session_key=session_key,
            session_start_time=getattr(
                session_decision,
                'session_start_time',
                None,
            ),
            session_24_7=bool(
                getattr(session_decision, 'session_24_7', False)
            ),
        )
        for bar in update.closed_bars:
            self._stores[normalized].append(bar)
        return update
