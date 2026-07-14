import gzip
import json
from types import SimpleNamespace

from app.journal.analysis_journal import AnalysisJournal
from app.journal.jsonl_journal import JsonlJournal


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_analysis_journal_aggregates_hold_without_writing_it_to_trades(tmp_path):
    trades_path = tmp_path / 'trades.jsonl'
    errors_path = tmp_path / 'errors.jsonl'
    summary_path = tmp_path / 'daily_summary.json'
    journal = AnalysisJournal(
        trade_journal=JsonlJournal(str(trades_path)),
        errors_journal=JsonlJournal(str(errors_path)),
        summary_path=str(summary_path),
        detail_level='normal',
        write_partial_summary=False,
    )

    journal.write(
        'decision',
        {
            'symbol': 'AAPL',
            'signal': SimpleNamespace(action='HOLD'),
            'trade_plan': SimpleNamespace(approved=False, reason='market_regime_dead_market'),
        },
    )
    journal.write('position_opened', {'symbol': 'AAPL', 'position_id': 'p-1'})
    journal.finalize()

    trade_events = _read_jsonl(trades_path)
    assert [event['event_type'] for event in trade_events] == ['position_opened']

    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['strategy_decisions']['hold_total'] == 1
    assert summary['hold_reasons'] == {'market_regime_dead_market': 1}
    assert 'decisions' not in summary


def test_analysis_journal_writes_errors_to_errors_file(tmp_path):
    trades_path = tmp_path / 'trades.jsonl'
    errors_path = tmp_path / 'errors.jsonl'
    summary_path = tmp_path / 'daily_summary.json'
    journal = AnalysisJournal(
        trade_journal=JsonlJournal(str(trades_path)),
        errors_journal=JsonlJournal(str(errors_path)),
        summary_path=str(summary_path),
        detail_level='normal',
        write_partial_summary=False,
    )

    journal.write('candidate_execution_error', {'symbol': 'AAPL', 'message': 'boom'})
    journal.finalize()

    assert not trades_path.exists()
    error_events = _read_jsonl(errors_path)
    assert error_events[0]['event_type'] == 'candidate_execution_error'

    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['errors']['by_type'] == {'candidate_execution_error': 1}


def test_analysis_journal_reduces_repeated_session_state_events(tmp_path):
    trades_path = tmp_path / 'trades.jsonl'
    errors_path = tmp_path / 'errors.jsonl'
    summary_path = tmp_path / 'daily_summary.json'
    journal = AnalysisJournal(
        trade_journal=JsonlJournal(str(trades_path)),
        errors_journal=JsonlJournal(str(errors_path)),
        summary_path=str(summary_path),
        detail_level='normal',
        write_partial_summary=False,
    )
    closed_decision = SimpleNamespace(
        session_active=False,
        collect_snapshots=False,
        new_entries_allowed=False,
        force_close_required=False,
        reason='session_closed',
        session_key=None,
    )
    active_decision = SimpleNamespace(
        session_active=True,
        collect_snapshots=True,
        new_entries_allowed=True,
        force_close_required=False,
        reason='session_tradable',
        session_key='EQUITY_US:test',
    )

    journal.write('session_state', {'symbol': 'AAPL', 'session_decision': closed_decision})
    journal.write('session_state', {'symbol': 'AAPL', 'session_decision': closed_decision})
    journal.write('session_state', {'symbol': 'AAPL', 'session_decision': active_decision})
    journal.finalize()

    trade_events = _read_jsonl(trades_path)
    assert [event['event_type'] for event in trade_events] == [
        'session_state_changed',
        'session_state_changed',
    ]
    assert trade_events[0]['payload']['new_state'] == 'closed'
    assert trade_events[1]['payload']['previous_state'] == 'closed'
    assert trade_events[1]['payload']['new_state'] == 'active'


def test_jsonl_journal_writes_gzip_when_path_ends_with_gz(tmp_path):
    journal_path = tmp_path / 'debug_decisions.jsonl.gz'
    journal = JsonlJournal(str(journal_path))

    journal.write('decision', {'symbol': 'AAPL'})

    with gzip.open(journal_path, 'rt', encoding='utf-8') as file:
        records = [json.loads(line) for line in file]
    assert records[0]['event_type'] == 'decision'
