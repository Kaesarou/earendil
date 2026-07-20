from collections import Counter
from datetime import datetime, timezone

from app.market.candle_builder import CandleBuilder
from app.market.models import MarketSnapshot
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
        self._pending_event: MarketDataEvent | None = None
        self._last_closed_result: CandleBuildResult | None = None

    def reset(self) -> None:
        self._builder.reset()
        self._bucket = None
        self._pending_event = None
        self._last_closed_result = None
        self._reset_quality()

    def prepare_event(self, event: MarketDataEvent) -> None:
        self._pending_event = event

    def take_last_closed_result(self) -> CandleBuildResult | None:
        result = self._last_closed_result
        self._last_closed_result = None
        return result

    def record_out_of_order_drop(self) -> None:
        self._out_of_order_drops += 1

    def on_snapshot(self, snapshot: MarketSnapshot):
        event = self._pending_event
        self._pending_event = None
        if event is None:
            event = MarketDataEvent(
                symbol=snapshot.symbol,
                source=MarketDataSource.PAPER,
                received_at=snapshot.received_at or snapshot.timestamp,
                snapshot=snapshot,
                price_changed=True,
            )
        result = self.on_event(event)
        self._last_closed_result = result
        return result.candle if result is not None else None

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

        if bucket < self._bucket:
            self.record_out_of_order_drop()
            return None

        if bucket == self._bucket:
            self._record_event(event, forwarded=event.price_changed)
            if event.price_changed:
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
