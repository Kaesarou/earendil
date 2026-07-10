import json
from datetime import datetime, timezone

from app.journal.jsonl_journal import JsonlJournal
from app.replay.comparison import build_replay_comparison
from app.replay.dataset import ReplayDataset


def test_comparison_surfaces_additional_tp_candidate_as_potential_missed_opportunity(tmp_path):
    run_id = 'run-test'
    market_path = tmp_path / 'market.jsonl'
    trades_path = tmp_path / 'trades.jsonl'
    candles_path = tmp_path / 'candles.jsonl'
    manifest_path = tmp_path / 'run_manifest.json'

    JsonlJournal(str(market_path), run_id=run_id, stream_name='market').write(
        'market_snapshot',
        {
            'snapshot': {
                'symbol': 'AAPL',
                'bid': 99.9,
                'ask': 100.1,
                'last': 100.0,
                'timestamp': datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
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
    replay_report = {
        'candidates': [
            {
                'key': 'AAPL|BUY|2026-07-10T12:00:00+00:00',
                'symbol': 'AAPL',
                'side': 'BUY',
                'closed_at': '2026-07-10T12:00:00+00:00',
                'counterfactual_outcome': {
                    'status': 'TP',
                    'gross_percent': 0.5,
                },
            }
        ]
    }

    comparison = build_replay_comparison(
        ReplayDataset(str(manifest_path)),
        replay_report,
    )

    assert comparison['comparison']['matched_candidates'] == 0
    assert len(comparison['comparison']['potential_missed_opportunities']) == 1
