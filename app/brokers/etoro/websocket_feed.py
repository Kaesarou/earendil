import asyncio
import json
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.brokers.etoro.websocket_protocol import (
    build_authentication_request,
    build_subscription_request,
    parse_json_frame,
    parse_websocket_events,
    validate_authentication_response,
)
from app.market_data.contracts import LiveMarketDataFeed, RestMarketDataClient
from app.market_data.models import MarketDataEvent


class _SubscriptionChanged(Exception):
    pass


class EtoroWebSocketMarketDataFeed(LiveMarketDataFeed):
    websocket_url = 'wss://ws.etoro.com/ws'

    def __init__(
        self,
        *,
        api_key: str,
        user_key: str,
        rest_client: RestMarketDataClient,
        queue_capacity: int,
        global_silence_seconds: float,
        connector: Callable | None = None,
    ) -> None:
        self.api_key = api_key
        self.user_key = user_key
        self.rest_client = rest_client
        self.global_silence_seconds = global_silence_seconds
        self.connector = connector or _default_connector
        self._queue: queue.Queue[MarketDataEvent] = queue.Queue(
            maxsize=queue_capacity
        )
        self._stop_event = threading.Event()
        self._subscription_changed = threading.Event()
        self._symbols_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._fatal_error: Exception | None = None
        self._symbols: tuple[str, ...] = ()
        self._instrument_id_by_symbol: dict[str, int] = {}
        self._connections = 0
        self._reconnections = 0
        self._subscription_restarts = 0
        self._subscription_updates = 0
        self._events = 0
        self._null_frames = 0
        self._global_silences = 0
        self._last_error: str | None = None

    @property
    def requires_websocket_health(self) -> bool:
        return True

    def start(self, symbols: list[str]) -> None:
        self.update_symbols(symbols)
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._thread_main,
            name='etoro-websocket-market-data',
            daemon=True,
        )
        self._thread.start()

    def update_symbols(self, symbols: list[str]) -> None:
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        with self._symbols_lock:
            if normalized == self._symbols:
                return
        instrument_ids = self.rest_client.resolve_instrument_ids(list(normalized))
        with self._symbols_lock:
            self._symbols = normalized
            self._instrument_id_by_symbol = {
                symbol: instrument_ids[symbol]
                for symbol in normalized
            }
            self._subscription_updates += 1
        if self._thread is not None:
            self._subscription_changed.set()

    def next_event(self, timeout_seconds: float) -> MarketDataEvent | None:
        try:
            return self._queue.get(timeout=timeout_seconds)
        except queue.Empty:
            if self._fatal_error is not None:
                raise RuntimeError(
                    'eToro WebSocket market-data feed failed'
                ) from self._fatal_error
            return None

    def stop(self) -> None:
        self._stop_event.set()
        self._subscription_changed.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)

    def diagnostics(self) -> dict[str, object]:
        symbols, _ = self._subscription_snapshot()
        return {
            'mode': 'websocket',
            'connections': self._connections,
            'reconnections': self._reconnections,
            'subscription_restarts': self._subscription_restarts,
            'subscription_updates': self._subscription_updates,
            'subscribed_symbols': list(symbols),
            'events': self._events,
            'null_frames': self._null_frames,
            'global_silences': self._global_silences,
            'queue_size': self._queue.qsize(),
            'last_error': self._last_error,
            'fatal_error': str(self._fatal_error) if self._fatal_error else None,
        }

    def _subscription_snapshot(self) -> tuple[tuple[str, ...], dict[str, int]]:
        with self._symbols_lock:
            return self._symbols, dict(self._instrument_id_by_symbol)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self._fatal_error = exc
            self._last_error = str(exc)

    async def _run(self) -> None:
        backoff_seconds = 1.0
        connected_once = False
        while not self._stop_event.is_set():
            self._subscription_changed.clear()
            _, instrument_id_by_symbol = self._subscription_snapshot()
            if not instrument_id_by_symbol:
                await asyncio.sleep(0.25)
                continue
            try:
                if connected_once:
                    self._reconnections += 1
                connected_once = True
                await self._run_connection(instrument_id_by_symbol)
                backoff_seconds = 1.0
            except _SubscriptionChanged:
                self._subscription_restarts += 1
                backoff_seconds = 1.0
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                if self._stop_event.is_set():
                    return
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30.0)

    async def _run_connection(
        self,
        instrument_id_by_symbol: dict[str, int],
    ) -> None:
        self._connections += 1
        connection_id = str(uuid4())
        symbol_by_instrument_id = {
            instrument_id: symbol
            for symbol, instrument_id in instrument_id_by_symbol.items()
        }
        state: dict[int, dict] = {}
        async with self.connector(self.websocket_url) as websocket:
            auth = build_authentication_request(
                api_key=self.api_key,
                user_key=self.user_key,
            )
            await websocket.send(json.dumps(auth))
            auth_text = await _receive_authentication_response(
                websocket,
                request_id=auth['id'],
            )
            validate_authentication_response(
                auth_text,
                request_id=auth['id'],
            )

            subscription = build_subscription_request(
                list(symbol_by_instrument_id)
            )
            await websocket.send(json.dumps(subscription))
            silence_probes = 0
            last_frame_at = time.monotonic()
            receive_timeout = min(1.0, self.global_silence_seconds)
            while not self._stop_event.is_set():
                if self._subscription_changed.is_set():
                    raise _SubscriptionChanged
                try:
                    raw = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=receive_timeout,
                    )
                except TimeoutError:
                    if self._subscription_changed.is_set():
                        raise _SubscriptionChanged
                    if (
                        time.monotonic() - last_frame_at
                        < self.global_silence_seconds
                    ):
                        continue
                    self._global_silences += 1
                    silence_probes += 1
                    pong_waiter = await websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5.0)
                    last_frame_at = time.monotonic()
                    if silence_probes >= 2:
                        raise RuntimeError(
                            'WebSocket stream globally silent'
                        )
                    continue
                silence_probes = 0
                last_frame_at = time.monotonic()
                text = _decode_frame(raw)
                if text == '\x00':
                    self._null_frames += 1
                    continue
                received_at = datetime.now(timezone.utc)
                for event in parse_websocket_events(
                    text,
                    symbol_by_instrument_id=symbol_by_instrument_id,
                    received_at=received_at,
                    connection_id=connection_id,
                    rate_state_by_instrument_id=state,
                ):
                    self._publish(event)

    def _publish(self, event: MarketDataEvent) -> None:
        try:
            self._queue.put(event, timeout=1.0)
            self._events += 1
        except queue.Full as exc:
            self._fatal_error = RuntimeError(
                'Market-data queue overflow'
            )
            self._stop_event.set()
            raise self._fatal_error from exc


def _default_connector(url: str):
    from websockets.asyncio.client import connect

    return connect(
        url,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=5,
        max_queue=2048,
    )


def _decode_frame(raw: str | bytes) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        return raw.decode('utf-8')
    raise TypeError(
        f'Unsupported WebSocket frame type: {type(raw).__name__}'
    )


async def _receive_authentication_response(
    websocket,
    *,
    request_id: str,
    timeout_seconds: float = 10.0,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                'No matching WebSocket authentication response'
            )
        raw = await asyncio.wait_for(
            websocket.recv(),
            timeout=remaining,
        )
        text = _decode_frame(raw)
        if text == '\x00':
            continue
        try:
            payload = parse_json_frame(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get('id') == request_id:
            return json.dumps(payload, separators=(',', ':'))
