import asyncio
import json

from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.recorder import ProbeRecorder
from app.market_data_probe.websocket_probe import EtoroWebSocketProbe


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.receive_count = 0

    async def send(self, raw_message: str) -> None:
        self.sent.append(json.loads(raw_message))

    async def recv(self) -> str:
        self.receive_count += 1
        if self.receive_count == 1:
            return json.dumps(
                {
                    'id': self.sent[-1]['id'],
                    'success': True,
                    'operation': 'Authenticate',
                }
            )
        if self.receive_count == 2:
            return json.dumps(
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


def test_probe_authenticates_subscribes_and_records_rate(tmp_path):
    websocket = FakeWebSocket()
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
