import asyncio
import json
import time
from collections.abc import Callable

from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.models import utc_now
from app.market_data_probe.recorder import ProbeRecorder
from app.market_data_probe.websocket_protocol import (
    build_authentication_request,
    build_subscription_request,
    parse_websocket_rates,
    validate_authentication_response,
)


class ForcedProbeReconnect(Exception):
    pass


class SilentStreamReconnect(Exception):
    pass


class EtoroWebSocketProbe:
    websocket_url = 'wss://ws.etoro.com/ws'

    def __init__(
        self,
        *,
        api_key: str,
        user_key: str,
        instrument_id_by_symbol: dict[str, int],
        recorder: ProbeRecorder,
        metrics: StudyMetrics,
        silence_seconds: float = 15.0,
        forced_reconnect_after_seconds: float | None = None,
        connector: Callable | None = None,
    ):
        self.api_key = api_key
        self.user_key = user_key
        self.instrument_id_by_symbol = instrument_id_by_symbol
        self.symbol_by_instrument_id = {
            instrument_id: symbol
            for symbol, instrument_id in instrument_id_by_symbol.items()
        }
        self.recorder = recorder
        self.metrics = metrics
        self.silence_seconds = silence_seconds
        self.forced_reconnect_after_seconds = forced_reconnect_after_seconds
        self.connector = connector or _default_connector
        self._forced_reconnect_done = False

    async def run(self, *, duration_seconds: float) -> None:
        started = time.monotonic()
        deadline = started + duration_seconds
        forced_reconnect_at = (
            started + self.forced_reconnect_after_seconds
            if self.forced_reconnect_after_seconds is not None
            else None
        )
        connection_attempt = 0
        backoff_seconds = 1.0

        while time.monotonic() < deadline:
            connection_attempt += 1
            if connection_attempt > 1:
                self.metrics.add_reconnection()
            self.recorder.append(
                'events',
                {
                    'event': 'websocket_connection_attempt',
                    'attempt': connection_attempt,
                    'observed_at': utc_now(),
                },
            )
            try:
                await self._run_connection(
                    deadline=deadline,
                    forced_reconnect_at=forced_reconnect_at,
                )
                backoff_seconds = 1.0
            except ForcedProbeReconnect:
                self._forced_reconnect_done = True
                self.recorder.append(
                    'events',
                    {
                        'event': 'websocket_forced_disconnect',
                        'observed_at': utc_now(),
                    },
                )
            except SilentStreamReconnect as exc:
                self.recorder.append(
                    'events',
                    {
                        'event': 'websocket_silent_stream_reconnect',
                        'message': str(exc),
                        'observed_at': utc_now(),
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.metrics.add_connection_error()
                self.recorder.append(
                    'events',
                    {
                        'event': 'websocket_connection_error',
                        'error_type': type(exc).__name__,
                        'message': str(exc),
                        'observed_at': utc_now(),
                    },
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            delay = min(backoff_seconds, remaining)
            await asyncio.sleep(delay)
            backoff_seconds = min(backoff_seconds * 2, 30.0)

    async def _run_connection(
        self,
        *,
        deadline: float,
        forced_reconnect_at: float | None,
    ) -> None:
        async with self.connector(self.websocket_url) as websocket:
            auth_request = build_authentication_request(
                api_key=self.api_key,
                user_key=self.user_key,
            )
            await websocket.send(json.dumps(auth_request))
            auth_frame = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_raw, auth_transport = _decode_websocket_frame(auth_frame)
            auth_payload = json.loads(auth_raw)
            self.recorder.append(
                'raw_websocket',
                {
                    'received_at': utc_now(),
                    'phase': 'authentication_response',
                    'transport': auth_transport,
                    'payload': auth_payload,
                },
            )
            validate_authentication_response(
                auth_raw,
                request_id=auth_request['id'],
            )
            self.metrics.add_authentication_success()
            self.recorder.append(
                'events',
                {
                    'event': 'websocket_authenticated',
                    'transport': auth_transport,
                    'observed_at': utc_now(),
                },
            )

            subscription_request = build_subscription_request(
                list(self.symbol_by_instrument_id),
                snapshot=True,
            )
            await websocket.send(json.dumps(subscription_request))
            self.recorder.append(
                'events',
                {
                    'event': 'websocket_subscribed',
                    'topics': subscription_request['data']['topics'],
                    'snapshot': True,
                    'observed_at': utc_now(),
                },
            )

            consecutive_silences = 0
            while time.monotonic() < deadline:
                timeout = self._receive_timeout(
                    deadline=deadline,
                    forced_reconnect_at=forced_reconnect_at,
                )
                if timeout <= 0:
                    self._raise_for_scheduled_reconnect(forced_reconnect_at)
                    return
                try:
                    raw_message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=timeout,
                    )
                except TimeoutError:
                    self._raise_for_scheduled_reconnect(forced_reconnect_at)
                    consecutive_silences += 1
                    self.metrics.add_silence()
                    self.recorder.append(
                        'events',
                        {
                            'event': 'websocket_silence_detected',
                            'silence_seconds': self.silence_seconds,
                            'consecutive_silences': consecutive_silences,
                            'observed_at': utc_now(),
                        },
                    )
                    pong_waiter = await websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5.0)
                    self.recorder.append(
                        'events',
                        {
                            'event': 'websocket_transport_pong',
                            'observed_at': utc_now(),
                        },
                    )
                    if consecutive_silences >= 2:
                        raise SilentStreamReconnect(
                            'No market-data message during two silence windows.'
                        )
                    continue

                consecutive_silences = 0
                received_at = utc_now()
                try:
                    decoded_message, transport = _decode_websocket_frame(
                        raw_message
                    )
                    payload = json.loads(decoded_message)
                    rates = parse_websocket_rates(
                        decoded_message,
                        symbol_by_instrument_id=self.symbol_by_instrument_id,
                        received_at=received_at,
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    self.recorder.append(
                        'events',
                        {
                            'event': 'websocket_parse_error',
                            'message': str(exc),
                            'frame_type': type(raw_message).__name__,
                            'frame_size': len(raw_message),
                            'observed_at': received_at,
                        },
                    )
                    continue
                self.recorder.append(
                    'raw_websocket',
                    {
                        'received_at': received_at,
                        'phase': 'stream',
                        'transport': transport,
                        'payload': payload,
                    },
                )
                for rate in rates:
                    self.metrics.add_rate(rate)
                    self.recorder.append('normalized_rates', rate.to_dict())

    def _receive_timeout(
        self,
        *,
        deadline: float,
        forced_reconnect_at: float | None,
    ) -> float:
        now = time.monotonic()
        candidates = [self.silence_seconds, deadline - now]
        if (
            forced_reconnect_at is not None
            and not self._forced_reconnect_done
        ):
            candidates.append(forced_reconnect_at - now)
        return max(0.0, min(candidates))

    def _raise_for_scheduled_reconnect(
        self,
        forced_reconnect_at: float | None,
    ) -> None:
        if (
            forced_reconnect_at is not None
            and not self._forced_reconnect_done
            and time.monotonic() >= forced_reconnect_at
        ):
            raise ForcedProbeReconnect


def _default_connector(url: str):
    from websockets.asyncio.client import connect

    return connect(
        url,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=5,
        max_queue=2048,
    )


def _decode_websocket_frame(raw_message: str | bytes) -> tuple[str, str]:
    if isinstance(raw_message, str):
        return raw_message, 'text'
    if isinstance(raw_message, bytes):
        return raw_message.decode('utf-8'), 'binary_utf8'
    raise TypeError(
        f'Unsupported WebSocket frame type: {type(raw_message).__name__}'
    )
