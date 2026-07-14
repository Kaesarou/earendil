from datetime import datetime, timedelta, timezone

from app.market.models import Candle, MarketSnapshot
from app.market.timeframes import BASE_TIMEFRAME


class CandleBuilder:
    """Build the canonical fixed M1 candle stream from accepted snapshots."""

    def __init__(self) -> None:
        self.timeframe_seconds = BASE_TIMEFRAME.value
        self._current_bucket_start: datetime | None = None
        self._prices: list[float] = []
        self._symbol: str | None = None

    def reset(self) -> None:
        self._current_bucket_start = None
        self._prices = []
        self._symbol = None

    def on_snapshot(self, snapshot: MarketSnapshot) -> Candle | None:
        bucket_start = self._bucket_start(snapshot.timestamp)

        if self._current_bucket_start is None:
            self._start_new_bucket(snapshot, bucket_start)
            return None

        if bucket_start == self._current_bucket_start:
            self._prices.append(snapshot.last)
            return None

        closed_candle = self._close_current_bucket()
        self._start_new_bucket(snapshot, bucket_start)

        return closed_candle

    def _start_new_bucket(
        self,
        snapshot: MarketSnapshot,
        bucket_start: datetime,
    ) -> None:
        self._current_bucket_start = bucket_start
        self._symbol = snapshot.symbol
        self._prices = [snapshot.last]

    def _close_current_bucket(self) -> Candle:
        if self._current_bucket_start is None:
            raise RuntimeError('Cannot close candle without current bucket')

        if self._symbol is None:
            raise RuntimeError('Cannot close candle without symbol')

        if not self._prices:
            raise RuntimeError('Cannot close candle without prices')

        return Candle(
            symbol=self._symbol,
            timeframe_seconds=self.timeframe_seconds,
            open=self._prices[0],
            high=max(self._prices),
            low=min(self._prices),
            close=self._prices[-1],
            volume=None,
            opened_at=self._current_bucket_start,
            closed_at=self._current_bucket_start + timedelta(
                seconds=self.timeframe_seconds,
            ),
            sample_count=len(self._prices),
        )

    def _bucket_start(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        epoch_seconds = int(timestamp.timestamp())
        bucket_epoch = epoch_seconds - (
            epoch_seconds % self.timeframe_seconds
        )

        return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
