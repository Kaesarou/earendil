import json
from types import SimpleNamespace

from app.journal.analysis_journal import AnalysisJournal
from app.journal.jsonl_journal import JsonlJournal


def test_candidate_selection_emits_standalone_entry_decision_event(tmp_path):
    trades_path = tmp_path / 'trades.jsonl'
    journal = AnalysisJournal(
        trade_journal=JsonlJournal(str(trades_path)),
        errors_journal=JsonlJournal(str(tmp_path / 'errors.jsonl')),
        summary_path=str(tmp_path / 'summary.json'),
        detail_level='normal',
        write_partial_summary=False,
        profile='balanced',
    )
    context = SimpleNamespace(version='market_context_v1', regime='risk_on')
    candidate = SimpleNamespace(
        candidate_id='candidate-1',
        symbol='AAPL',
        signal=SimpleNamespace(action='BUY'),
        score=120.0,
        rank_reason='test',
        market_context=context,
    )
    decision = SimpleNamespace(
        action='enter_now',
        reason='entry_conditions_satisfied',
        model_version='entry_router_v1',
    )
    evaluated = SimpleNamespace(
        candidate=candidate,
        entry_decision=decision,
        economics=SimpleNamespace(expected_net_profit_percent=0.4),
        tp_feasibility=SimpleNamespace(runway_score=80.0),
        tp_probability=None,
        effective_sl_tp=SimpleNamespace(take_profit_percent=1.0),
    )

    journal.write(
        'candidate_selection',
        {
            'selected_candidates': [candidate],
            'rejected_candidates': [],
            'selected_evaluated_candidates': [evaluated],
            'rejected_evaluated_candidates': [],
        },
    )

    records = [
        json.loads(line)
        for line in trades_path.read_text(encoding='utf-8').splitlines()
    ]
    entry_record = next(record for record in records if record['event_type'] == 'entry_decision')
    payload = entry_record['payload']
    assert payload['candidate_id'] == 'candidate-1'
    assert payload['selection_outcome'] == 'selected'
    assert payload['entry_model_version'] == 'entry_router_v1'
    assert payload['market_context_version'] == 'market_context_v1'
    assert payload['strategy_profile'] == 'balanced'
