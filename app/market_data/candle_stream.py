from collections import Counter
from datetime import datetime, timezone

from app.market.candle_builder import CandleBuilder
from app.market_data.models import (
    CandleBuildResult,
    CandleQuality,
    MarketDataEvent,
    MarketDataSource,
)


class QualityAwareCandleBuilder:
    def __init__(self) -> None:
        self._builder = CandleBuilder()
        self._bucket: datetime | None = None
        self._messages = 0
        self._price_events = 0
        self._fallback_events = 0
        self._out_of_order_drops = 0
        self._sources: Counter[str] = Counter()

    def reset(self) -> None:
        self._builder.reset()
        self._bucket = None
        self._reset_quality()

    def record_out_of_order_drop(self) -> None:
        self._out_of_order_drops += 1

    def on_event(self, event: MarketDataEvent) -> CandleBuildResult | None:
        snapshot = event.snapshot
        if snapshot is None:
            return None
        bucket = snapshot.timestamp.astimezone(timezone.utc).replace(
            second=0,
            microsecond=0,
        )
        if self._bucket is None:
            self._bucket = bucket
            self._record_event(event, forwarded=True)
            self._builder.on_snapshot(snapshot)
            return None

        bucket_changed = bucket != self._bucket
        if not bucket_changed:
            self._record_event(event, forwarded=event.price_changed)
            if not event.price_changed:
                return None
            self._builder.on_snapshot(snapshot)
            return None

        closed_quality = self._quality()
        closed = self._builder.on_snapshot(snapshot)
        self._bucket = bucket
        self._reset_quality()
        self._record_event(event, forwarded=True)
        if closed is None:
            return None
        return CandleBuildResult(candle=closed, quality=closed_quality)

    def _record_event(self, event: MarketDataEvent, *, forwarded: bool) -> None:
        self._messages += 1
        self._sources[event.source.value] += 1
        if forwarded:
            self._price_events += 1
        if event.source == MarketDataSource.REST_FALLBACK:
            self._fallback_events += 1

    def _reset_quality(self) -> None:
        self._messages = 0
        self._price_events = 0
        self._fallback_events = 0
        self._out_of_order_drops = 0
        self._sources = Counter()

    def _quality(self) -> CandleQuality:
        source = next(iter(self._sources)) if len(self._sources) == 1 else 'mixed'
        degraded = (
            self._fallback_events > 0
            or self._out_of_order_drops > 0
            or source == 'mixed'
        )
        return CandleQuality(
            source=source,
            message_count=self._messages,
            price_event_count=self._price_events,
            fallback_event_count=self._fallback_events,
            out_of_order_drop_count=self._out_of_order_drops,
            degraded=degraded,
        )
