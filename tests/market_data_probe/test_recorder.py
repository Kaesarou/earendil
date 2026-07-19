import json

from app.market_data_probe.recorder import ProbeRecorder


def test_recorder_echoes_events_but_not_rate_payloads(tmp_path, capsys):
    recorder = ProbeRecorder(tmp_path)

    recorder.append('events', {'event': 'websocket_subscribed'})
    recorder.append('normalized_rates', {'symbol': 'BTC', 'last': 100.0})

    output = capsys.readouterr().out
    prefix, serialized = output.strip().split(' ', maxsplit=1)
    assert prefix == '[market-data-probe]'
    assert json.loads(serialized) == {'event': 'websocket_subscribed'}
    assert 'BTC' not in output
