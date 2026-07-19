import asyncio
import json

import pytest

from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.recorder import ProbeRecorder
from app.market_data_probe.websocket_probe import (
    EtoroWebSocketProbe,
    _parse_json_frame,
    _redact_sensitive_payload,
)


class FakeWebSocket:
    def __init__(self, *, binary_frames: bool = False):
        self.sent: list[dict] = []
        self.receive_count = 0
        self.binary_frames = binary_frames

    async def send(self, raw_message: str) -> None:
        self.sent.append(json.loads(raw_message))

    async def recv(self) -> str | bytes:
        self.receive_count += 1
        if self.receive_count == 1:
            return self._frame(
                {
                    'id': self.sent[-1]['id'],
                    'success': True,
                    'operation': 'Authenticate',
                }
            )
        if self.receive_count == 2:
            return self._frame(
                {
                    'messages': [
                        {
                            'topic': 'instrument:100000',
                            'content': json.dumps(
                                {
                                    'Ask': '101',
                                    'Bid': '99',
                                    'LastExecution': '100',
                                    'Date': '2026-07-19T10:00:00Z',
                                    'PriceRateID': 'rate-1',
                                }
                            ),
                            'id': 'message-1',
                        }
                    ]
                }
            )
        await asyncio.sleep(60)
        raise AssertionError('unreachable')

    def _frame(self, payload: dict) -> str | bytes:
        serialized = json.dumps(payload)
        return serialized.encode('utf-8') if self.binary_frames else serialized

    async def ping(self):
        future = asyncio.get_running_loop().create_future()
        future.set_result(None)
        return future


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket):
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class GreetingFakeWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__(binary_frames=True)
        self.greeting_sent = False

    async def recv(self) -> str | bytes:
        if not self.greeting_sent:
            self.greeting_sent = True
            return b'Connected'
        return await super().recv()


@pytest.mark.parametrize('binary_frames', [False, True])
def test_probe_authenticates_subscribes_and_records_rate(
    tmp_path,
    binary_frames,
):
    websocket = FakeWebSocket(binary_frames=binary_frames)
    recorder = ProbeRecorder(tmp_path)
    metrics = StudyMetrics()
    probe = EtoroWebSocketProbe(
        api_key='api-key',
        user_key='user-key',
        instrument_id_by_symbol={'BTC': 100000},
        recorder=recorder,
        metrics=metrics,
        silence_seconds=1.0,
        connector=lambda url: FakeConnection(websocket),
    )

    asyncio.run(probe.run(duration_seconds=0.02))

    assert websocket.sent[0]['operation'] == 'Authenticate'
    assert websocket.sent[1] == {
        'id': websocket.sent[1]['id'],
        'operation': 'Subscribe',
        'data': {'topics': ['instrument:100000'], 'snapshot': True},
    }
    assert metrics.authentication_successes == 1
    assert metrics.rate_counts[('websocket_rate', 'BTC')] == 1
    assert (tmp_path / 'raw_websocket.jsonl').is_file()
    assert (tmp_path / 'normalized_rates.jsonl').is_file()
    raw_messages = [
        json.loads(line)
        for line in (tmp_path / 'raw_websocket.jsonl').read_text().splitlines()
    ]
    expected_transport = 'binary_utf8' if binary_frames else 'text'
    assert {message['transport'] for message in raw_messages} == {
        expected_transport
    }


def test_probe_ignores_non_json_greeting_before_authentication(tmp_path):
    websocket = GreetingFakeWebSocket()
    recorder = ProbeRecorder(tmp_path, echo_events_to_console=False)
    metrics = StudyMetrics()
    probe = EtoroWebSocketProbe(
        api_key='api-key',
        user_key='user-key',
        instrument_id_by_symbol={'BTC': 100000},
        recorder=recorder,
        metrics=metrics,
        silence_seconds=1.0,
        connector=lambda url: FakeConnection(websocket),
    )

    asyncio.run(probe.run(duration_seconds=0.02))

    assert metrics.authentication_successes == 1
    assert metrics.rate_counts[('websocket_rate', 'BTC')] == 1
    raw_messages = [
        json.loads(line)
        for line in (tmp_path / 'raw_websocket.jsonl').read_text().splitlines()
    ]
    assert raw_messages[0]['phase'] == 'pre_authentication_non_json'
    assert raw_messages[0]['prefix_hex'] == b'Connected'.hex()
    assert raw_messages[1]['phase'] == 'authentication_response'


def test_parse_json_frame_accepts_control_framing():
    payload, framing = _parse_json_frame(
        '\x00{"id":"auth-id","success":true}\x1e'
    )

    assert payload == {'id': 'auth-id', 'success': True}
    assert framing == 'embedded_json'


def test_pre_authentication_diagnostics_redact_credentials():
    payload = {
        'operation': 'Authenticate',
        'data': {
            'apiKey': 'api-secret',
            'user_key': 'user-secret',
        },
    }

    assert _redact_sensitive_payload(payload) == {
        'operation': 'Authenticate',
        'data': {
            'apiKey': '[REDACTED]',
            'user_key': '[REDACTED]',
        },
    }
