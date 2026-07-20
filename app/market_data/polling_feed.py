import queue
import threading
import time
from datetime import datetime, timezone

from app.market_data.contracts import LiveMarketDataFeed, RestMarketDataClient
from app.market_data.models import MarketDataEvent, MarketDataSource


class PollingMarketDataFeed(LiveMarketDataFeed):
    def __init__(
        self,
        *,
        client: RestMarketDataClient,
        interval_seconds: float,
        queue_capacity: int,
        source: MarketDataSource,
    ) -> None:
        self.client = client
        self.interval_seconds = interval_seconds
        self.source = source
        self._queue: queue.Queue[MarketDataEvent] = queue.Queue(maxsize=queue_capacity)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._symbols: list[str] = []
        self._fatal_error: Exception | None = None
        self._polls = 0
        self._events = 0

    @property
    def requires_websocket_health(self) -> bool:
        return False

    def start(self, symbols: list[str]) -> None:
        if self._thread is not None:
            return
        self._symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))
        self._thread = threading.Thread(
            target=self._run,
            name='market-data-polling',
            daemon=True,
        )
        self._thread.start()

    def next_event(self, timeout_seconds: float) -> MarketDataEvent | None:
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            if self._fatal_error is not None:
                raise RuntimeError('Polling market-data feed failed') from self._fatal_error
            return None

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def diagnostics(self) -> dict[str, object]:
        return {
            'mode': 'polling',
            'polls': self._polls,
            'events': self._events,
            'fatal_error': str(self._fatal_error) if self._fatal_error else None,
        }

    def _run(self) -> None:
        next_poll = time.monotonic()
        try:
            while not self._stop_event.is_set():
                snapshots = self.client.get_market_snapshots(self._symbols)
                self._polls += 1
                received_at = datetime.now(timezone.utc)
                for symbol, snapshot in snapshots.items():
                    self._publish(
                        MarketDataEvent(
                            symbol=symbol,
                            source=self.source,
                            received_at=received_at,
                            snapshot=snapshot,
                            price_changed=True,
                        )
                    )
                next_poll += self.interval_seconds
                delay = next_poll - time.monotonic()
                if delay > 0:
                    self._stop_event.wait(delay)
                else:
                    next_poll = time.monotonic()
        except Exception as exc:
            self._fatal_error = exc

    def _publish(self, event: MarketDataEvent) -> None:
        try:
            self._queue.put(event, timeout=1.0)
            self._events += 1
        except queue.Full as exc:
            self._fatal_error = RuntimeError('Market-data queue overflow')
            self._stop_event.set()
            raise self._fatal_error from exc
