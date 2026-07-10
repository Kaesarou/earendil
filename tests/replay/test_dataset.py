import json
from datetime import datetime, timezone

import pytest

from app.journal.jsonl_journal import JsonlJournal
from app.replay.dataset import ReplayDataset, ReplayIntegrityError, read_journal_records


def test_replay_dataset_filters_run_and_validates_sequences(tmp_path):
    run_id = 'run-test'
    market_path = tmp_path / 'market.jsonl'
    trades_path = tmp_path / 'trades.jsonl'
    candles_path = tmp_path / 'candles.jsonl'
    manifest_path = tmp_path / 'run_manifest.json'

    market = JsonlJournal(str(market_path), run_id=run_id, stream_name='market')
    market.write(
        'market_snapshot',
        {
            'loop_id': 1,
            'snapshot': {
                'symbol': 'AAPL',
                'bid': 99.9,
                'ask': 100.1,
                'last': 100.0,
                'timestamp': datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
            },
        },
    )
    market.write(
        'market_snapshot',
        {
            'loop_id': 2,
            'snapshot': {
                'symbol': 'AAPL',
                'bid': 100.0,
                'ask': 100.2,
                'last': 100.1,
                'timestamp': datetime(2026, 7, 10, 12, 1, tzinfo=timezone.utc),
            },
        },
    )
    JsonlJournal(str(trades_path), run_id=run_id, stream_name='trades').write(
        'runtime_started',
        {},
    )
    candles_path.write_text('', encoding='utf-8')
    manifest_path.write_text(
        json.dumps(
            {
                'run_id': run_id,
                'files': {
                    'market': str(market_path),
                    'trades': str(trades_path),
                    'candles': str(candles_path),
                },
            }
        ),
        encoding='utf-8',
    )

    dataset = ReplayDataset(str(manifest_path))

    assert [event.sequence for event in dataset.market_events()] == [1, 2]
    assert dataset.validate()['candle_records'] == 0


def test_replay_reader_rejects_sequence_gaps(tmp_path):
    path = tmp_path / 'market.jsonl'
    records = [
        {
            'run_id': 'run-test',
            'stream': 'market',
            'sequence': 1,
            'timestamp': '2026-07-10T12:00:00+00:00',
            'event_type': 'market_snapshot',
            'payload': {},
        },
        {
            'run_id': 'run-test',
            'stream': 'market',
            'sequence': 3,
            'timestamp': '2026-07-10T12:01:00+00:00',
            'event_type': 'market_snapshot',
            'payload': {},
        },
    ]
    path.write_text(
        ''.join(json.dumps(record) + '\n' for record in records),
        encoding='utf-8',
    )

    with pytest.raises(ReplayIntegrityError, match='Non-contiguous sequence'):
        list(
            read_journal_records(
                path,
                run_id='run-test',
                validate_sequences=True,
                require_records=True,
            )
        )
